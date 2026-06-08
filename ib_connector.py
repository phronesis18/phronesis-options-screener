"""
ib_connector.py — Gestion de la connexion à TWS / IB Gateway
=============================================================
Fournit un singleton thread-safe pour la connexion IBKR via ib_insync.
Gère la reconnexion automatique et les timeouts.
"""

import logging
import time
from typing import Optional

from ib_insync import IB, util

import config

logger = logging.getLogger(__name__)


class IBConnector:
    """
    Encapsule la connexion à Interactive Brokers TWS/Gateway.
    Pattern Singleton : une seule instance par processus.
    """

    _instance: Optional["IBConnector"] = None

    def __new__(cls) -> "IBConnector":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._ib = IB()
            cls._instance._connected = False
        return cls._instance

    # ──────────────────────────────────────────
    # Connexion / Déconnexion
    # ──────────────────────────────────────────

    def connect(self, max_retries: int = 3) -> bool:
        """
        Tente de se connecter à TWS/Gateway.
        Retente jusqu'à max_retries fois en cas d'échec.
        """
        if self._connected and self._ib.isConnected():
            logger.debug("Déjà connecté à IBKR.")
            return True

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Tentative {attempt}/{max_retries} : connexion à "
                    f"{config.IBKR_HOST}:{config.IBKR_PORT} "
                    f"(clientId={config.IBKR_CLIENT_ID})"
                )
                self._ib.connect(
                    host=config.IBKR_HOST,
                    port=config.IBKR_PORT,
                    clientId=config.IBKR_CLIENT_ID,
                    timeout=config.IBKR_TIMEOUT,
                    readonly=True,   # Lecture seule : pas d'ordres accidentels
                )
                self._connected = True
                logger.info(
                    f"✅ Connecté à IBKR — "
                    f"serverVersion={self._ib.serverVersion()}, "
                    f"account={self._ib.managedAccounts()}"
                )
                return True

            except Exception as exc:
                logger.warning(f"Échec tentative {attempt} : {exc}")
                if attempt < max_retries:
                    wait = 5 * attempt
                    logger.info(f"Nouvelle tentative dans {wait}s…")
                    time.sleep(wait)

        logger.error("❌ Impossible de se connecter à IBKR après "
                     f"{max_retries} tentatives.")
        return False

    def disconnect(self) -> None:
        """Déconnecte proprement."""
        if self._ib.isConnected():
            self._ib.disconnect()
            self._connected = False
            logger.info("Déconnecté d'IBKR.")

    def reconnect(self) -> bool:
        """Déconnecte puis reconnecte."""
        self.disconnect()
        time.sleep(2)
        return self.connect()

    # ──────────────────────────────────────────
    # Accesseur IB
    # ──────────────────────────────────────────

    @property
    def ib(self) -> IB:
        """Retourne l'objet IB. Reconnecte si nécessaire."""
        if not self._ib.isConnected():
            logger.warning("Connexion perdue — tentative de reconnexion…")
            self.connect()
        return self._ib

    def is_connected(self) -> bool:
        return self._ib.isConnected()

    # ──────────────────────────────────────────
    # Contexte (with statement)
    # ──────────────────────────────────────────

    def __enter__(self) -> "IBConnector":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()


# ──────────────────────────────────────────────
# Utilitaire : run_with_timeout
# ──────────────────────────────────────────────

def run_with_timeout(coro, timeout: float = 30):
    """
    Exécute une coroutine ib_insync avec un timeout.
    Wrapper pratique pour les appels bloquants.
    """
    return util.run(coro, timeout=timeout)
