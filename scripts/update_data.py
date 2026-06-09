"""
update_data.py — Scan périodique pour générer les opportunités
Intègre le calcul des IV ATM, OTM, ITM à partir des options.
"""

import json
import logging
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DISABLE_IBKR"] = "true"

import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import norm
from spread_builder import SpreadBuilder
from scoring_ia import score_from_dict
from iv_percentile_storage import save_iv, compute_iv_percentile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
DAYS_MIN = 7
DAYS_MAX = 1098

def get_watchlist():
    path = "data/watchlist.json"
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    logger.info(f"Watchlist chargée : {len(data)} symboles")
                    return data
        except:
            pass
    return DEFAULT_SYMBOLS

def get_spot_yfinance(symbol: str) -> float:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period='1d')
    if not hist.empty:
        return float(hist['Close'].iloc[-1])
    info = ticker.info
    return float(info.get('regularMarketPrice', info.get('currentPrice', 0)))

def get_option_chain_yfinance(symbol: str, days_min: int, days_max: int):
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
                    'strike': row['strike'],
                    'right': right,
                    'bid': row['bid'] if not pd.isna(row['bid']) else 0.0,
                    'ask': row['ask'] if not pd.isna(row['ask']) else 0.0,
                    'last': row['lastPrice'] if not pd.isna(row['lastPrice']) else 0.0,
                    'iv': row['impliedVolatility'] if not pd.isna(row['impliedVolatility']) else 0.0,
                    'open_interest': row['openInterest'] if not pd.isna(row['openInterest']) else 0,
                    'volume': row['volume'] if not pd.isna(row['volume']) else 0,
                    'dte': dte,
                })
    df = pd.DataFrame(rows)
    if not df.empty:
        spot = get_spot_yfinance(symbol)
        df['spot'] = round(spot, 2)
    return df

def add_greeks_bs(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Ajoute delta, theta, gamma, vega via Black-Scholes."""
    for col in ['strike', 'dte', 'spot', 'iv', 'right']:
        if col not in df.columns:
            if col == 'spot':
                df['spot'] = get_spot_yfinance(symbol) or 100.0
            elif col == 'iv':
                df['iv'] = 0.3
            elif col == 'dte':
                df['dte'] = 30
            else:
                df[col] = 0
    T = df['dte'].astype(float) / 365.0
    T = T.clip(lower=1e-6)
    S = df['spot'].astype(float)
    K = df['strike'].astype(float)
    sigma = df['iv'].astype(float).fillna(0.3)
    is_call = (df['right'] == 'C').values
    r = 0.05
    q = 0.0
    with np.errstate(divide='ignore', invalid='ignore'):
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
    delta_call = norm.cdf(d1)
    delta_put = norm.cdf(d1) - 1
    df['delta'] = np.where(is_call, delta_call, delta_put)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    df['gamma'] = gamma
    theta_call = - (S * sigma * norm.pdf(d1)) / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * norm.cdf(d2)
    theta_put = - (S * sigma * norm.pdf(d1)) / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm.cdf(-d2)
    df['theta'] = np.where(is_call, theta_call, theta_put) / 365.0
    vega = (S * norm.pdf(d1) * np.sqrt(T)) / 100
    df['vega'] = vega
    # remplacer les NaN par des valeurs par défaut
    df['delta'] = df['delta'].fillna(0.2)
    df['theta'] = df['theta'].fillna(-0.05)
    df['gamma'] = df['gamma'].fillna(0.01)
    df['vega'] = df['vega'].fillna(0.1)
    return df

def compute_iv_metrics(chain: pd.DataFrame, spot: float) -> dict:
    """
    Calcule IV ATM, OTM, ITM à partir du DataFrame des options (après grecques).
    OTM : delta entre 0.15 et 0.30 (calls) ou -0.15 à -0.30 (puts)
    ITM : delta > 0.70 ou < -0.70
    ATM : l'option avec le strike le plus proche du spot.
    """
    metrics = {"iv_atm": None, "iv_otm": None, "iv_itm": None}
    if chain.empty or 'iv' not in chain.columns:
        return metrics
    # IV ATM (strike le plus proche du spot)
    chain['strike_diff'] = (chain['strike'] - spot).abs()
    atm_row = chain.loc[chain['strike_diff'].idxmin()]
    metrics["iv_atm"] = round(atm_row['iv'], 4) if pd.notna(atm_row['iv']) else None

    # Filtrer OTM et ITM par delta
    otm = chain[(abs(chain['delta']) >= 0.15) & (abs(chain['delta']) <= 0.30)]
    itm = chain[abs(chain['delta']) >= 0.70]
    if not otm.empty:
        metrics["iv_otm"] = round(otm['iv'].mean(), 4)
    if not itm.empty:
        metrics["iv_itm"] = round(itm['iv'].mean(), 4)
    return metrics

def run_scan_and_save():
    symbols = get_watchlist()
    all_decisions = []
    total = len(symbols)
    for idx, symbol in enumerate(symbols, 1):
        logger.info(f"Scan {symbol} ({idx}/{total})...")
        chain = get_option_chain_yfinance(symbol, DAYS_MIN, DAYS_MAX)
        if chain.empty:
            logger.warning(f"Pas d'options pour {symbol}")
            continue
        if len(chain) < 10:
            logger.info(f"{symbol} : trop peu d'options ({len(chain)})")
            continue
        avg_spread = (chain['ask'] - chain['bid']).mean()
        if avg_spread > 0.50:
            logger.info(f"{symbol} : spread trop large ({avg_spread:.2f}$)")
            continue

        # Calcul des grecques
        chain = add_greeks_bs(chain, symbol)
        spot = chain['spot'].iloc[0] if 'spot' in chain.columns else get_spot_yfinance(symbol)

        # Métriques IV
        iv_metrics = compute_iv_metrics(chain, spot)
        iv_atm = iv_metrics["iv_atm"]
        iv_otm = iv_metrics["iv_otm"]
        iv_itm = iv_metrics["iv_itm"]

        # IV Rank à partir de l'IV ATM (si disponible)
        iv_pct = 50
        if iv_atm is not None:
            save_iv(symbol, iv_atm)
            iv_pct = compute_iv_percentile(symbol, iv_atm)
            if iv_pct is None:
                iv_pct = 50
        logger.info(f"{symbol} IV ATM={iv_atm} OTM={iv_otm} ITM={iv_itm} Rank={iv_pct:.0f}%")

        # Construction des spreads
        builder = SpreadBuilder()
        candidates = builder.build_all(
            symbol, chain,
            momentum_bias='seller',
            iv_percentile=iv_pct,
            days_to_event=None
        )
        if not candidates:
            logger.info(f"Aucun spread pour {symbol}")
            continue

        for c in candidates:
            leg1_delta = getattr(c, 'leg1_delta', 0.2)
            leg1_theta = getattr(c, 'leg1_theta', 0.05)
            leg1_oi = getattr(c, 'leg1_oi', 500)
            leg2_oi = getattr(c, 'leg2_oi', 500)
            min_oi = min(leg1_oi, leg2_oi) if leg1_oi and leg2_oi else 100
            ba_spread = (c.leg1_ask - c.leg1_bid) + (c.leg2_ask - c.leg2_bid) / 2
            score_data = {
                "iv_percentile": iv_pct,
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
                "credit": round(c.net_credit, 2),
                "risk": round(c.risk_usd, 2),
                "profit": round(c.max_profit * 100, 2) if hasattr(c, 'max_profit') else 0,
                "iv_rank": f"{iv_pct:.0f}%",
                "iv_atm": iv_atm,
                "iv_otm": iv_otm,
                "iv_itm": iv_itm,
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