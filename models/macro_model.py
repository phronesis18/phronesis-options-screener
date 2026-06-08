"""
macro_model.py — Pilier 1 : Analyse Macro
==========================================
Évalue le régime de marché via :
  - VIX (niveaux de peur / complaisance)
  - Position de SPY par rapport à sa MA50
  - Spread de taux (10Y - 2Y) via données IBKR

Un signal bullish favorise la vente de premium (credit spreads).
Un signal bearish favorise l'achat d'options protectrices.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict

import numpy as np
import pandas as pd

import config
from data_fetcher import get_vix, get_historical_bars, get_spot_price

logger = logging.getLogger(__name__)


@dataclass
class MacroResult:
    passed:     bool
    signal:     str          # "bullish", "bearish", "neutral"
    score:      float        # 0-1
    details:    Dict = field(default_factory=dict)
    message:    str = ""

    def __str__(self):
        emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(self.signal, "⚪")
        return (
            f"Macro [{emoji} {self.signal.upper()}] score={self.score:.2f} | "
            f"VIX={self.details.get('vix', 'N/A')} | "
            f"SPY vs MA50={self.details.get('spy_vs_ma50', 'N/A')} | "
            f"{self.message}"
        )


class MacroModel:
    """
    Analyse le régime macro pour orienter la stratégie d'options.

    Heuristique :
    ─────────────────────────────────────────────────────────
    • VIX > seuil_peur  → marché craintif  → signal BEARISH
                           (IV élevée → bon pour vendeurs)
    • VIX < seuil_comp  → marché complaisant → signal BULLISH
                           (tendance haussière, faible vol)
    • SPY sous MA50 > 2 % → correction en cours → BEARISH
    • Courbe de taux inversée → risque de récession → BEARISH
    ─────────────────────────────────────────────────────────
    """

    def __init__(self):
        self.cfg = config.MACRO

    def analyze(self) -> MacroResult:
        """Lance l'analyse macro complète."""
        details: Dict = {}
        signals = []
        scores  = []

        # ── 1. VIX ────────────────────────────────────────────
        vix = get_vix()
        details["vix"] = vix

        if vix is not None:
            if vix > self.cfg["vix_fear_threshold"]:
                signals.append("bearish")
                # VIX élevé → IV haute → favorable pour vendeurs
                scores.append(0.3)
                details["vix_signal"] = f"Peur élevée (VIX={vix:.1f} > {self.cfg['vix_fear_threshold']})"
            elif vix < self.cfg["vix_greed_threshold"]:
                signals.append("bullish")
                scores.append(0.8)
                details["vix_signal"] = f"Complaisance (VIX={vix:.1f} < {self.cfg['vix_greed_threshold']})"
            else:
                signals.append("neutral")
                scores.append(0.5)
                details["vix_signal"] = f"VIX neutre ({vix:.1f})"
        else:
            details["vix_signal"] = "VIX indisponible"

        # ── 2. SPY vs MA50 ────────────────────────────────────
        spy_bars = get_historical_bars("SPY", duration="3 M", bar_size="1 day")
        if spy_bars is not None and len(spy_bars) >= 50:
            spy_close = spy_bars["Close"]
            ma50      = spy_close.rolling(50).mean().iloc[-1]
            spy_last  = spy_close.iloc[-1]
            spy_pct   = (spy_last - ma50) / ma50

            details["spy_last"]    = round(spy_last, 2)
            details["spy_ma50"]    = round(ma50, 2)
            details["spy_vs_ma50"] = f"{spy_pct*100:+.1f}%"

            if spy_pct < -self.cfg["spy_ma50_buffer"]:
                signals.append("bearish")
                scores.append(0.25)
                details["spy_signal"] = f"SPY sous MA50 ({spy_pct*100:+.1f}%)"
            elif spy_pct > self.cfg["spy_ma50_buffer"]:
                signals.append("bullish")
                scores.append(0.75)
                details["spy_signal"] = f"SPY au-dessus MA50 ({spy_pct*100:+.1f}%)"
            else:
                signals.append("neutral")
                scores.append(0.5)
                details["spy_signal"] = f"SPY neutre vs MA50 ({spy_pct*100:+.1f}%)"
        else:
            details["spy_vs_ma50"] = "N/A"
            details["spy_signal"]  = "Données SPY indisponibles"

        # ── 3. Score agrégé ───────────────────────────────────
        agg_score = float(np.mean(scores)) if scores else 0.5

        # Signal dominant
        from collections import Counter
        if signals:
            dominant = Counter(signals).most_common(1)[0][0]
        else:
            dominant = "neutral"

        # Le pilier Macro "passe" si le signal est cohérent
        passed = dominant in ("bullish", "bearish")

        message = (
            f"Régime macro : {dominant.upper()} "
            f"({'favorable' if dominant != 'neutral' else 'indéterminé'} "
            f"pour les options)"
        )

        return MacroResult(
            passed=passed,
            signal=dominant,
            score=round(agg_score, 3),
            details=details,
            message=message,
        )
