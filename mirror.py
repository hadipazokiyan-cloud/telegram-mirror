#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from pathlib import Path

BASE_URL = "https://t.me"
POST_LIMIT = 10

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

DATA_FILE = "posts.json"


def load_json():
    if not os.path.exists(DATA_FILE):
        return {"channels": {}}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "channels" not in data:
            return {"channels": {}}

        return data

    except Exception:
        return {"channels": {}}


def save_json(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def hash_url(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def download_file(url, filepath):
    if os.path.exists(filepath):
        return

    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(r.content)
            print("Saved:", filepath)
    except Exception as e:
        print("Download error:", url, e)


def extract_images(post):
    images = []

    for img in post.select("img"):
        src = img.get("src")
        if src and src.startswith("https://"):
            images.append(src)

    for div in post.select("div.tgme_widget_message_photo_wrap"):
        style = div.get("style", "")
        if "url(" in style:
            start = style.find("url(") + 4
            end = style.find(")", start)
            url = style[start:end].replace("'", "").replace('"', "")
            images.append(url)

    return images


def fetch_channel(channel):
    url = f"{BASE_URL}/{channel}"
    print("Fetching:", url)

    try:
        r = requests.get(url, timeout=20)
    except Exception as e:
        print("Request error:", e)
        return []

    if r.status_code != 200:
        print("Failed:", channel)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    raw_posts = soup.select(".tgme_widget_message")
    raw_posts = raw_posts[-POST_LIMIT:]

    posts = []

    for post in raw_posts:
        try:
            pid = post.get("data-post", "")
            if "/" in pid:
                pid = pid.split("/")[-1]

            text_el = post.select_one(".tgme_widget_message_text")
            text = text_el.get_text("\n").strip() if text_el else ""

            time_el = post.select_one("time")
            date = time_el.get("datetime") if time_el else ""

            img_urls = extract_images(post)
            local_images = []

            for i, img_url in enumerate(img_urls):
                h = hash_url(img_url)
                filename = f"{channel}_{pid}_{i}_{h}.jpg"
                filepath = MEDIA_DIR / filename

                download_file(img_url, filepath)
                local_images.append(str(filepath))

            posts.append({
                "id": pid,
                "text": text,
                "date": date,
                "images": local_images,
                "videos": []
            })

        except Exception as e:
            print("Parse error:", e)

    return posts


def read_channels():
    if not os.path.exists("list.txt"):
        print("list.txt not found")
        return []

    with open("list.txt", "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def main():
    print("Telegram Mirror Start")

    data = load_json()
    channels_db = data.get("channels", {})

    channels = read_channels()

    for channel in channels:
        print("Channel:", channel)
        posts = fetch_channel(channel)
        channels_db[channel] = posts

    data["channels"] = channels_db
    save_json(data)

    print("DONE ✅")


if __name__ == "__main__":
    main()
