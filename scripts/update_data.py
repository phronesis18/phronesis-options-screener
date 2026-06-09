# scripts/update_data.py (version allégée sans IncomeModel)
"""
update_data.py — Scan périodique pour générer les opportunités (version allégée)
Lit la watchlist depuis data/watchlist.json (sinon liste par défaut).
Ne dépend pas de IncomeModel, utilise un filtre simple.
"""

import json
import logging
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DISABLE_IBKR"] = "true"

import pandas as pd
import yfinance as yf
from spread_builder import SpreadBuilder
from scoring_ia import score_from_dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
DAYS_MIN = 7
DAYS_MAX = 730

def get_watchlist():
    watchlist_path = "data/watchlist.json"
    if os.path.exists(watchlist_path):
        try:
            with open(watchlist_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    logger.info(f"Watchlist chargée : {len(data)} symboles")
                    return data
        except Exception as e:
            logger.warning(f"Erreur lecture watchlist : {e}")
    logger.info(f"Watchlist par défaut : {DEFAULT_SYMBOLS}")
    return DEFAULT_SYMBOLS

def get_spot_yfinance(symbol: str) -> float:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period='1d')
    if not hist.empty:
        return float(hist['Close'].iloc[-1])
    info = ticker.info
    return float(info.get('regularMarketPrice', info.get('currentPrice', 0)))

def get_option_chain_yfinance(symbol: str, days_min: int = DAYS_MIN, days_max: int = DAYS_MAX):
    ticker = yf.Ticker(symbol)
    expirations = ticker.options
    if not expirations:
        return pd.DataFrame()
    today = datetime.now().date()
    rows = []
    for exp_str in expirations:
        exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
        dte = (exp_date - today).days
        if dte < days_min or dte > days_max:
            continue
        try:
            chain = ticker.option_chain(exp_str)
        except:
            continue
        for right, df in [('C', chain.calls), ('P', chain.puts)]:
            for _, row in df.iterrows():
                bid = row['bid'] if not pd.isna(row['bid']) else 0.0
                ask = row['ask'] if not pd.isna(row['ask']) else 0.0
                iv = row['impliedVolatility'] if not pd.isna(row['impliedVolatility']) else 0.0
                open_interest = row['openInterest'] if not pd.isna(row['openInterest']) else 0
                rows.append({
                    'symbol': symbol,
                    'expiry': exp_str.replace('-', ''),
                    'dte': dte,
                    'strike': row['strike'],
                    'right': right,
                    'bid': bid,
                    'ask': ask,
                    'iv': iv,
                    'open_interest': open_interest,
                })
    df = pd.DataFrame(rows)
    if not df.empty:
        spot = get_spot_yfinance(symbol)
        df['spot'] = spot
    return df

def run_scan_and_save():
    symbols = get_watchlist()
    all_decisions = []
    total = len(symbols)
    for idx, symbol in enumerate(symbols, 1):
        logger.info(f"Scan {symbol} ({idx}/{total})...")
        spot = get_spot_yfinance(symbol)
        chain = get_option_chain_yfinance(symbol, days_min=DAYS_MIN, days_max=DAYS_MAX)
        if chain.empty:
            logger.warning(f"Pas d'options pour {symbol}")
            continue

        # Filtre basique : au moins 10 options et spread bid-ask moyen < 0.50$
        if len(chain) < 10:
            logger.info(f"{symbol} : trop peu d'options ({len(chain)})")
            continue
        avg_spread = (chain['ask'] - chain['bid']).mean()
        if avg_spread > 0.50:
            logger.info(f"{symbol} : spread trop large ({avg_spread:.2f}$)")
            continue

        builder = SpreadBuilder()
        # On utilise des valeurs par défaut pour les grecques manquantes
        candidates = builder.build_all(
            symbol, chain,
            momentum_bias='seller',
            iv_percentile=50,
            days_to_event=None
        )
        if not candidates:
            logger.info(f"Aucun spread pour {symbol}")
            continue

        for c in candidates:
            # Récupérer les valeurs nécessaires au scoring
            leg1_delta = getattr(c, 'leg1_delta', 0.2)
            leg1_theta = getattr(c, 'leg1_theta', 0.05)
            leg1_oi = getattr(c, 'leg1_oi', 500)
            leg2_oi = getattr(c, 'leg2_oi', 500)
            min_oi = min(leg1_oi, leg2_oi) if leg1_oi and leg2_oi else 100
            ba_spread = (c.leg1_ask - c.leg1_bid) + (c.leg2_ask - c.leg2_bid) / 2
            score_data = {
                "iv_percentile": 50,
                "theta_abs": abs(leg1_theta),
                "delta": abs(leg1_delta),
                "open_interest": min_oi,
                "bid_ask_spread": ba_spread,
                "credit_received": c.net_credit,
                "max_risk": c.risk_usd,
                "spot": spot,
                "strike": c.leg1_strike,
                "symbol": symbol,
                "strategy": c.strategy,
            }
            score_obj = score_from_dict(score_data)
            all_decisions.append({
                "symbol": symbol,
                "strategy": c.strategy,
                "strikes": f"{c.leg1_strike:.0f}/{c.leg2_strike:.0f}",
                "expiry": c.expiry,
                "dte": c.dte,
                "credit": c.net_credit,
                "risk": c.risk_usd,
                "profit": round(c.max_profit * 100, 2) if hasattr(c, 'max_profit') else 0,
                "iv_rank": f"{score_obj.iv_percentile:.0f}%" if hasattr(score_obj, 'iv_percentile') else "N/A",
                "score": score_obj.score,
                "label": score_obj.label,
                "delta": round(leg1_delta, 2),
                "theta": round(leg1_theta, 2),
            })
    os.makedirs("data", exist_ok=True)
    with open("data/opportunities.json", "w") as f:
        json.dump(all_decisions, f, indent=2)
    logger.info(f"Sauvegardé {len(all_decisions)} opportunités")

if __name__ == "__main__":
    run_scan_and_save()