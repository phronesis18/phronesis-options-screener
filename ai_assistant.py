"""
ai_assistant.py — Assistant IA conversationnel (DeepSeek / OpenAI)
===================================================================
Module de dialogue pédagogique pour les membres du club Phronesis.
Répond en français sur les grecques, les stratégies, le scoring IA.

Fonctionnalités :
  - Mode REPL interactif
  - Mode --ask (question unique depuis main.py)
  - Contexte d'alerte injecté pour des réponses précises
  - Limite de 20 requêtes par session
"""

import json
import logging
import os
from typing import Optional, List, Dict

import requests

import config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Prompt système expert
# ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es Phronesis AI, l'assistant quantitatif du club d'investissement Phronesis.
Tu es expert en options, grecques, stratégies de spreads et analyse quantitative.
Tu connais parfaitement le cours "Les Options en Finance de Marché" du Club Phronesis (Modules 1 à 9).

Règles absolues :
1. Réponds TOUJOURS en français, de manière pédagogique et précise.
2. Cite le module du cours pertinent quand tu expliques une stratégie.
3. Structure tes réponses avec des émojis 📊 pour la clarté.
4. Si une alerte est fournie en contexte, analyse-la en détail avec la stratégie recommandée.
5. Rappelle toujours la contrainte de risque de 120 $ par trade (règle Phronesis).
6. Applique la checklist du Module 9.3 avant de valider un trade.
7. Mentionne les risques et les conditions défavorables avec honnêteté.

Connaissance du cours Phronesis :
────────────────────────────────────────────────────────
MODULE 1 : Call/Put, Prime, Strike, Expiration, ITM/ATM/OTM
MODULE 2 : Greeks (Delta/Gamma/Theta/Vega), IV Rank, Schémas de marché
  → IV Rank < 30 : options bon marché → ACHETER
  → IV Rank 30–60 : zone neutre → spreads directionnels
  → IV Rank > 60 : options chères → VENDRE
MODULE 3 (Court terme < 30j) :
  → Long Call/Put directionnel (delta 0.40–0.60, DTE 10–21j)
  → Long Straddle pour événements binaires (earnings, FDA)
MODULE 4 (Moyen terme 1–6 mois) :
  → Bull Call Spread : haussier modéré, capital limité
  → Bear Put Spread : baissier modéré
  → Iron Condor : neutre + range + IV > 30
  → Cash-Secured Put : revenus + entrée sur conviction
MODULE 5 (Long terme 6 mois–2 ans) :
  → LEAPS : levier x4–x10, IV basse, conviction forte
  → Covered Call : revenus sur actions détenues
  → Wheel Strategy : cycle CSP → CC → répéter
MODULE 6 : IBKR, 200$, 5 premiers trades
MODULE 7 : Automatisation, IBKR API, ib_insync
MODULE 9.3 : Checklist pré-trade obligatoire
────────────────────────────────────────────────────────

Règles de gestion (cours) :
- Règle des 21j : si option perd 50% de sa valeur → couper
- Fermer à 50% du crédit reçu (credit spreads) — règle Tasty Trade
- Ne jamais risquer > 5% du capital total par position
- Tenir un journal de trading (chaque trade documenté)
- Ne jamais trader sous l'émotion (peur, euphorie)
- Pour l'Iron Condor : fermer à 50% du crédit, ajuster si strike approché

Ton style : Expert bienveillant, entre le professeur et le trader senior.
Toujours conclure avec une action concrète ou une question de clarification.
"""


# ──────────────────────────────────────────────────────────────
# Classe principale
# ──────────────────────────────────────────────────────────────

class PhronesisAssistant:
    """
    Assistant IA conversationnel pour le club Phronesis.
    Supporte DeepSeek (primaire) et OpenAI (fallback).
    """

    def __init__(self):
        self.request_count   = 0
        self.max_requests    = config.MAX_AI_REQUESTS
        self.history:        List[Dict] = []
        self.alert_context:  Optional[Dict] = None

        # Sélection du provider
        if config.AI_PROVIDER == "deepseek" and config.DEEPSEEK_API_KEY:
            self.provider  = "deepseek"
            self.api_key   = config.DEEPSEEK_API_KEY
            self.model     = config.DEEPSEEK_MODEL
            self.base_url  = "https://api.deepseek.com/v1"
        elif config.OPENAI_API_KEY:
            self.provider  = "openai"
            self.api_key   = config.OPENAI_API_KEY
            self.model     = config.OPENAI_MODEL
            self.base_url  = "https://api.openai.com/v1"
        else:
            self.provider  = None
            logger.warning(
                "⚠️  Aucune clé API configurée. "
                "Définissez DEEPSEEK_API_KEY ou OPENAI_API_KEY dans .env"
            )

    # ──────────────────────────────────────────────────────────
    # API principale
    # ──────────────────────────────────────────────────────────

    def set_alert_context(self, alert: Dict) -> None:
        """Injecte le contexte d'une alerte pour les questions suivantes."""
        self.alert_context = alert
        logger.debug(f"Contexte d'alerte défini : {alert.get('symbol', '?')}")

    def ask(self, question: str) -> str:
        """
        Pose une question à l'assistant.
        Retourne la réponse en français.
        """
        if not self.provider:
            return (
                "⚠️  Assistant IA non configuré.\n"
                "Ajoutez DEEPSEEK_API_KEY ou OPENAI_API_KEY dans votre fichier .env\n"
                "puis redémarrez le screener."
            )

        if self.request_count >= self.max_requests:
            return (
                f"⚠️  Limite de {self.max_requests} requêtes atteinte pour cette session.\n"
                "Relancez le screener pour une nouvelle session."
            )

        # Enrichir avec le contexte de stratégie si détecté
        full_question = self._build_question(question)

        self.history.append({"role": "user", "content": full_question})

        try:
            response = self._call_api()
            self.request_count += 1

            if response:
                self.history.append({"role": "assistant", "content": response})
                logger.info(
                    f"Requête IA #{self.request_count}/{self.max_requests} "
                    f"— {len(response)} caractères"
                )
                return response
            else:
                return "❌ Aucune réponse reçue de l'API."

        except Exception as e:
            logger.error(f"ask() erreur : {e}")
            return f"❌ Erreur lors de la requête : {e}"

    def reset(self) -> None:
        """Réinitialise la session (historique + compteur)."""
        self.history = []
        self.request_count = 0
        self.alert_context = None

    # ──────────────────────────────────────────────────────────
    # Mode REPL interactif
    # ──────────────────────────────────────────────────────────

    def run_repl(self, initial_context: Optional[Dict] = None) -> None:
        """Lance le mode conversationnel interactif dans le terminal."""
        if initial_context:
            self.set_alert_context(initial_context)

        print("\n" + "═" * 60)
        print("  🧠 PHRONESIS AI — Assistant Options")
        print(f"  Modèle : {self.model if self.provider else 'Non configuré'}")
        print(f"  Limite : {self.max_requests} requêtes/session")
        print("  Commandes :")
        print("    exit / quit      → Quitter")
        print("    reset            → Effacer l'historique")
        print("    context          → Voir l'alerte chargée")
        print("    strategies       → Lister toutes les stratégies")
        print("    strategy <clé>   → ex: strategy iron_condor")
        print("═" * 60 + "\n")

        while True:
            try:
                user_input = input(
                    f"[{self.request_count}/{self.max_requests}] Votre question : "
                ).strip()

                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit", "q"):
                    print("Au revoir ! 👋")
                    break

                if user_input.lower() == "reset":
                    self.reset()
                    print("✅ Session réinitialisée.\n")
                    continue

                if user_input.lower() == "context":
                    if self.alert_context:
                        print("\n📋 Contexte d'alerte :")
                        print(json.dumps(self.alert_context, indent=2, ensure_ascii=False))
                        print()
                    else:
                        print("ℹ️  Aucun contexte d'alerte chargé.\n")
                    continue

                if user_input.lower() == "strategies":
                    from strategy_advisor import list_all_strategies
                    print(list_all_strategies())
                    continue

                if user_input.lower().startswith("strategy "):
                    key = user_input[9:].strip()
                    from strategy_advisor import get_strategy_description
                    print(get_strategy_description(key))
                    continue

                # Appel IA
                print("\n⏳ Analyse en cours…\n")
                response = self.ask(user_input)
                print("─" * 60)
                print(response)
                print("─" * 60 + "\n")

            except KeyboardInterrupt:
                print("\n\nInterrompu par l'utilisateur. Au revoir ! 👋")
                break
            except EOFError:
                break

    # ──────────────────────────────────────────────────────────
    # Helpers privés
    # ──────────────────────────────────────────────────────────

    def _build_question(self, question: str) -> str:
        """Enrichit la question avec le contexte d'alerte si disponible."""
        if not self.alert_context:
            return question

        ctx = json.dumps(self.alert_context, ensure_ascii=False, indent=2)
        return (
            f"{question}\n\n"
            f"--- Contexte d'alerte actuelle ---\n{ctx}\n"
            "-----------------------------------"
        )

    def _call_api(self) -> Optional[str]:
        """Appelle l'API LLM (DeepSeek ou OpenAI)."""
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model":    self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                *self.history,
            ],
            "temperature": 0.7,
            "max_tokens":  1500,
        }

        url = f"{self.base_url}/chat/completions"

        response = requests.post(
            url, headers=headers,
            json=payload, timeout=60
        )
        response.raise_for_status()

        data = response.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0]["message"]["content"]
        return None


# ──────────────────────────────────────────────────────────────
# Utilitaires pour les tests hors-session
# ──────────────────────────────────────────────────────────────

def quick_ask(question: str,
              alert_context: Optional[Dict] = None) -> str:
    """
    Raccourci pour une question unique (mode --ask).
    Crée une instance temporaire sans historique.
    """
    assistant = PhronesisAssistant()
    if alert_context:
        assistant.set_alert_context(alert_context)
    return assistant.ask(question)
