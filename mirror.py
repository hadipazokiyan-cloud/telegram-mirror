import requests
import json
import os
from bs4 import BeautifulSoup
from datetime import datetime
import xml.etree.ElementTree as ET

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

LIST_FILE = "list.txt"
OUTPUT_FILE = "posts.json"


def clean_url(url):
    if not url:
        return ""
    return str(url).strip().replace('"', '').replace("'", "")


def scrape_channel(channel):

    url = f"https://t.me/s/{channel}"

    r = requests.get(url, headers=HEADERS, timeout=30)

    if r.status_code != 200:
        raise Exception("scrape failed")

    soup = BeautifulSoup(r.text, "html.parser")

    posts = []

    messages = soup.select(".tgme_widget_message")

    for m in messages:

        post_id = m.get("data-post")

        text_el = m.select_one(".tgme_widget_message_text")

        text = text_el.get_text("\n") if text_el else ""

        date_el = m.select_one("time")

        date = date_el["datetime"] if date_el else None

        media = []

        photo = m.select_one(".tgme_widget_message_photo_wrap")

        if photo:
            style = photo.get("style", "")
            if "url(" in style:
                url = style.split("url(")[1].split(")")[0]
                media.append({
                    "type": "photo",
                    "url": clean_url(url)
                })

        video = m.select_one("video")

        if video and video.get("src"):
            media.append({
                "type": "video",
                "url": clean_url(video.get("src"))
            })

        posts.append({
            "id": post_id,
            "text": text,
            "date": date,
            "media": media
        })

    return posts


def rss_fallback(channel):

    url = f"https://rsshub.app/telegram/channel/{channel}"

    r = requests.get(url, headers=HEADERS, timeout=30)

    if r.status_code != 200:
        return []

    root = ET.fromstring(r.text)

    posts = []

    for item in root.findall(".//item"):

        title = item.findtext("title")
        link = item.findtext("link")
        date = item.findtext("pubDate")

        posts.append({
            "id": link,
            "text": title,
            "date": date,
            "media": []
        })

    return posts


def load_channels():

    if not os.path.exists(LIST_FILE):
        return []

    with open(LIST_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    channels = []

    for l in lines:
        l = l.strip()
        if l:
            channels.append(l)

    return channels


def load_existing():

    if not os.path.exists(OUTPUT_FILE):
        return {"channels": {}}

    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(data):

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():

    channels = load_channels()

    data = load_existing()

    if "channels" not in data:
        data["channels"] = {}

    for ch in channels:

        print("fetching", ch)

        try:

            posts = scrape_channel(ch)

            if not posts:
                raise Exception()

        except:

            print("scrape failed, trying rss", ch)

            posts = rss_fallback(ch)

        if not posts:
            print("no posts", ch)
            continue

        data["channels"][ch] = posts

        print("saved", ch, len(posts))

    save(data)

    print("done")


if __name__ == "__main__":
    main()
