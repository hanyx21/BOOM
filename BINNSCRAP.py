# login_once_then_reuse.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv
import os
import time

# Load .env file
load_dotenv()

PROFILE_DIR = "binance_profile"
HOME = "https://accounts.binance.com/en/login"

EMAIL = os.getenv("BINANCE_EMAIL")
PASSWORD = os.getenv("BINANCE_PASSWORD")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=["--start-maximized"]
    )
    page = ctx.new_page()
    page.goto(HOME, wait_until="domcontentloaded")

    try:
        # Step 1: email/phone input
        page.fill('input[name="email"]', EMAIL)
        page.click('button:has-text("Next")')

        # Step 2: password input
        page.wait_for_selector('input[name="password"]', timeout=10000)
        page.fill('input[name="password"]', PASSWORD)
        page.click('button[type="submit"]')

        print("⚠️ If Binance asks for 2FA or CAPTCHA, complete it manually...")
        time.sleep(20)

    except PWTimeout:
        print("⚠️ Couldn’t reach login form — maybe already logged in?")

    # Confirm login
    try:
        page.wait_for_selector('img[alt="avatar"], [data-bn-type="profileIcon"]', timeout=8000)
        print("✅ Logged in successfully.")
    except PWTimeout:
        print("⚠️ Couldn’t confirm login, check browser manually.")

    print("Press Enter to close.")
    input()
    ctx.close()
