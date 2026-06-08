"""
strategy_advisor.py — Moteur de recommandation stratégique
===========================================================
Inspiré du cours "Les Options en Finance de Marché" du Club Phronesis.
Pour chaque opportunité détectée, ce module recommande la stratégie
optimale (parmi 12 stratégies) avec justification pédagogique complète.

Stratégies couvertes (du cours) :
  Court terme  : Long Call, Long Put, Long Straddle
  Moyen terme  : Bull Call Spread, Bear Put Spread, Iron Condor,
                 Cash-Secured Put, Bull Put Spread, Bear Call Spread
  Long terme   : LEAPS Call, LEAPS Put, Covered Call, Wheel Strategy

Logique de sélection :
  IV Rank + Momentum + Macro + Horizon → Stratégie recommandée
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Catalogue complet des stratégies (inspiré du cours)
# ──────────────────────────────────────────────────────────────

STRATEGY_CATALOG: Dict[str, Dict] = {

    # ── COURT TERME (< 30j) ───────────────────────────────────

    "long_call": {
        "name":       "Long Call Directionnel",
        "horizon":    "court",
        "bias":       "bullish",
        "iv_regime":  "low",          # IV Rank < 30 → options bon marché
        "risk":       "limited",      # Perte max = prime payée
        "reward":     "unlimited",
        "capital":    "low",
        "delta_target": (0.40, 0.60), # ATM/légèrement ITM
        "dte_range":  (10, 21),
        "description": (
            "Achat d'un Call ATM ou légèrement ITM. "
            "Idéal sur breakout technique confirmé avec volume croissant. "
            "Objectif : +50% de gain. Stop : -50% de la prime."
        ),
        "conditions": [
            "Tendance haussière forte, volume croissant",
            "IV Rank < 30 (options bon marché)",
            "Catalyseur identifiable (breakout, support, annonce)",
            "RSI non en zone de surachat (< 65)",
        ],
        "rules": [
            "Strike : ATM ou delta 0.40–0.60 (légèrement ITM)",
            "Expiration : 10–21 jours",
            "Take Profit : +50% de la prime",
            "Stop Loss : -50% de la prime",
            "Ne pas dépasser 5% du capital total",
        ],
        "risk_label": "Limité (prime)",
        "module_ref": "Module 3.2",
    },

    "long_put": {
        "name":       "Long Put Directionnel",
        "horizon":    "court",
        "bias":       "bearish",
        "iv_regime":  "low",
        "risk":       "limited",
        "reward":     "high",
        "capital":    "low",
        "delta_target": (-0.60, -0.40),
        "dte_range":  (10, 21),
        "description": (
            "Achat d'un Put ATM ou légèrement ITM sur tendance baissière. "
            "Profit si le sous-jacent baisse plus que la prime payée."
        ),
        "conditions": [
            "Tendance baissière confirmée, nouvelles négatives",
            "IV Rank < 30 (options bon marché)",
            "RSI en zone de surachat (> 65) ou divergence baissière",
            "Support clé cassé",
        ],
        "rules": [
            "Strike : ATM ou delta -0.40 à -0.60",
            "Expiration : 10–21 jours",
            "Take Profit : +50% de la prime",
            "Stop Loss : -50% de la prime",
        ],
        "risk_label": "Limité (prime)",
        "module_ref": "Module 3.2",
    },

    "long_straddle": {
        "name":       "Long Straddle (Événement Binaire)",
        "horizon":    "court",
        "bias":       "neutral_volatile",
        "iv_regime":  "low_pre_event",  # Acheter AVANT la hausse d'IV
        "risk":       "limited",
        "reward":     "unlimited",
        "capital":    "medium",
        "delta_target": (0.48, 0.52),   # ATM exact
        "dte_range":  (5, 15),
        "description": (
            "Achat simultané d'un Call ET d'un Put ATM, même expiration. "
            "Profitable si grand mouvement dans n'importe quelle direction. "
            "À utiliser AVANT les earnings ou annonces macro."
        ),
        "conditions": [
            "Événement binaire imminent (earnings, FDA, FOMC)",
            "IV Rank faible AVANT l'événement (IV crush risk après)",
            "Sous-jacent historiquement volatil post-annonces",
            "Le mouvement attendu > somme des deux primes",
        ],
        "rules": [
            "Strike : exactement ATM (delta ≈ 0.50)",
            "Expiration : 5–15 jours APRÈS l'événement",
            "Acheter 1–5 jours AVANT l'événement (pas trop tôt)",
            "Fermer avant expiration si mouvement insuffisant",
            "Risque = Call prime + Put prime",
        ],
        "risk_label": "Limité (2 primes)",
        "module_ref": "Module 3.3",
    },

    # ── MOYEN TERME (1–6 mois) ────────────────────────────────

    "bull_call_spread": {
        "name":       "Bull Call Spread",
        "horizon":    "moyen",
        "bias":       "bullish",
        "iv_regime":  "medium",        # IV Rank 30–60
        "risk":       "limited",
        "reward":     "capped",
        "capital":    "low",           # Idéal < 120$
        "delta_target": (0.35, 0.55),
        "dte_range":  (21, 60),
        "description": (
            "Achat d'un Call bas strike + Vente d'un Call strike plus haut. "
            "Coût réduit vs Long Call, profit plafonné à la largeur du spread. "
            "Idéal pour les petits comptes avec capital limité."
        ),
        "conditions": [
            "Biais haussier modéré (pas de tendance explosive)",
            "IV Rank 30–60 (spread directionnel neutre)",
            "Sous-jacent au-dessus de sa MA50",
            "Support technique tenu",
        ],
        "rules": [
            "Strike long : ATM ou légèrement OTM (delta 0.40–0.55)",
            "Strike short : OTM (2–5% au-dessus du spot)",
            "Largeur spread : 3–5$ pour coût < 120$",
            "DTE : 21–45 jours optimal",
            "Fermer à 50–75% du profit max",
        ],
        "risk_label": "Limité (débit net)",
        "module_ref": "Module 4.1",
    },

    "bear_put_spread": {
        "name":       "Bear Put Spread",
        "horizon":    "moyen",
        "bias":       "bearish",
        "iv_regime":  "medium",
        "risk":       "limited",
        "reward":     "capped",
        "capital":    "low",
        "delta_target": (-0.55, -0.35),
        "dte_range":  (21, 60),
        "description": (
            "Achat d'un Put haut strike + Vente d'un Put bas strike. "
            "Inverse du Bull Call Spread. Profit si le sous-jacent baisse "
            "modérément jusqu'au strike vendu."
        ),
        "conditions": [
            "Biais baissier modéré",
            "IV Rank 30–60",
            "Sous-jacent sous sa MA50",
            "Résistance technique tenue",
        ],
        "rules": [
            "Strike long : ATM ou légèrement OTM (delta -0.40 à -0.55)",
            "Strike short : OTM (2–5% sous le spot)",
            "Largeur spread : 3–5$",
            "DTE : 21–45 jours",
        ],
        "risk_label": "Limité (débit net)",
        "module_ref": "Module 4.2",
    },

    "iron_condor": {
        "name":       "Iron Condor",
        "horizon":    "moyen",
        "bias":       "neutral",
        "iv_regime":  "high",          # IV Rank > 30–60 (idéalement > 50)
        "risk":       "limited",
        "reward":     "capped_credit",
        "capital":    "medium",
        "delta_target": (0.15, 0.25),  # Chaque aile
        "dte_range":  (21, 45),
        "description": (
            "Bull Put Spread + Bear Call Spread. On collecte des primes des deux côtés. "
            "Profitable si le sous-jacent reste dans le range entre les deux spreads. "
            "Idéal sur ETF larges (SPY, QQQ, IWM) en marché calme."
        ),
        "conditions": [
            "Marché en range, faible volatilité directionnelle attendue",
            "IV Rank > 30 (options correctement valorisées)",
            "ADX < 20 (tendance faible)",
            "VIX stable ou légèrement élevé",
            "ETF larges préférés (SPY, QQQ, IWM)",
        ],
        "rules": [
            "Ailes delta 0.15–0.25 OTM (chaque côté)",
            "Largeur ailes : 3–5$ de large",
            "Crédit net ≥ 25% de la largeur de chaque aile",
            "Fermer à 50% du crédit reçu (règle d'or Tasty Trade)",
            "DTE : 21–45 jours",
            "Max loss = largeur d'une aile - crédit total",
        ],
        "risk_label": "Limité (largeur aile - crédit)",
        "module_ref": "Module 4.3",
    },

    "cash_secured_put": {
        "name":       "Cash-Secured Put",
        "horizon":    "moyen",
        "bias":       "bullish_neutral",
        "iv_regime":  "high",          # IV Rank > 40
        "risk":       "substantial",   # Risque = strike - prime
        "reward":     "capped_credit",
        "capital":    "high",          # Besoin du cash = strike × 100
        "delta_target": (-0.30, -0.20),
        "dte_range":  (14, 45),
        "description": (
            "Vendre un Put OTM en conservant le cash pour acheter les actions si exercé. "
            "Génère un revenu immédiat. Si exercé, on achète l'action à prix réduit "
            "(strike - prime). Étape 1 de la Wheel Strategy."
        ),
        "conditions": [
            "Action ou ETF qu'on voudrait posséder à prix réduit",
            "IV Rank > 40 (prime suffisante)",
            "Tendance haussière de fond ou support solide",
            "Capital disponible = strike × 100",
        ],
        "rules": [
            "Strike : 5–10% OTM (delta -0.20 à -0.30)",
            "DTE : 14–45 jours",
            "Fermer à 50% du crédit reçu",
            "Roller si prix approche du strike (roll down and out)",
            "Maximum 3–5 positions simultanées",
        ],
        "risk_label": "Élevé (strike × 100 - crédit)",
        "module_ref": "Module 4.4",
    },

    "bull_put_spread": {
        "name":       "Bull Put Spread (Credit)",
        "horizon":    "moyen",
        "bias":       "bullish_neutral",
        "iv_regime":  "high",
        "risk":       "limited",
        "reward":     "capped_credit",
        "capital":    "low",           # Marge = largeur - crédit
        "delta_target": (-0.25, -0.15),
        "dte_range":  (14, 45),
        "description": (
            "Vente d'un Put OTM + Achat d'un Put encore plus OTM (protection). "
            "Encaisse une prime nette. Profitable tant que le sous-jacent "
            "reste au-dessus du strike vendu."
        ),
        "conditions": [
            "Biais haussier ou neutre",
            "IV Rank > 40 (prime suffisante pour justifier le trade)",
            "Support technique solide sous le strike vendu",
            "RSI non en survente (> 35)",
        ],
        "rules": [
            "Strike short (vendu) : 5–8% OTM (delta -0.20 à -0.30)",
            "Strike long (acheté) : 2–5$ plus bas que le short",
            "Crédit ≥ 20% de la largeur du spread",
            "Fermer à 50% du crédit ou 21 DTE",
            "Max risk = (largeur - crédit) × 100 ≤ 120$",
        ],
        "risk_label": "Limité (marge ≤ 120$)",
        "module_ref": "Module 4 + Partie Income",
    },

    "bear_call_spread": {
        "name":       "Bear Call Spread (Credit)",
        "horizon":    "moyen",
        "bias":       "bearish_neutral",
        "iv_regime":  "high",
        "risk":       "limited",
        "reward":     "capped_credit",
        "capital":    "low",
        "delta_target": (0.15, 0.25),
        "dte_range":  (14, 45),
        "description": (
            "Vente d'un Call OTM + Achat d'un Call encore plus OTM. "
            "Encaisse une prime nette. Profitable tant que le sous-jacent "
            "reste sous le strike vendu."
        ),
        "conditions": [
            "Biais baissier ou neutre",
            "IV Rank > 40",
            "Résistance technique solide au-dessus du strike vendu",
            "RSI en zone de surachat (> 65) ou momentum baissier",
        ],
        "rules": [
            "Strike short (vendu) : 5–8% OTM au-dessus (delta 0.20–0.30)",
            "Strike long (acheté) : 2–5$ plus haut que le short",
            "Crédit ≥ 20% de la largeur",
            "Fermer à 50% du crédit ou 21 DTE",
            "Max risk ≤ 120$",
        ],
        "risk_label": "Limité (marge ≤ 120$)",
        "module_ref": "Module 4 + Partie Income",
    },

    # ── LONG TERME (6 mois – 2+ ans) ─────────────────────────

    "leaps_call": {
        "name":       "LEAPS Call (Long Terme)",
        "horizon":    "long",
        "bias":       "bullish_strong",
        "iv_regime":  "low",           # Acheter quand IV basse
        "risk":       "limited",
        "reward":     "very_high",
        "capital":    "medium",
        "delta_target": (0.60, 0.80),  # ITM pour moins de décote temporelle
        "dte_range":  (365, 730),
        "description": (
            "Call avec expiration 1–3 ans (LEAPS). Levier x4–x10 vs achat d'actions. "
            "Idéal pour parier sur une grande tendance long terme. "
            "Exemple : AAPL à 180$, LEAPS Call 190$ Jan 2027 ≈ 15$ (1 500$ par contrat)."
        ),
        "conditions": [
            "Conviction forte sur la tendance long terme",
            "IV Rank faible (LEAPS bon marché)",
            "Fondamentaux solides de l'entreprise",
            "Capital disponible pour tenir 12–24 mois",
        ],
        "rules": [
            "Strike : légèrement ITM (delta 0.60–0.80) pour minimiser la décote temporelle",
            "Expiration : minimum 1 an",
            "Position size : max 10% du portefeuille",
            "Ne pas vendre avant 6 mois (laisser la thèse se déployer)",
            "Exit : si thèse invalidée ou +100% de gain",
        ],
        "risk_label": "Limité (prime totale)",
        "module_ref": "Module 5.1",
    },

    "covered_call": {
        "name":       "Covered Call",
        "horizon":    "long",
        "bias":       "neutral_income",
        "iv_regime":  "high",          # Vendre quand IV élevée
        "risk":       "opportunity",   # Risque = manquer une hausse
        "reward":     "capped",
        "capital":    "very_high",     # Besoin de 100 actions
        "delta_target": (0.25, 0.40),
        "dte_range":  (14, 45),
        "description": (
            "Vendre un Call OTM contre 100 actions déjà détenues. "
            "Génère un revenu mensuel/hebdomadaire. "
            "Étape 2 de la Wheel Strategy. Transforme des actions dormantes en revenus."
        ),
        "conditions": [
            "Déjà propriétaire de 100 actions",
            "IV Rank élevé (prime suffisante)",
            "Pas d'attente de grande hausse à court terme",
            "Sous-jacent stable ou légèrement haussier",
        ],
        "rules": [
            "Strike : 5–10% OTM (delta 0.25–0.40)",
            "DTE : 14–45 jours",
            "Fermer à 50% du crédit",
            "Roller si prix approche du strike (roll up and out)",
            "Ne jamais vendre un Call ITM",
        ],
        "risk_label": "Opportunité manquée si hausse forte",
        "module_ref": "Module 5.2",
    },

    "wheel_strategy": {
        "name":       "Wheel Strategy (Roue)",
        "horizon":    "long",
        "bias":       "bullish_income",
        "iv_regime":  "high",
        "risk":       "substantial",
        "reward":     "regular_income",
        "capital":    "very_high",
        "delta_target": (-0.30, -0.20),
        "dte_range":  (14, 45),
        "description": (
            "Cycle : Cash-Secured Put → si exercé → Covered Call → répéter. "
            "Génère des revenus réguliers et optimise les points d'entrée. "
            "Idéal sur ETF liquides (SPY, QQQ) ou actions de conviction."
        ),
        "conditions": [
            "Conviction sur le sous-jacent sur le long terme",
            "IV Rank > 40 régulièrement",
            "Capital suffisant (strike × 100)",
            "Patience et discipline pour le cycle complet",
        ],
        "rules": [
            "Étape 1 : Vendre CSP à delta -0.20 à -0.30",
            "Si exercé : Étape 2 : Vendre CC à delta 0.25–0.40",
            "Toujours rester sur des sous-jacents qu'on accepte de détenir",
            "Ne pas interrompre le cycle sous l'émotion",
        ],
        "risk_label": "Élevé (possession d'actions possible)",
        "module_ref": "Module 5.3",
    },
}


# ──────────────────────────────────────────────────────────────
# Dataclass : Recommandation
# ──────────────────────────────────────────────────────────────

@dataclass
class StrategyRecommendation:
    """Recommandation stratégique complète pour un sous-jacent."""
    symbol:              str
    primary_strategy:    str               # Clé dans STRATEGY_CATALOG
    alternative_strategy: Optional[str]   # Deuxième meilleur choix
    confidence:          float             # 0-1
    rationale:           List[str]         # Pourquoi cette stratégie
    warnings:            List[str]         # Points de vigilance
    action_plan:         List[str]         # Plan d'action concret
    market_context:      Dict              # Snapshot des conditions
    iv_rank:             Optional[float]
    momentum_bias:       str
    horizon:             str               # "court", "moyen", "long"

    @property
    def strategy_info(self) -> Dict:
        return STRATEGY_CATALOG.get(self.primary_strategy, {})

    @property
    def alt_strategy_info(self) -> Optional[Dict]:
        if self.alternative_strategy:
            return STRATEGY_CATALOG.get(self.alternative_strategy)
        return None

    def __str__(self) -> str:
        info = self.strategy_info
        conf_bar = "★" * int(self.confidence * 5) + "☆" * (5 - int(self.confidence * 5))
        lines = [
            f"\n  {'═'*55}",
            f"  🎯 RECOMMANDATION STRATÉGIQUE — {self.symbol}",
            f"  {'═'*55}",
            f"  📋 Stratégie principale : {info.get('name', self.primary_strategy)}",
            f"  🎓 Référence cours      : {info.get('module_ref', 'N/A')}",
            f"  📊 Horizon              : {self.horizon.upper()}",
            f"  ⭐ Confiance            : {conf_bar} ({self.confidence:.0%})",
            f"  ⚠️  Risque              : {info.get('risk_label', 'N/A')}",
            f"",
            f"  📖 Description :",
            f"     {info.get('description', '')}",
            f"",
            f"  ✅ Conditions réunies :",
        ]
        for r in self.rationale:
            lines.append(f"     • {r}")

        if self.warnings:
            lines.append(f"\n  ⚠️  Points de vigilance :")
            for w in self.warnings:
                lines.append(f"     • {w}")

        lines.append(f"\n  🔧 Plan d'action :")
        for i, step in enumerate(self.action_plan, 1):
            lines.append(f"     {i}. {step}")

        if self.alternative_strategy:
            alt = self.alt_strategy_info
            lines.append(
                f"\n  💡 Alternative : {alt.get('name', self.alternative_strategy)} "
                f"({alt.get('module_ref', '')})"
            )

        lines.append(f"  {'─'*55}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Moteur de recommandation principal
# ──────────────────────────────────────────────────────────────

class StrategyAdvisor:
    """
    Recommande la stratégie optimale selon les conditions de marché.
    Basé sur la matrice IV Rank × Momentum × Horizon du cours Phronesis.

    Matrice de décision (tirée du Module 2.3 et 2.4 du cours) :
    ─────────────────────────────────────────────────────────────
    IV Rank < 20  + Bullish  → Long Call
    IV Rank < 20  + Bearish  → Long Put
    IV Rank < 20  + Événement→ Long Straddle
    IV Rank 20–40 + Bullish  → Bull Call Spread
    IV Rank 20–40 + Bearish  → Bear Put Spread
    IV Rank 40–60 + Bullish  → Bull Put Spread (crédit)
    IV Rank 40–60 + Bearish  → Bear Call Spread (crédit)
    IV Rank 40–60 + Neutre   → Iron Condor
    IV Rank > 60  + Bullish  → Cash-Secured Put ou Bull Put Spread
    IV Rank > 60  + Neutre   → Iron Condor ou Short Strangle
    Long terme    + Bullish  → LEAPS Call
    Long terme    + Income   → Covered Call / Wheel
    ─────────────────────────────────────────────────────────────
    """

    def recommend(
        self,
        symbol:           str,
        iv_rank:          Optional[float],
        momentum_signal:  str,      # "bullish", "bearish", "neutral"
        momentum_bias:    str,      # "call_buyer", "put_buyer", "seller", "neutral"
        macro_signal:     str,      # "bullish", "bearish", "neutral"
        rsi:              Optional[float] = None,
        adx:              Optional[float] = None,
        days_to_event:    Optional[float] = None,
        holds_shares:     bool = False,   # Détient déjà les 100 actions
        horizon_pref:     str = "moyen",  # "court", "moyen", "long"
        spot_price:       Optional[float] = None,
    ) -> StrategyRecommendation:
        """
        Retourne la recommandation stratégique optimale.
        """
        iv = iv_rank or 50.0  # Valeur neutre par défaut

        rationale  = []
        warnings   = []
        action     = []

        # ── Contexte marché ────────────────────────────────────
        context = {
            "iv_rank":        iv,
            "momentum":       momentum_signal,
            "macro":          macro_signal,
            "rsi":            rsi,
            "adx":            adx,
            "days_to_event":  days_to_event,
            "holds_shares":   holds_shares,
        }

        # ── Sélection de la stratégie ──────────────────────────
        strategy, alt, confidence, horizon = self._select_strategy(
            iv, momentum_signal, momentum_bias, macro_signal,
            rsi, adx, days_to_event, holds_shares, horizon_pref
        )

        info = STRATEGY_CATALOG[strategy]

        # ── Construction de la rationale ──────────────────────
        rationale.extend(
            self._build_rationale(strategy, iv, momentum_signal,
                                   macro_signal, rsi, adx)
        )

        # ── Avertissements ────────────────────────────────────
        warnings.extend(
            self._build_warnings(strategy, iv, days_to_event,
                                  rsi, adx, spot_price)
        )

        # ── Plan d'action ─────────────────────────────────────
        action.extend(info.get("rules", []))

        return StrategyRecommendation(
            symbol=symbol,
            primary_strategy=strategy,
            alternative_strategy=alt,
            confidence=confidence,
            rationale=rationale,
            warnings=warnings,
            action_plan=action,
            market_context=context,
            iv_rank=iv,
            momentum_bias=momentum_bias,
            horizon=horizon,
        )

    # ──────────────────────────────────────────────────────────
    # Moteur de sélection
    # ──────────────────────────────────────────────────────────

    def _select_strategy(
        self, iv, momentum, bias, macro,
        rsi, adx, days_to_event, holds_shares, horizon_pref
    ) -> Tuple[str, Optional[str], float, str]:
        """
        Retourne (strategy_key, alt_key, confidence 0-1, horizon).
        Matrice inspirée du Module 2.3 et 2.4 du cours.
        """

        # ── Cas spéciaux prioritaires ──────────────────────────

        # 1. Covered Call si on détient les actions
        if holds_shares and iv > 35:
            return "covered_call", "wheel_strategy", 0.85, "long"

        # 2. Long Straddle si événement imminent + IV encore basse
        if days_to_event and days_to_event <= 7 and iv < 50:
            return "long_straddle", "long_call", 0.70, "court"

        # 3. Long terme si horizon_pref = "long"
        if horizon_pref == "long":
            if momentum in ("bullish",) and iv < 40:
                return "leaps_call", "bull_call_spread", 0.75, "long"
            elif momentum == "bullish" and iv >= 40:
                return "wheel_strategy", "cash_secured_put", 0.72, "long"

        # ── Matrice IV Rank × Momentum ─────────────────────────

        # IV TRÈS BASSE (< 20) → ACHETER des options
        if iv < 20:
            if momentum == "bullish" or bias == "call_buyer":
                conf = 0.80 + 0.10 * (momentum == "bullish" and macro == "bullish")
                return "long_call", "bull_call_spread", min(conf, 0.90), "court"
            elif momentum == "bearish" or bias == "put_buyer":
                return "long_put", "bear_put_spread", 0.78, "court"
            else:
                # Neutre + IV basse → spreads directionnels à faible coût
                return "bull_call_spread", "bear_put_spread", 0.55, "moyen"

        # IV BASSE-NEUTRE (20–35) → SPREADS DÉBIT directionnels
        elif iv < 35:
            if momentum == "bullish" or macro == "bullish":
                return "bull_call_spread", "long_call", 0.72, "moyen"
            elif momentum == "bearish" or macro == "bearish":
                return "bear_put_spread", "long_put", 0.70, "moyen"
            else:
                # Range + IV neutre → Iron Condor basique
                return "iron_condor", "bull_put_spread", 0.58, "moyen"

        # IV NEUTRE-HAUTE (35–60) → SPREADS CRÉDIT (vendre la prime)
        elif iv < 60:
            if momentum == "bullish":
                if adx and adx < 20:
                    # Pas de tendance forte → vendre le Put
                    return "bull_put_spread", "iron_condor", 0.75, "moyen"
                else:
                    return "bull_put_spread", "bull_call_spread", 0.72, "moyen"
            elif momentum == "bearish":
                if adx and adx < 20:
                    return "bear_call_spread", "iron_condor", 0.75, "moyen"
                else:
                    return "bear_call_spread", "bear_put_spread", 0.70, "moyen"
            else:
                # Range → Iron Condor idéal
                adx_low = (adx or 25) < 20
                conf = 0.82 if adx_low else 0.68
                return "iron_condor", "bull_put_spread", conf, "moyen"

        # IV TRÈS HAUTE (> 60) → VENDRE MASSIVEMENT la prime
        else:
            if momentum == "bullish" or macro == "bullish":
                # Haussier + IV élevée → CSP ou Bull Put
                conf = 0.80
                return "bull_put_spread", "cash_secured_put", conf, "moyen"
            elif momentum == "bearish":
                return "bear_call_spread", "iron_condor", 0.78, "moyen"
            else:
                # IV très élevée + neutre → Iron Condor large
                return "iron_condor", "bear_call_spread", 0.85, "moyen"

    def _build_rationale(
        self, strategy, iv, momentum, macro, rsi, adx
    ) -> List[str]:
        """Construit la liste de justifications en langage naturel."""
        reasons = []
        info = STRATEGY_CATALOG[strategy]

        # IV Rank
        if iv < 20:
            reasons.append(f"IV Rank faible ({iv:.0f}%) → options bon marché → favorable à l'achat")
        elif iv < 40:
            reasons.append(f"IV Rank neutre ({iv:.0f}%) → spreads directionnels appropriés")
        elif iv < 60:
            reasons.append(f"IV Rank élevé ({iv:.0f}%) → vente de premium justifiée")
        else:
            reasons.append(f"IV Rank très élevé ({iv:.0f}%) → excellent environnement pour vendeur")

        # Momentum
        if momentum == "bullish":
            reasons.append("Momentum haussier confirmé → biais acheteur/vendeur put")
        elif momentum == "bearish":
            reasons.append("Momentum baissier confirmé → biais acheteur put/vendeur call")
        else:
            reasons.append("Momentum neutre → range market → stratégies income/neutres")

        # Macro
        if macro == "bullish":
            reasons.append("Régime macro haussier (VIX bas, SPY au-dessus MA50)")
        elif macro == "bearish":
            reasons.append("Régime macro défensif (VIX élevé ou SPY sous MA50)")

        # RSI
        if rsi:
            if rsi < 35:
                reasons.append(f"RSI en survente ({rsi:.0f}) → potentiel rebond → vente de Put OTM")
            elif rsi > 65:
                reasons.append(f"RSI en surachat ({rsi:.0f}) → attention aux baisses → vente de Call OTM")
            else:
                reasons.append(f"RSI neutre ({rsi:.0f}) → zone équilibrée")

        # ADX
        if adx:
            if adx < 20:
                reasons.append(f"ADX faible ({adx:.0f}) → pas de tendance forte → range market favorable à l'Iron Condor")
            elif adx > 25:
                reasons.append(f"ADX fort ({adx:.0f}) → tendance établie → spreads directionnels")

        # Conditions spécifiques de la stratégie
        for cond in info.get("conditions", [])[:2]:
            reasons.append(cond)

        return reasons

    def _build_warnings(
        self, strategy, iv, days_to_event, rsi, adx, spot
    ) -> List[str]:
        """Construit les avertissements pertinents."""
        warns = []

        # Événement imminent
        if days_to_event and days_to_event <= 5:
            warns.append(
                f"⚠️ Événement majeur dans {int(days_to_event)}j → "
                "risque d'IV crush post-annonce pour vendeurs de premium"
            )

        # IV très élevée pour acheter
        if strategy in ("long_call", "long_put") and iv > 50:
            warns.append(
                f"IV Rank élevé ({iv:.0f}%) → options chères → "
                "risque d'IV crush important. Préférer un spread."
            )

        # RSI extremes
        if rsi:
            if rsi > 75 and strategy in ("long_call", "bull_call_spread"):
                warns.append(f"RSI très élevé ({rsi:.0f}) → risque de correction à court terme")
            if rsi < 25 and strategy in ("long_put", "bear_put_spread"):
                warns.append(f"RSI très bas ({rsi:.0f}) → risque de rebond technique")

        # Iron Condor avec tendance
        if strategy == "iron_condor" and adx and adx > 25:
            warns.append(
                f"ADX élevé ({adx:.0f}) → tendance en cours → "
                "Iron Condor risqué, élargir les ailes ou réduire la taille"
            )

        # Contrainte 120$
        warns.append(
            "Respecter la contrainte Phronesis : risque max 120$ par position"
        )

        # Checklist du cours (Module 9.3)
        warns.append(
            "Checklist : vérifier OI > 100, bid-ask étroit, "
            "noter dans le journal de trading avant d'entrer"
        )

        return warns


# ──────────────────────────────────────────────────────────────
# Fonctions utilitaires
# ──────────────────────────────────────────────────────────────

def get_strategy_description(strategy_key: str) -> str:
    """Retourne la description complète d'une stratégie (pour l'assistant IA)."""
    info = STRATEGY_CATALOG.get(strategy_key)
    if not info:
        return f"Stratégie '{strategy_key}' non trouvée."

    lines = [
        f"# {info['name']} ({info.get('module_ref', '')})",
        f"\n{info['description']}",
        f"\n## Conditions idéales",
    ]
    for c in info.get("conditions", []):
        lines.append(f"- {c}")
    lines.append("\n## Règles de gestion")
    for r in info.get("rules", []):
        lines.append(f"- {r}")
    lines.append(f"\nProfil de risque : {info['risk_label']}")
    return "\n".join(lines)


def list_all_strategies() -> str:
    """Liste toutes les stratégies disponibles (pour l'assistant IA)."""
    lines = ["## Stratégies disponibles dans le screener Phronesis\n"]
    horizons = {"court": "Court terme (< 30j)", "moyen": "Moyen terme (1–6 mois)",
                "long": "Long terme (6 mois – 2 ans)"}
    for h_key, h_label in horizons.items():
        lines.append(f"\n### {h_label}")
        for k, v in STRATEGY_CATALOG.items():
            if v["horizon"] == h_key:
                lines.append(f"- **{v['name']}** ({v.get('module_ref', '')}) : {v['risk_label']}")
    return "\n".join(lines)
