#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mirror public Telegram channel posts into posts.json and media/.

The script intentionally uses only Telegram's public web pages
(https://t.me/s/<channel>). It does not need a bot token, API ID, or a
Telegram account, which makes it suitable for scheduled GitHub Actions runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import mimetypes
import os
import random
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# File extensions that are safe and useful to archive from public posts.
# Intentionally excludes web/code extensions such as .html, .js, .css, and
# .json because those are usually landing pages, not Telegram media files.
VALID_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico", ".tiff", ".heic",
    ".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".m4v", ".3gp", ".mpeg", ".mpg", ".wmv",
    ".mp3", ".ogg", ".wav", ".m4a", ".flac", ".aac", ".opus", ".wma", ".aiff",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".rtf",
    ".odt", ".ods", ".odp", ".csv",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2",
    ".apk", ".exe", ".msi", ".deb", ".rpm", ".appimage", ".dmg", ".bin",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico", ".tiff", ".heic"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".m4v", ".3gp", ".mpeg", ".mpg", ".wmv"}
AUDIO_EXTENSIONS = {".mp3", ".ogg", ".wav", ".m4a", ".flac", ".aac", ".opus", ".wma", ".aiff"}
DOCUMENT_EXTENSIONS = VALID_EXTENSIONS - IMAGE_EXTENSIONS - VIDEO_EXTENSIONS - AUDIO_EXTENSIONS

BLOCKED_MEDIA_HOSTS = {
    "t.me",
    "telegram.me",
    "telegram.org",
    "web.telegram.org",
    "core.telegram.org",
    "telegram.dog",
}

HTML_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}

EXCLUDED_PATTERNS = [
    r"^https?://t\.me/",
    r"^https?://telegram\.org/",
    r"^https?://web\.telegram\.org/",
    r"^https?://core\.telegram\.org/",
    r"^https?://telegram\.dog/",
    r"#",
    r"\?tgme",
    r"\?embed",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    list_file: Path
    db_file: Path
    media_dir: Path
    cache_dir: Path
    logs_dir: Path
    backup_dir: Path
    post_limit: int
    keep_posts: int
    max_file_mb: int
    max_total_mb: int
    timeout: int
    retries: int
    delay_min: float
    delay_max: float
    channels_parallel: int
    downloads_parallel: int
    cache_ttl_seconds: int
    max_post_age_hours: int
    cleanup_old_posts: bool
    cleanup_orphans: bool
    download_media: bool
    randomize_channels: bool
    user_agent: str


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(_env_str(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(_env_str(name, str(default))))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = _env_str(name, "1" if default else "0").lower()
    return value in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    return Settings(
        list_file=Path(_env_str("TELEGRAM_MIRROR_LIST", "list.txt")),
        db_file=Path(_env_str("TELEGRAM_MIRROR_DB", "posts.json")),
        media_dir=Path(_env_str("TELEGRAM_MIRROR_MEDIA_DIR", "media")),
        cache_dir=Path(_env_str("TELEGRAM_MIRROR_CACHE_DIR", "_cache_html")),
        logs_dir=Path(_env_str("TELEGRAM_MIRROR_LOG_DIR", "logs")),
        backup_dir=Path(_env_str("TELEGRAM_MIRROR_BACKUP_DIR", "backups")),
        post_limit=_env_int("TELEGRAM_MIRROR_POST_LIMIT", 30, 1),
        keep_posts=_env_int("TELEGRAM_MIRROR_KEEP_POSTS", 100, 1),
        max_file_mb=_env_int("TELEGRAM_MIRROR_MAX_FILE_MB", 100, 1),
        max_total_mb=_env_int("TELEGRAM_MIRROR_MAX_TOTAL_MB", 500, 1),
        timeout=_env_int("TELEGRAM_MIRROR_TIMEOUT", 45, 1),
        retries=_env_int("TELEGRAM_MIRROR_RETRIES", 3, 1),
        delay_min=_env_float("TELEGRAM_MIRROR_DELAY_MIN", 1.0, 0.0),
        delay_max=_env_float("TELEGRAM_MIRROR_DELAY_MAX", 4.0, 0.0),
        channels_parallel=_env_int("TELEGRAM_MIRROR_CHANNEL_WORKERS", 1, 1),
        downloads_parallel=_env_int("TELEGRAM_MIRROR_DOWNLOAD_WORKERS", 3, 1),
        cache_ttl_seconds=_env_int("TELEGRAM_MIRROR_CACHE_TTL", 3600, 0),
        max_post_age_hours=_env_int("TELEGRAM_MIRROR_MAX_AGE_HOURS", 0, 0),
        cleanup_old_posts=_env_bool("TELEGRAM_MIRROR_CLEANUP_OLD", False),
        cleanup_orphans=_env_bool("TELEGRAM_MIRROR_CLEANUP_ORPHANS", True),
        download_media=_env_bool("TELEGRAM_MIRROR_DOWNLOAD_MEDIA", True),
        randomize_channels=_env_bool("TELEGRAM_MIRROR_RANDOMIZE_CHANNELS", False),
        user_agent=_env_str("TELEGRAM_MIRROR_USER_AGENT", USER_AGENTS[0]),
    )


SETTINGS = load_settings()

# CONFIG keeps backwards-compatible names for tests and small local overrides.
CONFIG: Dict[str, Dict[str, Any]] = {
    "paths": {
        "list_file": str(SETTINGS.list_file),
        "db_file": str(SETTINGS.db_file),
        "media_dir": SETTINGS.media_dir,
        "cache_dir": SETTINGS.cache_dir,
        "logs_dir": SETTINGS.logs_dir,
        "backup_dir": SETTINGS.backup_dir,
    },
    "time": {
        "max_post_age_hours": SETTINGS.max_post_age_hours,
        "cleanup_interval_hours": 6,
        "cache_ttl_hours": SETTINGS.cache_ttl_seconds / 3600,
    },
    "limits": {
        "max_retries": SETTINGS.retries,
        "timeout": SETTINGS.timeout,
        "max_file_size_mb": SETTINGS.max_file_mb,
        "max_total_size_mb": SETTINGS.max_total_mb,
        "max_posts_per_channel": SETTINGS.keep_posts,
        "max_channels_parallel": SETTINGS.channels_parallel,
        "max_downloads_parallel": SETTINGS.downloads_parallel,
        "max_links_per_post": 30,
        "max_media_per_post": 20,
        "post_limit": SETTINGS.post_limit,
    },
    "network": {
        "use_rotating_user_agents": True,
        "min_delay_between_requests": SETTINGS.delay_min,
        "max_delay_between_requests": SETTINGS.delay_max,
        "retry": {"backoff_base": 2.0, "max_backoff": 60, "retry_status_codes": [429, 500, 502, 503, 504]},
        "cache": {"enabled": SETTINGS.cache_ttl_seconds > 0, "ttl_seconds": SETTINGS.cache_ttl_seconds},
        "download": {"chunk_size": 128 * 1024, "resume": True},
    },
    "processing": {
        "max_text_length": 10000,
        "organize_media_by_type": False,
        "extract_links": True,
        "skip_old_posts": SETTINGS.max_post_age_hours > 0,
        "download_media": SETTINGS.download_media,
    },
    "cleanup": {
        "remove_old_posts": SETTINGS.cleanup_old_posts,
        "remove_orphaned_files": SETTINGS.cleanup_orphans,
        "backup_before_cleanup": True,
    },
    "optimization": {"randomize_request_order": SETTINGS.randomize_channels},
}


logger = logging.getLogger("telegram_mirror")


def setup_logging() -> logging.Logger:
    """Configure console and file logging once."""
    if logger.handlers:
        return logger

    logs_dir = Path(CONFIG["paths"]["logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"mirror_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def create_session() -> requests.Session:
    """Create a requests session with retry support for GitHub Actions."""
    session = requests.Session()
    retry_strategy = Retry(
        total=CONFIG["limits"]["max_retries"],
        connect=CONFIG["limits"]["max_retries"],
        read=CONFIG["limits"]["max_retries"],
        backoff_factor=CONFIG["network"]["retry"]["backoff_base"],
        status_forcelist=CONFIG["network"]["retry"]["retry_status_codes"],
        allowed_methods={"GET", "HEAD"},
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": SETTINGS.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8,fa;q=0.7",
        "Connection": "keep-alive",
    })
    return session


SESSION = create_session()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_random_user_agent() -> str:
    if CONFIG["network"].get("use_rotating_user_agents", True):
        return random.choice(USER_AGENTS)
    return SETTINGS.user_agent


def get_human_like_delay() -> float:
    low = float(CONFIG["network"].get("min_delay_between_requests", 0.0))
    high = float(CONFIG["network"].get("max_delay_between_requests", low))
    if high < low:
        high = low
    return random.uniform(low, high) if high > 0 else 0.0


def get_channel_delay() -> float:
    return get_human_like_delay()


def randomize_request_order(items: List[Any]) -> List[Any]:
    """Return a shuffled copy only when randomization is enabled."""
    if CONFIG["optimization"].get("randomize_request_order"):
        shuffled = items.copy()
        random.shuffle(shuffled)
        return shuffled
    return items


def parse_datetime(value: str) -> Optional[datetime]:
    """Parse common Telegram datetime formats into timezone-aware UTC."""
    if not value:
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            parsed = datetime.strptime(cleaned[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            try:
                parsed = datetime.strptime(cleaned[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_post_within_age_limit(post_date_str: str) -> bool:
    """Return False when age filtering is enabled and the post is too old."""
    if not CONFIG["processing"].get("skip_old_posts"):
        return True
    max_age_hours = int(CONFIG["time"].get("max_post_age_hours", 0))
    if max_age_hours <= 0:
        return True
    post_date = parse_datetime(post_date_str)
    if post_date is None:
        return True
    return utc_now() - post_date <= timedelta(hours=max_age_hours)


def safe_filename(name: str) -> str:
    """Create a portable filename while preserving the extension."""
    name = unquote(str(name)).strip() or "file"
    name = re.sub(r"[^A-Za-z0-9_\-\.]", "_", name)
    name = re.sub(r"_+", "_", name).strip("._") or "file"
    if len(name) > 200:
        base, ext = os.path.splitext(name)
        name = base[: max(1, 200 - len(ext))] + ext
    return name


def get_extension_from_url(url: str) -> Optional[str]:
    """Find a known file extension in the URL path or query string."""
    if not url:
        return None
    parsed = urlparse(url.lower())
    path = unquote(parsed.path).lower()
    suffix = Path(path).suffix
    if suffix in VALID_EXTENSIONS:
        return suffix
    query = unquote(parsed.query).lower()
    for ext in sorted(VALID_EXTENSIONS, key=len, reverse=True):
        if re.search(re.escape(ext) + r"(?:$|[&=/?#])", query):
            return ext
    return None


def is_blocked_media_host(url: str) -> bool:
    """Reject Telegram/web page hosts before they can be downloaded as files."""
    try:
        host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:
        return True
    return any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_MEDIA_HOSTS)


def is_valid_media_url(url: str) -> bool:
    """Return True for downloadable media/document URLs only."""
    if not url or not isinstance(url, str):
        return False
    normalized = url.strip().lower()
    if not normalized.startswith(("http://", "https://", "//")):
        return False
    if normalized.startswith("//"):
        normalized = "https:" + normalized
    if is_blocked_media_host(normalized):
        return False
    if any(re.search(pattern, normalized) for pattern in EXCLUDED_PATTERNS):
        return False
    return get_extension_from_url(normalized) is not None


def classify_media(ext: str, default: str = "document") -> str:
    ext = ext.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    return default


def normalize_channel_name(value: str) -> Optional[str]:
    """Normalize @channel, t.me/channel, or raw channel names."""
    value = value.strip()
    if not value or value.startswith("#"):
        return None
    value = value.split("#", 1)[0].strip()
    value = re.sub(r"^https?://t\.me/s/", "", value, flags=re.I)
    value = re.sub(r"^https?://t\.me/", "", value, flags=re.I)
    value = value.strip("/@ ")
    if not re.fullmatch(r"[A-Za-z0-9_]{4,64}", value):
        logger.warning("Skipping invalid channel name: %s", value)
        return None
    return value


def load_channels() -> List[str]:
    """Load public channel names from list.txt."""
    list_file = Path(CONFIG["paths"]["list_file"])
    if not list_file.exists():
        logger.error("Channel list not found: %s", list_file)
        return []

    channels: List[str] = []
    seen = set()
    for line in list_file.read_text(encoding="utf-8").splitlines():
        channel = normalize_channel_name(line)
        if channel and channel.lower() not in seen:
            channels.append(channel)
            seen.add(channel.lower())

    channels = randomize_request_order(channels)
    logger.info("Loaded %d channel(s)", len(channels))
    return channels


def empty_database() -> Dict[str, Any]:
    return {"channels": {}, "last_update": None, "last_cleanup": None, "statistics": {}}


def load_database() -> Dict[str, Any]:
    """Read posts.json and recover safely if it is missing or invalid."""
    db_file = Path(CONFIG["paths"]["db_file"])
    if not db_file.exists():
        return empty_database()
    try:
        with db_file.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        backup_dir = Path(CONFIG["paths"]["backup_dir"])
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / f"posts_broken_{utc_now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy2(db_file, backup_file)
        logger.error("Could not read %s (%s). Broken copy saved to %s", db_file, exc, backup_file)
        return empty_database()

    if not isinstance(data, dict):
        return empty_database()
    data.setdefault("channels", {})
    data.setdefault("last_update", None)
    data.setdefault("last_cleanup", None)
    data.setdefault("statistics", {})
    if not isinstance(data["channels"], dict):
        data["channels"] = {}
    return data


def calculate_statistics(db: Dict[str, Any]) -> Dict[str, Any]:
    total_posts = 0
    total_media = 0
    total_links = 0
    files_by_type: Dict[str, int] = {}
    used_files: Set[str] = set()

    for posts in db.get("channels", {}).values():
        if not isinstance(posts, list):
            continue
        total_posts += len(posts)
        for post in posts:
            media_items = post.get("media", []) if isinstance(post, dict) else []
            link_items = post.get("links", []) if isinstance(post, dict) else []
            total_media += len(media_items)
            total_links += len(link_items)
            for media in media_items:
                media_type = media.get("type", "document")
                files_by_type[media_type] = files_by_type.get(media_type, 0) + 1
                if media.get("file"):
                    used_files.add(media["file"])

    media_dir = Path(CONFIG["paths"]["media_dir"])
    total_size = 0
    existing_files = 0
    if media_dir.exists():
        for file_path in media_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix != ".part":
                existing_files += 1
                total_size += file_path.stat().st_size

    return {
        "total_posts": total_posts,
        "total_media": total_media,
        "total_files": total_media,
        "total_links": total_links,
        "files_by_type": files_by_type,
        "referenced_files": len(used_files),
        "existing_media_files": existing_files,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "last_calculation": utc_now().isoformat(),
    }


def save_database(db: Dict[str, Any]) -> None:
    """Write posts.json atomically to avoid corrupt files on CI interruption."""
    db["last_update"] = utc_now().isoformat()
    db["statistics"] = calculate_statistics(db)

    db_file = Path(CONFIG["paths"]["db_file"])
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(db_file.parent or Path(".")), delete=False) as fh:
        json.dump(db, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
        tmp_name = fh.name
    os.replace(tmp_name, db_file)


def cache_path_for(url: str) -> Path:
    cache_dir = Path(CONFIG["paths"]["cache_dir"])
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{key}.html"


def fetch_html(url: str, use_cache: bool = True) -> Optional[str]:
    """Fetch a page with cache, retries, and bounded delays."""
    cache_enabled = bool(CONFIG["network"]["cache"].get("enabled"))
    ttl = int(CONFIG["network"]["cache"].get("ttl_seconds", 0))
    cache_path = cache_path_for(url)

    if use_cache and cache_enabled and cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age <= ttl:
            return cache_path.read_text(encoding="utf-8", errors="replace")

    delay = get_human_like_delay()
    if delay:
        time.sleep(delay)

    last_error: Optional[Exception] = None
    for attempt in range(1, int(CONFIG["limits"]["max_retries"]) + 1):
        try:
            SESSION.headers.update({"User-Agent": get_random_user_agent()})
            response = SESSION.get(url, timeout=int(CONFIG["limits"]["timeout"]))
            if response.status_code == 200:
                html = response.text
                if use_cache and cache_enabled:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(html, encoding="utf-8")
                return html
            logger.warning("HTTP %s for %s", response.status_code, url)
        except Exception as exc:
            last_error = exc
            logger.warning("Fetch attempt %d failed for %s: %s", attempt, url, exc)
        if attempt < int(CONFIG["limits"]["max_retries"]):
            time.sleep(min(60, 2 ** attempt))

    logger.error("Failed to fetch %s%s", url, f": {last_error}" if last_error else "")
    return None


def content_length_too_large(response: requests.Response) -> bool:
    length = response.headers.get("Content-Length")
    if not length or not length.isdigit():
        return False
    return int(length) > int(CONFIG["limits"]["max_file_size_mb"]) * 1024 * 1024


def normalized_content_type(response: requests.Response) -> str:
    """Return the response Content-Type without charset parameters."""
    return response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()


def content_type_matches_extension(content_type: str, ext: str) -> bool:
    """Validate that a downloaded response is not an HTML landing page."""
    if not content_type:
        return True
    if content_type in HTML_CONTENT_TYPES or content_type.startswith("text/html"):
        return False
    if ext in IMAGE_EXTENSIONS:
        return content_type.startswith("image/") or content_type == "application/octet-stream"
    if ext in VIDEO_EXTENSIONS:
        return content_type.startswith("video/") or content_type == "application/octet-stream"
    if ext in AUDIO_EXTENSIONS:
        return content_type.startswith("audio/") or content_type == "application/octet-stream"
    if ext in DOCUMENT_EXTENSIONS:
        return (
            content_type.startswith("application/")
            or content_type.startswith("text/plain")
            or content_type.startswith("text/csv")
            or content_type == "application/octet-stream"
        )
    return False


def looks_like_html_file(path: Path) -> bool:
    """Detect saved Telegram/web HTML pages even when they have media names."""
    try:
        sample = path.read_bytes()[:512].lower().lstrip()
    except OSError:
        return False
    return sample.startswith((b"<!doctype html", b"<html")) or b"<html" in sample[:128]


def download_file(url: str, filepath: Path) -> bool:
    """Download a file using a .part file and atomic rename."""
    ext = filepath.suffix.lower()
    if ext not in VALID_EXTENSIONS or not is_valid_media_url(url):
        logger.warning("Skipping invalid media URL: %s", url)
        return False
    if filepath.exists() and filepath.stat().st_size > 0:
        if looks_like_html_file(filepath):
            logger.warning("Removing HTML saved as media: %s", filepath)
            filepath.unlink(missing_ok=True)
            return False
        return True
    if not CONFIG["processing"].get("download_media", True):
        return False

    filepath.parent.mkdir(parents=True, exist_ok=True)
    temp_path = filepath.with_suffix(filepath.suffix + ".part")
    max_bytes = int(CONFIG["limits"]["max_file_size_mb"]) * 1024 * 1024

    for attempt in range(1, int(CONFIG["limits"]["max_retries"]) + 1):
        try:
            existing_size = temp_path.stat().st_size if temp_path.exists() else 0
            headers = {"User-Agent": get_random_user_agent()}
            if existing_size and CONFIG["network"]["download"].get("resume", True):
                headers["Range"] = f"bytes={existing_size}-"

            with SESSION.get(url, headers=headers, stream=True, timeout=int(CONFIG["limits"]["timeout"])) as response:
                if response.status_code not in {200, 206}:
                    logger.warning("Download HTTP %s for %s", response.status_code, url)
                    continue
                if is_blocked_media_host(response.url):
                    logger.warning("Skipping media URL redirected to Telegram page: %s -> %s", url, response.url)
                    temp_path.unlink(missing_ok=True)
                    return False
                final_ext = get_extension_from_url(response.url) or ext
                if final_ext not in VALID_EXTENSIONS:
                    logger.warning("Skipping download with invalid final extension: %s", response.url)
                    temp_path.unlink(missing_ok=True)
                    return False
                content_type = normalized_content_type(response)
                if not content_type_matches_extension(content_type, ext):
                    logger.warning("Skipping %s because Content-Type is %s", url, content_type or "missing")
                    temp_path.unlink(missing_ok=True)
                    return False
                if content_length_too_large(response):
                    logger.warning("Skipping oversized file by Content-Length: %s", url)
                    temp_path.unlink(missing_ok=True)
                    return False

                mode = "ab" if existing_size and response.status_code == 206 else "wb"
                total = existing_size if mode == "ab" else 0
                with temp_path.open(mode + "") as fh:
                    for chunk in response.iter_content(int(CONFIG["network"]["download"]["chunk_size"])):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > max_bytes:
                            logger.warning("Skipping oversized file: %s", url)
                            temp_path.unlink(missing_ok=True)
                            return False
                        fh.write(chunk)

            if temp_path.exists() and temp_path.stat().st_size > 0:
                if looks_like_html_file(temp_path):
                    logger.warning("Skipping HTML response saved as media: %s", url)
                    temp_path.unlink(missing_ok=True)
                    return False
                temp_path.replace(filepath)
                logger.info("Downloaded %s", filepath.name)
                return True
        except Exception as exc:
            logger.warning("Download attempt %d failed for %s: %s", attempt, url, exc)
        if attempt < int(CONFIG["limits"]["max_retries"]):
            time.sleep(min(60, 2 ** attempt))

    temp_path.unlink(missing_ok=True)
    return False


def extract_links_from_text(text: str) -> List[Dict[str, str]]:
    """Extract unique links from post text and classify common services."""
    if not text or not CONFIG["processing"].get("extract_links", True):
        return []
    url_pattern = r"https?://[^\s<>\"'{}|\\^`\[\]]+"
    links: List[Dict[str, str]] = []
    seen = set()
    for match in re.finditer(url_pattern, text):
        url = match.group().rstrip(".,؛،!?)]}")
        if url in seen:
            continue
        seen.add(url)
        host = urlparse(url).netloc.lower()
        link_type = "external"
        if host.endswith("t.me"):
            link_type = "telegram"
        elif "youtube.com" in host or "youtu.be" in host:
            link_type = "youtube"
        elif host in {"twitter.com", "x.com"} or host.endswith(".twitter.com") or host.endswith(".x.com"):
            link_type = "twitter"
        elif "instagram.com" in host:
            link_type = "instagram"
        elif "github.com" in host:
            link_type = "github"
        links.append({"url": url, "type": link_type, "display_text": url[:60] + "..." if len(url) > 60 else url})
        if len(links) >= int(CONFIG["limits"]["max_links_per_post"]):
            break
    return links


def media_filename(channel: str, post_id: int, index: int, url: str, ext: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return safe_filename(f"{channel}_{post_id}_{index}_{digest}{ext}")


def absolute_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return urljoin("https://t.me", url)


def extract_media_from_post(msg_element: Any, channel: str, post_id: int) -> List[Dict[str, str]]:
    """Extract media links from Telegram message HTML."""
    media: List[Dict[str, str]] = []
    seen_urls: Set[str] = set()

    def add_candidate(raw_url: Optional[str], forced_type: Optional[str] = None) -> None:
        if not raw_url or len(media) >= int(CONFIG["limits"]["max_media_per_post"]):
            return
        url = absolute_url(raw_url.strip())
        if url in seen_urls or not is_valid_media_url(url):
            return
        ext = get_extension_from_url(url) or mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "") or ".bin"
        media_type = forced_type or classify_media(ext)
        filename = media_filename(channel, post_id, len(media), url, ext)
        media.append({"type": media_type, "file": filename, "url": url})
        seen_urls.add(url)

    for img in msg_element.select("img"):
        add_candidate(img.get("src") or img.get("data-src"), "image")

    for video in msg_element.select("video"):
        add_candidate(video.get("src"), "video")
        for source in video.select("source[src]"):
            add_candidate(source.get("src"), "video")

    for audio in msg_element.select("audio"):
        add_candidate(audio.get("src"), "audio")
        for source in audio.select("source[src]"):
            add_candidate(source.get("src"), "audio")

    for link in msg_element.select("a[href]"):
        add_candidate(link.get("href"))

    # Telegram sometimes exposes image URLs in inline background styles.
    for styled in msg_element.select("[style]"):
        style = styled.get("style") or ""
        for match in re.finditer(r"url\(['\"]?([^)'\"]+)", style):
            add_candidate(match.group(1), "image")

    return media


def parse_posts(html: str, channel: str, existing_ids: Set[int]) -> List[Dict[str, Any]]:
    """Parse Telegram public channel HTML into post dictionaries."""
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    messages = soup.select(".tgme_widget_message")
    posts: List[Dict[str, Any]] = []

    for msg in messages[: int(CONFIG["limits"].get("post_limit", 30))]:
        data_post = msg.get("data-post", "")
        if "/" not in data_post:
            continue
        post_id_text = data_post.rsplit("/", 1)[-1]
        if not post_id_text.isdigit():
            continue
        post_id = int(post_id_text)
        if post_id in existing_ids:
            continue

        time_elem = msg.select_one("time[datetime]")
        date = time_elem.get("datetime") if time_elem else utc_now().isoformat()
        if not is_post_within_age_limit(date):
            continue

        text_elem = msg.select_one(".tgme_widget_message_text")
        text = text_elem.get_text("\n", strip=True) if text_elem else ""
        max_text = int(CONFIG["processing"].get("max_text_length", 10000))
        if len(text) > max_text:
            text = text[:max_text] + "..."

        media = extract_media_from_post(msg, channel, post_id)
        links = extract_links_from_text(text)
        posts.append({
            "id": post_id,
            "text": text,
            "date": date,
            "media": media,
            "links": links,
            "has_media": bool(media),
            "has_links": bool(links),
            "source": f"https://t.me/{channel}/{post_id}",
        })

    posts.sort(key=lambda item: item["id"], reverse=True)
    return posts


def download_post_media(post: Dict[str, Any], channel: str) -> Dict[str, Any]:
    """Download all media for one post and keep only successful files."""
    if not post.get("media") or not CONFIG["processing"].get("download_media", True):
        return post

    media_dir = Path(CONFIG["paths"]["media_dir"])
    downloaded: List[Dict[str, str]] = []
    for media in post.get("media", []):
        media_type = media.get("type", "document")
        if CONFIG["processing"].get("organize_media_by_type", False):
            filepath = media_dir / media_type / media["file"]
            stored_name = str(Path(media_type) / media["file"])
        else:
            filepath = media_dir / media["file"]
            stored_name = media["file"]
        if download_file(media.get("url", ""), filepath):
            downloaded.append({"type": media_type, "file": stored_name})
    post["media"] = downloaded
    post["has_media"] = bool(downloaded)
    return post


def merge_posts(existing: List[Dict[str, Any]], new_posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge posts by ID, newest first, respecting the keep limit."""
    merged: Dict[int, Dict[str, Any]] = {}
    for post in existing + new_posts:
        try:
            merged[int(post["id"])] = post
        except Exception:
            continue
    posts = sorted(merged.values(), key=lambda item: int(item.get("id", 0)), reverse=True)
    return posts[: int(CONFIG["limits"]["max_posts_per_channel"])]


def process_channel(channel: str, db: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch, parse, and download one channel. The caller merges results."""
    logger.info("Processing @%s", channel)
    existing = db.get("channels", {}).get(channel, [])
    existing_ids = {int(post.get("id")) for post in existing if isinstance(post, dict) and str(post.get("id", "")).isdigit()}
    html = fetch_html(f"https://t.me/s/{channel}")
    if not html:
        return []

    new_posts = parse_posts(html, channel, existing_ids)
    if not new_posts:
        logger.info("No new posts for @%s", channel)
        return []

    logger.info("Found %d new post(s) for @%s", len(new_posts), channel)
    if CONFIG["processing"].get("download_media", True):
        with ThreadPoolExecutor(max_workers=int(CONFIG["limits"]["max_downloads_parallel"])) as executor:
            futures = [executor.submit(download_post_media, post, channel) for post in new_posts]
            new_posts = [future.result() for future in as_completed(futures)]
    return new_posts


def media_files_referenced_by(db: Dict[str, Any]) -> Set[str]:
    used = set()
    for posts in db.get("channels", {}).values():
        for post in posts:
            for media in post.get("media", []):
                if media.get("file"):
                    used.add(str(media["file"]))
    return used


def cleanup_orphaned_files(db: Dict[str, Any]) -> None:
    """Remove files in media/ that are not referenced by posts.json."""
    if not CONFIG["cleanup"].get("remove_orphaned_files", True):
        return
    media_dir = Path(CONFIG["paths"]["media_dir"])
    if not media_dir.exists():
        return
    used = media_files_referenced_by(db)
    removed = 0
    for path in media_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".part":
            path.unlink(missing_ok=True)
            removed += 1
            continue
        rel = str(path.relative_to(media_dir))
        if rel not in used:
            path.unlink(missing_ok=True)
            removed += 1
    if removed:
        logger.info("Removed %d orphaned media file(s)", removed)


def cleanup_invalid_media_files(db: Dict[str, Any]) -> None:
    """Remove HTML or unsupported files that were previously saved as media."""
    media_dir = Path(CONFIG["paths"]["media_dir"])
    if not media_dir.exists():
        return

    removed_files: Set[str] = set()
    for path in media_dir.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        rel = str(path.relative_to(media_dir))
        if suffix == ".part" or suffix not in VALID_EXTENSIONS or looks_like_html_file(path):
            path.unlink(missing_ok=True)
            removed_files.add(rel)

    if not removed_files:
        return

    for posts in db.get("channels", {}).values():
        for post in posts:
            post["media"] = [
                media
                for media in post.get("media", [])
                if media.get("file") not in removed_files and Path(str(media.get("file", ""))).suffix.lower() in VALID_EXTENSIONS
            ]
            post["has_media"] = bool(post.get("media"))

    logger.info("Removed %d invalid media file(s)", len(removed_files))


def cleanup_old_posts(db: Dict[str, Any]) -> Dict[str, Any]:
    """Remove posts older than TELEGRAM_MIRROR_MAX_AGE_HOURS when enabled."""
    if not CONFIG["cleanup"].get("remove_old_posts", False):
        return db
    max_age = int(CONFIG["time"].get("max_post_age_hours", 0))
    if max_age <= 0:
        return db

    cutoff = utc_now() - timedelta(hours=max_age)
    for channel, posts in list(db.get("channels", {}).items()):
        kept = []
        for post in posts:
            parsed = parse_datetime(post.get("date", ""))
            if parsed is None or parsed >= cutoff:
                kept.append(post)
        if kept:
            db["channels"][channel] = kept
        else:
            del db["channels"][channel]
    return db


def backup_database(db: Dict[str, Any]) -> None:
    """Save a small JSON backup before destructive cleanup operations."""
    if not CONFIG["cleanup"].get("backup_before_cleanup", True):
        return
    backup_dir = Path(CONFIG["paths"]["backup_dir"])
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / f"posts_backup_{utc_now().strftime('%Y%m%d_%H%M%S')}.json"
    backup_file.write_text(json.dumps(db, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    backups = sorted(backup_dir.glob("posts_backup_*.json"))
    for old_backup in backups[:-5]:
        old_backup.unlink(missing_ok=True)


def enforce_media_size_limit(db: Dict[str, Any]) -> None:
    """Prune oldest referenced files if media/ exceeds the configured size."""
    media_dir = Path(CONFIG["paths"]["media_dir"])
    max_bytes = int(CONFIG["limits"].get("max_total_size_mb", 0)) * 1024 * 1024
    if max_bytes <= 0 or not media_dir.exists():
        return

    files = [path for path in media_dir.rglob("*") if path.is_file() and path.suffix != ".part"]
    total = sum(path.stat().st_size for path in files)
    if total <= max_bytes:
        return

    files.sort(key=lambda path: path.stat().st_mtime)
    removed_rel: Set[str] = set()
    for path in files:
        if total <= max_bytes:
            break
        size = path.stat().st_size
        rel = str(path.relative_to(media_dir))
        path.unlink(missing_ok=True)
        removed_rel.add(rel)
        total -= size

    if removed_rel:
        for posts in db.get("channels", {}).values():
            for post in posts:
                post["media"] = [media for media in post.get("media", []) if media.get("file") not in removed_rel]
                post["has_media"] = bool(post.get("media"))
        logger.info("Pruned %d media file(s) to respect size limit", len(removed_rel))


def print_statistics(db: Dict[str, Any]) -> None:
    stats = calculate_statistics(db)
    logger.info("Channels: %d", len(db.get("channels", {})))
    logger.info("Posts: %d", stats["total_posts"])
    logger.info("Media references: %d", stats["total_media"])
    logger.info("Links: %d", stats["total_links"])
    logger.info("Media size: %.2f MB", stats["total_size_mb"])


def ensure_directories() -> None:
    for key in ["media_dir", "cache_dir", "logs_dir", "backup_dir"]:
        Path(CONFIG["paths"][key]).mkdir(parents=True, exist_ok=True)


def self_test() -> int:
    """Run lightweight checks that do not require network access."""
    errors = []
    if not Path(CONFIG["paths"]["list_file"]).exists():
        errors.append("list.txt is missing")
    if Path(CONFIG["paths"]["db_file"]).exists():
        try:
            json.loads(Path(CONFIG["paths"]["db_file"]).read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"posts.json is invalid: {exc}")
    sample_html = '<div class="tgme_widget_message" data-post="demo/1"><time datetime="2026-01-01T00:00:00+00:00"></time><div class="tgme_widget_message_text">hello https://github.com</div></div>'
    with_skip = CONFIG["processing"].get("skip_old_posts")
    CONFIG["processing"]["skip_old_posts"] = False
    try:
        if not parse_posts(sample_html, "demo", set()):
            errors.append("HTML parser self-test failed")
    finally:
        CONFIG["processing"]["skip_old_posts"] = with_skip
    if errors:
        for error in errors:
            logger.error(error)
        return 1
    logger.info("Self-test passed")
    return 0


def run() -> int:
    setup_logging()
    ensure_directories()
    logger.info("Telegram Mirror started")

    channels = load_channels()
    if not channels:
        logger.error("No valid channels found in %s", CONFIG["paths"]["list_file"])
        return 1

    db = load_database()
    db.setdefault("channels", {})
    cleanup_invalid_media_files(db)

    if CONFIG["cleanup"].get("remove_old_posts", False):
        backup_database(db)
        db = cleanup_old_posts(db)

    with ThreadPoolExecutor(max_workers=int(CONFIG["limits"]["max_channels_parallel"])) as executor:
        futures = {executor.submit(process_channel, channel, db): channel for channel in channels}
        for future in as_completed(futures):
            channel = futures[future]
            try:
                new_posts = future.result()
            except Exception as exc:
                logger.error("Channel @%s failed: %s", channel, exc)
                continue
            if new_posts:
                existing = db["channels"].get(channel, [])
                db["channels"][channel] = merge_posts(existing, new_posts)

    cleanup_orphaned_files(db)
    cleanup_invalid_media_files(db)
    enforce_media_size_limit(db)
    save_database(db)
    print_statistics(db)
    logger.info("Telegram Mirror finished")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mirror public Telegram channels into posts.json and media/.")
    parser.add_argument("--self-test", action="store_true", help="run offline validation checks and exit")
    parser.add_argument("--no-media", action="store_true", help="parse posts without downloading media files")
    parser.add_argument("--no-cleanup", action="store_true", help="do not remove orphaned media files")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    setup_logging()

    if args.no_media:
        CONFIG["processing"]["download_media"] = False
    if args.no_cleanup:
        CONFIG["cleanup"]["remove_orphaned_files"] = False
    if args.self_test:
        return self_test()
    return run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        raise SystemExit(130)
