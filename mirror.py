import os
import re
import json
import requests
from pathlib import Path
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
}

POST_LIMIT = 50
MAX_POSTS_PER_CHANNEL = 200
MEDIA_DIR = "media"


def load_channels():
    if not os.path.exists("list.txt"):
        print("list.txt not found")
        return []

    with open("list.txt", "r", encoding="utf-8") as f:
        channels = []
        for line in f:
            ch = line.strip().replace("@", "")
            if ch:
                channels.append(ch)
        return channels


def load_old_data():
    if not os.path.exists("posts.json"):
        return {"channels": {}}

    try:
        with open("posts.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"channels": {}}
            if "channels" not in data:
                data["channels"] = {}
            return data
    except Exception:
        return {"channels": {}}


def save_data(data):
    with open("posts.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def extract_bg_url(style_value):
    if not style_value:
        return None
    m = re.search(r"url\(['\"]?(.*?)['\"]?\)", style_value)
    if not m:
        return None
    return m.group(1)


def ensure_media_dir():
    Path(MEDIA_DIR).mkdir(parents=True, exist_ok=True)


def download_image(url, channel, post_id):
    if not url:
        return None

    ensure_media_dir()

    ext = ".jpg"
    lower_url = url.lower()
    if ".png" in lower_url:
        ext = ".png"
    elif ".webp" in lower_url:
        ext = ".webp"
    elif ".jpeg" in lower_url:
        ext = ".jpg"

    filename = f"{channel}_{post_id}{ext}"
    filepath = os.path.join(MEDIA_DIR, filename)

    # اگر قبلاً دانلود شده، دوباره دانلود نکن
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return filepath.replace("\\", "/")

    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"image download failed [{channel}/{post_id}] status={r.status_code}")
            return None

        with open(filepath, "wb") as f:
            f.write(r.content)

        return filepath.replace("\\", "/")
    except Exception as e:
        print(f"image download error [{channel}/{post_id}]: {e}")
        return None


def parse_channel(channel):
    url = f"https://t.me/s/{channel}"
    r = requests.get(url, headers=HEADERS, timeout=30)

    if r.status_code != 200:
        raise Exception(f"request failed with status {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")
    blocks = soup.select(".tgme_widget_message")[:POST_LIMIT]

    posts = []

    for block in blocks:
        data_post = block.get("data-post")
        if not data_post or "/" not in data_post:
            continue

        try:
            pid = int(data_post.split("/")[-1])
        except Exception:
            continue

        text_el = block.select_one(".tgme_widget_message_text")
        text = clean_text(text_el.get_text(" ", strip=True) if text_el else "")

        time_el = block.select_one("time")
        date = time_el.get("datetime", "") if time_el else ""

        image_path = None
        photo_wrap = block.select_one(".tgme_widget_message_photo_wrap")
        if photo_wrap:
            style = photo_wrap.get("style", "")
            raw_img_url = extract_bg_url(style)
            if raw_img_url:
                image_path = download_image(raw_img_url, channel, pid)

        post = {
            "id": pid,
            "text": text,
            "date": date,
            "image": image_path
        }

        posts.append(post)

    return posts


def merge_posts(old_posts, new_posts):
    by_id = {}

    for p in old_posts:
        if "id" in p:
            by_id[p["id"]] = p

    for p in new_posts:
        pid = p.get("id")
        if not pid:
            continue

        if pid in by_id:
            # اگر پست قبلاً بوده ولی عکس نداشته و الان دارد، بروزرسانی کن
            old_item = by_id[pid]

            if not old_item.get("text") and p.get("text"):
                old_item["text"] = p["text"]

            if not old_item.get("date") and p.get("date"):
                old_item["date"] = p["date"]

            if not old_item.get("image") and p.get("image"):
                old_item["image"] = p["image"]

            by_id[pid] = old_item
        else:
            by_id[pid] = p

    merged = list(by_id.values())
    merged.sort(key=lambda x: x.get("id", 0), reverse=True)

    return merged[:MAX_POSTS_PER_CHANNEL]


def main():
    channels = load_channels()
    if not channels:
        print("No channels found in list.txt")
        return

    data = load_old_data()

    if "channels" not in data:
        data["channels"] = {}

    for channel in channels:
        print(f"Scraping channel: {channel}")

        try:
            new_posts = parse_channel(channel)
            old_posts = data["channels"].get(channel, [])
            merged = merge_posts(old_posts, new_posts)
            data["channels"][channel] = merged
            print(f"Saved {len(merged)} posts for {channel}")
        except Exception as e:
            print(f"Error in channel {channel}: {e}")
            continue

    save_data(data)
    print("Done.")


if __name__ == "__main__":
    main()
