"""
test_scoring.py — Tests unitaires du scoring IA (sans IBKR)
============================================================
Permet de valider la logique de scoring sans connexion à TWS.
Lance avec : python test_scoring.py

Couvre :
  - Calculs de normalisation
  - Score composite (cas réels)
  - Cas limites (valeurs nulles, extremes)
  - Sérialisation/désérialisation
"""

import sys
import json
from dataclasses import asdict

# Ajout du path courant
sys.path.insert(0, ".")

from scoring_ia import (
    ScoringInput, compute_score, score_from_dict,
    _norm_clamp, _liquidite_score, _event_penalty
)


# ─────────────────────────────────────────────
# Helpers de test
# ─────────────────────────────────────────────

PASS = "✅"
FAIL = "❌"
_results = []

def test(name: str, condition: bool, details: str = ""):
    status = PASS if condition else FAIL
    _results.append(condition)
    msg = f"  {status} {name}"
    if details:
        msg += f" → {details}"
    print(msg)


# ─────────────────────────────────────────────
# Suite de tests
# ─────────────────────────────────────────────

def test_normalisation():
    print("\n📐 Tests de normalisation")
    test("clamp(50, 0, 100) = 0.5",   abs(_norm_clamp(50, 0, 100) - 0.5) < 0.001)
    test("clamp(0, 0, 100) = 0.0",    abs(_norm_clamp(0, 0, 100) - 0.0) < 0.001)
    test("clamp(100, 0, 100) = 1.0",  abs(_norm_clamp(100, 0, 100) - 1.0) < 0.001)
    test("clamp(150, 0, 100) = 1.0",  abs(_norm_clamp(150, 0, 100) - 1.0) < 0.001)
    test("clamp(-10, 0, 100) = 0.0",  abs(_norm_clamp(-10, 0, 100) - 0.0) < 0.001)
    test("clamp(v_min==v_max) = 0.5", abs(_norm_clamp(50, 50, 50) - 0.5) < 0.001)


def test_liquidite():
    print("\n💧 Tests score liquidité")
    # OI=1000, spread=0 → score max = 1.0
    test("OI=1000 spread=0 → 1.0",
         abs(_liquidite_score(1000, 0.0) - 1.0) < 0.001)
    # OI=0 → 0 (quelle que soit spread)
    test("OI=0 → 0.0",
         abs(_liquidite_score(0, 0.05) - 0.0) < 0.001)
    # OI=500, spread=0.05 → 0.5 * 0.5 = 0.25
    test("OI=500 spread=0.05 → 0.25",
         abs(_liquidite_score(500, 0.05) - 0.25) < 0.001)
    # OI=2000, spread=0.02 → 1.0 * 0.8 = 0.80
    test("OI=2000 spread=0.02 → 0.80",
         abs(_liquidite_score(2000, 0.02) - 0.80) < 0.001)


def test_event_penalty():
    print("\n📅 Tests pénalité événement")
    p1  = _event_penalty(1)
    p5  = _event_penalty(5)
    p10 = _event_penalty(10)
    p20 = _event_penalty(20)
    test("Aucun événement → 0.0",         _event_penalty(None) == 0.0)
    test("J=0 → pénalité max (1.0)",      _event_penalty(0) >= 1.0)
    test("J=1 → pénalité élevée (≥0.8)",  p1 >= 0.8, f"obtenu={p1:.3f}")
    test("J=5 → pénalité < J=1",          p5 < p1,   f"p5={p5:.3f} < p1={p1:.3f}")
    test("J=10 < J=5 (décroissant)",      p10 < p5, f"p10={p10:.3f} p5={p5:.3f}")
    test("J=20 < J=10 (décroissant)",     p20 < p10, f"p20={p20:.3f} p10={p10:.3f}")


def test_score_fort():
    print("\n🟢 Test opportunité forte (score ≥ 60)")
    inp = ScoringInput(
        iv_percentile   = 82.0,   # IV très élevée → favorable vendeur
        theta_abs       = 0.10,   # Excellent thêta
        delta           = 0.12,   # Très faible delta (OTM profond)
        open_interest   = 2000,   # Très liquide
        bid_ask_spread  = 0.02,   # Spread très serré
        credit_received = 1.60,   # Crédit attractif
        max_risk        = 3.40,   # Bon ratio
        days_to_event   = None,   # Pas d'événement connu
        spot            = 182.50,
        strike          = 170.0,  # 6.8% OTM
        symbol          = "AAPL",
        strategy        = "bull_put",
    )
    result = compute_score(inp)
    test(f"Score ≥ 60 (obtenu: {result.score})", result.score >= 60,
         f"label='{result.label}'")
    test("Score est un entier 0-100",
         isinstance(result.score, int) and 0 <= result.score <= 100)
    test("Détails présents",
         all(k in result.details for k in
             ["iv_percentile", "theta_abs", "delta", "liquidite_score", "risk_reward"]))


def test_score_faible():
    print("\n🔴 Test opportunité faible (score < 40)")
    inp = ScoringInput(
        iv_percentile   = 8.0,    # IV très basse
        theta_abs       = 0.005,  # Thêta quasi nul
        delta           = 0.47,   # Delta très élevé (quasi ATM)
        open_interest   = 30,     # Très illiquide
        bid_ask_spread  = 0.14,   # Spread très large
        credit_received = 0.10,   # Crédit dérisoire
        max_risk        = 4.90,   # Très mauvais ratio
        days_to_event   = 1.0,    # Événement demain !
        spot            = 150.0,
        strike          = 149.0,
        symbol          = "XYZ",
        strategy        = "bear_call",
    )
    result = compute_score(inp)
    test(f"Score < 40 (obtenu: {result.score})", result.score < 40,
         f"label='{result.label}'")
    test("Score est un entier 0-100",
         isinstance(result.score, int) and 0 <= result.score <= 100)


def test_score_moderee():
    print("\n🟡 Test opportunité modérée (40 ≤ score < 75)")
    inp = ScoringInput(
        iv_percentile   = 55.0,
        theta_abs       = 0.05,
        delta           = 0.25,
        open_interest   = 400,
        bid_ask_spread  = 0.06,
        credit_received = 0.80,
        max_risk        = 4.20,
        days_to_event   = 8.0,
        spot            = 200.0,
        strike          = 190.0,
        symbol          = "SPY",
        strategy        = "bull_put",
    )
    result = compute_score(inp)
    test(f"Score dans la plage modérée 30-80 (obtenu: {result.score})",
         30 <= result.score <= 80, f"label='{result.label}'")


def test_score_from_dict():
    print("\n📦 Test score_from_dict")
    data = {
        "iv_percentile": 72, "theta_abs": 0.08, "delta": 0.18,
        "open_interest": 800, "bid_ask_spread": 0.04,
        "credit_received": 1.10, "max_risk": 3.90,
        "spot": 450.0, "strike": 430.0,
        "symbol": "SPY", "strategy": "bull_put",
    }
    result = score_from_dict(data)
    test(f"Score valide 0-100 (obtenu: {result.score})",
         0 <= result.score <= 100)
    test("Résultat sérialisable JSON",
         json.dumps({"score": result.score, "label": result.label}) is not None)


def test_contrainte_120():
    print("\n💰 Test contrainte 120$ (risk_usd ≤ 120)")
    # Score avec risque = exactement 120$
    inp = ScoringInput(
        iv_percentile   = 65.0,
        theta_abs       = 0.06,
        delta           = 0.20,
        open_interest   = 600,
        bid_ask_spread  = 0.05,
        credit_received = 0.80,
        max_risk        = 1.20,   # = 120$/100 actions
        days_to_event   = 12.0,
        spot            = 100.0,
        strike          = 95.0,
    )
    result = compute_score(inp)
    test(f"Score calculé sans erreur (obtenu: {result.score})",
         result.score is not None and 0 <= result.score <= 100)
    rr = inp.credit_received / inp.max_risk
    test(f"R/R = {rr:.2f} (attendu ~0.67)", abs(rr - 0.667) < 0.01)


def test_repr():
    print("\n🖨️  Test affichage __str__")
    inp = ScoringInput(
        iv_percentile=75, theta_abs=0.07, delta=0.15,
        open_interest=900, bid_ask_spread=0.03,
        credit_received=1.30, max_risk=3.70,
        spot=180.0, strike=172.0,
        symbol="MSFT", strategy="bull_put",
    )
    result = compute_score(inp)
    output = str(result)
    test("Score IA visible dans str()", "Score IA" in output)
    test("Thêta visible dans str()",    "Thêta" in output)
    test("Barre de progression présente", "█" in output or "░" in output)
    print(output)


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  🧪 PHRONESIS — Tests unitaires Scoring IA")
    print("=" * 55)

    test_normalisation()
    test_liquidite()
    test_event_penalty()
    test_score_fort()
    test_score_faible()
    test_score_moderee()
    test_score_from_dict()
    test_contrainte_120()
    test_repr()

    # Résumé
    passed = sum(_results)
    total  = len(_results)
    failed = total - passed

    print("\n" + "=" * 55)
    print(f"  Résultat : {passed}/{total} tests passés", end="")
    if failed:
        print(f"  ({failed} échec(s))")
    else:
        print("  🎉 Tous les tests passent !")
    print("=" * 55)

    sys.exit(0 if failed == 0 else 1)
