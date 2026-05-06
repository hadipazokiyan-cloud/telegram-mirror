# Telegram Public Channel Mirror

A small Python tool that archives the latest posts visible on a public Telegram channel web page into a JSON file stored in a GitHub repository.

This project uses Telegram's public web view (`https://t.me/s/<username>`) only. It does not use the Telegram API, TDLib, Telethon, Selenium, Playwright, or browser automation.

## How It Works

1. Reads `TG_CHANNEL_URL` from the environment.
2. Validates and extracts the public channel username.
3. Converts the channel URL to Telegram's public web view.
4. Downloads the HTML with `requests`.
5. Parses visible posts with `BeautifulSoup`.
6. Extracts each post's id, date, views, text, and permalink.
7. Merges posts into `data/posts.json`.
8. Avoids duplicate post ids across runs.
9. Saves UTF-8 JSON with stable formatting.

## Project Structure

```text
telegram-mirror/
├── mirror.py
├── requirements.txt
├── README.md
├── data/
│   └── posts.json
└── .github/
    └── workflows/
        └── update.yml
```

`data/posts.json` is created automatically after the first successful archive update.

## Deploy With GitHub Actions

1. Fork or create a repository from this project.
2. Go to your repository settings.
3. Open **Secrets and variables** → **Actions** → **Variables**.
4. Add a repository variable:
   - Name: `TG_CHANNEL_URL`
   - Value: `https://t.me/FVpnProxy`
5. Commit and push this project to GitHub.
6. Enable GitHub Actions if prompted.
7. Run the workflow manually once, or wait for the scheduled run.

The workflow runs every 30 minutes and commits `data/posts.json` only when it changes.

## Run Locally

```bash
cd telegram-mirror
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
TG_CHANNEL_URL="https://t.me/FVpnProxy" python mirror.py
```

## Change Channel

Update the `TG_CHANNEL_URL` repository variable in GitHub Actions.

Examples:

```text
https://t.me/FVpnProxy
https://t.me/s/FVpnProxy
```

Only public channel usernames are supported. Private invite links and internal Telegram URLs are not supported.

## Forking

To archive your own channel:

1. Fork the repository.
2. Set `TG_CHANNEL_URL` to your target public channel.
3. Confirm that GitHub Actions has permission to write repository contents.
4. Run the update workflow.

If commits fail, check **Settings** → **Actions** → **General** → **Workflow permissions** and allow read/write permissions.

## Example JSON Output

```json
[
  {
    "id": "FVpnProxy/338",
    "date": "2026-05-05T09:12:00+00:00",
    "views": "14.2K",
    "text": "post content",
    "link": "https://t.me/FVpnProxy/338"
  }
]
```

## Limitations And Disclaimer

This tool archives only posts visible in Telegram's public web view. Telegram may limit, block, redesign, or partially change this HTML at any time. Missing text, dates, views, or posts are handled gracefully, but the archive cannot access private content, full channel history, deleted posts, or content that Telegram does not expose in the public web page.

Use this project responsibly and respect Telegram's terms, channel owners, and applicable laws.

## Future Extensions

The code is intentionally modular so future features can be added without rewriting the core flow:

- Media downloading
- Multi-channel support
- Markdown export
- Static site generation
