#!/usr/bin/env python3
"""
Bot de vote NationsGlory.
- 2 sites : Serveur-prive (cooldown 1h30) et Serveur Minecraft (cooldown 3h)
- Tourne en boucle tout le mois, vote dès que le cooldown est écoulé
- Anti-détection + CAPTCHA automatique (2captcha, optionnel)
"""

import os, sys, time, random, logging, json, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ──────────────────────────────────────────────────────────────────
USERNAME       = os.getenv("NG_USERNAME", "")
PASSWORD       = os.getenv("NG_PASSWORD", "")
CAPTCHA_APIKEY = os.getenv("CAPTCHA_APIKEY", "")

BASE_URL  = "https://nationsglory.fr"
LOGIN_URL = f"{BASE_URL}/login"
VOTE_URL  = f"{BASE_URL}/vote"
TIMEOUT   = 30_000

# Cooldowns en secondes (on ajoute 2 min de marge)
COOLDOWN_SITE1 = 90  * 60 + 120   # 1h32
COOLDOWN_SITE2 = 180 * 60 + 120   # 3h02

# Sélecteurs exacts des boutons (d'après le screenshot)
SITE1_TEXT = "Voter sur Serveur-prive"
SITE2_TEXT = "Voter sur Serveur Minecraft"

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("vote_bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── User-agents & viewports ──────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
]


# ── Helpers humains ───────────────────────────────────────────────────────────

def _sleep(lo: float, hi: float):
    time.sleep(random.uniform(lo, hi))

def _human_type(page, selector: str, text: str):
    page.click(selector)
    _sleep(0.2, 0.6)
    for ch in text:
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.06, 0.17))

def _human_click(page, x: float, y: float):
    # Approche en deux temps
    page.mouse.move(x + random.uniform(-60, 60), y + random.uniform(-60, 60))
    _sleep(0.08, 0.25)
    page.mouse.move(x, y)
    _sleep(0.05, 0.12)
    page.mouse.click(x, y)

def _scroll(page):
    for _ in range(random.randint(1, 3)):
        page.mouse.wheel(0, random.randint(80, 300))
        _sleep(0.2, 0.6)


# ── CAPTCHA (2captcha) ────────────────────────────────────────────────────────

def _solve_captcha(page) -> bool:
    if not CAPTCHA_APIKEY:
        return False

    rc = page.query_selector("[data-sitekey]")
    if not rc:
        return False

    sitekey  = rc.get_attribute("data-sitekey")
    hcaptcha = bool(page.query_selector(".h-captcha"))
    method   = "hcaptcha" if hcaptcha else "userrecaptcha"
    log.info(f"CAPTCHA détecté ({method}) — envoi à 2captcha…")

    params = urllib.parse.urlencode({
        "key": CAPTCHA_APIKEY, "method": method,
        "sitekey": sitekey, "pageurl": page.url, "json": 1,
    })
    resp = json.loads(urllib.request.urlopen(f"https://2captcha.com/in.php?{params}", timeout=15).read())
    if resp.get("status") != 1:
        log.error(f"2captcha refus : {resp}")
        return False

    cid = resp["request"]
    log.info(f"CAPTCHA soumis id={cid}, attente solution…")
    for _ in range(24):
        _sleep(5, 6)
        data = json.loads(urllib.request.urlopen(
            f"https://2captcha.com/res.php?key={CAPTCHA_APIKEY}&action=get&id={cid}&json=1", timeout=10
        ).read())
        if data.get("status") == 1:
            sol = data["request"]
            if hcaptcha:
                page.evaluate(f'document.querySelector("[name=h-captcha-response]").value = "{sol}"')
            else:
                page.evaluate(f'document.getElementById("g-recaptcha-response").innerHTML = "{sol}"')
            log.info("Solution CAPTCHA injectée.")
            _sleep(0.5, 1.2)
            return True
        if "NOT_READY" not in data.get("request", ""):
            log.error(f"2captcha erreur : {data}")
            return False

    log.error("Délai CAPTCHA dépassé.")
    return False


# ── Navigateur (stealth) ──────────────────────────────────────────────────────

def _build_context(p):
    return p.chromium.launch_persistent_context(
        user_data_dir=str(Path("browser_data")),
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--lang=fr-FR",
        ],
        user_agent=random.choice(USER_AGENTS),
        viewport=random.choice(VIEWPORTS),
        locale="fr-FR",
        timezone_id="Europe/Paris",
        extra_http_headers={
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        },
        ignore_https_errors=True,
    )


def _patch_stealth(context):
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver',    { get: () => undefined });
        Object.defineProperty(navigator, 'languages',    { get: () => ['fr-FR', 'fr', 'en'] });
        Object.defineProperty(navigator, 'plugins',      { get: () => [1,2,3,4,5] });
        window.chrome = { runtime: {} };
    """)


# ── Login ─────────────────────────────────────────────────────────────────────

def _login(page) -> bool:
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=TIMEOUT)
    _sleep(1, 2)

    # Déjà connecté ?
    if page.query_selector("a[href*='logout'], .user-menu, #user-avatar, a[href*='profil']"):
        log.info("Session active — pas besoin de se reconnecter.")
        return True

    log.info("Connexion…")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT)
    _scroll(page)
    _sleep(1, 2)

    for sel in ["input[name='username']", "input[name='pseudo']", "input[name='login']", "#username", "input[type='text']"]:
        if page.query_selector(sel):
            _human_type(page, sel, USERNAME)
            break

    _sleep(0.4, 1.0)

    for sel in ["input[name='password']", "input[type='password']", "#password"]:
        if page.query_selector(sel):
            _human_type(page, sel, PASSWORD)
            break

    _sleep(0.5, 1.5)
    _solve_captcha(page)
    _sleep(0.3, 0.8)

    # Submit
    for sel in ["button[type='submit']", "input[type='submit']",
                "button:has-text('Connexion')", "button:has-text('Se connecter')", ".btn-login"]:
        elem = page.query_selector(sel)
        if elem:
            box = elem.bounding_box()
            if box:
                cx = box["x"] + box["width"]  * random.uniform(0.3, 0.7)
                cy = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                _human_click(page, cx, cy)
                break
    else:
        page.keyboard.press("Enter")

    page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
    _sleep(2, 3)

    if "/login" in page.url:
        log.error("Connexion échouée — vérifie NG_USERNAME et NG_PASSWORD dans .env")
        return False

    log.info(f"Connecté ({page.url})")
    return True


# ── Vote sur un site ──────────────────────────────────────────────────────────

def _click_vote_button(page, context, label: str) -> bool:
    """Clique sur le bouton de vote correspondant au label et vote sur la page externe."""
    page.goto(VOTE_URL, wait_until="domcontentloaded", timeout=TIMEOUT)
    _sleep(1.5, 3)
    _scroll(page)

    # Cherche le bouton par texte
    btn = page.query_selector(f"a:has-text('{label}'), button:has-text('{label}')")
    if not btn:
        log.warning(f"Bouton '{label}' introuvable.")
        return False

    # Vérifie si le bouton est actif (pas de cooldown actif = pas de point orange visible)
    btn_text = btn.inner_text()
    log.info(f"Bouton trouvé : '{btn_text.strip()}'")

    box = btn.bounding_box()
    if not box:
        return False

    cx = box["x"] + box["width"]  * random.uniform(0.35, 0.65)
    cy = box["y"] + box["height"] * random.uniform(0.35, 0.65)

    # Ouvre le lien dans un nouvel onglet
    try:
        with context.expect_page(timeout=TIMEOUT) as new_page_info:
            _human_click(page, cx, cy)
        ext = new_page_info.value
    except Exception:
        # Essai en forçant l'ouverture
        href = btn.get_attribute("href") or ""
        if not href:
            log.warning("Pas de href sur le bouton.")
            return False
        ext = context.new_page()
        ext.goto(href, wait_until="domcontentloaded", timeout=TIMEOUT)

    ext.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
    _sleep(2, 4)
    _scroll(ext)
    log.info(f"Page externe ouverte : {ext.url}")

    # Résout le CAPTCHA si présent
    _solve_captcha(ext)
    _sleep(0.5, 1.5)

    # Cherche et clique le bouton de vote sur la page externe
    voted = False
    for sel in [
        "button:has-text('Vote')", "button:has-text('Voter')",
        "a:has-text('Vote')",      "a:has-text('Voter')",
        "input[type='submit']",    "button[type='submit']",
        ".vote-btn", "#vote-btn",  ".btn-vote",
    ]:
        elem = ext.query_selector(sel)
        if elem:
            b = elem.bounding_box()
            if b:
                _human_click(ext, b["x"] + b["width"]/2, b["y"] + b["height"]/2)
                _sleep(2, 4)
                log.info(f"Vote cliqué sur {ext.url}")
                voted = True
                break

    if not voted:
        log.warning(f"Pas de bouton vote trouvé sur {ext.url} — dump sauvegardé.")
        Path(f"ext_vote_{label.replace(' ','_')}_{int(time.time())}.html").write_text(ext.content(), encoding="utf-8")

    _sleep(1, 2)
    ext.close()
    return voted


# ── Session de vote (les 2 sites) ─────────────────────────────────────────────

def vote_session(page, context, do_site1: bool, do_site2: bool):
    results = {"site1": False, "site2": False}

    if do_site1:
        log.info("=== Vote Serveur-prive ===")
        try:
            results["site1"] = _click_vote_button(page, context, SITE1_TEXT)
        except Exception as e:
            log.warning(f"Erreur site1 : {e}")
        _sleep(5, 12)

    if do_site2:
        log.info("=== Vote Serveur Minecraft ===")
        try:
            results["site2"] = _click_vote_button(page, context, SITE2_TEXT)
        except Exception as e:
            log.warning(f"Erreur site2 : {e}")

    return results


# ── Point d'entrée : vote unique ──────────────────────────────────────────────

def run_once():
    """Vote une fois sur les 2 sites (pour test)."""
    if not USERNAME or not PASSWORD:
        log.error("Remplis NG_USERNAME et NG_PASSWORD dans .env")
        sys.exit(1)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        context = _build_context(p)
        _patch_stealth(context)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            if not _login(page):
                return
            results = vote_session(page, context, do_site1=True, do_site2=True)
            log.info(f"Résultats : site1={results['site1']} | site2={results['site2']}")
        except Exception as e:
            log.exception(f"Erreur : {e}")
        finally:
            context.close()


if __name__ == "__main__":
    run_once()
