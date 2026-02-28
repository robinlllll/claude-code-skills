---
name: playwright
description: "Use when tasks require browser automation: navigation, form filling, screenshots, data extraction from JS-rendered pages. NOT for specific scrapers (use /xueqiu or /wechat-hao). Triggers on: browser automation, web scraping (JS), screenshot webpage, fill form, login to site."
---

# Playwright Skill (Browser Automation)

## When to Use

- Navigate websites that require JavaScript rendering
- Fill forms, click buttons, automate multi-step web workflows
- Take screenshots of web pages
- Extract data from dynamic/JS-heavy pages
- Login to authenticated sites

**Boundary:** Xueqiu → `/xueqiu`. WeChat articles → `/wechat-hao`. This skill is the general-purpose browser tool.

## Decision Tree (CRITICAL — Follow This Order)

**Always try the lightest tool first:**

### Tier 1: HTTP Only (Try First)
```python
import requests
import pandas as pd

# Tables → pd.read_html
tables = pd.read_html("https://example.com/data")
df = tables[0]

# JSON API → requests
resp = requests.get("https://api.example.com/data")
data = resp.json()
```
**Use when:** Static HTML, public tables, REST APIs, no login required

### Tier 2: Article Extraction
```python
from trafilatura import fetch_url, extract

html = fetch_url("https://example.com/article")
text = extract(html)
```
**Use when:** Blog posts, articles, news content

### Tier 3: Full Browser (Last Resort)
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://example.com")
    # ... interact ...
    browser.close()
```
**Use when:** JS rendering required, login needed, interactive forms, dynamic content that Tier 1/2 can't reach

## Core Workflow (Tier 3)

1. `page.goto(url)` — navigate
2. `page.screenshot()` — capture current state
3. Interact (click, fill, select)
4. `page.screenshot()` — verify result
5. Extract data or confirm action
6. Close browser

## Key API (Python sync)

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)  # headless=False for debugging
    context = browser.new_context()              # Isolated session
    page = context.new_page()

    # Navigation
    page.goto("https://example.com", wait_until="networkidle")

    # Interaction
    page.click("button#submit")
    page.fill("input[name='email']", "user@example.com")
    page.select_option("select#country", "US")
    page.press("input[name='search']", "Enter")

    # Waiting
    page.wait_for_selector(".results", timeout=30000)
    page.wait_for_load_state("networkidle")

    # Screenshots
    page.screenshot(path="screenshot.png", full_page=True)

    # Data extraction
    content = page.content()                         # Full HTML
    text = page.inner_text(".article-body")           # Element text
    items = page.query_selector_all(".list-item")     # Multiple elements
    data = page.evaluate("() => window.__DATA__")     # JS variables

    # Tables → DataFrame
    import pandas as pd
    tables = pd.read_html(page.content())

    context.close()
    browser.close()
```

See `references/python-api.md` for complete API reference.
See `references/patterns.md` for common patterns and stability guidance.

## Session Management

- Use **separate contexts** for different tasks/logins
- Contexts are isolated (cookies, storage, cache)
- For persistent login: save/load storage state

```python
# Save login state
context.storage_state(path="auth.json")

# Reuse login state
context = browser.new_context(storage_state="auth.json")
```

## Dependencies

```
pip install playwright
playwright install chromium
```

**Important:** `playwright install chromium` downloads the browser binary (~150MB). Run once after pip install. Use Windows native Python, not MSYS2.

## References

- Python API reference: `references/python-api.md`
- Common patterns + stability: `references/patterns.md`
