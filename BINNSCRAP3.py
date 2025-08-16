# binance_passkey_buy_btc_retry.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv
import os, time, pathlib, re

# ---------- CONFIG ----------
PROFILE_DIR = "binance_profile"
LOGIN_URL = "https://accounts.binance.com/en/login"
TRADE_URL = "https://www.binance.com/en/trade/BTC_USDT?type=spot"
PASSKEY_WAIT_SECONDS = 20
AMOUNT_USDT = 1500
EXECUTE_ORDER = True
USER_AGENT_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ---------- ENV ----------
load_dotenv()
EMAIL = os.getenv("BINANCE_EMAIL")
assert EMAIL, "Ajoute BINANCE_EMAIL dans ton .env"

# ---------- UTILS ----------
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
    """
    Navigates to url. If Binance triggers another auto-navigation (e.g., to /my/dashboard),
    retry once after waiting for things to settle.
    """
    try:
        page.goto(url, wait_until=first_wait)
        return
    except Exception as e:
        if "interrupted by another navigation" in str(e):
            # Let the current redirect complete, then retry
            try:
                page.wait_for_load_state("load", timeout=15000)
                page.wait_for_url(re.compile(r"^https://www\.binance\.com/.*"), timeout=15000)
            except Exception:
                pass
            time.sleep(0.8)
            page.goto(url, wait_until="networkidle")
        else:
            raise

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        user_agent=USER_AGENT_DESKTOP,
        # channel="chrome",  # décommente si tu veux forcer Chrome
    )
    page = ctx.new_page()

    # --- 1) LOGIN (email + passkey) ---
    page.goto(LOGIN_URL, wait_until="networkidle")
    try:
        # cookies éventuels
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
            raise PWTimeout("Champ email introuvable.")

        username.click()
        username.fill(EMAIL)

        next_btn = find_first_visible(page, [
            '[data-e2e="btn-accounts-form-submit"]',
            'button:has-text("Suivant")',
            'button:has-text("Next")',
        ])
        if not next_btn:
            snap(page, "no_next_button_email")
            raise PWTimeout("Bouton Suivant introuvable.")
        next_btn.click()

        print(f"🟡 Attente {PASSKEY_WAIT_SECONDS}s pour valider la clé d’accès…")
        time.sleep(PASSKEY_WAIT_SECONDS)

        # ⚠️ NOUVEAU: attendre la fin de la redirection post-login (quitte accounts.*)
        try:
            page.wait_for_url(re.compile(r"^https://www\.binance\.com/.*"), timeout=30000)
        except Exception:
            # Si toujours sur accounts.*, ce n'est pas bloquant; on gèrera avec retry sur le goto
            pass
        page.wait_for_load_state("domcontentloaded")

    except PWTimeout as e:
        print(f"⛔ Timeout phase login: {e}")
        snap(page, "exception_login")

    # --- 2) Aller vers BTC/USDT avec retry si navigation interrompue ---
    goto_with_retry(page, TRADE_URL, first_wait="domcontentloaded")

    # --- 3) S'assurer BUY + MARKET ---
    try:
        # onglet Buy
        click_if_visible(page, [
            '[data-testid="BuyTab"]',
            'div[role="tab"]:has-text("Buy")',
            'div[role="tab"]:has-text("Acheter")',
        ], timeout_ms=3000)

        # basculer en Market
        click_if_visible(page, [
            'span.trade-common-link:has-text("Market")',
            'span.trade-common-link:has-text("Marché")',
        ], timeout_ms=3000)

        time.sleep(0.5)

        # --- 4) Renseigner Total (USDT) ---
        total_input = find_first_visible(page, [
            '#FormRow-BUY-total',
            'input#FormRow-BUY-total',
            'input[name="total"]',
            'label:has-text("Total") ~ div input',
            'label:has-text("Total") + * input',
        ])
        if not total_input:
            snap(page, "no_total_input")
            raise PWTimeout("Champ Total (USDT) introuvable.")

        total_input.click()
        try:
            total_input.fill("")
        except Exception:
            pass
        total_input.type(str(AMOUNT_USDT), delay=30)

        # --- 5) Bouton Buy ---
        buy_btn = find_first_visible(page, [
            '#orderformBuyBtn',
            '[data-testid="button-spot-buy"]',
            'button:has-text("Buy")',
            'button:has-text("Acheter")',
        ])
        if not buy_btn:
            snap(page, "no_buy_button")
            raise PWTimeout("Bouton Buy introuvable.")

        # laisser le temps aux validations d'activer le bouton
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
            ], timeout_ms=2000)
            print(f"✅ Tentative d’ordre MARKET Buy BTC pour {AMOUNT_USDT} USDT envoyée.")
        else:
            print("🛈 Dry-run (EXECUTE_ORDER=False) ou bouton désactivé — aucune exécution.")
            snap(page, "dry_run_or_disabled")

    except PWTimeout as e:
        print(f"⛔ Timeout sur la phase trade: {e}")
        snap(page, "exception_trade")

    input("Press Enter to close…")
    ctx.close()
