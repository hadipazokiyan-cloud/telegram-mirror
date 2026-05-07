#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import hashlib
import shutil
import requests
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(".")
MEDIA_DIR = DATA_DIR / "media"
POSTS_FILE = DATA_DIR / "posts.json"

MEDIA_DIR.mkdir(exist_ok=True)


# -------------------------------------------------------
# Utility
# -------------------------------------------------------

def load_posts():
    if POSTS_FILE.exists():
        with open(POSTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_posts(db):
    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def sha1_bytes(b):
    return hashlib.sha1(b).hexdigest()[:12]


def unique_filename(channel, post_id, index, content_bytes, ext):
    digest = sha1_bytes(content_bytes)
    return f"{channel}_{post_id}_{index}_{digest}{ext}"


# -------------------------------------------------------
# Download Media (Safe & Atomic)
# -------------------------------------------------------

def download_file(url, dest_file):
    temp_file = dest_file + ".part"

    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return False

        with open(temp_file, "wb") as f:
            f.write(r.content)

        if os.path.getsize(temp_file) == 0:
            os.remove(temp_file)
            return False

        # Atomic rename
        os.replace(temp_file, dest_file)
        return True

    except Exception:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False


# -------------------------------------------------------
# Cleanup unused media
# -------------------------------------------------------

def cleanup_unused_media(db):
    used = set()

    for channel in db.values():
        for p in channel:
            for m in p.get("media", []):
                used.add(m["file"])

    for fname in os.listdir(MEDIA_DIR):
        if fname not in used:
            os.remove(MEDIA_DIR / fname)


# -------------------------------------------------------
# Main Sync Function
# -------------------------------------------------------

def sync_channel(channel_name, posts_from_telegram):
    """
    posts_from_telegram باید لیست پست‌ها باشد:
    هر پست شامل:
    {
        "id": 123,
        "text": "...",
        "date": "...",
        "media_urls": [ "https://..." , ... ]
    }
    """

    db = load_posts()
    channel_posts = db.get(channel_name, [])

    new_posts = []

    for p in posts_from_telegram:
        post_id = p["id"]

        new_post = {
            "id": post_id,
            "text": p.get("text", ""),
            "date": p.get("date", ""),
            "media": []
        }

        # download media
        for i, url in enumerate(p.get("media_urls", [])):
            try:
                ext = os.path.splitext(url)[1]
                if not ext:
                    ext = ".jpg"

                r = requests.get(url, timeout=10)
                if r.status_code != 200:
                    continue

                data = r.content
                name = unique_filename(channel_name, post_id, i, data, ext)
                filepath = MEDIA_DIR / name

                # write atomically
                tmp = str(filepath) + ".part"
                with open(tmp, "wb") as f:
                    f.write(data)

                if os.path.getsize(tmp) == 0:
                    os.remove(tmp)
                    continue

                os.replace(tmp, filepath)

                new_post["media"].append({
                    "url": url,
                    "file": name
                })

            except:
                pass

        new_posts.append(new_post)

    # sort descending by ID, keep last 10
    new_posts_sorted = sorted(new_posts, key=lambda x: x["id"], reverse=True)[:10]
    db[channel_name] = new_posts_sorted

    # cleanup
    cleanup_unused_media(db)

    save_posts(db)


# -------------------------------------------------------
# Example Usage (your workflow will call sync_channel)
# -------------------------------------------------------

if __name__ == "__main__":
    # Example:
    # Replace this with your Telegram download logic.
    sample = [
        {
            "id": 101,
            "text": "Hello World",
            "date": str(datetime.now()),
            "media_urls": [
                "https://picsum.photos/300/200"
            ]
        }
    ]

    sync_channel("mychannel", sample)
    print("Done.")
