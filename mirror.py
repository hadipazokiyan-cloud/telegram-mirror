import os
import json
from pyrogram import Client

# گرفتن مقادیر از GitHub Secrets یا متغیرهای محیطی
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
CHANNEL = os.getenv("TG_CHANNEL")

OUTPUT = "posts.json"


def load_existing_posts():
    """خواندن posts.json اگر وجود داشته باشد"""
    if not os.path.exists(OUTPUT):
        return []
    try:
        with open(OUTPUT, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_posts(posts):
    """ذخیره پست‌ها در فایل JSON"""
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def extract_media(msg):
    """استخراج نوع مدیا بدون دانلود"""
    if msg.photo:
        return {"type": "photo", "file_id": msg.photo.file_id}
    if msg.video:
        return {"type": "video", "file_id": msg.video.file_id}
    if msg.document:
        return {"type": "document", "file_id": msg.document.file_id}
    return None


def main():
    app = Client("mirror-session", api_id=API_ID, api_hash=API_HASH)
    app.start()

    existing = load_existing_posts()
    existing_ids = {p["id"] for p in existing}

    new_posts = []

    # تعداد پست‌ها قابل تغییر است (limit=100 یعنی ۱۰۰ پست آخر)
    for msg in app.get_chat_history(CHANNEL, limit=50):
        if msg.id in existing_ids:
            continue

        post = {
            "id": msg.id,
            "date": str(msg.date),
            "text": msg.text or "",
            "media": extract_media(msg)
        }

        new_posts.append(post)

    if new_posts:
        # مرتب‌سازی پست‌ها بر اساس شناسه
        existing.extend(sorted(new_posts, key=lambda x: x["id"]))
        save_posts(existing)

    app.stop()


if __name__ == "__main__":
    main()
