import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# Pour utiliser les secrets Streamlit (si présents) dans data_fetcher
if "TWELVE_DATA_API_KEY" in st.secrets:
    os.environ["TWELVE_DATA_API_KEY"] = st.secrets["TWELVE_DATA_API_KEY"]
if "ALPHA_VANTAGE_API_KEY" in st.secrets:
    os.environ["ALPHA_VANTAGE_API_KEY"] = st.secrets["ALPHA_VANTAGE_API_KEY"]

st.set_page_config(page_title="Phronesis Screener", layout="wide")
st.title("🧠 Phronesis Options Screener")
st.markdown("### Opportunités générées toutes les 2 heures (données multi-sources)")

# Charger les données pré-calculées
try:
    with open("data/opportunities.json", "r") as f:
        decisions = json.load(f)
except FileNotFoundError:
    st.warning("Aucune donnée disponible. Le premier scan va être exécuté automatiquement.")
    decisions = []
except Exception as e:
    st.error(f"Erreur de chargement: {e}")
    decisions = []

if not decisions:
    st.info("En attente de la première analyse. Revenez dans quelques minutes.")
else:
    # Convertir en DataFrame pour affichage
    df = pd.DataFrame(decisions)
    # Sélectionner les colonnes pertinentes
    cols = ["symbol", "strategy_name", "conviction", "go_no_go", "risk_usd", "max_profit_usd", "iv_rank", "breakeven"]
    # S'assurer que les colonnes existent
    available_cols = [c for c in cols if c in df.columns]
    df_display = df[available_cols].copy()
    if "go_no_go" in df_display.columns:
        df_display["go_no_go"] = df_display["go_no_go"].apply(lambda x: "✅ GO" if x else "🚫 NO-GO")
    st.dataframe(df_display, use_container_width=True)
    
    # Détail d'une fiche sélectionnée
    st.subheader("📄 Fiche de décision détaillée")
    if "symbol" in df.columns:
        symbol_choice = st.selectbox("Choisissez un symbole", df["symbol"].unique())
        selected = df[df["symbol"] == symbol_choice].iloc[0]
        st.json(selected)
    else:
        st.write("Aucun symbole disponible")

st.markdown("---")
st.caption(f"Dernière mise à jour : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
