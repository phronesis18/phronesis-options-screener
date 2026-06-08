"""
income_model.py — Pilier 3 : Analyse Income (vendeur de premium)
=================================================================
Filtre les options adaptées à la vente de premium :
  - Delta faible (OTM)
  - Thêta suffisant (gain quotidien)
  - DTE dans la fenêtre optimale (7-45j)
  - Crédit ≥ 20 % de la largeur du spread
  - Liquidité acceptable (OI, bid-ask)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List

import pandas as pd
import numpy as np

import config

logger = logging.getLogger(__name__)


@dataclass
class IncomeResult:
    passed:       bool
    score:        float        # 0-1
    candidates:   List[Dict] = field(default_factory=list)   # Options filtrées
    details:      Dict = field(default_factory=dict)
    message:      str = ""

    def __str__(self):
        emoji = "🟢" if self.passed else "🔴"
        return (
            f"Income [{emoji}] score={self.score:.2f} | "
            f"{len(self.candidates)} candidat(s) | "
            f"{self.message}"
        )


class IncomeModel:
    """
    Filtre les options favorables à la vente de premium (theta harvesting).

    Critères appliqués à chaque option de la chaîne :
    ────────────────────────────────────────────────────────────
    ✓ DTE entre min_dte et max_dte
    ✓ |Delta| ≤ delta_max
    ✓ |Thêta| ≥ theta_min
    ✓ OI ≥ min_open_interest
    ✓ Bid-Ask spread ≤ max_bid_ask_spread
    ────────────────────────────────────────────────────────────
    """

    def __init__(self):
        self.cfg = config.INCOME

    def analyze(self, option_chain: pd.DataFrame) -> IncomeResult:
        """
        Filtre la chaîne d'options pour identifier les candidats income.

        Args:
            option_chain : DataFrame retourné par data_fetcher.get_option_chain()
        """
        if option_chain.empty:
            return IncomeResult(
                passed=False, score=0.0,
                message="Chaîne d'options vide"
            )

        # ── 1. Filtre DTE ─────────────────────────────────────
        df = option_chain.copy()
        if "dte" not in df.columns:
            logger.warning("Colonne 'dte' absente de la chaîne.")
            return IncomeResult(passed=False, score=0.0, message="DTE manquant")

        df = df[
            (df["dte"] >= self.cfg["min_dte"]) &
            (df["dte"] <= self.cfg["max_dte"])
        ]

        if df.empty:
            return IncomeResult(
                passed=False, score=0.0,
                message=f"Aucune option dans la fenêtre DTE "
                        f"{self.cfg['min_dte']}-{self.cfg['max_dte']}j"
            )

        # ── 2. Filtre Delta ───────────────────────────────────
        df = df[df["delta"].notna()]
        df = df[df["delta"].abs() <= self.cfg["delta_max"]]

        # ── 3. Filtre Thêta ───────────────────────────────────
        df = df[df["theta"].notna()]
        df = df[df["theta"].abs() >= self.cfg["theta_min"]]

        # ── 4. Filtre Liquidité ───────────────────────────────
        df = df[df["open_interest"] >= self.cfg["min_open_interest"]]

        # Calcul bid-ask spread
        df = df[df["bid"].notna() & df["ask"].notna()]
        df = df[df["ask"] > 0]
        df["bid_ask_pct"] = (df["ask"] - df["bid"])
        df = df[df["bid_ask_pct"] <= self.cfg["max_bid_ask_spread"]]

        if df.empty:
            return IncomeResult(
                passed=False, score=0.2,
                message="Aucune option ne passe tous les filtres income"
            )

        # ── 5. Score par candidat ─────────────────────────────
        df = df.copy()
        df["income_score"] = df.apply(self._score_row, axis=1)
        df.sort_values("income_score", ascending=False, inplace=True)

        top_candidates = df.head(10).to_dict("records")
        agg_score = float(df["income_score"].mean())

        details = {
            "total_after_dte_filter":     len(option_chain[
                (option_chain["dte"] >= self.cfg["min_dte"]) &
                (option_chain["dte"] <= self.cfg["max_dte"])
            ]),
            "total_after_all_filters":    len(df),
            "best_theta":                 round(df["theta"].abs().max(), 4),
            "best_delta":                 round(df["delta"].abs().min(), 4),
        }

        return IncomeResult(
            passed=len(df) > 0,
            score=round(agg_score, 3),
            candidates=top_candidates,
            details=details,
            message=f"{len(df)} options validées (DTE, delta, thêta, liquidité)"
        )

    def _score_row(self, row: pd.Series) -> float:
        """Score une option individuelle de 0 à 1."""
        scores = []

        # Delta : plus faible est mieux
        delta_abs = abs(row["delta"]) if pd.notna(row["delta"]) else 0.5
        delta_score = max(0, 1 - delta_abs / self.cfg["delta_max"])
        scores.append(delta_score)

        # Thêta : plus élevé est mieux
        theta_abs = abs(row["theta"]) if pd.notna(row["theta"]) else 0.0
        theta_score = min(1.0, theta_abs / 0.15)  # Normalisé sur 0.15 $/j
        scores.append(theta_score)

        # DTE : sweet spot autour de 30j (Theta decay optimal)
        dte = row["dte"] if pd.notna(row.get("dte")) else 30
        dte_score = 1.0 - abs(dte - 30) / 30.0
        dte_score = max(0, dte_score)
        scores.append(dte_score)

        # Liquidité
        oi = row["open_interest"] if pd.notna(row["open_interest"]) else 0
        oi_score = min(1.0, oi / 2000.0)
        scores.append(oi_score)

        return round(float(np.mean(scores)), 4)
