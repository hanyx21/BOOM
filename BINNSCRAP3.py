# binance_login_passkey_to_wallet.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv
import os, time, pathlib, re

# ---------- CONFIG ----------
PROFILE_DIR = "binance_profile"
LOGIN_URL = "https://accounts.binance.com/en/login"
DASHBOARD_URL = "https://www.binance.com/en/my/dashboard"
PASSKEY_WAIT_SECONDS = 30
USER_AGENT_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ---------- ENV ----------
load_dotenv()
EMAIL = os.getenv("BINANCE_EMAIL")
assert EMAIL, "Ajoute BINANCE_EMAIL dans ton .env (pas besoin de mot de passe pour passkey)."

# ---------- UTILS ----------
def snap(page, name):
    pathlib.Path("debug").mkdir(exist_ok=True)
    page.screenshot(path=f"debug/{name}.png", full_page=True)
    try:
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

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        user_agent=USER_AGENT_DESKTOP,
        # channel="chrome",  # décommente si tu veux forcer Chrome installé
    )
    page = ctx.new_page()

    # 1) Aller à la page de login
    page.goto(LOGIN_URL, wait_until="networkidle")

    try:
        # Bannière cookies éventuelle
        click_if_visible(page, [
            'button:has-text("Accept all")',
            'button:has-text("Accept All")',
            'button:has-text("Tout accepter")',
            '[data-testid="privacy-accept"]',
        ], timeout_ms=2000)

        # 2) Entrer l'email (champ username) puis "Suivant"
        username = page.locator('[data-e2e="input-username"], input[name="username"]').first
        username.wait_for(state="visible", timeout=10000)
        username.fill(EMAIL)

        next_btn = page.locator('[data-e2e="btn-accounts-form-submit"], button:has-text("Suivant"), button:has-text("Next")').first
        next_btn.click()

        print(f"🟡 Attente {PASSKEY_WAIT_SECONDS}s pour que tu valides la **clé d’accès** (Windows Hello / YubiKey / TouchID)…")
        time.sleep(PASSKEY_WAIT_SECONDS)

    except PWTimeout as e:
        print(f"⛔ Timeout pendant la phase email/passkey: {e}")
        snap(page, "exception_email")
    
    # 3) Aller au dashboard wallet
    try:
        page.goto(DASHBOARD_URL, wait_until="networkidle")

        # 4) Vérifier que la session est bien active (icône profil ou URL dashboard)
        ok = False
        for sel in [
            'img[alt="avatar"]',
            '[data-bn-type="profileIcon"]',
            '[data-testid="header-profile"]',
        ]:
            loc = page.locator(sel).first
            try:
                if loc.count() and loc.is_visible(timeout=4000):
                    ok = True
                    break
            except Exception:
                pass

        if not ok and re.search(r"/my/dashboard", page.url, re.I):
            ok = True

        if ok:
            print("✅ Connecté et sur le dashboard wallet.")
        else:
            print("⚠️ Pas certain d’être connecté (peut-être redirigé vers login). Capture enregistrée.")
            snap(page, "dashboard_uncertain")

    except PWTimeout:
        print("⚠️ Timeout en allant sur le dashboard. Capture enregistrée.")
        snap(page, "dashboard_timeout")

    input("Press Enter to close…")
    ctx.close()
