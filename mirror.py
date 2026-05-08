#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Channel Mirror - Complete Version with All Files & Links Support
------------------------------------------------------
- پشتیبانی از تمام انواع فایل (ZIP, APK, PDF, تصاویر, ویدیوها, اسناد)
- استخراج و ذخیره لینک‌های خارجی پست‌ها
- دانلود فایل‌های ضمیمه شده
- ذخیره لینک‌های تلگرامی و خارجی
- بهینه‌سازی برای GitHub Actions
- پاکسازی خودکار فایل‌های قدیمی
- مدیریت حافظه و retry mechanism
"""

import os
import json
import time
import hashlib
import mimetypes
import re
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urlparse, unquote
import requests
from bs4 import BeautifulSoup

# ============================================
# تنظیمات - قابل تنظیم توسط کاربر
# ============================================

# محدودیت‌ها برای GitHub Actions
MAX_FILE_SIZE_MB = 100          # حداکثر حجم هر فایل (MB)
MAX_TOTAL_SIZE_MB = 500         # حداکثر حجم کل پوشه media (MB)
MAX_POSTS_PER_CHANNEL = 100     # حداکثر پست نگهداری شده برای هر کانال
MAX_RETRIES = 3                 # تعداد دفعات تکرار دانلود
REQUEST_TIMEOUT = 45            # تایم‌اوت درخواست‌ها (ثانیه)

# تنظیمات پاکسازی
AUTO_CLEANUP_DAYS = 30          # پاک کردن فایل‌های قدیمی‌تر از X روز
KEEP_RECENT_POSTS = 100         # نگهداری X پست آخر هر کانال

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
        'max_size': 50
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
    'links': {
        'extensions': [],
        'icon': '🔗',
        'folder': None,  # لینک‌ها در پوشه ذخیره نمی‌شوند
        'max_size': 0
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
        if category['folder']:
            folder = MEDIA_DIR / category['folder']
            folder.mkdir(exist_ok=True)
            print(f"  ✓ {category['folder']}/")
    
    print(f"✅ پوشه‌های مورد نیاز ایجاد شدند")


def get_file_category(filename: str) -> Tuple[str, str, int]:
    """تشخیص دسته‌بندی فایل"""
    ext = Path(filename).suffix.lower()
    
    for category_name, category_info in FILE_CATEGORIES.items():
        if ext in category_info['extensions']:
            folder = category_info['folder'] if category_info['folder'] else 'other'
            return category_name, folder, category_info.get('max_size', MAX_FILE_SIZE_MB)
    
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
        elif 'pdf' in mime_type:
            return 'documents', 'documents', FILE_CATEGORIES['documents']['max_size']
    
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
    """پاکسازی فایل‌های قدیمی و یتیم"""
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
        if not category['folder']:
            continue
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
        
        all_files = []
        for category in FILE_CATEGORIES.values():
            if not category['folder']:
                continue
            folder = media_path / category['folder']
            if folder.exists():
                for file in folder.iterdir():
                    if file.is_file():
                        all_files.append({
                            'path': file,
                            'mtime': file.stat().st_mtime,
                            'size': file.stat().st_size
                        })
        
        all_files.sort(key=lambda x: x['mtime'])
        
        freed_size = 0
        removed_count = 0
        for file_info in all_files:
            if total_size - freed_size <= max_size_bytes * 0.8:
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
                "total_links": 0,
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
            "total_links": 0,
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
                "total_links": 0,
                "files_by_type": {},
                "total_size_mb": 0
            }
        }


def save_posts_db(data: Dict):
    """ذخیره دیتابیس با آمار به‌روز"""
    # محاسبه آمار
    total_posts = 0
    total_files = 0
    total_links = 0
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
                
                file_path = Path("media") / media.get("path", "")
                if file_path.exists():
                    total_size += file_path.stat().st_size
            
            for link in post.get("links", []):
                total_links += 1
    
    data["statistics"] = {
        "total_posts": total_posts,
        "total_files": total_files,
        "total_links": total_links,
        "files_by_type": files_by_type,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "last_calculation": datetime.now().isoformat()
    }
    
    try:
        with open("posts.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 دیتابیس ذخیره شد: {total_posts} پست، {total_files} فایل، {total_links} لینک")
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


# ============================================
# توابع استخراج لینک‌ها و فایل‌ها
# ============================================

def extract_all_links(text: str) -> List[Dict]:
    """
    استخراج تمام لینک‌های خارجی از متن پست
    """
    links = []
    seen_urls = set()
    
    if not text:
        return links
    
    # الگوی لینک‌های معمولی
    url_pattern = r'https?://[^\s<>"\'{}|\\^`\[\]]+'
    
    for match in re.finditer(url_pattern, text):
        url = match.group()
        
        # حذف لینک‌های تکراری
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        # تشخیص نوع لینک
        link_type = 'external'
        if 't.me' in url or 'telegram' in url:
            link_type = 'telegram'
        elif 'youtube.com' in url or 'youtu.be' in url:
            link_type = 'youtube'
        elif 'twitter.com' in url or 'x.com' in url:
            link_type = 'twitter'
        elif 'instagram.com' in url:
            link_type = 'instagram'
        elif 'github.com' in url:
            link_type = 'github'
        
        links.append({
            "url": url,
            "type": link_type,
            "text": match.group()
        })
    
    return links


def extract_file_links_from_post(post_element, channel: str, post_id: str) -> List[Dict]:
    """
    استخراج لینک‌های فایل از المان‌های HTML پست
    """
    links = []
    seen_urls = set()
    
    # الگوهای مختلف برای یافتن لینک فایل
    patterns = [
        ('a[href*="/file/"]', 'href'),
        ('a[href*="download"]', 'href'),
        ('a[href*="telegram.org/file"]', 'href'),
        ('a[href$=".apk"]', 'href'),
        ('a[href$=".zip"]', 'href'),
        ('a[href$=".pdf"]', 'href'),
        ('a[href$=".mp4"]', 'href'),
        ('a[href$=".mp3"]', 'href'),
        ('a[href*="drive.google.com"]', 'href'),
        ('[data-url]', 'data-url'),
        ('[data-file]', 'data-file'),
        ('[data-document]', 'data-document'),
    ]
    
    for selector, attr in patterns:
        for elem in post_element.select(selector):
            url = elem.get(attr)
            if url and url.startswith('http') and url not in seen_urls:
                seen_urls.add(url)
                links.append({'url': url, 'type': 'document'})
    
    return links


def download_file(url: str, filepath: Path, max_size_mb: int = MAX_FILE_SIZE_MB) -> bool:
    """دانلود فایل با محدودیت حجم و پشتیبانی از resume"""
    if filepath.exists() and filepath.stat().st_size > 0:
        return True
    
    temp_path = filepath.with_suffix(filepath.suffix + '.part')
    
    for attempt in range(MAX_RETRIES):
        try:
            headers = {'User-Agent': USER_AGENT}
            
            if temp_path.exists():
                existing_size = temp_path.stat().st_size
                headers['Range'] = f'bytes={existing_size}-'
            else:
                existing_size = 0
            
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
            
            # بررسی حجم فایل
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
                            
                            if downloaded / (1024 * 1024) > max_size_mb:
                                print(f"  ⚠️ حجم فایل از حد مجاز عبور کرد")
                                temp_path.unlink(missing_ok=True)
                                return False
                
                if downloaded > 0:
                    temp_path.rename(filepath)
                    return True
                    
            elif response.status_code == 429:
                wait_time = 60 * (attempt + 1)
                print(f"  ⚠️ Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
    
    temp_path.unlink(missing_ok=True)
    return False


def process_post_media(post_element, channel: str, post_id: str) -> Tuple[List[Dict], List[Dict]]:
    """
    پردازش و دانلود تمام فایل‌های یک پست
    بازگشت: (media_list, external_links)
    """
    media_list = []
    external_links = []
    seen_urls = set()
    media_index = 0
    
    # 1. استخراج تصاویر از استایل background-image
    for elem in post_element.select('[style*="background-image"]'):
        style = elem.get('style', '')
        match = re.search(r'url\(["\']?([^"\'()]+)["\']?\)', style)
        if match:
            url = match.group(1)
            if url.startswith('http') and url not in seen_urls:
                seen_urls.add(url)
                
                filename = f"{channel}_{post_id}_{media_index}_{hashlib.md5(url.encode()).hexdigest()[:8]}.jpg"
                file_type, subfolder, max_size = get_file_category(filename)
                filepath = Path("media") / subfolder / filename
                
                if download_file(url, filepath, max_size):
                    relative_path = f"{subfolder}/{filename}"
                    media_list.append({
                        "type": file_type,
                        "subfolder": subfolder,
                        "file": filename,
                        "path": relative_path,
                        "icon": FILE_CATEGORIES.get(file_type, FILE_CATEGORIES['other'])['icon']
                    })
                    media_index += 1
    
    # 2. استخراج از تگ‌های img
    for img in post_element.select('img'):
        for attr in ['src', 'data-src']:
            url = img.get(attr)
            if url and url.startswith('http') and url not in seen_urls:
                seen_urls.add(url)
                
                # استخراج نام فایل
                parsed = urlparse(url)
                original_name = Path(unquote(parsed.path)).name
                if original_name and '.' in original_name:
                    filename = f"{channel}_{post_id}_{media_index}_{original_name}"
                else:
                    filename = f"{channel}_{post_id}_{media_index}_{hashlib.md5(url.encode()).hexdigest()[:8]}.jpg"
                
                file_type, subfolder, max_size = get_file_category(filename)
                filepath = Path("media") / subfolder / filename
                
                if download_file(url, filepath, max_size):
                    relative_path = f"{subfolder}/{filename}"
                    media_list.append({
                        "type": file_type,
                        "subfolder": subfolder,
                        "file": filename,
                        "path": relative_path,
                        "icon": FILE_CATEGORIES.get(file_type, FILE_CATEGORIES['other'])['icon']
                    })
                    media_index += 1
                break
    
    # 3. استخراج از تگ‌های video, audio
    for tag_type in ['video', 'audio']:
        for elem in post_element.select(tag_type):
            url = elem.get('src')
            if url and url.startswith('http') and url not in seen_urls:
                seen_urls.add(url)
                
                parsed = urlparse(url)
                original_name = Path(unquote(parsed.path)).name
                if original_name and '.' in original_name:
                    filename = f"{channel}_{post_id}_{media_index}_{original_name}"
                else:
                    ext = '.mp4' if tag_type == 'video' else '.mp3'
                    filename = f"{channel}_{post_id}_{media_index}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
                
                file_type, subfolder, max_size = get_file_category(filename)
                filepath = Path("media") / subfolder / filename
                
                if download_file(url, filepath, max_size):
                    relative_path = f"{subfolder}/{filename}"
                    media_list.append({
                        "type": file_type,
                        "subfolder": subfolder,
                        "file": filename,
                        "path": relative_path,
                        "icon": FILE_CATEGORIES.get(file_type, FILE_CATEGORIES['other'])['icon']
                    })
                    media_index += 1
    
    # 4. استخراج لینک‌های فایل از تگ‌های a
    file_links = extract_file_links_from_post(post_element, channel, post_id)
    for link_info in file_links:
        url = link_info['url']
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        parsed = urlparse(url)
        original_name = Path(unquote(parsed.path)).name
        if original_name and '.' in original_name:
            filename = f"{channel}_{post_id}_{media_index}_{original_name}"
        else:
            filename = f"{channel}_{post_id}_{media_index}_{hashlib.md5(url.encode()).hexdigest()[:8]}.file"
        
        file_type, subfolder, max_size = get_file_category(filename)
        filepath = Path("media") / subfolder / filename
        
        if download_file(url, filepath, max_size):
            relative_path = f"{subfolder}/{filename}"
            media_list.append({
                "type": file_type,
                "subfolder": subfolder,
                "file": filename,
                "path": relative_path,
                "icon": FILE_CATEGORIES.get(file_type, FILE_CATEGORIES['other'])['icon']
            })
            media_index += 1
    
    return media_list, external_links


# ============================================
# توابع اصلی دریافت پست‌ها
# ============================================

def fetch_new_posts(channel: str, existing_ids: Set[int]) -> List[Dict]:
    """دریافت فقط پست‌های جدید (بهینه شده)"""
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
            
            # اگر به پست موجود رسیدیم، ادامه نمی‌دهیم
            if post_id in existing_ids:
                if not found_new:
                    pass
                break
            
            found_new = True
            
            try:
                # متن پست
                text_elem = element.select_one('.tgme_widget_message_text')
                text = text_elem.get_text(strip=True) if text_elem else ""
                
                # تاریخ
                time_elem = element.select_one('time')
                date = time_elem.get('datetime', datetime.now().isoformat()) if time_elem else datetime.now().isoformat()
                
                # استخراج لینک‌های خارجی از متن
                external_links = extract_all_links(text)
                
                # پردازش و دانلود رسانه‌ها
                media_list, _ = process_post_media(element, channel, str(post_id))
                
                new_posts.append({
                    "id": post_id,
                    "text": text,
                    "date": date,
                    "media": media_list,
                    "links": external_links,
                    "has_media": len(media_list) > 0,
                    "has_links": len(external_links) > 0
                })
                
                if media_list:
                    print(f"  📎 پست {post_id}: {len(media_list)} فایل, {len(external_links)} لینک")
                
            except Exception as e:
                print(f"  ⚠️ خطا در پردازش پست {post_id}: {e}")
                continue
        
        if new_posts:
            print(f"  ✨ {len(new_posts)} پست جدید دریافت شد")
        
        return new_posts
        
    except Exception as e:
        print(f"  ❌ خطا: {e}")
        return []


# ============================================
# توابع بروزرسانی کانال
# ============================================

def update_channel(channel: str, db: Dict) -> Dict:
    """بروزرسانی یک کانال (فقط پست‌های جدید)"""
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
    
    # اضافه کردن پست‌های جدید
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
    total_links = sum(len(post.get("links", [])) for post in db["channels"][channel])
    
    print(f"\n  📊 @{channel}:")
    print(f"     • پست‌های جدید: {len(new_posts)}")
    print(f"     • کل پست‌ها: {len(db['channels'][channel])}")
    print(f"     • کل فایل‌ها: {total_files}")
    print(f"     • کل لینک‌ها: {total_links}")
    
    return db
    return db


# ============================================
# توابع نمایش آمار و اصلی
# ============================================

def print_statistics(db: Dict):
    """نمایش آمار کامل"""
    stats = db.get("statistics", {})
    
    print("\n" + "="*60)
    print("📊 آمار نهایی")
    print("="*60)
    print(f"📺 کانال‌ها: {len(db.get('channels', {}))}")
    print(f"📝 کل پست‌ها: {stats.get('total_posts', 0):,}")
    print(f"📎 کل فایل‌ها: {stats.get('total_files', 0):,}")
    print(f"🔗 کل لینک‌ها: {stats.get('total_links', 0):,}")
    print(f"💾 حجم کل: {stats.get('total_size_mb', 0):,} MB")
    print(f"🕐 آخرین بروزرسانی: {db.get('last_update', 'ندارد')}")
    
    print("\n📂 تفکیک بر اساس نوع فایل:")
    files_by_type = stats.get('files_by_type', {})
    for file_type, count in sorted(files_by_type.items(), key=lambda x: x[1], reverse=True):
        if count > 0 and file_type != 'links':
            icon = FILE_CATEGORIES.get(file_type, FILE_CATEGORIES['other'])['icon']
            print(f"   {icon} {file_type}: {count:,} فایل")
    
    print("="*60)


def main():
    """تابع اصلی"""
    start_time = time.time()
    
    print("="*60)
    print("🪞 Telegram Mirror - Complete Version with All Files & Links")
    print("="*60)
    print(f"⏰ شروع: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⚙️ تنظیمات:")
    print(f"   • حداکثر حجم هر فایل: {MAX_FILE_SIZE_MB} MB")
    print(f"   • حداکثر حجم کل: {MAX_TOTAL_SIZE_MB} MB")
    print(f"   • حداکثر پست هر کانال: {MAX_POSTS_PER_CHANNEL}")
    print(f"   • پشتیبانی از لینک‌های خارجی: ✓ فعال")
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
