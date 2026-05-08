#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Enterprise Telegram Mirror (Final Version)
------------------------------------------
Features:
- Full post extraction (id, text, date)
- Full media support (JPG, PNG, MP4, PDF, ZIP, APK, etc)
- External link extraction (YouTube, Twitter, Instagram, Telegram, GitHub, ...)
- Parallel download & parallel channel processing
- Safe filename handling
- Cache HTML pages (avoid rate-limit)
- Atomic DB write
- Stable retry mechanism (with exponential backoff)
- Compatible with GitHub Actions
- Compatible with viewer.html
"""

import os
import re
import json
import time
import hashlib
import shutil
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

LIST_FILE = "list.txt"
DB_FILE = "posts.json"
MEDIA_DIR = Path("media")
CACHE_DIR = Path("_cache_html")

MAX_RETRIES = 4
REQUEST_TIMEOUT = 30
BACKOFF_FACTOR = 1.8

MAX_FILE_SIZE_MB = 200
MAX_POSTS_PER_CHANNEL = 200

DOWNLOAD_THREADS = 6
CHANNEL_THREADS = 4

CHUNK_SIZE = 256 * 1024  # 256 KB

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


# ============================================================
# UTILS
# ============================================================

def log(msg: str):
    print(f"[mirror] {msg}")


def safe_filename(name: str) -> str:
    name = re.sub(r'[^a-zA-Z0-9._-]+', "_", name)
    return name[:120]


# ============================================================
# ATOMIC DB
# ============================================================

def load_db():
    if not os.path.exists(DB_FILE):
        return {"channels": {}, "last_update": None}

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        shutil.copy(DB_FILE, DB_FILE + ".corrupt")
        log("DB corrupted. Backup created.")
        return {"channels": {}, "last_update": None}


def save_db(db):
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DB_FILE)


# ============================================================
# HTML FETCH WITH CACHE
# ============================================================

def cached_get(url: str) -> str:
    CACHE_DIR.mkdir(exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()
    cache_path = CACHE_DIR / f"{key}.html"

    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    for attempt in range(MAX_RETRIES):
        try:
            r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                html = r.text
                cache_path.write_text(html, encoding="utf-8")
                return html
        except Exception:
            pass

        time.sleep(BACKOFF_FACTOR ** attempt)

    return ""


# ============================================================
# LINK EXTRACTION
# ============================================================

def extract_links(text: str) -> List[Dict]:
    if not text:
        return []

    url_pattern = r'https?://[^\s<>"\'{}|\\^`]+'
    links = []

    for match in re.finditer(url_pattern, text):
        url = match.group()
        lt = "external"

        if "t.me" in url:
            lt = "telegram"
        elif "youtube.com" in url or "youtu.be" in url:
            lt = "youtube"
        elif "twitter.com" in url or "x.com" in url:
            lt = "twitter"
        elif "instagram.com" in url:
            lt = "instagram"
        elif "github.com" in url:
            lt = "github"

        links.append({
            "url": url,
            "type": lt,
            "text": url
        })

    return links


# ============================================================
# MEDIA FILE DOWNLOAD
# ============================================================

def download_file(url: str, filepath: Path) -> bool:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp = filepath.with_suffix(filepath.suffix + ".part")

    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024

    for attempt in range(MAX_RETRIES):
        try:
            r = SESSION.get(url, stream=True, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                time.sleep(BACKOFF_FACTOR ** attempt)
                continue

            size = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(CHUNK_SIZE):
                    if chunk:
                        size += len(chunk)
                        if size > max_bytes:
                            tmp.unlink(missing_ok=True)
                            return False
                        f.write(chunk)

            tmp.replace(filepath)
            return True
        except Exception:
            time.sleep(BACKOFF_FACTOR ** attempt)

    tmp.unlink(missing_ok=True)
    return False


# ============================================================
# PARSE TELEGRAM PAGE
# ============================================================

def get_file_ext_from_url(url: str) -> str:
    u = url.lower()
    if ".jpg" in u or ".jpeg" in u:
        return ".jpg"
    if ".png" in u:
        return ".png"
    if ".mp4" in u:
        return ".mp4"
    if ".zip" in u:
        return ".zip"
    if ".apk" in u:
        return ".apk"
    if ".pdf" in u:
        return ".pdf"
    return ".file"


def fetch_posts(channel: str, existing_ids: Set[int]) -> List[Dict]:
    url = f"https://t.me/s/{channel}"
    log(f"Fetching {channel}")

    html = cached_get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    msgs = soup.select(".tgme_widget_message")

    new_posts = []

    for msg in msgs:
        data_post = msg.get("data-post")
        if not data_post:
            continue

        pid = data_post.split("/")[-1]
        if not pid.isdigit():
            continue
        pid = int(pid)

        if pid in existing_ids:
            continue

        # text
        txt_elem = msg.select_one(".tgme_widget_message_text")
        text = txt_elem.get_text("\n", strip=True) if txt_elem else ""

        # date
        t = msg.select_one("time")
        date = t.get("datetime", datetime.now().isoformat()) if t else datetime.now().isoformat()

        # links
        links = extract_links(text)

        # media
        media = []
        idx = 0

        # images
        imgs = msg.select("img")
        for img in imgs:
            src = img.get("src") or img.get("data-src")
            if src and src.startswith("http"):
                ext = get_file_ext_from_url(src)
                fname = safe_filename(f"{channel}_{pid}_{idx}{ext}")
                media.append({"type": "image", "file": fname, "url": src})
                idx += 1

        # videos & documents
        docs = msg.select("video, a[href]")
        for d in docs:
            url = d.get("src") or d.get("href")
            if url and url.startswith("http") and not any(url.endswith(ext) for ext in ["?attach=1"]):
                ext = get_file_ext_from_url(url)
                fname = safe_filename(f"{channel}_{pid}_{idx}{ext}")
                media.append({"type": "file", "file": fname, "url": url})
                idx += 1

        new_posts.append({
            "id": pid,
            "text": text,
            "date": date,
            "media": media,
            "links": links
        })

    return new_posts


# ============================================================
# MAIN MIRROR ENGINE
# ============================================================

def mirror_channel(channel: str, db: dict):
    log(f"Processing channel {channel}")

    existing_ids = {p["id"] for p in db["channels"].get(channel, [])}
    posts = fetch_posts(channel, existing_ids)

    if not posts:
        return

    # download media (parallel)
    for post in posts:
        if not post["media"]:
            continue

        def dl(m):
            fpath = MEDIA_DIR / m["file"]
            return download_file(m["url"], fpath)

        with ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS) as pool:
            pool.map(dl, post["media"])

    # write to DB
    db["channels"].setdefault(channel, [])
    db["channels"][channel].extend(posts)
    db["channels"][channel].sort(key=lambda x: x["id"], reverse=True)
    db["channels"][channel] = db["channels"][channel][:MAX_POSTS_PER_CHANNEL]


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    MEDIA_DIR.mkdir(exist_ok=True)

    if not os.path.exists(LIST_FILE):
        log("list.txt not found")
        return

    channels = [
        c.strip() for c in open(LIST_FILE, "r", encoding="utf-8")
        if c.strip() and not c.startswith("#")
    ]

    db = load_db()

    with ThreadPoolExecutor(max_workers=CHANNEL_THREADS) as pool:
        futures = {pool.submit(mirror_channel, ch, db): ch for ch in channels}
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                log(f"Channel {futures[f]} failed: {e}")

    db["last_update"] = datetime.now().isoformat()
    save_db(db)

    log("All channels done.")


if __name__ == "__main__":
    main()
