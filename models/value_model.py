"""
value_model.py — Pilier 2 : Analyse Value
==========================================
Évalue si le sous-jacent est :
  1. Valorisé raisonnablement (P/E, P/B, EV/EBITDA)
  2. Dans une zone d'IV favorable pour le type de trade envisagé

Signal "value" = l'action n'est pas trop chère ET l'IV est dans
la fenêtre exploitable (ni trop basse, ni extrême).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict

import config
from data_fetcher import get_fundamentals
from iv_percentile_storage import compute_iv_percentile, save_iv

logger = logging.getLogger(__name__)


@dataclass
class ValueResult:
    passed:          bool
    signal:          str          # "value", "overvalued", "neutral"
    score:           float        # 0-1
    iv_percentile:   Optional[float] = None
    details:         Dict = field(default_factory=dict)
    message:         str = ""

    def __str__(self):
        emoji = {"value": "🟢", "overvalued": "🔴", "neutral": "🟡"}.get(self.signal, "⚪")
        iv_str = f"{self.iv_percentile:.0f}%" if self.iv_percentile is not None else "N/A"
        return (
            f"Value [{emoji} {self.signal.upper()}] score={self.score:.2f} | "
            f"IV%ile={iv_str} | "
            f"PE={self.details.get('pe', 'N/A')} | "
            f"{self.message}"
        )


class ValueModel:
    """
    Analyse la valorisation fondamentale et la position de l'IV.

    Critères (configurable dans config.py) :
    ──────────────────────────────────────────────────────────
    • P/E < 30 → pas surcoté
    • P/B < 5  → tangible value
    • EV/EBITDA < 20 → flux raisonnables
    • IV Percentile entre 40-85 → zone favorable vente premium
    ──────────────────────────────────────────────────────────
    """

    def __init__(self):
        self.cfg = config.VALUE

    def analyze(self, symbol: str, current_iv: Optional[float] = None) -> ValueResult:
        """
        Analyse value pour un symbole donné.

        Args:
            symbol      : ticker (ex: "AAPL")
            current_iv  : IV implicite actuelle (float) ; si None,
                          le percentile ne peut pas être calculé.
        """
        details: Dict = {}
        score_parts = []

        # ── 1. Fondamentaux ───────────────────────────────────
        fundamentals = get_fundamentals(symbol)
        pe       = fundamentals.get("pe")
        pb       = fundamentals.get("pb")
        ev_ebitda = fundamentals.get("ev_ebitda")

        details.update({"pe": pe, "pb": pb, "ev_ebitda": ev_ebitda})

        fundamental_score = self._score_fundamentals(pe, pb, ev_ebitda)
        score_parts.append(fundamental_score)

        # ── 2. IV Percentile ──────────────────────────────────
        iv_percentile = None
        if current_iv is not None:
            # Sauvegarder l'IV du jour
            save_iv(symbol, current_iv)
            iv_percentile = compute_iv_percentile(symbol, current_iv)

        details["iv_percentile"]       = iv_percentile
        details["current_iv"]          = current_iv
        details["iv_percentile_min"]   = self.cfg["iv_percentile_min"]
        details["iv_percentile_max"]   = self.cfg["iv_percentile_max"]

        iv_score = self._score_iv_percentile(iv_percentile)
        score_parts.append(iv_score)

        # ── 3. Signal agrégé ──────────────────────────────────
        agg_score = sum(score_parts) / len(score_parts) if score_parts else 0.5

        # Détermination du signal
        if agg_score >= 0.60:
            signal = "value"
            passed = True
            message = f"{symbol} : valorisation et IV favorables"
        elif agg_score <= 0.35:
            signal = "overvalued"
            passed = False
            message = f"{symbol} : sur-valorisé ou IV défavorable"
        else:
            signal = "neutral"
            passed = True  # On laisse passer les cas neutres
            message = f"{symbol} : valorisation neutre"

        return ValueResult(
            passed=passed,
            signal=signal,
            score=round(agg_score, 3),
            iv_percentile=iv_percentile,
            details=details,
            message=message,
        )

    # ──────────────────────────────────────────────────────────
    # Helpers privés
    # ──────────────────────────────────────────────────────────

    def _score_fundamentals(self,
                            pe: Optional[float],
                            pb: Optional[float],
                            ev_ebitda: Optional[float]) -> float:
        """
        Score les fondamentaux sur une échelle 0-1.
        Valeurs manquantes → contribution neutre (0.5).
        """
        scores = []

        if pe is not None:
            if pe <= 0:
                scores.append(0.1)  # PE négatif = perte
            elif pe < self.cfg["pe_max"]:
                scores.append(0.8)
            elif pe < self.cfg["pe_max"] * 1.5:
                scores.append(0.4)
            else:
                scores.append(0.1)
        else:
            scores.append(0.5)

        if pb is not None:
            if pb < self.cfg["pb_max"]:
                scores.append(0.75)
            elif pb < self.cfg["pb_max"] * 1.5:
                scores.append(0.40)
            else:
                scores.append(0.15)
        else:
            scores.append(0.5)

        if ev_ebitda is not None:
            if ev_ebitda < self.cfg["ev_ebitda_max"]:
                scores.append(0.80)
            elif ev_ebitda < self.cfg["ev_ebitda_max"] * 1.5:
                scores.append(0.40)
            else:
                scores.append(0.10)
        else:
            scores.append(0.5)

        return sum(scores) / len(scores)

    def _score_iv_percentile(self, iv_percentile: Optional[float]) -> float:
        """
        Score l'IV percentile sur une échelle 0-1.
        La zone idéale pour vendre du premium est 40-85.
        """
        if iv_percentile is None:
            return 0.5  # Neutre si pas calculable

        lo = self.cfg["iv_percentile_min"]  # 40
        hi = self.cfg["iv_percentile_max"]  # 85

        if lo <= iv_percentile <= hi:
            # Zone idéale — score maximal au centre
            center = (lo + hi) / 2
            dist   = abs(iv_percentile - center) / (hi - lo) * 2
            return round(1.0 - 0.2 * dist, 3)  # Entre 0.80 et 1.0
        elif iv_percentile < lo:
            # IV trop basse pour vendeur ; acceptable pour acheteur
            return round(max(0.2, iv_percentile / lo * 0.6), 3)
        else:
            # IV très élevée : tail risk possible
            excess = (iv_percentile - hi) / (100 - hi)
            return round(max(0.3, 0.8 - excess * 0.5), 3)
