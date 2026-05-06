import os
import json
import requests
from bs4 import BeautifulSoup

MEDIA_IMG = "media/images"
MEDIA_VID = "media/videos"

os.makedirs(MEDIA_IMG, exist_ok=True)
os.makedirs(MEDIA_VID, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

POST_LIMIT = 50


def load_channels():
    if not os.path.exists("list.txt"):
        return []

    with open("list.txt", "r", encoding="utf8") as f:
        return [x.strip().replace("@","") for x in f if x.strip()]


def load_db():
    if not os.path.exists("posts.json"):
        return {"channels":{}}

    with open("posts.json","r",encoding="utf8") as f:
        return json.load(f)


def save_db(db):
    with open("posts.json","w",encoding="utf8") as f:
        json.dump(db,f,ensure_ascii=False,indent=2)


def download(url,path):
    try:
        r=requests.get(url,headers=HEADERS,timeout=20)
        if r.status_code==200:
            with open(path,"wb") as f:
                f.write(r.content)
            return True
    except:
        pass
    return False


def parse_channel(channel):

    url=f"https://t.me/s/{channel}"

    r=requests.get(url,headers=HEADERS)

    soup=BeautifulSoup(r.text,"html.parser")

    posts=[]

    for msg in soup.select(".tgme_widget_message")[:POST_LIMIT]:

        msg_id = msg.get("data-post","").split("/")[-1]

        text_el = msg.select_one(".tgme_widget_message_text")
        text = text_el.get_text("\n",strip=True) if text_el else ""

        date_el = msg.select_one("time")
        date = date_el["datetime"] if date_el else ""

        image=None
        video=None

        img_el = msg.select_one(".tgme_widget_message_photo_wrap")

        if img_el:
            style = img_el.get("style","")
            if "url(" in style:
                img_url = style.split("url('")[1].split("')")[0]
                filename=f"{channel}_{msg_id}.jpg"
                path=f"{MEDIA_IMG}/{filename}"

                if not os.path.exists(path):
                    download(img_url,path)

                image=f"media/images/{filename}"

        vid_el = msg.select_one("video source")

        if vid_el:
            vid_url = vid_el.get("src")
            filename=f"{channel}_{msg_id}.mp4"
            path=f"{MEDIA_VID}/{filename}"

            if not os.path.exists(path):
                download(vid_url,path)

            video=f"media/videos/{filename}"

        posts.append({
            "id":msg_id,
            "text":text,
            "date":date,
            "image":image,
            "video":video
        })

    return posts


def merge(old,new):

    seen={p["id"]:p for p in old}

    for p in new:
        seen[p["id"]]=p

    return list(seen.values())


def main():

    db=load_db()

    channels=load_channels()

    for ch in channels:

        print("scraping:",ch)

        new=parse_channel(ch)

        old=db["channels"].get(ch,[])

        merged=merge(old,new)

        db["channels"][ch]=merged

    save_db(db)


if __name__=="__main__":
    main()
