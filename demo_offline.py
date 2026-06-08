"""
demo_offline.py — Démonstration complète SANS connexion IBKR
=============================================================
Simule une chaîne d'options complète et exécute le pipeline
entier (spreads + scoring + affichage) pour valider l'install.

Usage :
  python demo_offline.py
  python demo_offline.py --chat    # Lance le chat IA ensuite
"""

import argparse
import json
import sys
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# ─────────────────────────────────────────────
# Simulation d'une chaîne d'options
# ─────────────────────────────────────────────

def make_fake_chain(symbol: str = "AAPL",
                    spot: float = 182.50,
                    base_iv: float = 0.28) -> pd.DataFrame:
    """
    Génère une chaîne d'options fictive réaliste.
    Utilise le modèle de Black-Scholes simplifié pour les prix.
    """
    import math

    today = datetime.now().date()
    rows = []

    expirations = {
        (today + timedelta(days=21)).strftime("%Y%m%d"): 21,
        (today + timedelta(days=35)).strftime("%Y%m%d"): 35,
    }

    # Strikes : ±10% autour du spot, par pas de 2.5$
    strikes = [round(spot * (1 + pct), 1)
               for pct in np.arange(-0.10, 0.11, 0.025)]

    def bs_approx_price(S, K, T, iv, right):
        """Approximation de prix BS (pour la démo)."""
        d1 = (math.log(S/K) + 0.5 * iv**2 * T) / (iv * math.sqrt(T))
        d2 = d1 - iv * math.sqrt(T)

        from scipy.stats import norm
        try:
            if right == "C":
                price = S * norm.cdf(d1) - K * norm.cdf(d2)
                delta = norm.cdf(d1)
            else:
                price = K * norm.cdf(-d2) - S * norm.cdf(-d1)
                delta = norm.cdf(d1) - 1
        except Exception:
            price = max(0, S - K) if right == "C" else max(0, K - S)
            delta = 0.5

        theta = -S * iv / (2 * math.sqrt(T * 365)) / 365
        return max(0.01, price), delta, theta

    for expiry, dte in expirations.items():
        T = dte / 365.0
        for strike in strikes:
            for right in ["C", "P"]:
                # IV smile simplifié
                moneyness = abs(spot / strike - 1)
                smile_adj = 0.02 * (moneyness / 0.05) ** 2
                iv = base_iv + smile_adj

                price, delta, theta = bs_approx_price(spot, strike, T, iv, right)

                # Spread bid-ask (plus large pour les OTM profonds)
                ba_spread = 0.02 + 0.03 * moneyness * 10
                bid = max(0.01, price - ba_spread / 2)
                ask = price + ba_spread / 2

                # Open interest (plus élevé near ATM)
                oi_base = 2000 if moneyness < 0.03 else 800
                oi = int(oi_base * (1 + np.random.uniform(-0.3, 0.3)))

                rows.append({
                    "symbol":        symbol,
                    "expiry":        expiry,
                    "strike":        strike,
                    "right":         right,
                    "bid":           round(bid, 2),
                    "ask":           round(ask, 2),
                    "last":          round(price, 2),
                    "iv":            round(iv, 4),
                    "delta":         round(delta, 4),
                    "gamma":         round(0.02 / (iv * spot), 4),
                    "theta":         round(theta, 4),
                    "vega":          round(spot * iv * 0.01, 4),
                    "open_interest": oi,
                    "volume":        int(oi * 0.3),
                    "spot":          spot,
                    "dte":           dte,
                    "expiry_date":   pd.Timestamp(
                        datetime.now().date() + timedelta(days=dte)),
                })

    df = pd.DataFrame(rows)
    print(f"  📊 Chaîne fictive générée : {len(df)} options "
          f"({len(strikes)} strikes × 2 rights × {len(expirations)} expirations)")
    return df


# ─────────────────────────────────────────────
# Pipeline offline
# ─────────────────────────────────────────────

def run_demo(with_chat: bool = False):
    print("\n" + "═" * 60)
    print("  🧠 PHRONESIS DEMO OFFLINE — Sans connexion IBKR")
    print("═" * 60)

    # ── 1. Paramètres de démo ─────────────────────────────────
    symbol    = "AAPL"
    spot      = 182.50
    iv_now    = 0.285
    iv_pct    = 68.0    # Percentile simulé

    print(f"\n  Sous-jacent   : {symbol}")
    print(f"  Spot          : {spot:.2f}$")
    print(f"  IV actuelle   : {iv_now:.3f} ({iv_pct:.0f}e percentile)")

    # ── 2. Génération de la chaîne ────────────────────────────
    print("\n  ── Génération de la chaîne d'options…")
    try:
        chain = make_fake_chain(symbol, spot, iv_now)
    except ImportError:
        print("  ⚠️  scipy non installé — pip install scipy")
        chain = _make_simple_chain(symbol, spot)

    # ── 3. Modèle Income ──────────────────────────────────────
    print("\n  ── Pilier Income…")
    from models.income_model import IncomeModel
    income = IncomeModel()
    income_result = income.analyze(chain)
    print(f"    {income_result}")

    # ── 4. Construction des spreads ───────────────────────────
    print("\n  ── Construction des spreads (contrainte 120$)…")
    from spread_builder import SpreadBuilder
    builder = SpreadBuilder()

    candidates = builder.build_all(
        symbol        = symbol,
        option_chain  = chain,
        momentum_bias = "seller",    # Range → vente premium
        iv_percentile = iv_pct,
        days_to_event = 14.0,        # Earnings dans 14j
    )

    if not candidates:
        print("  ❌ Aucun spread généré avec les paramètres de démo.")
        print("     Essayez : python demo_offline.py (scipy requis pour les prix BS)")
        return

    # ── 5. Affichage ──────────────────────────────────────────
    print(f"\n  ── {len(candidates)} spread(s) candidat(s) :\n")
    for i, c in enumerate(candidates, 1):
        print(f"  [{i}] {c}")

    # ── 6. Résumé scoré ───────────────────────────────────────
    print("\n  ── Classement par score IA :\n")
    sorted_c = sorted(candidates,
                      key=lambda x: x.scoring.score if x.scoring else 0,
                      reverse=True)
    for i, c in enumerate(sorted_c, 1):
        score = c.scoring.score if c.scoring else 0
        label = c.scoring.label if c.scoring else ""
        print(
            f"  {i}. {c.strategy:12} "
            f"Exp:{c.expiry[-4:]} "
            f"K:{c.leg1_strike:.0f}/{c.leg2_strike:.0f} "
            f"Risque:{c.risk_usd:5.0f}$ "
            f"Score:{score:3}/100 {label}"
        )

    # ── 7. Sauvegarde pour le chat ────────────────────────────
    import os, json
    os.makedirs("data", exist_ok=True)
    alerts = [c.to_alert_dict() for c in sorted_c[:3]]
    with open("data/demo_alerts.json", "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  💾 Alertes de démo sauvegardées dans data/demo_alerts.json")

    # ── 8. Test scoring ───────────────────────────────────────
    print("\n  ── Test scoring rapide :")
    from scoring_ia import score_from_dict
    test_data = {
        "iv_percentile": iv_pct, "theta_abs": 0.07, "delta": 0.18,
        "open_interest": 900, "bid_ask_spread": 0.04,
        "credit_received": 1.20, "max_risk": 3.80,
        "spot": spot, "strike": 175.0,
        "symbol": symbol, "strategy": "bull_put",
    }
    result = score_from_dict(test_data)
    print(f"\n{result}\n")

    # ── 9. Chat IA optionnel ──────────────────────────────────
    if with_chat:
        print("\n" + "═" * 60)
        print("  Mode chat IA (les alertes de démo sont chargées)")
        print("═" * 60)
        from ai_assistant import PhronesisAssistant
        assistant = PhronesisAssistant()
        assistant.run_repl(initial_context=alerts[0] if alerts else None)
    else:
        print("  💬 Pour explorer avec l'assistant IA :")
        print("     python demo_offline.py --chat")
        print("     python main.py --chat --alert data/demo_alerts.json\n")


def _make_simple_chain(symbol: str, spot: float) -> pd.DataFrame:
    """Chaîne simplifiée sans scipy (fallback)."""
    from datetime import datetime, timedelta
    today = datetime.now().date()
    expiry = (today + timedelta(days=21)).strftime("%Y%m%d")
    rows = []
    for k in [spot * 0.95, spot * 0.97, spot, spot * 1.03, spot * 1.05]:
        k = round(k, 1)
        for right in ["C", "P"]:
            itm = max(0, spot - k) if right == "C" else max(0, k - spot)
            price = max(0.10, itm + 0.50)
            rows.append({
                "symbol": symbol, "expiry": expiry, "strike": k,
                "right": right, "bid": price - 0.02, "ask": price + 0.02,
                "last": price, "iv": 0.28, "delta": 0.3 if right == "C" else -0.3,
                "gamma": 0.02, "theta": -0.05, "vega": 0.10,
                "open_interest": 500, "volume": 150, "spot": spot, "dte": 21,
                "expiry_date": pd.Timestamp(today + timedelta(days=21)),
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Démo Phronesis Screener (sans IBKR)"
    )
    parser.add_argument(
        "--chat", action="store_true",
        help="Lancer le chat IA après la démo"
    )
    args = parser.parse_args()
    run_demo(with_chat=args.chat)
