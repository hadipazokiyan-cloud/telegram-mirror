import requests
import json
import os
from bs4 import BeautifulSoup
from xml.etree import ElementTree

CHANNEL = "FVpnProxy"

SCRAPE_URL = f"https://t.me/s/{CHANNEL}"
RSS_URL = f"https://rsshub.app/telegram/channel/{CHANNEL}"

OUTPUT = "posts.json"


def load_existing():
    if not os.path.exists(OUTPUT):
        return []

    with open(OUTPUT, "r", encoding="utf-8") as f:
        return json.load(f)


def save(posts):
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def scrape_posts():

    print("Trying web scrape...")

    try:
        r = requests.get(SCRAPE_URL, timeout=30)

        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        messages = soup.find_all("div", class_="tgme_widget_message")

        posts = []

        for msg in messages:

            msg_id = msg.get("data-post")

            text_block = msg.find("div", class_="tgme_widget_message_text")
            text = text_block.get_text("\n") if text_block else ""

            date_tag = msg.find("time")
            date = date_tag.get("datetime") if date_tag else ""

            media = []

            photo = msg.find("a", class_="tgme_widget_message_photo_wrap")
            if photo and photo.get("style"):
                style = photo.get("style")
                start = style.find("url(") + 4
                end = style.find(")")
                img = style[start:end]

                media.append({
                    "type": "photo",
                    "url": img
                })

            video = msg.find("video")
            if video and video.get("src"):
                media.append({
                    "type": "video",
                    "url": video.get("src")
                })

            posts.append({
                "id": msg_id,
                "text": text,
                "date": date,
                "media": media
            })

        return posts

    except Exception as e:
        print("Scrape failed:", e)
        return []


def rss_posts():

    print("Fallback to RSS...")

    try:
        r = requests.get(RSS_URL, timeout=30)

        root = ElementTree.fromstring(r.content)

        posts = []

        for item in root.findall(".//item"):

            title = item.find("title").text if item.find("title") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            date = item.find("pubDate").text if item.find("pubDate") is not None else ""

            posts.append({
                "id": link,
                "text": title,
                "date": date,
                "media": []
            })

        return posts

    except Exception as e:
        print("RSS failed:", e)
        return []


def main():

    existing = load_existing()

    existing_ids = {p["id"] for p in existing}

    posts = scrape_posts()

    if not posts:
        posts = rss_posts()

    if not posts:
        print("No posts fetched")
        return

    new_posts = []

    for p in posts:
        if p["id"] not in existing_ids:
            new_posts.append(p)

    if new_posts:
        existing.extend(new_posts)
        save(existing)
        print(f"{len(new_posts)} new posts added")

    else:
        print("No new posts")


if __
