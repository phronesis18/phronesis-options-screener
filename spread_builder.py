"""
spread_builder.py — Construction des spreads calibrés à 120 $
=============================================================
Construit les structures d'options suivantes :
  1. Bull Call Spread  (débit acheteur haussier)
  2. Bear Put Spread   (débit acheteur baissier)
  3. Bull Put Spread   (crédit vendeur haussier)
  4. Bear Call Spread  (crédit vendeur baissier)

Contrainte : risque net ≤ 120 $ par trade (= 1 contrat × 100).
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict

import pandas as pd
import numpy as np

import config
from scoring_ia import ScoringInput, compute_score, ScoringResult

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Dataclass : Spread
# ──────────────────────────────────────────────────────────────

@dataclass
class SpreadCandidate:
    """Représente un spread d'options candidat à l'alerte."""
    symbol:          str
    strategy:        str       # "bull_call", "bear_put", "bull_put", "bear_call"
    expiry:          str
    dte:             int

    # Leg 1 (achat pour débit, vente pour crédit)
    leg1_right:      str       # "C" ou "P"
    leg1_strike:     float
    leg1_bid:        float
    leg1_ask:        float
    leg1_delta:      float
    leg1_theta:      float
    leg1_iv:         float
    leg1_oi:         int

    # Leg 2
    leg2_right:      str
    leg2_strike:     float
    leg2_bid:        float
    leg2_ask:        float
    leg2_delta:      float
    leg2_theta:      float
    leg2_iv:         float
    leg2_oi:         int

    # Métriques du spread
    spread_width:    float     # abs(leg2_strike - leg1_strike)
    net_debit:       float     # Pour spreads débit
    net_credit:      float     # Pour spreads crédit
    max_profit:      float     # En $ (× 100 non inclus)
    max_loss:        float     # En $ (× 100 non inclus)
    risk_usd:        float     # max_loss × 100 (contrainte 120 $)
    breakeven:       float     # Prix d'équilibre
    spot:            float

    # IA
    scoring:         Optional[ScoringResult] = None
    iv_percentile:   Optional[float] = None

    def to_alert_dict(self) -> Dict:
        """Sérialise en dict pour JSON/Sheets."""
        return {
            "symbol":       self.symbol,
            "strategy":     self.strategy,
            "expiry":       self.expiry,
            "dte":          self.dte,
            "leg1":         f"{self.leg1_right}{self.leg1_strike:.0f}",
            "leg2":         f"{self.leg2_right}{self.leg2_strike:.0f}",
            "net_debit":    round(self.net_debit, 2),
            "net_credit":   round(self.net_credit, 2),
            "max_profit":   round(self.max_profit * 100, 2),
            "max_loss":     round(self.max_loss * 100, 2),
            "risk_usd":     round(self.risk_usd, 2),
            "breakeven":    round(self.breakeven, 2),
            "spot":         round(self.spot, 2),
            "score":        self.scoring.score if self.scoring else None,
            "score_label":  self.scoring.label if self.scoring else None,
            "iv_percentile": self.iv_percentile,
        }

    def __str__(self) -> str:
        strat_label = {
            "bull_call": "Bull Call Spread 📈",
            "bear_put":  "Bear Put Spread  📉",
            "bull_put":  "Bull Put Spread  💰",
            "bear_call": "Bear Call Spread 💰",
        }.get(self.strategy, self.strategy)

        lines = [
            f"  ┌─ {self.symbol} — {strat_label}",
            f"  │  Expiry : {self.expiry} (J-{self.dte})",
            f"  │  Legs   : {self.leg1_right}{self.leg1_strike:.0f} / {self.leg2_right}{self.leg2_strike:.0f}",
            f"  │  Spot   : {self.spot:.2f}  |  Break-even : {self.breakeven:.2f}",
        ]

        if self.net_debit > 0:
            lines.append(f"  │  Débit net   : {self.net_debit:.2f}$ | Max profit: {self.max_profit*100:.0f}$")
        else:
            lines.append(f"  │  Crédit net  : {self.net_credit:.2f}$ | Max profit: {self.max_profit*100:.0f}$")

        lines.append(f"  │  Risque max  : {self.risk_usd:.0f}$ ≤ {config.MAX_RISK_USD}$  ✅")

        if self.scoring:
            lines.append(f"  ├─ {self.scoring}")

        lines.append("  └" + "─" * 55)
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Classe principale
# ──────────────────────────────────────────────────────────────

class SpreadBuilder:
    """
    Construit et filtre les spreads à partir d'une chaîne d'options.
    Contrainte centrale : risque net ≤ MAX_RISK_USD (120 $).
    """

    def __init__(self):
        self.cfg   = config.SPREAD
        self.max_r = config.MAX_RISK_USD

    def build_all(self,
                  symbol: str,
                  option_chain: pd.DataFrame,
                  momentum_bias: str = "neutral",
                  iv_percentile: Optional[float] = None,
                  days_to_event: Optional[float] = None) -> List[SpreadCandidate]:
        """
        Point d'entrée principal.
        Construit tous les spreads pertinents selon le biais momentum.
        """
        if option_chain.empty:
            return []

        candidates: List[SpreadCandidate] = []
        spot = option_chain["spot"].iloc[0] if "spot" in option_chain.columns else None
        if not spot:
            return []

        # Sélection des stratégies selon le biais
        strategies = self._select_strategies(momentum_bias)

        for strategy in strategies:
            if strategy == "bull_call":
                spreads = self._build_bull_call(symbol, option_chain, spot)
            elif strategy == "bear_put":
                spreads = self._build_bear_put(symbol, option_chain, spot)
            elif strategy == "bull_put":
                spreads = self._build_bull_put(symbol, option_chain, spot)
            elif strategy == "bear_call":
                spreads = self._build_bear_call(symbol, option_chain, spot)
            else:
                continue

            # Filtrer par contrainte 120 $
            valid = [s for s in spreads if s.risk_usd <= self.max_r]

            # Scorer chaque candidat
            for spread in valid:
                spread.iv_percentile = iv_percentile
                spread.scoring = self._score_spread(
                    spread, iv_percentile, days_to_event
                )

            # Trier par score décroissant
            valid.sort(key=lambda s: s.scoring.score if s.scoring else 0,
                       reverse=True)
            candidates.extend(valid[:3])  # Max 3 par stratégie

        logger.info(
            f"{symbol} : {len(candidates)} spread(s) candidat(s) "
            f"(biais={momentum_bias})"
        )
        return candidates

    # ──────────────────────────────────────────────────────────
    # Constructeurs de spreads
    # ──────────────────────────────────────────────────────────

    def _build_bull_call(self, symbol: str, chain: pd.DataFrame,
                          spot: float) -> List[SpreadCandidate]:
        """
        Bull Call Spread : achat call ATM/légèrement OTM +
                           vente call OTM plus éloigné.
        Débit = ask(leg1) - bid(leg2).
        Risque max = débit × 100.
        """
        calls = chain[chain["right"] == "C"].copy()
        return self._build_vertical(
            symbol, calls, spot, "bull_call",
            lower_is_long=True
        )

    def _build_bear_put(self, symbol: str, chain: pd.DataFrame,
                         spot: float) -> List[SpreadCandidate]:
        """
        Bear Put Spread : achat put ATM/légèrement OTM +
                          vente put OTM plus bas.
        """
        puts = chain[chain["right"] == "P"].copy()
        return self._build_vertical(
            symbol, puts, spot, "bear_put",
            lower_is_long=False
        )

    def _build_bull_put(self, symbol: str, chain: pd.DataFrame,
                         spot: float) -> List[SpreadCandidate]:
        """
        Bull Put Spread (credit) : vente put OTM + achat put OTM inférieur.
        Crédit encaissé = bid(short) - ask(long).
        Risque = (largeur spread - crédit) × 100.
        """
        puts = chain[chain["right"] == "P"].copy()
        return self._build_credit_spread(
            symbol, puts, spot, "bull_put"
        )

    def _build_bear_call(self, symbol: str, chain: pd.DataFrame,
                          spot: float) -> List[SpreadCandidate]:
        """
        Bear Call Spread (credit) : vente call OTM + achat call OTM supérieur.
        """
        calls = chain[chain["right"] == "C"].copy()
        return self._build_credit_spread(
            symbol, calls, spot, "bear_call"
        )

    # ──────────────────────────────────────────────────────────
    # Générateurs génériques
    # ──────────────────────────────────────────────────────────

    def _build_vertical(self, symbol: str, df: pd.DataFrame,
                         spot: float, strategy: str,
                         lower_is_long: bool) -> List[SpreadCandidate]:
        """Génère des spreads verticaux débit."""
        results = []
        expirations = df["expiry"].unique()

        for expiry in expirations:
            exp_df = df[df["expiry"] == expiry].copy()
            dte = int(exp_df["dte"].iloc[0]) if "dte" in exp_df.columns else 30

            strikes = sorted(exp_df["strike"].unique())

            for i, s1 in enumerate(strikes):
                for s2 in strikes[i+1:]:
                    width = s2 - s1
                    if not (self.cfg["min_spread_width"] <= width <= self.cfg["max_spread_width"]):
                        continue

                    row1 = exp_df[exp_df["strike"] == s1].iloc[0]
                    row2 = exp_df[exp_df["strike"] == s2].iloc[0]

                    if lower_is_long:
                        # Achat s1 (ATM/NTM), vente s2 (OTM)
                        long_leg, short_leg = row1, row2
                    else:
                        # Achat s2 (ATM/NTM), vente s1 (OTM)
                        long_leg, short_leg = row2, row1

                    debit = (long_leg["ask"] or 0) - (short_leg["bid"] or 0)
                    if debit <= 0:
                        continue

                    risk_usd = debit * 100
                    if risk_usd > self.max_r:
                        continue

                    max_profit = (width - debit)
                    if max_profit <= 0:
                        continue

                    if lower_is_long:
                        breakeven = s1 + debit
                    else:
                        breakeven = s2 - debit

                    candidate = self._make_candidate(
                        symbol=symbol, strategy=strategy, expiry=expiry, dte=dte,
                        leg1=long_leg, leg2=short_leg,
                        net_debit=debit, net_credit=0,
                        max_profit=max_profit, max_loss=debit,
                        risk_usd=risk_usd, breakeven=breakeven, spot=spot
                    )
                    results.append(candidate)

        return results

    def _build_credit_spread(self, symbol: str, df: pd.DataFrame,
                              spot: float, strategy: str) -> List[SpreadCandidate]:
        """Génère des spreads verticaux crédit."""
        results = []
        expirations = df["expiry"].unique()

        for expiry in expirations:
            exp_df = df[df["expiry"] == expiry].copy()
            dte = int(exp_df["dte"].iloc[0]) if "dte" in exp_df.columns else 30

            strikes = sorted(exp_df["strike"].unique())

            for i, s_short in enumerate(strikes):
                for s_long in strikes[i+1:]:
                    width = s_long - s_short
                    if not (self.cfg["min_spread_width"] <= width <= self.cfg["max_spread_width"]):
                        continue

                    row_short = exp_df[exp_df["strike"] == s_short].iloc[0]
                    row_long  = exp_df[exp_df["strike"] == s_long].iloc[0]

                    if strategy == "bull_put":
                        # Vente put OTM supérieur (s_long), achat put inférieur (s_short)
                        short_row = row_long
                        long_row  = row_short
                    else:
                        # bear_call : vente call OTM inférieur, achat call supérieur
                        short_row = row_short
                        long_row  = row_long

                    credit = (short_row["bid"] or 0) - (long_row["ask"] or 0)
                    if credit <= 0:
                        continue

                    # Crédit minimum = 20 % de la largeur
                    if credit < self.cfg.get("credit_min_pct", 0.20) * width:
                        continue

                    max_loss   = width - credit
                    risk_usd   = max_loss * 100
                    if risk_usd > self.max_r:
                        continue

                    max_profit = credit
                    if strategy == "bull_put":
                        breakeven = short_row["strike"] - credit
                    else:
                        breakeven = short_row["strike"] + credit

                    candidate = self._make_candidate(
                        symbol=symbol, strategy=strategy, expiry=expiry, dte=dte,
                        leg1=short_row, leg2=long_row,
                        net_debit=0, net_credit=credit,
                        max_profit=max_profit, max_loss=max_loss,
                        risk_usd=risk_usd, breakeven=breakeven, spot=spot
                    )
                    results.append(candidate)

        return results

    # ──────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────

    def _make_candidate(self, symbol, strategy, expiry, dte,
                         leg1, leg2,
                         net_debit, net_credit,
                         max_profit, max_loss,
                         risk_usd, breakeven, spot) -> SpreadCandidate:
        return SpreadCandidate(
            symbol=symbol, strategy=strategy,
            expiry=expiry, dte=dte,
            leg1_right=leg1.get("right", ""),
            leg1_strike=float(leg1.get("strike", 0)),
            leg1_bid=float(leg1.get("bid") or 0),
            leg1_ask=float(leg1.get("ask") or 0),
            leg1_delta=float(leg1.get("delta") or 0),
            leg1_theta=float(leg1.get("theta") or 0),
            leg1_iv=float(leg1.get("iv") or 0),
            leg1_oi=int(leg1.get("open_interest") or 0),
            leg2_right=leg2.get("right", ""),
            leg2_strike=float(leg2.get("strike", 0)),
            leg2_bid=float(leg2.get("bid") or 0),
            leg2_ask=float(leg2.get("ask") or 0),
            leg2_delta=float(leg2.get("delta") or 0),
            leg2_theta=float(leg2.get("theta") or 0),
            leg2_iv=float(leg2.get("iv") or 0),
            leg2_oi=int(leg2.get("open_interest") or 0),
            spread_width=abs(float(leg2.get("strike", 0)) - float(leg1.get("strike", 0))),
            net_debit=net_debit,
            net_credit=net_credit,
            max_profit=max_profit,
            max_loss=max_loss,
            risk_usd=risk_usd,
            breakeven=breakeven,
            spot=spot,
        )

    def _score_spread(self, spread: SpreadCandidate,
                       iv_percentile: Optional[float],
                       days_to_event: Optional[float]) -> ScoringResult:
        """Calcule le score IA pour un spread."""
        theta = abs(spread.leg1_theta) + abs(spread.leg2_theta)
        delta = abs(spread.leg1_delta)

        oi_min = min(spread.leg1_oi, spread.leg2_oi)
        ba_avg = (
            (spread.leg1_ask - spread.leg1_bid) +
            (spread.leg2_ask - spread.leg2_bid)
        ) / 2

        credit = spread.net_credit if spread.net_credit > 0 else 0

        inp = ScoringInput(
            iv_percentile   = iv_percentile or 50.0,
            theta_abs       = theta,
            delta           = delta,
            open_interest   = oi_min,
            bid_ask_spread  = ba_avg,
            credit_received = credit,
            max_risk        = spread.risk_usd / 100,  # En $ par action
            days_to_event   = days_to_event,
            spot            = spread.spot,
            strike          = spread.leg1_strike,
            symbol          = spread.symbol,
            strategy        = spread.strategy,
            expiry          = spread.expiry,
        )
        return compute_score(inp)

    def _select_strategies(self, bias: str) -> List[str]:
        """Retourne les stratégies pertinentes selon le biais momentum."""
        mapping = {
            "bullish":    ["bull_call", "bull_put"],
            "bearish":    ["bear_put",  "bear_call"],
            "call_buyer": ["bull_call"],
            "put_buyer":  ["bear_put"],
            "seller":     ["bull_put", "bear_call"],
            "neutral":    ["bull_put", "bear_call"],   # Range → vente premium
        }
        return mapping.get(bias, ["bull_put", "bear_call"])
