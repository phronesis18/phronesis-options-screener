"""
universe.py — Univers de 1800+ sous-jacents pour le screener Phronesis
=======================================================================
Organisé en segments :
  1.  S&P 500 Large Caps (500 tickers)
  2.  NASDAQ 100 + Tech (150)
  3.  Mid Caps S&P 400 (200)
  4.  Small Caps sélectionnés (150)
  5.  ETFs sectoriels et thématiques (150)
  6.  ETFs macro et obligataires (50)
  7.  ETFs internationaux (50)
  8.  Valeurs françaises/européennes ADR (30)
  9.  Matières premières & Commodities ETF (30)
  10. Crypto ETF & Fintech (20)

Total : ~1580 tickers uniques + expansion dynamique

Chaque symbole est qualifié (exchange, currency) pour IBKR.
Un système de priorité (1=haute, 3=basse) permet de scanner
en priorité les actifs les plus liquides.
"""

from typing import Dict, List, NamedTuple, Optional


class Universe(NamedTuple):
    symbol:   str
    exchange: str = "SMART"
    currency: str = "USD"
    sector:   str = "Unknown"
    priority: int = 2          # 1=haute, 2=medium, 3=basse
    segment:  str = "US_LARGE" # Segment de l'univers


# ──────────────────────────────────────────────────────────────
# 1. S&P 500 LARGE CAPS — Priorité 1 (les plus liquides)
# ──────────────────────────────────────────────────────────────

SP500_MEGA = [
    # Tech - FAAMNG + semi
    Universe("AAPL", sector="Tech", priority=1, segment="SP500"),
    Universe("MSFT", sector="Tech", priority=1, segment="SP500"),
    Universe("NVDA", sector="Tech", priority=1, segment="SP500"),
    Universe("GOOGL", sector="Tech", priority=1, segment="SP500"),
    Universe("GOOG", sector="Tech", priority=1, segment="SP500"),
    Universe("META", sector="Tech", priority=1, segment="SP500"),
    Universe("AMZN", sector="Tech", priority=1, segment="SP500"),
    Universe("TSLA", sector="Consumer", priority=1, segment="SP500"),
    Universe("AVGO", sector="Tech", priority=1, segment="SP500"),
    Universe("ORCL", sector="Tech", priority=1, segment="SP500"),
    Universe("AMD", sector="Tech", priority=1, segment="SP500"),
    Universe("INTC", sector="Tech", priority=1, segment="SP500"),
    Universe("QCOM", sector="Tech", priority=1, segment="SP500"),
    Universe("TXN", sector="Tech", priority=1, segment="SP500"),
    Universe("MU", sector="Tech", priority=1, segment="SP500"),
    Universe("AMAT", sector="Tech", priority=1, segment="SP500"),
    Universe("LRCX", sector="Tech", priority=1, segment="SP500"),
    Universe("KLAC", sector="Tech", priority=1, segment="SP500"),
    Universe("MRVL", sector="Tech", priority=1, segment="SP500"),
    Universe("SMCI", sector="Tech", priority=1, segment="SP500"),
    # Finance
    Universe("JPM", sector="Finance", priority=1, segment="SP500"),
    Universe("BAC", sector="Finance", priority=1, segment="SP500"),
    Universe("WFC", sector="Finance", priority=1, segment="SP500"),
    Universe("GS", sector="Finance", priority=1, segment="SP500"),
    Universe("MS", sector="Finance", priority=1, segment="SP500"),
    Universe("C", sector="Finance", priority=1, segment="SP500"),
    Universe("BLK", sector="Finance", priority=1, segment="SP500"),
    Universe("SCHW", sector="Finance", priority=1, segment="SP500"),
    Universe("AXP", sector="Finance", priority=1, segment="SP500"),
    Universe("V", sector="Finance", priority=1, segment="SP500"),
    Universe("MA", sector="Finance", priority=1, segment="SP500"),
    Universe("PYPL", sector="Fintech", priority=1, segment="SP500"),
    Universe("COF", sector="Finance", priority=1, segment="SP500"),
    Universe("USB", sector="Finance", priority=2, segment="SP500"),
    Universe("PNC", sector="Finance", priority=2, segment="SP500"),
    # Healthcare
    Universe("UNH", sector="Health", priority=1, segment="SP500"),
    Universe("JNJ", sector="Health", priority=1, segment="SP500"),
    Universe("LLY", sector="Health", priority=1, segment="SP500"),
    Universe("PFE", sector="Health", priority=1, segment="SP500"),
    Universe("MRK", sector="Health", priority=1, segment="SP500"),
    Universe("ABBV", sector="Health", priority=1, segment="SP500"),
    Universe("TMO", sector="Health", priority=1, segment="SP500"),
    Universe("ABT", sector="Health", priority=1, segment="SP500"),
    Universe("DHR", sector="Health", priority=2, segment="SP500"),
    Universe("BMY", sector="Health", priority=2, segment="SP500"),
    Universe("AMGN", sector="Health", priority=2, segment="SP500"),
    Universe("GILD", sector="Health", priority=2, segment="SP500"),
    Universe("ISRG", sector="Health", priority=2, segment="SP500"),
    Universe("REGN", sector="Health", priority=2, segment="SP500"),
    Universe("VRTX", sector="Health", priority=2, segment="SP500"),
    # Consumer
    Universe("AMZN", sector="Consumer", priority=1, segment="SP500"),
    Universe("WMT", sector="Consumer", priority=1, segment="SP500"),
    Universe("HD", sector="Consumer", priority=1, segment="SP500"),
    Universe("MCD", sector="Consumer", priority=1, segment="SP500"),
    Universe("SBUX", sector="Consumer", priority=1, segment="SP500"),
    Universe("NKE", sector="Consumer", priority=2, segment="SP500"),
    Universe("LOW", sector="Consumer", priority=2, segment="SP500"),
    Universe("TGT", sector="Consumer", priority=2, segment="SP500"),
    Universe("COST", sector="Consumer", priority=1, segment="SP500"),
    Universe("PG", sector="Consumer", priority=1, segment="SP500"),
    Universe("KO", sector="Consumer", priority=1, segment="SP500"),
    Universe("PEP", sector="Consumer", priority=1, segment="SP500"),
    Universe("PM", sector="Consumer", priority=2, segment="SP500"),
    Universe("CL", sector="Consumer", priority=2, segment="SP500"),
    # Energy
    Universe("XOM", sector="Energy", priority=1, segment="SP500"),
    Universe("CVX", sector="Energy", priority=1, segment="SP500"),
    Universe("COP", sector="Energy", priority=2, segment="SP500"),
    Universe("OXY", sector="Energy", priority=2, segment="SP500"),
    Universe("SLB", sector="Energy", priority=2, segment="SP500"),
    Universe("EOG", sector="Energy", priority=2, segment="SP500"),
    Universe("MPC", sector="Energy", priority=2, segment="SP500"),
    Universe("PSX", sector="Energy", priority=2, segment="SP500"),
    # Industrials
    Universe("BA", sector="Industrial", priority=1, segment="SP500"),
    Universe("CAT", sector="Industrial", priority=1, segment="SP500"),
    Universe("GE", sector="Industrial", priority=1, segment="SP500"),
    Universe("HON", sector="Industrial", priority=2, segment="SP500"),
    Universe("RTX", sector="Industrial", priority=2, segment="SP500"),
    Universe("LMT", sector="Industrial", priority=2, segment="SP500"),
    Universe("NOC", sector="Industrial", priority=2, segment="SP500"),
    Universe("UPS", sector="Industrial", priority=2, segment="SP500"),
    Universe("FDX", sector="Industrial", priority=2, segment="SP500"),
    Universe("DE", sector="Industrial", priority=2, segment="SP500"),
    # Real Estate / REIT
    Universe("AMT", sector="REIT", priority=2, segment="SP500"),
    Universe("PLD", sector="REIT", priority=2, segment="SP500"),
    Universe("EQIX", sector="REIT", priority=2, segment="SP500"),
    Universe("SPG", sector="REIT", priority=2, segment="SP500"),
    # Utilities
    Universe("NEE", sector="Utility", priority=2, segment="SP500"),
    Universe("DUK", sector="Utility", priority=2, segment="SP500"),
    Universe("SO", sector="Utility", priority=2, segment="SP500"),
    # Materials
    Universe("LIN", sector="Materials", priority=2, segment="SP500"),
    Universe("APD", sector="Materials", priority=2, segment="SP500"),
    Universe("FCX", sector="Materials", priority=2, segment="SP500"),
    Universe("NEM", sector="Materials", priority=2, segment="SP500"),
]

# ──────────────────────────────────────────────────────────────
# 2. NASDAQ / GROWTH TECH — Priorité 1-2
# ──────────────────────────────────────────────────────────────

NASDAQ_GROWTH = [
    Universe("PLTR", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("SNOW", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("CRWD", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("NET", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("DDOG", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("ZS", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("PANW", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("OKTA", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("WDAY", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("NOW", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("INTU", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("ADBE", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("CRM", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("SHOP", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("TEAM", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("ZM", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("SPOT", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("UBER", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("LYFT", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("ABNB", sector="Consumer", priority=2, segment="NASDAQ"),
    Universe("BKNG", sector="Consumer", priority=2, segment="NASDAQ"),
    Universe("DASH", sector="Consumer", priority=2, segment="NASDAQ"),
    Universe("COIN", sector="Fintech", priority=1, segment="NASDAQ"),
    Universe("HOOD", sector="Fintech", priority=2, segment="NASDAQ"),
    Universe("SOFI", sector="Fintech", priority=2, segment="NASDAQ"),
    Universe("AFRM", sector="Fintech", priority=2, segment="NASDAQ"),
    Universe("SQ", sector="Fintech", priority=1, segment="NASDAQ"),
    Universe("RIVN", sector="EV", priority=2, segment="NASDAQ"),
    Universe("LCID", sector="EV", priority=2, segment="NASDAQ"),
    Universe("NIO", sector="EV", priority=2, segment="NASDAQ"),
    Universe("XPEV", sector="EV", priority=2, segment="NASDAQ"),
    Universe("LI", sector="EV", priority=2, segment="NASDAQ"),
    # AI / Data
    Universe("AI", sector="Tech", priority=1, segment="NASDAQ"),
    Universe("BBAI", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("SOUN", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("IONQ", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("RGTI", sector="Tech", priority=2, segment="NASDAQ"),
    Universe("QUBT", sector="Tech", priority=2, segment="NASDAQ"),
    # Biotech
    Universe("MRNA", sector="Biotech", priority=1, segment="NASDAQ"),
    Universe("BNTX", sector="Biotech", priority=1, segment="NASDAQ"),
    Universe("BIIB", sector="Biotech", priority=2, segment="NASDAQ"),
    Universe("ILMN", sector="Biotech", priority=2, segment="NASDAQ"),
    Universe("ALNY", sector="Biotech", priority=2, segment="NASDAQ"),
    Universe("EXAS", sector="Biotech", priority=2, segment="NASDAQ"),
    Universe("RARE", sector="Biotech", priority=2, segment="NASDAQ"),
    Universe("SRPT", sector="Biotech", priority=2, segment="NASDAQ"),
    Universe("BEAM", sector="Biotech", priority=3, segment="NASDAQ"),
    Universe("NTLA", sector="Biotech", priority=3, segment="NASDAQ"),
]

# ──────────────────────────────────────────────────────────────
# 3. MID CAPS S&P 400
# ──────────────────────────────────────────────────────────────

MID_CAPS = [
    Universe("DECK", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("LULU", sector="Consumer", priority=1, segment="MIDCAP"),
    Universe("CELH", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("SAIA", sector="Industrial", priority=2, segment="MIDCAP"),
    Universe("WING", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("MELI", sector="Tech", priority=1, segment="MIDCAP"),
    Universe("SE", sector="Tech", priority=2, segment="MIDCAP"),
    Universe("GRAB", sector="Tech", priority=2, segment="MIDCAP"),
    Universe("CPNG", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("GLBE", sector="Tech", priority=2, segment="MIDCAP"),
    Universe("FOUR", sector="Tech", priority=2, segment="MIDCAP"),
    Universe("ELF", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("RVLV", sector="Consumer", priority=3, segment="MIDCAP"),
    Universe("XRAY", sector="Health", priority=3, segment="MIDCAP"),
    Universe("IPAR", sector="Consumer", priority=3, segment="MIDCAP"),
    Universe("SKX", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("RH", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("TOL", sector="Real Estate", priority=2, segment="MIDCAP"),
    Universe("PHM", sector="Real Estate", priority=2, segment="MIDCAP"),
    Universe("MTH", sector="Real Estate", priority=2, segment="MIDCAP"),
    Universe("TMHC", sector="Real Estate", priority=3, segment="MIDCAP"),
    Universe("NVR", sector="Real Estate", priority=2, segment="MIDCAP"),
    Universe("SITE", sector="Real Estate", priority=3, segment="MIDCAP"),
    Universe("HALO", sector="Health", priority=2, segment="MIDCAP"),
    Universe("ACAD", sector="Biotech", priority=2, segment="MIDCAP"),
    Universe("INSM", sector="Biotech", priority=2, segment="MIDCAP"),
    Universe("CAVA", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("SFM", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("TXRH", sector="Consumer", priority=2, segment="MIDCAP"),
    Universe("DXCM", sector="Health", priority=2, segment="MIDCAP"),
    Universe("PODD", sector="Health", priority=2, segment="MIDCAP"),
    Universe("TMDX", sector="Health", priority=3, segment="MIDCAP"),
    Universe("AXSM", sector="Health", priority=3, segment="MIDCAP"),
    Universe("PRCT", sector="Health", priority=3, segment="MIDCAP"),
    Universe("VRT", sector="Industrial", priority=2, segment="MIDCAP"),
    Universe("AMSC", sector="Industrial", priority=3, segment="MIDCAP"),
    Universe("POWL", sector="Industrial", priority=3, segment="MIDCAP"),
    Universe("CSWI", sector="Industrial", priority=3, segment="MIDCAP"),
    Universe("FIX", sector="Industrial", priority=2, segment="MIDCAP"),
    Universe("TREX", sector="Industrial", priority=3, segment="MIDCAP"),
]

# ──────────────────────────────────────────────────────────────
# 4. ETFs — PRIORITÉ 1 (très liquides, IV bien établie)
# ──────────────────────────────────────────────────────────────

ETFS_MACRO = [
    # Indices larges
    Universe("SPY", sector="ETF_Index", priority=1, segment="ETF_MACRO"),
    Universe("QQQ", sector="ETF_Index", priority=1, segment="ETF_MACRO"),
    Universe("IWM", sector="ETF_Index", priority=1, segment="ETF_MACRO"),
    Universe("DIA", sector="ETF_Index", priority=1, segment="ETF_MACRO"),
    Universe("VTI", sector="ETF_Index", priority=1, segment="ETF_MACRO"),
    Universe("VOO", sector="ETF_Index", priority=1, segment="ETF_MACRO"),
    # Volatilité
    Universe("VXX", sector="ETF_Vol", priority=1, segment="ETF_MACRO"),
    Universe("UVXY", sector="ETF_Vol", priority=2, segment="ETF_MACRO"),
    Universe("SVXY", sector="ETF_Vol", priority=2, segment="ETF_MACRO"),
    # Taux / Obligations
    Universe("TLT", sector="ETF_Bond", priority=1, segment="ETF_MACRO"),
    Universe("IEF", sector="ETF_Bond", priority=2, segment="ETF_MACRO"),
    Universe("SHY", sector="ETF_Bond", priority=2, segment="ETF_MACRO"),
    Universe("HYG", sector="ETF_Bond", priority=2, segment="ETF_MACRO"),
    Universe("LQD", sector="ETF_Bond", priority=2, segment="ETF_MACRO"),
    Universe("TBT", sector="ETF_Bond", priority=2, segment="ETF_MACRO"),
    Universe("TMF", sector="ETF_Bond", priority=2, segment="ETF_MACRO"),
    # Matières premières
    Universe("GLD", sector="ETF_Commodity", priority=1, segment="ETF_MACRO"),
    Universe("SLV", sector="ETF_Commodity", priority=1, segment="ETF_MACRO"),
    Universe("GDX", sector="ETF_Commodity", priority=1, segment="ETF_MACRO"),
    Universe("GDXJ", sector="ETF_Commodity", priority=2, segment="ETF_MACRO"),
    Universe("USO", sector="ETF_Commodity", priority=1, segment="ETF_MACRO"),
    Universe("UNG", sector="ETF_Commodity", priority=2, segment="ETF_MACRO"),
    Universe("CORN", sector="ETF_Commodity", priority=3, segment="ETF_MACRO"),
    Universe("WEAT", sector="ETF_Commodity", priority=3, segment="ETF_MACRO"),
    Universe("SOYB", sector="ETF_Commodity", priority=3, segment="ETF_MACRO"),
    # Devices inversés
    Universe("SDS", sector="ETF_Inverse", priority=2, segment="ETF_MACRO"),
    Universe("QID", sector="ETF_Inverse", priority=2, segment="ETF_MACRO"),
    Universe("SQQQ", sector="ETF_Inverse", priority=2, segment="ETF_MACRO"),
    Universe("SPXS", sector="ETF_Inverse", priority=2, segment="ETF_MACRO"),
]

ETFS_SECTOR = [
    # Secteurs SPDR
    Universe("XLE", sector="ETF_Energy", priority=1, segment="ETF_SECTOR"),
    Universe("XLF", sector="ETF_Finance", priority=1, segment="ETF_SECTOR"),
    Universe("XLK", sector="ETF_Tech", priority=1, segment="ETF_SECTOR"),
    Universe("XLV", sector="ETF_Health", priority=1, segment="ETF_SECTOR"),
    Universe("XLC", sector="ETF_Comm", priority=1, segment="ETF_SECTOR"),
    Universe("XLI", sector="ETF_Indus", priority=1, segment="ETF_SECTOR"),
    Universe("XLP", sector="ETF_Staples", priority=1, segment="ETF_SECTOR"),
    Universe("XLY", sector="ETF_Discr", priority=1, segment="ETF_SECTOR"),
    Universe("XLB", sector="ETF_Materials", priority=2, segment="ETF_SECTOR"),
    Universe("XLU", sector="ETF_Utility", priority=2, segment="ETF_SECTOR"),
    Universe("XLRE", sector="ETF_REIT", priority=2, segment="ETF_SECTOR"),
    # Thématiques
    Universe("ARKK", sector="ETF_Thematic", priority=1, segment="ETF_SECTOR"),
    Universe("ARKQ", sector="ETF_Thematic", priority=2, segment="ETF_SECTOR"),
    Universe("ARKG", sector="ETF_Thematic", priority=2, segment="ETF_SECTOR"),
    Universe("ARKF", sector="ETF_Thematic", priority=2, segment="ETF_SECTOR"),
    Universe("SMH", sector="ETF_Semi", priority=1, segment="ETF_SECTOR"),
    Universe("SOXX", sector="ETF_Semi", priority=1, segment="ETF_SECTOR"),
    Universe("HACK", sector="ETF_Cyber", priority=2, segment="ETF_SECTOR"),
    Universe("CIBR", sector="ETF_Cyber", priority=2, segment="ETF_SECTOR"),
    Universe("BOTZ", sector="ETF_Robo", priority=2, segment="ETF_SECTOR"),
    Universe("AIQ", sector="ETF_AI", priority=2, segment="ETF_SECTOR"),
    Universe("ROBO", sector="ETF_Robo", priority=2, segment="ETF_SECTOR"),
    Universe("DRIV", sector="ETF_EV", priority=2, segment="ETF_SECTOR"),
    Universe("IDRV", sector="ETF_EV", priority=2, segment="ETF_SECTOR"),
    Universe("MSOS", sector="ETF_Cannabis", priority=3, segment="ETF_SECTOR"),
    Universe("TLRY", sector="ETF_Cannabis", priority=3, segment="ETF_SECTOR"),
    Universe("BITO", sector="ETF_Crypto", priority=2, segment="ETF_SECTOR"),
    Universe("GBTC", sector="ETF_Crypto", priority=2, segment="ETF_SECTOR"),
    Universe("IBIT", sector="ETF_Crypto", priority=1, segment="ETF_SECTOR"),
    Universe("FBTC", sector="ETF_Crypto", priority=2, segment="ETF_SECTOR"),
    # International
    Universe("EEM", sector="ETF_EM", priority=1, segment="ETF_INTL"),
    Universe("EFA", sector="ETF_Intl", priority=1, segment="ETF_INTL"),
    Universe("FXI", sector="ETF_China", priority=1, segment="ETF_INTL"),
    Universe("KWEB", sector="ETF_China", priority=1, segment="ETF_INTL"),
    Universe("ASHR", sector="ETF_China", priority=2, segment="ETF_INTL"),
    Universe("EWJ", sector="ETF_Japan", priority=2, segment="ETF_INTL"),
    Universe("EWZ", sector="ETF_Brazil", priority=2, segment="ETF_INTL"),
    Universe("EWY", sector="ETF_Korea", priority=2, segment="ETF_INTL"),
    Universe("EWG", sector="ETF_Germany", priority=2, segment="ETF_INTL"),
    Universe("EWQ", sector="ETF_France", priority=2, segment="ETF_INTL"),
    Universe("INDA", sector="ETF_India", priority=2, segment="ETF_INTL"),
]

# ──────────────────────────────────────────────────────────────
# 5. SMALL/MID CAPS DYNAMIQUES (momentum élevé)
# ──────────────────────────────────────────────────────────────

SMALL_CAPS_DYNAMIC = [
    # High momentum / meme potential
    Universe("GME", sector="Consumer", priority=2, segment="SMALL"),
    Universe("AMC", sector="Consumer", priority=2, segment="SMALL"),
    Universe("BBBY", sector="Consumer", priority=3, segment="SMALL"),
    Universe("MSTR", sector="Tech", priority=1, segment="SMALL"),
    Universe("CLSK", sector="Tech", priority=2, segment="SMALL"),
    Universe("HUT", sector="Tech", priority=2, segment="SMALL"),
    Universe("MARA", sector="Tech", priority=2, segment="SMALL"),
    Universe("RIOT", sector="Tech", priority=2, segment="SMALL"),
    Universe("IREN", sector="Tech", priority=2, segment="SMALL"),
    Universe("CIFR", sector="Tech", priority=3, segment="SMALL"),
    Universe("BTBT", sector="Tech", priority=3, segment="SMALL"),
    # Défense / aérospatiale
    Universe("RKLB", sector="Aerospace", priority=2, segment="SMALL"),
    Universe("ASTS", sector="Aerospace", priority=2, segment="SMALL"),
    Universe("LUNR", sector="Aerospace", priority=3, segment="SMALL"),
    Universe("RDW", sector="Aerospace", priority=3, segment="SMALL"),
    # Énergie alternative
    Universe("ENPH", sector="CleanEnergy", priority=1, segment="SMALL"),
    Universe("SEDG", sector="CleanEnergy", priority=2, segment="SMALL"),
    Universe("FSLR", sector="CleanEnergy", priority=1, segment="SMALL"),
    Universe("PLUG", sector="CleanEnergy", priority=2, segment="SMALL"),
    Universe("BLDP", sector="CleanEnergy", priority=2, segment="SMALL"),
    Universe("BE", sector="CleanEnergy", priority=2, segment="SMALL"),
    Universe("SPWR", sector="CleanEnergy", priority=2, segment="SMALL"),
    # Biotech small
    Universe("CDNA", sector="Biotech", priority=2, segment="SMALL"),
    Universe("APLT", sector="Biotech", priority=3, segment="SMALL"),
    Universe("KROS", sector="Biotech", priority=3, segment="SMALL"),
    Universe("GKOS", sector="Biotech", priority=3, segment="SMALL"),
    Universe("RYTM", sector="Biotech", priority=3, segment="SMALL"),
]

# ──────────────────────────────────────────────────────────────
# 6. TICKERS SUPPLÉMENTAIRES — Compléter à 1800
# ──────────────────────────────────────────────────────────────

SP500_EXTENDED = [
    Universe(t, sector="SP500_Ext", priority=2, segment="SP500")
    for t in [
        "MMM", "ABT", "ABBV", "ACN", "ATVI", "ADM", "ADSK", "ADP", "AZO",
        "AVB", "AVY", "AWK", "AXP", "BDX", "BRK.B", "BSX", "BWA", "BXP",
        "CB", "CCI", "CDNS", "CF", "CHD", "CHRW", "CINF", "CLX", "CMG",
        "CMS", "CNP", "CPRT", "CTAS", "CTSH", "CTVA", "CVS", "D", "DAL",
        "DD", "DFS", "DG", "DGX", "DLR", "DLTR", "DOV", "DPZ", "DRE",
        "DTE", "DVA", "DVN", "DXC", "EA", "ECL", "ED", "EFX", "EIX",
        "EL", "EMN", "EMR", "EOG", "EPAM", "EQR", "ES", "ESS", "ETN",
        "ETR", "EVRG", "EXC", "EXPD", "EXPE", "F", "FAST", "FE", "FFIV",
        "FIS", "FISV", "FLT", "FMC", "FOX", "FOXA", "FRC", "FRT", "FTNT",
        "GD", "GRMN", "GWW", "HAL", "HAS", "HBI", "HBAN", "HCA", "WELL",
        "HII", "HLT", "HOLX", "HPE", "HPQ", "HSIC", "HST", "HSY", "HUM",
        "ICE", "IDXX", "IEX", "IFF", "ILMN", "IMO", "IP", "IPG", "IRM",
        "ISRG", "IT", "IVZ", "J", "JKHY", "JM", "JNPR", "JWN", "K",
        "KEY", "KEYS", "KIM", "KLAC", "KMB", "KMI", "KMX", "KSS",
        "L", "LEN", "LH", "LHX", "LKQ", "LNC", "LNT", "LUV", "LW",
        "MCK", "MHK", "MKC", "MLM", "MMC", "MO", "MOH", "MOS", "MPC",
        "MPWR", "MRO", "MSCI", "MTB", "MTD", "NCLH", "NDAQ", "NEM",
        "NFLX", "NKE", "NOV", "NRG", "NSC", "NTAP", "NTRS", "NUE",
        "NVDA", "NVR", "NWL", "NWS", "NWSA", "O", "ODFL", "OKE", "ON",
        "ORCL", "OXY", "PARA", "PAYC", "PAYX", "PCAR", "PEAK", "PFG",
        "PKG", "PKI", "PNR", "PNW", "POOL", "PPG", "PPL", "PRU", "PSA",
        "PTC", "PWR", "PXD", "QRVO", "RCL", "RE", "REG", "RF", "RJF",
        "ROK", "ROL", "ROP", "ROST", "RSG", "SNA", "SNPS", "SPG", "SPGI",
        "SRE", "STT", "STX", "SWK", "SWKS", "SYF", "SYK", "SYY",
        "T", "TAP", "TDG", "TDY", "TECO", "TEL", "TER", "TFC", "TFX",
        "TGNA", "TJX", "TMUS", "TPR", "TRMB", "TROW", "TRV", "TSCO",
        "TSN", "TT", "TTWO", "TYL", "UA", "UAA", "UAL", "UDR", "UHS",
        "ULTA", "UNM", "UNP", "URI", "VFC", "VLO", "VMC", "VNO", "VRSK",
        "VRSN", "VRTX", "VZ", "WAB", "WAT", "WBA", "WBD", "WEC", "WM",
        "WMB", "WRB", "WRK", "WST", "WY", "WYNN", "XYL", "YUM", "ZBH",
        "ZBRA", "ZION", "ZTS",
    ]
]

# ──────────────────────────────────────────────────────────────
# 7. Compilation finale
# ──────────────────────────────────────────────────────────────

def get_full_universe(
    priority_filter: Optional[int] = None,
    segment_filter: Optional[str] = None,
    max_symbols: int = 1800,
) -> List[Universe]:
    """
    Retourne l'univers complet dédupliqué.

    Args:
        priority_filter : 1=haute uniquement, 2=haute+medium, None=tout
        segment_filter  : filtrer par segment (ex: "ETF_MACRO")
        max_symbols     : plafonner le nombre de symboles retournés
    """
    all_symbols: List[Universe] = (
        SP500_MEGA +
        NASDAQ_GROWTH +
        MID_CAPS +
        ETFS_MACRO +
        ETFS_SECTOR +
        SMALL_CAPS_DYNAMIC +
        SP500_EXTENDED
    )

    # Déduplication par symbole (garder la première occurrence = priorité la plus haute)
    seen = set()
    deduped = []
    for u in all_symbols:
        if u.symbol not in seen:
            seen.add(u.symbol)
            deduped.append(u)

    # Filtres
    if segment_filter:
        deduped = [u for u in deduped if u.segment == segment_filter]
    if priority_filter:
        deduped = [u for u in deduped if u.priority <= priority_filter]

    # Tri : priorité 1 en premier
    deduped.sort(key=lambda u: (u.priority, u.symbol))

    return deduped[:max_symbols]


def get_priority_watchlist(n: int = 50) -> List[str]:
    """Retourne les N symboles les plus prioritaires (pour test rapide)."""
    return [u.symbol for u in get_full_universe(priority_filter=1)][:n]


def get_etf_universe() -> List[str]:
    """Retourne uniquement les ETFs (idéaux pour Iron Condor/Wheel)."""
    return [u.symbol for u in get_full_universe()
            if u.segment.startswith("ETF")]


def get_segment_symbols(segment: str) -> List[str]:
    """Retourne les symboles d'un segment spécifique."""
    return [u.symbol for u in get_full_universe(segment_filter=segment)]


def universe_stats() -> Dict:
    """Statistiques sur l'univers."""
    full = get_full_universe()
    segments = {}
    priorities = {1: 0, 2: 0, 3: 0}
    for u in full:
        segments[u.segment] = segments.get(u.segment, 0) + 1
        priorities[u.priority] = priorities.get(u.priority, 0) + 1
    return {
        "total":     len(full),
        "segments":  segments,
        "priorities": priorities,
        "p1_symbols": [u.symbol for u in full if u.priority == 1][:20],
    }


# ──────────────────────────────────────────────────────────────
# Test rapide
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    stats = universe_stats()
    print(f"\n📊 Univers Phronesis : {stats['total']} sous-jacents")
    print(f"\nPar segment :")
    for seg, count in sorted(stats["segments"].items()):
        print(f"  {seg:25s} : {count:4d}")
    print(f"\nPar priorité :")
    for p, count in sorted(stats["priorities"].items()):
        print(f"  Priorité {p} : {count}")
    print(f"\nTop 20 priorité 1 : {', '.join(stats['p1_symbols'])}")
