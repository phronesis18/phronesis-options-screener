"""
data_fetcher.py — Récupération des données avec fallback multi-sources
et calcul robuste des grecques (valeurs arrondies à 2 décimales)
"""

import logging
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import norm

from ib_insync import (
    IB, Stock, Index, Option, Contract,
    util, BarData
)

import config
from ib_connector import IBConnector

load_dotenv()
logger = logging.getLogger(__name__)

# Clés API
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")

# Fonction utilitaire d'arrondi
def _round_df(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Arrondit les colonnes spécifiées à 2 décimales."""
    for col in cols:
        if col in df.columns:
            df[col] = df[col].round(2)
    return df

# ──────────────────────────────────────────────────────────────
# Helpers IBKR
# ──────────────────────────────────────────────────────────────
def _get_ib() -> IB:
    connector = IBConnector()
    ib = connector.ib
    if ib.isConnected():
        ib.reqMarketDataType(3)
    return ib

def _qualify(contract: Contract) -> Optional[Contract]:
    ib = _get_ib()
    try:
        qualified = ib.qualifyContracts(contract)
        return qualified[0] if qualified else None
    except Exception as e:
        logger.warning(f"Qualification échouée {contract.symbol}: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 1. Spot
# ──────────────────────────────────────────────────────────────
def get_spot_price(symbol: str, exchange: str = "SMART",
                   currency: str = "USD") -> Optional[float]:
    ib = _get_ib()
    contract = Stock(symbol, exchange, currency)
    contract = _qualify(contract)
    if contract:
        try:
            ticker = ib.reqMktData(contract, "", False, False)
            ib.sleep(2)
            price = ticker.last or ticker.close or ticker.bid
            ib.cancelMktData(contract)
            if price and price > 0:
                return round(float(price), 2)
        except Exception as e:
            logger.debug(f"IBKR spot échoué: {e}")

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='1d')
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            return round(price, 2)
        info = ticker.info
        price = info.get('regularMarketPrice', info.get('currentPrice'))
        if price:
            return round(float(price), 2)
    except Exception as e:
        logger.debug(f"yfinance spot échoué: {e}")
    return None

def get_historical_bars(symbol: str, duration: str = "1 Y",
                        bar_size: str = "1 day",
                        exchange: str = "SMART",
                        currency: str = "USD") -> Optional[pd.DataFrame]:
    """Récupère l'historique OHLCV (fallback yfinance si IBKR indisponible)."""
    # Tentative IBKR (simplifiée)
    # Pour l'instant, on retourne un DataFrame vide pour éviter l'erreur
    # Mais on peut implémenter via yfinance
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=duration.replace(' ', ''))
        if not hist.empty:
            return hist
    except:
        pass
    return None


# ──────────────────────────────────────────────────────────────
# 2. Fondamentaux (inchangé)
# ──────────────────────────────────────────────────────────────
def _fundamentals_from_alpha_vantage(symbol: str) -> Dict:
    if not ALPHA_VANTAGE_API_KEY:
        return {}
    try:
        url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        pe = data.get("TrailingPE")
        pb = data.get("PriceToBookRatio")
        return {"pe": float(pe) if pe else None, "pb": float(pb) if pb else None}
    except:
        return {}

def _fundamentals_from_ibkr(symbol: str) -> Dict:
    ib = _get_ib()
    contract = Stock(symbol, "SMART", "USD")
    contract = _qualify(contract)
    if not contract:
        return {}
    try:
        xml_data = ib.reqFundamentalData(contract, "ReportSnapshot")
        if not xml_data:
            return {}
        import re
        def _extract(tag):
            pattern = rf'<{tag}[^>]*>([\d.]+)</{tag}>'
            match = re.search(pattern, xml_data, re.IGNORECASE)
            return float(match.group(1)) if match else None
        return {
            "pe": _extract("PERatio") or _extract("TTMPeExclXor"),
            "pb": _extract("PriceToBvPerShare"),
        }
    except:
        return {}

def _fundamentals_from_yfinance(symbol: str) -> Dict:
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "pe": info.get("trailingPE") or info.get("forwardPE"),
            "pb": info.get("priceToBook"),
        }
    except:
        return {}

def get_fundamentals(symbol: str) -> Dict[str, Optional[float]]:
    data = _fundamentals_from_alpha_vantage(symbol)
    if data.get("pe") is not None and data.get("pb") is not None:
        return data
    data = _fundamentals_from_ibkr(symbol)
    if data.get("pe") is not None or data.get("pb") is not None:
        return data
    return _fundamentals_from_yfinance(symbol)


# ──────────────────────────────────────────────────────────────
# 3. Options chain (IBKR puis fallback yfinance + calcul grecques)
# ──────────────────────────────────────────────────────────────
def _option_chain_from_ibkr(symbol: str, days_min: int, days_max: int) -> pd.DataFrame:
    ib = _get_ib()
    stock = Stock(symbol, "SMART", "USD")
    stock = _qualify(stock)
    if not stock:
        return pd.DataFrame()

    chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
    if not chains:
        return pd.DataFrame()

    chain_info = chains[0]
    today = datetime.now().date()
    expirations = []
    for exp in chain_info.expirations:
        dte = (datetime.strptime(exp, "%Y%m%d").date() - today).days
        if days_min <= dte <= days_max:
            expirations.append((exp, dte))
    if not expirations:
        return pd.DataFrame()

    spot = get_spot_price(symbol)
    if not spot:
        return pd.DataFrame()

    strikes = [s for s in chain_info.strikes if 0.85 * spot <= s <= 1.15 * spot]
    if not strikes:
        return pd.DataFrame()

    contracts = []
    for exp, dte in expirations[:5]:
        for strike in strikes[:30]:
            for right in ("C", "P"):
                contracts.append(Option(symbol, exp, strike, right, "SMART"))

    if not contracts:
        return pd.DataFrame()

    qualified = ib.qualifyContracts(*contracts)
    tickers = ib.reqTickers(*qualified)
    ib.sleep(2)

    rows = []
    for t in tickers:
        if not t.contract:
            continue
        c = t.contract
        gk = t.modelGreeks or t.lastGreeks
        rows.append({
            'symbol': symbol,
            'expiry': c.lastTradeDateOrContractMonth,
            'strike': c.strike,
            'right': c.right,
            'bid': t.bid,
            'ask': t.ask,
            'last': t.last,
            'iv': gk.impliedVol if gk else None,
            'delta': gk.delta if gk else None,
            'gamma': gk.gamma if gk else None,
            'theta': gk.theta if gk else None,
            'vega': gk.vega if gk else None,
            'open_interest': t.openInterest or 0,
            'volume': t.volume or 0,
            'spot': spot,
            'dte': (datetime.strptime(c.lastTradeDateOrContractMonth, '%Y%m%d').date() - today).days,
        })
    df = pd.DataFrame(rows)
    # Arrondi des colonnes numériques
    numeric_cols = ['bid', 'ask', 'last', 'iv', 'delta', 'gamma', 'theta', 'vega', 'spot', 'open_interest', 'volume', 'dte']
    df = _round_df(df, numeric_cols)
    logger.info(f"IBKR: {symbol} - {len(df)} options (arrondies)")
    return df

def _option_chain_from_yfinance(symbol: str, days_min: int, days_max: int) -> pd.DataFrame:
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
                    'spot': None,
                    'dte': dte,
                })
    df = pd.DataFrame(rows)
    if not df.empty:
        spot = get_spot_price(symbol) or 0.0
        df['spot'] = round(spot, 2)
    # Arrondi des colonnes numériques (sauf spot déjà arrondi)
    numeric_cols = ['bid', 'ask', 'last', 'iv', 'open_interest', 'volume', 'dte']
    df = _round_df(df, numeric_cols)
    logger.info(f"yfinance raw: {symbol} - {len(df)} options (arrondies)")
    return df

def _add_greeks_robust(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Ajoute les colonnes delta, theta, gamma, vega et arrondit à 2 décimales.
    """
    # Colonnes nécessaires
    required_cols = ['strike', 'dte', 'spot', 'iv', 'right']
    for col in required_cols:
        if col not in df.columns:
            if col == 'spot':
                df['spot'] = get_spot_price(symbol) or 100.0
            elif col == 'iv':
                df['iv'] = 0.3
            elif col == 'dte':
                df['dte'] = 30
            else:
                df[col] = 0

    # Convertir DTE en années
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

    # Delta
    delta_call = norm.cdf(d1)
    delta_put = norm.cdf(d1) - 1
    df['delta'] = np.where(is_call, delta_call, delta_put)

    # Gamma
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    df['gamma'] = gamma

    # Theta (par jour)
    theta_call = - (S * sigma * norm.pdf(d1)) / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * norm.cdf(d2)
    theta_put = - (S * sigma * norm.pdf(d1)) / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm.cdf(-d2)
    df['theta'] = np.where(is_call, theta_call, theta_put) / 365.0

    # Vega (pour 1% de IV)
    vega = (S * norm.pdf(d1) * np.sqrt(T)) / 100
    df['vega'] = vega

    # Remplacer NaN/inf par valeurs par défaut
    df['delta'] = df['delta'].fillna(0.2)
    df['theta'] = df['theta'].fillna(-0.05)
    df['gamma'] = df['gamma'].fillna(0.01)
    df['vega'] = df['vega'].fillna(0.1)

    # Arrondi
    greek_cols = ['delta', 'theta', 'gamma', 'vega']
    df = _round_df(df, greek_cols)
    return df

def get_option_chain(symbol: str, days_min: int = 7, days_max: int = 60) -> pd.DataFrame:
    # Tentative IBKR
    df = _option_chain_from_ibkr(symbol, days_min, days_max)
    if not df.empty:
        return df

    # Fallback yfinance
    logger.info(f"Fallback yfinance pour {symbol}")
    df = _option_chain_from_yfinance(symbol, days_min, days_max)
    if df.empty:
        logger.warning(f"Aucune option pour {symbol}")
        return df

    # Calcul des grecques
    try:
        df = _add_greeks_robust(df, symbol)
        logger.info(f"yfinance enrichi: {symbol} - {len(df)} options (grecques calculées et arrondies)")
    except Exception as e:
        logger.error(f"Erreur calcul grecques pour {symbol}: {e}")
        df['delta'] = 0.2
        df['theta'] = -0.05
        df['gamma'] = 0.01
        df['vega'] = 0.1
        df = _round_df(df, ['delta', 'theta', 'gamma', 'vega'])

    return df


# ──────────────────────────────────────────────────────────────
# 4. VIX (inchangé, mais arrondi si besoin)
# ──────────────────────────────────────────────────────────────
def _vix_from_twelvedata() -> Optional[float]:
    if not TWELVE_DATA_API_KEY:
        return None
    try:
        url = f"https://api.twelvedata.com/quote?symbol=VIX&apikey={TWELVE_DATA_API_KEY}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if "close" in data:
            return round(float(data["close"]), 2)
    except:
        pass
    return None

def _vix_from_alpha_vantage() -> Optional[float]:
    if not ALPHA_VANTAGE_API_KEY:
        return None
    try:
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=VIX&apikey={ALPHA_VANTAGE_API_KEY}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if "Global Quote" in data and "05. price" in data["Global Quote"]:
            return round(float(data["Global Quote"]["05. price"]), 2)
    except:
        pass
    return None

def _vix_from_ibkr() -> Optional[float]:
    ib = _get_ib()
    try:
        contract = Index("VIX", "CBOE", "USD")
        qualified = ib.qualifyContracts(contract)
        if qualified:
            ticker = ib.reqMktData(qualified[0], "", False, False)
            ib.sleep(2)
            vix = ticker.last or ticker.close
            ib.cancelMktData(qualified[0])
            if vix and vix > 0:
                return round(float(vix), 2)
    except:
        pass
    return None

def _vix_from_yfinance() -> Optional[float]:
    try:
        ticker = yf.Ticker("^VIX")
        hist = ticker.history(period='1d')
        if not hist.empty:
            return round(float(hist['Close'].iloc[-1]), 2)
    except:
        pass
    return None

def get_vix() -> Optional[float]:
    vix = _vix_from_twelvedata()
    if vix is not None:
        return vix
    vix = _vix_from_alpha_vantage()
    if vix is not None:
        return vix
    vix = _vix_from_ibkr()
    if vix is not None:
        return vix
    return _vix_from_yfinance()


# ──────────────────────────────────────────────────────────────
# 5. Utilitaires
# ──────────────────────────────────────────────────────────────
def get_atm_iv(symbol: str) -> Optional[float]:
    chain = get_option_chain(symbol)
    if chain.empty:
        return None
    chain = chain.copy()
    if 'dte' not in chain.columns:
        return None
    chain["dte_diff"] = (chain["dte"] - 30).abs()
    nearest_exp = chain.loc[chain["dte_diff"].idxmin(), "expiry"]
    subset = chain[chain["expiry"] == nearest_exp]
    if 'spot' not in subset.columns:
        spot = get_spot_price(symbol)
        if spot is None:
            return None
        subset['spot'] = spot
    spot = subset['spot'].iloc[0]
    subset["strike_diff"] = (subset["strike"] - spot).abs()
    atm = subset.loc[subset["strike_diff"].idxmin()]
    iv = atm["iv"]
    return round(float(iv), 4) if pd.notna(iv) and iv > 0 else None

def get_spy_ma50() -> Optional[float]:
    try:
        ticker = yf.Ticker("SPY")
        hist = ticker.history(period='6mo')
        if len(hist) >= 50:
            return round(float(hist['Close'].rolling(50).mean().iloc[-1]), 2)
    except:
        pass
    return None