"""Archive visible posts from a public Telegram channel web page.

This script intentionally uses Telegram's public web view only:
https://t.me/s/<channel>

It does not use Telegram API, TDLib, Telethon, Selenium, Playwright, or any
browser automation. It is designed for unattended runs in GitHub Actions.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup


ARCHIVE_PATH = Path("data") / "posts.json"
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_RETRIES = 3
RETRY_DELAY_SECONDS = 3
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True)
class FetchResult:
    """Result of a network request that may fail gracefully."""

    html: str | None
    status_code: int | None = None
    error: str | None = None


def get_channel_username(channel_url: str) -> str:
    """Validate a Telegram channel URL and return its public username."""
    parsed = urlparse(channel_url.strip())

    if parsed.scheme != "https" or parsed.netloc.lower() != "t.me":
        raise ValueError("TG_CHANNEL_URL must start with https://t.me/")

    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        raise ValueError("TG_CHANNEL_URL must contain a channel username")

    if path_parts[0] == "s":
        if len(path_parts) < 2 or not path_parts[1]:
            raise ValueError("TG_CHANNEL_URL must contain a channel username")
        username = path_parts[1]
    else:
        username = path_parts[0]

    if username.startswith("+") or username.lower() in {"joinchat", "c"}:
        raise ValueError("TG_CHANNEL_URL must point to a public channel username")

    return username


def build_public_view_url(username: str) -> str:
    """Build Telegram's public web-view URL for a channel username."""
    return f"https://t.me/s/{quote(username, safe='')}"


def fetch_html(url: str) -> FetchResult:
    """Download HTML with a short retry loop and browser-like headers."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    last_error: str | None = None
    last_status: int | None = None

    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            last_status = response.status_code

            if response.status_code in {403, 429}:
                return FetchResult(
                    html=None,
                    status_code=response.status_code,
                    error=f"Telegram returned {response.status_code}; request may be blocked or rate limited",
                )

            if response.status_code >= 400:
                last_error = f"HTTP error {response.status_code}"
            elif not response.text.strip():
                last_error = "Telegram returned an empty HTML body"
            else:
                return FetchResult(html=response.text, status_code=response.status_code)

        except requests.Timeout:
            last_error = f"Request timed out after {REQUEST_TIMEOUT_SECONDS} seconds"
        except requests.RequestException as exc:
            last_error = f"Network error: {exc}"

        if attempt < REQUEST_RETRIES:
            print(f"Fetch attempt {attempt} failed: {last_error}. Retrying...")
            time.sleep(RETRY_DELAY_SECONDS)

    return FetchResult(html=None, status_code=last_status, error=last_error or "Unknown fetch error")


def clean_text(value: str) -> str:
    """Normalize extracted text while preserving readable line breaks."""
    lines = [line.strip() for line in value.splitlines()]
    non_empty_lines = [line for line in lines if line]
    return "\n".join(non_empty_lines)


def extract_text(message: Any) -> str:
    """Extract plain post text from a Telegram message node."""
    text_node = message.select_one(".tgme_widget_message_text")
    if text_node is None:
        return ""

    # Telegram uses <br> tags for user-visible line breaks inside posts.
    return clean_text(text_node.get_text(separator="\n", strip=True))


def extract_date(message: Any) -> str | None:
    """Extract the ISO datetime string from a Telegram message node."""
    time_node = message.select_one("time")
    if time_node is None:
        return None

    datetime_value = time_node.get("datetime")
    if not datetime_value:
        return None

    return str(datetime_value).strip() or None


def extract_views(message: Any) -> str | None:
    """Extract the visible Telegram view count, if present."""
    views_node = message.select_one(".tgme_widget_message_views")
    if views_node is None:
        return None

    views_text = views_node.get_text(strip=True)
    return views_text or None


def extract_link(message: Any, post_id: str) -> str:
    """Extract the permalink, falling back to data-post when needed."""
    link_node = message.select_one("a.tgme_widget_message_date")
    href = link_node.get("href") if link_node is not None else None
    if href:
        return str(href)

    return f"https://t.me/{post_id}"


def parse_posts(html: str) -> list[dict[str, str | None]]:
    """Parse visible Telegram posts from public web-view HTML."""
    if "<html" not in html.lower() and "tgme_widget_message" not in html:
        print("HTML does not look like a Telegram channel page; no posts parsed.")
        return []

    soup = BeautifulSoup(html, "html.parser")
    messages = soup.select("div.tgme_widget_message")
    if not messages:
        print("No visible Telegram posts found in the current HTML.")
        return []

    posts: list[dict[str, str | None]] = []

    for message in messages:
        # The stable public post identifier is stored in data-post, e.g. "FVpnProxy/338".
        post_id = message.get("data-post")
        if not post_id:
            continue

        post_id_text = str(post_id).strip()
        if not post_id_text:
            continue

        posts.append(
            {
                "id": post_id_text,
                "date": extract_date(message),
                "views": extract_views(message),
                "text": extract_text(message),
                "link": extract_link(message, post_id_text),
            }
        )

    return posts


def load_archive(path: Path) -> list[dict[str, str | None]]:
    """Load existing archived posts from disk, returning an empty list on issues."""
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as archive_file:
            data = json.load(archive_file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read existing archive at {path}: {exc}. Starting with an empty archive.")
        return []

    if not isinstance(data, list):
        print(f"Existing archive at {path} is not a JSON list. Starting with an empty archive.")
        return []

    valid_posts: list[dict[str, str | None]] = []
    for item in data:
        if isinstance(item, dict) and item.get("id"):
            valid_posts.append(
                {
                    "id": str(item.get("id", "")),
                    "date": item.get("date") if item.get("date") else None,
                    "views": item.get("views") if item.get("views") else None,
                    "text": str(item.get("text", "")),
                    "link": str(item.get("link", "")),
                }
            )

    return valid_posts


def sort_key(post: dict[str, str | None]) -> tuple[int, str, str]:
    """Sort posts chronologically while keeping undated posts stable at the end."""
    date = post.get("date")
    if date:
        return (0, date, post.get("id") or "")
    return (1, "", post.get("id") or "")


def merge_posts(
    existing_posts: list[dict[str, str | None]],
    new_posts: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    """Merge posts by id, preserving older archived records when duplicates exist."""
    posts_by_id: dict[str, dict[str, str | None]] = {}

    for post in existing_posts:
        post_id = post.get("id")
        if post_id:
            posts_by_id[post_id] = post

    for post in new_posts:
        post_id = post.get("id")
        if post_id and post_id not in posts_by_id:
            posts_by_id[post_id] = post

    return sorted(posts_by_id.values(), key=sort_key)


def save_archive(path: Path, posts: list[dict[str, str | None]]) -> None:
    """Save archived posts as formatted UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as archive_file:
        json.dump(posts, archive_file, ensure_ascii=False, indent=2)
        archive_file.write("\n")


def run() -> int:
    """Run one mirror update and return the process exit code."""
    channel_url = os.getenv("TG_CHANNEL_URL", "").strip()

    try:
        username = get_channel_username(channel_url)
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 1

    public_view_url = build_public_view_url(username)
    print(f"Fetching Telegram public web view: {public_view_url}")

    fetch_result = fetch_html(public_view_url)
    if fetch_result.html is None:
        print(f"Fetch failed: {fetch_result.error}")
        print("Keeping existing archive unchanged.")
        return 0

    parsed_posts = parse_posts(fetch_result.html)
    existing_posts = load_archive(ARCHIVE_PATH)
    merged_posts = merge_posts(existing_posts, parsed_posts)

    if merged_posts == existing_posts:
        print(f"No new posts found. Archive still contains {len(existing_posts)} posts.")
        return 0

    save_archive(ARCHIVE_PATH, merged_posts)
    print(
        f"Archive updated: {len(parsed_posts)} visible posts parsed, "
        f"{len(merged_posts) - len(existing_posts)} new posts added, "
        f"{len(merged_posts)} total posts saved."
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
