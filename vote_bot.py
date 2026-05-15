#!/usr/bin/env python3
"""
Bot de vote automatique pour NationsGlory.
Lance le navigateur, se connecte, puis vote sur tous les sites disponibles.
"""

import os
import sys
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("vote_bot.log"),
    ],
)
log = logging.getLogger(__name__)

USERNAME = os.getenv("NG_USERNAME", "")
PASSWORD = os.getenv("NG_PASSWORD", "")

BASE_URL = "https://nationsglory.fr"
VOTE_URL = f"{BASE_URL}/vote"
LOGIN_URL = f"{BASE_URL}/login"

TIMEOUT = 15_000  # ms


def run():
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    if not USERNAME or not PASSWORD:
        log.error("Définis NG_USERNAME et NG_PASSWORD dans le fichier .env ou en variables d'environnement.")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=True pour tourner en arrière-plan
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
        )
        page = context.new_page()

        try:
            _login(page)
            voted = _vote_all(page, context)
            log.info(f"Terminé — {voted} site(s) voté(s) avec succès.")
        except Exception as e:
            log.exception(f"Erreur inattendue : {e}")
        finally:
            context.close()
            browser.close()


def _login(page):
    from playwright.sync_api import TimeoutError as PWTimeout

    log.info("Connexion à NationsGlory…")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    # Rempli le formulaire de connexion
    for selector in ["input[name='username']", "input[name='pseudo']", "input[name='login']", "#username", "#pseudo"]:
        try:
            page.fill(selector, USERNAME, timeout=2000)
            log.debug(f"Champ username trouvé : {selector}")
            break
        except Exception:
            continue

    for selector in ["input[name='password']", "input[type='password']", "#password"]:
        try:
            page.fill(selector, PASSWORD, timeout=2000)
            log.debug(f"Champ password trouvé : {selector}")
            break
        except Exception:
            continue

    # Soumet le formulaire
    for selector in ["button[type='submit']", "input[type='submit']", "button:text('Connexion')", "button:text('Se connecter')"]:
        try:
            page.click(selector, timeout=2000)
            break
        except Exception:
            continue

    page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)

    # Vérifie qu'on est connecté (pas de page login)
    if "/login" in page.url:
        log.error("Échec de la connexion — vérifie les identifiants.")
        sys.exit(1)

    log.info(f"Connecté ! Page actuelle : {page.url}")


def _vote_all(page, context) -> int:
    from playwright.sync_api import TimeoutError as PWTimeout

    log.info(f"Ouverture de la page de vote : {VOTE_URL}")
    page.goto(VOTE_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    voted = 0

    # Cherche tous les liens/boutons de vote
    vote_selectors = [
        "a[href*='vote']",
        "a.vote-btn",
        "a.btn-vote",
        ".vote-link",
        ".vote a",
        "a[class*='vote']",
        "button[class*='vote']",
    ]

    all_links = []
    for sel in vote_selectors:
        links = page.query_selector_all(sel)
        all_links.extend(links)

    # Déduplique par href
    seen_hrefs = set()
    unique_links = []
    for link in all_links:
        href = link.get_attribute("href") or ""
        if href not in seen_hrefs and href:
            seen_hrefs.add(href)
            unique_links.append((href, link))

    if not unique_links:
        log.warning("Aucun lien de vote trouvé — inspection manuelle du HTML…")
        _dump_vote_page(page)
        return 0

    log.info(f"{len(unique_links)} lien(s) de vote détecté(s).")

    for href, link in unique_links:
        try:
            voted += _click_vote_link(page, context, href, link)
            time.sleep(2)
        except Exception as e:
            log.warning(f"Erreur sur {href} : {e}")

    return voted


def _click_vote_link(page, context, href: str, link) -> int:
    from playwright.sync_api import TimeoutError as PWTimeout

    log.info(f"Vote sur : {href}")

    if href.startswith("http"):
        # Lien externe — ouvre dans un nouvel onglet
        with context.expect_page(timeout=TIMEOUT) as new_page_info:
            link.click()
        new_page = new_page_info.value
        new_page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
        log.info(f"  Onglet ouvert : {new_page.url}")

        # Cherche un bouton de vote sur la page externe
        for sel in ["button:text('Vote')", "input[type='submit']", "button[type='submit']", ".vote-btn", "#vote-btn"]:
            try:
                new_page.click(sel, timeout=3000)
                log.info(f"  Bouton cliqué sur {new_page.url}")
                new_page.wait_for_timeout(2000)
                break
            except Exception:
                continue

        new_page.close()
    else:
        # Lien interne
        page.click(f"a[href='{href}']", timeout=TIMEOUT)
        page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
        log.info(f"  Voté sur page interne : {page.url}")
        page.go_back(timeout=TIMEOUT)

    return 1


def _dump_vote_page(page):
    """Sauvegarde le HTML de la page de vote pour analyse."""
    html = page.content()
    fname = f"vote_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"HTML sauvegardé dans {fname} — ouvre-le pour analyser la structure.")


if __name__ == "__main__":
    # Charge .env si présent
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    run()
