#!/usr/bin/env python3
"""
Lance vote_bot.py toutes les 24h (les votes NationsGlory se réinitialisent quotidiennement).
Exécute directement ce script pour une boucle infinie, ou utilise cron/Task Scheduler.
"""

import subprocess
import sys
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("scheduler.log")],
)
log = logging.getLogger(__name__)

INTERVAL_HOURS = 24


def run_bot():
    log.info("Lancement du bot de vote…")
    result = subprocess.run(
        [sys.executable, "vote_bot.py"],
        capture_output=False,
    )
    if result.returncode == 0:
        log.info("Bot terminé avec succès.")
    else:
        log.error(f"Bot terminé avec code {result.returncode}.")


def main():
    log.info(f"Planificateur démarré — vote toutes les {INTERVAL_HOURS}h.")
    while True:
        run_bot()
        next_run = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        log.info(f"Prochaine exécution dans {INTERVAL_HOURS}h.")
        time.sleep(INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    main()
