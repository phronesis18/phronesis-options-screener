"""
decision_engine.py — Moteur de décision pour la négociation
============================================================
Transforme chaque alerte en une fiche de décision complète et
actionnable, intégrant :
  1. Recommandation stratégique (strategy_advisor)
  2. Points d'entrée précis (prix limites, strikes optimaux)
  3. Plan de gestion de position (take profit, stop loss, roll)
  4. Check-list pré-trade (inspirée du Module 9.3 du cours)
  5. Score de conviction global (0–100)
  6. Fiche de trade imprimable

Ce module est le cœur de l'outil de prise de décision Phronesis.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import config
from scoring_ia import ScoringResult
from strategy_advisor import StrategyAdvisor, StrategyRecommendation, STRATEGY_CATALOG
from spread_builder import SpreadCandidate

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Dataclass : Fiche de décision complète
# ──────────────────────────────────────────────────────────────

@dataclass
class TradeDecision:
    """
    Fiche de décision complète prête à l'exécution.
    Combine le scoring IA + la recommandation stratégique +
    les paramètres d'entrée/sortie précis.
    """
    # Identification
    symbol:          str
    scan_time:       str = field(default_factory=lambda: datetime.now().isoformat())
    decision_id:     str = ""

    # Stratégie recommandée
    recommendation:  Optional[StrategyRecommendation] = None
    spread:          Optional[SpreadCandidate] = None

    # Conviction globale
    conviction_score: int = 0          # 0–100 (combo score IA + stratégie)
    conviction_label: str = ""
    go_no_go:         bool = False      # Décision finale go/no-go

    # Paramètres d'entrée précis
    entry_price_limit: Optional[float] = None   # Prix limite d'entrée
    entry_notes:       str = ""

    # Plan de sortie
    take_profit_pct:   float = 50.0    # % du crédit/profit max
    take_profit_price: Optional[float] = None
    stop_loss_pct:     float = 100.0   # % de la perte max (credit spreads)
    stop_loss_price:   Optional[float] = None
    max_dte_exit:      int = 21        # Fermer si DTE ≤ ce niveau

    # Gestion & Adjustements
    roll_trigger:      str = ""        # Condition pour roller
    adjustment_plan:   str = ""

    # Checklist pré-trade
    checklist:         Dict[str, bool] = field(default_factory=dict)

    # Métriques clés agrégées
    iv_rank:           Optional[float] = None
    risk_usd:          float = 0.0
    max_profit_usd:    float = 0.0
    breakeven:         Optional[float] = None
    prob_profit_est:   Optional[float] = None  # Estimation probabilité de profit

    def __str__(self) -> str:
        return self._render_full()

    def _render_full(self) -> str:
        """Rendu complet de la fiche de décision (console)."""
        strat_name = ""
        if self.recommendation:
            info = STRATEGY_CATALOG.get(self.recommendation.primary_strategy, {})
            strat_name = info.get("name", self.recommendation.primary_strategy)

        # Barre de conviction
        bar = "█" * (self.conviction_score // 5) + "░" * (20 - self.conviction_score // 5)
        go_icon = "✅ GO" if self.go_no_go else "🚫 NO-GO"

        lines = [
            f"\n  {'╔' + '═'*58 + '╗'}",
            f"  ║  🎯 FICHE DE DÉCISION — {self.symbol:<10}  {go_icon:<18} ║",
            f"  {'╠' + '═'*58 + '╣'}",
            f"  ║  Stratégie   : {strat_name:<42} ║",
            f"  ║  Conviction  : [{bar}] {self.conviction_score:3}/100     ║",
            f"  ║  IV Rank     : {str(f'{self.iv_rank:.0f}%') if self.iv_rank else 'N/A':<10}"
            f"  Risque max   : {self.risk_usd:6.0f}$          ║",
            f"  ║  Profit max  : {self.max_profit_usd:6.0f}$  "
            f"  Break-even   : {str(f'{self.breakeven:.2f}') if self.breakeven else 'N/A':<10}  ║",
            f"  {'╠' + '═'*58 + '╣'}",
        ]

        # Paramètres d'entrée
        if self.spread:
            s = self.spread
            lines += [
                f"  ║  📥 ENTRÉE",
                f"  ║  Legs    : {s.leg1_right}{s.leg1_strike:.0f} / {s.leg2_right}{s.leg2_strike:.0f}  "
                f"  Expiry : {s.expiry}  DTE: {s.dte}j     ║",
            ]
            if s.net_credit > 0:
                lines.append(
                    f"  ║  Crédit  : {s.net_credit:.2f}$  "
                    f"  Prix limite : {self.entry_price_limit or s.net_credit:.2f}$              ║"
                )
            else:
                lines.append(
                    f"  ║  Débit   : {s.net_debit:.2f}$  "
                    f"  Prix limite : {self.entry_price_limit or s.net_debit:.2f}$              ║"
                )

        # Plan de sortie
        lines += [
            f"  {'╠' + '═'*58 + '╣'}",
            f"  ║  📤 SORTIE",
            f"  ║  Take Profit : {self.take_profit_pct:.0f}% du profit max"
            f"  → {self.take_profit_price:.2f}$ " if self.take_profit_price
            else f"  ║  Take Profit : {self.take_profit_pct:.0f}% du profit max" + " " * 20 + "║",
            f"  ║  Stop Loss   : {self.stop_loss_pct:.0f}% de la perte max"
            + " " * 22 + "║",
            f"  ║  Exit temps  : Fermer si DTE ≤ {self.max_dte_exit}j"
            + " " * 23 + "║",
        ]

        if self.roll_trigger:
            lines.append(f"  ║  Roll        : {self.roll_trigger[:44]:<44}║")

        # Check-list
        lines.append(f"  {'╠' + '═'*58 + '╣'}")
        lines.append(f"  ║  ✅ CHECKLIST PRÉ-TRADE (Module 9.3)")
        for item, checked in self.checklist.items():
            icon = "☑" if checked else "☐"
            lines.append(f"  ║  {icon} {item[:54]:<54} ║")

        # Avertissements
        if self.recommendation and self.recommendation.warnings:
            lines.append(f"  {'╠' + '═'*58 + '╣'}")
            lines.append(f"  ║  ⚠️  POINTS DE VIGILANCE")
            for w in self.recommendation.warnings[:3]:
                lines.append(f"  ║  • {w[:54]:<54} ║")

        lines.append(f"  {'╚' + '═'*58 + '╝'}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Sérialise pour JSON/Sheets."""
        return {
            "decision_id":     self.decision_id,
            "symbol":          self.symbol,
            "scan_time":       self.scan_time,
            "strategy":        self.recommendation.primary_strategy if self.recommendation else "",
            "strategy_name":   STRATEGY_CATALOG.get(
                                self.recommendation.primary_strategy if self.recommendation else "",
                                {}).get("name", ""),
            "conviction":      self.conviction_score,
            "conviction_label": self.conviction_label,
            "go_no_go":        self.go_no_go,
            "iv_rank":         self.iv_rank,
            "risk_usd":        self.risk_usd,
            "max_profit_usd":  self.max_profit_usd,
            "breakeven":       self.breakeven,
            "take_profit_pct": self.take_profit_pct,
            "stop_loss_pct":   self.stop_loss_pct,
            "max_dte_exit":    self.max_dte_exit,
            "roll_trigger":    self.roll_trigger,
            "checklist_ok":    all(self.checklist.values()),
            "prob_profit_est": self.prob_profit_est,
            "entry_price_limit": self.entry_price_limit,
        }


# ──────────────────────────────────────────────────────────────
# Moteur de décision principal
# ──────────────────────────────────────────────────────────────

class DecisionEngine:
    """
    Transforme un SpreadCandidate + contexte de marché
    en une TradeDecision actionnable.
    """

    def __init__(self):
        self.advisor = StrategyAdvisor()

    def evaluate(
        self,
        spread:           SpreadCandidate,
        momentum_signal:  str = "neutral",
        momentum_bias:    str = "neutral",
        macro_signal:     str = "neutral",
        rsi:              Optional[float] = None,
        adx:              Optional[float] = None,
        days_to_event:    Optional[float] = None,
    ) -> TradeDecision:
        """
        Évalue un spread et retourne une fiche de décision complète.
        """
        iv_rank = spread.iv_percentile

        # ── 1. Recommandation stratégique ─────────────────────
        rec = self.advisor.recommend(
            symbol          = spread.symbol,
            iv_rank         = iv_rank,
            momentum_signal = momentum_signal,
            momentum_bias   = momentum_bias,
            macro_signal    = macro_signal,
            rsi             = rsi,
            adx             = adx,
            days_to_event   = days_to_event,
            spot_price      = spread.spot,
        )

        # ── 2. Score de conviction combiné ────────────────────
        ai_score   = spread.scoring.score if spread.scoring else 50
        strat_conf = rec.confidence * 100

        # Bonus si le spread correspond exactement à la stratégie recommandée
        strategy_match = self._strategy_matches_spread(
            rec.primary_strategy, spread.strategy
        )
        match_bonus = 10 if strategy_match else 0

        conviction = int(
            0.60 * ai_score +
            0.30 * strat_conf +
            0.10 * match_bonus * 10
        )
        conviction = max(0, min(100, conviction))

        # ── 3. Label de conviction ────────────────────────────
        if conviction >= 70:
            conv_label = "🟢 Conviction forte"
        elif conviction >= 50:
            conv_label = "🟡 Conviction modérée"
        else:
            conv_label = "🔴 Conviction faible"

        # ── 4. Go / No-Go ─────────────────────────────────────
        go_no_go = (
            conviction >= 50 and
            spread.risk_usd <= config.MAX_RISK_USD and
            (spread.scoring.score if spread.scoring else 0) >= config.SCORE_MODERATE
        )

        # ── 5. Plan de sortie ─────────────────────────────────
        tp_pct, sl_pct, dte_exit = self._exit_plan(spread.strategy, iv_rank)

        # Prix cibles
        if spread.net_credit > 0:
            tp_price = round(spread.net_credit * (1 - tp_pct / 100), 2)
        else:
            tp_price = round(spread.net_debit * (1 + tp_pct / 100), 2)

        # Prix d'entrée limite (légèrement meilleur que le mid)
        if spread.net_credit > 0:
            entry_limit = round(spread.net_credit * 0.95, 2)  # 5% de marge
        else:
            entry_limit = round(spread.net_debit * 1.05, 2)

        # ── 6. Trigger de roll ────────────────────────────────
        roll_trigger = self._roll_trigger(spread.strategy, spread)

        # ── 7. Probabilité de profit estimée ─────────────────
        prob_profit = self._estimate_prob_profit(spread)

        # ── 8. Check-list pré-trade (Module 9.3 du cours) ────
        checklist = self._build_checklist(spread, iv_rank, days_to_event)

        # ── 9. Construction de la décision ────────────────────
        decision = TradeDecision(
            symbol           = spread.symbol,
            decision_id      = f"{spread.symbol}_{spread.strategy}_{spread.expiry}",
            recommendation   = rec,
            spread           = spread,
            conviction_score = conviction,
            conviction_label = conv_label,
            go_no_go         = go_no_go,
            entry_price_limit= entry_limit,
            take_profit_pct  = tp_pct,
            take_profit_price= tp_price,
            stop_loss_pct    = sl_pct,
            max_dte_exit     = dte_exit,
            roll_trigger     = roll_trigger,
            checklist        = checklist,
            iv_rank          = iv_rank,
            risk_usd         = spread.risk_usd,
            max_profit_usd   = spread.max_profit * 100,
            breakeven        = spread.breakeven,
            prob_profit_est  = prob_profit,
        )

        logger.info(
            f"{spread.symbol} | {spread.strategy} | "
            f"Conviction={conviction}/100 | {'GO' if go_no_go else 'NO-GO'}"
        )
        return decision

    # ──────────────────────────────────────────────────────────
    # Helpers privés
    # ──────────────────────────────────────────────────────────

    def _strategy_matches_spread(self, recommended: str, actual: str) -> bool:
        """Vérifie si le spread correspond à la stratégie recommandée."""
        mapping = {
            "bull_put_spread":  ["bull_put"],
            "bear_call_spread": ["bear_call"],
            "bull_call_spread": ["bull_call"],
            "bear_put_spread":  ["bear_put"],
            "iron_condor":      ["bull_put", "bear_call"],
            "long_call":        ["bull_call"],
            "long_put":         ["bear_put"],
        }
        return actual in mapping.get(recommended, [recommended])

    def _exit_plan(
        self, strategy: str, iv_rank: Optional[float]
    ) -> Tuple[float, float, int]:
        """
        Retourne (take_profit_pct, stop_loss_pct, max_dte_exit).
        Basé sur les règles du cours (fermer à 50% du crédit = règle Tasty Trade).
        """
        # Stratégies crédit (règle d'or : fermer à 50% du crédit)
        if strategy in ("bull_put", "bear_call", "iron_condor"):
            return (50.0, 200.0, 21)

        # Spreads débit (fermer à +75% du profit max ou -50% du débit)
        elif strategy in ("bull_call", "bear_put"):
            return (75.0, 50.0, 10)

        # Long options (plus volatil)
        elif strategy in ("long_call", "long_put"):
            return (50.0, 50.0, 5)

        # Default
        return (50.0, 100.0, 21)

    def _roll_trigger(self, strategy: str, spread: SpreadCandidate) -> str:
        """Génère le trigger de roll approprié selon la stratégie."""
        if strategy in ("bull_put", "cash_secured_put"):
            return (
                f"Roller si spot < {spread.leg1_strike:.0f}$ "
                f"(strike vendu) → roll down and out, +30j DTE"
            )
        elif strategy in ("bear_call", "covered_call"):
            return (
                f"Roller si spot > {spread.leg1_strike:.0f}$ "
                f"(strike vendu) → roll up and out, +30j DTE"
            )
        elif strategy == "iron_condor":
            return (
                f"Ajuster si spot < {spread.leg1_strike:.0f}$ ou "
                f"> {spread.leg2_strike:.0f}$ → réduire la position ou roller"
            )
        return "Fermer si DTE ≤ 21j ou perte > 2× le crédit"

    def _estimate_prob_profit(self, spread: SpreadCandidate) -> Optional[float]:
        """
        Estimation simplifiée de la probabilité de profit.
        Pour les spreads crédit : basée sur le delta du short strike.
        """
        try:
            delta = abs(spread.leg1_delta)
            if spread.strategy in ("bull_put", "bear_call"):
                # Prob de profit ≈ 1 - |delta du strike short|
                return round((1 - delta) * 100, 1)
            elif spread.strategy in ("bull_call", "bear_put"):
                # Pour les débit spreads : prob plus faible
                return round(delta * 0.7 * 100, 1)
        except Exception:
            pass
        return None

    def _build_checklist(
        self,
        spread:        SpreadCandidate,
        iv_rank:       Optional[float],
        days_to_event: Optional[float],
    ) -> Dict[str, bool]:
        """
        Checklist pré-trade inspirée du Module 9.3 du cours.
        Chaque item est auto-évalué selon les données disponibles.
        """
        checklist = {}

        # 1. Hypothèse directionnelle identifiée
        checklist["Hypothèse directionnelle identifiée"] = True

        # 2. IV Rank vérifié
        checklist[f"IV Rank vérifié ({iv_rank:.0f}% → {'options chères' if (iv_rank or 0) > 40 else 'options bon marché'})"] = \
            iv_rank is not None

        # 3. Strike et expiration appropriés
        checklist[f"Strike OTM ({abs(spread.leg1_strike/spread.spot - 1)*100:.1f}% OTM)"] = \
            abs(spread.leg1_strike / spread.spot - 1) > 0.03

        checklist[f"DTE optimal ({spread.dte}j, fenêtre 14–45j)"] = \
            14 <= spread.dte <= 45

        # 4. P&L calculés
        checklist[f"Profit max : {spread.max_profit*100:.0f}$ | Perte max : {spread.risk_usd:.0f}$"] = True

        # 5. Risque ≤ 120$
        checklist[f"Risque ≤ 120$ (actuel : {spread.risk_usd:.0f}$)"] = \
            spread.risk_usd <= config.MAX_RISK_USD

        # 6. Pas d'earnings imminent
        no_event = days_to_event is None or days_to_event > 5
        checklist[f"Pas d'annonce de résultats imminente ({f'{int(days_to_event)}j' if days_to_event else 'N/A'})"] = \
            no_event

        # 7. Liquidité
        min_oi = min(spread.leg1_oi, spread.leg2_oi)
        ba_avg = ((spread.leg1_ask - spread.leg1_bid) + (spread.leg2_ask - spread.leg2_bid)) / 2
        checklist[f"Liquidité : OI min={min_oi}, bid-ask moy={ba_avg:.2f}$"] = \
            min_oi >= 100 and ba_avg <= 0.15

        # 8. Journal de trading
        checklist["Trade noté dans le journal de trading"] = False  # Toujours manuel

        # 9. Take profit et stop loss fixés
        checklist["Take profit et stop loss fixés AVANT l'entrée"] = True

        return checklist


# ──────────────────────────────────────────────────────────────
# Batch evaluation
# ──────────────────────────────────────────────────────────────

def evaluate_all_candidates(
    candidates: List[SpreadCandidate],
    momentum_signal: str = "neutral",
    momentum_bias:   str = "neutral",
    macro_signal:    str = "neutral",
    rsi:             Optional[float] = None,
    adx:             Optional[float] = None,
    days_to_event:   Optional[float] = None,
) -> List[TradeDecision]:
    """
    Évalue tous les candidats et retourne les décisions GO triées.
    """
    engine = DecisionEngine()
    decisions = []

    for spread in candidates:
        try:
            decision = engine.evaluate(
                spread           = spread,
                momentum_signal  = momentum_signal,
                momentum_bias    = momentum_bias,
                macro_signal     = macro_signal,
                rsi              = rsi,
                adx              = adx,
                days_to_event    = days_to_event,
            )
            decisions.append(decision)
        except Exception as e:
            logger.error(f"evaluate {spread.symbol}: {e}")

    # Trier : GO en premier, puis par conviction décroissante
    decisions.sort(
        key=lambda d: (not d.go_no_go, -d.conviction_score)
    )
    return decisions
