"""
update_data.py — Scan périodique pour générer les opportunités
Exécuté par GitHub Actions toutes les 2 heures.
"""

import json
import logging
import os
import sys
from datetime import datetime

# Ajouter le chemin racine pour importer les modules du projet
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ib_connector import IBConnector
from data_fetcher import get_option_chain, get_atm_iv
from models import MacroModel, ValueModel, IncomeModel, MomentumModel
from spread_builder import SpreadBuilder
from iv_percentile_storage import compute_iv_percentile, save_iv
from decision_engine import evaluate_all_candidates
from universe import get_priority_watchlist
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_scan_and_save(symbols=None, max_symbols=50):
    """Scanne les symboles, génère les spreads, évalue les décisions, sauvegarde JSON."""
    if symbols is None:
        # Utiliser la watchlist prioritaire pour éviter trop de symboles
        symbols = get_priority_watchlist(n=max_symbols)
        logger.info(f"Scan de {len(symbols)} symboles prioritaires")
    
    connector = IBConnector()
    # On essaie de se connecter, mais ce n'est pas bloquant (fallback yfinance)
    connector.connect()
    
    macro_model = MacroModel()
    value_model = ValueModel()
    income_model = IncomeModel()
    momentum_model = MomentumModel()
    spread_builder = SpreadBuilder()
    
    all_candidates = []
    macro_result = macro_model.analyze()
    
    for sym in symbols:
        try:
            logger.info(f"Analyse de {sym}...")
            chain = get_option_chain(sym)
            if chain.empty:
                logger.warning(f"{sym}: chaîne vide")
                continue
            current_iv = get_atm_iv(sym)
            iv_percentile = None
            if current_iv:
                save_iv(sym, current_iv)
                iv_percentile = compute_iv_percentile(sym, current_iv)
            
            value_result = value_model.analyze(sym, current_iv)
            momentum_result = momentum_model.analyze(sym)
            income_result = income_model.analyze(chain)
            
            pillars_passed = sum([
                macro_result.signal != "neutral",
                value_result.passed,
                income_result.passed,
                momentum_result.passed,
            ])
            if pillars_passed < 2:
                continue
            
            candidates = spread_builder.build_all(
                symbol=sym,
                option_chain=chain,
                momentum_bias=momentum_result.bias,
                iv_percentile=iv_percentile,
                days_to_event=None,
            )
            # Garder uniquement ceux avec score >= MODERATE (config)
            strong = [c for c in candidates if c.scoring and c.scoring.score >= config.SCORE_MODERATE]
            all_candidates.extend(strong)
            logger.info(f"{sym}: {len(strong)} spreads retenus")
        except Exception as e:
            logger.error(f"Erreur sur {sym}: {e}")
    
    connector.disconnect()
    
    if not all_candidates:
        logger.info("Aucun spread candidat trouvé")
        # Sauvegarder un tableau vide
        os.makedirs("data", exist_ok=True)
        with open("data/opportunities.json", "w", encoding="utf-8") as f:
            json.dump([], f)
        return
    
    # Évaluation des décisions
    decisions = evaluate_all_candidates(
        all_candidates,
        momentum_signal=macro_result.signal,
        macro_signal=macro_result.signal
    )
    
    # Sérialisation
    output = []
    for d in decisions:
        output.append(d.to_dict())
    
    os.makedirs("data", exist_ok=True)
    with open("data/opportunities.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Sauvegardé {len(output)} décisions dans data/opportunities.json")

if __name__ == "__main__":
    run_scan_and_save()
