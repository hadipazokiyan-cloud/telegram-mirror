import os
import json
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

POST_LIMIT = 50
MEDIA_DIR = "media"


def ensure_dirs():
    if not os.path.exists(MEDIA_DIR):
        os.makedirs(MEDIA_DIR)


def load_channels():
    channels = []
    if os.path.exists("list.txt"):
        with open("list.txt", "r", encoding="utf-8") as f:
            for line in f:
                ch = line.strip().replace("@", "")
                if ch:
                    channels.append(ch)
    return channels


def load_db():
    if not os.path.exists("posts.json"):
        return {"channels": {}}

    try:
        with open("posts.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"channels": {}}


def save_db(data):
    with open("posts.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def download_image(url, path):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            with open(path, "wb") as f:
                f.write(r.content)
            return True
    except:
        pass
    return False


def parse_channel(channel):

    url = f"https://t.me/s/{channel}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
    except:
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    posts = []

    messages = soup.select(".tgme_widget_message")

    for msg in messages[:POST_LIMIT]:

        post_id = msg.get("data-post", "")
        if "/" in post_id:
            post_id = post_id.split("/")[-1]

        text_el = msg.select_one(".tgme_widget_message_text")
        text = text_el.get_text("\n", strip=True) if text_el else ""

        time_el = msg.select_one("time")
        date = time_el.get("datetime") if time_el else ""

        image_path = None

        photo = msg.select_one(".tgme_widget_message_photo_wrap")

        if photo:
            style = photo.get("style", "")
            if "url(" in style:
                try:
                    img_url = style.split("url('")[1].split("')")[0]

                    filename = f"{channel}_{post_id}.jpg"
                    local = os.path.join(MEDIA_DIR, filename)

                    if not os.path.exists(local):
                        download_image(img_url, local)

                    image_path = f"media/{filename}"

                except:
                    pass

        posts.append({
            "id": post_id,
            "text": text,
            "date": date,
            "image": image_path
        })

    return posts


def merge_posts(old, new):

    existing = {p["id"]: p for p in old}

    for p in new:
        existing[p["id"]] = p

    return list(existing.values())


def main():

    ensure_dirs()

    db = load_db()

    channels = load_channels()

    for ch in channels:

        print("Scraping:", ch)

        new_posts = parse_channel(ch)

        old_posts = db["channels"].get(ch, [])

        merged = merge_posts(old_posts, new_posts)

        db["channels"][ch] = merged

    save_db(db)

    print("Done.")


if __name__ == "__main__":
    main()
