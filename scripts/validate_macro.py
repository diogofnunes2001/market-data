"""Validate machine contracts and make provider failures visible after publication."""
import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from macro_common import number

EXPECTED = {
    "interest_rates": {"fed_target_lower", "fed_target_upper", "fed_effective", "ecb_deposit", "ecb_main_refinancing", "ecb_marginal_lending"},
    "euribor": {"euribor_1m", "euribor_3m", "euribor_6m", "euribor_12m"},
    "sovereign_bonds": {"us_2y", "us_10y", "us_2s10s", "de_2y", "de_10y", "pt_10y", "pt_de_10y_spread"},
}


def validate(name, data, now):
    assert data["schema_version"] == 1
    generated = datetime.fromisoformat(data["generated_at_utc"])
    assert generated.tzinfo is not None
    assert 0 <= (now - generated).total_seconds() < 36 * 3600, "Stale or future collection"
    assert set(data["records"]) == EXPECTED[name]
    for key, r in data["records"].items():
        assert r["source"]["url"].startswith("https://")
        assert r["source"]["name"] and r["source"]["series_id"]
        assert r["kind"] in ("observed", "derived")
        assert r["status"] in ("fresh", "stale", "unavailable")
        assert r["usable"] == (r["status"] == "fresh")
        assert datetime.fromisoformat(r["retrieved_at_utc"]) == generated
        if r["status"] == "unavailable":
            assert r["value"] is None and r["error"] and key in data["errors"]
        else:
            assert date.fromisoformat(r["observation_date"]) <= now.date()
            if r["kind"] == "observed":
                number(r["value"])
            else:
                assert r["unit"] == "basis_points" and abs(r["value"]) <= 6000
        if r["status"] == "stale":
            assert r["error"] and key in data["errors"]
    if name == "sovereign_bonds" and data["records"]["pt_de_10y_spread"]["usable"]:
        spread = data["records"]["pt_de_10y_spread"]
        values = spread["input_observations"]
        assert all(r["observation_date"] == spread["observation_date"] for r in values.values())
        assert abs(spread["value"] - 100 * (values["pt_10y"]["value"] - values["de_10y"]["value"])) < 1e-6


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    failed = []
    lines = ["### Official rates and bonds", "", "| File | Status | Errors |", "| --- | --- | --- |"]
    for name in EXPECTED:
        data = json.loads((Path(os.getenv("MARKET_DATA_DIR", "data")) / (name + ".json")).read_text(encoding="utf-8"))
        validate(name, data, datetime.now(timezone.utc))
        print(name, data["status"], json.dumps(data["errors"], ensure_ascii=True))
        lines.append(f"| {name}.json | {data['status']} | {len(data['errors'])} |")
        if data["errors"]:
            failed.append(name)
    if args.health:
        summary = os.getenv("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as output:
                output.write("\n".join(lines) + "\n")
        if failed:
            raise SystemExit("Published explicit source errors/staleness: " + ", ".join(failed))


if __name__ == "__main__":
    main()
