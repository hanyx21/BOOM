# login_once_then_reuse.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROFILE_DIR = "binance_profile"  # will store cookies/session here
HOME = "https://www.binance.com/"

with sync_playwright() as p:
    # Persistent context keeps you logged in across runs
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,  # show the real browser
        args=["--start-maximized"]
    )
    page = ctx.new_page()
    page.goto(HOME, wait_until="domcontentloaded")

    # If you haven’t logged in before, do it manually now (incl. 2FA/CAPTCHA).
    try:
        # Heuristic: if "Log In" button exists, wait for you to finish login
        page.get_by_role("link", name="Log In").wait_for(timeout=3000)
        print("Please log in manually in the opened window, then press Enter here.")
        input()
    except PWTimeout:
        pass  # Likely already logged in

    # Quick sanity check: look for something that only appears when logged in (avatar/menu)
    # This selector may change; update if Binance updates UI.
    try:
        page.wait_for_selector('img[alt="avatar"], [data-bn-type="profileIcon"]', timeout=8000)
        print("✅ Logged in / session stored.")
    except PWTimeout:
        print("⚠️ Couldn’t confirm login. If you’re not in yet, complete it and rerun.")

    # Do stuff now that you’re logged in:
    # e.g., open the dashboard or balances page
    page.goto(HOME + "en/my/dashboard", wait_until="domcontentloaded")

    # keep browser open so you can see it
    print("Press Enter to close.")
    input()
    ctx.close()