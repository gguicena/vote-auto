#!/usr/bin/env python3
"""
Bot de vote NationsGlory — version améliorée.
Anti-détection, résolution CAPTCHA automatique, boucle mensuelle.
"""

import os, sys, time, random, logging, json
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
USERNAME       = os.getenv("NG_USERNAME", "")
PASSWORD       = os.getenv("NG_PASSWORD", "")
CAPTCHA_APIKEY = os.getenv("CAPTCHA_APIKEY", "")   # clé 2captcha.com

BASE_URL  = "https://nationsglory.fr"
LOGIN_URL = f"{BASE_URL}/login"
VOTE_URL  = f"{BASE_URL}/vote"

TIMEOUT   = 30_000   # ms Playwright
LOG_FILE  = Path("vote_bot.log")

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# User-agents réalistes
# ──────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
]


# ──────────────────────────────────────────────
# Helpers humains
# ──────────────────────────────────────────────

def _sleep(lo: float, hi: float):
    """Pause aléatoire pour imiter un humain."""
    time.sleep(random.uniform(lo, hi))


def _human_type(page, selector: str, text: str):
    """Tape caractère par caractère avec délais variables."""
    page.click(selector)
    _sleep(0.3, 0.7)
    for char in text:
        page.keyboard.type(char)
        time.sleep(random.uniform(0.05, 0.18))


def _human_click(page, selector: str):
    """Déplace la souris aléatoirement avant de cliquer."""
    try:
        elem = page.query_selector(selector)
        if not elem:
            return False
        box = elem.bounding_box()
        if not box:
            return False
        # Coordonnées aléatoires dans l'élément
        x = box["x"] + box["width"]  * random.uniform(0.3, 0.7)
        y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        # Mouvement en plusieurs étapes
        page.mouse.move(
            x + random.uniform(-80, 80),
            y + random.uniform(-80, 80),
        )
        _sleep(0.1, 0.4)
        page.mouse.move(x, y)
        _sleep(0.05, 0.15)
        page.mouse.click(x, y)
        return True
    except Exception:
        return False


def _random_scroll(page):
    """Scroll aléatoire pour simuler une lecture humaine."""
    for _ in range(random.randint(2, 5)):
        page.mouse.wheel(0, random.randint(100, 400))
        _sleep(0.3, 0.9)


# ──────────────────────────────────────────────
# CAPTCHA (2captcha)
# ──────────────────────────────────────────────

def _solve_recaptcha(page) -> bool:
    """Détecte et résout un reCAPTCHA v2 / hCaptcha via 2captcha."""
    if not CAPTCHA_APIKEY:
        log.warning("Pas de clé CAPTCHA_APIKEY — CAPTCHA ignoré.")
        return False

    import urllib.request, urllib.parse

    # Cherche reCAPTCHA v2
    sitekey = None
    hcaptcha = False

    rc = page.query_selector("[data-sitekey]")
    if rc:
        sitekey = rc.get_attribute("data-sitekey")
        hcaptcha = bool(page.query_selector(".h-captcha"))

    if not sitekey:
        return False  # Pas de CAPTCHA détecté

    captcha_type = "hcaptcha" if hcaptcha else "userrecaptcha"
    log.info(f"CAPTCHA détecté ({captcha_type}), envoi à 2captcha…")

    page_url = page.url

    # Soumet à 2captcha
    params = urllib.parse.urlencode({
        "key":     CAPTCHA_APIKEY,
        "method":  "hcaptcha" if hcaptcha else "userrecaptcha",
        "sitekey": sitekey,
        "pageurl": page_url,
        "json":    1,
    })
    req = urllib.request.urlopen(f"https://2captcha.com/in.php?{params}", timeout=15)
    resp = json.loads(req.read())
    if resp.get("status") != 1:
        log.error(f"2captcha refus : {resp}")
        return False

    captcha_id = resp["request"]
    log.info(f"CAPTCHA soumis (id={captcha_id}), attente de la solution…")

    # Attend la solution (max 120s)
    solution = None
    for _ in range(24):
        _sleep(5, 6)
        poll = urllib.request.urlopen(
            f"https://2captcha.com/res.php?key={CAPTCHA_APIKEY}&action=get&id={captcha_id}&json=1",
            timeout=10,
        )
        data = json.loads(poll.read())
        if data.get("status") == 1:
            solution = data["request"]
            break
        if data.get("request") not in ("CAPCHA_NOT_READY", "CAPTCHA_NOT_READY"):
            log.error(f"Erreur 2captcha : {data}")
            return False

    if not solution:
        log.error("Délai CAPTCHA dépassé.")
        return False

    log.info("Solution CAPTCHA reçue — injection…")

    # Injecte la solution dans la page
    if hcaptcha:
        page.evaluate(f'document.querySelector("[name=h-captcha-response]").value = "{solution}"')
    else:
        page.evaluate(f'document.getElementById("g-recaptcha-response").innerHTML = "{solution}"')

    _sleep(0.5, 1.5)
    return True


# ──────────────────────────────────────────────
# Stealth — init contexte navigateur
# ──────────────────────────────────────────────

def _build_context(p):
    """Crée un contexte Playwright avec paramètres anti-détection."""
    ua       = random.choice(USER_AGENTS)
    viewport = random.choice(VIEWPORTS)

    context = p.chromium.launch_persistent_context(
        user_data_dir=str(Path("browser_data")),   # garde les cookies/session
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--window-size={},{}".format(viewport["width"], viewport["height"]),
            "--lang=fr-FR",
        ],
        user_agent=ua,
        viewport=viewport,
        locale="fr-FR",
        timezone_id="Europe/Paris",
        accept_downloads=False,
        ignore_https_errors=True,
        # Masque le flag webdriver
        extra_http_headers={
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        },
    )

    # Patch JS anti-détection (supprime navigator.webdriver etc.)
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR', 'fr', 'en'] });
        Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'permissions', {
            get: () => ({
                query: (p) => Promise.resolve({ state: p.name === 'notifications' ? 'denied' : 'granted' })
            })
        });
    """)

    return context


# ──────────────────────────────────────────────
# Login
# ──────────────────────────────────────────────

def _login(page) -> bool:
    log.info("Vérification de la session…")
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=TIMEOUT)
    _sleep(1, 2)

    # Déjà connecté ?
    if page.query_selector("a[href*='logout'], a[href*='deconnexion'], .user-menu, #user-avatar"):
        log.info("Déjà connecté — session valide.")
        return True

    log.info("Connexion en cours…")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT)
    _random_scroll(page)
    _sleep(1, 2)

    # Champs username
    for sel in ["input[name='username']", "input[name='pseudo']", "input[name='login']", "#username", "#pseudo", "input[type='text']"]:
        if page.query_selector(sel):
            _human_type(page, sel, USERNAME)
            break

    _sleep(0.5, 1.2)

    # Champs password
    for sel in ["input[name='password']", "input[type='password']", "#password"]:
        if page.query_selector(sel):
            _human_type(page, sel, PASSWORD)
            break

    _sleep(0.5, 1.5)
    _solve_recaptcha(page)
    _sleep(0.3, 0.8)

    # Submit
    submitted = False
    for sel in ["button[type='submit']", "input[type='submit']", "button:has-text('Connexion')", "button:has-text('Se connecter')", ".btn-login"]:
        if _human_click(page, sel):
            submitted = True
            break

    if not submitted:
        page.keyboard.press("Enter")

    page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
    _sleep(2, 4)

    if "/login" in page.url or page.query_selector(".alert-danger, .error-message"):
        log.error("Échec connexion — vérifie identifiants dans .env")
        return False

    log.info(f"Connecté ! URL : {page.url}")
    return True


# ──────────────────────────────────────────────
# Vote
# ──────────────────────────────────────────────

def _vote_all(page, context) -> int:
    log.info("Chargement de la page de vote…")
    page.goto(VOTE_URL, wait_until="domcontentloaded", timeout=TIMEOUT)
    _random_scroll(page)
    _sleep(1.5, 3)

    # Collecte tous les liens de vote
    all_hrefs = page.evaluate("""
        () => {
            const links = [];
            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                const text = (a.textContent || '').toLowerCase();
                const cls  = (a.className || '').toLowerCase();
                if (
                    href.includes('vote') ||
                    text.includes('vote') ||
                    cls.includes('vote') ||
                    a.closest('[class*="vote"]')
                ) {
                    links.push({ href, text: a.textContent.trim() });
                }
            });
            return links;
        }
    """)

    if not all_hrefs:
        log.warning("Aucun lien de vote trouvé — dump HTML sauvegardé.")
        _dump_page(page)
        return 0

    # Déduplique
    seen   = set()
    unique = []
    for item in all_hrefs:
        h = item["href"]
        if h and h not in seen:
            seen.add(h)
            unique.append(item)

    log.info(f"{len(unique)} lien(s) de vote trouvé(s).")

    voted = 0
    for item in unique:
        href = item["href"]
        text = item["text"]
        log.info(f"  → Vote : {text or href}")
        try:
            ok = _do_vote(page, context, href)
            if ok:
                voted += 1
            _sleep(3, 7)   # pause humaine entre chaque vote
        except Exception as e:
            log.warning(f"  Échec sur {href} : {e}")

    return voted


def _do_vote(page, context, href: str) -> bool:
    if href.startswith("http") and BASE_URL not in href:
        # Site externe — nouvel onglet
        with context.expect_page(timeout=TIMEOUT) as new_page_info:
            page.evaluate(f"window.open('{href}', '_blank')")
        ext = new_page_info.value
        ext.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
        _sleep(2, 4)
        _random_scroll(ext)

        _solve_recaptcha(ext)

        # Cherche bouton vote sur la page externe
        for sel in [
            "button:has-text('Vote')", "input[type='submit']",
            "button[type='submit']", ".vote-btn", "#vote-btn",
            "a:has-text('Vote')", "button:has-text('Voter')",
        ]:
            if _human_click(ext, sel):
                log.info(f"    Bouton cliqué sur {ext.url}")
                _sleep(2, 4)
                break

        ext.close()
    else:
        # Lien interne
        page.goto(href, wait_until="domcontentloaded", timeout=TIMEOUT)
        _random_scroll(page)
        _sleep(1, 3)
        _solve_recaptcha(page)
        for sel in ["button[type='submit']", "input[type='submit']", ".vote-btn"]:
            if _human_click(page, sel):
                break
        _sleep(1, 2)
        page.goto(VOTE_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    return True


def _dump_page(page):
    fname = f"vote_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    Path(fname).write_text(page.content(), encoding="utf-8")
    log.info(f"HTML sauvegardé : {fname}")


# ──────────────────────────────────────────────
# Point d'entrée — vote unique
# ──────────────────────────────────────────────

def run_once() -> bool:
    from playwright.sync_api import sync_playwright

    if not USERNAME or not PASSWORD:
        log.error("Remplis NG_USERNAME et NG_PASSWORD dans .env")
        sys.exit(1)

    log.info("=== Démarrage du bot de vote ===")
    with sync_playwright() as p:
        context = _build_context(p)
        page    = context.pages[0] if context.pages else context.new_page()
        try:
            if not _login(page):
                return False
            voted = _vote_all(page, context)
            log.info(f"=== {voted} vote(s) effectué(s) ===")
            return voted > 0
        except Exception as e:
            log.exception(f"Erreur critique : {e}")
            return False
        finally:
            context.close()


if __name__ == "__main__":
    run_once()
