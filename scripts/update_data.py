"""
update_data.py — Scan périodique pour générer les opportunités (version CI rapide)
Utilise uniquement yfinance, pas d'IBKR, et seulement quelques symboles.
"""

import json
import logging
import os
import sys
from datetime import datetime

# Ajouter le chemin racine
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Forcer l'utilisation de yfinance uniquement (pas d'IBKR)
os.environ["DISABLE_IBKR"] = "true"

import pandas as pd
import yfinance as yf
from spread_builder import SpreadBuilder
from models.income_model import IncomeModel
from scoring_ia import score_from_dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Liste réduite pour CI
SYMBOLS_CI = ['SPY', 'QQQ']  # seulement 2 symboles

def get_spot_yfinance(symbol: str) -> float:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period='1d')
    if not hist.empty:
        return float(hist['Close'].iloc[-1])
    info = ticker.info
    return float(info.get('regularMarketPrice', info.get('currentPrice', 0)))

def get_option_chain_yfinance(symbol: str, days_min: int = 7, days_max: int = 60):
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
                rows.append({
                    'symbol': symbol,
                    'expiry': exp_str.replace('-', ''),
                    'dte': dte,
                    'strike': row['strike'],
                    'right': right,
                    'bid': row['bid'] if not pd.isna(row['bid']) else 0,
                    'ask': row['ask'] if not pd.isna(row['ask']) else 0,
                    'iv': row['impliedVolatility'] if not pd.isna(row['impliedVolatility']) else 0,
                    'delta': row.get('delta', 0),
                    'theta': row.get('theta', 0),
                    'open_interest': row['openInterest'] if not pd.isna(row['openInterest']) else 0,
                    'volume': row['volume'] if not pd.isna(row['volume']) else 0,
                })
    df = pd.DataFrame(rows)
    if not df.empty:
        spot = get_spot_yfinance(symbol)
        df['spot'] = spot
    return df

def run_scan_and_save():
    all_decisions = []
    for symbol in SYMBOLS_CI:
        logger.info(f"Scan {symbol}...")
        spot = get_spot_yfinance(symbol)
        chain = get_option_chain_yfinance(symbol)
        if chain.empty:
            logger.warning(f"Pas d'options pour {symbol}")
            continue
        
        # Income filter simplifié
        income = IncomeModel()
        income_result = income.analyze(chain)
        if not income_result.passed:
            logger.info(f"{symbol} ne passe pas le filtre income")
            continue
        
        # Construction des spreads
        builder = SpreadBuilder()
        candidates = builder.build_all(
            symbol, chain,
            momentum_bias='seller',
            iv_percentile=50,
            days_to_event=None
        )
        if not candidates:
            logger.info(f"Aucun spread pour {symbol}")
            continue
        
        # Scoring
        for c in candidates:
            score_data = {
                "iv_percentile": 50,
                "theta_abs": abs(c.leg1_theta) if hasattr(c, 'leg1_theta') else 0.05,
                "delta": abs(c.leg1_delta) if hasattr(c, 'leg1_delta') else 0.2,
                "open_interest": min(c.leg1_oi, c.leg2_oi),
                "bid_ask_spread": (c.leg1_ask - c.leg1_bid) + (c.leg2_ask - c.leg2_bid) / 2,
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
                "score": score_obj.score,
                "label": score_obj.label,
            })
    
    # Sauvegarde
    os.makedirs("data", exist_ok=True)
    with open("data/opportunities.json", "w") as f:
        json.dump(all_decisions, f, indent=2)
    logger.info(f"Sauvegardé {len(all_decisions)} opportunités")

if __name__ == "__main__":
    run_scan_and_save()