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

    return parsed_posts


# -----------------------------
# دانلود تمام رسانه‌های یک کانال
# -----------------------------
async def download_media_for_channel(channel: str, posts):
    """
    برای لیست پست‌های یک کانال، تمام رسانه‌ها را دانلود می‌کند.
    """
    if not posts:
        return

    tasks = []

    for post in posts:
        # تصاویر
        for idx, (remote, local) in enumerate(zip(post.get("remote_images", []), post.get("images", []))):
            local_path = Path(local)
            if not local_path.exists():
                tasks.append(download_file(remote, local_path))

        # ویدیوها
        for idx, (remote, local) in enumerate(zip(post.get("remote_videos", []), post.get("videos", []))):
            local_path = Path(local)
            if not local_path.exists():
                tasks.append(download_file(remote, local_path))

    if tasks:
        print(f"📥 Downloading {len(tasks)} media files for @{channel} ...")
        await asyncio.gather(*tasks)


# -----------------------------
# ادغام پست‌های جدید با JSON موجود
# -----------------------------
def merge_posts(existing_posts, new_posts, channel: str):
    """
    ادغام پست‌های جدید با پست‌های موجود
    - حذف تکراری‌ها بر اساس id
    - نگهداری آخرین POST_LIMIT پست
    """
    # تبدیل به دیکشنری برای حذف تکراری‌ها
    posts_dict = {}
    for post in existing_posts:
        posts_dict[post["id"]] = post

    for post in new_posts:
        posts_dict[post["id"]] = post

    # تبدیل به لیست و مرتب‌سازی بر اساس id (عدد)
    posts_list = list(posts_dict.values())
    try:
        posts_list.sort(key=lambda x: int(x["id"]), reverse=True)
    except ValueError:
        # اگر id عدد نبود، بر اساس string مرتب کن
        posts_list.sort(key=lambda x: x["id"], reverse=True)

    # فقط آخرین POST_LIMIT پست را نگه دار
    return posts_list[:POST_LIMIT]


# -----------------------------
# تابع اصلی (اجرای کل فرآیند)
# -----------------------------
async def main():
    """
    1. خواندن list.txt
    2. دریافت پست‌های کانال‌ها
    3. دانلود رسانه‌ها
    4. ادغام با posts.json
    """
    # خواندن لیست کانال‌ها
    try:
        with open("list.txt", "r", encoding="utf-8") as f:
            channels = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("❌ list.txt not found!")
        return

    if not channels:
        print("❌ No channels in list.txt")
        return

    print(f"📡 Processing {len(channels)} channels: {channels}")

    # بارگذاری JSON موجود
    data = load_json_safe()
    all_posts = data.get("channels", {})

    # دریافت پست‌های جدید از همه کانال‌ها
    async with aiohttp.ClientSession() as session:
        fetch_tasks = [fetch_channel_posts(session, ch) for ch in channels]
        results = await asyncio.gather(*fetch_tasks)

    # پردازش هر کانال
    for channel, new_posts in zip(channels, results):
        if not new_posts:
            print(f"⚠ No new posts for @{channel}")
            continue

        print(f"📝 Found {len(new_posts)} posts for @{channel}")

        # دانلود رسانه‌ها
        await download_media_for_channel(channel, new_posts)

        # ادغام با پست‌های موجود
        existing = all_posts.get(channel, [])
        merged = merge_posts(existing, new_posts, channel)

        # به‌روزرسانی مسیرهای محلی در merged posts
        # (حذف remote_*ها برای ذخیره‌سازی نهایی)
        for post in merged:
            post.pop("remote_images", None)
            post.pop("remote_videos", None)

        all_posts[channel] = merged
        print(f"✅ Updated @{channel}: {len(merged)} posts stored")

    # ذخیره نهایی
    save_json_safe({"channels": all_posts})
    print("🎉 All done! posts.json saved.")


if __name__ == "__main__":
    asyncio.run(main())
