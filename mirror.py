import requests
import json
import os
from bs4 import BeautifulSoup
from xml.etree import ElementTree

CHANNEL = "ZibaNabz"

SCRAPE_URL = f"https://t.me/s/{CHANNEL}"
RSS_URL = f"https://rsshub.app/telegram/channel/{CHANNEL}"

OUTPUT = "posts.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


def load_existing():
    if not os.path.exists(OUTPUT):
        return []

    try:
        with open(OUTPUT, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save(posts):
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def scrape_posts():

    print("Trying web scrape...")

    try:
        r = requests.get(SCRAPE_URL, headers=HEADERS, timeout=30)

        if r.status_code != 200:
            print("Scrape HTTP error:", r.status_code)
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

        print(f"Scraped {len(posts)} posts")

        return posts

    except Exception as e:
        print("Scrape failed:", e)
        return []


def rss_posts():

    print("Trying RSS fallback...")

    try:
        r = requests.get(RSS_URL, headers=HEADERS, timeout=30)

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

        print(f"RSS fetched {len(posts)} posts")

        return posts

    except Exception as e:
        print("RSS failed:", e)
        return []


def main():

    existing = load_existing()

    existing_ids = {p["id"] for p in existing}

    posts = scrape_posts()

    if not posts:
        print("Scrape returned nothing, trying RSS")
        posts = rss_posts()

    if not posts:
        print("Nothing fetched, exiting safely")
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


if __name__ == "__main__":
    main()
