#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Channel Mirror - Optimized Production Version
------------------------------------------------------
- پشتیبانی از تمام انواع فایل (ZIP, APK, PDF, و ...)
- محدودیت حجم فایل برای GitHub Actions
- پردازش افزایشی (فقط پست‌های جدید)
- پاکسازی خودکار فایل‌های قدیمی
- مدیریت حافظه و بهینه‌سازی سرعت
"""

import os
import json
import time
import hashlib
import mimetypes
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Set
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote
import re

# ============================================
# تنظیمات - قابل تنظیم توسط کاربر
# ============================================

# محدودیت‌ها برای GitHub Actions
MAX_FILE_SIZE_MB = 100          # حداکثر حجم هر فایل (MB)
MAX_TOTAL_SIZE_MB = 500         # حداکثر حجم کل پوشه media (MB)
MAX_POSTS_PER_CHANNEL = 50      # حداکثر پست نگهداری شده برای هر کانال
MAX_RETRIES = 3                 # تعداد دفعات تکرار دانلود
REQUEST_TIMEOUT = 45            # تایم‌اوت درخواست‌ها (ثانیه)

# تنظیمات پاکسازی
AUTO_CLEANUP_DAYS = 30          # پاک کردن فایل‌های قدیمی‌تر از X روز
KEEP_RECENT_POSTS = 50          # نگهداری X پست آخر هر کانال

# تنظیمات دانلود
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CHUNK_SIZE = 32768              # سایز هر chunk برای دانلود (32KB)

# ============================================
# پیکربندی انواع فایل‌ها
# ============================================

FILE_CATEGORIES = {
    'images': {
        'extensions': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico', '.tiff', '.heic'],
        'icon': '🖼️',
        'folder': 'images',
        'max_size': 50  # حداکثر حجم هر فایل در این دسته (MB)
    },
    'videos': {
        'extensions': ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.m4v', '.3gp', '.mpeg', '.mpg', '.wmv'],
        'icon': '🎬',
        'folder': 'videos',
        'max_size': 100
    },
    'audios': {
        'extensions': ['.mp3', '.ogg', '.wav', '.m4a', '.flac', '.aac', '.opus', '.wma', '.aiff'],
        'icon': '🎵',
        'folder': 'audios',
        'max_size': 50
    },
    'documents': {
        'extensions': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md', '.rtf', '.odt', '.ods', '.odp'],
        'icon': '📄',
        'folder': 'documents',
        'max_size': 50
    },
    'archives': {
        'extensions': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2'],
        'icon': '📦',
        'folder': 'archives',
        'max_size': 100
    },
    'applications': {
        'extensions': ['.apk', '.exe', '.msi', '.deb', '.rpm', '.appimage', '.dmg', '.bin', '.sh', '.bat'],
        'icon': '📱',
        'folder': 'applications',
        'max_size': 100
    },
    'code': {
        'extensions': ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.php', '.rb', '.go', '.rs', '.json', '.xml', '.yaml', '.yml'],
        'icon': '💻',
        'folder': 'code',
        'max_size': 10
    },
    'other': {
        'extensions': [],
        'icon': '📎',
        'folder': 'other',
        'max_size': 20
    }
}

# ============================================
# توابع مدیریت پوشه‌ها
# ============================================

def ensure_directories():
    """ایجاد تمام پوشه‌های مورد نیاز"""
    MEDIA_DIR = Path("media")
    MEDIA_DIR.mkdir(exist_ok=True)
    
    for category in FILE_CATEGORIES.values():
        folder = MEDIA_DIR / category['folder']
        folder.mkdir(exist_ok=True)
        print(f"  ✓ {category['folder']}/")
    
    print(f"✅ پوشه‌های مورد نیاز ایجاد شدند")


def get_file_category(filename: str) -> Tuple[str, str, int]:
    """
    تشخیص دسته‌بندی فایل
    بازگشت: (نام دسته, مسیر پوشه, حداکثر حجم مجاز)
    """
    ext = Path(filename).suffix.lower()
    
    for category_name, category_info in FILE_CATEGORIES.items():
        if ext in category_info['extensions']:
            return category_name, category_info['folder'], category_info.get('max_size', MAX_FILE_SIZE_MB)
    
    # تلاش بر اساس mime type
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        if mime_type.startswith('image/'):
            return 'images', 'images', FILE_CATEGORIES['images']['max_size']
        elif mime_type.startswith('video/'):
            return 'videos', 'videos', FILE_CATEGORIES['videos']['max_size']
        elif mime_type.startswith('audio/'):
            return 'audios', 'audios', FILE_CATEGORIES['audios']['max_size']
        elif 'zip' in mime_type or 'compressed' in mime_type:
            return 'archives', 'archives', FILE_CATEGORIES['archives']['max_size']
        elif 'apk' in mime_type or 'android' in mime_type:
            return 'applications', 'applications', FILE_CATEGORIES['applications']['max_size']
    
    return 'other', 'other', FILE_CATEGORIES['other']['max_size']


def get_total_media_size() -> int:
    """محاسبه حجم کل پوشه media به بایت"""
    media_path = Path("media")
    if not media_path.exists():
        return 0
    
    total = 0
    for file in media_path.rglob('*'):
        if file.is_file():
            total += file.stat().st_size
    return total


def cleanup_old_files(db: Dict):
    """
    پاکسازی فایل‌های قدیمی که در دیتابیس نیستند
    و همچنین فایل‌هایی که از محدودیت حجم عبور کرده‌اند
    """
    print("\n🧹 شروع پاکسازی فایل‌های قدیمی...")
    
    media_path = Path("media")
    if not media_path.exists():
        return
    
    # جمع‌آوری تمام فایل‌های موجود در دیتابیس
    used_files: Set[str] = set()
    for channel, posts in db.get("channels", {}).items():
        for post in posts:
            for media in post.get("media", []):
                file_path = media.get("path", "")
                if file_path:
                    used_files.add(file_path)
    
    # پاکسازی فایل‌های یتیم
    orphaned_count = 0
    orphaned_size = 0
    
    for category in FILE_CATEGORIES.values():
        folder = media_path / category['folder']
        if not folder.exists():
            continue
            
        for file in folder.iterdir():
            if file.is_file():
                relative_path = f"{category['folder']}/{file.name}"
                if relative_path not in used_files:
                    file_size = file.stat().st_size
                    orphaned_size += file_size
                    file.unlink()
                    orphaned_count += 1
                    print(f"  🗑️ حذف فایل یتیم: {relative_path}")
    
    if orphaned_count > 0:
        print(f"  ✅ {orphaned_count} فایل یتیم حذف شد ({orphaned_size / (1024*1024):.2f} MB)")
    else:
        print("  ✅ هیچ فایل یتیمی یافت نشد")
    
    # بررسی حجم کل و پاکسازی در صورت نیاز
    total_size = get_total_media_size()
    max_size_bytes = MAX_TOTAL_SIZE_MB * 1024 * 1024
    
    if total_size > max_size_bytes:
        print(f"\n⚠️ حجم کل از حد مجاز عبور کرده است!")
        print(f"   حجم فعلی: {total_size / (1024*1024):.2f} MB")
        print(f"   حد مجاز: {MAX_TOTAL_SIZE_MB} MB")
        print(f"   شروع پاکسازی فایل‌های قدیمی...")
        
        # جمع‌آوری تمام فایل‌ها با زمان آخرین دسترسی
        all_files = []
        for category in FILE_CATEGORIES.values():
            folder = media_path / category['folder']
            if folder.exists():
                for file in folder.iterdir():
                    if file.is_file():
                        all_files.append({
                            'path': file,
                            'mtime': file.stat().st_mtime,
                            'size': file.stat().st_size
                        })
        
        # مرتب‌سازی بر اساس زمان (قدیمی‌ترها اول)
        all_files.sort(key=lambda x: x['mtime'])
        
        # حذف فایل‌های قدیمی تا رسیدن به حجم مجاز
        freed_size = 0
        removed_count = 0
        for file_info in all_files:
            if total_size - freed_size <= max_size_bytes * 0.8:  # 80% of limit
                break
            
            file_info['path'].unlink()
            freed_size += file_info['size']
            removed_count += 1
            print(f"  🗑️ حذف فایل قدیمی: {file_info['path'].name}")
        
        if removed_count > 0:
            print(f"  ✅ {removed_count} فایل قدیمی حذف شد ({freed_size / (1024*1024):.2f} MB)")


# ============================================
# توابع مدیریت دیتابیس
# ============================================

def load_posts_db() -> Dict:
    """بارگذاری دیتابیس پست‌ها"""
    posts_file = Path("posts.json")
    
    if not posts_file.exists():
        print("📁 ایجاد فایل جدید posts.json...")
        return {
            "channels": {},
            "last_update": None,
            "statistics": {
                "total_posts": 0,
                "total_files": 0,
                "files_by_type": {},
                "total_size_mb": 0
            }
        }
    
    try:
        with open(posts_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        data.setdefault("channels", {})
        data.setdefault("last_update", None)
        data.setdefault("statistics", {
            "total_posts": 0,
            "total_files": 0,
            "files_by_type": {},
            "total_size_mb": 0
        })
        
        return data
        
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️ خطا در خواندن posts.json: {e}")
        return {
            "channels": {},
            "last_update": None,
            "statistics": {
                "total_posts": 0,
                "total_files": 0,
                "files_by_type": {},
                "total_size_mb": 0
            }
        }


def save_posts_db(data: Dict):
    """ذخیره دیتابیس با آمار به‌روز"""
    # محاسبه آمار
    total_posts = 0
    total_files = 0
    files_by_type = {cat: 0 for cat in FILE_CATEGORIES.keys()}
    total_size = 0
    
    for channel, posts in data.get("channels", {}).items():
        total_posts += len(posts)
        for post in posts:
            for media in post.get("media", []):
                total_files += 1
                file_type = media.get("type", "other")
                if file_type in files_by_type:
                    files_by_type[file_type] += 1
                
                # اضافه کردن حجم فایل
                file_path = Path("media") / media.get("path", "")
                if file_path.exists():
                    total_size += file_path.stat().st_size
    
    data["statistics"] = {
        "total_posts": total_posts,
        "total_files": total_files,
        "files_by_type": files_by_type,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "last_calculation": datetime.now().isoformat()
    }
    
    try:
        with open("posts.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 دیتابیس ذخیره شد: {total_posts} پست، {total_files} فایل")
    except Exception as e:
        print(f"❌ خطا در ذخیره: {e}")


def load_channels() -> List[str]:
    """خواندن لیست کانال‌ها از list.txt"""
    list_file = Path("list.txt")
    
    if not list_file.exists():
        print("❌ فایل list.txt یافت نشد!")
        print("📝 لطفاً فایل list.txt را با نام کانال‌ها ایجاد کنید")
        return []
    
    try:
        with open(list_file, 'r', encoding='utf-8') as f:
            channels = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        channels = [ch.replace('@', '') for ch in channels]
        
        if channels:
            print(f"📋 کانال‌ها: {', '.join(channels)}")
        return channels
        
    except Exception as e:
        print(f"❌ خطا: {e}")
        return []


def get_existing_post_ids(channel: str, db: Dict) -> Set[int]:
    """دریافت مجموعه ID پست‌های موجود در دیتابیس"""
    if channel not in db.get("channels", {}):
        return set()
    return {post["id"] for post in db["channels"][channel]}


def download_file(url: str, filepath: Path, max_size_mb: int = MAX_FILE_SIZE_MB) -> bool:
    """
    دانلود فایل با محدودیت حجم و پشتیبانی از resume
    """
    # بررسی وجود فایل
    if filepath.exists() and filepath.stat().st_size > 0:
        return True
    
    temp_path = filepath.with_suffix(filepath.suffix + '.part')
    
    for attempt in range(MAX_RETRIES):
        try:
            headers = {'User-Agent': USER_AGENT}
            
            # پشتیبانی از resume
            if temp_path.exists():
                existing_size = temp_path.stat().st_size
                headers['Range'] = f'bytes={existing_size}-'
            else:
                existing_size = 0
            
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
            
            # بررسی حجم فایل قبل از دانلود
            content_length = response.headers.get('Content-Length')
            if content_length:
                size_mb = int(content_length) / (1024 * 1024)
                if size_mb > max_size_mb:
                    print(f"  ⚠️ فایل بزرگ‌تر از {max_size_mb}MB رد شد ({size_mb:.1f}MB)")
                    return False
            
            if response.status_code in [200, 206]:
                mode = 'ab' if existing_size > 0 else 'wb'
                downloaded = existing_size
                
                with open(temp_path, mode) as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # بررسی حجم در حین دانلود
                            if downloaded / (1024 * 1024) > max_size_mb:
                                print(f"  ⚠️ حجم فایل از حد مجاز عبور کرد، قطع دانلود")
                                temp_path.unlink(missing_ok=True)
                                return False
                
                if downloaded > 0:
                    temp_path.rename(filepath)
                    return True
                    
            elif response.status_code == 404:
                return False
                
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
    
    temp_path.unlink(missing_ok=True)
    return False


def fetch_new_posts(channel: str, existing_ids: Set[int]) -> List[Dict]:
    """
    دریافت فقط پست‌های جدید (بهینه شده)
    """
    url = f"https://t.me/s/{channel}"
    print(f"\n📡 دریافت پست‌های جدید @{channel}")
    
    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            print(f"  ❌ خطا: HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'lxml')
        post_elements = soup.select('.tgme_widget_message')
        
        if not post_elements:
            return []
        
        new_posts = []
        found_new = False
        
        for element in post_elements:
            # استخراج ID
            data_post = element.get('data-post', '')
            if '/' in data_post:
                post_id = int(data_post.split('/')[-1])
            else:
                continue
            
            # اگر به پست موجود رسیدیم، ادامه نمی‌دهیم (بهینه‌سازی)
            if post_id in existing_ids:
                if not found_new:
                    print(f"  📍 به پست‌های موجود رسیدیم،停止")
                break
            
            found_new = True
            
            # پردازش پست جدید
            try:
                # متن
                text_elem = element.select_one('.tgme_widget_message_text')
                text = text_elem.get_text(strip=True) if text_elem else ""
                
                # تاریخ
                time_elem = element.select_one('time')
                date = time_elem.get('datetime', datetime.now().isoformat()) if time_elem else datetime.now().isoformat()
                
                # استخراج لینک‌های فایل
                media_list = extract_and_download_media(element, channel, str(post_id))
                
                new_posts.append({
                    "id": post_id,
                    "text": text,
                    "date": date,
                    "media": media_list,
                    "has_media": len(media_list) > 0
                })
                
            except Exception as e:
                print(f"  ⚠️ خطا در پردازش پست {post_id}: {e}")
                continue
        
        if new_posts:
            print(f"  ✨ {len(new_posts)} پست جدید دریافت شد")
        
        return new_posts
        
    except Exception as e:
        print(f"  ❌ خطا: {e}")
        return []


def extract_and_download_media(post_element, channel: str, post_id: str) -> List[Dict]:
    """
    استخراج و دانلود تمام فایل‌های یک پست
    """
    media_list = []
    seen_urls = set()
    media_index = 0
    
    # الگوهای مختلف برای یافتن لینک فایل
    patterns = [
        ('[style*="background-image"]', 'style', r'url\(["\']?([^"\'()]+)["\']?\)'),
        ('img', 'src', None),
        ('img', 'data-src', None),
        ('video', 'src', None),
        ('audio', 'src', None),
        ('a[href*="/file/"]', 'href', None),
        ('a[href*="download"]', 'href', None),
        ('[data-url]', 'data-url', None),
        ('[data-file]', 'data-file', None),
        ('[data-document]', 'data-document', None),
    ]
    
    for selector, attr, pattern in patterns:
        for elem in post_element.select(selector):
            if pattern:
                # استخراج با regex
                style = elem.get(attr, '')
                match = re.search(pattern, style)
                if match:
                    url = match.group(1)
                else:
                    continue
            else:
                url = elem.get(attr)
            
            if not url or not url.startswith('http') or url in seen_urls:
                continue
            
            seen_urls.add(url)
            
            # تشخیص نوع و دانلود
            filename = f"{channel}_{post_id}_{media_index}_{hashlib.md5(url.encode()).hexdigest()[:8]}"
            
            # تلاش برای استخراج نام اصلی
            parsed = urlparse(url)
            original = Path(unquote(parsed.path)).name
            if original and '.' in original:
                ext = Path(original).suffix
                filename = f"{channel}_{post_id}_{media_index}_{original}"
            
            # تشخیص دسته‌بندی
            file_type, subfolder, max_size = get_file_category(filename)
            filepath = Path("media") / subfolder / filename
            
            if download_file(url, filepath, max_size):
                relative_path = f"{subfolder}/{filename}"
                media_list.append({
                    "type": file_type,
                    "subfolder": subfolder,
                    "file": filename,
                    "path": relative_path,
                    "icon": FILE_CATEGORIES.get(file_type, FILE_CATEGORIES['other'])['icon'],
                    "size": filepath.stat().st_size if filepath.exists() else 0
                })
                media_index += 1
    
    return media_list


def update_channel(channel: str, db: Dict) -> Dict:
    """
    بروزرسانی یک کانال (فقط پست‌های جدید)
    """
    print(f"\n{'='*60}")
    print(f"🔄 بروزرسانی: @{channel}")
    print(f"{'='*60}")
    
    # دریافت IDهای موجود
    existing_ids = get_existing_post_ids(channel, db)
    print(f"  📊 پست‌های موجود: {len(existing_ids)}")
    
    # دریافت فقط پست‌های جدید
    new_posts = fetch_new_posts(channel, existing_ids)
    
    if not new_posts:
        print("  ✅ پست جدیدی یافت نشد")
        return db
    
    # اطمینان از وجود کانال در دیتابیس
    if channel not in db["channels"]:
        db["channels"][channel] = []
    
    # اضافه کردن پست‌های جدید (مرتب‌سازی نزولی)
    for post in new_posts:
        db["channels"][channel].append(post)
    
    # مرتب‌سازی بر اساس ID (جدیدترین اول)
    db["channels"][channel].sort(key=lambda x: x["id"], reverse=True)
    
    # محدودیت تعداد پست‌ها
    if len(db["channels"][channel]) > MAX_POSTS_PER_CHANNEL:
        removed_posts = db["channels"][channel][MAX_POSTS_PER_CHANNEL:]
        db["channels"][channel] = db["channels"][channel][:MAX_POSTS_PER_CHANNEL]
        
        # حذف فایل‌های پست‌های قدیمی
        for post in removed_posts:
            for media in post.get("media", []):
                file_path = Path("media") / media.get("path", "")
                if file_path.exists():
                    file_path.unlink()
                    print(f"  🗑️ حذف فایل قدیمی: {media.get('file')}")
        
        print(f"  🗑️ {len(removed_posts)} پست قدیمی حذف شد")
    
    # آمار
    total_files = sum(len(post.get("media", [])) for post in db["channels"][channel])
    print(f"\n  📊 @{channel}:")
    print(f"     • پست‌های جدید: {len(new_posts)}")
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
    print(f"💾 حجم کل: {stats.get('total_size_mb', 0)} MB")
    print(f"🕐 آخرین بروزرسانی: {db.get('last_update', 'ندارد')}")
    
    print("\n📂 تفکیک بر اساس نوع فایل:")
    files_by_type = stats.get('files_by_type', {})
    for file_type, count in sorted(files_by_type.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            icon = FILE_CATEGORIES.get(file_type, FILE_CATEGORIES['other'])['icon']
            print(f"   {icon} {file_type}: {count} فایل")
    
    print("="*60)


def main():
    """تابع اصلی"""
    start_time = time.time()
    
    print("="*60)
    print("🪞 Telegram Mirror - Optimized Version")
    print("="*60)
    print(f"⏰ شروع: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⚙️ تنظیمات:")
    print(f"   • حداکثر حجم هر فایل: {MAX_FILE_SIZE_MB} MB")
    print(f"   • حداکثر حجم کل: {MAX_TOTAL_SIZE_MB} MB")
    print(f"   • حداکثر پست هر کانال: {MAX_POSTS_PER_CHANNEL}")
    print("="*60)
    
    # ایجاد پوشه‌ها
    ensure_directories()
    
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
    
    # پاکسازی فایل‌های قدیمی
    cleanup_old_files(db)
    
    # بروزرسانی زمان آخرین اجرا
    db["last_update"] = datetime.now().isoformat()
    
    # ذخیره دیتابیس
    save_posts_db(db)
    
    # نمایش آمار
    print_statistics(db)
    
    elapsed = time.time() - start_time
    print(f"\n⏱️ زمان اجرا: {elapsed:.2f} ثانیه")
    print("✅ عملیات با موفقیت کامل شد!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ برنامه توسط کاربر متوقف شد.")
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
