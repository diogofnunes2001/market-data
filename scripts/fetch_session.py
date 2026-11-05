#!/usr/bin/env python3
"""Intraday session statistics; all values refer to the last available trading session."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import yfinance as yf

SYMBOLS = [s.strip() for s in os.getenv("MARKET_SYMBOLS", "SXR8.DE,EUNL.DE").split(",") if s.strip()]
OUT = Path("data/session.json")
TZ = ZoneInfo("Europe/Lisbon")

def collect(symbol):
    t = yf.Ticker(symbol)
    bars = t.history(period="5d", interval="1m", auto_adjust=True)
    if bars.empty:
        raise ValueError("No minute bars")
    last = bars.index[-1]
    session = bars[bars.index.date == last.date()]
    if session.empty:
        raise ValueError("No bars in latest session")
    high = float(session["High"].max())
    low = float(session["Low"].min())
    opening = float(session["Open"].iloc[0])
    latest = float(session["Close"].iloc[-1])
    volume = int(session["Volume"].fillna(0).sum())
    return {
        "symbol": symbol,
        "session_date_exchange": str(last.date()),
        "open": round(opening, 4),
        "high": round(high, 4),
        "low": round(low, 4),
        "last": round(latest, 4),
        "session_range_percent": round((high / low - 1) * 100, 4) if low else None,
        "from_open_percent": round((latest / opening - 1) * 100, 4) if opening else None,
        "below_session_high_percent": round((latest / high - 1) * 100, 4) if high else None,
        "above_session_low_percent": round((latest / low - 1) * 100, 4) if low else None,
        "volume": volume,
        "volume_unit": "shares",
        "last_bar_time_lisbon": last.tz_convert(TZ).isoformat(),
        "source": "Yahoo Finance via yfinance; unofficial, may be delayed",
    }

def main():
    data = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "sessions": {}, "errors": {}}
    for symbol in SYMBOLS:
        try:
            data["sessions"][symbol] = collect(symbol)
        except Exception as e:
            data["errors"][symbol] = str(e)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if not data["sessions"]:
        raise SystemExit("No session statistics")

if __name__ == "__main__":
    main()
