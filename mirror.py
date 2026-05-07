# mirror.py
# نسخه نهایی و پایدار
# Async – Multi‑channel – Auto‑resume – Clean merge – Ultra compatible

import aiohttp
import asyncio
import os
import json
import re
from bs4 import BeautifulSoup

DB_FILE = "posts.json"
LIST_FILE = "list.txt"
MEDIA_DIR = "media"

MAX_POSTS_PER_CHANNEL = 10
MAX_CONCURRENT = 8  # تعداد دانلودهای موازی
sem = asyncio.Semaphore(MAX_CONCURRENT)

TELEGRAM_BASE = "https://t.me/"

# -----------------------------------------------------
# Load + Save Database
# -----------------------------------------------------

def load_db():
    if not os.path.exists(DB_FILE):
        return {"channels": {}}
    with open(DB_FILE, "r", encoding="utf8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

# -----------------------------------------------------
# Utilities
# -----------------------------------------------------

def safe_filename(channel, post_id, index, ext):
    return f"{channel}_{post_id}_{index}{ext}"

async def fetch_html(session, url):
    try:
        async with session.get(url, timeout=12) as r:
            if r.status == 200:
                return await r.text()
    except:
        return None
    return None

# -----------------------------------------------------
# Extract media URLs from Telegram HTML
# -----------------------------------------------------

def extract_media_urls(html):
    soup = BeautifulSoup(html, "html.parser")

    links = []

    # عکس‌ها
    for img in soup.select("a[href*='.jpg'], a[href*='.png'], a[href*='.webp']"):
        links.append(img.get("href"))

    # ویدیوها
    for vid in soup.select("a[href*='.mp4']"):
        links.append(vid.get("href"))

    # انواع فایل مثل zip, apk, pdf, rar
    for filetag in soup.select("a[href*='.zip'], a[href*='.apk'], a[href*='.pdf'], a[href*='.rar'], a[href*='.doc'], a[href*='.docx'], a[href*='.txt']"):
        links.append(filetag.get("href"))

    return list(dict.fromkeys(links))

# -----------------------------------------------------
# Download media with resume
# -----------------------------------------------------

async def download_file(session, url, path):

    async with sem:

        tmp_path = path + ".part"

        # اگر قبلاً کامل دانلود شده، رد شو
        if os.path.exists(path):
            return True

        # اگر فایل نیمه‌کاره وجود دارد
        headers = {}
        resume_pos = 0

        if os.path.exists(tmp_path):
            resume_pos = os.path.getsize(tmp_path)
            headers["Range"] = f"bytes={resume_pos}-"

        try:
            async with session.get(url, headers=headers) as r:
                if r.status in (200, 206):

                    # ایجاد پوشه
                    os.makedirs(os.path.dirname(path), exist_ok=True)

                    mode = "ab" if resume_pos > 0 else "wb"

                    with open(tmp_path, mode) as f:
                        async for chunk in r.content.iter_chunked(2048):
                            f.write(chunk)

                    os.rename(tmp_path, path)
                    print(f"[mirror] downloaded {path}")
                    return True

        except Exception as e:
            print(f"[mirror] download error {url}: {e}")

        return False

# -----------------------------------------------------
# Scrape a single post
# -----------------------------------------------------

async def scrape_post(session, channel, post_id):
    url = f"{TELEGRAM_BASE}{channel}/{post_id}"
    html = await fetch_html(session, url)

    if not html:
        return None

    media_urls = extract_media_urls(html)

    soup = BeautifulSoup(html, "html.parser")

    # متن پست
    text_tag = soup.select_one(".tgme_widget_message_text")
    text = text_tag.get_text("\n") if text_tag else ""

    # تاریخ
    date_tag = soup.select_one("time")
    date = date_tag.get("datetime") if date_tag else ""

    # ساختن لیست رسانه
    media_paths = []
    index = 0

    for m in media_urls:
        ext = os.path.splitext(m)[1].lower().split("?")[0]
        if not ext:
            ext = ".bin"

        filename = safe_filename(channel, post_id, index, ext)
        filepath = f"{MEDIA_DIR}/{filename}"
        media_paths.append(filepath)
        index += 1

    return {
        "id": str(post_id),
        "text": text,
        "date": date,
        "media": media_paths
    }, media_urls

# -----------------------------------------------------
# Merge database safely
# -----------------------------------------------------

def merge_posts(db, channel, new_posts):
    if channel not in db["channels"]:
        db["channels"][channel] = []

    existing_ids = {p["id"] for p in db["channels"][channel]}

    for p in new_posts:
        if p["id"] not in existing_ids:
            db["channels"][channel].append(p)

    # مرتب‌سازی نزولی
    db["channels"][channel].sort(key=lambda x: int(x["id"]), reverse=True)

    # محدود کردن دیتابیس
    db["channels"][channel] = db["channels"][channel][:500]

# -----------------------------------------------------
# Scrape Channel
# -----------------------------------------------------

async def scrape_channel(session, channel, db):

    print(f"[mirror] scraping channel {channel} ...")

    # آخرین 10 پست
    post_ids = list(range(1, MAX_POSTS_PER_CHANNEL + 1))

    # ابتدا شماره پست‌ها را با regex پیدا می‌کنیم
    main = await fetch_html(session, f"{TELEGRAM_BASE}{channel}")

    if main:
        ids = re.findall(rf"{channel}/(\d+)", main)
        if ids:
            ids = sorted({int(x) for x in ids}, reverse=True)
            post_ids = ids[:MAX_POSTS_PER_CHANNEL]

    new_posts = []
    media_tasks = []

    for pid in post_ids:
        result = await scrape_post(session, channel, pid)
        if not result:
            continue

        post, media_urls = result
        new_posts.append(post)

        # ایجاد تسک دانلود
        for idx, url in enumerate(media_urls):
            path = post["media"][idx]
            media_tasks.append(download_file(session, url, path))

    # دانلود تمام مدیاها
    await asyncio.gather(*media_tasks)

    # ادغام با دیتابیس
    merge_posts(db, channel, new_posts)

    print(f"[mirror] done {channel}: {len(new_posts)} posts")

# -----------------------------------------------------
# MAIN
# -----------------------------------------------------

async def main():

    if not os.path.exists(LIST_FILE):
        print("[mirror] list.txt not found")
        return

    with open(LIST_FILE, "r", encoding="utf8") as f:
        channels = [x.strip().replace("@", "") for x in f if x.strip()]

    if not channels:
        print("[mirror] list is empty")
        return

    db = load_db()

    async with aiohttp.ClientSession() as session:
        for ch in channels:
            await scrape_channel(session, ch, db)

    save_db(db)

    print("[mirror] all done")

if __name__ == "__main__":
    asyncio.run(main())
