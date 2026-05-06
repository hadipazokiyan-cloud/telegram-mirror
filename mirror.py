import os
import json
import asyncio
import aiohttp
import random
from bs4 import BeautifulSoup
from urllib.parse import urlparse

BASE_URL = "https://t.me/s/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

POST_LIMIT = 10
MAX_DOWNLOADS = 8

MEDIA_DIR = "media"
POST_FILE = "posts.json"
CHANNEL_LIST = "list.txt"

os.makedirs(MEDIA_DIR, exist_ok=True)

download_semaphore = asyncio.Semaphore(MAX_DOWNLOADS)


def log(msg):
    print(f"[mirror] {msg}", flush=True)


def load_db():
    if not os.path.exists(POST_FILE):
        return {"channels": {}}

    with open(POST_FILE, "r", encoding="utf8") as f:
        return json.load(f)


def save_db(db):
    with open(POST_FILE, "w", encoding="utf8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def filename_from_url(url, prefix):
    path = urlparse(url).path
    name = os.path.basename(path)
    return f"{prefix}_{name}"


async def download(session, url, filename):

    path = os.path.join(MEDIA_DIR, filename)

    async with download_semaphore:

        existing = 0
        headers = {}

        if os.path.exists(path):
            existing = os.path.getsize(path)
            headers["Range"] = f"bytes={existing}-"

        for attempt in range(3):

            try:

                async with session.get(url, headers=headers, timeout=300) as r:

                    if r.status not in (200, 206):
                        raise Exception(f"HTTP {r.status}")

                    mode = "ab" if existing else "wb"

                    with open(path, mode) as f:
                        async for chunk in r.content.iter_chunked(65536):
                            f.write(chunk)

                    log(f"downloaded {filename}")
                    return path

            except Exception as e:

                log(f"retry {filename} ({attempt+1}) {e}")
                await asyncio.sleep(2)

        log(f"failed {filename}")
        return None


def extract_photo_url(style):

    if not style:
        return None

    start = style.find("url(")

    if start == -1:
        return None

    start += 4
    end = style.find(")", start)

    return style[start:end]


async def parse_channel(session, channel):

    log(f"fetch {channel}")

    async with session.get(BASE_URL + channel) as r:
        html = await r.text()

    soup = BeautifulSoup(html, "html.parser")

    posts = soup.select("[data-post]")[:POST_LIMIT]

    results = []
    tasks = []

    for p in posts:

        try:

            link = p.get("data-post")
            msg_id = link.split("/")[-1]

            text_tag = p.select_one(".tgme_widget_message_text")
            text = text_tag.get_text("\n") if text_tag else ""

            time_tag = p.find("time")
            date = time_tag["datetime"] if time_tag else ""

            media = []

            # photos
            for i, img in enumerate(p.find_all("a")):

                style = img.get("style")
                photo_url = extract_photo_url(style)

                if photo_url:

                    filename = f"{channel}_{msg_id}_{i}.jpg"

                    tasks.append(download(session, photo_url, filename))

                    media.append(os.path.join(MEDIA_DIR, filename))

            # videos
            for video in p.find_all("video"):

                src = video.get("src")

                if src:

                    filename = filename_from_url(src, f"{channel}_{msg_id}")

                    tasks.append(download(session, src, filename))

                    media.append(os.path.join(MEDIA_DIR, filename))

            # documents / files
            for a in p.find_all("a", href=True):

                href = a["href"]

                if "/file/" in href or "/document/" in href:

                    filename = filename_from_url(href, f"{channel}_{msg_id}")

                    tasks.append(download(session, href, filename))

                    media.append(os.path.join(MEDIA_DIR, filename))

            results.append({
                "id": msg_id,
                "text": text,
                "date": date,
                "media": media
            })

        except Exception as e:

            log(f"parse error {channel} {e}")

    await asyncio.gather(*tasks)

    return results


def merge(db, channel, posts):

    if channel not in db["channels"]:
        db["channels"][channel] = []

    existing = {p["id"] for p in db["channels"][channel]}

    added = 0

    for p in posts:

        if p["id"] not in existing:
            db["channels"][channel].append(p)
            added += 1

    log(f"{channel} +{added}")


async def main():

    log("start")

    db = load_db()

    if not os.path.exists(CHANNEL_LIST):
        log("list.txt not found")
        return

    with open(CHANNEL_LIST) as f:
        channels = [x.strip() for x in f if x.strip()]

    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:

        for ch in channels:

            try:

                posts = await parse_channel(session, ch)

                merge(db, ch, posts)

                await asyncio.sleep(random.uniform(2, 4))

            except Exception as e:

                log(f"channel error {ch} {e}")

    save_db(db)

    log("done")


if __name__ == "__main__":
    asyncio.run(main())
