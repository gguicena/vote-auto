#!/usr/bin/env python3
"""
Boucle mensuelle de vote NationsGlory.
- Site 1 (Serveur-prive)    : vote toutes les 1h30
- Site 2 (Serveur Minecraft) : vote toutes les 3h
- Tourne du 1er au dernier jour du mois sans interruption

Usage :
    python run_monthly.py
"""

import time, logging, random
from datetime import datetime
from calendar import monthrange

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from vote_bot import _build_context, _patch_stealth, _login, vote_session, COOLDOWN_SITE1, COOLDOWN_SITE2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scheduler.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # vérifie toutes les 60s si un vote est dispo


def _end_of_month() -> datetime:
    now = datetime.now()
    _, last = monthrange(now.year, now.month)
    return now.replace(day=last, hour=23, minute=59, second=59)


def main():
    from playwright.sync_api import sync_playwright

    end = _end_of_month()
    log.info(f"=== Bot mensuel démarré — tourne jusqu'au {end.strftime('%d/%m/%Y')} ===")
    log.info(f"Site 1 (Serveur-prive)    : vote toutes les 1h30")
    log.info(f"Site 2 (Serveur Minecraft): vote toutes les 3h")

    # Timestamp du dernier vote réussi pour chaque site
    last_vote1 = 0.0
    last_vote2 = 0.0

    with sync_playwright() as p:
        context = _build_context(p)
        _patch_stealth(context)
        page = context.pages[0] if context.pages else context.new_page()

        if not _login(page):
            log.error("Impossible de se connecter — arrêt.")
            context.close()
            return

        try:
            while datetime.now() < end:
                now_ts   = time.time()
                do_site1 = (now_ts - last_vote1) >= COOLDOWN_SITE1
                do_site2 = (now_ts - last_vote2) >= COOLDOWN_SITE2

                if do_site1 or do_site2:
                    log.info(f"--- Lancement vote | site1={'OUI' if do_site1 else 'cooldown'} | site2={'OUI' if do_site2 else 'cooldown'} ---")

                    results = vote_session(page, context, do_site1=do_site1, do_site2=do_site2)

                    if results["site1"]:
                        last_vote1 = time.time()
                        log.info(f"Site1 voté — prochain dans 1h32")
                    if results["site2"]:
                        last_vote2 = time.time()
                        log.info(f"Site2 voté — prochain dans 3h02")

                    # Ré-affiche les prochains horaires
                    _log_next_votes(last_vote1, last_vote2)

                # Attente avant la prochaine vérification
                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log.info("Arrêt manuel (Ctrl+C).")
        except Exception as e:
            log.exception(f"Erreur critique : {e}")
        finally:
            context.close()

    log.info("=== Bot mensuel terminé ===")


def _log_next_votes(last1: float, last2: float):
    import time
    now = time.time()
    def fmt(last, cooldown):
        remaining = max(0, (last + cooldown) - now)
        h = int(remaining // 3600)
        m = int((remaining % 3600) // 60)
        return f"{h}h{m:02d}"
    log.info(f"Prochain vote → site1 dans {fmt(last1, COOLDOWN_SITE1)} | site2 dans {fmt(last2, COOLDOWN_SITE2)}")


if __name__ == "__main__":
    main()
