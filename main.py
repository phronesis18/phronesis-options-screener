"""
main.py — Orchestrateur principal du screener Phronesis v3.0
=============================================================
Nouveautés v3.0 :
  - Univers 1800+ sous-jacents (universe.py)
  - Moteur de recommandation stratégique (strategy_advisor.py)
  - Fiche de décision complète (decision_engine.py)
  - Scan parallèle par batches pour les grands univers
  - Mode --decide pour afficher les fiches de décision

Usage :
  python main.py                                    # Scan watchlist
  python main.py --symbols AAPL MSFT SPY            # Scan ciblé
  python main.py --universe full                    # Scan 1800 actifs
  python main.py --universe etf                     # ETFs uniquement
  python main.py --universe priority                # Top 50 prioritaires
  python main.py --universe full --max 200          # Limiter à 200
  python main.py --ask "Explique le thêta"          # Assistant IA
  python main.py --decide                           # Fiches de décision
  python main.py --chat                             # Mode conversationnel
  python main.py --import-iv data/historical_iv.csv
  python main.py --strategies                       # Lister les stratégies
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import List, Optional, Dict

import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

try:
    from rich.console import Console
    from rich.panel   import Panel
    from rich.table   import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    class _FallbackConsole:
        def print(self, *a, **k): print(*a)
        def rule(self, t=""): print("─" * 60, t)
    console = _FallbackConsole()

from ib_connector          import IBConnector
from data_fetcher          import get_option_chain, get_atm_iv, get_vix
from models                import MacroModel, ValueModel, IncomeModel, MomentumModel
from spread_builder        import SpreadBuilder, SpreadCandidate
from iv_percentile_storage import import_csv_to_db, compute_iv_percentile, save_iv
from ai_assistant          import PhronesisAssistant, quick_ask
from scoring_ia            import score_from_dict
from strategy_advisor      import StrategyAdvisor, list_all_strategies, get_strategy_description
from decision_engine       import DecisionEngine, TradeDecision, evaluate_all_candidates
from universe              import get_full_universe, get_priority_watchlist, get_etf_universe, universe_stats


BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║   🧠 PHRONESIS OPTIONS SCREENER — v3.0                          ║
║   1800+ Actifs × 4 Piliers × IA × Recommandation Stratégique    ║
╚══════════════════════════════════════════════════════════════════╝
"""

BATCH_SIZE     = 20    # Symboles par batch (anti rate-limit IBKR)
BATCH_PAUSE    = 3.0   # Secondes entre batches


class PhronesisScreener:
    """Orchestrateur principal v3.0."""

    def __init__(self):
        self.connector      = IBConnector()
        self.macro_model    = MacroModel()
        self.value_model    = ValueModel()
        self.income_model   = IncomeModel()
        self.momentum_model = MomentumModel()
        self.spread_builder = SpreadBuilder()
        self.decision_engine= DecisionEngine()
        self.all_candidates : List[SpreadCandidate]  = []
        self.all_decisions  : List[TradeDecision]    = []

    def run(
        self,
        symbols:    Optional[List[str]] = None,
        max_symbols: int = 1800,
        show_decisions: bool = True,
    ) -> List[TradeDecision]:

        print(BANNER)
        symbols = symbols or config.WATCHLIST

        if not self.connector.connect():
            logger.error("Impossible de se connecter à IBKR. Abandon.")
            sys.exit(1)

        try:
            return self._run_scan(symbols[:max_symbols], show_decisions)
        finally:
            self.connector.disconnect()

    def _run_scan(
        self, symbols: List[str], show_decisions: bool
    ) -> List[TradeDecision]:

        total = len(symbols)
        console.rule(f"🌍 Pilier 1 — Analyse Macro (base commune)")
        macro_result = self.macro_model.analyze()
        print(f"  {macro_result}")

        console.rule(f"📊 Scan de {total} sous-jacents")

        # Traitement par batches
        batches = [symbols[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]

        for b_idx, batch in enumerate(batches):
            logger.info(f"Batch {b_idx+1}/{len(batches)} : {batch}")
            for sym in batch:
                try:
                    spreads = self._process_symbol(sym, macro_result.signal)
                    self.all_candidates.extend(spreads)
                except Exception as e:
                    logger.error(f"  {sym} : {e}")
                time.sleep(1.2)

            if b_idx < len(batches) - 1:
                logger.info(f"⏳ Pause {BATCH_PAUSE}s entre batches…")
                time.sleep(BATCH_PAUSE)

        # Évaluation des décisions
        if self.all_candidates:
            self.all_decisions = evaluate_all_candidates(
                candidates      = self.all_candidates,
                momentum_signal = macro_result.signal,
                macro_signal    = macro_result.signal,
            )

        # Affichage
        self._print_summary(self.all_decisions)
        if show_decisions:
            self._print_decisions(self.all_decisions[:10])
        self._save_results()

        return self.all_decisions

    def _process_symbol(self, symbol: str, macro_signal: str) -> List[SpreadCandidate]:
        chain = get_option_chain(symbol)
        if chain.empty:
            return []

        current_iv = get_atm_iv(symbol)
        iv_percentile = None
        if current_iv:
            save_iv(symbol, current_iv)
            iv_percentile = compute_iv_percentile(symbol, current_iv)

        value_result    = self.value_model.analyze(symbol, current_iv)
        momentum_result = self.momentum_model.analyze(symbol)
        income_result   = self.income_model.analyze(chain)

        pillars_passed = sum([
            macro_signal != "neutral",
            value_result.passed,
            income_result.passed,
            momentum_result.passed,
        ])

        if pillars_passed < 2:
            return []

        candidates = self.spread_builder.build_all(
            symbol        = symbol,
            option_chain  = chain,
            momentum_bias = momentum_result.bias,
            iv_percentile = iv_percentile,
            days_to_event = None,
        )

        strong = [c for c in candidates
                  if c.scoring and c.scoring.score >= config.SCORE_MODERATE]
        logger.info(f"  {symbol} → {len(strong)} spread(s) validé(s)")
        return strong

    def _print_summary(self, decisions: List[TradeDecision]) -> None:
        console.rule("📋 RÉSUMÉ EXÉCUTIF")
        go_decisions = [d for d in decisions if d.go_no_go]

        if not decisions:
            print("  ❌ Aucune opportunité détectée.\n")
            return

        print(f"\n  📊 {len(self.all_candidates)} spread(s) analysé(s) → "
              f"{len(decisions)} décision(s) → "
              f"{len(go_decisions)} GO\n")

        print(f"  {'#':3} {'Symbole':8} {'Stratégie':22} "
              f"{'Conviction':12} {'Risque':8} {'Profit':8} {'Décision':8}")
        print(f"  {'─'*75}")

        for i, d in enumerate(decisions[:20], 1):
            strat = d.recommendation.primary_strategy if d.recommendation else ""
            strat_short = strat.replace("_", " ").title()[:20]
            go_str = "✅ GO" if d.go_no_go else "🚫 NO-GO"
            print(
                f"  {i:3}. {d.symbol:8} {strat_short:22} "
                f"{d.conviction_score:3}/100       "
                f"{d.risk_usd:6.0f}$   "
                f"{d.max_profit_usd:6.0f}$   "
                f"{go_str}"
            )

    def _print_decisions(self, decisions: List[TradeDecision]) -> None:
        console.rule("🎯 FICHES DE DÉCISION — Top 10")
        for d in decisions:
            if d.go_no_go:
                print(str(d))
                if d.recommendation:
                    print(str(d.recommendation))

    def _save_results(self) -> None:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        scan_time = datetime.now().isoformat()

        # Sauvegarder les alertes brutes
        alerts = [c.to_alert_dict() for c in self.all_candidates]
        for a in alerts:
            a["scan_time"] = scan_time

        existing = []
        if os.path.exists(config.ALERTS_JSON_PATH):
            try:
                with open(config.ALERTS_JSON_PATH) as f:
                    existing = json.load(f)
            except Exception:
                pass

        with open(config.ALERTS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(existing + alerts, f, indent=2, ensure_ascii=False)

        # Sauvegarder les décisions
        decisions_path = config.DATA_DIR + "/decisions.json"
        all_d = [d.to_dict() for d in self.all_decisions]
        with open(decisions_path, "w", encoding="utf-8") as f:
            json.dump(all_d, f, indent=2, ensure_ascii=False)

        logger.info(
            f"  {len(alerts)} alertes → {config.ALERTS_JSON_PATH}\n"
            f"  {len(all_d)} décisions → {decisions_path}"
        )


# ──────────────────────────────────────────────────────────────
# Argument parser
# ──────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Phronesis Options Screener v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python main.py                                  # Watchlist par défaut
  python main.py --symbols AAPL NVDA SPY          # Symboles ciblés
  python main.py --universe full                  # 1800 actifs
  python main.py --universe etf                   # ETFs seulement
  python main.py --universe priority --max 100    # Top 100 prioritaires
  python main.py --decide                         # Fiches de décision
  python main.py --chat                           # Assistant IA interactif
  python main.py --ask "C'est quoi un Iron Condor ?"
  python main.py --strategies                     # Lister les stratégies
  python main.py --import-iv data/historical_iv.csv
  python main.py --universe-stats                 # Statistiques univers
        """,
    )

    parser.add_argument("--symbols", nargs="+", metavar="SYMBOL")
    parser.add_argument("--universe", choices=["full","etf","priority","midcap","sp500"],
                        help="Univers prédéfini à scanner")
    parser.add_argument("--max", type=int, default=1800,
                        help="Nombre max de symboles à scanner (défaut: 1800)")
    parser.add_argument("--ask", type=str, metavar="QUESTION")
    parser.add_argument("--alert", type=str, metavar="JSON_PATH")
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--decide", action="store_true",
                        help="Afficher les fiches de décision depuis alerts.json")
    parser.add_argument("--import-iv", type=str, metavar="CSV_PATH")
    parser.add_argument("--score", type=str, metavar="JSON")
    parser.add_argument("--strategies", action="store_true",
                        help="Lister toutes les stratégies disponibles")
    parser.add_argument("--strategy-info", type=str, metavar="STRATEGY_KEY",
                        help="Détails d'une stratégie (ex: iron_condor)")
    parser.add_argument("--universe-stats", action="store_true",
                        help="Statistiques sur l'univers de 1800 actifs")

    return parser.parse_args()


# ──────────────────────────────────────────────────────────────
# Point d'entrée
# ──────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if args.import_iv:
        print(f"📥 Import IV depuis : {args.import_iv}")
        n = import_csv_to_db(args.import_iv)
        print(f"✅ {n} lignes importées.")
        return

    if args.universe_stats:
        stats = universe_stats()
        print(f"\n📊 Univers Phronesis : {stats['total']} sous-jacents\n")
        for seg, count in sorted(stats["segments"].items()):
            print(f"  {seg:30s} : {count:4d}")
        print(f"\nTop 20 priorité 1 : {', '.join(stats['p1_symbols'])}")
        return

    if args.strategies:
        print(list_all_strategies())
        return

    if args.strategy_info:
        print(get_strategy_description(args.strategy_info))
        return

    if args.score:
        try:
            result = score_from_dict(json.loads(args.score))
            print(f"\n{result}")
        except json.JSONDecodeError as e:
            print(f"❌ JSON invalide : {e}")
        return

    if args.decide:
        _show_decisions_from_file(args.alert)
        return

    if args.chat:
        alert_context = _load_last_alert(args.alert)
        PhronesisAssistant().run_repl(initial_context=alert_context)
        return

    if args.ask:
        alert_context = _load_last_alert(args.alert)
        print("\n⏳ Consultation de l'assistant IA…\n")
        print("─" * 60)
        print(quick_ask(args.ask, alert_context=alert_context))
        print("─" * 60)
        return

    # ── Sélection de l'univers ────────────────────────────────
    if args.symbols:
        symbols = args.symbols
    elif args.universe == "full":
        symbols = [u.symbol for u in get_full_universe(max_symbols=args.max)]
        print(f"  🌐 Univers complet : {len(symbols)} symboles")
    elif args.universe == "etf":
        symbols = get_etf_universe()
        print(f"  📊 Univers ETF : {len(symbols)} symboles")
    elif args.universe == "priority":
        symbols = get_priority_watchlist(n=args.max)
        print(f"  ⭐ Univers prioritaire : {len(symbols)} symboles")
    elif args.universe == "sp500":
        from universe import SP500_MEGA
        symbols = list(dict.fromkeys([u.symbol for u in SP500_MEGA]))
        print(f"  📈 S&P 500 Large Caps : {len(symbols)} symboles")
    elif args.universe == "midcap":
        from universe import MID_CAPS
        symbols = [u.symbol for u in MID_CAPS]
        print(f"  📊 Mid Caps : {len(symbols)} symboles")
    else:
        symbols = config.WATCHLIST

    screener = PhronesisScreener()
    decisions = screener.run(symbols=symbols, max_symbols=args.max)

    if decisions:
        print("\n💬 Pour approfondir l'analyse :")
        print("   python main.py --chat --alert data/decisions.json")
        print("   python main.py --decide")

    return decisions


def _show_decisions_from_file(json_path: Optional[str] = None) -> None:
    """Affiche les fiches de décision depuis un fichier JSON."""
    path = json_path or (config.DATA_DIR + "/decisions.json")
    if not os.path.exists(path):
        print(f"❌ Fichier introuvable : {path}")
        print("   Lancez d'abord un scan : python main.py")
        return

    with open(path, encoding="utf-8") as f:
        decisions = json.load(f)

    go = [d for d in decisions if d.get("go_no_go")]
    print(f"\n  📋 {len(decisions)} décisions — {len(go)} GO\n")

    for d in go[:15]:
        print(f"  {'═'*55}")
        print(f"  ✅ {d['symbol']:8} | {d.get('strategy_name','')}")
        print(f"     Conviction : {d['conviction']:3}/100  |  "
              f"Risque : {d.get('risk_usd',0):.0f}$  |  "
              f"Profit max : {d.get('max_profit_usd',0):.0f}$")
        print(f"     IV Rank : {d.get('iv_rank','N/A')}%  |  "
              f"Break-even : {d.get('breakeven','N/A')}")
        print(f"     Take Profit : {d.get('take_profit_pct',50):.0f}% du profit max")
        pp = d.get("prob_profit_est")
        if pp:
            print(f"     Prob. de profit estimée : {pp}%")
        print()


def _load_last_alert(json_path: Optional[str]) -> Optional[Dict]:
    """Charge la dernière alerte/décision disponible."""
    # Essayer decisions.json d'abord
    for path in [
        json_path,
        config.DATA_DIR + "/decisions.json",
        config.ALERTS_JSON_PATH,
    ]:
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    return data[-1]
            except Exception:
                continue
    return None


if __name__ == "__main__":
    main()
