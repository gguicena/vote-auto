#!/usr/bin/env python3
"""
Lance le bot de vote tous les jours pendant tout le mois.
Tu lances ce script le 1er du mois et il tourne jusqu'à la fin du mois.

Usage :
    python run_monthly.py
"""

import random
import time
import logging
from datetime import datetime, timedelta
from calendar import monthrange

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from vote_bot import run_once

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scheduler.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# Heure de vote chaque jour : entre 8h et 22h, aléatoire (moins suspect)
VOTE_HOUR_MIN = 8
VOTE_HOUR_MAX = 22


def _next_vote_time() -> datetime:
    """Calcule l'heure du prochain vote : demain à une heure aléatoire."""
    tomorrow = datetime.now() + timedelta(days=1)
    hour     = random.randint(VOTE_HOUR_MIN, VOTE_HOUR_MAX)
    minute   = random.randint(0, 59)
    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _end_of_month() -> datetime:
    """Retourne le dernier instant du mois en cours."""
    now   = datetime.now()
    _, last_day = monthrange(now.year, now.month)
    return now.replace(day=last_day, hour=23, minute=59, second=59)


def main():
    end = _end_of_month()
    log.info(f"=== Bot mensuel démarré — tourne jusqu'au {end.strftime('%d/%m/%Y')} ===")

    attempt = 0

    while datetime.now() < end:
        attempt += 1
        log.info(f"--- Tentative #{attempt} ({datetime.now().strftime('%d/%m/%Y %H:%M')}) ---")

        success = False
        for retry in range(1, 4):   # max 3 essais par jour
            log.info(f"  Essai {retry}/3…")
            try:
                success = run_once()
                if success:
                    break
            except Exception as e:
                log.warning(f"  Erreur essai {retry} : {e}")
            if retry < 3:
                wait = retry * 300   # 5min, 10min entre les retries
                log.info(f"  Attente {wait//60} min avant nouvel essai…")
                time.sleep(wait)

        if success:
            log.info("  Vote du jour réussi.")
        else:
            log.error("  Tous les essais ont échoué aujourd'hui.")

        # Pause jusqu'au prochain vote
        next_vote = _next_vote_time()
        if next_vote > end:
            log.info("Fin du mois atteinte — arrêt du bot.")
            break

        delta = (next_vote - datetime.now()).total_seconds()
        log.info(f"Prochain vote : {next_vote.strftime('%d/%m/%Y à %Hh%M')} (dans {delta/3600:.1f}h)")
        time.sleep(max(delta, 0))

    log.info("=== Bot mensuel terminé ===")


if __name__ == "__main__":
    main()
