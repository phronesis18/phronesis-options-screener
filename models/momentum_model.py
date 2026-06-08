"""
momentum_model.py — Pilier 4 : Analyse Momentum
================================================
Évalue la dynamique de prix et de volume via :
  - RSI (14j) : surachat / survente
  - MACD : croisements de tendance
  - ADX : force de la tendance
  - Volume ratio : confirmation du mouvement

Utilise pandas_ta pour les calculs techniques.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict

import pandas as pd
import numpy as np

try:
    import pandas_ta as ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    logging.warning("pandas_ta non installé. Calculs TA limités.")

import config
from data_fetcher import get_historical_bars

logger = logging.getLogger(__name__)


@dataclass
class MomentumResult:
    passed:     bool
    signal:     str          # "bullish", "bearish", "neutral"
    score:      float        # 0-1
    bias:       str          # "call_buyer", "put_buyer", "seller", "neutral"
    details:    Dict = field(default_factory=dict)
    message:    str = ""

    def __str__(self):
        emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(self.signal, "⚪")
        return (
            f"Momentum [{emoji} {self.signal.upper()}] score={self.score:.2f} | "
            f"Biais={self.bias} | "
            f"RSI={self.details.get('rsi', 'N/A')} | "
            f"ADX={self.details.get('adx', 'N/A')} | "
            f"{self.message}"
        )


class MomentumModel:
    """
    Analyse le momentum pour orienter le type d'option à trader.

    Logique :
    ─────────────────────────────────────────────────────────
    RSI < 35  + ADX > 20 → momentum baissier       → acheteur put
    RSI > 65  + ADX > 20 → momentum haussier fort  → acheteur call OU vendeur put
    RSI 40-60 + ADX < 20 → range / pas de tendance → vendeur de premium
    MACD > Signal        → tendance haussière
    Volume > 1.2x MA20   → confirmation
    ─────────────────────────────────────────────────────────
    """

    def __init__(self):
        self.cfg = config.MOMENTUM

    def analyze(self, symbol: str,
                df: Optional[pd.DataFrame] = None) -> MomentumResult:
        """
        Analyse le momentum d'un sous-jacent.

        Args:
            symbol : ticker
            df     : optionnel — DataFrame OHLCV déjà chargé
        """
        if df is None:
            df = get_historical_bars(symbol, duration="6 M", bar_size="1 day")

        if df is None or len(df) < 50:
            return MomentumResult(
                passed=False,
                signal="neutral",
                score=0.5,
                bias="neutral",
                message=f"Données insuffisantes pour {symbol}"
            )

        details: Dict = {}

        # ── 1. RSI ────────────────────────────────────────────
        rsi = self._calc_rsi(df["Close"])
        details["rsi"] = round(rsi, 1) if rsi is not None else None

        # ── 2. MACD ───────────────────────────────────────────
        macd_line, macd_signal, macd_hist = self._calc_macd(df["Close"])
        details["macd"]        = round(macd_line, 4) if macd_line is not None else None
        details["macd_signal"] = round(macd_signal, 4) if macd_signal is not None else None
        details["macd_hist"]   = round(macd_hist, 4)  if macd_hist  is not None else None

        # ── 3. ADX ────────────────────────────────────────────
        adx = self._calc_adx(df)
        details["adx"] = round(adx, 1) if adx is not None else None

        # ── 4. Volume Ratio ───────────────────────────────────
        vol_ratio = self._calc_volume_ratio(df["Volume"])
        details["volume_ratio"] = round(vol_ratio, 2) if vol_ratio is not None else None

        # ── 5. Score et Signal ────────────────────────────────
        score, signal, bias = self._aggregate_signals(
            rsi, macd_line, macd_signal, adx, vol_ratio
        )

        passed = (score > 0.35)

        message_parts = []
        if rsi is not None:
            if rsi < self.cfg["rsi_oversold"]:
                message_parts.append(f"Survente (RSI={rsi:.0f})")
            elif rsi > self.cfg["rsi_overbought"]:
                message_parts.append(f"Surachat (RSI={rsi:.0f})")

        if macd_line is not None and macd_signal is not None:
            cross = "haussier" if macd_line > macd_signal else "baissier"
            message_parts.append(f"MACD {cross}")

        if adx is not None and adx > self.cfg["adx_trend_min"]:
            message_parts.append(f"Tendance forte (ADX={adx:.0f})")

        message = " | ".join(message_parts) if message_parts else f"{symbol} momentum neutre"

        return MomentumResult(
            passed=passed,
            signal=signal,
            score=round(score, 3),
            bias=bias,
            details=details,
            message=message,
        )

    # ──────────────────────────────────────────────────────────
    # Calculs techniques
    # ──────────────────────────────────────────────────────────

    def _calc_rsi(self, close: pd.Series, period: int = 14) -> Optional[float]:
        """RSI sur `period` jours."""
        try:
            if TA_AVAILABLE:
                rsi_series = ta.rsi(close, length=period)
                return float(rsi_series.iloc[-1]) if rsi_series is not None else None
            else:
                # Fallback manuel
                delta = close.diff()
                gain  = delta.clip(lower=0).rolling(period).mean()
                loss  = (-delta.clip(upper=0)).rolling(period).mean()
                rs    = gain / (loss + 1e-10)
                rsi   = 100 - (100 / (1 + rs))
                return float(rsi.iloc[-1])
        except Exception as e:
            logger.debug(f"_calc_rsi : {e}")
            return None

    def _calc_macd(self, close: pd.Series,
                   fast: int = 12, slow: int = 26,
                   signal: int = 9):
        """MACD standard 12/26/9."""
        try:
            if TA_AVAILABLE:
                macd_df = ta.macd(close, fast=fast, slow=slow, signal=signal)
                if macd_df is None or macd_df.empty:
                    return None, None, None
                line   = float(macd_df[f"MACD_{fast}_{slow}_{signal}"].iloc[-1])
                sig    = float(macd_df[f"MACDs_{fast}_{slow}_{signal}"].iloc[-1])
                hist   = float(macd_df[f"MACDh_{fast}_{slow}_{signal}"].iloc[-1])
                return line, sig, hist
            else:
                ema_fast = close.ewm(span=fast, adjust=False).mean()
                ema_slow = close.ewm(span=slow, adjust=False).mean()
                macd_line = ema_fast - ema_slow
                macd_sig  = macd_line.ewm(span=signal, adjust=False).mean()
                macd_hist = macd_line - macd_sig
                return (float(macd_line.iloc[-1]),
                        float(macd_sig.iloc[-1]),
                        float(macd_hist.iloc[-1]))
        except Exception as e:
            logger.debug(f"_calc_macd : {e}")
            return None, None, None

    def _calc_adx(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """ADX sur `period` jours."""
        try:
            if TA_AVAILABLE:
                adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=period)
                if adx_df is None or adx_df.empty:
                    return None
                col = [c for c in adx_df.columns if c.startswith("ADX_")]
                return float(adx_df[col[0]].iloc[-1]) if col else None
            else:
                # Fallback simplifié : True Range moyen
                tr = pd.concat([
                    df["High"] - df["Low"],
                    (df["High"] - df["Close"].shift()).abs(),
                    (df["Low"]  - df["Close"].shift()).abs()
                ], axis=1).max(axis=1)
                atr = tr.rolling(period).mean().iloc[-1]
                # ADX approximé (non normalisé, indicatif)
                return float(atr / df["Close"].iloc[-1] * 100)
        except Exception as e:
            logger.debug(f"_calc_adx : {e}")
            return None

    def _calc_volume_ratio(self, volume: pd.Series,
                           period: int = 20) -> Optional[float]:
        """Ratio volume actuel / MA20 volume."""
        try:
            ma20 = volume.rolling(period).mean().iloc[-1]
            if ma20 and ma20 > 0:
                return float(volume.iloc[-1] / ma20)
        except Exception as e:
            logger.debug(f"_calc_volume_ratio : {e}")
        return None

    # ──────────────────────────────────────────────────────────
    # Agrégation des signaux
    # ──────────────────────────────────────────────────────────

    def _aggregate_signals(self,
                           rsi:        Optional[float],
                           macd_line:  Optional[float],
                           macd_sig:   Optional[float],
                           adx:        Optional[float],
                           vol_ratio:  Optional[float]):
        """
        Retourne (score 0-1, signal, bias).
        bias ∈ {"call_buyer", "put_buyer", "seller", "neutral"}
        """
        bull_signals = 0
        bear_signals = 0
        total        = 0

        if rsi is not None:
            total += 1
            if rsi < self.cfg["rsi_oversold"]:
                bear_signals += 1
            elif rsi > self.cfg["rsi_overbought"]:
                bull_signals += 1

        if macd_line is not None and macd_sig is not None:
            total += 1
            if macd_line > macd_sig:
                bull_signals += 1
            else:
                bear_signals += 1

        if vol_ratio is not None:
            total += 1
            if vol_ratio > self.cfg["volume_ratio_min"]:
                # Confirmation du mouvement dominant
                if bull_signals >= bear_signals:
                    bull_signals += 0.5
                else:
                    bear_signals += 0.5

        if total == 0:
            return 0.5, "neutral", "neutral"

        bull_ratio = bull_signals / (total + 0.5)
        bear_ratio = bear_signals / (total + 0.5)

        trend_strength = adx or 0

        if bull_ratio > 0.55:
            signal = "bullish"
            score  = min(1.0, bull_ratio + 0.1 * (trend_strength > self.cfg["adx_trend_min"]))
            # RSI surachat + tendance forte → vendeur call OTM
            if rsi and rsi > self.cfg["rsi_overbought"] and trend_strength > self.cfg["adx_trend_min"]:
                bias = "seller"
            else:
                bias = "call_buyer"
        elif bear_ratio > 0.55:
            signal = "bearish"
            score  = min(1.0, bear_ratio + 0.1 * (trend_strength > self.cfg["adx_trend_min"]))
            # RSI survente → rebond possible → vendeur put OTM
            if rsi and rsi < self.cfg["rsi_oversold"]:
                bias = "put_buyer"
            else:
                bias = "seller"
        else:
            signal = "neutral"
            score  = 0.5
            bias   = "seller"   # Range → vente premium idéale

        return round(score, 3), signal, bias
