"""
config.py — Paramètres centraux du screener Phronesis
======================================================
Toutes les constantes métier, seuils des 4 piliers et paramètres
de connexion sont regroupés ici pour simplifier la maintenance.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONNEXION IBKR
# ─────────────────────────────────────────────
IBKR_HOST      = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT      = int(os.getenv("IBKR_PORT", 7497))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", 1))
IBKR_TIMEOUT   = 20  # secondes

# ─────────────────────────────────────────────
# CONTRAINTE DE RISQUE
# ─────────────────────────────────────────────
MAX_RISK_USD = float(os.getenv("MAX_RISK_PER_TRADE", 120))

# ─────────────────────────────────────────────
# UNIVERS DES SOUS-JACENTS À SCREENER
# ─────────────────────────────────────────────
# Watchlist par défaut (scan rapide quotidien)
WATCHLIST = [
    # ETFs indiciels — priorité absolue (Iron Condor/Wheel idéaux)
    "SPY", "QQQ", "IWM", "DIA",
    # Large caps Tech (momentum élevé, IV riche)
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    # Finance
    "JPM", "BAC", "GS", "V", "MA",
    # Secteurs ETFs
    "XLE", "XLF", "XLK", "XLV", "GLD", "TLT",
    # Growth/Momentum
    "AMD", "PLTR", "CRWD", "COIN", "SMCI",
]

# Univers complet : utiliser universe.py
# python main.py --universe full        → 1800 actifs
# python main.py --universe priority    → top 50
# python main.py --universe etf         → ETFs seulement

# Taille des batches pour le scan des grands univers
SCAN_BATCH_SIZE  = 20    # Symboles par batch
SCAN_BATCH_PAUSE = 3.0   # Secondes entre batches (anti rate-limit IBKR)

# ─────────────────────────────────────────────
# PILIER 1 — MACRO
# ─────────────────────────────────────────────
MACRO = {
    "vix_fear_threshold":    25,    # VIX > 25 → marché craintif (acheteur d'options)
    "vix_greed_threshold":   18,    # VIX < 18 → marché complaisant (vendeur d'options)
    "yield_spread_min":      0.5,   # spread 10Y-2Y > 0.5 % → courbe saine
    "spy_ma50_buffer":       0.02,  # SPY doit être à ±2 % de sa MA50
}

# ─────────────────────────────────────────────
# PILIER 2 — VALUE
# ─────────────────────────────────────────────
VALUE = {
    "pe_max":           30,    # P/E < 30
    "pb_max":            5,    # P/B < 5
    "ev_ebitda_max":    20,    # EV/EBITDA < 20
    "iv_percentile_min": 40,   # IV Percentile > 40 % pour vendeur
    "iv_percentile_max": 85,   # IV Percentile < 85 % (éviter les extrêmes)
}

# ─────────────────────────────────────────────
# PILIER 3 — INCOME (vendeur de premium)
# ─────────────────────────────────────────────
INCOME = {
    "delta_max":            0.35,  # Delta absolu ≤ 0.35 (OTM)
    "theta_min":            0.03,  # Thêta absolu ≥ 0.03 $/j
    "min_dte":              7,     # Minimum jours avant expiration
    "max_dte":             45,     # Maximum jours avant expiration (Theta sweet spot)
    "credit_min_pct":       0.20,  # Crédit ≥ 20 % de la largeur du spread
    "min_open_interest":   100,    # OI minimum par leg
    "max_bid_ask_spread":  0.15,   # Spread bid-ask ≤ 0.15 $
}

# ─────────────────────────────────────────────
# PILIER 4 — MOMENTUM
# ─────────────────────────────────────────────
MOMENTUM = {
    "rsi_oversold":      35,   # RSI < 35 → potentiel rebond (acheteur put ou bull call)
    "rsi_overbought":    65,   # RSI > 65 → potentiel retournement (vendeur call)
    "macd_signal_gap":   0.0,  # MACD doit être au-dessus de sa signal line
    "adx_trend_min":     20,   # ADX > 20 → tendance établie
    "volume_ratio_min":  1.2,  # Volume / MA20Vol > 1.2 → momentum confirmé
}

# ─────────────────────────────────────────────
# SCORING IA HEURISTIQUE — Pondérations
# ─────────────────────────────────────────────
SCORING_WEIGHTS = {
    "iv_percentile":       0.20,
    "theta_abs":           0.15,
    "delta":               0.15,
    "liquidite":           0.10,
    "risk_reward":         0.20,
    "days_to_event":       0.10,
    "moneyness_distance":  0.10,
}

SCORE_STRONG    = 70   # ≥ 70 → opportunité forte
SCORE_MODERATE  = 50   # 50-69 → modérée

# ─────────────────────────────────────────────
# SPREADS — Calibration à 120 $
# ─────────────────────────────────────────────
SPREAD = {
    "max_debit_usd":     120,   # Débit max pour spreads acheteur
    "max_margin_usd":    120,   # Marge max pour credit spreads
    "strike_step_pct":   0.02,  # Pas entre strikes : ±2 % du sous-jacent
    "min_spread_width":  1.0,   # Largeur minimale du spread (en $)
    "max_spread_width":  5.0,   # Largeur maximale du spread (en $)
}

# ─────────────────────────────────────────────
# ASSISTANT IA
# ─────────────────────────────────────────────
AI_PROVIDER        = "deepseek"    # "deepseek" ou "openai"
DEEPSEEK_API_KEY   = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL     = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL       = "gpt-4o-mini"
MAX_AI_REQUESTS    = 20           # Limite par session

# ─────────────────────────────────────────────
# STOCKAGE & LOGS
# ─────────────────────────────────────────────
DATA_DIR           = "data"
IV_CSV_PATH        = f"{DATA_DIR}/historical_iv.csv"
IV_DB_PATH         = f"{DATA_DIR}/iv_history.sqlite"
ALERTS_JSON_PATH   = f"{DATA_DIR}/alerts.json"
LOG_LEVEL          = os.getenv("LOG_LEVEL", "INFO")

# ─────────────────────────────────────────────
# GOOGLE SHEETS (optionnel)
# ─────────────────────────────────────────────
GOOGLE_SHEETS_ENABLED = os.getenv("GOOGLE_SHEETS_ENABLED", "false").lower() == "true"
GOOGLE_SHEET_ID       = os.getenv("GOOGLE_SHEET_ID", "")
