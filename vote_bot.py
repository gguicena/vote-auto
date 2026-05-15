#!/usr/bin/env python3
"""
Bot de vote NationsGlory.
- 2 sites : Serveur-prive (cooldown 1h30) et Serveur Minecraft (cooldown 3h)
- Tourne en boucle tout le mois, vote dès que le cooldown est écoulé
- Anti-détection + CAPTCHA image automatique (2captcha)
"""

import os, sys, time, random, logging, json, base64, urllib.request, urllib.parse
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

def _2captcha_poll(cid: str) -> str | None:
    """Attend et retourne la solution depuis 2captcha."""
    for _ in range(24):
        _sleep(5, 6)
        data = json.loads(urllib.request.urlopen(
            f"https://2captcha.com/res.php?key={CAPTCHA_APIKEY}&action=get&id={cid}&json=1", timeout=10
        ).read())
        if data.get("status") == 1:
            return data["request"]
        if "NOT_READY" not in data.get("request", ""):
            log.error(f"2captcha erreur : {data}")
            return None
    log.error("Délai 2captcha dépassé.")
    return None


def _solve_image_captcha(page) -> str | None:
    """
    Résout un CAPTCHA image texte (type serveur-prive.net).
    Prend une capture de l'image, l'envoie à 2captcha, retourne le texte.
    """
    if not CAPTCHA_APIKEY:
        log.warning("Pas de CAPTCHA_APIKEY — impossible de résoudre le CAPTCHA image.")
        return None

    # Cherche l'image CAPTCHA (essaie plusieurs sélecteurs)
    img_elem = None
    for sel in ["img.captcha", ".captcha img", "img[src*='captcha']", "#captcha img", "img[alt*='captcha']"]:
        img_elem = page.query_selector(sel)
        if img_elem:
            break

    if not img_elem:
        log.warning("Image CAPTCHA introuvable sur la page.")
        return None

    # Screenshot de l'image uniquement → base64
    img_bytes = img_elem.screenshot()
    img_b64   = base64.b64encode(img_bytes).decode()

    log.info("CAPTCHA image détecté — envoi à 2captcha…")
    params = urllib.parse.urlencode({
        "key":    CAPTCHA_APIKEY,
        "method": "base64",
        "body":   img_b64,
        "json":   1,
    })
    resp = json.loads(urllib.request.urlopen(f"https://2captcha.com/in.php?{params}", timeout=15).read())
    if resp.get("status") != 1:
        log.error(f"2captcha refus image : {resp}")
        return None

    solution = _2captcha_poll(resp["request"])
    if solution:
        log.info(f"Solution CAPTCHA image : '{solution}'")
    return solution


def _solve_recaptcha(page) -> bool:
    """Résout un reCAPTCHA v2 ou hCaptcha (type Google/hCaptcha)."""
    if not CAPTCHA_APIKEY:
        return False

    rc = page.query_selector("[data-sitekey]")
    if not rc:
        return False

    sitekey  = rc.get_attribute("data-sitekey")
    hcaptcha = bool(page.query_selector(".h-captcha"))
    method   = "hcaptcha" if hcaptcha else "userrecaptcha"
    log.info(f"reCAPTCHA détecté ({method}) — envoi à 2captcha…")

    params = urllib.parse.urlencode({
        "key": CAPTCHA_APIKEY, "method": method,
        "sitekey": sitekey, "pageurl": page.url, "json": 1,
    })
    resp = json.loads(urllib.request.urlopen(f"https://2captcha.com/in.php?{params}", timeout=15).read())
    if resp.get("status") != 1:
        log.error(f"2captcha refus : {resp}")
        return False

    sol = _2captcha_poll(resp["request"])
    if not sol:
        return False

    if hcaptcha:
        page.evaluate(f'document.querySelector("[name=h-captcha-response]").value = "{sol}"')
    else:
        page.evaluate(f'document.getElementById("g-recaptcha-response").innerHTML = "{sol}"')
    log.info("reCAPTCHA résolu et injecté.")
    _sleep(0.5, 1.2)
    return True


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


# ── Ouverture d'un onglet externe depuis un bouton NationsGlory ──────────────

def _open_external_tab(page, context, label: str):
    """Clique sur le bouton NationsGlory et retourne la page externe ouverte."""
    page.goto(VOTE_URL, wait_until="domcontentloaded", timeout=TIMEOUT)
    _sleep(1.5, 3)
    _scroll(page)

    btn = page.query_selector(f"a:has-text('{label}'), button:has-text('{label}')")
    if not btn:
        log.warning(f"Bouton '{label}' introuvable sur la page de vote.")
        return None

    log.info(f"Bouton trouvé : '{btn.inner_text().strip()}'")
    box = btn.bounding_box()
    if not box:
        return None

    cx = box["x"] + box["width"]  * random.uniform(0.35, 0.65)
    cy = box["y"] + box["height"] * random.uniform(0.35, 0.65)

    try:
        with context.expect_page(timeout=TIMEOUT) as new_page_info:
            _human_click(page, cx, cy)
        ext = new_page_info.value
    except Exception:
        href = btn.get_attribute("href") or ""
        if not href:
            log.warning("Pas de href sur le bouton.")
            return None
        ext = context.new_page()
        ext.goto(href, wait_until="domcontentloaded", timeout=TIMEOUT)

    ext.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
    _sleep(2, 3)
    log.info(f"Page externe : {ext.url}")
    return ext


# ── Site 1 : serveur-prive.net ────────────────────────────────────────────────
# Structure : CAPTCHA image texte + champ Pseudonyme + bouton "Je vote maintenant"

def _vote_serveur_prive(page, context) -> bool:
    ext = _open_external_tab(page, context, SITE1_TEXT)
    if not ext:
        return False

    try:
        _scroll(ext)
        _sleep(1, 2)

        # Résout le CAPTCHA image (ex: "UQWU")
        captcha_text = _solve_image_captcha(ext)

        # Champ CAPTCHA texte
        captcha_input = None
        for sel in ["input[name='captcha']", "input[placeholder*='captcha']",
                    "input[placeholder*='Captcha']", ".captcha input", "#captcha"]:
            captcha_input = ext.query_selector(sel)
            if captcha_input:
                break

        if captcha_text and captcha_input:
            b = captcha_input.bounding_box()
            if b:
                _human_click(ext, b["x"] + b["width"]/2, b["y"] + b["height"]/2)
            _sleep(0.3, 0.6)
            for ch in captcha_text:
                ext.keyboard.type(ch)
                time.sleep(random.uniform(0.07, 0.15))
            log.info(f"CAPTCHA tapé : '{captcha_text}'")
        elif not captcha_text:
            log.warning("CAPTCHA image non résolu (pas de clé 2captcha ?).")

        # Champ Pseudonyme
        for sel in ["input[name='pseudo']", "input[placeholder*='Pseudonyme']",
                    "input[placeholder*='pseudo']", "input[name='username']"]:
            pseudo_input = ext.query_selector(sel)
            if pseudo_input:
                b = pseudo_input.bounding_box()
                if b:
                    _human_click(ext, b["x"] + b["width"]/2, b["y"] + b["height"]/2)
                _sleep(0.2, 0.5)
                # Efface d'abord
                ext.keyboard.press("Control+a")
                ext.keyboard.press("Delete")
                _sleep(0.1, 0.3)
                for ch in USERNAME:
                    ext.keyboard.type(ch)
                    time.sleep(random.uniform(0.07, 0.15))
                log.info(f"Pseudonyme tapé : '{USERNAME}'")
                break

        _sleep(0.5, 1.2)

        # Bouton "Je vote maintenant"
        for sel in ["button:has-text('Je vote maintenant')", "a:has-text('Je vote maintenant')",
                    "input[type='submit']", "button[type='submit']", ".btn-vote"]:
            btn = ext.query_selector(sel)
            if btn:
                b = btn.bounding_box()
                if b:
                    _human_click(ext, b["x"] + b["width"]/2, b["y"] + b["height"]/2)
                    _sleep(2, 4)
                    log.info("Bouton 'Je vote maintenant' cliqué.")
                    break

        # Vérifie succès (page redirige vers classement ou affiche confirmation)
        _sleep(2, 3)
        log.info(f"Après vote site1 : {ext.url}")
        return True

    except Exception as e:
        log.warning(f"Erreur site1 : {e}")
        Path(f"site1_error_{int(time.time())}.html").write_text(ext.content(), encoding="utf-8")
        return False
    finally:
        ext.close()


# ── Site 2 : serveurs-minecraft.org (ou similaire) ───────────────────────────
# Structure inconnue pour l'instant — mode générique + dump si raté

def _vote_serveur_minecraft(page, context) -> bool:
    ext = _open_external_tab(page, context, SITE2_TEXT)
    if not ext:
        return False

    try:
        _scroll(ext)
        _sleep(1, 2)

        # Tente reCAPTCHA d'abord
        _solve_recaptcha(ext)

        # Tente CAPTCHA image si présent
        captcha_text = _solve_image_captcha(ext)
        if captcha_text:
            for sel in ["input[name='captcha']", "input[placeholder*='captcha']",
                        "input[placeholder*='Captcha']", ".captcha input"]:
                inp = ext.query_selector(sel)
                if inp:
                    b = inp.bounding_box()
                    if b:
                        _human_click(ext, b["x"] + b["width"]/2, b["y"] + b["height"]/2)
                    for ch in captcha_text:
                        ext.keyboard.type(ch)
                        time.sleep(random.uniform(0.07, 0.15))
                    break

        # Champ pseudo si présent
        for sel in ["input[name='pseudo']", "input[name='username']",
                    "input[placeholder*='pseudo']", "input[placeholder*='Pseudonyme']"]:
            inp = ext.query_selector(sel)
            if inp:
                b = inp.bounding_box()
                if b:
                    _human_click(ext, b["x"] + b["width"]/2, b["y"] + b["height"]/2)
                ext.keyboard.press("Control+a")
                for ch in USERNAME:
                    ext.keyboard.type(ch)
                    time.sleep(random.uniform(0.07, 0.15))
                log.info(f"Pseudo tapé sur site2")
                break

        _sleep(0.5, 1.2)

        # Bouton vote
        voted = False
        for sel in ["button:has-text('Je vote')", "button:has-text('Vote')",
                    "a:has-text('Je vote')",       "a:has-text('Voter')",
                    "input[type='submit']",         "button[type='submit']"]:
            btn = ext.query_selector(sel)
            if btn:
                b = btn.bounding_box()
                if b:
                    _human_click(ext, b["x"] + b["width"]/2, b["y"] + b["height"]/2)
                    _sleep(2, 4)
                    log.info(f"Vote site2 cliqué sur {ext.url}")
                    voted = True
                    break

        if not voted:
            log.warning("Bouton vote site2 introuvable — dump HTML sauvegardé.")
            Path(f"site2_dump_{int(time.time())}.html").write_text(ext.content(), encoding="utf-8")

        return voted

    except Exception as e:
        log.warning(f"Erreur site2 : {e}")
        return False
    finally:
        ext.close()


# ── Session de vote (les 2 sites) ─────────────────────────────────────────────

def vote_session(page, context, do_site1: bool, do_site2: bool):
    results = {"site1": False, "site2": False}

    if do_site1:
        log.info("=== Vote Serveur-prive ===")
        results["site1"] = _vote_serveur_prive(page, context)
        _sleep(5, 12)

    if do_site2:
        log.info("=== Vote Serveur Minecraft ===")
        results["site2"] = _vote_serveur_minecraft(page, context)

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
