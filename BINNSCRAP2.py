# binance_login_passkey.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv
import os, time, pathlib

load_dotenv()
EMAIL = os.getenv("BINANCE_EMAIL")
assert EMAIL, "Ajoute BINANCE_EMAIL dans ton .env"

PROFILE_DIR = "binance_profile"
HOME = "https://accounts.binance.com/en/login"

def snap(page, name):
    pathlib.Path("debug").mkdir(exist_ok=True)
    page.screenshot(path=f"debug/{name}.png", full_page=True)

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
    )
    page = ctx.new_page()
    page.goto(HOME, wait_until="networkidle")

    try:
        # --- EMAIL ---
        username = page.locator('[data-e2e="input-username"]').first
        username.wait_for(state="visible", timeout=10000)
        username.fill(EMAIL)

        # --- Suivant ---
        next_btn = page.locator('[data-e2e="btn-accounts-form-submit"]').first
        next_btn.click()

        print("🟡 Attente de 30s pour que tu valides la connexion avec ta clé d’accès…")
        time.sleep(30)

    except PWTimeout as e:
        print(f"⛔ Timeout: {e}")
        snap(page, "exception")

    # Vérif login (avatar ou dashboard)
    try:
        page.wait_for_load_state("networkidle")
        if page.locator('img[alt="avatar"], [data-bn-type="profileIcon"]').first.is_visible(timeout=10000):
            print("✅ Connexion confirmée.")
        else:
            print("⚠️ Impossible de confirmer — regarde debug/")
            snap(page, "cannot_confirm_login")
    except PWTimeout:
        print("⚠️ Timeout sur la vérif connexion.")
        snap(page, "verify_timeout")

    input("Press Enter to close…")
    ctx.close()
