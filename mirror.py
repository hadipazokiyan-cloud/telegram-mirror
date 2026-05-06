import json
import requests
import os
import re
from xml.etree import ElementTree

CHANNEL = "FVpnProxy"

OUTPUT = "posts.json"

RSS_URL = f"https://rsshub.app/telegram/channel/{CHANNEL}"
WEB_URL = f"https://t.me/s/{CHANNEL}"


def load_existing():
    if not os.path.exists(OUTPUT):
        return []
    with open(OUTPUT, "r", encoding="utf-8") as f:
        return json.load(f)


def save(posts):
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def fetch_rss():
    try:
        r = requests.get(RSS_URL, timeout=20)
        if r.status_code != 200:
            return []

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

    except:
        return []


def fetch_web():
    try:
        r = requests.get(WEB_URL, timeout=20)
        html = r.text

        posts = []

        messages = re.findall(
            r'tgme_widget_message_text.*?>(.*?)</div>',
            html,
            re.S
        )

        for i, m in enumerate(messages):
            text = re.sub("<.*?>", "", m)
            posts.append({
                "text": text.strip(),
                "link": f"https://t.me/{CHANNEL}",
                "date": ""
            })

        return posts

    except:
        return []


def main():
    print("Trying RSS...")

    posts = fetch_rss()

    if not posts:
        print("RSS failed, trying web...")
        posts = fetch_web()

    if not posts:
        print("No posts found")
        return

    save(posts)
    print(f"{len(posts)} posts saved")


if __name__ == "__main__":
    main()
