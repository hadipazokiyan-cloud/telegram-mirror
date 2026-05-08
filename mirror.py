#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Mirror Ultra - Final Production Version
-----------------------------------------------

ویژگی‌ها:
- خواندن لیست کانال‌ها از list.txt
- گرفتن آخرین 10 پست هر کانال از t.me
- استخراج متن، تاریخ، عکس‌ها و ویدیوها از HTML عمومی تلگرام
- دانلود موازی رسانه‌ها (async) با محدودیت همزمانی
- ذخیره‌ی محلی رسانه‌ها در پوشه media/
- تولید و به‌روزرسانی posts.json با ساختار سازگار با viewer.html
- ادغام امن (merge) پست‌ها و جلوگیری از corruption
- حذف پست‌های تکراری بر اساس id
"""

import aiohttp
import asyncio
import json
import os
import re
import hashlib
from bs4 import BeautifulSoup
from pathlib import Path

# -----------------------------
# تنظیمات کلی
# -----------------------------
POST_LIMIT = 10          # تعداد پست‌هایی که از هر کانال نگه می‌داریم
MAX_DOWNLOADS = 6        # حداکثر دانلود همزمان
TIMEOUT = 18             # timeout درخواست‌ها (ثانیه)

BASE_URL = "https://t.me"
DATA_FILE = "posts.json"
MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

semaphore = asyncio.Semaphore(MAX_DOWNLOADS)


# -----------------------------
# توابع کمکی JSON امن
# -----------------------------
def load_json_safe():
    """
    posts.json را به‌صورت امن می‌خواند.
    اگر خراب باشد یا ساختار اشتباه داشته باشد، ساختار سالم برمی‌گرداند.
    """
    if not os.path.exists(DATA_FILE):
        return {"channels": {}}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"channels": {}}

        channels = data.get("channels", {})
        if not isinstance(channels, dict):
            return {"channels": {}}

        clean_channels = {}
        for ch_name, posts in channels.items():
            if not isinstance(posts, list):
                continue
            cleaned_list = []
            for p in posts:
                if isinstance(p, dict) and "id" in p:
                    cleaned_list.append(p)
            clean_channels[ch_name] = cleaned_list

        return {"channels": clean_channels}

    except Exception:
        # در صورت هر نوع خطای parsing، فایل را نادیده می‌گیریم و از صفر شروع می‌کنیم
        return {"channels": {}}


def save_json_safe(data):
    """
    ذخیره‌ی امن JSON:
    - ابتدا در فایل .tmp
    - سپس os.replace برای جلوگیری از corruption
    """
    tmp_path = DATA_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, DATA_FILE)


# -----------------------------
# دانلود رسانه به‌صورت async
# -----------------------------
async def download_file(url: str, dest_path: Path) -> bool:
    """
    دانلود یک فایل با پشتیبانی از:
    - محدودیت همزمانی (Semaphore)
    - ذخیره‌ی موقت .part و rename اتمیک
    """
    async with semaphore:
        temp_path = dest_path.with_suffix(dest_path.suffix + ".part")

        try:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status not in (200, 206):
                        print(f"❌ Download failed ({resp.status}): {url}")
                        return False

                    with open(temp_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(4096):
                            if not chunk:
                                continue
                            f.write(chunk)

            if temp_path.stat().st_size == 0:
                temp_path.unlink(missing_ok=True)
                print(f"❌ Empty file for: {url}")
                return False

            os.replace(temp_path, dest_path)
            print(f"✔ Saved: {dest_path}")
            return True

        except Exception as e:
            print(f"❌ Error downloading {url}: {e}")
            temp_path.unlink(missing_ok=True)
            return False


# -----------------------------
# استخراج رسانه از HTML یک پست
# -----------------------------
def extract_media_from_post(post_soup: BeautifulSoup):
    """
    از یک عنصر .tgme_widget_message:
    - لینک تصاویر
    - لینک ویدیوها
    را استخراج می‌کند.
    """
    images = []
    videos = []

    # 1) تگ‌های <img> با کلاس media_photo
    for img in post_soup.select("img.media_photo"):
        src = img.get("src") or img.get("data-src")
        if src:
            images.append(src)

    # 2) تگ‌های <video>
    for v in post_soup.select("video"):
        src = v.get("src")
        if src:
            videos.append(src)

    # 3) پس‌زمینه‌هایی که به صورت CSS (background-image:url(...)) هستند
    for div in post_soup.select("div.tgme_widget_message_photo_wrap, div.tgme_widget_message_photo"):
        style = div.get("style", "")
        if "url(" in style:
            m = re.search(r"url\((['\"]?)(.*?)\1\)", style)
            if m:
                images.append(m.group(2))

    # 4) data-video در divهای ویدیو
    for div in post_soup.select("div.tgme_widget_message_video"):
        src = div.get("data-video")
        if src:
            videos.append(src)

    return images, videos


def local_media_name(channel: str, post_id: str, index: int, url: str, kind: str) -> str:
    """
    یک نام یکتا برای فایل رسانه‌ای تولید می‌کند:
    kind = "img" یا "vid"
    """
    # hash روی URL برای یکتا بودن
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]

    # تعیین پسوند
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if not ext or len(ext) > 5:
        ext = ".jpg" if kind == "img" else ".mp4"

    return f"{channel}_{post_id}_{index}_{digest}{ext}"


# -----------------------------
# گرفتن پست‌های یک کانال از t.me
# -----------------------------
async def fetch_channel_posts(session: aiohttp.ClientSession, channel: str):
    """
    صفحه‌ی وب https://t.me/<channel> را می‌گیرد و آخرین POST_LIMIT پست را استخراج می‌کند.
    خروجی: لیستی از دیکشنری‌ها:
    {
      "id": "12345",
      "text": "...",
      "date": "...",
      "images": [local_paths...],
      "videos": [local_paths...],
      "remote_images": [urls...],
      "remote_videos": [urls...]
    }
    """
    url = f"{BASE_URL}/{channel}"
    print(f"🔎 Fetch: {url}")

    async with session.get(url) as resp:
        if resp.status != 200:
            print(f"❌ Cannot fetch channel {channel}: HTTP {resp.status}")
            return []

        html = await resp.text()

    soup = BeautifulSoup(html, "html.parser")
    raw_posts = soup.select(".tgme_widget_message")

    if not raw_posts:
        print(f"⚠ No posts found for channel: {channel}")
        return []

    # فقط آخرین POST_LIMIT پست
    raw_posts = raw_posts[-POST_LIMIT:]

    parsed_posts = []

   for post in raw_posts:
    try:
        pid = post.get("data-post", "")
        if "/" in pid:
            pid = pid.split("/")[-1]
        pid = pid.strip()

        # متن پست
        text_el = post.select_one(".tgme_widget_message_text")
        text = text_el.get_text("\n").strip() if text_el else ""

        # تاریخ/زمان
        date_el = post.select_one("time")
        date = date_el.get("datetime", "") if date_el else ""

        # رسانه
        img_urls, vid_urls = extract_media_from_post(post)

        # نگاشت URLها به مسیرهای محلی
        local_images = []
        for idx, img_url in enumerate(img_urls):
            fname = local_media_name(channel, pid, idx, img_url, "img")
            local_images.append(str(MEDIA_DIR / fname))

        local_videos = []
        for idx, vid_url in enumerate(vid_urls):
            fname = local_media_name(channel, pid, idx, vid_url, "vid")
            local_videos.append(str(MEDIA_DIR / fname))

        parsed_posts.append({
            "id": pid,
            "text": text,
            "date": date,
            "images": local_images,
            "videos": local_videos,
            "remote_images": img_urls,
            "remote_videos": vid_urls,
        })

    except Exception as e:
        print(f"⚠ Error parsing a post in {channel}: {e}")
