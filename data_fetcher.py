"""
data_fetcher.py — Récupération des données de marché avec fallback multi-sources
=================================================================================
Sources de données (ordre de priorité selon le type de donnée) :

- VIX / données macro : Twelve Data (API gratuite, 800 req/jour) → Alpha Vantage (25 req/jour) → IBKR → yfinance
- Prix spot : IBKR → yfinance
- Chaîne d'options : IBKR → yfinance
- Fondamentaux : IBKR uniquement (pas de fallback fiable)

Garantit que le screener fonctionne toujours, même sans abonnement aux données IBKR.
"""

import logging
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

import pandas as pd
import numpy as np
import yfinance as yf  # fallback

from ib_insync import (
    IB, Stock, Index, Option, Contract,
    util, BarData
)

import config
from ib_connector import IBConnector

load_dotenv()
logger = logging.getLogger(__name__)

# Clés API externes
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")


# ──────────────────────────────────────────────────────────────
# Helpers internes IBKR
# ──────────────────────────────────────────────────────────────

def _get_ib() -> IB:
    """Retourne l'objet IB connecté."""
    connector = IBConnector()
    return connector.ib


def _qualify(contract: Contract) -> Optional[Contract]:
    """Qualifie un contrat IBKR (récupère conId, etc.)."""
    ib = _get_ib()
    try:
        qualified = ib.qualifyContracts(contract)
        return qualified[0] if qualified else None
    except Exception as e:
        logger.warning(f"Impossible de qualifier {contract.symbol} : {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Sources externes : Twelve Data et Alpha Vantage
# ──────────────────────────────────────────────────────────────

def _vix_from_twelvedata() -> Optional[float]:
    """Récupère le VIX via Twelve Data (800 requêtes/jour gratuites)."""
    if not TWELVE_DATA_API_KEY:
        logger.debug("Clé Twelve Data manquante, saut.")
        return None
    try:
        url = f"https://api.twelvedata.com/quote?symbol=VIX&apikey={TWELVE_DATA_API_KEY}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if "close" in data:
            price = float(data["close"])
            logger.debug(f"VIX via Twelve Data: {price}")
            return price
        else:
            logger.debug(f"Twelve Data réponse inattendue: {data}")
    except Exception as e:
        logger.debug(f"Twelve Data VIX échoué: {e}")
    return None


def _vix_from_alpha_vantage() -> Optional[float]:
    """Récupère le VIX via Alpha Vantage (25 requêtes/jour)."""
    if not ALPHA_VANTAGE_API_KEY:
        logger.debug("Clé Alpha Vantage manquante, saut.")
        return None
    try:
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=VIX&apikey={ALPHA_VANTAGE_API_KEY}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if "Global Quote" in data and "05. price" in data["Global Quote"]:
            price = float(data["Global Quote"]["05. price"])
            logger.debug(f"VIX via Alpha Vantage: {price}")
            return price
        else:
            logger.debug(f"Alpha Vantage réponse inattendue: {data}")
    except Exception as e:
        logger.debug(f"Alpha Vantage VIX échoué: {e}")
    return None


# ──────────────────────────────────────────────────────────────
# Fallback yfinance (utilisé si les autres sources échouent)
# ──────────────────────────────────────────────────────────────

def _spot_from_yfinance(symbol: str) -> Optional[float]:
    """Récupère le prix spot via yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='1d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
        info = ticker.info
        price = info.get('regularMarketPrice', info.get('currentPrice'))
        return float(price) if price else None
    except Exception as e:
        logger.debug(f"yfinance spot échoué pour {symbol}: {e}")
        return None


def _option_chain_from_yfinance(symbol: str, days_min: int = 7, days_max: int = 60) -> pd.DataFrame:
    """Récupère la chaîne d'options via yfinance (fallback)."""
    ticker = yf.Ticker(symbol)
    expirations = ticker.options
    if not expirations:
        logger.warning(f"Aucune expiration trouvée pour {symbol} via yfinance")
        return pd.DataFrame()

    today = datetime.now().date()
    all_rows = []

    for exp_str in expirations:
        exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
        dte = (exp_date - today).days
        if dte < days_min or dte > days_max:
            continue

        try:
            chain = ticker.option_chain(exp_str)
        except Exception as e:
            logger.warning(f"Erreur récupération chaîne {exp_str} pour {symbol}: {e}")
            continue

        for right, df in [('C', chain.calls), ('P', chain.puts)]:
            for _, row in df.iterrows():
                bid = row['bid'] if not pd.isna(row['bid']) else 0.0
                ask = row['ask'] if not pd.isna(row['ask']) else 0.0
                iv = row['impliedVolatility'] if not pd.isna(row['impliedVolatility']) else 0.0
                delta = row.get('delta', np.nan)
                theta = row.get('theta', np.nan)
                gamma = row.get('gamma', np.nan)
                vega = row.get('vega', np.nan)
                open_interest = row['openInterest'] if not pd.isna(row['openInterest']) else 0
                volume = row['volume'] if not pd.isna(row['volume']) else 0
                last_price = row['lastPrice'] if not pd.isna(row['lastPrice']) else 0.0

                all_rows.append({
                    'symbol': symbol,
                    'expiry': exp_str.replace('-', ''),
                    'expiry_date': exp_date,
                    'dte': dte,
                    'strike': row['strike'],
                    'right': right,
                    'bid': bid,
                    'ask': ask,
                    'last': last_price,
                    'iv': iv,
                    'delta': delta,
                    'gamma': gamma,
                    'theta': theta,
                    'vega': vega,
                    'open_interest': open_interest,
                    'volume': volume,
                })

    df = pd.DataFrame(all_rows)
    if not df.empty:
        # Ajout spot (on le récupère pour info)
        spot = _spot_from_yfinance(symbol)
        if spot:
            df['spot'] = spot
    logger.info(f"{symbol} : {len(df)} options récupérées via yfinance (fallback)")
    return df


def _vix_from_yfinance() -> Optional[float]:
    """Récupère le VIX via yfinance (dernier fallback)."""
    try:
        ticker = yf.Ticker("^VIX")
        hist = ticker.history(period='1d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception as e:
        logger.debug(f"yfinance VIX échoué: {e}")
    return None


def _spy_ma50_from_yfinance() -> Optional[float]:
    """Calcule la MA50 du SPY via yfinance."""
    try:
        ticker = yf.Ticker("SPY")
        hist = ticker.history(period='6mo')
        if len(hist) >= 50:
            ma50 = hist['Close'].rolling(50).mean().iloc[-1]
            return float(ma50)
    except Exception as e:
        logger.debug(f"yfinance SPY MA50 échoué: {e}")
    return None


# ──────────────────────────────────────────────────────────────
# 1. Prix spot et historique OHLCV
# ──────────────────────────────────────────────────────────────

def get_spot_price(symbol: str, exchange: str = "SMART",
                   currency: str = "USD") -> Optional[float]:
    """
    Retourne le dernier prix spot du sous-jacent.
    Tente d'abord IBKR, puis yfinance.
    """
    # Tentative IBKR
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
                logger.debug(f"{symbol} spot via IBKR = {price:.2f}")
                return float(price)
        except Exception as e:
            logger.debug(f"get_spot_price IBKR échoué pour {symbol}: {e}")

    # Fallback yfinance
    price = _spot_from_yfinance(symbol)
    if price is not None:
        logger.debug(f"{symbol} spot via yfinance = {price:.2f}")
        return price
    return None


def get_historical_bars(symbol: str, duration: str = "1 Y",
                        bar_size: str = "1 day",
                        exchange: str = "SMART",
                        currency: str = "USD") -> Optional[pd.DataFrame]:
    """
    Récupère l'historique OHLCV (IBKR uniquement, pas de fallback yfinance).
    """
    ib = _get_ib()
    contract = Stock(symbol, exchange, currency)
    contract = _qualify(contract)
    if not contract:
        return None

    try:
        bars: List[BarData] = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        if not bars:
            logger.warning(f"Aucune barre historique pour {symbol}.")
            return None

        df = util.df(bars)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.rename(columns={
            "open": "Open", "high": "High",
            "low": "Low", "close": "Close",
            "volume": "Volume"
        }, inplace=True)
        return df

    except Exception as e:
        logger.error(f"get_historical_bars({symbol}) : {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 2. Fondamentaux (uniquement IBKR)
# ──────────────────────────────────────────────────────────────

def get_fundamentals(symbol: str) -> Dict[str, Optional[float]]:
    """
    Récupère les fondamentaux via reqFundamentalData (XML IBKR).
    Pas de fallback car yfinance ne fournit pas ces ratios de manière fiable.
    """
    ib = _get_ib()
    contract = Stock(symbol, "SMART", "USD")
    contract = _qualify(contract)

    defaults = {"pe": None, "pb": None, "ev_ebitda": None}
    if not contract:
        return defaults

    try:
        xml_data = ib.reqFundamentalData(contract, "ReportSnapshot")
        if not xml_data:
            return defaults

        def _extract(tag: str) -> Optional[float]:
            import re
            pattern = rf'<{tag}[^>]*>([\d.]+)</{tag}>'
            match = re.search(pattern, xml_data, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    return None
            return None

        result = {
            "pe":       _extract("PERatio") or _extract("TTMPeExclXor"),
            "pb":       _extract("PriceToBvPerShare"),
            "ev_ebitda": _extract("EV2TTMEbitda"),
        }
        logger.debug(f"Fondamentaux {symbol} : {result}")
        return result

    except Exception as e:
        logger.warning(f"get_fundamentals({symbol}) : {e}")
        return defaults


# ──────────────────────────────────────────────────────────────
# 3. Chaîne d'options (fallback yfinance si IBKR échoue)
# ──────────────────────────────────────────────────────────────

def get_option_chain(symbol: str, exchange: str = "SMART",
                     currency: str = "USD") -> pd.DataFrame:
    """
    Récupère la chaîne d'options complète.
    Tente d'abord IBKR, si échec utilise yfinance.
    """
    # ---------- Tentative IBKR ----------
    ib = _get_ib()
    stock = Stock(symbol, exchange, currency)
    stock = _qualify(stock)
    if stock:
        try:
            chains = ib.reqSecDefOptParams(
                stock.symbol, "", stock.secType, stock.conId
            )
            if not chains:
                logger.warning(f"Pas de paramètres d'options via IBKR pour {symbol}.")
            else:
                # Sélectionner un exchange valide
                chain = next(
                    (c for c in chains if c.exchange in ("SMART", "CBOE")),
                    chains[0]
                )
                today = datetime.now().date()
                valid_expirations = [
                    exp for exp in chain.expirations
                    if config.INCOME.get("min_dte", 7) <=
                       (datetime.strptime(exp, "%Y%m%d").date() - today).days
                       <= 60
                ]

                if not valid_expirations:
                    logger.warning(f"{symbol} : aucune expiration IBKR dans la fenêtre.")
                else:
                    spot = get_spot_price(symbol)  # utilise déjà fallback
                    if not spot:
                        logger.warning(f"{symbol} : spot introuvable, fallback yfinance pour options.")
                    else:
                        # Filtrer strikes ±15%
                        strike_filter = [
                            s for s in chain.strikes
                            if 0.85 * spot <= s <= 1.15 * spot
                        ]
                        contracts = []
                        for expiry in valid_expirations[:4]:
                            for strike in strike_filter:
                                for right in ["C", "P"]:
                                    contracts.append(Option(
                                        symbol, expiry, strike, right, "SMART"
                                    ))
                        if contracts:
                            qualified = ib.qualifyContracts(*contracts)
                            tickers = ib.reqTickers(*qualified)
                            ib.sleep(3)
                            rows = []
                            for t in tickers:
                                c = t.contract
                                if not c:
                                    continue
                                gk = t.modelGreeks or t.lastGreeks
                                iv   = gk.impliedVol  if gk else None
                                delt = gk.delta       if gk else None
                                gamm = gk.gamma       if gk else None
                                thet = gk.theta       if gk else None
                                vega = gk.vega        if gk else None
                                rows.append({
                                    "symbol":        symbol,
                                    "expiry":        c.lastTradeDateOrContractMonth,
                                    "strike":        c.strike,
                                    "right":         c.right,
                                    "bid":           t.bid,
                                    "ask":           t.ask,
                                    "last":          t.last,
                                    "iv":            iv,
                                    "delta":         delt,
                                    "gamma":         gamm,
                                    "theta":         thet,
                                    "vega":          vega,
                                    "open_interest": t.openInterest or 0,
                                    "volume":        t.volume or 0,
                                    "spot":          spot,
                                })
                            df_ibkr = pd.DataFrame(rows)
                            if not df_ibkr.empty:
                                today_ts = pd.Timestamp(today)
                                df_ibkr["expiry_date"] = pd.to_datetime(df_ibkr["expiry"], format="%Y%m%d")
                                df_ibkr["dte"] = (df_ibkr["expiry_date"] - today_ts).dt.days
                                logger.info(f"{symbol} : {len(df_ibkr)} options récupérées via IBKR.")
                                return df_ibkr
        except Exception as e:
            logger.debug(f"get_option_chain IBKR échoué pour {symbol}: {e}")

    # ---------- Fallback yfinance ----------
    logger.info(f"{symbol} : utilisation du fallback yfinance pour les options.")
    return _option_chain_from_yfinance(symbol, days_min=config.INCOME.get("min_dte", 7), days_max=60)


# ──────────────────────────────────────────────────────────────
# 4. VIX (avec fallback multi-sources)
# Ordre : Twelve Data → Alpha Vantage → IBKR → yfinance
# ──────────────────────────────────────────────────────────────

def get_vix() -> Optional[float]:
    """
    Retourne le niveau actuel du VIX.
    Ordre de priorité : Twelve Data → Alpha Vantage → IBKR → yfinance.
    """
    # 1. Twelve Data
    vix = _vix_from_twelvedata()
    if vix is not None:
        return vix

    # 2. Alpha Vantage
    vix = _vix_from_alpha_vantage()
    if vix is not None:
        return vix

    # 3. IBKR
    ib = _get_ib()
    try:
        vix_contract = Index("VIX", "CBOE", "USD")
        qualified = ib.qualifyContracts(vix_contract)
        if qualified:
            ticker = ib.reqMktData(qualified[0], "", False, False)
            ib.sleep(2)
            vix = ticker.last or ticker.close
            ib.cancelMktData(qualified[0])
            if vix and vix > 0:
                logger.debug(f"VIX via IBKR = {vix:.2f}")
                return float(vix)
    except Exception as e:
        logger.debug(f"get_vix IBKR échoué: {e}")

    # 4. yfinance (fallback final)
    vix = _vix_from_yfinance()
    if vix is not None:
        logger.debug(f"VIX via yfinance = {vix:.2f}")
        return vix

    return None


# ──────────────────────────────────────────────────────────────
# 5. IV implicite du sous-jacent (ATM)
# ──────────────────────────────────────────────────────────────

def get_atm_iv(symbol: str) -> Optional[float]:
    """
    Retourne l'IV implicite de l'option ATM la plus proche (~30j).
    Utilise la chaîne d'options (avec fallback intégré).
    """
    chain = get_option_chain(symbol)
    if chain.empty:
        return None

    target_dte = 30
    chain["dte_diff"] = (chain["dte"] - target_dte).abs()
    nearest_exp = chain.loc[chain["dte_diff"].idxmin(), "expiry"]

    subset = chain[chain["expiry"] == nearest_exp].copy()
    if "spot" not in subset.columns:
        spot = get_spot_price(symbol)
        if spot is None:
            return None
        subset["spot"] = spot
    spot = subset["spot"].iloc[0]

    subset["strike_diff"] = (subset["strike"] - spot).abs()
    atm = subset.loc[subset["strike_diff"].idxmin()]

    iv = atm["iv"]
    if pd.notna(iv) and iv > 0:
        return float(iv)
    return None


# ──────────────────────────────────────────────────────────────
# 6. Utilitaires macro supplémentaires
# ──────────────────────────────────────────────────────────────

def get_spy_ma50() -> Optional[float]:
    """Retourne la MA50 du SPY (via yfinance, pas de fallback IBKR nécessaire)."""
    return _spy_ma50_from_yfinance()