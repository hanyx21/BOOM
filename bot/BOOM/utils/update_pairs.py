# update_pairs.py  – universe = USDT spot pairs up ≥ 10 % (24 h)

import os, re
import ccxt
from pathlib import Path
from dotenv import load_dotenv

ENV_FILE   = Path(".env")            # adjust the path if needed
TARGET_VAR = "SELECTED_CRYPTO_PAIRS"

BINANCE = ccxt.binance()

# ----------------------------------------------------------------------
def gainers_binance(limit: int = 40, pct_min: float = 10.0) -> list[str]:
    """
    Return up to <limit> Binance spot pairs (…/USDT) whose
    24-hour priceChangePercent is >= pct_min (default 10 %).
    """
    tickers = BINANCE.fetch_tickers()    # single bulk call
    gainers = []

    for sym, t in tickers.items():
        if not sym.endswith("/USDT"):        # keep USDT spot only
            continue

        # priceChangePercent is a string in the raw response → cast to float
        pct = float(t["info"].get("priceChangePercent", 0))
        if pct >= pct_min:
            gainers.append((pct, sym))

    gainers.sort(reverse=True)               # biggest % first
    return [sym for _, sym in gainers[:limit]]

# ----------------------------------------------------------------------
def update_env_var(pairs: list[str]) -> None:
    """Insert or replace SELECTED_CRYPTO_PAIRS=... inside ../.env."""
    new_line = f"{TARGET_VAR}=" + ",".join(pairs) + "\n"

    if ENV_FILE.exists():
        lines = ENV_FILE.read_text().splitlines(keepends=True)
        pat   = re.compile(rf"^{TARGET_VAR}=.*$", re.I)
        replaced = False

        for i, l in enumerate(lines):
            if pat.match(l):
                lines[i] = new_line
                replaced = True
                break
        if not replaced:
            lines.append(new_line)

        ENV_FILE.write_text("".join(lines))
    else:
        ENV_FILE.write_text(new_line)

    print(f"Wrote {len(pairs)} pairs → {ENV_FILE}")

# ----------------------------------------------------------------------
def main() -> None:
    load_dotenv(dotenv_path=ENV_FILE, override=True)  # optional: picks API keys
    pairs = gainers_binance(limit=40, pct_min=10.0)
    update_env_var(pairs)

# ----------------------------------------------------------------------
if __name__ == "__main__":
    main()
