"""Opens the app in a real (headless) browser so Streamlit counts it as a visitor.
Also clicks the 'get this app back up' button if the app has gone to sleep."""
import os
from playwright.sync_api import sync_playwright

URL = os.environ["APP_URL"]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(URL, timeout=120_000)
    page.wait_for_timeout(8_000)
    btn = page.get_by_text("Yes, get this app back up!")
    if btn.count():
        btn.first.click()
        print("App was asleep: wake-up button clicked")
        page.wait_for_timeout(60_000)
    else:
        page.wait_for_timeout(30_000)   # stay connected for a while
    print("Visited:", page.title())
    browser.close()
