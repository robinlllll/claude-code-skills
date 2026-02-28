# Playwright Skill Lessons

## 2026-02-13 | Cloudflare-protected sites block Playwright

ChatGPT (chatgpt.com) uses Cloudflare Turnstile that detects `navigator.webdriver=true`. Even with `channel="chrome"` (real Chrome binary), Playwright gets blocked → redirects to `/api/auth/error`.

**Workaround:** For CF-protected sites needing login (ChatGPT, etc.), use their API instead. ChatGPT has conversation API + manual data export (Settings → Data Controls → Export).

**Rule:** Before Playwright on any site, check for Cloudflare/bot detection. Signs: challenge pages, captchas, 403s. If detected → fall back to API or manual export.
