# vote-auto — Bot de vote NationsGlory

Vote automatiquement sur https://nationsglory.fr/vote avec ton compte.

## Installation

```bash
# 1. Installe les dépendances Python
pip install -r requirements.txt

# 2. Installe le navigateur Chromium pour Playwright
playwright install chromium

# 3. Configure tes identifiants
cp .env.example .env
# Édite .env avec ton pseudo et mot de passe
```

## Utilisation

### Vote unique (maintenant)
```bash
python vote_bot.py
```

### Vote automatique toutes les 24h
```bash
python schedule_vote.py
```

### Avec cron (Linux/Mac) — vote tous les jours à minuit
```bash
crontab -e
# Ajoute cette ligne :
0 0 * * * cd /chemin/vers/vote-auto && python vote_bot.py >> vote_bot.log 2>&1
```

### Avec Task Scheduler (Windows)
Crée une tâche planifiée qui exécute `python vote_bot.py` tous les jours.

## Notes

- Le bot ouvre un vrai navigateur (visible à l'écran). Pour le cacher, mets `headless=True` dans `vote_bot.py` ligne `browser = p.chromium.launch(...)`.
- Les logs sont dans `vote_bot.log`.
- Si la structure du site change, le HTML de la page est sauvegardé dans `vote_page_*.html` pour débogage.
