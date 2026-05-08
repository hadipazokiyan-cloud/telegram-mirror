#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Channel Mirror - Production Ready
-------------------------------------------
- پشتیبانی از چند کانال همزمان
- دانلود تصاویر و ویدیوها
- ذخیره ساختار استاندارد JSON
- جلوگیری از دانلود مجدد
- مدیریت خطا
"""

import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

# ============================================
# تنظیمات
# ============================================
MEDIA_DIR = Path("media")
POSTS_FILE = Path("posts.json")
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ایجاد پوشه رسانه
MEDIA_DIR.mkdir(exist_ok=True)

# ============================================
# توابع کمکی
# ============================================

def load_posts_db() -> Dict:
    """بارگذاری دیتابیس پست‌ها"""
    if POSTS_FILE.exists():
        try:
            with open(POSTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print("⚠️ فایل posts.json خراب است، ایجاد فایل جدید...")
    return {"channels": {}}


def save_posts_db(data: Dict):
    """ذخیره دیتابیس پست‌ها"""
    with open(POSTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_channels() -> List[str]:
    """خواندن لیست کانال‌ها از فایل"""
    if not Path("list.txt").exists():
        print("❌ فایل list.txt یافت نشد!")
        return []
    
    with open("list.txt", 'r', encoding='utf-8') as f:
        channels = [line.strip() for line in f if line.strip()]
    
    return channels


def get_filename_from_url(url: str, channel: str, post_id: str, index: int, media_type: str) -> str:
    """تولید نام فایل یکتا برای رسانه"""
    # گرفتن پسوند از URL
    url_lower = url.lower()
    if '.jpg' in url_lower or '.jpeg' in url_lower:
        ext = '.jpg'
    elif '.png' in url_lower:
        ext = '.png'
    elif '.mp4' in url_lower:
        ext = '.mp4'
    elif '.webm' in url_lower:
        ext = '.webm'
    else:
        ext = '.jpg' if media_type == 'image' else '.mp4'
    
    # ایجاد هش برای اطمینان از یکتایی
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    
    return f"{channel}_{post_id}_{index}_{url_hash}{ext}"


def download_file(url: str, filepath: Path) -> bool:
    """دانلود فایل با پشتیبانی از retry"""
    if filepath.exists():
        print(f"  ⏭️  موجود است: {filepath.name}")
        return True
    
    for attempt in range(MAX_RETRIES):
        try:
            headers = {'User-Agent': USER_AGENT}
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
            
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"  ✓ دانلود شد: {filepath.name}")
                return True
            else:
                print(f"  ✗ خطا {response.status_code}: {url[:80]}")
                
        except requests.RequestException as e:
            print(f"  ✗ تلاش {attempt + 1} ناموفق: {str(e)[:50]}")
            
        if attempt < MAX_RETRIES - 1:
            time.sleep(2)
    
    return False


def extract_media_from_post(post_element, channel: str, post_id: str) -> List[Dict]:
    """استخراج رسانه‌های یک پست"""
    media_list = []
    media_index = 0
    
    # استخراج تصاویر
    photo_wraps = post_element.select('a.tgme_widget_message_photo_wrap')
    for wrap in photo_wraps:
        style = wrap.get('style', '')
        if 'background-image:url(' in style:
            # استخراج URL از style
            url_start = style.find('url(') + 4
            url_end = style.find(')', url_start)
            url = style[url_start:url_end].strip('\'"')
            
            if url and not url.startswith('data:'):
                filename = get_filename_from_url(url, channel, post_id, media_index, 'image')
                filepath = MEDIA_DIR / filename
                
                if download_file(url, filepath):
                    media_list.append({
                        "type": "image",
                        "file": filename,
                        "url": url
                    })
                    media_index += 1
    
    # استخراج ویدیوها
    videos = post_element.select('video')
    for video in videos:
        url = video.get('src')
        if url:
            filename = get_filename_from_url(url, channel, post_id, media_index, 'video')
            filepath = MEDIA_DIR / filename
            
            if download_file(url, filepath):
                media_list.append({
                    "type": "video",
                    "file": filename,
                    "url": url
                })
                media_index += 1
    
    return media_list


def fetch_channel_posts(channel: str) -> List[Dict]:
    """دریافت پست‌های یک کانال از تلگرام"""
    url = f"https://t.me/s/{channel}"
    print(f"\n📡 در حال دریافت: @{channel}")
    
    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            print(f"  ❌ خطا: HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'lxml')
        post_elements = soup.select('.tgme_widget_message')
        
        if not post_elements:
            print(f"  ⚠️  پستی یافت نشد")
            return []
        
        posts = []
        
        for element in post_elements:
            try:
                # استخراج ID پست
                data_post = element.get('data-post', '')
                if '/' in data_post:
                    post_id = data_post.split('/')[-1]
                else:
                    continue
                
                # استخراج متن
                text_elem = element.select_one('.tgme_widget_message_text')
                text = text_elem.get_text(strip=True) if text_elem else ""
                
                # استخراج تاریخ
                time_elem = element.select_one('time')
                date = time_elem.get('datetime', '') if time_elem else ""
                
                # استخراج رسانه‌ها
                media = extract_media_from_post(element, channel, post_id)
                
                # ساخت پست
                post = {
                    "id": int(post_id),
                    "text": text,
                    "date": date if date else datetime.now().isoformat(),
                    "media": media
                }
                
                posts.append(post)
                
            except Exception as e:
                print(f"  ⚠️  خطا در پردازش پست: {e}")
                continue
        
        print(f"  ✓ {len(posts)} پست دریافت شد")
        return posts
        
    except requests.RequestException as e:
        print(f"  ❌ خطا در اتصال: {e}")
        return []


def update_channel(channel: str, db: Dict) -> Dict:
    """بروزرسانی پست‌های یک کانال"""
    
    # دریافت پست‌های جدید
    new_posts = fetch_channel_posts(channel)
    
    if not new_posts:
        return db
    
    # ایجاد یا دریافت کانال در دیتابیس
    if channel not in db["channels"]:
        db["channels"][channel] = []
    
    # شناسه‌های موجود
    existing_ids = {post["id"] for post in db["channels"][channel]}
    
    # اضافه کردن پست‌های جدید
    added_count = 0
    for post in new_posts:
        if post["id"] not in existing_ids:
            # حذف فیلد url از media برای ذخیره نهایی
            for media in post["media"]:
                media.pop("url", None)
            
            db["channels"][channel].append(post)
            added_count += 1
    
    # مرتب‌سازی بر اساس ID (نزولی)
    db["channels"][channel].sort(key=lambda x: x["id"], reverse=True)
    
    # نگهداری فقط 50 پست آخر هر کانال
    if len(db["channels"][channel]) > 50:
        db["channels"][channel] = db["channels"][channel][:50]
    
    print(f"  ✨ {added_count} پست جدید اضافه شد")
    
    return db


def main():
    """تابع اصلی"""
    print("=" * 50)
    print("🪞 Telegram Channel Mirror - Version 2.0")
    print("=" * 50)
    
    # بارگذاری کانال‌ها
    channels = load_channels()
    if not channels:
        print("❌ هیچ کانالی در list.txt وجود ندارد")
        return
    
    print(f"\n📋 کانال‌ها: {', '.join(channels)}")
    
    # بارگذاری دیتابیس
    db = load_posts_db()
    
    # بروزرسانی هر کانال
    for channel in channels:
        db = update_channel(channel, db)
    
    # ذخیره دیتابیس
    save_posts_db(db)
    
    # آمار نهایی
    total_posts = sum(len(posts) for posts in db["channels"].values())
    total_media = sum(
        sum(len(post.get("media", [])) for post in posts)
        for posts in db["channels"].values()
    )
    
    print("\n" + "=" * 50)
    print(f"✅ عملیات کامل شد!")
    print(f"📊 آمار نهایی:")
    print(f"   • کانال‌ها: {len(db['channels'])}")
    print(f"   • پست‌ها: {total_posts}")
    print(f"   • رسانه‌ها: {total_media}")
    print(f"   • پوشه media: {len(list(MEDIA_DIR.glob('*')))} فایل")
    print("=" * 50)


if __name__ == "__main__":
    main()
