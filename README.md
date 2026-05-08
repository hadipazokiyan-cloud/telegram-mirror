# Telegram Mirror

آرشیوکننده‌ی خودکار کانال‌های عمومی تلگرام بدون نیاز به Bot Token، API ID یا سرور شخصی. این پروژه از صفحه‌ی عمومی `https://t.me/s/<channel>` پست‌ها را می‌خواند، رسانه‌ها را داخل `media/` ذخیره می‌کند، داده‌ها را در `posts.json` نگه می‌دارد و با GitHub Actions به‌صورت زمان‌بندی‌شده به‌روزرسانی و روی GitHub Pages منتشر می‌شود.

> این پروژه فقط برای کانال‌های عمومی تلگرام کار می‌کند. کانال خصوصی، گروه خصوصی یا محتوایی که در صفحه‌ی عمومی تلگرام نمایش داده نمی‌شود قابل دریافت نیست.

## ویژگی‌ها

- دریافت پست‌های جدید کانال‌های تعریف‌شده در `list.txt`
- ذخیره‌ی پایدار اطلاعات در `posts.json`
- دانلود تصویر، ویدیو، صدا و فایل‌های قابل تشخیص در پوشه‌ی `media/`
- جلوگیری از دانلود دوباره‌ی فایل‌های موجود
- اجرای امن با retry، timeout و کنترل حجم فایل‌ها
- پاکسازی فایل‌های ناقص (`*.part`) و رسانه‌های بدون ارجاع
- نگهداری تعداد مشخصی پست از هر کانال برای کنترل حجم ریپو
- سازگار با GitHub Actions و GitHub Pages
- نمایشگر وب پیشرفته با فایل `viewer-advanced.html`
- بدون وابستگی به API رسمی تلگرام

## ساختار پروژه

| مسیر | توضیح |
| --- | --- |
| `mirror.py` | اسکریپت اصلی دریافت پست‌ها، دانلود رسانه و به‌روزرسانی دیتابیس |
| `list.txt` | فهرست کانال‌ها؛ هر خط یک نام کانال بدون `@` |
| `posts.json` | دیتابیس آرشیو شامل کانال‌ها، پست‌ها، لینک‌ها، رسانه‌ها و آمار |
| `media/` | فایل‌های دانلودشده؛ نام فایل‌ها یکتا و قابل commit هستند |
| `viewer-advanced.html` | نمایشگر اصلی آرشیو با رابط کاربری پیشرفته |
| `website/` | فایل‌های سایت GitHub Pages |
| `.github/workflows/update.yml` | اجرای خودکار mirror و commit تغییرات |
| `.github/workflows/pages.yml` | آماده‌سازی و انتشار GitHub Pages |
| `.github/workflows/keep-alive.yml` | health check دوره‌ای برای فعال نگه داشتن مخزن |
| `requirements.txt` | وابستگی‌های Python |

## پیش‌نیازها

- Python 3.11 یا بالاتر
- دسترسی اینترنت برای اجرای واقعی mirror
- بسته‌های Python داخل `requirements.txt`

نصب وابستگی‌ها:

```bash
python -m pip install -r requirements.txt
```

## تنظیم کانال‌ها

در فایل `list.txt`، هر کانال را در یک خط بنویسید:

```txt
whitedns
tavaanatech
```

نکته‌ها:

- از `@` استفاده نکنید؛ اگر وارد شود اسکریپت آن را حذف می‌کند.
- لینک‌هایی مثل `https://t.me/channel` نیز تا حد امکان پاک‌سازی می‌شوند.
- خط‌های خالی و خط‌هایی که با `#` شروع شوند نادیده گرفته می‌شوند.
- فقط نام‌های معتبر شامل حروف انگلیسی، عدد و `_` پذیرفته می‌شوند.

## اجرای دستی

از ریشه‌ی پروژه اجرا کنید:

```bash
python mirror.py
```

خروجی اجرا:

- `posts.json` به‌روزرسانی می‌شود.
- فایل‌های جدید در `media/` ذخیره می‌شوند.
- فایل‌های ناقص یا بدون ارجاع پاکسازی می‌شوند.
- آمار کلی داخل `posts.json.statistics` بازسازی می‌شود.

## تنظیمات قابل تغییر با Environment Variable

| متغیر | مقدار پیش‌فرض | توضیح |
| --- | --- | --- |
| `TELEGRAM_MIRROR_POST_LIMIT` | `20` | تعداد پست‌هایی که از صفحه‌ی عمومی هر کانال بررسی می‌شود |
| `TELEGRAM_MIRROR_KEEP_POSTS` | `100` | حداکثر پست نگهداری‌شده برای هر کانال |
| `TELEGRAM_MIRROR_MAX_FILE_MB` | `100` | حداکثر حجم هر فایل دانلودی |
| `TELEGRAM_MIRROR_MAX_TOTAL_MB` | `500` | حداکثر حجم کل پوشه‌ی `media/` |
| `TELEGRAM_MIRROR_TIMEOUT` | `45` | timeout هر درخواست HTTP بر حسب ثانیه |
| `TELEGRAM_MIRROR_RETRIES` | `3` | تعداد تلاش مجدد برای درخواست‌ها |
| `TELEGRAM_MIRROR_DELAY_MIN` | `1.5` | حداقل فاصله بین بررسی کانال‌ها |
| `TELEGRAM_MIRROR_DELAY_MAX` | `5` | حداکثر فاصله بین بررسی کانال‌ها |
| `TELEGRAM_MIRROR_USER_AGENT` | مرورگر Chrome | User-Agent درخواست‌ها |

نمونه:

```bash
TELEGRAM_MIRROR_POST_LIMIT=50 TELEGRAM_MIRROR_KEEP_POSTS=200 python mirror.py
```

## فرمت `posts.json`

نمونه‌ی خلاصه:

```json
{
  "channels": {
    "durov": [
      {
        "id": 503,
        "text": "متن پست",
        "date": "2026-05-08T16:00:22+00:00",
        "media": [
          {
            "type": "video",
            "file": "durov_503_0_898f3a65.mp4"
          }
        ],
        "links": [
          {
            "url": "https://example.com",
            "type": "external",
            "text": "https://example.com"
          }
        ],
        "has_media": true,
        "has_links": true
      }
    ]
  },
  "last_update": "2026-05-08T18:00:00+00:00",
  "statistics": {
    "total_posts": 1,
    "total_files": 1,
    "total_links": 1,
    "files_by_type": {"video": 1},
    "total_size_mb": 2.4
  }
}
```

رسانه‌ها با نام فایل داخل `media/` ذخیره می‌شوند و نمایشگرها مسیر را به شکل `media/<file>` می‌سازند.

## GitHub Actions

### Auto-Update

فایل `.github/workflows/update.yml` هر ۳۰ دقیقه اجرا می‌شود و این کارها را انجام می‌دهد:

1. نصب Python و وابستگی‌ها
2. اعتبارسنجی `mirror.py`، `posts.json` و `list.txt`
3. اجرای `mirror.py` با سه بار تلاش مجدد
4. ثبت خلاصه‌ی اجرا در `logs/last_run.txt`
5. commit و push کردن تغییرات `posts.json`، `media/` و لاگ اجرا

برای اجرای دستی، از تب Actions workflow با نام `Telegram Mirror Auto-Update` را انتخاب کنید و `Run workflow` بزنید. در اجرای دستی می‌توانید `post_limit` و `keep_posts` را هم تغییر دهید.

### GitHub Pages

فایل `.github/workflows/pages.yml` پس از موفقیت Auto-Update یا پس از push فایل‌های سایت اجرا می‌شود. این workflow:

- `posts.json` را به `website/posts.json` کپی می‌کند.
- `viewer-advanced.html` را به `website/viewer-advanced.html` کپی می‌کند.
- فایل‌های رسانه‌ای کوچک‌تر از ۲۵MB را به `website/media/` منتقل می‌کند.
- سایت را با GitHub Pages منتشر می‌کند.

برای فعال‌سازی Pages در GitHub:

1. به Settings مخزن بروید.
2. بخش Pages را باز کنید.
3. Source را روی `GitHub Actions` بگذارید.
4. workflow را دستی اجرا کنید یا منتظر اجرای زمان‌بندی‌شده بمانید.

### Keep-Alive

فایل `.github/workflows/keep-alive.yml` هر ۶ ساعت health check ساده انجام می‌دهد و فایل `.alive` را به‌روزرسانی می‌کند. هدف آن فعال نگه داشتن workflowها و مشخص بودن آخرین وضعیت سلامت مخزن است.

## نمایش آرشیو

### حالت GitHub Pages

پس از اجرای موفق Pages، آدرس سایت معمولاً شبیه این است:

```txt
https://USERNAME.github.io/REPOSITORY/
```

صفحه‌ی اصلی به `viewer-advanced.html` منتقل می‌شود.

### حالت محلی

به دلیل محدودیت مرورگر در خواندن فایل JSON با `file://`، بهتر است یک وب‌سرور ساده اجرا کنید:

```bash
python -m http.server 8000
```

سپس باز کنید:

```txt
http://localhost:8000/viewer-advanced.html
```

## نکات پایداری و محدودیت‌ها

- تلگرام ممکن است ساختار HTML صفحه‌های عمومی را تغییر دهد؛ در این حالت parser باید به‌روزرسانی شود.
- اگر کانالی در `t.me/s` قابل نمایش نباشد، اسکریپت نمی‌تواند آن را آرشیو کند.
- GitHub برای حجم repository و Pages محدودیت دارد؛ مقدارهای `KEEP_POSTS` و `MAX_TOTAL_MB` را متناسب نگه دارید.
- فایل‌های بزرگ‌تر از حد تنظیم‌شده دانلود نمی‌شوند.
- اگر رسانه‌ای بیشتر از ۲۵MB باشد، در Pages کپی نمی‌شود ولی در branch می‌تواند باقی بماند.
- اجرای خیلی پرتکرار ممکن است باعث rate limit شود؛ delay و retry برای کاهش این ریسک اضافه شده‌اند.

## آماده‌سازی برای commit

قبل از commit این دستورها را اجرا کنید:

```bash
python -m py_compile mirror.py
python -m json.tool posts.json > /tmp/posts.check.json
python mirror.py
```

سپس تغییرات مهم را بررسی کنید:

```bash
git status
git diff --stat
```

مواردی که عمداً قابل commit هستند:

- `mirror.py`
- `README.md`
- `requirements.txt`
- `.github/workflows/*.yml`
- `posts.json`
- فایل‌های لازم داخل `media/`
- فایل‌های viewer داخل `website/` و `viewer-advanced.html`

مواردی که نباید commit شوند و در `.gitignore` آمده‌اند:

- `__pycache__/`
- فایل‌های `*.pyc`
- فایل‌های ناقص `*.part`
- محیط مجازی Python مثل `.venv/`
- فایل‌های موقت و لاگ‌های غیرضروری

## عیب‌یابی

| مشکل | راه‌حل |
| --- | --- |
| `ModuleNotFoundError` | `python -m pip install -r requirements.txt` را اجرا کنید |
| `posts.json` خراب است | اسکریپت تلاش می‌کند نسخه‌ی خراب را با پسوند `broken` کنار بگذارد و دیتابیس جدید بسازد |
| Pages رسانه‌ها را نشان نمی‌دهد | مطمئن شوید فایل در `media/` وجود دارد و workflow Pages موفق بوده است |
| کانال آپدیت نمی‌شود | بررسی کنید کانال عمومی باشد و در `https://t.me/s/channel` پست‌ها دیده شوند |
| حجم repo زیاد شده | مقدار `TELEGRAM_MIRROR_KEEP_POSTS` یا `TELEGRAM_MIRROR_MAX_TOTAL_MB` را کاهش دهید |

## مجوز

این پروژه با مجوز MIT قابل استفاده، تغییر و توسعه است. هنگام آرشیو و بازنشر محتوا، قوانین GitHub، تلگرام و حقوق محتوای کانال‌ها را رعایت کنید.
