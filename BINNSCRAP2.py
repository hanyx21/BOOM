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

def click_if_visible(page_or_frame, selectors, timeout_ms=3000):
    """
    Try clicking the first visible element among a list of selectors in the given page or frame.
    """
    for sel in selectors:
        loc = page_or_frame.locator(sel).first
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

def accept_cookies_everywhere(page, timeout_ms=3000, max_wait_s=6):
    """
    Attempts to accept cookie/consent banners on the current page and within iframes.
    Binance may show separate banners on accounts.binance.com and www.binance.com.
    This function is idempotent—calling it multiple times is fine.
    """
    # Common labels (EN/FR/ES and generic attributes)
    selectors = [
        # Buttons by text
        'button:has-text("Accept all")',
        'button:has-text("Accept All")',
        'button:has-text("Allow all")',
        'button:has-text("I Accept")',
        'button:has-text("Agree")',
        'button:has-text("Got it")',
        'button:has-text("Okay")',
        'button:has-text("Ok")',
        # Localized
        'button:has-text("Tout accepter")',
        'button:has-text("Aceptar todo")',
        'button:has-text("Aceptar todas")',
        'button:has-text("Permitir todo")',
        'button:has-text("Compris")',
        # TestIDs/ARIA
        '[data-testid="privacy-accept"]',
        '[data-testid="cookie-accept-all"]',
        '[aria-label="Accept all"]',
        # Common CMPs (OneTrust/TrustArc/Didomi variants)
        '#onetrust-accept-btn-handler',
        'button#truste-consent-button',
        'button.didomi-accept-all',
        'button[aria-label="Accept cookies"]',
    ]

    # Try a short polling loop to catch late-appearing banners/animations
    deadline = time.time() + max_wait_s
    accepted = False
    while time.time() < deadline and not accepted:
        # Main page first
        if click_if_visible(page, selectors, timeout_ms=timeout_ms):
            accepted = True
            break

        # Then try within iframes (CMPs often load inside iframes)
        for frame in page.frames:
            try:
                if click_if_visible(frame, selectors, timeout_ms=timeout_ms):
                    accepted = True
                    break
            except Exception:
                pass

        if not accepted:
            time.sleep(0.25)  # brief wait before polling again

    return accepted

# -------- MAIN --------
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
        ],
        user_agent=USER_AGENT_DESKTOP,
        # channel="chrome",  # uncomment to force installed Chrome
    )
    page = ctx.new_page()

    # 1) Login (email + passkey)
    page.goto(LOGIN_URL, wait_until="networkidle")

    # Handle cookie banner on accounts.binance.com
    try:
        accept_cookies_everywhere(page, timeout_ms=2500, max_wait_s=6)
    except Exception:
        pass

    try:
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

    # Handle cookie banner on www.binance.com (separate consent surface)
    try:
        accepted = accept_cookies_everywhere(page, timeout_ms=2500, max_wait_s=8)
        if accepted:
            print("✅ Cookie banner dismissed on trade page.")
        else:
            print("ℹ️ No cookie banner found on trade page (or already accepted).")
    except Exception:
        pass

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
