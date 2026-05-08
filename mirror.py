#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Channel Mirror - Production Ready
-------------------------------------------
- پشتیبانی از چند کانال همزمان
- دانلود تصاویر و ویدیوها
- ذخیره ساختار استاندارد JSON
- جلوگیری از دانلود مجدد
- مدیریت خطا و retry
- ذخیره آخرین زمان بروزرسانی
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
MAX_POSTS_PER_CHANNEL = 50  # حداکثر پست نگهداری شده برای هر کانال
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ایجاد پوشه رسانه
MEDIA_DIR.mkdir(exist_ok=True)

# ============================================
# توابع کمکی
# ============================================

def load_posts_db() -> Dict:
    """
    بارگذاری دیتابیس پست‌ها از فایل JSON
    اگر فایل وجود نداشت یا خراب بود، دیتابیس جدید ایجاد می‌کند
    """
    if not POSTS_FILE.exists():
        print("📁 فایل posts.json وجود ندارد، ایجاد فایل جدید...")
        return {"channels": {}, "last_update": None}
    
    try:
        with open(POSTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # اطمینان از وجود ساختار صحیح
        if "channels" not in data:
            data["channels"] = {}
        if "last_update" not in data:
            data["last_update"] = None
            
        return data
        
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️ فایل posts.json خراب است ({e})، ایجاد فایل جدید...")
        return {"channels": {}, "last_update": None}


def save_posts_db(data: Dict):
    """ذخیره دیتابیس پست‌ها در فایل JSON"""
    try:
        with open(POSTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 دیتابیس ذخیره شد: {POSTS_FILE}")
    except Exception as e:
        print(f"❌ خطا در ذخیره دیتابیس: {e}")


def load_channels() -> List[str]:
    """خواندن لیست کانال‌ها از فایل list.txt"""
    list_file = Path("list.txt")
    
    if not list_file.exists():
        print("❌ فایل list.txt یافت نشد!")
        print("📝 لطفاً یک فایل list.txt با نام کانال‌ها ایجاد کنید (هر خط یک کانال)")
        return []
    
    try:
        with open(list_file, 'r', encoding='utf-8') as f:
            channels = [line.strip() for line in f if line.strip()]
        
        if not channels:
            print("⚠️ فایل list.txt خالی است!")
            return []
        
        # حذف @ از ابتدای نام کانال اگر وجود داشته باشد
        channels = [ch.replace('@', '') for ch in channels]
        
        print(f"📋 کانال‌های بارگذاری شده: {', '.join(channels)}")
        return channels
        
    except Exception as e:
        print(f"❌ خطا در خواندن list.txt: {e}")
        return []


def get_filename_from_url(url: str, channel: str, post_id: str, index: int, media_type: str) -> str:
    """
    تولید نام فایل یکتا برای رسانه
    با استفاده از هش URL برای جلوگیری از نام‌های تکراری
    """
    # گرفتن پسوند از URL یا تنظیم پیش‌فرض
    url_lower = url.lower()
    
    if '.jpg' in url_lower or '.jpeg' in url_lower:
        ext = '.jpg'
    elif '.png' in url_lower:
        ext = '.png'
    elif '.gif' in url_lower:
        ext = '.gif'
    elif '.mp4' in url_lower:
        ext = '.mp4'
    elif '.webm' in url_lower:
        ext = '.webm'
    elif '.mov' in url_lower:
        ext = '.mov'
    else:
        ext = '.jpg' if media_type == 'image' else '.mp4'
    
    # ایجاد هش برای اطمینان از یکتایی
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    
    return f"{channel}_{post_id}_{index}_{url_hash}{ext}"


def download_file(url: str, filepath: Path) -> bool:
    """
    دانلود فایل با پشتیبانی از:
    - بررسی وجود فایل (جلوگیری از دانلود مجدد)
    - retry در صورت خطا
    - streaming برای فایل‌های بزرگ
    """
    # اگر فایل از قبل وجود دارد، دانلود نکن
    if filepath.exists() and filepath.stat().st_size > 0:
        print(f"  ⏭️  موجود است: {filepath.name} ({filepath.stat().st_size / 1024:.1f} KB)")
        return True
    
    for attempt in range(MAX_RETRIES):
        try:
            headers = {'User-Agent': USER_AGENT}
            
            # دانلود با streaming برای فایل‌های بزرگ
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
            
            if response.status_code == 200:
                # بررسی type محتوا
                content_type = response.headers.get('content-type', '')
                if 'text/html' in content_type:
                    print(f"  ⚠️ URL به صفحه HTML اشاره دارد: {url[:80]}")
                    return False
                
                # دانلود و ذخیره
                with open(filepath, 'wb') as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                
                # بررسی اینکه فایل خالی نباشد
                if downloaded > 0:
                    size_kb = downloaded / 1024
                    print(f"  ✓ دانلود شد: {filepath.name} ({size_kb:.1f} KB)")
                    return True
                else:
                    print(f"  ✗ فایل خالی: {url[:80]}")
                    filepath.unlink(missing_ok=True)
                    return False
                    
            elif response.status_code == 404:
                print(f"  ✗ فایل یافت نشد (404): {url[:80]}")
                return False
            else:
                print(f"  ✗ خطا {response.status_code}: {url[:80]}")
                
        except requests.Timeout:
            print(f"  ✗ تلاش {attempt + 1} - Timeout: {url[:80]}")
        except requests.RequestException as e:
            print(f"  ✗ تلاش {attempt + 1} - {str(e)[:50]}: {url[:80]}")
        except Exception as e:
            print(f"  ✗ خطای غیرمنتظره: {e}")
        
        # منتظر بمان قبل از تلاش مجدد
        if attempt < MAX_RETRIES - 1:
            time.sleep(2)
    
    return False


def extract_media_from_post(post_element, channel: str, post_id: str) -> List[Dict]:
    """
    استخراج رسانه‌های یک پست از HTML
    پشتیبانی از: تصاویر، ویدیوها
    """
    media_list = []
    media_index = 0
    
    # ========== استخراج تصاویر ==========
    # روش 1: عکس‌های باکلاس tgme_widget_message_photo_wrap
    photo_wraps = post_element.select('a.tgme_widget_message_photo_wrap')
    for wrap in photo_wraps:
        style = wrap.get('style', '')
        if 'background-image:url(' in style:
            # استخراج URL از style
            url_start = style.find('url(') + 4
            url_end = style.find(')', url_start)
            url = style[url_start:url_end].strip('\'"')
            
            if url and not url.startswith('data:') and url.startswith('http'):
                filename = get_filename_from_url(url, channel, post_id, media_index, 'image')
                filepath = MEDIA_DIR / filename
                
                if download_file(url, filepath):
                    media_list.append({
                        "type": "image",
                        "file": filename
                    })
                    media_index += 1
    
    # روش 2: تگ‌های img با کلاس tgme_widget_message_photo
    images = post_element.select('img.tgme_widget_message_photo')
    for img in images:
        # تلاش برای گرفتن src یا data-src
        url = img.get('src') or img.get('data-src')
        if url and url.startswith('http'):
            filename = get_filename_from_url(url, channel, post_id, media_index, 'image')
            filepath = MEDIA_DIR / filename
            
            if download_file(url, filepath):
                media_list.append({
                    "type": "image",
                    "file": filename
                })
                media_index += 1
    
    # ========== استخراج ویدیوها ==========
    # تگ‌های video
    videos = post_element.select('video')
    for video in videos:
        url = video.get('src')
        if url and url.startswith('http'):
            filename = get_filename_from_url(url, channel, post_id, media_index, 'video')
            filepath = MEDIA_DIR / filename
            
            if download_file(url, filepath):
                media_list.append({
                    "type": "video",
                    "file": filename
                })
                media_index += 1
    
    # ویدیوهای با data-video
    video_divs = post_element.select('div.tgme_widget_message_video')
    for div in video_divs:
        url = div.get('data-video')
        if url and url.startswith('http'):
            filename = get_filename_from_url(url, channel, post_id, media_index, 'video')
            filepath = MEDIA_DIR / filename
            
            if download_file(url, filepath):
                media_list.append({
                    "type": "video",
                    "file": filename
                })
                media_index += 1
    
    return media_list


def fetch_channel_posts(channel: str) -> List[Dict]:
    """
    دریافت پست‌های یک کانال از تلگرام
    بازگشت: لیستی از دیکشنری‌های حاوی اطلاعات پست‌ها
    """
    url = f"https://t.me/s/{channel}"
    print(f"\n📡 در حال دریافت: @{channel}")
    print(f"🔗 URL: {url}")
    
    try:
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            print(f"  ❌ خطا: HTTP {response.status_code}")
            return []
        
        # پارس HTML
        soup = BeautifulSoup(response.text, 'lxml')
        post_elements = soup.select('.tgme_widget_message')
        
        if not post_elements:
            print(f"  ⚠️  پستی یافت نشد (ممکن است کانال خصوصی یا نامعتبر باشد)")
            return []
        
        print(f"  📝 {len(post_elements)} پست در صفحه یافت شد")
        
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
                if time_elem and time_elem.get('datetime'):
                    date = time_elem.get('datetime')
                else:
                    date = datetime.now().isoformat()
                
                # استخراج رسانه‌ها
                media = extract_media_from_post(element, channel, post_id)
                
                # ساخت پست
                post = {
                    "id": int(post_id),
                    "text": text,
                    "date": date,
                    "media": media
                }
                
                posts.append(post)
                
                # نمایش پیشرفت
                media_count = len(media)
                if media_count > 0:
                    print(f"  📎 پست {post_id}: {media_count} رسانه")
                
            except Exception as e:
                print(f"  ⚠️  خطا در پردازش پست: {e}")
                continue
        
        print(f"  ✅ {len(posts)} پست معتبر دریافت شد")
        return posts
        
    except requests.Timeout:
        print(f"  ❌ Timeout: اتصال به {url} بیش از حد طول کشید")
        return []
    except requests.ConnectionError:
        print(f"  ❌ خطا در اتصال: نمی‌توان به {url} متصل شد")
        return []
    except Exception as e:
        print(f"  ❌ خطای غیرمنتظره: {e}")
        return []


def update_channel(channel: str, db: Dict) -> Dict:
    """
    بروزرسانی پست‌های یک کانال
    اضافه کردن پست‌های جدید و حذف پست‌های تکراری
    """
    print(f"\n{'='*50}")
    print(f"🔄 بروزرسانی کانال: @{channel}")
    print(f"{'='*50}")
    
    # دریافت پست‌های جدید
    new_posts = fetch_channel_posts(channel)
    
    if not new_posts:
        print(f"  ⚠️  پستی دریافت نشد برای @{channel}")
        return db
    
    # ایجاد یا دریافت کانال در دیتابیس
    if channel not in db["channels"]:
        db["channels"][channel] = []
        print(f"  📁 کانال جدید اضافه شد: @{channel}")
    
    # شناسه‌های موجود
    existing_ids = {post["id"] for post in db["channels"][channel]}
    
    # اضافه کردن پست‌های جدید (قدیمی‌ترین‌ها اول)
    added_count = 0
    skipped_count = 0
    
    for post in reversed(new_posts):  # معکوس برای اضافه کردن از قدیم به جدید
        if post["id"] not in existing_ids:
            db["channels"][channel].append(post)
            added_count += 1
            existing_ids.add(post["id"])
        else:
            skipped_count += 1
    
    # مرتب‌سازی بر اساس ID (نزولی - جدیدترین اول)
    db["channels"][channel].sort(key=lambda x: x["id"], reverse=True)
    
    # محدودیت تعداد پست‌ها
    if len(db["channels"][channel]) > MAX_POSTS_PER_CHANNEL:
        removed = len(db["channels"][channel]) - MAX_POSTS_PER_CHANNEL
        db["channels"][channel] = db["channels"][channel][:MAX_POSTS_PER_CHANNEL]
        print(f"  🗑️  {removed} پست قدیمی حذف شد")
    
    # آمار نهایی
    total_media = sum(len(post.get("media", [])) for post in db["channels"][channel])
    
    print(f"\n  📊 آمار @{channel}:")
    print(f"     • پست‌های جدید: {added_count}")
    print(f"     • پست‌های تکراری: {skipped_count}")
    print(f"     • مجموع پست‌ها: {len(db['channels'][channel])}")
    print(f"     • مجموع رسانه‌ها: {total_media}")
    
    return db


def clean_orphaned_media(db: Dict):
    """
    پاکسازی فایل‌های رسانه‌ای که در دیتابیس نیستند
    (اختیاری - برای کاهش حجم مخزن)
    """
    print("\n🧹 پاکسازی فایل‌های اضافی...")
    
    # جمع‌آوری تمام فایل‌های موجود در دیتابیس
    used_files = set()
    for channel, posts in db["channels"].items():
        for post in posts:
            for media in post.get("media", []):
                used_files.add(media["file"])
    
    # بررسی فایل‌های موجود در پوشه media
    orphaned = []
    for file in MEDIA_DIR.glob("*"):
        if file.is_file() and file.name not in used_files:
            orphaned.append(file)
    
    # حذف فایل‌های یتیم
    if orphaned:
        print(f"  🗑️  {len(orphaned)} فایل یتیم یافت شد")
        for file in orphaned:
            try:
                file.unlink()
                print(f"     • حذف: {file.name}")
            except Exception as e:
                print(f"     • خطا در حذف {file.name}: {e}")
    else:
        print("  ✅ هیچ فایل یتیمی یافت نشد")


def print_summary(db: Dict, start_time: float):
    """
    چاپ خلاصه نهایی از عملیات
    """
    elapsed_time = time.time() - start_time
    
    total_posts = sum(len(posts) for posts in db["channels"].values())
    total_media = sum(
        sum(len(post.get("media", [])) for post in posts)
        for posts in db["channels"].values()
    )
    
    print("\n" + "="*50)
    print("🎉 عملیات با موفقیت کامل شد!")
    print("="*50)
    print(f"⏱️  زمان اجرا: {elapsed_time:.2f} ثانیه")
    print(f"📊 آمار نهایی:")
    print(f"   • کانال‌ها: {len(db['channels'])}")
    print(f"   • پست‌ها: {total_posts}")
    print(f"   • رسانه‌ها: {total_media}")
    print(f"   • فایل‌های رسانه: {len(list(MEDIA_DIR.glob('*')))} فایل")
    print(f"   • آخرین بروزرسانی: {db.get('last_update', 'ندارد')}")
    print("="*50)


def main():
    """تابع اصلی برنامه"""
    start_time = time.time()
    
    print("="*50)
    print("🪞 Telegram Channel Mirror - Version 2.0")
    print("="*50)
    print(f"⏰ زمان شروع: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 پوشه رسانه: {MEDIA_DIR.absolute()}")
    print(f"📄 فایل دیتابیس: {POSTS_FILE.absolute()}")
    print("="*50)
    
    # بارگذاری کانال‌ها
    channels = load_channels()
    if not channels:
        print("\n❌ برنامه متوقف شد. هیچ کانالی برای پردازش وجود ندارد.")
        return
    
    # بارگذاری دیتابیس
    db = load_posts_db()
    
    # بروزرسانی هر کانال
    for channel in channels:
        db = update_channel(channel, db)
    
    # پاکسازی فایل‌های اضافی (اختیاری)
    # clean_orphaned_media(db)
    
    # بروزرسانی زمان آخرین اجرا
    db["last_update"] = datetime.now().isoformat()
    
    # ذخیره دیتابیس
    save_posts_db(db)
    
    # نمایش خلاصه
    print_summary(db, start_time)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ برنامه توسط کاربر متوقف شد.")
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
