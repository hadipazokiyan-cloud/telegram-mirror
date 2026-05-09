#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Mirror - Enterprise Grade
===================================
- Fully rewritten from scratch
- Robust media detection and filtering
- Parallel processing with intelligent queuing
- Atomic operations with retry mechanisms
- Clean, modular architecture
- Production-ready for GitHub Actions
"""

import os
import re
import json
import time
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote

import requests
from bs4 import BeautifulSoup

# ============================================================================
# CONFIGURATION - تنظیمات اصلی
# ============================================================================

CONFIG = {
    # فایل‌ها و مسیرها
    "list_file": "list.txt",
    "db_file": "posts.json",
    "media_dir": Path("media"),
    "cache_dir": Path("_cache_html"),
    
    # محدودیت‌ها
    "max_retries": 3,
    "timeout": 30,
    "max_file_size_mb": 200,
    "max_posts_per_channel": 200,
    "max_channels_parallel": 4,
    "max_downloads_parallel": 6,
    
    # رفتارها
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "backoff_factor": 1.5,
    "chunk_size": 256 * 1024,  # 256 KB
}

# ============================================================================
# VALID MEDIA EXTENSIONS - پسوندهای معتبر فایل
# ============================================================================

VALID_EXTENSIONS = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico', '.tiff',
    # Videos
    '.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.m4v', '.3gp', '.mpeg', '.mpg',
    # Audio
    '.mp3', '.ogg', '.wav', '.m4a', '.flac', '.aac', '.opus', '.wma',
    # Documents
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md', '.rtf',
    '.odt', '.ods', '.odp',
    # Archives
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tgz',
    # Applications
    '.apk', '.exe', '.msi', '.deb', '.rpm', '.dmg', '.bin', '.sh', '.bat',
    # Code
    '.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.php', '.rb', '.go',
    '.rs', '.json', '.xml', '.yaml', '.yml',
}

# ============================================================================
# EXCLUDED URL PATTERNS - الگوهای لینک نامعتبر
# ============================================================================

EXCLUDED_PATTERNS = [
    r'^https?://t\.me/',
    r'^https?://telegram\.org/',
    r'^https?://web\.telegram\.org/',
    r'^https?://core\.telegram\.org/',
    r'\.html$',
    r'\.php$',
    r'\?',
]

# ============================================================================
# UTILITY FUNCTIONS - توابع کمکی
# ============================================================================

def log(message: str, level: str = "INFO"):
    """لاگ کردن با فرمت یکسان"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}][{level}] {message}")


def safe_filename(name: str) -> str:
    """ایجاد نام فایل امن"""
    # حذف کاراکترهای غیرمجاز
    name = re.sub(r'[^\w\-_.]', '_', name)
    # محدودیت طول
    if len(name) > 150:
        base, ext = os.path.splitext(name)
        name = base[:140] + ext
    return name


def is_valid_media_url(url: str) -> bool:
    """بررسی معتبر بودن لینک رسانه"""
    if not url or not isinstance(url, str):
        return False
    
    url_lower = url.lower().strip()
    
    # بررسی الگوهای نامعتبر
    for pattern in EXCLUDED_PATTERNS:
        if re.match(pattern, url_lower):
            return False
    
    # بررسی پسوند معتبر
    parsed = urlparse(url_lower)
    path = unquote(parsed.path).lower()
    
    for ext in VALID_EXTENSIONS:
        if path.endswith(ext):
            return True
    
    # بررسی در query string
    if parsed.query:
        for ext in VALID_EXTENSIONS:
            if ext in parsed.query.lower():
                return True
    
    return False


def get_extension_from_url(url: str) -> Optional[str]:
    """استخراج پسوند فایل از URL"""
    url_lower = url.lower()
    parsed = urlparse(url_lower)
    path = unquote(parsed.path).lower()
    
    for ext in VALID_EXTENSIONS:
        if path.endswith(ext):
            return ext
    
    if parsed.query:
        for ext in VALID_EXTENSIONS:
            if ext in parsed.query.lower():
                return ext
    
    return None


def load_channels() -> List[str]:
    """بارگذاری لیست کانال‌ها از فایل list.txt"""
    if not os.path.exists(CONFIG["list_file"]):
        log(f"فایل {CONFIG['list_file']} یافت نشد", "ERROR")
        return []
    
    with open(CONFIG["list_file"], "r", encoding="utf-8") as f:
        channels = [
            line.strip().replace('@', '')
            for line in f
            if line.strip() and not line.startswith('#')
        ]
    
    log(f"{len(channels)} کانال بارگذاری شد: {', '.join(channels[:5])}...")
    return channels


def load_database() -> Dict:
    """بارگذاری دیتابیس posts.json"""
    db_path = Path(CONFIG["db_file"])
    
    if not db_path.exists():
        log("دیتابیس جدید ایجاد می‌شود")
        return {"channels": {}, "last_update": None}
    
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"خطا در خواندن دیتابیس: {e}", "ERROR")
        backup_path = db_path.with_suffix(".json.bak")
        shutil.copy(db_path, backup_path)
        log(f"بکاپ در {backup_path} ذخیره شد")
        return {"channels": {}, "last_update": None}


def save_database(db: Dict):
    """ذخیره دیتابیس به صورت اتمیک"""
    db["last_update"] = datetime.now().isoformat()
    tmp_path = Path(CONFIG["db_file"] + ".tmp")
    
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    
    tmp_path.replace(CONFIG["db_file"])


def download_file(url: str, filepath: Path) -> bool:
    """دانلود فایل با retry و بررسی حجم"""
    if filepath.exists() and filepath.stat().st_size > 0:
        return True
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    temp_path = filepath.with_suffix(filepath.suffix + ".part")
    max_bytes = CONFIG["max_file_size_mb"] * 1024 * 1024
    
    for attempt in range(CONFIG["max_retries"]):
        try:
            response = requests.get(
                url, 
                stream=True, 
                timeout=CONFIG["timeout"],
                headers={"User-Agent": CONFIG["user_agent"]}
            )
            
            if response.status_code != 200:
                time.sleep(CONFIG["backoff_factor"] ** attempt)
                continue
            
            total = 0
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(CONFIG["chunk_size"]):
                    if chunk:
                        total += len(chunk)
                        if total > max_bytes:
                            log(f"فایل بزرگتر از حد مجاز: {filepath.name}", "WARNING")
                            temp_path.unlink(missing_ok=True)
                            return False
                        f.write(chunk)
            
            temp_path.replace(filepath)
            log(f"دانلود شد: {filepath.name}")
            return True
            
        except Exception as e:
            log(f"تلاش {attempt + 1} ناموفق برای {url[:80]}: {e}", "WARNING")
            time.sleep(CONFIG["backoff_factor"] ** attempt)
    
    temp_path.unlink(missing_ok=True)
    return False


def extract_links_from_text(text: str) -> List[Dict]:
    """استخراج لینک‌های خارجی از متن"""
    if not text:
        return []
    
    url_pattern = r'https?://[^\s<>"\'{}|\\^`\[\]]+'
    links = []
    seen = set()
    
    for match in re.finditer(url_pattern, text):
        url = match.group()
        
        if url in seen:
            continue
        seen.add(url)
        
        # تشخیص نوع لینک
        link_type = "external"
        if "t.me" in url or "telegram" in url:
            link_type = "telegram"
        elif "youtube.com" in url or "youtu.be" in url:
            link_type = "youtube"
        elif "twitter.com" in url or "x.com" in url:
            link_type = "twitter"
        elif "instagram.com" in url:
            link_type = "instagram"
        elif "github.com" in url:
            link_type = "github"
        
        links.append({
            "url": url,
            "type": link_type,
            "text": url
        })
    
    return links


def fetch_channel_page(channel: str) -> Optional[str]:
    """دریافت صفحه HTML کانال با کش"""
    CONFIG["cache_dir"].mkdir(exist_ok=True)
    url = f"https://t.me/s/{channel}"
    
    # کش
    cache_key = hashlib.sha1(url.encode()).hexdigest()
    cache_path = CONFIG["cache_dir"] / f"{cache_key}.html"
    
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < 3600:  # یک ساعت
            return cache_path.read_text(encoding="utf-8")
    
    # دانلود
    for attempt in range(CONFIG["max_retries"]):
        try:
            response = requests.get(
                url,
                timeout=CONFIG["timeout"],
                headers={"User-Agent": CONFIG["user_agent"]}
            )
            
            if response.status_code == 200:
                cache_path.write_text(response.text, encoding="utf-8")
                return response.text
            else:
                log(f"HTTP {response.status_code} برای {channel}", "WARNING")
                
        except Exception as e:
            log(f"خطا در دریافت {channel}: {e}", "WARNING")
        
        time.sleep(CONFIG["backoff_factor"] ** attempt)
    
    return None


def parse_posts(html: str, channel: str, existing_ids: Set[int]) -> List[Dict]:
    """پارس کردن پست‌های HTML و استخراج اطلاعات"""
    if not html:
        return []
    
    soup = BeautifulSoup(html, "lxml")
    messages = soup.select(".tgme_widget_message")
    
    new_posts = []
    
    for msg in messages:
        # استخراج ID
        data_post = msg.get("data-post", "")
        if "/" not in data_post:
            continue
        
        post_id = data_post.split("/")[-1]
        if not post_id.isdigit():
            continue
        
        pid = int(post_id)
        if pid in existing_ids:
            break  # پست‌ها جدیدترین اول هستند
        
        # متن پست
        text_elem = msg.select_one(".tgme_widget_message_text")
        text = text_elem.get_text("\n", strip=True) if text_elem else ""
        
        # تاریخ
        time_elem = msg.select_one("time")
        date = time_elem.get("datetime", datetime.now().isoformat()) if time_elem else datetime.now().isoformat()
        
        # لینک‌های متن
        links = extract_links_from_text(text)
        
        # استخراج رسانه‌ها
        media = []
        media_index = 0
        
        # تصاویر
        for img in msg.select("img"):
            src = img.get("src") or img.get("data-src")
            if src and is_valid_media_url(src):
                ext = get_extension_from_url(src)
                if ext:
                    filename = safe_filename(f"{channel}_{pid}_{media_index}{ext}")
                    media.append({
                        "type": "image",
                        "file": filename,
                        "url": src
                    })
                    media_index += 1
        
        # ویدیوها و فایل‌ها
        for video in msg.select("video"):
            src = video.get("src")
            if src and is_valid_media_url(src):
                ext = get_extension_from_url(src) or ".mp4"
                filename = safe_filename(f"{channel}_{pid}_{media_index}{ext}")
                media.append({
                    "type": "video",
                    "file": filename,
                    "url": src
                })
                media_index += 1
        
        # لینک‌های دانلود
        for a in msg.select("a[href]"):
            href = a.get("href")
            if href and is_valid_media_url(href):
                ext = get_extension_from_url(href) or ".file"
                filename = safe_filename(f"{channel}_{pid}_{media_index}{ext}")
                media.append({
                    "type": "document",
                    "file": filename,
                    "url": href
                })
                media_index += 1
        
        new_posts.append({
            "id": pid,
            "text": text,
            "date": date,
            "media": media,
            "links": links
        })
    
    return new_posts


def download_post_media(post: Dict, channel: str) -> Dict:
    """دانلود رسانه‌های یک پست"""
    if not post.get("media"):
        return post
    
    downloaded_media = []
    
    for media in post["media"]:
        filepath = CONFIG["media_dir"] / media["file"]
        
        if download_file(media["url"], filepath):
            downloaded_media.append({
                "type": media["type"],
                "file": media["file"]
            })
        else:
            log(f"دانلود ناموفق: {media['url'][:80]}", "WARNING")
    
    post["media"] = downloaded_media
    return post


def process_channel(channel: str, db: Dict) -> Dict:
    """پردازش کامل یک کانال"""
    log(f"شروع پردازش کانال: @{channel}")
    
    # IDهای موجود
    existing_ids = {p["id"] for p in db.get("channels", {}).get(channel, [])}
    
    # دریافت صفحه
    html = fetch_channel_page(channel)
    if not html:
        log(f"دریافت صفحه برای @{channel} ناموفق", "ERROR")
        return db
    
    # پارس پست‌های جدید
    new_posts = parse_posts(html, channel, existing_ids)
    
    if not new_posts:
        log(f"پست جدیدی برای @{channel} یافت نشد")
        return db
    
    log(f"{len(new_posts)} پست جدید برای @{channel} یافت شد")
    
    # دانلود رسانه‌ها با موازی
    with ThreadPoolExecutor(max_workers=CONFIG["max_downloads_parallel"]) as executor:
        futures = {executor.submit(download_post_media, post, channel): post for post in new_posts}
        
        for future in as_completed(futures):
            try:
                completed_post = future.result()
                # به‌روزرسانی در لیست اصلی
                for i, p in enumerate(new_posts):
                    if p["id"] == completed_post["id"]:
                        new_posts[i] = completed_post
                        break
            except Exception as e:
                log(f"خطا در دانلود رسانه: {e}", "ERROR")
    
    # اضافه کردن به دیتابیس
    if channel not in db["channels"]:
        db["channels"][channel] = []
    
    db["channels"][channel].extend(new_posts)
    
    # مرتب‌سازی و محدودیت
    db["channels"][channel].sort(key=lambda x: x["id"], reverse=True)
    if len(db["channels"][channel]) > CONFIG["max_posts_per_channel"]:
        db["channels"][channel] = db["channels"][channel][:CONFIG["max_posts_per_channel"]]
    
    log(f"کانال @{channel} به‌روز شد. مجموع پست‌ها: {len(db['channels'][channel])}")
    return db


def clean_invalid_media_files():
    """پاکسازی فایل‌های نامعتبر از پوشه media"""
    media_dir = CONFIG["media_dir"]
    if not media_dir.exists():
        return
    
    removed = 0
    for file in media_dir.rglob("*"):
        if file.is_file():
            # حذف فایل‌های .part
            if file.suffix == ".part":
                file.unlink()
                removed += 1
                continue
            
            # حذف فایل‌های HTML اشتباه
            if file.suffix == ".html" or file.suffix == ".file":
                content = file.read_bytes()[:500]
                if b"<!DOCTYPE html" in content or b"<html" in content:
                    file.unlink()
                    removed += 1
                    log(f"حذف فایل نامعتبر: {file.name}", "WARNING")
    
    if removed > 0:
        log(f"{removed} فایل نامعتبر حذف شد")


def print_statistics(db: Dict):
    """نمایش آمار نهایی"""
    channels = db.get("channels", {})
    total_posts = sum(len(posts) for posts in channels.values())
    total_media = 0
    total_links = 0
    
    for posts in channels.values():
        for post in posts:
            total_media += len(post.get("media", []))
            total_links += len(post.get("links", []))
    
    log("=" * 50)
    log("آمار نهایی:")
    log(f"  کانال‌ها: {len(channels)}")
    log(f"  پست‌ها: {total_posts}")
    log(f"  رسانه‌ها: {total_media}")
    log(f"  لینک‌ها: {total_links}")
    
    if CONFIG["media_dir"].exists():
        media_count = sum(1 for _ in CONFIG["media_dir"].rglob("*") if _.is_file())
        log(f"  فایل‌های رسانه: {media_count}")
    
    log("=" * 50)


def main():
    """تابع اصلی"""
    start_time = time.time()
    
    log("=" * 50)
    log("Telegram Mirror - Enterprise Edition")
    log("=" * 50)
    
    # ایجاد پوشه‌ها
    CONFIG["media_dir"].mkdir(exist_ok=True)
    CONFIG["cache_dir"].mkdir(exist_ok=True)
    
    # پاکسازی فایل‌های نامعتبر
    clean_invalid_media_files()
    
    # بارگذاری کانال‌ها
    channels = load_channels()
    if not channels:
        log("هیچ کانالی برای پردازش وجود ندارد", "ERROR")
        return
    
    # بارگذاری دیتابیس
    db = load_database()
    
    # پردازش موازی کانال‌ها
    with ThreadPoolExecutor(max_workers=CONFIG["max_channels_parallel"]) as executor:
        futures = {executor.submit(process_channel, channel, db): channel for channel in channels}
        
        for future in as_completed(futures):
            channel = futures[future]
            try:
                db = future.result()
            except Exception as e:
                log(f"خطا در پردازش کانال {channel}: {e}", "ERROR")
    
    # ذخیره دیتابیس
    save_database(db)
    
    # نمایش آمار
    print_statistics(db)
    
    elapsed = time.time() - start_time
    log(f"زمان اجرا: {elapsed:.2f} ثانیه")
    log("پایان کار")


if __name__ == "__main__":
    main()
