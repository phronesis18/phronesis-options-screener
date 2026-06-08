"""
data_fetcher.py — Récupération des données de marché via IBKR
=============================================================
Fournit des fonctions haut niveau pour :
  - Prix spot et données OHLCV
  - Fondamentaux (P/E, P/B, EV/EBITDA)
  - Chaînes d'options complètes (avec grecques et OI)
  - VIX et données macro
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from ib_insync import (
    IB, Stock, Index, Option, Contract,
    util, BarData
)

import config
from ib_connector import IBConnector

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Helpers internes
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
# 1. Prix spot et historique OHLCV
# ──────────────────────────────────────────────────────────────

def get_spot_price(symbol: str, exchange: str = "SMART",
                   currency: str = "USD") -> Optional[float]:
    """
    Retourne le dernier prix spot du sous-jacent.
    Utilise snapshots de marché (reqMktData).
    """
    ib = _get_ib()
    contract = Stock(symbol, exchange, currency)
    contract = _qualify(contract)
    if not contract:
        return None

    try:
        ticker = ib.reqMktData(contract, "", False, False)
        ib.sleep(2)  # Laisser le temps aux données d'arriver
        price = ticker.last or ticker.close or ticker.bid
        ib.cancelMktData(contract)
        if price and price > 0:
            logger.debug(f"{symbol} spot = {price:.2f}")
            return float(price)
    except Exception as e:
        logger.error(f"get_spot_price({symbol}) : {e}")

    return None


def get_historical_bars(symbol: str, duration: str = "1 Y",
                        bar_size: str = "1 day",
                        exchange: str = "SMART",
                        currency: str = "USD") -> Optional[pd.DataFrame]:
    """
    Récupère l'historique OHLCV.
    duration : ex. '1 Y', '6 M', '252 D'
    bar_size  : ex. '1 day', '1 hour'
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
# 2. Fondamentaux
# ──────────────────────────────────────────────────────────────

def get_fundamentals(symbol: str) -> Dict[str, Optional[float]]:
    """
    Récupère les fondamentaux via reqFundamentalData (XML IBKR).
    Retourne P/E, P/B, EV/EBITDA. Valeurs None si indisponibles.

    Note : IBKR retourne un XML brut — on parse les ratios clés.
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

        # Parse simple avec string search (évite lxml comme dépendance)
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
# 3. Chaîne d'options
# ──────────────────────────────────────────────────────────────

def get_option_chain(symbol: str, exchange: str = "SMART",
                     currency: str = "USD") -> pd.DataFrame:
    """
    Récupère la chaîne d'options complète (tous strikes, toutes expirations).
    Retourne un DataFrame avec :
      expiry, strike, right, bid, ask, last, iv, delta, gamma,
      theta, vega, open_interest, volume
    """
    ib = _get_ib()
    stock = Stock(symbol, exchange, currency)
    stock = _qualify(stock)
    if not stock:
        return pd.DataFrame()

    try:
        # Récupération des paramètres de la chaîne
        chains = ib.reqSecDefOptParams(
            stock.symbol, "", stock.secType, stock.conId
        )
        if not chains:
            logger.warning(f"Pas de chaîne d'options pour {symbol}.")
            return pd.DataFrame()

        # On prend le premier exchange (généralement SMART ou CBOE)
        chain = next(
            (c for c in chains if c.exchange in ("SMART", "CBOE")),
            chains[0]
        )

        # Filtrer les expirations utiles (7 à 60 jours)
        today = datetime.now().date()
        valid_expirations = [
            exp for exp in chain.expirations
            if config.INCOME["min_dte"] <=
               (datetime.strptime(exp, "%Y%m%d").date() - today).days
               <= 60
        ]

        if not valid_expirations:
            logger.warning(f"{symbol} : aucune expiration dans la fenêtre 7-60j.")
            return pd.DataFrame()

        # Spot pour filtrer les strikes autour du prix actuel
        spot = get_spot_price(symbol)
        if not spot:
            return pd.DataFrame()

        # Filtrer strikes dans la fenêtre ±15 % du spot
        strike_filter = [
            s for s in chain.strikes
            if 0.85 * spot <= s <= 1.15 * spot
        ]

        # Construire les contrats options
        contracts = []
        for expiry in valid_expirations[:4]:   # Max 4 expirations
            for strike in strike_filter:
                for right in ["C", "P"]:
                    contracts.append(Option(
                        symbol, expiry, strike, right, "SMART"
                    ))

        if not contracts:
            return pd.DataFrame()

        # Qualifier en batch
        logger.info(f"{symbol} : qualification de {len(contracts)} contrats options…")
        qualified = ib.qualifyContracts(*contracts)

        # Récupérer les tickers avec grecques
        tickers = ib.reqTickers(*qualified)
        ib.sleep(3)

        rows = []
        for t in tickers:
            c = t.contract
            if not c:
                continue

            # Grecques model-based
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

        df = pd.DataFrame(rows)
        if not df.empty:
            today_ts = pd.Timestamp(today)
            df["expiry_date"] = pd.to_datetime(df["expiry"], format="%Y%m%d")
            df["dte"] = (df["expiry_date"] - today_ts).dt.days

        logger.info(f"{symbol} : {len(df)} options récupérées.")
        return df

    except Exception as e:
        logger.error(f"get_option_chain({symbol}) : {e}")
        return pd.DataFrame()


# ──────────────────────────────────────────────────────────────
# 4. VIX (indicateur macro)
# ──────────────────────────────────────────────────────────────

def get_vix() -> Optional[float]:
    """Retourne le niveau actuel du VIX."""
    ib = _get_ib()
    try:
        vix_contract = Index("VIX", "CBOE", "USD")
        qualified = ib.qualifyContracts(vix_contract)
        if not qualified:
            return None

        ticker = ib.reqMktData(qualified[0], "", False, False)
        ib.sleep(2)
        vix = ticker.last or ticker.close
        ib.cancelMktData(qualified[0])
        if vix:
            logger.info(f"VIX = {vix:.2f}")
            return float(vix)
    except Exception as e:
        logger.warning(f"get_vix() : {e}")
    return None


# ──────────────────────────────────────────────────────────────
# 5. IV implicite du sous-jacent (ATM)
# ──────────────────────────────────────────────────────────────

def get_atm_iv(symbol: str) -> Optional[float]:
    """
    Retourne l'IV implicite de l'option ATM la plus proche
    (expiration ~30j, strike le plus proche du spot).
    Utilisé pour le calcul du percentile IV.
    """
    chain = get_option_chain(symbol)
    if chain.empty:
        return None

    # Expiration la plus proche de 30j
    target_dte = 30
    chain["dte_diff"] = (chain["dte"] - target_dte).abs()
    nearest_exp = chain.loc[chain["dte_diff"].idxmin(), "expiry"]

    subset = chain[chain["expiry"] == nearest_exp].copy()
    spot = subset["spot"].iloc[0]

    # Strike ATM
    subset["strike_diff"] = (subset["strike"] - spot).abs()
    atm = subset.loc[subset["strike_diff"].idxmin()]

    iv = atm["iv"]
    if pd.notna(iv) and iv > 0:
        return float(iv)
    return None
