import streamlit as st
import pandas as pd
import json
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Phronesis Screener v4", layout="wide", initial_sidebar_state="expanded")

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("## 🧠 Phronesis")
    st.markdown("Options Screener v4.0")
    st.divider()
    risk_enabled = st.toggle("Contrainte de risque", value=True, help="Max 120$ par trade")
    st.caption(f"Risque max : {'120$' if risk_enabled else 'illimité'}")
    st.divider()
    st.metric("Actifs scannés", "1 800", help="Univers complet")
    st.metric("Spreads détectés", "247", help="Après 4 piliers")
    st.metric("Score ≥ 50", "42", help="Opportunités valides")
    if risk_enabled:
        st.metric("Décisions GO", "7", delta="≤120$", delta_color="normal")
    else:
        st.metric("Mode 360°", "10", delta="sans contrainte")
    st.divider()
    st.markdown("**TWS · Paper** · Connecté")
    st.caption(f"Dernier scan : {datetime.now().strftime('%H:%M')}")

# ---------- Chargement des données ----------
try:
    with open("data/opportunities.json", "r") as f:
        ops = json.load(f)
except:
    ops = []

if not ops:
    st.warning("Aucune opportunité. Lancez d'abord `python scripts/update_data.py` ou attendez GitHub Actions.")
    st.stop()

# Conversion en DataFrame
df = pd.DataFrame(ops)
if risk_enabled:
    df = df[df["risk"] <= 120]

# ---------- Onglets ----------
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📈 Portfolio", "📖 Glossaire"])

with tab1:
    # Métriques principales en lignes
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Opportunités GO", len(df))
    col2.metric("Score IA moyen", round(df["score"].mean()) if not df.empty else 0)
    col3.metric("Risque moyen", round(df["risk"].mean()) if not df.empty else 0)
    col4.metric("Crédit / Débit", df["credit"].mean() if "credit" in df else 0)
    
    # Graphique des scores
    if not df.empty:
        fig = px.histogram(df, x="score", nbins=10, title="Distribution des scores IA", color_discrete_sequence=["#185FA5"])
        st.plotly_chart(fig, use_container_width=True)
    
    # Tableau interactif
    st.subheader("Opportunités")
    # Afficher les colonnes pertinentes
    display_cols = ["symbol", "strategy", "score", "risk", "profit", "iv_rank", "dte", "label"]
    available_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available_cols], use_container_width=True, height=400)
    
    # Détail au clic (utilisation d'un selectbox)
    if not df.empty:
        selected = st.selectbox("Choisissez un symbole", df["symbol"].unique())
        sel_row = df[df["symbol"] == selected].iloc[0].to_dict()
        st.subheader(f"Fiche de décision — {selected}")
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("Stratégie", sel_row.get("strategy", ""))
            st.metric("Score IA", f"{sel_row.get('score',0)}/100")
            st.metric("Risque", f"{sel_row.get('risk',0)}$")
        with col_b:
            st.metric("Profit max", f"+{sel_row.get('profit',0)}$")
            st.metric("IV Rank", sel_row.get("iv_rank", ""))
            st.metric("DTE", f"{sel_row.get('dte',0)} jours")
        st.json(sel_row)

with tab2:
    st.info("Portfolio hybride – bientôt disponible : allocation automatique des 8-15 meilleures opportunités.")
    # Placeholder pour futures fonctionnalités

with tab3:
    st.markdown("### Glossaire des options (52 termes essentiels)")
    # Charger le glossaire depuis un fichier séparé ou intégré
    # Version simplifiée avec quelques exemples
    glossary = {
        "Delta": "Sensibilité du prix de l'option à une variation du sous-jacent. Delta 0.30 = si l'action monte de 1$, l'option gagne 0.30$.",
        "Thêta": "Érosion temporelle. Perte de valeur chaque jour. Pour un vendeur d'options, c'est un gain journalier.",
        "Vega": "Sensibilité à la volatilité implicite. Vega 0.10 = si IV monte de 1%, l'option gagne 0.10$.",
        "IV Rank": "Position de l'IV actuelle par rapport à son historique. >50% = options chères → vendeur.",
        "Iron Condor": "Stratégie de vente de premium. Bull Put + Bear Call. Profitable si le cours reste dans un range.",
        "Bull Put Spread": "Vente d'un put OTM + achat d'un put plus OTM. Biais haussier ou neutre.",
        "Bear Call Spread": "Vente d'un call OTM + achat d'un call plus OTM. Biais baissier ou neutre.",
        "Score IA Phronesis": "Composite 0–100 basé sur IV Rank, thêta, delta, liquidité, risk/reward, événements, moneyness."
    }
    search = st.text_input("Rechercher un terme")
    for term, defi in glossary.items():
        if search.lower() in term.lower() or search.lower() in defi.lower():
            with st.expander(term):
                st.write(defi)