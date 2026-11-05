#!/usr/bin/env python3
"""Daily historical returns and technical indicators."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import yfinance as yf

SYMBOLS = [s.strip() for s in os.getenv("MARKET_SYMBOLS", "SXR8.DE,EUNL.DE").split(",") if s.strip()]
OUT = Path("data/technical.json")

def collect(symbol):
    bars = yf.Ticker(symbol).history(period="2y", interval="1d", auto_adjust=True)
    if len(bars) < 30:
        raise ValueError("Insufficient daily history")
    close = bars["Close"].dropna()
    latest = float(close.iloc[-1])
    date = close.index[-1].date()
    # Return lookbacks are trading sessions; 1m and 1y are approximations.
    lookbacks = {"5_sessions": 5, "1_month_approx": 21, "3_months_approx": 63, "1_year_approx": 252}
    returns = {k: round((latest / float(close.iloc[-n-1]) - 1) * 100, 4) if len(close) > n else None for k, n in lookbacks.items()}
    year_start = close[close.index.year == date.year]
    returns["ytd"] = round((latest / float(year_start.iloc[0]) - 1) * 100, 4) if len(year_start) else None
    year = bars.tail(252)
    high52 = float(year["High"].max())
    low52 = float(year["Low"].min())
    return {
        "symbol": symbol,
        "last_daily_bar_date": str(date),
        "daily_close": round(latest, 4),
        "high_52w_approx": round(high52, 4),
        "low_52w_approx": round(low52, 4),
        "distance_from_52w_high_percent": round((latest / high52 - 1) * 100, 4),
        "distance_from_52w_low_percent": round((latest / low52 - 1) * 100, 4),
        "sma_50": round(float(close.tail(50).mean()), 4) if len(close) >= 50 else None,
        "sma_200": round(float(close.tail(200).mean()), 4) if len(close) >= 200 else None,
        "returns_percent": returns,
        "history_daily": [{"date": str(d.date()), "close": round(float(v), 4)} for d, v in close.tail(260).items()],
        "source": "Yahoo Finance via yfinance; adjusted daily bars; unofficial",
    }

def main():
    data = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "technical": {}, "errors": {}}
    for symbol in SYMBOLS:
        try:
            data["technical"][symbol] = collect(symbol)
        except Exception as e:
            data["errors"][symbol] = str(e)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if not data["technical"]:
        raise SystemExit("No historical statistics")

if __name__ == "__main__":
    main()
