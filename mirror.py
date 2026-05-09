#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import time
import random
import shutil
import hashlib
import logging
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote

import requests
from bs4 import BeautifulSoup
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# ============================================================================
# VALID EXTENSIONS - پسوندهای معتبر فایل
# ============================================================================

VALID_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico', '.tiff', '.heic',
    '.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.m4v', '.3gp', '.mpeg', '.mpg', '.wmv',
    '.mp3', '.ogg', '.wav', '.m4a', '.flac', '.aac', '.opus', '.wma', '.aiff',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md', '.rtf',
    '.odt', '.ods', '.odp', '.csv',
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2',
    '.apk', '.exe', '.msi', '.deb', '.rpm', '.appimage', '.dmg', '.bin', '.sh', '.bat',
    '.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.php', '.rb', '.go',
    '.rs', '.json', '.xml', '.yaml', '.yml', '.toml',
}

# ============================================================================
# EXCLUDED PATTERNS - الگوهای لینک نامعتبر
# ============================================================================

EXCLUDED_PATTERNS = [
    r'^https?://t\.me/',
    r'^https?://telegram\.org/',
    r'^https?://web\.telegram\.org/',
    r'^https?://core\.telegram\.org/',
    r'^https?://telegram\.dog/',
    r'\.html$', r'\.php$', r'\.asp$', r'\.aspx$',
    r'#', r'\?tgme', r'\?embed',
]

# ============================================================================
# ROTATING USER AGENTS - لیست User-Agent های مختلف
# ============================================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

# ============================================================================
# CONFIGURATION - تنظیمات کامل با رفتارهای انسانی
# ============================================================================

CONFIG = {
    # ------------------------------------------------------------------------
    # فایل‌ها و مسیرها
    # ------------------------------------------------------------------------
    "paths": {
        "list_file": "list.txt",
        "db_file": "posts.json",
        "media_dir": Path("media"),
        "cache_dir": Path("_cache_html"),
        "logs_dir": Path("logs"),
        "backup_dir": Path("backups"),
    },
    
    # ------------------------------------------------------------------------
    # محدودیت‌های زمانی - حذف پست‌های قدیمی
    # ------------------------------------------------------------------------
    "time": {
        "max_post_age_hours": 48,      # حذف پست‌های قدیمی‌تر از 48 ساعت
        "cleanup_interval_hours": 6,   # بررسی پاکسازی هر 6 ساعت
        "cache_ttl_hours": 2,           # اعتبار کش HTML (2 ساعت)
    },
    
    # ------------------------------------------------------------------------
    # محدودیت‌ها
    # ------------------------------------------------------------------------
    "limits": {
        "max_retries": 3,               # کاهش برای طبیعی‌تر بودن
        "timeout": 30,
        "max_file_size_mb": 200,
        "max_total_size_mb": 1000,
        "max_posts_per_channel": 200,
        "max_channels_parallel": 2,     # کاهش برای کمتر دیده شدن
        "max_downloads_parallel": 3,    # کاهش برای طبیعی‌تر بودن
        "max_links_per_post": 30,
        "max_media_per_post": 20,
    },
    
    # ------------------------------------------------------------------------
    # رفتارهای شبکه - شبیه‌سازی انسان
    # ------------------------------------------------------------------------
    "network": {
        "use_rotating_user_agents": True,
        "min_delay_between_requests": 2.0,   # حداقل تأخیر بین درخواست‌ها
        "max_delay_between_requests": 5.0,   # حداکثر تأخیر بین درخواست‌ها
        "min_delay_between_channels": 3.0,   # تأخیر بین کانال‌ها
        "max_delay_between_channels": 8.0,   # تأخیر بین کانال‌ها
        "jitter_factor": 0.3,                # نویز تصادفی در تأخیرها
        
        "retry": {
            "backoff_base": 2.0,
            "max_backoff": 30,
            "retry_status_codes": [429, 500, 502, 503, 504],
            "retry_exceptions": ["Timeout", "ConnectionError"],
        },
        
        "cache": {
            "enabled": True,
            "ttl_seconds": 7200,  # 2 ساعت
            "max_size_mb": 200,
        },
        
        "download": {
            "chunk_size": 128 * 1024,      # کاهش برای طبیعی‌تر بودن
            "min_chunk": 32 * 1024,
            "max_chunk": 512 * 1024,
            "adaptive_chunking": True,
            "resume": True,
        },
    },
    
    # ------------------------------------------------------------------------
    # رفتارهای پردازش
    # ------------------------------------------------------------------------
    "processing": {
        "max_text_length": 10000,
        "organize_media_by_type": True,
        "extract_links": True,
        "keep_original_filenames": True,
        "remove_duplicate_media": True,
        "skip_old_posts": True,            # اسکیپ پست‌های قدیمی
    },
    
    # ------------------------------------------------------------------------
    # پاکسازی خودکار - حذف پست‌های قدیمی
    # ------------------------------------------------------------------------
    "cleanup": {
        "auto_cleanup": True,
        "remove_old_posts": True,           # حذف پست‌های قدیمی از دیتابیس
        "remove_orphaned_files": True,      # حذف فایل‌های بدون مرجع
        "max_total_size_mb": 1000,
        "backup_before_cleanup": True,      # بکاپ قبل از پاکسازی
    },
    
    # ------------------------------------------------------------------------
    # بهینه‌سازی و امنیت
    # ------------------------------------------------------------------------
    "optimization": {
        "enable_cache": True,
        "adaptive_delay": True,
        "randomize_request_order": True,    # تصادفی کردن ترتیب درخواست‌ها
        "batch_size": 20,
    },
}

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    logs_dir = CONFIG["paths"]["logs_dir"]
    logs_dir.mkdir(exist_ok=True)
    
    log_file = logs_dir / f"mirror_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s][%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger("Mirror")

logger = setup_logging()

# ============================================================================
# SESSION WITH RETRY - نشست با قابلیت Retry
# ============================================================================

def create_session() -> requests.Session:
    """ایجاد نشست با retry strategy و تنظیمات ضد تشخیص"""
    session = requests.Session()
    
    # Retry strategy
    retry_strategy = Retry(
        total=CONFIG["limits"]["max_retries"],
        backoff_factor=CONFIG["network"]["retry"]["backoff_base"],
        status_forcelist=CONFIG["network"]["retry"]["retry_status_codes"],
        allowed_methods=["GET", "HEAD"],
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Headers شبیه انسان
    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })
    
    return session

SESSION = create_session()

# ============================================================================
# ANTI-DETECTION UTILITIES - توابع ضد تشخیص
# ============================================================================

def get_random_user_agent() -> str:
    """دریافت User-Agent تصادفی"""
    if CONFIG["network"]["use_rotating_user_agents"]:
        return random.choice(USER_AGENTS)
    return USER_AGENTS[0]


def get_human_like_delay() -> float:
    """محاسبه تأخیر شبیه انسان (با نویز تصادفی)"""
    min_delay = CONFIG["network"]["min_delay_between_requests"]
    max_delay = CONFIG["network"]["max_delay_between_requests"]
    jitter = CONFIG["network"]["jitter_factor"]
    
    base_delay = random.uniform(min_delay, max_delay)
    noise = random.uniform(-base_delay * jitter, base_delay * jitter)
    
    return max(0.5, base_delay + noise)


def get_channel_delay() -> float:
    """تأخیر بین پردازش کانال‌ها"""
    min_delay = CONFIG["network"]["min_delay_between_channels"]
    max_delay = CONFIG["network"]["max_delay_between_channels"]
    return random.uniform(min_delay, max_delay)


def randomize_request_order(items: List) -> List:
    """تصادفی کردن ترتیب درخواست‌ها"""
    if CONFIG["optimization"]["randomize_request_order"]:
        shuffled = items.copy()
        random.shuffle(shuffled)
        return shuffled
    return items


def is_post_within_age_limit(post_date_str: str) -> bool:
    """بررسی اینکه پست در 48 ساعت گذشته منتشر شده باشد"""
    if not CONFIG["processing"]["skip_old_posts"]:
        return True
    
    try:
        # پشتیبانی از فرمت‌های مختلف تاریخ
        if '+' in post_date_str:
            post_date_str = post_date_str.split('+')[0]
        if 'T' in post_date_str:
            post_date_str = post_date_str.replace('T', ' ')
        if len(post_date_str) > 19:
            post_date_str = post_date_str[:19]
        
        post_date = datetime.fromisoformat(post_date_str)
        age_hours = (datetime.now() - post_date).total_seconds() / 3600
        
        return age_hours <= CONFIG["time"]["max_post_age_hours"]
    except Exception as e:
        logger.debug(f"خطا در解析 تاریخ: {e}")
        return True  # در صورت خطا، نگه دار


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def safe_filename(name: str) -> str:
    """ایجاد نام فایل امن"""
    name = re.sub(r'[^\w\-_.]', '_', name)
    if len(name) > 200:
        base, ext = os.path.splitext(name)
        name = base[:180] + ext
    return name


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


def is_valid_media_url(url: str) -> bool:
    """بررسی معتبر بودن لینک رسانه"""
    if not url or not isinstance(url, str):
        return False
    
    url_lower = url.lower().strip()
    
    for pattern in EXCLUDED_PATTERNS:
        if re.match(pattern, url_lower):
            return False
    
    return get_extension_from_url(url) is not None


# ============================================================================
# FILE AND DATABASE OPERATIONS
# ============================================================================

def load_channels() -> List[str]:
    """بارگذاری لیست کانال‌ها"""
    list_file = CONFIG["paths"]["list_file"]
    
    if not os.path.exists(list_file):
        logger.error(f"فایل {list_file} یافت نشد")
        return []
    
    with open(list_file, "r", encoding="utf-8") as f:
        channels = [
            line.strip().replace('@', '')
            for line in f
            if line.strip() and not line.startswith('#')
        ]
    
    # تصادفی کردن ترتیب کانال‌ها
    channels = randomize_request_order(channels)
    
    logger.info(f"{len(channels)} کانال بارگذاری شد")
    return channels


def load_database() -> Dict:
    """بارگذاری دیتابیس"""
    db_file = CONFIG["paths"]["db_file"]
    
    if not os.path.exists(db_file):
        logger.info("ایجاد دیتابیس جدید")
        return {"channels": {}, "last_update": None, "last_cleanup": None, "statistics": {}}
    
    try:
        with open(db_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"خطا در خواندن دیتابیس: {e}")
        backup_file = CONFIG["paths"]["backup_dir"] / f"posts_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        CONFIG["paths"]["backup_dir"].mkdir(exist_ok=True)
        shutil.copy(db_file, backup_file)
        logger.info(f"بکاپ ایجاد شد: {backup_file}")
        return {"channels": {}, "last_update": None, "last_cleanup": None, "statistics": {}}


def save_database(db: Dict):
    """ذخیره دیتابیس به صورت اتمیک"""
    db["last_update"] = datetime.now().isoformat()
    
    # به‌روزرسانی آمار
    total_posts = 0
    total_media = 0
    total_links = 0
    
    for channel, posts in db.get("channels", {}).items():
        total_posts += len(posts)
        for post in posts:
            total_media += len(post.get("media", []))
            total_links += len(post.get("links", []))
    
    db["statistics"] = {
        "total_posts": total_posts,
        "total_media": total_media,
        "total_links": total_links,
        "last_calculation": datetime.now().isoformat()
    }
    
    db_file = CONFIG["paths"]["db_file"]
    tmp_file = f"{db_file}.tmp"
    
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    
    os.replace(tmp_file, db_file)


# ============================================================================
# NETWORK OPERATIONS WITH ANTI-DETECTION
# ============================================================================

def fetch_html(url: str, use_cache: bool = True) -> Optional[str]:
    """دریافت HTML با تأخیر تصادفی و User-Agent مختلف"""
    
    # تأخیر شبیه انسان
    time.sleep(get_human_like_delay())
    
    if use_cache and CONFIG["network"]["cache"]["enabled"]:
        cache_dir = CONFIG["paths"]["cache_dir"]
        cache_dir.mkdir(exist_ok=True)
        
        cache_key = hashlib.sha1(url.encode()).hexdigest()
        cache_path = cache_dir / f"{cache_key}.html"
        
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < CONFIG["network"]["cache"]["ttl_seconds"]:
                logger.debug(f"کش استفاده شد: {url[:60]}...")
                return cache_path.read_text(encoding="utf-8")
    
    # تغییر User-Agent برای هر درخواست
    current_ua = get_random_user_agent()
    SESSION.headers.update({"User-Agent": current_ua})
    
    for attempt in range(CONFIG["limits"]["max_retries"]):
        try:
            response = SESSION.get(url, timeout=CONFIG["limits"]["timeout"])
            
            if response.status_code == 200:
                html = response.text
                
                if use_cache and CONFIG["network"]["cache"]["enabled"]:
                    cache_path.write_text(html, encoding="utf-8")
                
                return html
            elif response.status_code == 429:
                logger.warning("Rate limit detected, waiting longer...")
                time.sleep(CONFIG["network"]["retry"]["max_backoff"])
            else:
                logger.warning(f"HTTP {response.status_code} برای {url[:60]}...")
                
        except Exception as e:
            logger.warning(f"تلاش {attempt + 1} ناموفق: {e}")
        
        delay = min(CONFIG["network"]["retry"]["max_backoff"], 
                    CONFIG["network"]["retry"]["backoff_base"] ** attempt)
        time.sleep(delay)
    
    logger.error(f"دریافت صفحه ناموفق: {url}")
    return None


def download_file(url: str, filepath: Path) -> bool:
    """دانلود فایل با تأخیر شبیه انسان"""
    
    if filepath.exists() and filepath.stat().st_size > 0:
        logger.debug(f"فایل موجود است: {filepath.name}")
        return True
    
    # تأخیر قبل از دانلود
    time.sleep(random.uniform(0.5, 1.5))
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    temp_path = filepath.with_suffix(filepath.suffix + ".part")
    
    max_bytes = CONFIG["limits"]["max_file_size_mb"] * 1024 * 1024
    
    for attempt in range(CONFIG["limits"]["max_retries"]):
        try:
            current_ua = get_random_user_agent()
            headers = {"User-Agent": current_ua}
            
            if CONFIG["network"]["download"]["resume"] and temp_path.exists():
                existing_size = temp_path.stat().st_size
                headers["Range"] = f"bytes={existing_size}-"
            else:
                existing_size = 0
            
            response = SESSION.get(url, headers=headers, stream=True, 
                                   timeout=CONFIG["limits"]["timeout"])
            
            if response.status_code not in (200, 206):
                delay = min(CONFIG["network"]["retry"]["max_backoff"], 
                           CONFIG["network"]["retry"]["backoff_base"] ** attempt)
                time.sleep(delay)
                continue
            
            chunk_size = CONFIG["network"]["download"]["chunk_size"]
            total = existing_size
            
            mode = "ab" if existing_size > 0 else "wb"
            with open(temp_path, mode) as f:
                for chunk in response.iter_content(chunk_size):
                    if chunk:
                        total += len(chunk)
                        if total > max_bytes:
                            logger.warning(f"فایل بزرگتر از حد مجاز: {filepath.name}")
                            temp_path.unlink(missing_ok=True)
                            return False
                        f.write(chunk)
            
            temp_path.replace(filepath)
            logger.info(f"دانلود شد: {filepath.name} ({total / 1024 / 1024:.2f} MB)")
            return True
            
        except Exception as e:
            logger.warning(f"تلاش {attempt + 1} برای {filepath.name}: {e}")
            delay = min(CONFIG["network"]["retry"]["max_backoff"], 
                       CONFIG["network"]["retry"]["backoff_base"] ** attempt)
            time.sleep(delay)
    
    temp_path.unlink(missing_ok=True)
    logger.error(f"دانلود ناموفق: {url[:100]}")
    return False


# ============================================================================
# LINK EXTRACTION
# ============================================================================

def extract_links_from_text(text: str) -> List[Dict]:
    """استخراج لینک‌های خارجی از متن"""
    if not text or not CONFIG["processing"]["extract_links"]:
        return []
    
    url_pattern = r'https?://[^\s<>"\'{}|\\^`\[\]]+'
    links = []
    seen = set()
    
    for match in re.finditer(url_pattern, text):
        url = match.group()
        
        if url in seen:
            continue
        seen.add(url)
        
        link_type = "external"
        if "t.me" in url:
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
            "display_text": url[:60] + "..." if len(url) > 60 else url
        })
        
        if len(links) >= CONFIG["limits"]["max_links_per_post"]:
            break
    
    return links


# ============================================================================
# MEDIA EXTRACTION
# ============================================================================

def extract_media_from_post(msg_element, channel: str, post_id: int) -> List[Dict]:
    """استخراج رسانه‌های یک پست"""
    media = []
    media_index = 0
    
    # تصاویر
    for img in msg_element.select("img"):
        src = img.get("src") or img.get("data-src")
        if src and is_valid_media_url(src):
            ext = get_extension_from_url(src) or ".jpg"
            filename = safe_filename(f"{channel}_{post_id}_{media_index}{ext}")
            media.append({"type": "image", "file": filename, "url": src})
            media_index += 1
    
    # ویدیوها
    for video in msg_element.select("video"):
        src = video.get("src")
        if src and is_valid_media_url(src):
            ext = get_extension_from_url(src) or ".mp4"
            filename = safe_filename(f"{channel}_{post_id}_{media_index}{ext}")
            media.append({"type": "video", "file": filename, "url": src})
            media_index += 1
    
    # فایل‌ها و اسناد
    for a in msg_element.select("a[href]"):
        href = a.get("href")
        if href and is_valid_media_url(href):
            ext = get_extension_from_url(href) or ".file"
            filename = safe_filename(f"{channel}_{post_id}_{media_index}{ext}")
            
            media_type = "document"
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                media_type = "image"
            elif ext in ['.mp4', '.webm', '.mov']:
                media_type = "video"
            elif ext in ['.mp3', '.ogg', '.wav']:
                media_type = "audio"
            
            media.append({"type": media_type, "file": filename, "url": href})
            media_index += 1
        
        if media_index >= CONFIG["limits"]["max_media_per_post"]:
            break
    
    return media


# ============================================================================
# POST PARSING WITH TIME FILTER
# ============================================================================

def parse_posts(html: str, channel: str, existing_ids: Set[int]) -> List[Dict]:
    """پارس کردن پست‌های HTML با فیلتر سنی"""
    if not html:
        return []
    
    soup = BeautifulSoup(html, "lxml")
    messages = soup.select(".tgme_widget_message")
    
    new_posts = []
    skipped_old = 0
    
    for msg in messages:
        data_post = msg.get("data-post", "")
        if "/" not in data_post:
            continue
        
        post_id_str = data_post.split("/")[-1]
        if not post_id_str.isdigit():
            continue
        
        post_id = int(post_id_str)
        
        if post_id in existing_ids:
            break
        
        # تاریخ پست
        time_elem = msg.select_one("time")
        date = time_elem.get("datetime", datetime.now().isoformat()) if time_elem else datetime.now().isoformat()
        
        # بررسی سن پست - حذف پست‌های قدیمی‌تر از 48 ساعت
        if not is_post_within_age_limit(date):
            skipped_old += 1
            logger.debug(f"پست {post_id} رد شد (قدیمی‌تر از {CONFIG['time']['max_post_age_hours']} ساعت)")
            continue
        
        # متن پست
        text_elem = msg.select_one(".tgme_widget_message_text")
        text = text_elem.get_text("\n", strip=True) if text_elem else ""
        
        if len(text) > CONFIG["processing"]["max_text_length"]:
            text = text[:CONFIG["processing"]["max_text_length"]] + "..."
        
        # لینک‌ها و رسانه‌ها
        links = extract_links_from_text(text)
        media = extract_media_from_post(msg, channel, post_id)
        
        new_posts.append({
            "id": post_id,
            "text": text,
            "date": date,
            "media": media,
            "links": links
        })
        
        logger.debug(f"پست {post_id} پذیرفته شد: {len(media)} رسانه, {len(links)} لینک")
    
    if skipped_old > 0:
        logger.info(f"{skipped_old} پست قدیمی از @{channel} رد شد")
    
    return new_posts


# ============================================================================
# CHANNEL PROCESSING
# ============================================================================

def download_post_media(post: Dict, channel: str) -> Dict:
    """دانلود رسانه‌های یک پست"""
    if not post.get("media"):
        return post
    
    downloaded_media = []
    media_dir = CONFIG["paths"]["media_dir"]
    
    for media in post["media"]:
        if CONFIG["processing"]["organize_media_by_type"]:
            type_dir = media_dir / media["type"]
            type_dir.mkdir(exist_ok=True)
            filepath = type_dir / media["file"]
        else:
            filepath = media_dir / media["file"]
        
        if download_file(media["url"], filepath):
            downloaded_media.append({
                "type": media["type"],
                "file": str(filepath.relative_to(media_dir)) if CONFIG["processing"]["organize_media_by_type"] else media["file"]
            })
        else:
            logger.warning(f"دانلود ناموفق: {media['url'][:80]}")
    
    post["media"] = downloaded_media
    return post


def process_channel(channel: str, db: Dict) -> Dict:
    """پردازش کامل یک کانال"""
    logger.info(f"🔄 شروع پردازش کانال: @{channel}")
    
    existing_ids = {p["id"] for p in db.get("channels", {}).get(channel, [])}
    
    url = f"https://t.me/s/{channel}"
    html = fetch_html(url)
    
    if not html:
        logger.error(f"❌ دریافت صفحه برای @{channel} ناموفق")
        return db
    
    new_posts = parse_posts(html, channel, existing_ids)
    
    if not new_posts:
        logger.info(f"📭 پست جدیدی برای @{channel} یافت نشد")
        return db
    
    logger.info(f"📝 {len(new_posts)} پست جدید برای @{channel} یافت شد")
    
    # دانلود رسانه‌ها
    with ThreadPoolExecutor(max_workers=CONFIG["limits"]["max_downloads_parallel"]) as executor:
        futures = {executor.submit(download_post_media, post, channel): post for post in new_posts}
        
        for future in as_completed(futures):
            try:
                completed_post = future.result()
                for i, p in enumerate(new_posts):
                    if p["id"] == completed_post["id"]:
                        new_posts[i] = completed_post
                        break
            except Exception as e:
                logger.error(f"خطا در دانلود رسانه: {e}")
    
    # اضافه کردن به دیتابیس
    if channel not in db["channels"]:
        db["channels"][channel] = []
    
    db["channels"][channel].extend(new_posts)
    
    # مرتب‌سازی و محدودیت
    db["channels"][channel].sort(key=lambda x: x["id"], reverse=True)
    if len(db["channels"][channel]) > CONFIG["limits"]["max_posts_per_channel"]:
        removed = len(db["channels"][channel]) - CONFIG["limits"]["max_posts_per_channel"]
        db["channels"][channel] = db["channels"][channel][:CONFIG["limits"]["max_posts_per_channel"]]
        logger.debug(f"{removed} پست قدیمی از @{channel} حذف شد")
    
    logger.info(f"✅ کانال @{channel} به‌روز شد. مجموع پست‌ها: {len(db['channels'][channel])}")
    
    # تأخیر بین کانال‌ها
    time.sleep(get_channel_delay())
    
    return db


# ============================================================================
# CLEANUP OLD POSTS - حذف پست‌های قدیمی
# ============================================================================

def cleanup_old_posts(db: Dict) -> Dict:
    """حذف پست‌های قدیمی‌تر از 48 ساعت از دیتابیس"""
    if not CONFIG["cleanup"]["remove_old_posts"]:
        return db
    
    logger.info("🧹 شروع پاکسازی پست‌های قدیمی...")
    
    removed_posts = 0
    removed_media = 0
    cutoff_time = datetime.now() - timedelta(hours=CONFIG["time"]["max_post_age_hours"])
    
    for channel, posts in db.get("channels", {}).items():
        original_count = len(posts)
        kept_posts = []
        
        for post in posts:
            try:
                post_date_str = post.get("date", "")
                if '+' in post_date_str:
                    post_date_str = post_date_str.split('+')[0]
                if 'T' in post_date_str:
                    post_date_str = post_date_str.replace('T', ' ')
                if len(post_date_str) > 19:
                    post_date_str = post_date_str[:19]
                
                post_date = datetime.fromisoformat(post_date_str)
                
                if post_date >= cutoff_time:
                    kept_posts.append(post)
                else:
                    removed_posts += 1
                    removed_media += len(post.get("media", []))
                    
                    # حذف فایل‌های رسانه
                    for media in post.get("media", []):
                        media_path = CONFIG["paths"]["media_dir"] / media["file"]
                        if media_path.exists():
                            media_path.unlink()
                            
            except Exception as e:
                logger.debug(f"خطا در تاریخ پست {post.get('id')}: {e}")
                kept_posts.append(post)  # در صورت خطا، نگه دار
        
        db["channels"][channel] = kept_posts
        
        if original_count != len(kept_posts):
            logger.info(f"کانال @{channel}: {original_count - len(kept_posts)} پست قدیمی حذف شد")
    
    # حذف کانال‌های خالی
    empty_channels = [ch for ch, posts in db["channels"].items() if not posts]
    for ch in empty_channels:
        del db["channels"][ch]
        logger.info(f"کانال خالی حذف شد: @{ch}")
    
    logger.info(f"✅ پاکسازی کامل: {removed_posts} پست و {removed_media} فایل حذف شد")
    
    return db


def cleanup_orphaned_files(db: Dict):
    """پاکسازی فایل‌های یتیم"""
    if not CONFIG["cleanup"]["remove_orphaned_files"]:
        return
    
    logger.info("🧹 پاکسازی فایل‌های یتیم...")
    
    media_dir = CONFIG["paths"]["media_dir"]
    if not media_dir.exists():
        return
    
    used_files = set()
    for channel, posts in db.get("channels", {}).items():
        for post in posts:
            for media in post.get("media", []):
                used_files.add(media["file"])
    
    removed = 0
    for file in media_dir.rglob("*"):
        if file.is_file() and file.suffix != ".part":
            rel_path = str(file.relative_to(media_dir))
            if rel_path not in used_files:
                file.unlink()
                removed += 1
                logger.debug(f"حذف فایل یتیم: {rel_path}")
    
    if removed > 0:
        logger.info(f"🗑️ {removed} فایل یتیم حذف شد")
    else:
        logger.info("✅ هیچ فایل یتیمی یافت نشد")


def backup_database(db: Dict):
    """بکاپ گرفتن از دیتابیس قبل از پاکسازی"""
    if not CONFIG["cleanup"]["backup_before_cleanup"]:
        return
    
    backup_dir = CONFIG["paths"]["backup_dir"]
    backup_dir.mkdir(exist_ok=True)
    
    backup_file = backup_dir / f"posts_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    
    logger.info(f"📦 بکاپ دیتابیس ایجاد شد: {backup_file}")
    
    # حذف بکاپ‌های قدیمی (فقط 5 بکاپ آخر نگهداری شود)
    backups = sorted(backup_dir.glob("posts_backup_*.json"))
    for old_backup in backups[:-5]:
        old_backup.unlink()


# ============================================================================
# STATISTICS
# ============================================================================

def print_statistics(db: Dict):
    """نمایش آمار نهایی"""
    stats = db.get("statistics", {})
    
    logger.info("=" * 60)
    logger.info("📊 آمار نهایی")
    logger.info("=" * 60)
    logger.info(f"📺 کانال‌ها: {len(db.get('channels', {}))}")
    logger.info(f"📝 کل پست‌ها: {stats.get('total_posts', 0)}")
    logger.info(f"🖼️ کل رسانه‌ها: {stats.get('total_media', 0)}")
    logger.info(f"🔗 کل لینک‌ها: {stats.get('total_links', 0)}")
    
    media_dir = CONFIG["paths"]["media_dir"]
    if media_dir.exists():
        media_count = sum(1 for _ in media_dir.rglob("*") if _.is_file())
        total_size = sum(f.stat().st_size for f in media_dir.rglob("*") if f.is_file())
        logger.info(f"💾 فایل‌های رسانه: {media_count} فایل ({total_size / (1024*1024):.2f} MB)")
    
    logger.info(f"⏰ حداکثر سن پست‌ها: {CONFIG['time']['max_post_age_hours']} ساعت")
    logger.info(f"🕐 آخرین بروزرسانی: {db.get('last_update', 'ندارد')}")
    logger.info("=" * 60)


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """تابع اصلی برنامه"""
    start_time = time.time()
    
    logger.info("=" * 60)
    logger.info("🪞 Telegram Mirror - Ultra-Stable Enterprise Edition")
    logger.info("=" * 60)
    logger.info(f"⏰ حداکثر سن پست‌ها: {CONFIG['time']['max_post_age_hours']} ساعت")
    logger.info(f"🕐 پاکسازی خودکار: هر {CONFIG['time']['cleanup_interval_hours']} ساعت")
    logger.info("=" * 60)
    
    # ایجاد پوشه‌ها
    for path in CONFIG["paths"].values():
        if isinstance(path, Path):
            path.mkdir(exist_ok=True)
    
    # بارگذاری کانال‌ها
    channels = load_channels()
    if not channels:
        logger.error("هیچ کانالی برای پردازش وجود ندارد")
        return
    
    # بارگذاری دیتابیس
    db = load_database()
    
    # بررسی نیاز به پاکسازی
    last_cleanup = db.get("last_cleanup")
    if last_cleanup:
        try:
            last_cleanup_date = datetime.fromisoformat(last_cleanup)
            hours_since_cleanup = (datetime.now() - last_cleanup_date).total_seconds() / 3600
            need_cleanup = hours_since_cleanup >= CONFIG["time"]["cleanup_interval_hours"]
        except:
            need_cleanup = True
    else:
        need_cleanup = True
    
    if need_cleanup:
        logger.info("🕐 شروع پاکسازی دوره‌ای...")
        backup_database(db)
        db = cleanup_old_posts(db)
        cleanup_orphaned_files(db)
        db["last_cleanup"] = datetime.now().isoformat()
        save_database(db)
    
    # پردازش موازی کانال‌ها
    with ThreadPoolExecutor(max_workers=CONFIG["limits"]["max_channels_parallel"]) as executor:
        futures = {executor.submit(process_channel, channel, db): channel for channel in channels}
        
        for future in as_completed(futures):
            channel = futures[future]
            try:
                db = future.result()
            except Exception as e:
                logger.error(f"خطا در پردازش کانال {channel}: {e}")
    
    # پاکسازی نهایی
    cleanup_orphaned_files(db)
    
    # ذخیره دیتابیس
    save_database(db)
    
    # نمایش آمار
    print_statistics(db)
    
    elapsed = time.time() - start_time
    logger.info(f"⏱️ زمان اجرا: {elapsed:.2f} ثانیه")
    logger.info("✅ عملیات با موفقیت کامل شد!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("⚠️ برنامه توسط کاربر متوقف شد")
    except Exception as e:
        logger.error(f"❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
