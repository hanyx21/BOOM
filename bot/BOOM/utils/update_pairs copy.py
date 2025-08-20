# import os, re
# from pathlib import Path
# import ccxt
# from dotenv import load_dotenv
#
# BINANCE = ccxt.binance()
#
# ENV_FILE = Path("../.env")          # adjust if your env file is elsewhere
# TARGET_VAR = "SELECTED_CRYPTO_PAIRS"
#
#
# def fetch_top_gainers(limit: int = 50) -> list[str]:
#     """Return top-N USDT-quoted spot pairs by 24 h %-change (positive only)."""
#     tickers = BINANCE.fetch_tickers()                 # 2–3 s for all symbols
#     gainers = []
#
#     for sym, t in tickers.items():
#         if not sym.endswith("/USDT"):
#             continue
#         pct = t.get("percentage")  # ccxt already computes 24h change %
#         if pct is None or pct <= 0:
#             continue
#         gainers.append((pct, sym))
#
#     gainers.sort(reverse=True)     # biggest % first
#     return [s for _, s in gainers[:limit]]
#
#
# def update_env_var(pairs: list[str]) -> None:
#     """Write SELECTED_CRYPTO_PAIRS=AAA,BBB,CCC into .env (create if missing)."""
#     line  = f"{TARGET_VAR}=" + ",".join(pairs) + "\n"
#
#     if ENV_FILE.exists():
#         lines = ENV_FILE.read_text().splitlines(keepends=True)
#         pattern = re.compile(rf"^{TARGET_VAR}=.*$", re.I)
#         replaced = False
#
#         for i, old in enumerate(lines):
#             if pattern.match(old):
#                 lines[i] = line
#                 replaced = True
#                 break
#         if not replaced:
#             lines.append(line)
#         ENV_FILE.write_text("".join(lines))
#     else:
#         ENV_FILE.write_text(line)
#
#     print(f"Updated {TARGET_VAR} with {len(pairs)} pairs.")
#
#
# def main():
#     load_dotenv(ENV_FILE)                      # so ccxt picks API keys if any
#     pairs = fetch_top_gainers(limit=50)
#     update_env_var(pairs)
#
#
# if __name__ == "__main__":
#     main()

"""
Build a broad but curated universe for the scalping bot.

* fast_money()      : tape-pressure + liquidity
* mean_revert()     : oversold flips
* low_corr()        : BTC-low-beta diversifiers
* funding_edge()    : short-squeeze candidates
* external_gainers(): CoinMarketCap top 100 / 24 h %
-----------------------------------------------------------------
Final list (~60) =  25 fast_money
                    15 mean_revert
                    10 funding_edge
                    10 low_corr
                    + external gainers until size hits 80
"""

############################################################################
# import os, re, random, requests, ccxt
# from pathlib import Path
# from dotenv  import load_dotenv
# import pandas as pd, numpy as np
#
# ENV_FILE   = Path("../.env")
# TARGET_VAR = "SELECTED_CRYPTO_PAIRS"
# from dotenv import load_dotenv
# print("Looking for .env at", ENV_FILE.resolve())
# BINANCE = ccxt.binance()
# # ----------------------------------------------------------------------
# def fast_money(limit=25):
#     gain=[]; ticks=BINANCE.fetch_tickers()
#     for sym,t in ticks.items():
#         if not sym.endswith("/USDT") or t["quoteVolume"]<5_000_000: continue
#         ohlcv=BINANCE.fetch_ohlcv(sym,"1m",limit=31)
#         vwap=sum(c[4]*c[5] for c in ohlcv[1:])/sum(c[5] for c in ohlcv[1:])
#         delta=(ohlcv[-1][4]-vwap)/vwap*100
#         if delta<0.25 or ohlcv[-1][4]<=max(c[4] for c in ohlcv[-8:-1]): continue
#         gain.append((delta,sym))
#     gain.sort(reverse=True); return [s for _,s in gain[:limit]]
#
# def mean_revert(limit=15):
#     picks=[]
#     for sym,t in BINANCE.fetch_tickers().items():
#         if not sym.endswith('/USDT') or t['quoteVolume']<1_000_000: continue
#         pct24=t['percentage'];  df=pd.DataFrame(BINANCE.fetch_ohlcv(sym,'15m',limit=32))
#         if pct24<-3 or pct24>2 or len(df)<32: continue
#         delta=df[4].diff(); up=delta.clip(lower=0).rolling(14).mean()
#         dn=(-delta.clip(upper=0)).rolling(14).mean(); rsi=100-100/(1+up/dn)
#         if rsi.iloc[-3]<35 and rsi.iloc[-1]>45: picks.append((rsi.iloc[-1],sym))
#     picks.sort(reverse=True); return [s for _,s in picks[:limit]]
#
# def low_corr(limit=10):
#     btc=pd.Series([c[4] for c in BINANCE.fetch_ohlcv('BTC/USDT','1h',limit=25)])
#     picks=[]
#     for sym in BINANCE.symbols:
#         if not sym.endswith('/USDT') or sym=='BTC/USDT': continue
#         closes=[c[4] for c in BINANCE.fetch_ohlcv(sym,'1h',limit=25)]
#         if len(closes)<25: continue
#         corr=float(np.corrcoef(btc,closes)[0,1]);
#         if abs(corr)<0.25: picks.append((abs(corr),sym))
#     picks.sort(); return [s for _,s in picks[:limit]]
#
# def funding_edge(limit: int = 10) -> list[str]:
#     """
#     Pick coins whose funding rate is negative (shorts pay longs)
#     *and* whose spot price is green (> +1 % today) – a squeeze setup.
#     """
#     BINANCE_FUT = ccxt.binance({'options': {'defaultType': 'future'}})
#
#     try:
#         fut = BINANCE_FUT.fapiPublicGetPremiumIndex()   # ← camel-case
#     except Exception as exc:
#         print("⚠️  Futures premium-index fetch failed:", exc)
#         return []
#
#     prem = {d['symbol'] + '/USDT': float(d['lastFundingRate']) for d in fut}
#     picks = []
#
#     for sym, t in BINANCE.fetch_tickers().items():
#         if sym not in prem or not sym.endswith('/USDT'):
#             continue
#         if t['percentage'] < 1:        # needs to be green on the day
#             continue
#         if prem[sym] < 0:              # shorts paying longs
#             picks.append((prem[sym], sym))
#
#     picks.sort()                       # most negative first
#     return [s for _, s in picks[:limit]]
#
#
# # ----------------------------------------------------------------------
# # utils/combo_pair_updater.py  (replace the old external_gainers function)
# # -----------------------------------------------------------------------
# def external_gainers(limit: int = 40) -> list[str]:
#     """
#     Use CoinMarketCap top movers.  Requires CMC_KEY in .env (or environment).
#     """
#     key = os.getenv("CMC_KEY")          # ← split into its own line
#     if not key:
#         print("No CMC_KEY in env; skipping external gainers.")
#         return []
#
#     url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
#     try:
#         r = requests.get(url,
#                          headers={"X-CMC_PRO_API_KEY": key},
#                          params={"convert": "USDT", "limit": 200})
#         r.raise_for_status()
#         data = r.json()["data"]
#
#         ranked = [(d["quote"]["USDT"]["percent_change_24h"],
#                    f'{d["symbol"]}/USDT')
#                   for d in data
#                   if d["quote"]["USDT"]["percent_change_24h"] > 0]
#
#         ranked.sort(reverse=True)
#         return [s for _, s in ranked[:limit]]
#
#     except Exception as exc:
#         print("CMC fetch failed:", exc)
#         return []
#
#
# # ----------------------------------------------------------------------
# def combo_pairs():
#     universe  = fast_money()
#     universe += mean_revert()
#     universe += funding_edge()
#     universe += low_corr()
#     universe  = list(dict.fromkeys(universe))      # dedupe
#
#     # pad with CoinMarketCap movers if you have a key
#     universe += [s for s in external_gainers(40) if s not in universe]
#     universe  = universe[:80]
#
#     # ---- safe ranking -------------------------------------------
#     info   = BINANCE.fetch_tickers()
#     ranked = [(pct, s)
#               for s in universe
#               if s in info and (pct := info[s]["percentage"]) is not None]
#
#     ranked.sort(reverse=True)
#     return [s for _, s in ranked] or universe      # fallback
#
# # ----------------------------------------------------------------------
# def update_env_var(pairs):
#     line=f"{TARGET_VAR}=" + ",".join(pairs)+"\n"
#     if ENV_FILE.exists():
#         txt=ENV_FILE.read_text().splitlines(keepends=True)
#         pat=re.compile(rf"^{TARGET_VAR}=.*$",re.I); rep=False
#         for i,l in enumerate(txt):
#             if pat.match(l): txt[i]=line; rep=True; break
#         if not rep: txt.append(line)
#         ENV_FILE.write_text("".join(txt))
#     else:
#         ENV_FILE.write_text(line)
#     print(f"Wrote {len(pairs)} pairs → {ENV_FILE}")
#
# # ----------------------------------------------------------------------
# def main():
#     #load_dotenv(ENV_FILE)          # for CMC_KEY if present
#     load_dotenv(dotenv_path=ENV_FILE, override=True)
#     print("CMC_KEY read as:", os.getenv("CMC_KEY") or "<None>")
#     pairs=combo_pairs()
#     update_env_var(pairs)
#
# if __name__=="__main__":
#     main()


###############################################################################################
import os
import requests
import ccxt
from dotenv import load_dotenv
from pathlib import Path
import re

ENV_FILE = Path("../.env")
TARGET_VAR = "SELECTED_CRYPTO_PAIRS"

BINANCE = ccxt.binance()


# -------------------------------------------------------
def gainers_binance(limit: int = 40) -> list[str]:
    """
    Focus on Binance's top gainers with positive percentage change.
    """
    gainers = []

    # Fetch the tickers data for Binance
    tickers = BINANCE.fetch_tickers()

    for symbol, ticker in tickers.items():
        # Filter for only USDT pairs with positive price change in the last 24 hours
        if not symbol.endswith('/USDT'):
            continue

        percentage_change = ticker.get('percentage', None)  # Use None as default if not found

        # Ensure percentage_change is valid (not None) and greater than 1%
        if percentage_change is not None and percentage_change > 1:
            gainers.append((percentage_change, symbol))

    # Sort the gainers by the percentage change (highest first)
    gainers.sort(reverse=True, key=lambda x: x[0])

    # Return top gainers based on the given limit
    return [symbol for _, symbol in gainers[:limit]]


def update_env_var(pairs):
    line = f"{TARGET_VAR}=" + ",".join(pairs) + "\n"
    if ENV_FILE.exists():
        txt = ENV_FILE.read_text().splitlines(keepends=True)
        pat = re.compile(rf"^{TARGET_VAR}=.*$", re.I)
        rep = False
        for i, l in enumerate(txt):
            if pat.match(l):
                txt[i] = line
                rep = True
                break
        if not rep:
            txt.append(line)
        ENV_FILE.write_text("".join(txt))
    else:
        ENV_FILE.write_text(line)
    print(f"Wrote {len(pairs)} pairs → {ENV_FILE}")


def main():
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    print("CMC_KEY read as:", os.getenv("CMC_KEY") or "<None>")

    # Fetch top gainers based on the new logic
    pairs = gainers_binance()

    # Update the environment variable with the selected pairs
    update_env_var(pairs)


if __name__ == "__main__":
    main()
