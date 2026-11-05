"""Shared transport, provenance and freshness contract for supplemental data."""
import json
import math
import os
import ssl
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from defusedxml import ElementTree as ET
import certifi


def utcnow():
    return datetime.now(timezone.utc)


def business_age(observed, today):
    """Weekday lag; holidays are covered by a documented three-weekday allowance."""
    if observed > today:
        raise ValueError("Future observation date")
    return sum((observed + timedelta(days=i)).weekday() < 5
               for i in range(1, (today - observed).days + 1))


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Missing value or boolean is not a rate")
    result = float(value)
    if not math.isfinite(result) or not -10 <= result <= 50:
        raise ValueError("Missing/non-finite/out-of-range rate (-10..50 percent)")
    return result


def download(url):
    """Bounded HTTPS requests, certificate validation, and retries; no secret URLs."""
    if not url.startswith("https://"):
        raise ValueError("HTTPS required")
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "market-data/1.0 (public statistical feeds)",
                                            "Accept": "*/*"})
            with urlopen(request, timeout=25, context=ssl.create_default_context(cafile=certifi.where())) as response:
                body = response.read(8_000_001)
                if len(body) > 8_000_000:
                    raise ValueError("Response exceeds 8 MB")
                return body.decode("utf-8-sig")
        except (HTTPError, URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def source(name, url, series, **extra):
    return {"name": name, "url": url, "series_id": series, **extra}


def record(value, observed, origin, now, *, unit="percent_per_annum", kind="observed",
           max_age=3, effective_date=None):
    observed = date.fromisoformat(observed)
    age = business_age(observed, now.date())
    fresh = age <= max_age
    result = {"kind": kind, "value": number(value), "unit": unit,
              "observation_date": observed.isoformat(), "retrieved_at_utc": now.isoformat(),
              "source": origin, "status": "fresh" if fresh else "stale", "usable": fresh,
              "freshness": {"age_weekdays": age, "max_age_weekdays": max_age,
                            "calendar": "weekdays; allowance includes publication lag and holidays"},
              "error": None if fresh else "Observation exceeds freshness allowance"}
    if effective_date:
        result["effective_date"] = effective_date
    return result


def missing(origin, now, error, kind="observed", unit="percent_per_annum"):
    return {"kind": kind, "value": None, "unit": unit, "observation_date": None,
            "retrieved_at_utc": now.isoformat(), "source": origin, "status": "unavailable",
            "usable": False, "freshness": None, "error": str(error)[:500]}


def document(records, now, **extra):
    errors = {key: r["error"] for key, r in records.items() if r.get("error")}
    return {"schema_version": 1, "generated_at_utc": now.isoformat(),
            "status": "ok" if not errors else "partial" if any(r["usable"] for r in records.values()) else "unavailable",
            "records": records, "errors": errors, **extra}


def write_json(name, payload, now):
    """Atomic latest plus immutable per-run snapshot, all from the same collection."""
    directory = Path(os.getenv("MARKET_DATA_DIR", "data"))
    paths = [directory / (name + ".json"),
             directory / "history" / now.strftime("%Y-%m-%d") / (name + "_" + now.strftime("%H%M%S%f") + ".json")]
    body = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(body, encoding="utf-8")
        temporary.replace(path)


def spread(left, right, left_id, right_id, now):
    origin = source("Calculated from observed yields", "https://github.com/diogofnunes2001/market-data",
                    f"{left_id} - {right_id}", inputs={left_id: left["source"], right_id: right["source"]})
    if not left["usable"] or not right["usable"]:
        return missing(origin, now, "Input missing or stale", "derived", "basis_points")
    if left["observation_date"] != right["observation_date"]:
        return missing(origin, now, "Input observation dates differ; refusing asynchronous spread", "derived", "basis_points")
    result = record(0, left["observation_date"], origin, now, kind="derived", unit="basis_points")
    result["value"] = round(100 * (left["value"] - right["value"]), 4)
    result["formula"] = f"100 * ({left_id} - {right_id}); percentage points to basis points"
    return result
