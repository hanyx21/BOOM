# binance_passkey.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv
import argparse
import os, time, pathlib, re, sys

# -------- CONFIG --------
PROFILE_DIR = "binance_profile"
LOGIN_URL = "https://accounts.binance.com/en/login"
TRADE_URL_TPL = "https://www.binance.com/en/trade/{symbol}?type=spot"  # e.g., BTC_USDT
PASSKEY_WAIT_SECONDS = 20
EXECUTE_ORDER = True       # set to False to dry-run (no final Buy/Sell click)
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
    """Try clicking the first visible element among a list of selectors in the given page or frame."""
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
        # TestIDs/ARIA/CMPs
        '[data-testid="privacy-accept"]',
        '[data-testid="cookie-accept-all"]',
        '[aria-label="Accept all"]',
        '#onetrust-accept-btn-handler',
        'button#truste-consent-button',
        'button.didomi-accept-all',
        'button[aria-label="Accept cookies"]',
    ]
    deadline = time.time() + max_wait_s
    accepted = False
    while time.time() < deadline and not accepted:
        if click_if_visible(page, selectors, timeout_ms=timeout_ms):
            accepted = True
            break
        for frame in page.frames:
            try:
                if click_if_visible(frame, selectors, timeout_ms=timeout_ms):
                    accepted = True
                    break
            except Exception:
                pass
        if not accepted:
            time.sleep(0.25)
    return accepted

def ensure_trade_page(page, symbol):
    url = TRADE_URL_TPL.format(symbol=symbol)
    goto_with_retry(page, url, first_wait="domcontentloaded")
    try:
        accepted = accept_cookies_everywhere(page, timeout_ms=2500, max_wait_s=8)
        if accepted:
            print("✅ Cookie banner dismissed on trade page.")
    except Exception:
        pass

def ensure_market_mode(page):
    # Ensure "Market" order type is active (fallbacks for locales)
    clicked_type = click_if_visible(page, [
        'span.trade-common-link:has-text("Market")',
        'button:has-text("Market")',
        'span.trade-common-link:has-text("Marché")',
        'button:has-text("Marché")',
    ], timeout_ms=2500)
    if clicked_type:
        time.sleep(0.3)

def ensure_buy_tab(page):
    click_if_visible(page, [
        '[data-testid="BuyTab"]',
        'div[role="tab"]:has-text("Buy")',
        'div[role="tab"]:has-text("Acheter")',
    ], timeout_ms=2500)

def ensure_sell_tab(page):
    click_if_visible(page, [
        '[data-testid="SellTab"]',
        'div[role="tab"]:has-text("Sell")',
        'div[role="tab"]:has-text("Vendre")',
    ], timeout_ms=2500)

# -------- ORDER ACTIONS --------
def market_buy(page, amount_usdt):
    """
    Market BUY using a total (quote) amount in USDT.
    """
    ensure_buy_tab(page)
    ensure_market_mode(page)

    # Locate the "Total (USDT)" input on BUY side
    total_input = None
    try_order_total_selectors = [
        'input#FormRow-BUY-total',
        # Extra fallbacks if Binance changes IDs:
        'input[name="total"]',
        '[data-testid="orderFormTotal"] input',
        '[data-testid="orderFormInput"] input[name="total"]',
        'input[placeholder*="Total"]',
    ]
    for sel in try_order_total_selectors:
        loc = page.locator(sel).first
        if loc.count():
            total_input = loc
            break
    if not total_input:
        snap(page, "buy_total_input_not_found")
        raise PWTimeout("Buy total input not found.")

    total_input.wait_for(state="visible", timeout=10000)
    total_input.scroll_into_view_if_needed()
    total_input.click()
    try:
        total_input.fill("")
    except Exception:
        pass
    total_input.type(str(amount_usdt), delay=20)

    # Find and click the BUY button
    buy_btn = find_first_visible(page, [
        '#orderformBuyBtn',
        '[data-testid="button-spot-buy"]',
        'button:has-text("Buy")',
        'button:has-text("Acheter")',
    ])
    if not buy_btn:
        snap(page, "buy_button_not_found")
        raise PWTimeout("Buy button not found.")

    # Wait a bit for validations to enable
    for _ in range(30):
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
        print(f"✅ Sent MARKET Buy for {amount_usdt} USDT.")
    else:
        print("🛈 Dry-run or disabled BUY button — not clicking.")
        snap(page, "buy_dry_or_disabled")

def sell_all(page):
    """
    Market SELL: set the percentage slider to 100% and click Sell.
    """
    ensure_sell_tab(page)
    ensure_market_mode(page)

    # 1) Locate the SELL slider inside the SELL form
    slider = page.locator('form#autoFormSELL input[type="range"].bn-slider').first
    if not slider.count():
        snap(page, "sell_slider_not_found")
        raise PWTimeout("Sell slider not found.")

    slider.wait_for(state="attached", timeout=8000)
    slider.scroll_into_view_if_needed()

    # 2) Set slider to 100 with native setter + fire events (React-friendly)
    slider.evaluate("""
        (el) => {
            // Use the native setter so frameworks detect it
            const proto = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
            proto && proto.set ? proto.set.call(el, '100') : (el.value = '100');
            el.setAttribute('value', '100');

            // Fire events so UI recalculates available amount and enables the button
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
    """)

    # (Optional) small pause to let UI update validations
    page.wait_for_timeout(200)

    # 3) Click the SELL button
    sell_btn = find_first_visible(page, [
        '#orderformSellBtn',
        '[data-testid="button-spot-sell"]',
        'button:has-text("Sell")',
        'button:has-text("Vendre")',
    ])
    if not sell_btn:
        snap(page, "sell_button_not_found")
        raise PWTimeout("Sell button not found.")

    for _ in range(30):
        try:
            if sell_btn.is_enabled():
                break
        except Exception:
            pass
        time.sleep(0.2)

    if EXECUTE_ORDER and sell_btn.is_enabled():
        sell_btn.click()
        click_if_visible(page, [
            'button:has-text("Confirm")',
            'button:has-text("Place Order")',
            'button:has-text("I understand")',
            'button:has-text("Compris")',
        ], timeout_ms=2500)
        print("✅ Sent MARKET Sell (100%).")
    else:
        print("🛈 Dry-run or disabled SELL button — not clicking.")
        snap(page, "sell_dry_or_disabled")



# -------- LOGIN & CONTEXT --------
def login_with_passkey_and_open(symbol):
    """
    Launch Chrome with a persistent profile, log in (email + passkey), and open the trade page for `symbol`.
    Returns the (context, page).
    """
    p = sync_playwright().start()
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        user_agent=USER_AGENT_DESKTOP,
        channel="chrome",  # <- Force installed Chrome
    )
    page = ctx.new_page()

    # Login
    page.goto(LOGIN_URL, wait_until="networkidle")
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

    # Open the trade page for the requested symbol
    ensure_trade_page(page, symbol)
    return p, ctx, page

# -------- CLI --------
def main():
    parser = argparse.ArgumentParser(description="Binance passkey login + market trade helpers.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_buy = sub.add_parser("buy", help="Market BUY with a USDT total.")
    p_buy.add_argument("--symbol", required=True, help="Trading pair, e.g., BTC_USDT")
    p_buy.add_argument("--amount", required=True, type=float, help="USDT amount to spend")

    p_sell = sub.add_parser("sell", help="Market SELL 100% of current asset.")
    p_sell.add_argument("--symbol", required=True, help="Trading pair to sell, e.g., BTC_USDT")

    parser.add_argument("--dry", action="store_true", help="Dry-run (do not click final Buy/Sell)")

    args = parser.parse_args()

    global EXECUTE_ORDER
    EXECUTE_ORDER = not args.dry

    p, ctx, page = login_with_passkey_and_open(args.symbol)

    try:
        if args.cmd == "buy":
            market_buy(page, args.amount)
        elif args.cmd == "sell":
            sell_all(page)
        else:
            print("Unknown command.")
    finally:
        try:
            input("Press Enter to close…")
        except KeyboardInterrupt:
            pass
        ctx.close()
        p.stop()

if __name__ == "__main__":
    main()
