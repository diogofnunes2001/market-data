"""Shared dynamic watchlist with permanent ETFs, commodities and US Treasury yield indices."""
import json
import os
import re
from pathlib import Path

CORE = ("SXR8.DE", "EUNL.DE", "GC=F", "SI=F", "BZ=F", "CL=F", "^IRX", "^FVX", "^TNX", "^TYX")
PATTERN = re.compile(r"^[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,24}$")

def get_symbols():
    override = os.getenv("MARKET_SYMBOLS")
    if override:
        requested = override.split(",")
    else:
        config = json.loads(Path("config/tickers.json").read_text(encoding="utf-8"))
        requested = config.get("tickers", [])
        if not isinstance(requested, list):
            raise ValueError("tickers must be a list")
    symbols = list(CORE)
    for raw in requested:
        if not isinstance(raw, str):
            raise ValueError("Ticker must be a string")
        symbol = raw.strip().upper()
        if not PATTERN.fullmatch(symbol):
            raise ValueError(f"Invalid ticker: {raw!r}")
        if symbol not in symbols:
            symbols.append(symbol)
    if len(symbols) > 25:
        raise ValueError("Watchlist cannot exceed 25 symbols")
    return symbols
