# Python Playwright API Reference

## Setup

```bash
pip install playwright
playwright install chromium
```

## Browser Launch

```python
from playwright.sync_api import sync_playwright

# Headless (default — no visible window)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    # ... work ...
    browser.close()

# Headed (visible — for debugging)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=500)
    page = browser.new_page()
    # ...
```

## Navigation

```python
page.goto("https://example.com")
page.goto("https://example.com", wait_until="networkidle")  # Wait for network
page.goto("https://example.com", wait_until="domcontentloaded")
page.goto("https://example.com", timeout=60000)  # 60s timeout

page.go_back()
page.go_forward()
page.reload()
```

## Selectors

```python
# CSS selectors (default)
page.click("button#submit")
page.click(".nav-item >> text=Login")
page.click("a[href='/dashboard']")

# Text selector
page.click("text=Sign In")
page.click("text=/Submit Order/i")  # Case-insensitive regex

# XPath
page.click("xpath=//button[@type='submit']")

# Role selector
page.click("role=button[name='Submit']")

# Nth element
page.click(".item >> nth=2")  # Third .item
```

## Interaction

```python
# Click
page.click("button#submit")
page.dblclick(".editable-cell")
page.click("button", button="right")  # Right-click

# Type / Fill
page.fill("input[name='email']", "user@example.com")  # Clear + type
page.type("input[name='search']", "query", delay=100)   # Key by key
page.press("input", "Enter")
page.press("body", "Control+a")

# Select
page.select_option("select#country", "US")
page.select_option("select", label="United States")

# Checkbox / Radio
page.check("input[type='checkbox']")
page.uncheck("input[type='checkbox']")

# File upload
page.set_input_files("input[type='file']", "path/to/file.pdf")

# Hover
page.hover(".dropdown-trigger")

# Drag and drop
page.drag_and_drop("#source", "#target")
```

## Waiting

```python
# Wait for selector
page.wait_for_selector(".results", timeout=30000)
page.wait_for_selector(".loading", state="hidden")
page.wait_for_selector(".modal", state="attached")

# Wait for load state
page.wait_for_load_state("networkidle")
page.wait_for_load_state("domcontentloaded")

# Wait for URL
page.wait_for_url("**/dashboard**")

# Wait for function
page.wait_for_function("() => document.querySelectorAll('.item').length > 5")

# Explicit wait
page.wait_for_timeout(2000)  # 2 seconds (avoid if possible)
```

## Data Extraction

```python
# Text content
text = page.inner_text(".article-body")
text = page.text_content("h1")

# HTML
html = page.inner_html(".content")
full_html = page.content()

# Attribute
href = page.get_attribute("a.primary", "href")

# Multiple elements
elements = page.query_selector_all(".list-item")
texts = [el.inner_text() for el in elements]

# Evaluate JavaScript
data = page.evaluate("() => window.__DATA__")
count = page.evaluate("document.querySelectorAll('.item').length")

# Tables → DataFrame
import pandas as pd
tables = pd.read_html(page.content())
df = tables[0]
```

## Screenshots

```python
# Full page
page.screenshot(path="full.png", full_page=True)

# Viewport only
page.screenshot(path="viewport.png")

# Element screenshot
page.locator(".chart").screenshot(path="chart.png")

# PDF (Chromium only, headless)
page.pdf(path="page.pdf", format="A4")
```

## Browser Context (Session Isolation)

```python
# New isolated context
context = browser.new_context(
    viewport={"width": 1920, "height": 1080},
    user_agent="Mozilla/5.0...",
    locale="en-US",
)
page = context.new_page()

# Save login state
context.storage_state(path="auth.json")

# Reuse login
context = browser.new_context(storage_state="auth.json")

# Close context
context.close()
```

## Network Interception

```python
# Block images (faster loading)
page.route("**/*.{png,jpg,jpeg,gif,svg}", lambda route: route.abort())

# Intercept API response
def handle_response(response):
    if "/api/data" in response.url:
        print(response.json())

page.on("response", handle_response)

# Mock API
page.route("**/api/data", lambda route: route.fulfill(
    status=200,
    content_type="application/json",
    body='{"items": []}'
))
```

## Error Handling

```python
from playwright.sync_api import TimeoutError as PlaywrightTimeout

try:
    page.click("button#submit", timeout=5000)
except PlaywrightTimeout:
    print("Button not found within 5s")
    page.screenshot(path="debug.png")
```
