import json

sp500 = ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","BRK-B","LLY","TSLA","V","UNH","XOM","JPM","JNJ","PG","MA","HD","CVX","ABBV","MRK","KO","PEP","COST","TMO","ADBE","CRM","AMD","NFLX","INTC","QCOM","TXN","CSCO","ACN","IBM","ORCL","LIN","DIS","ABT","PM","NEE","RTX","LOW","AMGN","HON","UNP","BKNG","BA","CAT","SPGI","DE","SYK","MDT","BLK","PLD","CMCSA","GS","DHR","INTU","AXP","VZ","NOW","T","ELV","UPS","LMT","ISRG","NKE","SCHW","PFE","ADP","CI","MMC","COP","BMY","ZTS","GILD","AMAT","ETN","REGN","CB","ADI","C","LRCX","MU","PANW","MCD","FIS","EQIX","GE","ICE","HUM","SBUX","CSX","PLTR","CME","PYPL","TGT","WM","MS","CVS","BDX","FISV","SHW","APH","MDLZ","AON","FCX","GM","WMB","MPC","NOC","CL","MMM","PGR","ITW","CTAS","EOG","WELL","APD","MAR","D","EMR","AJG","OXY","USB","TDG","HLT","AIG","ADSK","TRV","ADM","KMB","JCI","PSA","MET","VLO","ALL","SLB","ROST","SRE","PCAR","CCI","AEP","NSC","PSX","BK","CARR","CNC","CPRT","F","VRTX","O","PWR","LHX","IDXX","EXC","MCHP","PAYX","ODFL","FAST","YUM","SNPS","CDNS","BIIB","MNST","DXCM","KHC","KMI","HCA","KR"]
etfs = ["SPY","QQQ","IWM","DIA","TLT","GLD","SLV","USO","XLE","XLF","XLK","XLV","XLI","XLP","XLY","XLB","XLC","XLU","VNQ","HYG","LQD","EMB","EEM","EFA","AGG","BND","SHY","IEI","TIP","TLH","EDV","VT","VTI","SCHD","VOO","IVV"]
commodities = ["GLD","SLV","USO","DBC","GSG","WEAT","CORN","SOYB","COW","JJG"]
watchlist = list(set(sp500[:250] + etfs + commodities))
watchlist = [s.upper() for s in watchlist if s and len(s) <= 5]
watchlist = sorted(watchlist)[:350]
with open("data/watchlist.json", "w") as f:
    json.dump(watchlist, f, indent=2)
print(f"Watchlist générée : {len(watchlist)} symboles")
