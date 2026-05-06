import json
import requests
import os
from xml.etree import ElementTree

CHANNEL = os.getenv("TG_CHANNEL")
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


def fetch_posts():
    r = requests.get(RSS_URL, timeout=30)
    root = ElementTree.fromstring(r.content)

    posts = []

    for item in root.findall(".//item"):
        title = item.find("title").text if item.find("title") is not None else ""
        link = item.find("link").text if item.find("link") is not None else ""
        date = item.find("pubDate").text if item.find("pubDate") is not None else ""

        posts.append({
            "text": title,
            "link": link,
            "date": date
        })

    return posts


def main():
    existing = load_existing()
    new_posts = fetch_posts()

    if new_posts:
        save(new_posts)


if __name__ == "__main__":
    main()
