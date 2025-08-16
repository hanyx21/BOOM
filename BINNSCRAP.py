# binance_login_full.py
# Playwright desktop login for Binance (email -> password), robust selectors + debug dumps
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv
import os, time, pathlib, re

# ---------- CONFIG ----------
PROFILE_DIR = "binance_profile"
HOME = "https://accounts.binance.com/en/login"  # FR/EN ok, Binance redirige selon la locale
HUMAN_TYPE_DELAY = 50  # ms entre touches sur le password
TFA_WAIT_SECONDS = 40  # temps pour valider 2FA/captcha manuellement
USER_AGENT_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ---------- ENV ----------
load_dotenv()
EMAIL = os.getenv("BINANCE_EMAIL")
PASSWORD = os.getenv("BINANCE_PASSWORD")
assert EMAIL and PASSWORD, "Ajoute BINANCE_EMAIL et BINANCE_PASSWORD dans ton fichier .env"

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

def find_first_visible(page, selectors):
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            return loc
    return None

# ---------- MAIN ----------
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
        ],
        user_agent=USER_AGENT_DESKTOP,
        # channel="chrome",  # décommente si tu as Chrome installé et veux l'utiliser
    )
    page = ctx.new_page()
    page.goto(HOME, wait_until="networkidle")

    try:
        # 0) Bannière cookies si présente
        click_if_visible(page, [
            'button:has-text("Accept all")',
            'button:has-text("Accept All")',
            'button:has-text("Tout accepter")',
            '[data-testid="privacy-accept"]',
        ], timeout_ms=2000)

        # 1) Step EMAIL (ton DOM montre name="username", data-e2e="input-username")
        username = find_first_visible(page, [
            '[data-e2e="input-username"]',
            'input[name="username"]',
            'input[autocomplete="username"]',
            'input[placeholder*="E-mail"], input[placeholder*="Email"]',
        ])
        if not username:
            snap(page, "no_username_field")
            raise PWTimeout("Champ email/username introuvable (voir debug/no_username_field.*)")

        username.click()
        # .fill ici fonctionne, pas de validation spécifique sur ce champ
        username.fill(EMAIL)

        # Bouton Suivant / Next
        next_btn_email = find_first_visible(page, [
            '[data-e2e="btn-accounts-form-submit"]',
            'button:has-text("Suivant")',
            'button:has-text("Next")',
            'button[aria-label="Suivant"]',
        ])
        if not next_btn_email:
            snap(page, "no_next_button_email")
            raise PWTimeout("Bouton Suivant (email) introuvable (voir debug/no_next_button_email.*)")
        next_btn_email.click()

        # 2) Step PASSWORD (certaines variantes imbriquent un iframe)
        page.wait_for_load_state("networkidle")
        time.sleep(0.8)  # petit délai SPA

        # Essayons de localiser le champ password soit sur la page, soit dans une frame liée au login
        pw_context = page
        for f in page.frames:
            if re.search(r"accounts\.binance\.com|/login", f.url or "", re.I):
                pw_context = f
                break

        pwd = find_first_visible(pw_context, [
            'input[name="password"]',
            'input[type="password"]',
            'input[autocomplete="current-password"]',
            'input[placeholder*="Password"]',
            'input[placeholder*="Mot de passe"]',
            '[data-e2e="input-password"]',
        ])
        if not pwd:
            snap(page, "no_password_field")
            raise PWTimeout("Champ mot de passe introuvable (voir debug/no_password_field.*)")

        pwd.click()
        # Utiliser .type (événements clavier) plutôt que .fill — le bouton Next reste sinon désactivé
        try:
            # Effacer si possible
            pwd.fill("")  # safe pour vider dans la plupart des cas
        except Exception:
            pass
        pwd.type(PASSWORD, delay=HUMAN_TYPE_DELAY)

        # Bouton Next / Connexion pour la step password
        next_btn_pw = find_first_visible(pw_context, [
            '[data-e2e="btn-accounts-form-submit"]',
            'button[type="submit"]',
            'button:has-text("Next")',
            'button:has-text("Suivant")',
            'button:has-text("Log in")',
            'button:has-text("Sign in")',
            'button:has-text("Connexion")',
            'button:has-text("Se connecter")',
        ])
        if not next_btn_pw:
            # On tente Enter si aucun bouton identifiable
            pwd.press("Enter")
        else:
            # Attendre que le bouton devienne enabled (debounce côté UI)
            for _ in range(30):  # ~6s
                try:
                    if next_btn_pw.is_enabled():
                        break
                except Exception:
                    pass
                time.sleep(0.2)
            if next_btn_pw.is_enabled():
                next_btn_pw.click()
            else:
                pwd.press("Enter")

        print(f"🟡 Si Binance demande 2FA/CAPTCHA, fais-le maintenant ({TFA_WAIT_SECONDS}s)…")
        time.sleep(TFA_WAIT_SECONDS)

    except PWTimeout as e:
        print(f"⛔ Timeout pendant le flux de login: {e}")
        snap(page, "exception_flow")

    # 3) Vérification connexion (plusieurs heuristiques)
    try:
        page.wait_for_load_state("networkidle")
        ok = False

        for sel in [
            'img[alt="avatar"]',
            '[data-bn-type="profileIcon"]',
            '[data-testid="header-profile"]',
            'a[href*="/my/dashboard"]',
        ]:
            loc = page.locator(sel).first
            try:
                if loc.count() and loc.is_visible(timeout=2000):
                    ok = True
                    break
            except Exception:
                pass

        if not ok:
            # Heuristique URL post-login
            if re.search(r"/(dashboard|account|wallet|my)/", page.url, re.I):
                ok = True

        if ok:
            print("✅ Connexion confirmée.")
        else:
            print("⚠️ Impossible de confirmer la connexion — j’enregistre une capture.")
            snap(page, "cannot_confirm_login")

    except PWTimeout:
        print("⚠️ Timeout pendant la vérification — j’enregistre une capture.")
        snap(page, "verify_timeout")

    input("Press Enter to close…")
    ctx.close()
