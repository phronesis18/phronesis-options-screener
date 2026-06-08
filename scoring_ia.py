"""
scoring_ia.py — Scoring IA Heuristique (Expert Quantitatif)
============================================================
Calcule un score composite 0-100 pour chaque opportunité de spread
en pondérant 7 features normalisées. Aucun ML requis.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Dataclass : Entrée du scoring
# ──────────────────────────────────────────────────────────────

@dataclass
class ScoringInput:
    """
    Toutes les métriques nécessaires pour scorer une opportunité.
    Les champs optionnels (None) reçoivent des valeurs par défaut neutres.
    """
    # Core
    iv_percentile:      float           # 0-100
    theta_abs:          float           # Valeur absolue du thêta (ex: 0.07)
    delta:              float           # Delta absolu (ex: 0.15)

    # Liquidité
    open_interest:      float = 0.0     # Nombre de contrats ouverts
    bid_ask_spread:     float = 0.10    # Écart bid-ask en $

    # Risk/Reward
    credit_received:    float = 0.0     # Crédit net encaissé (spreads vendeur)
    max_risk:           float = 120.0   # Risque max ($ par contrat × 100)

    # Événements
    days_to_event:      Optional[float] = None  # Jours avant earnings/FOMC/etc.

    # Moneyness
    spot:               float = 100.0   # Prix du sous-jacent
    strike:             float = 100.0   # Strike considéré

    # Métadonnées (pour l'affichage)
    symbol:             str = ""
    strategy:           str = ""
    expiry:             str = ""


# ──────────────────────────────────────────────────────────────
# Dataclass : Résultat du scoring
# ──────────────────────────────────────────────────────────────

@dataclass
class ScoringResult:
    score:              int             # Score final 0-100
    label:              str             # "Forte", "Modérée", "Faible"
    details:            dict = field(default_factory=dict)  # Scores partiels
    recommendation:     str = ""        # Texte de recommandation

    def __str__(self) -> str:
        bar = "█" * (self.score // 5) + "░" * (20 - self.score // 5)
        lines = [
            f"  Score IA : {self.score}/100  [{bar}]  ({self.label})",
            f"  ├─ IV Percentile   : {self.details.get('iv_percentile', 0):.0f}%",
            f"  ├─ Thêta           : {self.details.get('theta_abs', 0):.3f} $/j",
            f"  ├─ Delta           : {self.details.get('delta', 0):.2f}",
            f"  ├─ Liquidité       : {self.details.get('liquidite_label', 'N/A')}",
            f"  ├─ Risk/Reward     : {self.details.get('risk_reward', 0):.2f}",
            f"  ├─ Événement       : {self.details.get('event_info', 'Aucun')}",
            f"  └─ Moneyness       : {self.details.get('moneyness_pct', 0):.1f}% OTM",
        ]
        if self.recommendation:
            lines.append(f"  💡 {self.recommendation}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Fonctions de normalisation
# ──────────────────────────────────────────────────────────────

def _norm_clamp(value: float, v_min: float, v_max: float) -> float:
    """Normalise value dans [0, 1] par rapport à [v_min, v_max]."""
    if v_max == v_min:
        return 0.5
    return max(0.0, min(1.0, (value - v_min) / (v_max - v_min)))


def _liquidite_score(open_interest: float, bid_ask_spread: float) -> float:
    """
    Score de liquidité composite :
      min(1, OI/1000) × (1 - spread_bid_ask/0.10)
    Pénalise les options illiquides (faible OI ou large spread).
    """
    oi_score  = min(1.0, open_interest / 1000.0)
    ba_score  = max(0.0, 1.0 - bid_ask_spread / 0.10)
    return oi_score * ba_score


def _event_penalty(days_to_event: Optional[float]) -> float:
    """
    Pénalité si un événement majeur est imminent (< 5 jours).
    Retourne un facteur de pénalité entre 0 et 1.
    0 = pénalité maximale (événement demain)
    1 = pas de pénalité
    """
    if days_to_event is None:
        return 0.0   # Pas d'événement connu → pas de pénalité
    if days_to_event <= 0:
        return 1.0   # Événement passé ou aujourd'hui → pénalité max
    if days_to_event >= 5:
        return max(0.0, 1.0 - days_to_event / 20.0)  # Pénalité décroissante au-delà de 5j
    return min(1.0, 5.0 / days_to_event - 1.0)        # Pénalité forte si < 5j


# ──────────────────────────────────────────────────────────────
# Fonction principale de scoring
# ──────────────────────────────────────────────────────────────

def compute_score(inp: ScoringInput) -> ScoringResult:
    """
    Calcule le score heuristique composite pour une opportunité.

    Formule :
    score = (
        0.20 * iv_percentile_norm
      + 0.15 * theta_abs_norm
      + 0.15 * (1 - delta_norm)        # faible delta = bien pour vendeur
      + 0.10 * liquidite_norm
      + 0.20 * min(risk_reward, 1.0)
      + 0.10 * (1 - penalty_event)
      + 0.10 * (1 - moneyness_distance_norm)
    ) × 100
    """
    W = config.SCORING_WEIGHTS

    # ── Feature 1 : IV Percentile ──────────────────────────────
    iv_norm = _norm_clamp(inp.iv_percentile, 0, 100)

    # ── Feature 2 : Thêta absolu ──────────────────────────────
    # Plage de référence : 0 → 0.12 $/j (seuil réaliste pour options < 120$)
    theta_norm = _norm_clamp(inp.theta_abs, 0.0, 0.12)

    # ── Feature 3 : Delta (plus faible est mieux pour vendeur) ──
    # Plage de référence : 0 → 0.40
    delta_abs = abs(inp.delta)
    delta_norm = _norm_clamp(delta_abs, 0.0, 0.40)

    # ── Feature 4 : Liquidité ──────────────────────────────────
    liq = _liquidite_score(inp.open_interest, inp.bid_ask_spread)
    liquidite_norm = liq  # Déjà dans [0, 1]

    # ── Feature 5 : Risk/Reward ─────────────────────────────────
    if inp.max_risk > 0:
        rr = inp.credit_received / inp.max_risk
    else:
        rr = 0.0
    rr_clamped = min(rr, 1.0)  # Plafonné à 1.0

    # ── Feature 6 : Événement (pénalité) ──────────────────────
    penalty = _event_penalty(inp.days_to_event)

    # ── Feature 7 : Distance au moneyness (OTM distance) ──────
    if inp.spot > 0:
        moneyness_dist = abs(inp.spot / inp.strike - 1.0)
    else:
        moneyness_dist = 0.0
    # Plus la distance est grande (OTM), mieux c'est pour vendeur
    # Plage : 0 → 0.12 (12 %) — au-delà, liquidité insuffisante
    moneyness_norm = _norm_clamp(moneyness_dist, 0.0, 0.12)

    # ── Score composite ────────────────────────────────────────
    raw = (
        W["iv_percentile"]      * iv_norm
        + W["theta_abs"]        * theta_norm
        + W["delta"]            * (1.0 - delta_norm)
        + W["liquidite"]        * liquidite_norm
        + W["risk_reward"]      * rr_clamped
        + W["days_to_event"]    * (1.0 - penalty)
        + W["moneyness_distance"] * (1.0 - moneyness_norm)
    )

    score = int(round(raw * 100))
    score = max(0, min(100, score))

    # ── Label ──────────────────────────────────────────────────
    if score >= config.SCORE_STRONG:
        label = "🟢 Forte opportunité"
    elif score >= config.SCORE_MODERATE:
        label = "🟡 Opportunité modérée"
    else:
        label = "🔴 Opportunité faible"

    # ── Liquidité label ────────────────────────────────────────
    if liq >= 0.70:
        liq_label = "Excellente"
    elif liq >= 0.40:
        liq_label = "Bonne"
    elif liq >= 0.20:
        liq_label = "Acceptable"
    else:
        liq_label = "Faible"

    # ── Événement info ─────────────────────────────────────────
    if inp.days_to_event is not None:
        event_info = (
            f"⚠️ Dans {int(inp.days_to_event)}j"
            if inp.days_to_event < 5
            else f"Dans {int(inp.days_to_event)}j"
        )
    else:
        event_info = "Aucun connu"

    # ── Recommandation ─────────────────────────────────────────
    rec_parts = []
    if inp.iv_percentile > 75:
        rec_parts.append("IV élevée → vente de premium favorisée")
    elif inp.iv_percentile < 25:
        rec_parts.append("IV basse → achat d'options à considérer")
    if delta_abs > 0.35:
        rec_parts.append("Delta élevé → risque directionnel important")
    if inp.days_to_event and inp.days_to_event < 5:
        rec_parts.append("Événement imminent → prudence accrue")
    if rr < 0.20:
        rec_parts.append("Risk/reward défavorable")
    elif rr > 0.50:
        rec_parts.append("Risk/reward attractif")

    recommendation = " | ".join(rec_parts) if rec_parts else "Conditions neutres"

    details = {
        "iv_percentile":   inp.iv_percentile,
        "theta_abs":       inp.theta_abs,
        "delta":           delta_abs,
        "liquidite_label": liq_label,
        "liquidite_score": round(liq, 3),
        "risk_reward":     round(rr, 3),
        "event_info":      event_info,
        "moneyness_pct":   round(moneyness_dist * 100, 2),
        # Contributions normalisées (pour debug)
        "_iv_contrib":        round(W["iv_percentile"] * iv_norm * 100, 2),
        "_theta_contrib":     round(W["theta_abs"] * theta_norm * 100, 2),
        "_delta_contrib":     round(W["delta"] * (1 - delta_norm) * 100, 2),
        "_liq_contrib":       round(W["liquidite"] * liquidite_norm * 100, 2),
        "_rr_contrib":        round(W["risk_reward"] * rr_clamped * 100, 2),
        "_event_contrib":     round(W["days_to_event"] * (1 - penalty) * 100, 2),
        "_money_contrib":     round(W["moneyness_distance"] * (1 - moneyness_norm) * 100, 2),
    }

    return ScoringResult(
        score=score,
        label=label,
        details=details,
        recommendation=recommendation,
    )


# ──────────────────────────────────────────────────────────────
# Utilitaire : scoring rapide depuis un dict
# ──────────────────────────────────────────────────────────────

def score_from_dict(data: dict) -> ScoringResult:
    """
    Permet de scorer depuis un dictionnaire plat (ex. depuis JSON).
    Utile pour l'assistant IA et les tests unitaires.
    """
    inp = ScoringInput(
        iv_percentile   = float(data.get("iv_percentile", 50)),
        theta_abs       = float(data.get("theta_abs", 0.05)),
        delta           = float(data.get("delta", 0.20)),
        open_interest   = float(data.get("open_interest", 500)),
        bid_ask_spread  = float(data.get("bid_ask_spread", 0.05)),
        credit_received = float(data.get("credit_received", 0.0)),
        max_risk        = float(data.get("max_risk", 120.0)),
        days_to_event   = data.get("days_to_event"),
        spot            = float(data.get("spot", 100.0)),
        strike          = float(data.get("strike", 100.0)),
        symbol          = str(data.get("symbol", "")),
        strategy        = str(data.get("strategy", "")),
        expiry          = str(data.get("expiry", "")),
    )
    return compute_score(inp)
