# binance_passkey_buy_1500.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv
import os, time, pathlib, re

# -------- CONFIG --------
PROFILE_DIR = "binance_profile"
LOGIN_URL = "https://accounts.binance.com/en/login"
TRADE_URL = "https://www.binance.com/en/trade/BTC_USDT?type=spot"
PASSKEY_WAIT_SECONDS = 20
EXECUTE_ORDER = True       # set to False to test without clicking "Buy"
USER_AGENT_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# -------- ENV --------
load_dotenv()
EMAIL = os.getenv("BINANCE_EMAIL")
assert EMAIL, "Add BINANCE_EMAIL to your .env (passkey-only login)."

# -------- UTILS --------
def snap(page, name):
    pathlib.Path("debug").mkdir(exist_ok=True)
    try:
        page.screenshot(path=f"debug/{name}.png", full_page=True)
        with open(f"debug/{name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass

def click_if_visible(page, selectors, timeout_ms=3000):
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible(timeout=timeout_ms):
                loc.click()
                return True
        except Exception:
            pass
    return False

def find_first_visible(page, selectors):
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            return loc
    return None

def goto_with_retry(page, url, first_wait="domcontentloaded"):
    try:
        page.goto(url, wait_until=first_wait)
        return
    except Exception as e:
        if "interrupted by another navigation" in str(e):
            try:
                page.wait_for_load_state("load", timeout=15000)
                page.wait_for_url(re.compile(r"^https://www\.binance\.com/.*"), timeout=15000)
            except Exception:
                pass
            time.sleep(0.8)
            page.goto(url, wait_until="networkidle")
        else:
            raise

# -------- MAIN --------
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        user_agent=USER_AGENT_DESKTOP,
        # channel="chrome",  # uncomment to force installed Chrome
    )
    page = ctx.new_page()

    # 1) Login (email + passkey)
    page.goto(LOGIN_URL, wait_until="networkidle")
    try:
        click_if_visible(page, [
            'button:has-text("Accept all")',
            'button:has-text("Accept All")',
            'button:has-text("Tout accepter")',
            '[data-testid="privacy-accept"]',
        ], timeout_ms=2000)

        username = find_first_visible(page, [
            '[data-e2e="input-username"]',
            'input[name="username"]',
            'input[autocomplete="username"]',
        ])
        if not username:
            snap(page, "no_username_field")
            raise PWTimeout("Email/username field not found.")

        username.click()
        username.fill(EMAIL)

        next_btn = find_first_visible(page, [
            '[data-e2e="btn-accounts-form-submit"]',
            'button:has-text("Suivant")',
            'button:has-text("Next")',
        ])
        if not next_btn:
            snap(page, "no_next_btn")
            raise PWTimeout("Next button not found.")
        next_btn.click()

        print(f"🟡 Waiting {PASSKEY_WAIT_SECONDS}s for you to approve the passkey…")
        time.sleep(PASSKEY_WAIT_SECONDS)

        # Ensure post-login redirect completes
        try:
            page.wait_for_url(re.compile(r"^https://www\.binance\.com/.*"), timeout=30000)
        except Exception:
            pass
        page.wait_for_load_state("domcontentloaded")

    except PWTimeout as e:
        print(f"⛔ Login timeout: {e}")
        snap(page, "login_timeout")

    # 2) Go to BTC/USDT spot with retry
    goto_with_retry(page, TRADE_URL, first_wait="domcontentloaded")

    # 3) Ensure Buy tab + Market mode
    try:
        click_if_visible(page, [
            '[data-testid="BuyTab"]',
            'div[role="tab"]:has-text("Buy")',
            'div[role="tab"]:has-text("Acheter")',
        ], timeout_ms=3000)

        click_if_visible(page, [
            'span.trade-common-link:has-text("Market")',
            'span.trade-common-link:has-text("Marché")',
        ], timeout_ms=3000)

        time.sleep(0.5)

        # 4) EXACT selector you provided: #FormRow-BUY-total
        total_input = page.locator('input#FormRow-BUY-total').first
        total_input.wait_for(state="visible", timeout=10000)
        total_input.scroll_into_view_if_needed()
        total_input.click()

        # Clear any previous value, then type 1500 (fires input events)
        try:
            total_input.fill("")
        except Exception:
            pass
        total_input.type("1500", delay=25)

        # 5) Click Buy
        buy_btn = find_first_visible(page, [
            '#orderformBuyBtn',
            '[data-testid="button-spot-buy"]',
            'button:has-text("Buy")',
            'button:has-text("Acheter")',
        ])
        if not buy_btn:
            snap(page, "no_buy_button")
            raise PWTimeout("Buy button not found.")

        # Let validations enable the button
        for _ in range(25):
            try:
                if buy_btn.is_enabled():
                    break
            except Exception:
                pass
            time.sleep(0.2)

        if EXECUTE_ORDER and buy_btn.is_enabled():
            buy_btn.click()
            click_if_visible(page, [
                'button:has-text("Confirm")',
                'button:has-text("Place Order")',
                'button:has-text("I understand")',
                'button:has-text("Compris")',
            ], timeout_ms=2500)
            print("✅ Sent MARKET Buy for 1500 USDT.")
        else:
            print("🛈 Dry-run or disabled button — not clicking Buy.")
            snap(page, "dry_run_or_disabled")

    except PWTimeout as e:
        print(f"⛔ Trade phase timeout: {e}")
        snap(page, "trade_timeout")

    input("Press Enter to close…")
    ctx.close()
