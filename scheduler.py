"""
scheduler.py — Planificateur Python natif (alternative au cron)
===============================================================
Lance le screener automatiquement aux horaires configurés.
Utile sur Windows ou si le cron système n'est pas disponible.

Usage :
  python scheduler.py               # Démarrer le planificateur
  python scheduler.py --test        # Lancer un scan immédiatement (test)
"""

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime

try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Configuration des horaires (heure locale)
# ─────────────────────────────────────────────

# Adapte ces horaires selon ton fuseau horaire
# Marché US : 9h30 - 16h00 ET = 15h30 - 22h00 Paris (hiver)
SCAN_TIMES = [
    "09:35",   # Ouverture marché US (heure locale machine)
    "14:00",   # Mi-session
    "15:45",   # Avant la clôture
]

# Symboles prioritaires pour les scans intra-journaliers
PRIORITY_SYMBOLS = ["SPY", "QQQ", "AAPL", "NVDA", "MSFT"]


# ─────────────────────────────────────────────
# Fonctions de lancement
# ─────────────────────────────────────────────

def run_full_scan():
    """Lance le scan complet (watchlist entière)."""
    logger.info("🚀 Lancement du scan complet…")
    _run_screener([])


def run_priority_scan():
    """Lance un scan rapide sur les symboles prioritaires."""
    logger.info(f"⚡ Scan rapide : {', '.join(PRIORITY_SYMBOLS)}")
    _run_screener(["--symbols"] + PRIORITY_SYMBOLS)


def _run_screener(extra_args: list):
    """Exécute main.py en sous-processus."""
    cmd = [sys.executable, "main.py"] + extra_args
    start = datetime.now()
    try:
        result = subprocess.run(
            cmd,
            capture_output=False,
            text=True,
            timeout=600,   # 10 minutes max
        )
        elapsed = (datetime.now() - start).seconds
        if result.returncode == 0:
            logger.info(f"✅ Scan terminé en {elapsed}s.")
        else:
            logger.error(f"❌ Scan échoué (code={result.returncode}) en {elapsed}s.")
    except subprocess.TimeoutExpired:
        logger.error("❌ Timeout — scan interrompu après 10 minutes.")
    except Exception as e:
        logger.error(f"❌ Erreur inattendue : {e}")


# ─────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Planificateur Phronesis Screener")
    parser.add_argument("--test", action="store_true",
                        help="Lancer un scan immédiatement puis quitter")
    args = parser.parse_args()

    if args.test:
        logger.info("Mode test : scan immédiat.")
        run_full_scan()
        return

    if not SCHEDULE_AVAILABLE:
        logger.error("Module 'schedule' non installé. Lancez : pip install schedule")
        sys.exit(1)

    logger.info("📅 Planificateur démarré.")
    logger.info(f"   Horaires configurés : {', '.join(SCAN_TIMES)}")
    logger.info("   Ctrl+C pour arrêter.\n")

    # Enregistrement des tâches (jours ouvrés uniquement)
    for scan_time in SCAN_TIMES:
        schedule.every().monday.at(scan_time).do(run_full_scan)
        schedule.every().tuesday.at(scan_time).do(run_full_scan)
        schedule.every().wednesday.at(scan_time).do(run_full_scan)
        schedule.every().thursday.at(scan_time).do(run_full_scan)
        schedule.every().friday.at(scan_time).do(run_full_scan)

    # Boucle principale
    try:
        while True:
            schedule.run_pending()
            next_run = schedule.next_run()
            if next_run:
                wait = (next_run - datetime.now()).seconds
                logger.debug(f"Prochain scan dans {wait//60}min {wait%60}s")
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("\n🛑 Planificateur arrêté.")


if __name__ == "__main__":
    main()
