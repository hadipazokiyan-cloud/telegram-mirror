#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Channel Mirror - Complete Media Support
------------------------------------------------
- پشتیبانی از تمام انواع فایل: تصاویر، ویدیوها، صوتی، اسناد، APK، ZIP و ...
- تشخیص خودکار نوع فایل
- دانلود همزمان با مدیریت صف
- ذخیره در پوشه‌های دسته‌بندی شده
- جلوگیری از دانلود مجدد
- مدیریت خطا و retry
"""

import os
import json
import time
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote
import re

# ============================================
# تنظیمات
# ============================================
MEDIA_DIR = Path("media")
POSTS_FILE = Path("posts.json")
REQUEST_TIMEOUT = 60  # افزایش timeout برای فایل‌های بزرگ
MAX_RETRIES = 3
MAX_POSTS_PER_CHANNEL = 100
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ============================================
# پیکربندی انواع فایل‌ها
# ============================================

FILE_CATEGORIES = {
    'images': {
        'extensions': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico', '.tiff', '.heic'],
        'icon': '🖼️',
        'folder': 'images'
    },
    'videos': {
        'extensions': ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.m4v', '.3gp', '.mpeg', '.mpg', '.wmv'],
        'icon': '🎬',
        'folder': 'videos'
    },
    'audios': {
        'extensions': ['.mp3', '.ogg', '.wav', '.m4a', '.flac', '.aac', '.opus', '.wma', '.aiff'],
        'icon': '🎵',
        'folder': 'audios'
    },
    'documents': {
        'extensions': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md', '.rtf', '.odt', '.ods', '.odp'],
        'icon': '📄',
        'folder': 'documents'
    },
    'archives': {
        'extensions': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2'],
        'icon': '📦',
        'folder': 'archives'
    },
    'applications': {
        'extensions': ['.apk', '.exe', '.msi', '.deb', '.rpm', '.appimage', '.dmg', '.bin', '.sh', '.bat'],
        'icon': '📱',
        'folder': 'applications'
    },
    'code': {
        'extensions': ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.php', '.rb', '.go', '.rs', '.json', '.xml', '.yaml', '.yml'],
        'icon': '💻',
        'folder': 'code'
    },
    'other': {
        'extensions': [],
        'icon': '📎',
        'folder': 'other'
    }
}

# ایجاد پوشه‌ها
MEDIA_DIR.mkdir(exist_ok=True)
for category in FILE_CATEGORIES.values():
    (MEDIA_DIR / category['folder']).mkdir(exist_ok=True)


def get_file_category(filename: str) -> Tuple[str, str]:
    """
    تشخیص دسته‌بندی فایل بر اساس پسوند
    بازگشت: (نام دسته, مسیر پوشه)
    """
    ext = Path(filename).suffix.lower()
    
    for category_name, category_info in FILE_CATEGORIES.items():
        if ext in category_info['extensions']:
            return category_name, category_info['folder']
    
    # اگر پسوند ناشناخته بود، براساس mime type تلاش کن
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        if mime_type.startswith('image/'):
            return 'images', 'images'
        elif mime_type.startswith('video/'):
            return 'videos', 'videos'
        elif mime_type.startswith('audio/'):
            return 'audios', 'audios'
        elif mime_type.startswith('application/zip') or 'compressed' in mime_type:
            return 'archives', 'archives'
        elif 'pdf' in mime_type:
            return 'documents', 'documents'
        elif 'vnd.android.package-archive' in mime_type:
            return 'applications', 'applications'
    
    return 'other', 'other'


def get_file_icon(filename: str) -> str:
    """دریافت آیکون مناسب برای فایل"""
    category, _ = get_file_category(filename)
    return FILE_CATEGORIES.get(category, FILE_CATEGORIES['other'])['icon']


# ============================================
# توابع کمکی
# ============================================

def load_posts_db() -> Dict:
    """بارگذاری دیتابیس پست‌ها"""
    if not POSTS_FILE.exists():
        print("📁 ایجاد فایل جدید posts.json...")
        return {"channels": {}, "last_update": None, "statistics": {"total_posts": 0, "total_files": 0, "files_by_type": {}}}
    
    try:
        with open(POSTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # اطمینان از وجود ساختار صحیح
        data.setdefault("channels", {})
        data.setdefault("last_update", None)
        data.setdefault("statistics", {"total_posts": 0, "total_files": 0, "files_by_type": {}})
        
        return data
        
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️ خطا در خواندن posts.json: {e}")
        return {"channels": {}, "last_update": None, "statistics": {"total_posts": 0, "total_files": 0, "files_by_type": {}}}


def save_posts_db(data: Dict):
    """ذخیره دیتابیس"""
    # به‌روزرسانی آمار
    total_posts = 0
    total_files = 0
    files_by_type = {cat: 0 for cat in FILE_CATEGORIES.keys()}
    
    for channel, posts in data.get("channels", {}).items():
        total_posts += len(posts)
        for post in posts:
            for media in post.get("media", []):
                total_files += 1
                file_type = media.get("type", "other")
                if file_type in files_by_type:
                    files_by_type[file_type] += 1
    
    data["statistics"] = {
        "total_posts": total_posts,
        "total_files": total_files,
        "files_by_type": files_by_type,
        "last_calculation": datetime.now().isoformat()
    }
    
    try:
        with open(POSTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 دیتابیس ذخیره شد: {total_posts} پست، {total_files} فایل")
    except Exception as e:
        print(f"❌ خطا در ذخیره: {e}")


def load_channels() -> List[str]:
    """خواندن لیست کانال‌ها"""
    list_file = Path("list.txt")
    
    if not list_file.exists():
        print("❌ فایل list.txt یافت نشد!")
        print("📝 لطفاً فایل list.txt را با نام کانال‌ها ایجاد کنید")
        return []
    
    try:
        with open(list_file, 'r', encoding='utf-8') as f:
            channels = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        # حذف @ از ابتدا
        channels = [ch.replace('@', '') for ch in channels]
        
        if channels:
            print(f"📋 کانال‌ها: {', '.join(channels)}")
        return channels
        
    except Exception as e:
        print(f"❌ خطا: {e}")
        return []


def get_filename_from_url(url: str, channel: str, post_id: str, index: int) -> str:
    """
    تولید نام فایل یکتا از URL
    """
    # تلاش برای استخراج نام اصلی فایل از URL
    parsed_url = urlparse(url)
    original_name = Path(unquote(parsed_url.path)).name
    
    # حذف پارامترهای اضافی
    if '?' in original_name:
        original_name = original_name.split('?')[0]
    
    # اگر نام فایل معتبر است و پسوند دارد، از آن استفاده کن
    if original_name and '.' in original_name:
        # پاکسازی نام فایل
        safe_name = re.sub(r'[^\w\-_.]', '_', original_name)
        # محدودیت طول
        if len(safe_name) > 100:
            name_part = safe_name[:80]
            ext_part = safe_name.split('.')[-1]
            safe_name = f"{name_part}.{ext_part}"
        return f"{channel}_{post_id}_{index}_{safe_name}"
    
    # در غیر این صورت، از هش URL استفاده کن
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    
    # تشخیص پسوند از Content-Type یا URL
    ext = '.file'
    for category in FILE_CATEGORIES.values():
        for category_ext in category['extensions']:
            if category_ext in url.lower():
                ext = category_ext
                break
    
    return f"{channel}_{post_id}_{index}_{url_hash}{ext}"


def download_file(url: str, filepath: Path, retry_count: int = 0) -> bool:
    """
    دانلود فایل با پشتیبانی از resume و retry
    """
    if filepath.exists() and filepath.stat().st_size > 0:
        size_kb = filepath.stat().st_size / 1024
        print(f"  ⏭️  موجود: {filepath.name} ({size_kb:.1f} KB)")
        return True
    
    temp_path = filepath.with_suffix(filepath.suffix + '.part')
    
    for attempt in range(MAX_RETRIES):
        try:
            headers = {'User-Agent': USER_AGENT}
            
            # پشتیبانی از resume برای دانلودهای ناقص
            if temp_path.exists():
                existing_size = temp_path.stat().st_size
                headers['Range'] = f'bytes={existing_size}-'
            else:
                existing_size = 0
            
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
            
            if response.status_code in [200, 206]:
                mode = 'ab' if existing_size > 0 else 'wb'
                with open(temp_path, mode) as f:
                    downloaded = existing_size
                    for chunk in response.iter_content(chunk_size=32768):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                
                if downloaded > 0:
                    # حرکت فایل از موقت به نهایی
                    temp_path.rename(filepath)
                    size_mb = downloaded / (1024 * 1024)
                    icon = get_file_icon(filepath.name)
                    print(f"  {icon} دانلود: {filepath.name} ({size_mb:.2f} MB)")
                    return True
                    
            elif response.status_code == 404:
                print(f"  ✗ فایل یافت نشد: {url[:80]}")
                return False
                
        except requests.Timeout:
            print(f"  ⚠️ تلاش {attempt + 1} - Timeout")
        except Exception as e:
            print(f"  ⚠️ تلاش {attempt + 1} - {str(e)[:50]}")
        
        if attempt < MAX_RETRIES - 1:
            time.sleep(3)
    
    # پاکسازی فایل موقت در صورت خطا
    temp_path.unlink(missing_ok=True)
    return False


def extract_all_links_from_post(post_element) -> List[Dict]:
    """
    استخراج تمام لینک‌های فایل از یک پست
    """
    links = []
    seen_urls = set()
    
    # 1. عکس‌ها (با استایل background-image)
    for elem in post_element.select('[style*="background-image"]'):
        style = elem.get('style', '')
        url_match = re.search(r'url\(["\']?([^"\'()]+)["\']?\)', style)
        if url_match:
            url = url_match.group(1)
            if url.startswith('http') and url not in seen_urls:
                seen_urls.add(url)
                links.append({'url': url, 'type': 'image'})
    
    # 2. تگ‌های img
    for img in post_element.select('img'):
        for attr in ['src', 'data-src']:
            url = img.get(attr)
            if url and url.startswith('http') and url not in seen_urls:
                seen_urls.add(url)
                links.append({'url': url, 'type': 'image'})
    
    # 3. تگ‌های video
    for video in post_element.select('video'):
        url = video.get('src')
        if url and url.startswith('http') and url not in seen_urls:
            seen_urls.add(url)
            links.append({'url': url, 'type': 'video'})
    
    # 4. تگ‌های audio
    for audio in post_element.select('audio'):
        url = audio.get('src')
        if url and url.startswith('http') and url not in seen_urls:
            seen_urls.add(url)
            links.append({'url': url, 'type': 'audio'})
    
    # 5. لینک‌های دانلود مستقیم
    for a in post_element.select('a[href*="/file/"], a[href*="download"], a[href*="telegram.org/file"]'):
        url = a.get('href')
        if url and url.startswith('http') and url not in seen_urls:
            # بررسی پسوند فایل
            path = urlparse(url).path.lower()
            if any(ext in path for cat in FILE_CATEGORIES.values() for ext in cat['extensions']):
                seen_urls.add(url)
                links.append({'url': url, 'type': 'document'})
    
    # 6. المان‌های با data-url یا data-file
    for elem in post_element.select('[data-url], [data-file], [data-document]'):
        for attr in ['data-url', 'data-file', 'data-document']:
            url = elem.get(attr)
            if url and url.startswith('http') and url not in seen_urls:
                seen_urls.add(url)
                links.append({'url': url, 'type': 'document'})
    
    # 7. لینک‌های معمولی که به فایل اشاره دارند
    for a in post_element.select('a'):
        url = a.get('href')
        if url and url.startswith('http'):
            path = urlparse(url).path.lower()
            # چک کردن پسوند فایل
            for category in FILE_CATEGORIES.values():
                for ext in category['extensions']:
                    if path.endswith(ext):
                        if url not in seen_urls:
                            seen_urls.add(url)
                            links.append({'url': url, 'type': category['folder']})
                        break
    
    return links


def fetch_channel_posts(channel: str) -> List[Dict]:
    """
    دریافت پست‌های یک کانال
    """
    url = f"https://t.me/s/{channel}"
    print(f"\n📡 دریافت: @{channel}")
    
    try:
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            print(f"  ❌ خطا: HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'lxml')
        post_elements = soup.select('.tgme_widget_message')
        
        if not post_elements:
            print(f"  ⚠️ پستی یافت نشد")
            return []
        
        print(f"  📝 {len(post_elements)} پست یافت شد")
        
        posts = []
        
        for element in post_elements:
            try:
                # استخراج ID
                data_post = element.get('data-post', '')
                if '/' in data_post:
                    post_id = data_post.split('/')[-1]
                else:
                    continue
                
                # متن پست
                text_elem = element.select_one('.tgme_widget_message_text')
                text = text_elem.get_text(strip=True) if text_elem else ""
                
                # تاریخ
                time_elem = element.select_one('time')
                date = time_elem.get('datetime', datetime.now().isoformat()) if time_elem else datetime.now().isoformat()
                
                # استخراج تمام لینک‌های فایل
                all_links = extract_all_links_from_post(element)
                
                # دانلود فایل‌ها و ساخت لیست رسانه
                media_list = []
                for idx, link_info in enumerate(all_links):
                    filename = get_filename_from_url(link_info['url'], channel, post_id, idx)
                    file_type, subfolder = get_file_category(filename)
                    filepath = MEDIA_DIR / subfolder / filename
                    
                    if download_file(link_info['url'], filepath):
                        relative_path = f"{subfolder}/{filename}"
                        media_list.append({
                            "type": file_type,
                            "subfolder": subfolder,
                            "file": filename,
                            "path": relative_path,
                            "icon": get_file_icon(filename),
                            "size": filepath.stat().st_size if filepath.exists() else 0,
                            "name": filename
                        })
                
                # فقط پست‌هایی که فایل یا متن دارند ذخیره کن
                if media_list or text:
                    posts.append({
                        "id": int(post_id),
                        "text": text,
                        "date": date,
                        "media": media_list,
                        "has_media": len(media_list) > 0
                    })
                    
                    if media_list:
                        print(f"  📎 پست {post_id}: {len(media_list)} فایل")
                
            except Exception as e:
                print(f"  ⚠️ خطا در پردازش پست: {e}")
                continue
        
        print(f"  ✅ {len(posts)} پست معتبر دریافت شد")
        return posts
        
    except Exception as e:
        print(f"  ❌ خطا: {e}")
        return []


def update_channel(channel: str, db: Dict) -> Dict:
    """
    بروزرسانی پست‌های یک کانال
    """
    print(f"\n{'='*60}")
    print(f"🔄 بروزرسانی: @{channel}")
    print(f"{'='*60}")
    
    new_posts = fetch_channel_posts(channel)
    
    if not new_posts:
        return db
    
    if channel not in db["channels"]:
        db["channels"][channel] = []
        print(f"  📁 کانال جدید اضافه شد")
    
    existing_ids = {post["id"] for post in db["channels"][channel]}
    
    added_count = 0
    for post in new_posts:
        if post["id"] not in existing_ids:
            db["channels"][channel].append(post)
            added_count += 1
            existing_ids.add(post["id"])
    
    # مرتب‌سازی نزولی بر اساس ID
    db["channels"][channel].sort(key=lambda x: x["id"], reverse=True)
    
    # محدودیت تعداد پست‌ها
    if len(db["channels"][channel]) > MAX_POSTS_PER_CHANNEL:
        removed = len(db["channels"][channel]) - MAX_POSTS_PER_CHANNEL
        db["channels"][channel] = db["channels"][channel][:MAX_POSTS_PER_CHANNEL]
        print(f"  🗑️ {removed} پست قدیمی حذف شد")
    
    # آمار فایل‌ها
    total_files = sum(len(post.get("media", [])) for post in db["channels"][channel])
    
    print(f"\n  📊 @{channel}:")
    print(f"     • پست‌های جدید: {added_count}")
    print(f"     • کل پست‌ها: {len(db['channels'][channel])}")
    print(f"     • کل فایل‌ها: {total_files}")
    
    return db


def print_statistics(db: Dict):
    """نمایش آمار کامل"""
    stats = db.get("statistics", {})
    
    print("\n" + "="*60)
    print("📊 آمار نهایی")
    print("="*60)
    print(f"📺 کانال‌ها: {len(db.get('channels', {}))}")
    print(f"📝 کل پست‌ها: {stats.get('total_posts', 0)}")
    print(f"📎 کل فایل‌ها: {stats.get('total_files', 0)}")
    print("\n📂 تفکیک بر اساس نوع فایل:")
    
    files_by_type = stats.get('files_by_type', {})
    for file_type, count in sorted(files_by_type.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            icon = FILE_CATEGORIES.get(file_type, FILE_CATEGORIES['other'])['icon']
            print(f"   {icon} {file_type}: {count} فایل")
    
    # محاسبه حجم کل فایل‌ها
    total_size = 0
    for category in FILE_CATEGORIES.values():
        folder = MEDIA_DIR / category['folder']
        if folder.exists():
            for file in folder.rglob('*'):
                if file.is_file():
                    total_size += file.stat().st_size
    
    if total_size > 0:
        size_gb = total_size / (1024**3)
        size_mb = total_size / (1024**2)
        if size_gb >= 1:
            print(f"\n💾 حجم کل: {size_gb:.2f} GB")
        else:
            print(f"\n💾 حجم کل: {size_mb:.2f} MB")
    
    print("="*60)


def main():
    """تابع اصلی"""
    start_time = time.time()
    
    print("="*60)
    print("🪞 Telegram Mirror - Full Media Support")
    print("="*60)
    print(f"⏰ شروع: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 پوشه رسانه: {MEDIA_DIR.absolute()}")
    print("="*60)
    
    # بارگذاری کانال‌ها
    channels = load_channels()
    if not channels:
        print("\n❌ برنامه متوقف شد. کانالی برای پردازش وجود ندارد.")
        return
    
    # بارگذاری دیتابیس
    db = load_posts_db()
    
    # بروزرسانی هر کانال
    for channel in channels:
        db = update_channel(channel, db)
    
    # بروزرسانی زمان آخرین اجرا
    db["last_update"] = datetime.now().isoformat()
    
    # ذخیره دیتابیس (آمار خودکار محاسبه می‌شود)
    save_posts_db(db)
    
    # نمایش آمار نهایی
    print_statistics(db)
    
    elapsed = time.time() - start_time
    print(f"\n⏱️ زمان اجرا: {elapsed:.2f} ثانیه")
    print("✅ عملیات با موفقیت کامل شد!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ برنامه متوقف شد.")
    except Exception as e:
        print(f"\n❌ خطا: {e}")
        import traceback
        traceback.print_exc()
