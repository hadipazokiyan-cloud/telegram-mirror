import os
import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

MEDIA_DIR = "media"
POST_LIMIT = 50

os.makedirs(MEDIA_DIR, exist_ok=True)


def load_channels():
    with open("list.txt", "r", encoding="utf-8") as f:
        return [x.strip() for x in f if x.strip()]


def load_db():
    if not os.path.exists("posts.json"):
        return {"channels": {}}

    with open("posts.json", "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(data):
    with open("posts.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_extension(url):
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    if ext:
        return ext
    return ".bin"


def detect_type(ext):
    ext = ext.lower()

    if ext in [".jpg",".jpeg",".png",".webp",".gif"]:
        return "image"

    if ext in [".mp4",".mov",".webm",".mkv"]:
        return "video"

    if ext in [".mp3",".ogg",".wav",".m4a"]:
        return "audio"

    return "file"


def download_file(url, path):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            return True
    except:
        pass
    return False


def extract_media(post, channel, post_id):

    media = []
    index = 1

    # عکس
    imgs = post.select("a.tgme_widget_message_photo_wrap")

    for img in imgs:
        style = img.get("style","")
        m = re.search(r"url\('(.+?)'\)", style)

        if not m:
            continue

        url = m.group(1)
        ext = get_extension(url)

        filename = f"{channel}_{post_id}_{index}{ext}"
        path = os.path.join(MEDIA_DIR, filename)

        if not os.path.exists(path):
            download_file(url, path)

        media.append({
            "type": "image",
            "file": f"media/{filename}"
        })

        index += 1

    # ویدیو
    videos = post.select("video source")

    for v in videos:
        url = v.get("src")
        if not url:
            continue

        ext = get_extension(url)

        filename = f"{channel}_{post_id}_{index}{ext}"
        path = os.path.join(MEDIA_DIR, filename)

        if not os.path.exists(path):
            download_file(url, path)

        media.append({
            "type": "video",
            "file": f"media/{filename}"
        })

        index += 1

    # فایل‌ها
    files = post.select("a.tgme_widget_message_document")

    for f in files:
        href = f.get("href")
        if not href:
            continue

        url = urljoin("https://t.me", href)

        ext = get_extension(url)

        filename = f"{channel}_{post_id}_{index}{ext}"
        path = os.path.join(MEDIA_DIR, filename)

        if not os.path.exists(path):
            download_file(url, path)

        media.append({
            "type": detect_type(ext),
            "file": f"media/{filename}"
        })

        index += 1

    return media


def scrape_channel(channel):

    url = f"https://t.me/s/{channel}"

    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")

    posts = soup.select(".tgme_widget_message")[:POST_LIMIT]

    results = []

    for post in posts:

        post_id = post.get("data-post")

        if not post_id:
            continue

        post_id = post_id.split("/")[-1]

        text_el = post.select_one(".tgme_widget_message_text")

        text = ""
        if text_el:
            text = text_el.get_text("\n", strip=True)

        date_el = post.select_one("time")

        date = ""
        if date_el:
            date = date_el.get("datetime","")

        media = extract_media(post, channel, post_id)

        results.append({
            "id": post_id,
            "date": date,
            "text": text,
            "media": media
        })

    return results


def merge(old, new):

    old_ids = {p["id"] for p in old}

    merged = old.copy()

    for p in new:
        if p["id"] not in old_ids:
            merged.append(p)

    return merged


def main():

    channels = load_channels()

    db = load_db()

    for ch in channels:

        print("Scraping:", ch)

        new_posts = scrape_channel(ch)

        if ch not in db["channels"]:
            db["channels"][ch] = new_posts
        else:
            db["channels"][ch] = merge(db["channels"][ch], new_posts)

    save_db(db)

    print("Done.")


if __name__ == "__main__":
    main()
