# آینه تلگرام (Telegram Mirror)

این پروژه پست‌های کانال‌های عمومی تلگرام را بدون نیاز به Bot Token، API ID، شماره تلفن یا سرور شخصی ذخیره می‌کند. اسکریپت `mirror.py` صفحه عمومی کانال‌ها را از مسیر `https://t.me/s/<channel>` می‌خواند، متن پست‌ها را در `posts.json` نگه می‌دارد، فایل‌های رسانه‌ای را در پوشه `media/` ذخیره می‌کند و با GitHub Actions می‌تواند به صورت خودکار اجرا شود.

> این ابزار فقط برای کانال‌های عمومی مناسب است. کانال خصوصی، گروه خصوصی، محتوای حذف‌شده، محتوای محدودشده یا چیزی که در صفحه عمومی `t.me/s` دیده نمی‌شود قابل آرشیو نیست.

## برای کاربران معمولی

اگر فقط می‌خواهید چند کانال عمومی را آرشیو کنید، کافی است این مراحل را انجام دهید:

1. فایل `list.txt` را باز کنید.
2. نام هر کانال را در یک خط بنویسید؛ مثلا:

```txt
durov
telegram
```

3. تغییرات را در GitHub ذخیره کنید.
4. از تب **Actions**، workflow به نام **Telegram Mirror Auto-Update** را اجرا کنید.
5. بعد از پایان موفق workflow، فایل `posts.json` و پوشه `media/` به‌روز می‌شوند.
6. اگر GitHub Pages فعال باشد، سایت آرشیو هم به‌روزرسانی می‌شود.

### نکته‌های ساده

- لازم نیست قبل از نام کانال `@` بگذارید؛ اگر بگذارید اسکریپت حذفش می‌کند.
- لینک‌هایی مثل `https://t.me/channelname` هم تا حد امکان به نام کانال تبدیل می‌شوند.
- خط‌هایی که با `#` شروع شوند نادیده گرفته می‌شوند.
- اگر کانالی عمومی نباشد یا صفحه `https://t.me/s/channelname` باز نشود، اسکریپت نمی‌تواند آن را ذخیره کند.
- فایل‌های خیلی بزرگ طبق تنظیمات workflow دانلود نمی‌شوند تا حجم مخزن GitHub بیش از حد زیاد نشود.

## امکانات اصلی

- خواندن پست‌های جدید از کانال‌های عمومی تلگرام
- ذخیره متن، تاریخ، لینک‌ها، رسانه‌ها و آدرس منبع هر پست
- دانلود تصویر، ویدیو، صدا و فایل‌های قابل تشخیص
- جلوگیری از دانلود دوباره فایل‌های موجود
- ذخیره امن `posts.json` به شکل اتمیک برای جلوگیری از خراب شدن فایل در GitHub Actions
- retry، timeout، backoff و cache برای پایداری بیشتر
- پاکسازی فایل‌های ناقص `*.part` و فایل‌های رسانه‌ای بدون ارجاع
- محدود کردن تعداد پست‌ها و حجم کل رسانه‌ها برای کنترل حجم repository
- اجرای خودکار با GitHub Actions و انتشار با GitHub Pages
- تست آفلاین با `python mirror.py --self-test` و `python -m unittest`

## ساختار فایل‌ها

| مسیر | کاربرد |
| --- | --- |
| `mirror.py` | اسکریپت اصلی آرشیو، دانلود رسانه، پاکسازی و ساخت آمار |
| `test_mirror.py` | تست‌های آفلاین برای parser و توابع اصلی |
| `list.txt` | فهرست کانال‌ها؛ هر خط یک کانال |
| `posts.json` | دیتابیس خروجی شامل کانال‌ها، پست‌ها، رسانه‌ها، لینک‌ها و آمار |
| `media/` | فایل‌های دانلودشده از پست‌ها |
| `viewer-advanced.html` | نمایشگر وب آرشیو |
| `website/` | فایل‌های مورد استفاده برای GitHub Pages |
| `.github/workflows/update.yml` | اجرای زمان‌بندی‌شده mirror و commit تغییرات |
| `.github/workflows/pages.yml` | انتشار خروجی روی GitHub Pages |
| `.github/workflows/keep-alive.yml` | بررسی سلامت دوره‌ای مخزن |
| `.github/workflows/test.yml` | اجرای تست‌ها در push و pull request |
| `requirements.txt` | وابستگی‌های Python |

## نصب و اجرای محلی

پیش‌نیازها:

- Python 3.11 یا بالاتر
- اینترنت برای اجرای واقعی mirror
- نصب وابستگی‌های داخل `requirements.txt`

نصب وابستگی‌ها:

```bash
python -m pip install -r requirements.txt
```

اجرای تست آفلاین:

```bash
python mirror.py --self-test
python -m unittest -v test_mirror.py
```

اجرای mirror:

```bash
python mirror.py
```

اجرای mirror بدون دانلود رسانه:

```bash
python mirror.py --no-media
```

اجرای mirror بدون پاکسازی فایل‌های بدون ارجاع:

```bash
python mirror.py --no-cleanup
```

## فرمت فایل `list.txt`

نمونه:

```txt
# کانال‌های خبری
IranintlTV

# کانال‌های فناوری
tavaanatech
@durov
https://t.me/telegram
```

قواعد:

- هر خط فقط یک کانال باشد.
- نام معتبر کانال باید شامل حروف انگلیسی، عدد یا `_` باشد.
- نام‌های تکراری فقط یک بار پردازش می‌شوند.
- کامنت با `#` شروع می‌شود.

## خروجی `posts.json`

نمونه کوتاه:

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
            "display_text": "https://example.com"
          }
        ],
        "has_media": true,
        "has_links": true,
        "source": "https://t.me/durov/503"
      }
    ]
  },
  "last_update": "2026-05-09T12:00:00+00:00",
  "last_cleanup": null,
  "statistics": {
    "total_posts": 1,
    "total_media": 1,
    "total_files": 1,
    "total_links": 1,
    "files_by_type": {
      "video": 1
    },
    "referenced_files": 1,
    "existing_media_files": 1,
    "total_size_mb": 2.4,
    "last_calculation": "2026-05-09T12:00:00+00:00"
  }
}
```

توضیح فیلدهای مهم:

- `channels`: کل پست‌ها به تفکیک کانال.
- `id`: شماره پست در تلگرام.
- `text`: متن پست.
- `date`: تاریخ منتشرشده در صفحه عمومی تلگرام.
- `media`: فایل‌های دانلودشده برای پست.
- `links`: لینک‌های استخراج‌شده از متن پست.
- `source`: لینک مستقیم پست در تلگرام.
- `statistics`: آمار کلی برای نمایش و عیب‌یابی.

## GitHub Actions

### اجرای خودکار آرشیو

workflow اصلی در `.github/workflows/update.yml` قرار دارد. این workflow معمولا کارهای زیر را انجام می‌دهد:

1. checkout کردن repository
2. نصب Python و وابستگی‌ها
3. اجرای `py_compile`، `self-test` و تست‌های `unittest`
4. اجرای `python mirror.py` با چند تلاش مجدد
5. نوشتن خلاصه اجرا در `logs/last_run.txt`
6. commit و push کردن تغییرات `posts.json`، `media/` و فایل خلاصه اجرا

برای اجرای دستی:

1. در GitHub وارد تب **Actions** شوید.
2. workflow با نام **Telegram Mirror Auto-Update** را انتخاب کنید.
3. روی **Run workflow** بزنید.
4. در صورت نیاز مقدار `post_limit` یا `keep_posts` را تغییر دهید.

### انتشار GitHub Pages

workflow مربوط به Pages در `.github/workflows/pages.yml` قرار دارد. این workflow فایل‌های لازم را داخل `website/` آماده می‌کند و با GitHub Pages منتشر می‌کند.

فعال‌سازی Pages:

1. وارد Settings مخزن شوید.
2. بخش Pages را باز کنید.
3. Source را روی **GitHub Actions** بگذارید.
4. workflow مربوط به Pages را اجرا کنید یا منتظر اجرای خودکار بمانید.

آدرس سایت معمولا این شکل است:

```txt
https://USERNAME.github.io/REPOSITORY/
```

## تنظیمات برای کاربران پیشرفته

رفتار `mirror.py` با Environment Variable قابل تغییر است. این متغیرها در GitHub Actions هم قابل استفاده هستند.

| متغیر | پیش‌فرض | توضیح |
| --- | --- | --- |
| `TELEGRAM_MIRROR_LIST` | `list.txt` | مسیر فایل فهرست کانال‌ها |
| `TELEGRAM_MIRROR_DB` | `posts.json` | مسیر دیتابیس JSON |
| `TELEGRAM_MIRROR_MEDIA_DIR` | `media` | مسیر ذخیره رسانه‌ها |
| `TELEGRAM_MIRROR_CACHE_DIR` | `_cache_html` | مسیر cache صفحه‌های HTML |
| `TELEGRAM_MIRROR_LOG_DIR` | `logs` | مسیر logها |
| `TELEGRAM_MIRROR_BACKUP_DIR` | `backups` | مسیر backupهای دیتابیس |
| `TELEGRAM_MIRROR_POST_LIMIT` | `30` | تعداد پیام‌هایی که از صفحه هر کانال بررسی می‌شود |
| `TELEGRAM_MIRROR_KEEP_POSTS` | `100` | حداکثر تعداد پست نگهداری‌شده برای هر کانال |
| `TELEGRAM_MIRROR_MAX_FILE_MB` | `100` | حداکثر حجم هر فایل دانلودی |
| `TELEGRAM_MIRROR_MAX_TOTAL_MB` | `500` | حداکثر حجم کل پوشه `media/` |
| `TELEGRAM_MIRROR_TIMEOUT` | `45` | timeout هر درخواست HTTP بر حسب ثانیه |
| `TELEGRAM_MIRROR_RETRIES` | `3` | تعداد تلاش مجدد برای درخواست‌ها |
| `TELEGRAM_MIRROR_DELAY_MIN` | `1.0` | حداقل تأخیر تصادفی قبل از درخواست |
| `TELEGRAM_MIRROR_DELAY_MAX` | `4.0` | حداکثر تأخیر تصادفی قبل از درخواست |
| `TELEGRAM_MIRROR_CHANNEL_WORKERS` | `1` | تعداد کانال‌هایی که همزمان پردازش می‌شوند |
| `TELEGRAM_MIRROR_DOWNLOAD_WORKERS` | `3` | تعداد دانلودهای همزمان برای رسانه‌ها |
| `TELEGRAM_MIRROR_CACHE_TTL` | `3600` | عمر cache HTML بر حسب ثانیه؛ مقدار `0` یعنی غیرفعال |
| `TELEGRAM_MIRROR_MAX_AGE_HOURS` | `0` | اگر بزرگ‌تر از صفر باشد، پست‌های قدیمی‌تر از این مقدار نادیده گرفته می‌شوند |
| `TELEGRAM_MIRROR_CLEANUP_OLD` | `false` | حذف پست‌های قدیمی از دیتابیس بر اساس `MAX_AGE_HOURS` |
| `TELEGRAM_MIRROR_CLEANUP_ORPHANS` | `true` | حذف فایل‌های رسانه‌ای بدون ارجاع در `posts.json` |
| `TELEGRAM_MIRROR_DOWNLOAD_MEDIA` | `true` | دانلود یا عدم دانلود رسانه‌ها |
| `TELEGRAM_MIRROR_RANDOMIZE_CHANNELS` | `false` | تصادفی کردن ترتیب پردازش کانال‌ها |
| `TELEGRAM_MIRROR_USER_AGENT` | Chrome | User-Agent ثابت برای درخواست‌ها |

نمونه اجرای پیشرفته:

```bash
TELEGRAM_MIRROR_POST_LIMIT=50 \
TELEGRAM_MIRROR_KEEP_POSTS=200 \
TELEGRAM_MIRROR_MAX_TOTAL_MB=800 \
python mirror.py
```

نمونه اجرای سبک فقط برای متن:

```bash
TELEGRAM_MIRROR_DOWNLOAD_MEDIA=false python mirror.py
```

## نکات پایداری در نسخه جدید `mirror.py`

- کامنت‌ها و نام‌گذاری‌های داخلی اسکریپت انگلیسی شده‌اند تا نگهداری کد ساده‌تر باشد.
- ذخیره `posts.json` به صورت atomic انجام می‌شود؛ یعنی اول فایل موقت ساخته می‌شود و سپس جایگزین فایل اصلی می‌شود.
- اگر `posts.json` خراب باشد، یک نسخه از فایل خراب در `backups/` ذخیره می‌شود و دیتابیس جدید ساخته می‌شود.
- پردازش کانال‌ها به صورت پیش‌فرض تک‌کارگره است تا احتمال rate limit در GitHub Actions کمتر شود.
- رسانه‌ها به صورت پیش‌فرض در همان پوشه `media/` ذخیره می‌شوند تا با workflow فعلی GitHub Pages سازگار باشند.
- فایل‌های ناقص با پسوند `.part` بعد از اجرا پاک می‌شوند.
- اگر حجم کل `media/` از مقدار تنظیم‌شده بیشتر شود، قدیمی‌ترین فایل‌ها حذف و ارجاعشان از `posts.json` پاک می‌شود.
- `--self-test` بدون اینترنت اجرا می‌شود و برای health check در CI مناسب است.

## محدودیت‌ها

- Telegram ممکن است ساختار HTML صفحه‌های عمومی را تغییر دهد؛ در این حالت parser باید اصلاح شود.
- همه رسانه‌ها در صفحه عمومی قابل دانلود نیستند.
- GitHub محدودیت حجم repository و Pages دارد؛ اگر کانال‌ها رسانه زیاد دارند، مقدارهای `KEEP_POSTS` و `MAX_TOTAL_MB` را کنترل کنید.
- فایل‌هایی که از حد `TELEGRAM_MIRROR_MAX_FILE_MB` بزرگ‌تر باشند دانلود نمی‌شوند.
- اجرای خیلی پرتکرار ممکن است باعث خطا یا محدودیت از سمت Telegram شود؛ مقدار delay و تعداد workerها را منطقی نگه دارید.

## عیب‌یابی

| مشکل | راه‌حل |
| --- | --- |
| `ModuleNotFoundError` | دستور `python -m pip install -r requirements.txt` را اجرا کنید. |
| تست‌ها در GitHub Actions fail می‌شوند | لاگ مرحله `Run offline validation` را بررسی کنید. |
| کانال هیچ پستی نمی‌دهد | آدرس `https://t.me/s/CHANNEL` را در مرورگر باز کنید و مطمئن شوید عمومی است. |
| رسانه‌ها در سایت دیده نمی‌شوند | بررسی کنید فایل در `media/` وجود داشته باشد و workflow Pages موفق اجرا شده باشد. |
| حجم repository زیاد شده | `TELEGRAM_MIRROR_KEEP_POSTS` یا `TELEGRAM_MIRROR_MAX_TOTAL_MB` را کمتر کنید. |
| `posts.json` خراب شده | پوشه `backups/` را بررسی کنید؛ نسخه خراب یا backupهای قبلی آنجا ذخیره می‌شوند. |
| workflow چیزی commit نمی‌کند | یعنی پست جدید یا فایل جدیدی پیدا نشده است؛ این حالت خطا نیست. |

## پیشنهادهای نگهداری

برای کاربران معمولی:

- تعداد کانال‌ها را کم و ضروری نگه دارید.
- اگر فقط متن برایتان مهم است، دانلود رسانه را خاموش کنید.
- هر چند وقت یک بار حجم `media/` را بررسی کنید.

برای کاربران پیشرفته:

- قبل از تغییر parser، تست‌های `test_mirror.py` را اجرا کنید.
- برای کاهش rate limit، `CHANNEL_WORKERS=1` و delay بالاتر استفاده کنید.
- اگر Pages فایل‌های بزرگ را نشان نمی‌دهد، محدودیت کپی فایل در workflow Pages را بررسی کنید.
- اگر می‌خواهید media بر اساس نوع فایل در زیرپوشه‌ها ذخیره شود، باید workflow Pages و viewer را هم با همان ساختار هماهنگ کنید.

## بررسی قبل از commit

```bash
python -m py_compile mirror.py test_mirror.py
python mirror.py --self-test
python -m unittest -v test_mirror.py
python -m json.tool posts.json >/dev/null
```

اگر اجرای واقعی می‌خواهید:

```bash
python mirror.py
```

سپس تغییرات را بررسی کنید:

```bash
git status
git diff --stat
```

## مسئولیت استفاده

این پروژه برای آرشیو محتوای عمومی طراحی شده است. هنگام ذخیره، انتشار یا بازنشر محتوا، قوانین GitHub، قوانین Telegram، حقوق تولیدکنندگان محتوا و قوانین کشور خود را رعایت کنید.
