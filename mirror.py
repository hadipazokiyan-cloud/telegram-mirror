#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Channel Mirror - با retry mechanism کامل
"""

import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set
import requests
from bs4 import BeautifulSoup
import random

# ============================================
# تنظیمات retry
# ============================================

MAX_DOWNLOAD_RETRIES = 3        # تعداد تلاش برای دانلود هر فایل
MAX_FETCH_RETRIES = 5           # تعداد تلاش برای دریافت صفحه کانال
RETRY_DELAY_BASE = 5            # delay پایه (ثانیه)
RETRY_BACKOFF_FACTOR = 2        # ضریب افزایش delay (exponential backoff)
REQUEST_TIMEOUT = 45            # timeout هر درخواست

# ============================================
# توابع retry پیشرفته
# ============================================

def retry_with_backoff(func, max_retries=MAX_FETCH_RETRIES, *args, **kwargs):
    """
    اجرا با retry و exponential backoff
    مناسب برای درخواست‌های شبکه
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            print(f"  🔄 تلاش {attempt + 1}/{max_retries}...")
            result = func(*args, **kwargs)
            
            # اگر نتیجه None یا خالی بود، خطا محسوب می‌شود
            if result is None or (isinstance(result, list) and len(result) == 0):
                raise Exception("نتیجه خالی دریافت شد")
            
            return result
            
        except Exception as e:
            last_error = e
            wait_time = RETRY_DELAY_BASE * (RETRY_BACKOFF_FACTOR ** attempt)
            wait_time += random.uniform(0, 2)  # اضافه کردن randomness
            
            print(f"  ⚠️ تلاش {attempt + 1} ناموفق: {str(e)[:100]}")
            
            if attempt < max_retries - 1:
                print(f"  ⏳ صبر {wait_time:.1f} ثانیه و تلاش مجدد...")
                time.sleep(wait_time)
            else:
                print(f"  ❌ پس از {max_retries} تلاش، عملیات ناموفق بود")
    
    raise last_error


def download_file_with_retry(url: str, filepath: Path, max_retries=MAX_DOWNLOAD_RETRIES) -> bool:
    """
    دانلود فایل با retry و resume
    """
    temp_path = filepath.with_suffix(filepath.suffix + '.part')
    
    for attempt in range(max_retries):
        try:
            # بررسی فایل موجود
            if filepath.exists() and filepath.stat().st_size > 0:
                return True
            
            # تنظیم هدرها
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            
            # Resume از جایی که قطع شده
            existing_size = 0
            if temp_path.exists():
                existing_size = temp_path.stat().st_size
                headers['Range'] = f'bytes={existing_size}-'
                print(f"    ادامه دانلود از {existing_size/(1024*1024):.1f}MB")
            
            # درخواست با timeout
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
            
            if response.status_code in [200, 206]:
                mode = 'ab' if existing_size > 0 else 'wb'
                downloaded = existing_size
                
                with open(temp_path, mode) as f:
                    for chunk in response.iter_content(chunk_size=32768):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                
                # بررسی اینکه فایل خالی نباشد
                if downloaded > 0:
                    temp_path.rename(filepath)
                    return True
                    
            elif response.status_code == 429:  # Too Many Requests
                wait_time = 60 * (attempt + 1)
                print(f"  ⚠️ Rate limited, waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
                
        except requests.Timeout:
            print(f"  ⚠️ Timeout در تلاش {attempt + 1}")
            
        except requests.ConnectionError:
            print(f"  ⚠️ خطای اتصال در تلاش {attempt + 1}")
            
        except Exception as e:
            print(f"  ⚠️ خطا: {str(e)[:100]}")
        
        # انتظار با backoff قبل از تلاش مجدد
        if attempt < max_retries - 1:
            wait_time = RETRY_DELAY_BASE * (RETRY_BACKOFF_FACTOR ** attempt)
            print(f"  ⏳ صبر {wait_time} ثانیه و تلاش مجدد...")
            time.sleep(wait_time)
    
    # پاکسازی فایل موقت
    temp_path.unlink(missing_ok=True)
    return False


def fetch_url_with_retry(url: str, max_retries=MAX_FETCH_RETRIES) -> requests.Response:
    """
    دریافت URL با retry mechanism
    """
    for attempt in range(max_retries):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                wait_time = 60 * (attempt + 1)
                print(f"  ⚠️ Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"  ⚠️ HTTP {response.status_code}")
                
        except requests.Timeout:
            print(f"  ⚠️ Timeout in attempt {attempt + 1}")
        except Exception as e:
            print(f"  ⚠️ Error: {e}")
        
        if attempt < max_retries - 1:
            wait_time = RETRY_DELAY_BASE * (RETRY_BACKOFF_FACTOR ** attempt)
            time.sleep(wait_time)
    
    raise Exception(f"Failed to fetch {url} after {max_retries} attempts")


def fetch_channel_with_retry(channel: str, max_retries=MAX_FETCH_RETRIES) -> List[Dict]:
    """
    دریافت پست‌های کانال با retry
    """
    url = f"https://t.me/s/{channel}"
    
    for attempt in range(max_retries):
        try:
            print(f"  🌐 تلاش {attempt + 1} برای دریافت @{channel}")
            
            response = fetch_url_with_retry(url, max_retries=1)
            soup = BeautifulSoup(response.text, 'lxml')
            posts = soup.select('.tgme_widget_message')
            
            if posts:
                print(f"  ✅ {len(posts)} پست دریافت شد")
                return posts
            else:
                print(f"  ⚠️ پستی یافت نشد")
                
        except Exception as e:
            print(f"  ⚠️ خطا: {str(e)[:100]}")
            
        if attempt < max_retries - 1:
            wait_time = RETRY_DELAY_BASE * (RETRY_BACKOFF_FACTOR ** attempt)
            print(f"  ⏳ صبر {wait_time}s و تلاش مجدد...")
            time.sleep(wait_time)
    
    return []


def get_max_post_id_with_retry(channel: str) -> int:
    """
    دریافت آخرین ID پست کانال
    """
    posts = fetch_channel_with_retry(channel, max_retries=2)
    
    if not posts:
        return 0
    
    for post in posts[:5]:  # فقط 5 پست اول را بررسی کن
        data_post = post.get('data-post', '')
        if '/' in data_post:
            try:
                return int(data_post.split('/')[-1])
            except:
                continue
    
    return 0


# ============================================
# کلاس اصلی با retry داخلی
# ============================================

class TelegramMirror:
    def __init__(self):
        self.media_dir = Path("media")
        self.posts_file = Path("posts.json")
        self.ensure_directories()
    
    def ensure_directories(self):
        """ایجاد پوشه‌های مورد نیاز"""
        folders = ['images', 'videos', 'audios', 'documents', 'archives', 'applications', 'code', 'other']
        for folder in folders:
            (self.media_dir / folder).mkdir(parents=True, exist_ok=True)
    
    def load_db(self) -> Dict:
        """بارگذاری دیتابیس با retry"""
        try:
            if self.posts_file.exists():
                with open(self.posts_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ خطا در بارگذاری دیتابیس: {e}")
        
        return {"channels": {}, "last_update": None}
    
    def save_db(self, data: Dict):
        """ذخیره دیتابیس با retry"""
        for attempt in range(3):
            try:
                with open(self.posts_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    print(f"❌ خطا در ذخیره دیتابیس: {e}")
        return False
    
    def update_channel(self, channel: str) -> int:
        """بروزرسانی یک کانال"""
        print(f"\n🔄 بروزرسانی @{channel}")
        
        # دریافت پست‌های جدید با retry
        posts = fetch_channel_with_retry(channel)
        
        if not posts:
            print(f"  ❌ دریافت نشد")
            return 0
        
        print(f"  ✅ {len(posts)} پست دریافت شد")
        return len(posts)
    
    def run(self):
        """اجرای اصلی با retry برای کل فرآیند"""
        max_main_retries = 3
        
        for attempt in range(max_main_retries):
            try:
                print(f"\n🚀 شروع آپدیت - تلاش {attempt + 1}/{max_main_retries}")
                
                channels = self.load_channels()
                if not channels:
                    print("❌ کانالی یافت نشد")
                    return
                
                db = self.load_db()
                
                for channel in channels:
                    self.update_channel(channel)
                
                db["last_update"] = datetime.now().isoformat()
                self.save_db(db)
                
                print("✅ آپدیت کامل شد")
                return
                
            except Exception as e:
                print(f"⚠️ خطا در آپدیت: {e}")
                
                if attempt < max_main_retries - 1:
                    wait_time = 30 * (attempt + 1)
                    print(f"⏳ صبر {wait_time} ثانیه و restart...")
                    time.sleep(wait_time)
                else:
                    print("❌ آپدیت ناموفق بود")
    
    def load_channels(self) -> List[str]:
        """خواندن لیست کانال‌ها"""
        try:
            with open("list.txt", 'r') as f:
                channels = [line.strip().replace('@', '') 
                           for line in f if line.strip() and not line.startswith('#')]
            return channels
        except:
            return []


# ============================================
# اجرای اصلی
# ============================================

if __name__ == "__main__":
    mirror = TelegramMirror()
    mirror.run()
