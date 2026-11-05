#!/usr/bin/env python3
"""Fetch intraday ETF quotes from Yahoo Finance using yfinance."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

SYMBOLS = [s.strip() for s in os.getenv("MARKET_SYMBOLS", "SXR8.DE,EUNL.DE").split(",") if s.strip()]
OUTPUT = Path("data/prices.json")
LISBON = ZoneInfo("Europe/Lisbon")


def fetch(symbol):
    ticker = yf.Ticker(symbol)
    minute = ticker.history(period="2d", interval="1m", auto_adjust=True)
    daily = ticker.history(period="10d", interval="1d", auto_adjust=True)
    if minute.empty or daily.empty:
        raise ValueError("Missing intraday or daily data")
    last_timestamp = minute.index[-1]
    last_day = last_timestamp.date()
    previous = daily[daily.index.date < last_day]
    if previous.empty:
        raise ValueError("Previous session close unavailable")
    price = float(minute["Close"].iloc[-1])
    close = float(previous["Close"].iloc[-1])
    timestamp = last_timestamp.tz_convert(LISBON)
    return {
        "symbol": symbol,
        "currency": "EUR" if symbol.endswith(".DE") else ticker.fast_info.get("currency", "UNKNOWN"),
        "price": round(price, 4),
        "previous_close": round(close, 4),
        "change": round(price - close, 4),
        "change_percent": round((price / close - 1) * 100, 4),
        "last_bar_time_lisbon": timestamp.isoformat(),
        "last_bar_time_utc": last_timestamp.tz_convert(timezone.utc).isoformat(),
        "bar_interval": "1m",
        "source": "Yahoo Finance via yfinance (unofficial; may be delayed)",
    }


def main():
    result = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "quotes": {}, "errors": {}}
    for symbol in SYMBOLS:
        try:
            result["quotes"][symbol] = fetch(symbol)
            print(f"{symbol}: {result['quotes'][symbol]['price']}")
        except Exception as exc:
            result["errors"][symbol] = str(exc)
            print(f"{symbol}: ERROR {exc}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not result["quotes"]:
        raise SystemExit("No valid quotes; refusing to publish")


if __name__ == "__main__":
    main()
