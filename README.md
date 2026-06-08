# 🧠 Phronesis Options Screener v2.0

> Screener d'options multi-modèles avec scoring IA heuristique et assistant conversationnel.  
> Développé pour le **club d'investissement Phronesis** — contrainte de risque : **120 $ par trade**.

---

## Table des matières

1. [Introduction](#introduction)
2. [Architecture](#architecture)
3. [Prérequis](#prérequis)
4. [Installation pas à pas](#installation)
5. [Configuration TWS / IB Gateway](#configuration-ibkr)
6. [Configuration du fichier .env](#configuration-env)
7. [Exécution normale](#exécution-normale)
8. [Utilisation de l'assistant IA](#assistant-ia)
9. [Interprétation du score IA](#score-ia)
10. [Déploiement programmé](#déploiement-programmé)
11. [Structure des fichiers](#structure-des-fichiers)
12. [Dépannage](#dépannage)

---

## Introduction

Le screener Phronesis analyse automatiquement un univers d'actions et d'ETFs pour identifier les **spreads d'options** offrant le meilleur rapport risque/rendement, dans une contrainte de **120 $ de risque maximum par position**.

### Les 4 Piliers de décision

| Pilier | Rôle | Fichier |
|--------|------|---------|
| **Macro** | Régime de marché (VIX, SPY vs MA50) | `models/macro_model.py` |
| **Value** | Valorisation + IV Percentile | `models/value_model.py` |
| **Income** | Filtres vendeur (delta, thêta, DTE, liquidité) | `models/income_model.py` |
| **Momentum** | RSI, MACD, ADX, Volume ratio | `models/momentum_model.py` |

Un spread n'est retenu que si **au moins 2 piliers sur 4 sont validés**.

### Scoring IA Heuristique (0-100)

Chaque opportunité reçoit un score calculé par formule pondérée (pas de ML) :

| Feature | Pondération |
|---------|-------------|
| IV Percentile | 20 % |
| Thêta absolu | 15 % |
| Delta (inverse) | 15 % |
| Liquidité (OI × bid-ask) | 10 % |
| Risk/Reward | 20 % |
| Événements (pénalité) | 10 % |
| Distance moneyness | 10 % |

- **≥ 70** → 🟢 Forte opportunité
- **50-69** → 🟡 Opportunité modérée
- **< 50** → 🔴 Opportunité faible

---

## Architecture

```
options_screener/
├── main.py                  # Orchestrateur principal
├── config.py                # Paramètres centraux
├── ib_connector.py          # Connexion IBKR (singleton)
├── data_fetcher.py          # Prix, chaînes options, VIX, fondamentaux
├── spread_builder.py        # Construction spreads calibrés 120$
├── iv_percentile_storage.py # Historique IV (SQLite + CSV)
├── scoring_ia.py            # Score heuristique 0-100
├── ai_assistant.py          # Assistant DeepSeek/OpenAI
├── models/
│   ├── macro_model.py       # Pilier Macro
│   ├── value_model.py       # Pilier Value
│   ├── income_model.py      # Pilier Income
│   └── momentum_model.py    # Pilier Momentum
├── data/
│   ├── historical_iv.csv    # Historique IV (bootstrap)
│   ├── iv_history.sqlite    # Base SQLite (auto-créée)
│   └── alerts.json          # Alertes générées
├── requirements.txt
├── .env.example
└── README.md
```

**Flux de données :**
```
TWS/Gateway
    │
    ▼
data_fetcher.py  ←──── ib_connector.py
    │
    ├──▶ models/ (4 piliers) ──▶ Filtrage go/no-go
    │
    ├──▶ iv_percentile_storage.py ──▶ Percentile IV
    │
    ├──▶ spread_builder.py ──▶ Construction + contrainte 120$
    │
    └──▶ scoring_ia.py ──▶ Score 0-100
                │
                └──▶ alerts.json ──▶ ai_assistant.py
```

---

## Prérequis

### Logiciels
- **Python 3.10+** (3.11 recommandé)
- **Interactive Brokers TWS** ou **IB Gateway** installé et configuré
- Compte IBKR avec accès aux données de marché (compte paper OK)

### Vérification Python
```bash
python --version   # Doit afficher Python 3.10+
```

---

## Installation

### Étape 1 — Cloner le projet

```bash
git clone https://github.com/votre-org/phronesis-screener.git
cd phronesis-screener
```

Ou, si vous avez reçu une archive :
```bash
unzip phronesis-screener.zip
cd phronesis-screener
```

### Étape 2 — Créer l'environnement virtuel

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Windows (cmd)
venv\Scripts\activate.bat
```

> **Vérification :** votre invite doit afficher `(venv)`.

### Étape 3 — Installer les dépendances

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note Windows :** si `ib_insync` échoue, installez d'abord `pip install pywin32`.

### Étape 4 — Configurer le fichier .env

```bash
cp .env.example .env
```

Éditez `.env` avec vos identifiants (voir section [Configuration .env](#configuration-env)).

### Étape 5 — Importer l'historique IV (bootstrap)

```bash
python main.py --import-iv data/historical_iv.csv
```

Cette commande initialise la base SQLite avec les données d'exemple.  
Remplacez `data/historical_iv.csv` par vos propres données historiques si disponible.

---

## Configuration IBKR

### TWS (Trader Workstation)

1. Ouvrir TWS et vous connecter à votre compte
2. Aller dans **Edit → Global Configuration → API → Settings**
3. Cocher **Enable ActiveX and Socket Clients**
4. Définir **Socket port** :
   - `7497` → Paper trading
   - `7496` → Live trading
5. Décocher **Read-Only API** si nécessaire (pour notre usage, Read-Only suffit)
6. Cocher **Allow connections from localhost only** (sécurité)
7. Cliquer **OK** et redémarrer TWS

### IB Gateway (recommandé en production)

1. Télécharger IB Gateway sur [ibkr.com](https://www.interactivebrokers.com)
2. Lancer IB Gateway, sélectionner le mode `API`
3. Port par défaut :
   - `4002` → Paper
   - `4001` → Live
4. Configurer dans `.env` : `IBKR_PORT=4002`

### Vérification de la connexion

```bash
python -c "from ib_connector import IBConnector; c = IBConnector(); print('OK' if c.connect() else 'ECHEC'); c.disconnect()"
```

---

## Configuration .env

Copiez `.env.example` en `.env` et remplissez :

```bash
# Connexion IBKR
IBKR_HOST=127.0.0.1
IBKR_PORT=7497          # TWS paper
IBKR_CLIENT_ID=1        # Doit être unique si plusieurs connexions

# DeepSeek (assistant IA — recommandé)
DEEPSEEK_API_KEY=sk-votre-cle-deepseek

# OpenAI (fallback)
OPENAI_API_KEY=sk-votre-cle-openai

# Paramètres
MAX_RISK_PER_TRADE=120
LOG_LEVEL=INFO           # DEBUG pour plus de détails
```

**Obtenir une clé DeepSeek :** https://platform.deepseek.com/  
**Obtenir une clé OpenAI :** https://platform.openai.com/api-keys

---

## Exécution normale

### Scan complet (watchlist par défaut)

```bash
python main.py
```

### Scan ciblé sur quelques symboles

```bash
python main.py --symbols AAPL MSFT SPY NVDA
```

### Sortie console typique

```
╔══════════════════════════════════════════════════════════════╗
║   🧠 PHRONESIS OPTIONS SCREENER — v2.0                      ║
╚══════════════════════════════════════════════════════════════╝

──────────── 🔌 Connexion IBKR ────────────
✅ Connecté à IBKR — serverVersion=175

──────────── 🌍 Pilier 1 — Analyse Macro ────────────
Macro [🟡 NEUTRAL] score=0.52 | VIX=18.3 | SPY vs MA50=+1.2%

──────────── [1/3] 📊 AAPL ────────────
  🔍 Pilier 2 — Value
    Value [🟢 VALUE] score=0.74 | IV%ile=68% | PE=28.4

  📈 Pilier 4 — Momentum
    Momentum [🟢 BULLISH] score=0.71 | Biais=seller | RSI=58.2

  💰 Pilier 3 — Income
    Income [🟢] score=0.68 | 12 candidat(s)

  🏗️  Construction des spreads…

  ┌─ AAPL — Bull Put Spread 💰
  │  Expiry : 20240119 (J-21)
  │  Legs   : P170 / P165
  │  Spot   : 182.50  |  Break-even : 168.45
  │  Crédit net  : 1.55$ | Max profit: 155$
  │  Risque max  : 345$ → 🔧 Ajusté P175/P173 → Risque: 112$  ✅
  ├─   Score IA : 78/100  [████████████████░░░░]  (🟢 Forte opportunité)
  │  ├─ IV Percentile   : 68%
  │  ├─ Thêta           : 0.089 $/j
  │  ├─ Delta           : 0.18
  │  ├─ Liquidité       : Excellente
  │  ├─ Risk/Reward     : 0.55
  │  ├─ Événement       : Aucun connu
  │  └─ Moneyness       : 4.1% OTM
  │  💡 IV élevée → vente de premium favorisée | Risk/reward attractif
  └───────────────────────────────────────────────────────────

──────────── 📋 RÉSUMÉ ────────────
  ✅ 3 opportunité(s) détectée(s) :
   1. AAPL   bull_put     Exp:20240119 DTE:21j  Risque: 112$  Score: 78/100 🟢 Forte
   2. SPY    bear_call    Exp:20240119 DTE:21j  Risque: 98$   Score: 71/100 🟢 Forte
   3. MSFT   bull_put     Exp:20240126 DTE:28j  Risque: 115$  Score: 65/100 🟡 Modérée
```

---

## Assistant IA

### Mode question unique

```bash
# Question générale
python main.py --ask "C'est quoi le thêta en options ?"

# Question sur la dernière alerte
python main.py --ask "Pourquoi le score de cette opportunité est-il de 78 ?"

# Avec fichier d'alertes spécifique
python main.py --ask "Analyse ce spread" --alert data/alerts.json
```

### Mode conversationnel interactif

```bash
python main.py --chat

# Avec contexte d'alerte préchargé
python main.py --chat --alert data/alerts.json
```

**Commandes disponibles dans le chat :**
- `exit` ou `quit` → Quitter
- `reset` → Effacer l'historique
- `context` → Afficher l'alerte en contexte

### Exemples de questions

```
[0/20] Votre question : Explique-moi le bull put spread
[0/20] Votre question : Pourquoi cette opportunité a un score de 78 ?
[0/20] Votre question : Quel est le risque si AAPL chute de 5% ?
[0/20] Votre question : Comment choisir entre un crédit spread et un débit spread ?
[0/20] Votre question : C'est quoi l'IV crush post-earnings ?
```

---

## Score IA

### Formule (rappel)

```python
score = (
    0.20 * iv_percentile_norm +          # IV dans la fenêtre 40-85%
    0.15 * theta_abs_norm +              # Thêta ≥ 0.03 $/j
    0.15 * (1 - delta_norm) +            # Delta faible (OTM)
    0.10 * liquidite_norm +              # OI × (1 - bid-ask)
    0.20 * min(credit/max_risk, 1.0) +   # Risk/reward
    0.10 * (1 - event_penalty) +         # Pas d'événement imminent
    0.10 * (1 - moneyness_dist_norm)     # Distance au spot
) × 100
```

### Interprétation

| Score | Label | Action suggérée |
|-------|-------|----------------|
| 70-100 | 🟢 Forte opportunité | Analyser et potentiellement trader |
| 50-69 | 🟡 Modérée | Surveiller, condition partielle |
| 0-49 | 🔴 Faible | Éviter ou approfondir l'analyse |

### Calcul de score manuel (test)

```bash
python main.py --score '{"iv_percentile":75,"theta_abs":0.07,"delta":0.15,"open_interest":800,"bid_ask_spread":0.04,"credit_received":1.20,"max_risk":3.80,"spot":182.5,"strike":175}'
```

---

## Déploiement programmé

### Option A — Cron Linux/macOS

```bash
crontab -e
```

Ajouter :
```cron
# Scan tous les jours ouvrés à 9h30 (heure de New York = 14h30 UTC)
30 14 * * 1-5 cd /chemin/vers/options_screener && /chemin/venv/bin/python main.py >> logs/screener.log 2>&1

# Scan à l'ouverture ET à mi-session
30 14 * * 1-5 cd /chemin/vers/options_screener && /chemin/venv/bin/python main.py --symbols SPY QQQ IWM >> logs/screener.log 2>&1
00 19 * * 1-5 cd /chemin/vers/options_screener && /chemin/venv/bin/python main.py >> logs/screener.log 2>&1
```

Créer le dossier logs :
```bash
mkdir -p logs
```

### Option B — Tâche planifiée Windows

Ouvrir le **Planificateur de tâches** Windows :
1. Nouvelle tâche → Action → Démarrer un programme
2. Programme : `C:\chemin\venv\Scripts\python.exe`
3. Arguments : `main.py`
4. Dossier de démarrage : `C:\chemin\options_screener`
5. Déclencheur : quotidien, 9h30, jours ouvrés

### Option C — Script Python avec schedule

Créer `scheduler.py` :
```python
import schedule
import time
import subprocess

def run_screener():
    subprocess.run(["python", "main.py"])

# 9h30 et 15h30 (heure de Paris)
schedule.every().monday.at("09:30").do(run_screener)
schedule.every().tuesday.at("09:30").do(run_screener)
# ... etc.

while True:
    schedule.run_pending()
    time.sleep(60)
```

```bash
python scheduler.py
```

---

## Structure des fichiers

| Fichier | Description |
|---------|-------------|
| `main.py` | Point d'entrée, argparse, orchestration |
| `config.py` | Tous les paramètres (seuils, watchlist, API) |
| `ib_connector.py` | Singleton de connexion IBKR |
| `data_fetcher.py` | Récupération prix, chaînes options, VIX |
| `models/macro_model.py` | VIX + SPY MA50 |
| `models/value_model.py` | P/E, P/B + IV Percentile |
| `models/income_model.py` | Filtres delta, thêta, DTE, liquidité |
| `models/momentum_model.py` | RSI, MACD, ADX, Volume |
| `spread_builder.py` | Bull call/Bear put/Bull put/Bear call spreads |
| `iv_percentile_storage.py` | SQLite + CSV pour l'historique IV |
| `scoring_ia.py` | Formule de score heuristique |
| `ai_assistant.py` | Client DeepSeek/OpenAI + REPL |
| `data/historical_iv.csv` | Données d'amorçage (AAPL, SPY, NVDA) |
| `data/iv_history.sqlite` | Base SQLite auto-créée au premier run |
| `data/alerts.json` | Alertes générées (cumulatives) |

---

## Dépannage

### ❌ `Connection refused` à IBKR

**Cause :** TWS/Gateway pas démarré ou mauvais port.

```bash
# Vérifier le port
IBKR_PORT=7497   # TWS paper
IBKR_PORT=7496   # TWS live
IBKR_PORT=4002   # IB Gateway paper
IBKR_PORT=4001   # IB Gateway live
```

**Solution :**
1. Vérifier que TWS est ouvert et connecté
2. Dans TWS : Edit → Global Configuration → API → Settings → Socket port
3. Vérifier que `IBKR_HOST=127.0.0.1` dans `.env`

---

### ❌ `No market data permissions`

**Cause :** Votre compte IBKR n'a pas l'abonnement aux données en temps réel.

**Solution :**
- Utiliser un compte paper (données simulées gratuites)
- Ou souscrire aux données US sur le portail IBKR

---

### ❌ `ImportError: No module named 'ib_insync'`

**Cause :** Environnement virtuel non activé ou dépendances non installées.

```bash
source venv/bin/activate    # Linux/macOS
.\venv\Scripts\Activate.ps1  # Windows

pip install -r requirements.txt
```

---

### ❌ `IV Percentile non calculable`

**Cause :** Historique IV insuffisant (< 20 jours).

**Solution :**
```bash
# Importer le CSV d'exemple
python main.py --import-iv data/historical_iv.csv

# Ou lancer le screener plusieurs jours consécutifs
# (chaque run sauvegarde l'IV du jour)
```

---

### ❌ Assistant IA : `No API key`

**Cause :** Clé API manquante dans `.env`.

**Solution :**
```bash
# Vérifier le .env
cat .env | grep API_KEY

# Tester la clé manuellement
python -c "from ai_assistant import quick_ask; print(quick_ask('Test'))"
```

---

### ❌ `pandas_ta` erreurs d'importation

```bash
pip uninstall pandas_ta
pip install pandas_ta==0.3.14b0
```

---

### Mode debug complet

```bash
LOG_LEVEL=DEBUG python main.py --symbols AAPL 2>&1 | tee debug.log
```

---

### Réinitialiser la base de données

```bash
rm data/iv_history.sqlite
python main.py --import-iv data/historical_iv.csv
```

---

## Notes importantes

### Responsabilité
Ce screener est un **outil pédagogique et d'aide à la décision** pour le club Phronesis. Il ne constitue pas un conseil en investissement. Tout trade doit être validé par les membres du club avant exécution.

### Mode paper trading
**Toujours tester avec un compte paper** avant de connecter un compte réel. Utiliser `IBKR_PORT=7497` (TWS paper).

### Rate limits IBKR
L'API IBKR limite les requêtes à ~50/s. Le screener inclut des délais (`time.sleep`) pour respecter ces limites. Ne pas réduire ces délais sans comprendre les conséquences.

### Mise à jour des clés API
Les clés API ne doivent **jamais** être committées dans Git. Le fichier `.env` est dans `.gitignore` par convention. Vérifier :
```bash
echo ".env" >> .gitignore
git rm --cached .env 2>/dev/null || true
```

---

## Contact & Contribution

Pour toute question technique, contacter l'équipe tech du club Phronesis.  
Les contributions (nouveaux modèles, filtres, stratégies) sont les bienvenues via Pull Request.

---

*Phronesis Options Screener — Conçu pour le club Phronesis*  
*"La phronésis est la sagesse pratique qui permet d'agir justement."*

---

## Mise à jour v3.0 — Nouveautés

### 1. Recommandation Stratégique (12 stratégies du cours)

Le screener recommande maintenant **automatiquement** la stratégie optimale pour chaque opportunité, basée sur la matrice IV Rank × Momentum du cours Phronesis :

| IV Rank | Momentum | Stratégie recommandée | Module |
|---------|----------|----------------------|--------|
| < 20 | Haussier | Long Call | 3.2 |
| < 20 | Baissier | Long Put | 3.2 |
| < 20 | Événement | Long Straddle | 3.3 |
| 20–35 | Haussier | Bull Call Spread | 4.1 |
| 20–35 | Baissier | Bear Put Spread | 4.2 |
| 35–60 | Haussier | Bull Put Spread (crédit) | 4 |
| 35–60 | Baissier | Bear Call Spread (crédit) | 4 |
| 35–60 | Neutre | Iron Condor | 4.3 |
| > 60 | Haussier | Bull Put Spread / CSP | 4.3/4.4 |
| > 60 | Neutre | Iron Condor large | 4.3 |
| Long terme | Haussier | LEAPS Call | 5.1 |
| Détient actions | Income | Covered Call / Wheel | 5.2/5.3 |

### 2. Fiche de Décision (module decision_engine.py)

Chaque opportunité génère une **fiche de décision complète** avec :
- Score de conviction combiné (IA + recommandation stratégique)
- Décision GO / NO-GO automatique
- Prix limite d'entrée suggéré
- Take Profit et Stop Loss précalculés
- Trigger de roll automatique
- Checklist pré-trade du Module 9.3 (auto-évaluée)
- Probabilité de profit estimée

### 3. Univers 1800+ Actifs (module universe.py)

```bash
# Scan complet 1800 actifs
python main.py --universe full

# Top 100 prioritaires (les plus liquides)
python main.py --universe priority --max 100

# ETFs uniquement (Iron Condor idéaux)
python main.py --universe etf

# S&P 500 Large Caps
python main.py --universe sp500

# Statistiques sur l'univers
python main.py --universe-stats
```

Segments couverts :
- **S&P 500 Mega/Large Caps** (343 tickers, priorité 1)
- **NASDAQ Growth/Tech** (48 tickers)
- **Mid Caps S&P 400** (40 tickers)
- **ETFs Macro** (SPY, QQQ, TLT, GLD…) (29 tickers)
- **ETFs Sectoriels** (XLE, XLK, ARKK, SMH…) (30 tickers)
- **ETFs Internationaux** (EEM, FXI, KWEB…) (11 tickers)
- **Small Caps Dynamiques** (27 tickers)

### 4. Nouvelles commandes

```bash
# Lister toutes les stratégies disponibles
python main.py --strategies

# Détails d'une stratégie spécifique
python main.py --strategy-info iron_condor
python main.py --strategy-info bull_put_spread
python main.py --strategy-info leaps_call

# Afficher les fiches de décision du dernier scan
python main.py --decide

# Dans le chat IA :
strategies                 # Liste des stratégies
strategy iron_condor       # Détails Iron Condor
strategy wheel_strategy    # Détails Wheel Strategy
```

### 5. Scan par batches (anti rate-limit IBKR)

Pour les grands univers, le screener scanne par **batches de 20 symboles** avec une pause de 3 secondes entre chaque batch. Pour 1800 actifs, prévoir environ 4–5 heures de scan complet (recommandé en tâche de nuit).

```bash
# Scan nocturne recommandé (cron 23h00)
0 23 * * 1-5 cd /path && python main.py --universe full >> logs/scan.log 2>&1
```

