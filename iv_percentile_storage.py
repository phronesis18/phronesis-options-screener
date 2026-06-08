"""
iv_percentile_storage.py — Historique IV et calcul du percentile
=================================================================
Persiste les IV quotidiennes dans un SQLite (primary) et un CSV
(backup/export). Calcule le percentile sur 252 jours de bourse.
"""

import csv
import logging
import os
import sqlite3
from datetime import date, datetime
from typing import Optional

import pandas as pd
import numpy as np

import config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Initialisation de la base
# ──────────────────────────────────────────────────────────────

def _get_db_connection() -> sqlite3.Connection:
    """Ouvre (et crée si besoin) la base SQLite."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.IV_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS iv_history (
            date    TEXT NOT NULL,
            symbol  TEXT NOT NULL,
            iv      REAL NOT NULL,
            PRIMARY KEY (date, symbol)
        )
    """)
    conn.commit()
    return conn


# ──────────────────────────────────────────────────────────────
# Lecture / Écriture
# ──────────────────────────────────────────────────────────────

def save_iv(symbol: str, iv: float,
            trade_date: Optional[date] = None) -> None:
    """
    Enregistre l'IV du jour pour un symbole.
    Si l'enregistrement existe déjà, il est mis à jour (UPSERT).
    """
    if trade_date is None:
        trade_date = date.today()
    date_str = trade_date.isoformat()

    try:
        conn = _get_db_connection()
        conn.execute(
            "INSERT OR REPLACE INTO iv_history (date, symbol, iv) VALUES (?, ?, ?)",
            (date_str, symbol, iv)
        )
        conn.commit()
        conn.close()
        logger.debug(f"IV sauvegardée : {symbol} {date_str} → {iv:.4f}")

        # Sync CSV backup
        _sync_csv(symbol, date_str, iv)

    except Exception as e:
        logger.error(f"save_iv({symbol}) : {e}")


def get_iv_history(symbol: str, days: int = 252) -> pd.Series:
    """
    Retourne les `days` dernières valeurs IV d'un symbole
    sous forme de pd.Series indexée par date.
    """
    try:
        conn = _get_db_connection()
        df = pd.read_sql_query(
            """
            SELECT date, iv FROM iv_history
            WHERE symbol = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            conn, params=(symbol, days)
        )
        conn.close()

        if df.empty:
            # Tentative de lecture depuis le CSV
            df = _read_from_csv(symbol, days)

        if df.empty:
            return pd.Series(dtype=float)

        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        return df["iv"]

    except Exception as e:
        logger.error(f"get_iv_history({symbol}) : {e}")
        return pd.Series(dtype=float)


# ──────────────────────────────────────────────────────────────
# Calcul du Percentile IV
# ──────────────────────────────────────────────────────────────

def compute_iv_percentile(symbol: str, current_iv: float,
                           days: int = 252) -> Optional[float]:
    """
    Calcule le percentile de l'IV actuelle par rapport
    aux 252 derniers jours de bourse.

    Retourne un float entre 0 et 100.
    Ex : 75 signifie que l'IV actuelle dépasse 75 % des observations.

    Interprétation :
      > 80 → IV élevée → favorable pour vendeur d'options
      < 20 → IV basse  → favorable pour acheteur d'options
    """
    history = get_iv_history(symbol, days)

    if len(history) < 20:
        logger.warning(
            f"{symbol} : historique IV insuffisant ({len(history)} jours). "
            "Percentile non calculable."
        )
        return None

    percentile = float(
        np.mean(history.values < current_iv) * 100
    )
    logger.info(
        f"{symbol} IV Percentile = {percentile:.1f}% "
        f"(IV={current_iv:.3f}, n={len(history)})"
    )
    return round(percentile, 1)


# ──────────────────────────────────────────────────────────────
# Sync CSV (backup)
# ──────────────────────────────────────────────────────────────

def _sync_csv(symbol: str, date_str: str, iv: float) -> None:
    """Ajoute une ligne au CSV de backup."""
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        file_exists = os.path.exists(config.IV_CSV_PATH)
        with open(config.IV_CSV_PATH, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["date", "symbol", "iv"])
            writer.writerow([date_str, symbol, f"{iv:.6f}"])
    except Exception as e:
        logger.warning(f"_sync_csv : {e}")


def _read_from_csv(symbol: str, days: int) -> pd.DataFrame:
    """Lit l'historique depuis le CSV si la DB est vide."""
    if not os.path.exists(config.IV_CSV_PATH):
        return pd.DataFrame(columns=["date", "iv"])
    try:
        df = pd.read_csv(config.IV_CSV_PATH)
        df = df[df["symbol"] == symbol].tail(days)
        return df[["date", "iv"]]
    except Exception as e:
        logger.warning(f"_read_from_csv({symbol}) : {e}")
        return pd.DataFrame(columns=["date", "iv"])


# ──────────────────────────────────────────────────────────────
# Import CSV initial (bootstrap)
# ──────────────────────────────────────────────────────────────

def import_csv_to_db(csv_path: Optional[str] = None) -> int:
    """
    Importe un CSV historique (colonnes: date, symbol, iv) en base.
    Utile pour amorcer la base avec des données historiques.
    Retourne le nombre de lignes importées.
    """
    path = csv_path or config.IV_CSV_PATH
    if not os.path.exists(path):
        logger.warning(f"CSV introuvable : {path}")
        return 0

    try:
        df = pd.read_csv(path)
        required = {"date", "symbol", "iv"}
        if not required.issubset(df.columns):
            logger.error(f"CSV {path} doit avoir les colonnes : {required}")
            return 0

        conn = _get_db_connection()
        imported = 0
        for _, row in df.iterrows():
            conn.execute(
                "INSERT OR IGNORE INTO iv_history (date, symbol, iv) VALUES (?, ?, ?)",
                (str(row["date"]), str(row["symbol"]), float(row["iv"]))
            )
            imported += 1
        conn.commit()
        conn.close()
        logger.info(f"Import CSV : {imported} lignes insérées depuis {path}.")
        return imported

    except Exception as e:
        logger.error(f"import_csv_to_db : {e}")
        return 0
