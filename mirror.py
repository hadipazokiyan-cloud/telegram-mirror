import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

POST_LIMIT = 50


def load_channels():
    if not os.path.exists("list.txt"):
        return []
    with open("list.txt", "r", encoding="utf-8") as f:
        return [x.strip().replace("@","") for x in f if x.strip()]


def load_old():
    if not os.path.exists("posts.json"):
        return {"channels": {}}

    try:
        with open("posts.json","r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"channels": {}}


def clean_text(t):
    if not t:
        return ""
    return re.sub(r"\s+", " ", t).strip()


def parse_channel(channel):
    url = f"https://t.me/s/{channel}"
    r = requests.get(url, headers=HEADERS, timeout=20)

    if r.status_code != 200:
        raise Exception("request failed")

    soup = BeautifulSoup(r.text,"html.parser")

    posts = []

    blocks = soup.select(".tgme_widget_message")[:POST_LIMIT]

    for b in blocks:

        post_id = b.get("data-post")
        if not post_id:
            continue

        try:
            pid = int(post_id.split("/")[-1])
        except:
            continue

        text_el = b.select_one(".tgme_widget_message_text")
        text = clean_text(text_el.get_text(" ",strip=True) if text_el else "")

        date_el = b.select_one("time")
        date = date_el.get("datetime") if date_el else ""

        img = None
        photo = b.select_one(".tgme_widget_message_photo_wrap")
        if photo:
            style = photo.get("style","")
            m = re.search(r"url\('(.*?)'\)",style)
            if m:
                img = m.group(1)

        posts.append({
            "id": pid,
            "text": text,
            "date": date,
            "image": img
        })

    return posts


def merge(old_posts,new_posts):

    ids = {p["id"] for p in old_posts}

    for p in new_posts:
        if p["id"] not in ids:
            old_posts.append(p)

    old_posts.sort(key=lambda x:x["id"], reverse=True)

    return old_posts[:200]


def main():

    channels = load_channels()

    if not channels:
        print("no channels")
        return

    data = load_old()

    if "channels" not in data:
        data["channels"] = {}

    for ch in channels:

        print("scraping",ch)

        try:
            new_posts = parse_channel(ch)
        except Exception as e:
            print("error:",ch,e)
            continue

        old_posts = data["channels"].get(ch,[])

        merged = merge(old_posts,new_posts)

        data["channels"][ch] = merged

        print("posts:",len(merged))

    with open("posts.json","w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)

    print("done")


if __name__ == "__main__":
    main()
