import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import mirror


class MirrorUtilityTests(unittest.TestCase):
    def test_safe_filename_replaces_unsafe_chars_and_preserves_extension(self):
        unsafe = "bad/name:with spaces?.jpg"
        self.assertEqual(mirror.safe_filename(unsafe), "bad_name_with_spaces_.jpg")

    def test_safe_filename_truncates_long_names(self):
        filename = "a" * 250 + ".png"
        result = mirror.safe_filename(filename)
        self.assertLessEqual(len(result), 200)
        self.assertTrue(result.endswith(".png"))

    def test_get_extension_from_url_handles_paths_and_query_strings(self):
        self.assertEqual(mirror.get_extension_from_url("https://example.com/file.MP4?x=1"), ".mp4")
        self.assertEqual(mirror.get_extension_from_url("https://example.com/download?id=1&name=image.jpg"), ".jpg")
        self.assertIsNone(mirror.get_extension_from_url("https://example.com/page"))

    def test_is_valid_media_url_rejects_telegram_and_non_media_urls(self):
        self.assertTrue(mirror.is_valid_media_url("https://cdn.example.com/photo.webp"))
        self.assertFalse(mirror.is_valid_media_url("https://t.me/channel/123"))
        self.assertFalse(mirror.is_valid_media_url("https://example.com/index.html"))
        self.assertFalse(mirror.is_valid_media_url(None))

    def test_extract_links_from_text_deduplicates_and_classifies_links(self):
        text = (
            "See https://github.com/example/repo and https://youtu.be/abc "
            "then https://github.com/example/repo again"
        )
        links = mirror.extract_links_from_text(text)
        self.assertEqual([link["type"] for link in links], ["github", "youtube"])
        self.assertEqual(len(links), 2)

    def test_randomize_request_order_can_be_disabled(self):
        items = ["a", "b", "c"]
        with patch.dict(mirror.CONFIG["optimization"], {"randomize_request_order": False}):
            self.assertIs(mirror.randomize_request_order(items), items)


class MirrorParsingTests(unittest.TestCase):
    def setUp(self):
        self.processing_patch = patch.dict(
            mirror.CONFIG["processing"],
            {"skip_old_posts": True, "extract_links": True, "max_text_length": 10000},
        )
        self.time_patch = patch.dict(mirror.CONFIG["time"], {"max_post_age_hours": 48})
        self.processing_patch.start()
        self.time_patch.start()

    def tearDown(self):
        self.processing_patch.stop()
        self.time_patch.stop()

    def test_parse_posts_extracts_text_links_and_media(self):
        recent_date = datetime.now().isoformat()
        html = f"""
        <div class="tgme_widget_message" data-post="sample/101">
          <time datetime="{recent_date}"></time>
          <div class="tgme_widget_message_text">
            Hello https://github.com/example/repo
          </div>
          <img src="https://cdn.example.com/photo.jpg">
          <video src="https://cdn.example.com/movie.mp4"></video>
          <a href="https://cdn.example.com/doc.pdf">doc</a>
        </div>
        """
        posts = mirror.parse_posts(html, "sample", existing_ids=set())

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["id"], 101)
        self.assertIn("Hello", posts[0]["text"])
        self.assertEqual(posts[0]["links"][0]["type"], "github")
        self.assertEqual([item["type"] for item in posts[0]["media"]], ["image", "video", "document"])

    def test_parse_posts_skips_existing_ids_and_old_posts(self):
        old_date = (datetime.now() - timedelta(hours=72)).isoformat()
        recent_date = datetime.now().isoformat()
        html = f"""
        <div class="tgme_widget_message" data-post="sample/201">
          <time datetime="{old_date}"></time>
          <div class="tgme_widget_message_text">old</div>
        </div>
        <div class="tgme_widget_message" data-post="sample/200">
          <time datetime="{recent_date}"></time>
          <div class="tgme_widget_message_text">existing</div>
        </div>
        """
        self.assertEqual(mirror.parse_posts(html, "sample", existing_ids={200}), [])


class MirrorFileOperationTests(unittest.TestCase):
    def test_load_channels_strips_at_signs_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            list_file = Path(tmpdir) / "list.txt"
            list_file.write_text("# comment\n@first\n\nsecond\n", encoding="utf-8")

            with patch.dict(mirror.CONFIG["paths"], {"list_file": str(list_file)}), \
                 patch("mirror.randomize_request_order", side_effect=lambda channels: channels):
                self.assertEqual(mirror.load_channels(), ["first", "second"])

    def test_save_database_writes_statistics_atomically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "posts.json"
            db = {
                "channels": {
                    "sample": [
                        {"id": 1, "media": [{"file": "a.jpg"}], "links": [{"url": "https://example.com"}]},
                        {"id": 2, "media": [], "links": []},
                    ]
                }
            }

            with patch.dict(mirror.CONFIG["paths"], {"db_file": str(db_file)}):
                mirror.save_database(db)

            saved = json.loads(db_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["statistics"]["total_posts"], 2)
            self.assertEqual(saved["statistics"]["total_media"], 1)
            self.assertEqual(saved["statistics"]["total_links"], 1)
            self.assertIn("last_update", saved)

    def test_download_post_media_keeps_only_successful_downloads(self):
        post = {
            "id": 1,
            "media": [
                {"type": "image", "file": "ok.jpg", "url": "https://example.com/ok.jpg"},
                {"type": "image", "file": "bad.jpg", "url": "https://example.com/bad.jpg"},
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(mirror.CONFIG["paths"], {"media_dir": Path(tmpdir)}), \
                 patch.dict(mirror.CONFIG["processing"], {"organize_media_by_type": False}), \
                 patch("mirror.download_file", side_effect=[True, False]) as mocked_download:
                result = mirror.download_post_media(post, "sample")

            self.assertEqual(result["media"], [{"type": "image", "file": "ok.jpg"}])
            self.assertEqual(mocked_download.call_count, 2)


class MirrorNetworkTests(unittest.TestCase):
    def test_fetch_html_uses_fresh_cache_without_network_request(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            url = "https://example.com/page"
            cache_key = mirror.hashlib.sha1(url.encode()).hexdigest()
            (cache_dir / f"{cache_key}.html").write_text("<html>cached</html>", encoding="utf-8")

            with patch.dict(mirror.CONFIG["paths"], {"cache_dir": cache_dir}), \
                 patch.dict(mirror.CONFIG["network"]["cache"], {"enabled": True, "ttl_seconds": 7200}), \
                 patch("mirror.time.sleep"), \
                 patch.object(mirror.SESSION, "get", Mock(side_effect=AssertionError("network should not be used"))):
                self.assertEqual(mirror.fetch_html(url), "<html>cached</html>")


if __name__ == "__main__":
    unittest.main()
