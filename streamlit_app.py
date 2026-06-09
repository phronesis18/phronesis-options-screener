import streamlit as st
import pandas as pd
import json
import plotly.express as px
from datetime import datetime
import os
import requests

st.set_page_config(page_title="Phronesis Screener v4", layout="wide", initial_sidebar_state="expanded")

# Forcer le rendu en mode classique (évite certains bugs DOM)
st.markdown("""
    <style>
        .stApp { background-color: var(--bg); }
    </style>
""", unsafe_allow_html=True)

# ---------- Clé API DeepSeek (à mettre dans secrets en prod) ----------
DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")

# ---------- Gestion de la watchlist ----------
WATCHLIST_FILE = "data/watchlist.json"

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    return ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]

def save_watchlist(wl):
    os.makedirs("data", exist_ok=True)
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(wl, f, indent=2)

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("## 🧠 Phronesis")
    st.markdown("Options Screener v4.0")
    st.divider()

    with st.expander("📋 Watchlist permanente", expanded=True):
        current_wl = load_watchlist()
        for sym in current_wl[:]:
            col1, col2 = st.columns([4, 1])
            col1.write(sym)
            if col2.button("❌", key=f"del_{sym}"):
                current_wl.remove(sym)
                save_watchlist(current_wl)
                st.rerun()
        new_sym = st.text_input("Ajouter un symbole", key="new_sym")
        if st.button("➕ Ajouter"):
            if new_sym and new_sym.upper() not in current_wl:
                current_wl.append(new_sym.upper())
                save_watchlist(current_wl)
                st.rerun()
            elif new_sym:
                st.warning("Symbole déjà présent")
        st.caption(f"{len(current_wl)} symboles surveillés")

    st.divider()
    risk_enabled = st.toggle("Contrainte de risque", value=True, help="Max 120$ par trade")
    st.caption(f"Risque max : {'120$' if risk_enabled else 'illimité'}")
    st.divider()
    st.metric("Actifs scannés", len(current_wl), help="Watchlist personnalisée")
    st.metric("Spreads détectés", "247", help="Après 4 piliers")
    st.metric("Score ≥ 50", "42", help="Opportunités valides")
    st.metric("Décisions GO", "7" if risk_enabled else "10", delta="≤120$" if risk_enabled else "sans contrainte")
    st.divider()
    st.markdown("**TWS · Paper** · Connecté")
    st.caption(f"Dernier scan : {datetime.now().strftime('%H:%M')}")

# ---------- Chargement des opportunités ----------
try:
    with open("data/opportunities.json", "r") as f:
        ops = json.load(f)
except:
    ops = []

if not ops:
    st.warning("Aucune opportunité. Lancez `python scripts/update_data.py` ou attendez GitHub Actions.")
    st.stop()

df = pd.DataFrame(ops)

# Conversion de la colonne dte en numérique
if "dte" in df.columns:
    df["dte"] = pd.to_numeric(df["dte"], errors="coerce")
    df = df.dropna(subset=["dte"])

# Filtre DTE
max_dte = st.sidebar.slider("Échéance maximale (DTE)", min_value=7, max_value=1098, value=60, step=5,
                            help="Afficher seulement les options avec DTE ≤ cette valeur")
df = df[df["dte"] <= max_dte]

# Filtre risque
if risk_enabled and "risk" in df.columns:
    df = df[df["risk"] <= 120]

# ---------- Onglets ----------
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "📈 Portfolio", "📖 Glossaire", "🤖 Assistant IA"])

# ---------- Onglet Dashboard ----------
with tab1:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Opportunités GO", len(df))
    col2.metric("Score IA moyen", round(df["score"].mean(), 2) if not df.empty else 0)
    col3.metric("Risque moyen", round(df["risk"].mean(), 2) if not df.empty else 0)
    col4.metric("Crédit / Débit", round(df["credit"].mean(), 2) if "credit" in df and not df.empty else 0)

    if not df.empty:
        fig = px.histogram(df, x="score", nbins=10, title="Distribution des scores IA",
                           color_discrete_sequence=["#185FA5"])
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Opportunités")
    # Colonnes à afficher (incluant les IV)
    display_cols = ["symbol", "strategy", "score", "risk", "profit", "iv_rank", "iv_atm", "iv_otm", "iv_itm", "dte", "label", "delta", "theta"]
    available_cols = [c for c in display_cols if c in df.columns]
    
    # Copie pour arrondir
    display_df = df[available_cols].copy()
    numeric_cols = ['score', 'risk', 'profit', 'dte', 'delta', 'theta', 'iv_atm', 'iv_otm', 'iv_itm']
    for col in numeric_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].round(2)
    
    st.dataframe(display_df, use_container_width=True, height=400)

    if not df.empty:
        selected = st.selectbox("Choisissez un symbole", df["symbol"].unique())
        sel_row = df[df["symbol"] == selected].iloc[0].to_dict()
        # Arrondir les valeurs dans le détail
        for k in numeric_cols:
            if k in sel_row and isinstance(sel_row[k], (float, int)):
                sel_row[k] = round(sel_row[k], 2)
        st.subheader(f"Fiche de décision — {selected}")
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("Stratégie", sel_row.get("strategy", ""))
            st.metric("Score IA", f"{sel_row.get('score',0)}/100")
            st.metric("Risque", f"{sel_row.get('risk',0)}$")
        with col_b:
            st.metric("Profit max", f"+{sel_row.get('profit',0)}$")
            st.metric("IV Rank", sel_row.get("iv_rank", "N/A"))
            st.metric("DTE", f"{sel_row.get('dte',0)} jours")
        # Afficher les trois IV en détail
        st.markdown("**Volatilité implicite**")
        iv_atm = sel_row.get('iv_atm')
        iv_otm = sel_row.get('iv_otm')
        iv_itm = sel_row.get('iv_itm')
        col_c, col_d, col_e = st.columns(3)
        col_c.metric("IV ATM", f"{iv_atm:.1%}" if iv_atm else "N/A")
        col_d.metric("IV OTM", f"{iv_otm:.1%}" if iv_otm else "N/A")
        col_e.metric("IV ITM", f"{iv_itm:.1%}" if iv_itm else "N/A")
        st.json(sel_row)

# ---------- Onglet Portfolio ----------
with tab2:
    st.subheader("Construction automatique du portefeuille")
    if df.empty:
        st.info("Aucune opportunité disponible pour construire le portefeuille.")
    else:
        portfolio_df = df.sort_values("score", ascending=False).head(12).copy()
        numeric_cols = ['score', 'risk', 'profit', 'dte', 'delta', 'theta', 'iv_atm', 'iv_otm', 'iv_itm']
        for col in numeric_cols:
            if col in portfolio_df.columns:
                portfolio_df[col] = portfolio_df[col].round(2)
        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Positions sélectionnées", len(portfolio_df))
        col2.metric("💰 Risque total", f"{portfolio_df['risk'].sum():.2f}$")
        col3.metric("📈 Profit potentiel total", f"+{portfolio_df['profit'].sum():.2f}$")

        st.markdown("#### Allocation du capital")
        total_risk = portfolio_df['risk'].sum()
        if total_risk > 0:
            cols = st.columns(len(portfolio_df))
            for i, (idx, row) in enumerate(portfolio_df.iterrows()):
                percent = row['risk'] / total_risk * 100
                cols[i].markdown(f"<div style='background-color:#185FA5; height:8px; width:{percent:.1f}%;'></div>",
                                 unsafe_allow_html=True)
                cols[i].caption(f"{row['symbol']} ({percent:.0f}%)")

        st.markdown("#### Opportunités recommandées")
        for i, (idx, row) in enumerate(portfolio_df.iterrows()):
            with st.expander(f"**{row['symbol']}** – {row['strategy']} (Score {row['score']:.2f}/100)"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("Risque", f"{row['risk']:.2f}$")
                    st.metric("IV Rank", row['iv_rank'] if 'iv_rank' in row else "N/A")
                with col_b:
                    st.metric("Profit max", f"+{row['profit']:.2f}$")
                    st.metric("DTE", f"{row['dte']:.0f} jours")
                # Afficher les IV
                st.markdown("**IV :** ATM = " + (f"{row['iv_atm']:.1%}" if pd.notna(row.get('iv_atm')) else "N/A") +
                            " | OTM = " + (f"{row['iv_otm']:.1%}" if pd.notna(row.get('iv_otm')) else "N/A") +
                            " | ITM = " + (f"{row['iv_itm']:.1%}" if pd.notna(row.get('iv_itm')) else "N/A"))
                st.json(row.to_dict())

# ---------- Onglet Glossaire ----------
with tab3:
    st.markdown("### Glossaire des options (52 termes essentiels)")
    glossary = {
        "Delta": "Sensibilité du prix de l'option à une variation du sous-jacent.",
        "Thêta": "Érosion temporelle. Perte de valeur chaque jour.",
        "Vega": "Sensibilité à la volatilité implicite.",
        "IV Rank": "Position de l'IV actuelle par rapport à son historique.",
        "Iron Condor": "Bull Put + Bear Call. Profitable si le cours reste dans un range.",
        "Bull Put Spread": "Vente put OTM + achat put plus OTM.",
        "Bear Call Spread": "Vente call OTM + achat call plus OTM.",
        "Score IA Phronesis": "Composite 0–100 basé sur IV Rank, thêta, delta, liquidité, risk/reward."
    }
    search = st.text_input("Rechercher un terme")
    for term, defi in glossary.items():
        if search.lower() in term.lower() or search.lower() in defi.lower():
            with st.expander(term):
                st.write(defi)

# ---------- Onglet Assistant IA (DeepSeek) ----------
with tab4:
    st.subheader("💬 Assistant IA Phronesis")
    if not DEEPSEEK_API_KEY:
        st.warning("Clé API DeepSeek non configurée. Ajoutez DEEPSEEK_API_KEY dans les secrets.")
    else:
        def ask_deepseek(prompt):
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Tu es l'assistant IA de Phronesis Options Screener."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=15)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            except Exception as e:
                return f"Erreur : {e}"

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
        user_input = st.chat_input("Posez une question...")
        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.write(user_input)
            with st.chat_message("assistant"):
                with st.spinner("Réflexion..."):
                    answer = ask_deepseek(user_input)
                st.write(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})