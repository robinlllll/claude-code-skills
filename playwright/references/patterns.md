# Playwright Common Patterns

## Pattern 1: Form Fill → Submit → Extract Result

```python
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.goto("https://example.com/form")
    page.wait_for_load_state("networkidle")

    # Fill form
    page.fill("input[name='query']", "search term")
    page.select_option("select#category", "finance")
    page.click("button[type='submit']")

    # Wait for results
    page.wait_for_selector(".results", timeout=30000)

    # Extract
    results = page.query_selector_all(".result-item")
    data = [r.inner_text() for r in results]

    browser.close()
```

## Pattern 2: Table Data → DataFrame

```python
import pandas as pd

page.goto("https://example.com/data-table")
page.wait_for_selector("table")

# Method 1: pd.read_html (simplest)
tables = pd.read_html(page.content())
df = tables[0]

# Method 2: Manual extraction (more control)
rows = page.query_selector_all("table tbody tr")
data = []
for row in rows:
    cells = row.query_selector_all("td")
    data.append([cell.inner_text() for cell in cells])

headers = [h.inner_text() for h in page.query_selector_all("table thead th")]
df = pd.DataFrame(data, columns=headers)
```

## Pattern 3: Paginated Scraping

```python
all_data = []
page_num = 1

while True:
    # Extract current page
    items = page.query_selector_all(".item")
    for item in items:
        all_data.append(item.inner_text())

    # Check for next page
    next_btn = page.query_selector("a.next-page:not(.disabled)")
    if not next_btn:
        break

    next_btn.click()
    page.wait_for_load_state("networkidle")
    page_num += 1

    # Safety limit
    if page_num > 50:
        break
```

## Pattern 4: Login → Authenticated Session

```python
import os

AUTH_FILE = "auth_state.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # Check for saved session
    if os.path.exists(AUTH_FILE):
        context = browser.new_context(storage_state=AUTH_FILE)
    else:
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("https://example.com/login")
        page.fill("input[name='email']", "user@example.com")
        page.fill("input[name='password']", "password")
        page.click("button[type='submit']")
        page.wait_for_url("**/dashboard**")

        # Save session
        context.storage_state(path=AUTH_FILE)

    page = context.new_page()
    page.goto("https://example.com/protected-data")
    # ... extract data ...

    context.close()
    browser.close()
```

## Pattern 5: Screenshot → Analyze Loop

```python
# Navigate
page.goto(url)
page.wait_for_load_state("networkidle")

# Screenshot for user review
page.screenshot(path="step1_loaded.png", full_page=True)

# Interact
page.click(".expand-details")
page.wait_for_selector(".detail-panel")

# Screenshot again
page.screenshot(path="step2_expanded.png", full_page=True)
```

## Stability Patterns (IMPORTANT)

### Always Wait for Selectors
```python
# BAD — may fail on slow pages
page.click("button#submit")

# GOOD — explicit wait
page.wait_for_selector("button#submit", state="visible", timeout=30000)
page.click("button#submit")
```

### Retry Wrapper
```python
import time
import random

def retry_action(action, max_retries=3, base_delay=1.0):
    """Retry with exponential backoff + jitter."""
    for attempt in range(max_retries):
        try:
            return action()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            print(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s...")
            time.sleep(delay)

# Usage
retry_action(lambda: page.click("button#submit"))
```

### Random Delays Between Actions
```python
import random
import time

def human_delay(min_s=0.5, max_s=2.0):
    """Random delay to avoid detection and respect rate limits."""
    time.sleep(random.uniform(min_s, max_s))

page.fill("input[name='search']", "query")
human_delay()
page.click("button[type='submit']")
human_delay()
```

### Timeout Configuration
```python
# Global default timeout (30s)
page.set_default_timeout(30000)
page.set_default_navigation_timeout(60000)

# Per-action timeout
page.click("button", timeout=10000)
page.wait_for_selector(".results", timeout=45000)
```

### Headed Mode for Debugging
```python
# When things go wrong, switch to headed mode to see what's happening
browser = p.chromium.launch(
    headless=False,  # Show browser window
    slow_mo=500      # Slow down actions by 500ms
)
```

### Error Recovery
```python
from playwright.sync_api import TimeoutError as PlaywrightTimeout

try:
    page.goto(url, timeout=30000)
    page.wait_for_selector(".content", timeout=15000)
except PlaywrightTimeout:
    # Take debug screenshot
    page.screenshot(path="debug_timeout.png")
    # Try alternative approach
    page.reload()
    page.wait_for_load_state("domcontentloaded")
```

## Anti-Pattern Warnings

- **DON'T** use `page.wait_for_timeout()` as primary wait — use `wait_for_selector` instead
- **DON'T** hardcode element indices — use stable selectors (id, data-testid, role)
- **DON'T** skip `browser.close()` — always close to free resources
- **DON'T** use Playwright when `requests + pd.read_html` would work (see SKILL.md decision tree)
