# vote-auto — Bot NationsGlory

Vote automatiquement chaque jour sur https://nationsglory.fr/vote pendant tout le mois.

## Fonctionnalités

- **Anti-détection** : user-agent rotatif, délais humains aléatoires, mouvements de souris simulés, patch `navigator.webdriver`
- **CAPTCHA automatique** : résolution via 2captcha (optionnel, ~3€/mois max)
- **Boucle mensuelle** : tourne tout le mois, vote à une heure aléatoire chaque jour
- **Retry automatique** : 3 tentatives par jour si échec
- **Session persistante** : garde les cookies, pas besoin de se reconnecter chaque fois

---

## Installation (une seule fois)

```bash
# 1. Installe Python 3.10+  →  https://www.python.org/downloads/

# 2. Installe les dépendances
pip install -r requirements.txt

# 3. Installe le navigateur
playwright install chromium

# 4. Configure tes identifiants
copy .env.example .env        # Windows
# cp .env.example .env        # Mac/Linux
# Ouvre .env et remplis NG_USERNAME, NG_PASSWORD (et CAPTCHA_APIKEY si tu veux)
```

---

## Utilisation

### Le 1er du mois — lance le bot pour tout le mois :
```
python run_monthly.py
```
Laisse la fenêtre ouverte (ou mets-le en arrière-plan). Il tourne tout seul jusqu'à la fin du mois.

### Vote unique (pour tester) :
```
python vote_bot.py
```

---

## CAPTCHA (optionnel mais recommandé)

Si le site affiche un CAPTCHA, le bot a besoin d'une clé 2captcha :
1. Crée un compte sur https://2captcha.com
2. Recharge 3€ (suffisant pour plusieurs mois)
3. Copie ta clé API dans `.env` → `CAPTCHA_APIKEY=ta_clé`

Sans clé, le bot tente de voter quand même mais peut échouer sur les CAPTCHAs.

---

## Logs

- `vote_bot.log`    — log de chaque session de vote
- `scheduler.log`   — log de la boucle mensuelle
- `vote_page_*.html` — dump HTML si le bot ne trouve pas les boutons (pour debug)

---

## Mode invisible (headless)

Par défaut le navigateur est **visible**. Pour le cacher complètement :
Ouvre `vote_bot.py`, ligne `headless=False` → change en `headless=True`.
