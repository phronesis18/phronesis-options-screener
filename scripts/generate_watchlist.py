import sys
import os
import json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from universe import get_full_universe

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def scrape_table(url, table_index=0, header=0):
    """Télécharge une page HTML et extrait un tableau pandas."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(resp.text, header=header)
        return tables[table_index] if len(tables) > table_index else None
    except Exception as e:
        print(f"⚠️ Erreur scraping {url}: {e}")
        return None

# 1. Base universe.py
base_symbols = {u.symbol for u in get_full_universe()}
print(f"📦 Base universe.py : {len(base_symbols)} symboles")

# 2. S&P 500 (Wikipedia)
sp500_df = scrape_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
if sp500_df is not None:
    sp500 = set(sp500_df["Symbol"].str.replace(".", "-", regex=False))
    print(f"📈 S&P 500 : {len(sp500)} symboles")
    base_symbols.update(sp500)

# 3. NASDAQ-100 (Wikipedia)
nasdaq_df = scrape_table("https://en.wikipedia.org/wiki/Nasdaq-100", table_index=4)
if nasdaq_df is not None:
    # La colonne s'appelle souvent "Ticker" ou "Symbol"
    ticker_col = "Ticker" if "Ticker" in nasdaq_df.columns else "Symbol"
    nasdaq100 = set(nasdaq_df[ticker_col].str.replace(".", "-", regex=False))
    print(f"📊 NASDAQ-100 : {len(nasdaq100)} symboles")
    base_symbols.update(nasdaq100)

# 4. ETFs supplémentaires (pour enrichir)
extra_etfs = [
    "SPY","QQQ","IWM","DIA","VTI","VOO","TLT","IEF","SHY","HYG","LQD",
    "GLD","SLV","USO","DBC","WEAT","CORN","SOYB","COW","XLE","XLF","XLK",
    "XLV","XLP","XLY","XLB","XLC","XLU","VNQ","EMB","EEM","EFA","AGG","BND",
    "VT","SCHD","IVV","IJH","IJR","MDY","VB","VO","VBK","VOT","VWO","EWJ",
    "EWZ","FXI","KWEB","ASHR","GDX","GDXJ","SILJ","URA","TAN","ICLN",
    "ARKK","ARKG","ARKW","ARKF","SMH","SOXX","HACK","CIBR","ROBO","AIQ",
    "DRIV","MSOS","BITO","GBTC","IBIT","FBTC","VXX","UVXY","SQQQ","SPXS",
    "SDS","QID","TMF","TBT"
]
base_symbols.update(extra_etfs)
print(f"🔄 Après ajout ETFs : {len(base_symbols)} symboles")

# 5. Small/Mid caps supplémentaires (si besoin)
extra_tickers = [
    "AFRM","UPST","SOFI","RIVN","LCID","NIO","XPEV","LI","BYND","FVRR",
    "PINS","SNAP","TWLO","ZM","DOCU","OKTA","NET","CRWD","ZS","MDB","DDOG",
    "HUBS","TEAM","WDAY","SNOW","PLTR","U","PATH","AI","BIGC","WISH","TDOC",
    "LVGO","ROKU","TTD","TTWO","EA","ATVI","NTES","BIDU","BABA","JD","PDD",
    "TCEHY","BZUN","MOMO","YY","IQ","HUYA","BEKE","ZTO","QFIN","FUTU","TIGR",
    "YMM","LU","KC","DIDI","BEST","DAO","JKS","DQ","CSIQ","SOL","SPI","JASO",
    "VALE","PBR","ABEV","GGB","SID","ERJ","SBS","CIG","TSU","VIV","TIMB","UGP",
    "ELP","AKO.B","BRFS","BZUN","YY","MOMO","IQ","TAL","EDU","GSX","FUTU",
    "TIGR","LX","YMM","BEKE","QFIN","FINV","QD","LU","KC","DIDI","BEST","DAO",
    "ZTO","JKS","DQ","CSIQ","SOL","SPI","JASO","CVNA","PLUG","ENPH","SEDG",
    "FSLR","SPWR","BLDP","BE","RUN","NOVA","STEM","CHPT","BLNK","QS","NKLA",
    "FCEL","RIDE","WISH","GME","AMC","BBBY","MULN","MARA","RIOT","BB","KOSS",
    "NOK","TLRY","SNDL","CLOV","SPCE","FUBO","RKT","UWMC","LAZR","ZIM",
    "HIMS","RBLX","COIN","HOOD"
]
base_symbols.update(extra_tickers)

# Limiter à 1800 (au cas où)
final_symbols = sorted(base_symbols)[:1800]

# Sauvegarde
os.makedirs("data", exist_ok=True)
with open("data/watchlist.json", "w") as f:
    json.dump(final_symbols, f, indent=2)

print(f"\n✅ Watchlist finale : {len(final_symbols)} symboles")
print(f"   Fichier : data/watchlist.json")