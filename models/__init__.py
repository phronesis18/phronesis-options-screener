"""
models/ — Les 4 piliers de décision du screener Phronesis
=========================================================
Chaque module retourne un objet PillarResult avec :
  - signal  : "bullish" | "bearish" | "neutral"
  - score   : float 0-1 (force du signal)
  - details : dict de métriques calculées
  - passed  : bool (filtre go/no-go)
"""

from .macro_model    import MacroModel, MacroResult
from .value_model    import ValueModel, ValueResult
from .income_model   import IncomeModel, IncomeResult
from .momentum_model import MomentumModel, MomentumResult

__all__ = [
    "MacroModel",    "MacroResult",
    "ValueModel",    "ValueResult",
    "IncomeModel",   "IncomeResult",
    "MomentumModel", "MomentumResult",
]
