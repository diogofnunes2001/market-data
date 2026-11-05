#!/usr/bin/env python3
"""Collect official observed policy rates, Euribor and sovereign yields."""
import csv
import io
import json
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from macro_common import ET, document, download, missing, number, record, source, spread, utcnow, write_json

TREASURY = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
FED = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json"
EURIBOR = "https://reports.suomenpankki.fi/WebForms/ReportViewerPage.aspx?output=xml&report=%2Ftilastot%2Fmarkkina-_ja_hallinnolliset_korot%2Feuribor_korot_today_xml_en"
BP = "https://bpstat.bportugal.pt/data/v1/domains/26/datasets/690b7b36fd36c0dbe249c48cbbc39524/?series_ids=12099459&obs_since={start}"
# The change-event histories are small. The API currently returns 500 for
# lastNObservations on MRR_FR/MLFR, so request the complete official histories.
ECB = "https://data-api.ecb.europa.eu/service/data/FM/{key}?format=csvdata"
BUND = "https://api.statistiken.bundesbank.de/rest/data/BBSSY/{key}?format=csv&lang=en&startPeriod={start}"


def parse_treasury(text):
    rows = []
    for prop in ET.fromstring(text).iter():
        if prop.tag.endswith("}properties"):
            fields = {child.tag.split("}")[-1]: child.text for child in prop}
            if fields.get("NEW_DATE"):
                rows.append((fields["NEW_DATE"][:10], fields.get("BC_2YEAR"), fields.get("BC_10YEAR")))
    if not rows:
        raise ValueError("No Treasury observations")
    day, two, ten = max(rows, key=lambda r: r[0])
    return day, number(two), number(ten)


def parse_ecb(text, key, today):
    rows = list(csv.DictReader(io.StringIO(text)))
    valid = [r for r in rows if r.get("OBS_VALUE") and r.get("OBS_STATUS") not in ("M", "L")]
    if not valid or any(r.get("KEY") != "FM." + key for r in valid):
        raise ValueError("Missing or unexpected ECB series")
    effective = [r for r in valid if r["TIME_PERIOD"] <= today]
    if not effective:
        raise ValueError("No ECB rate effective on collection date")
    row = max(effective, key=lambda r: r["TIME_PERIOD"])
    if row.get("UNIT") not in ("PCPA", "PC") or row.get("UNIT_MULT", "0") != "0":
        raise ValueError("Unexpected ECB rate unit or multiplier")
    return row["TIME_PERIOD"], number(row["OBS_VALUE"])


def parse_bund(text):
    rows = list(csv.reader(io.StringIO(text)))
    candidates = [r for r in rows if len(r) >= 2 and len(r[0]) == 10 and r[0][4:5] == "-"]
    if not candidates:
        raise ValueError("No Bundesbank daily observations")
    # Missing dates are excluded; retained dates are still checked for freshness.
    return {r[0]: number(r[1]) for r in candidates if r[1].strip() not in (".", "", "-", "NA")}


def parse_bp(text):
    data = json.loads(text)
    if [r["id"] for r in data["extension"]["series"]] != [12099459]:
        raise ValueError("Unexpected BPstat series")
    ids, sizes = data["id"], data["size"]
    if ids[-1] != "reference_date" or any(n != 1 for n in sizes[:-1]):
        raise ValueError("Expected single BPstat daily series")
    cat = data["dimension"]["reference_date"]["category"]["index"]
    dates = cat if isinstance(cat, list) else sorted(cat, key=cat.get)
    values = data["value"]
    rows = [(d, values[i] if isinstance(values, list) else values.get(str(i))) for i, d in enumerate(dates)]
    return {day: number(value) for day, value in rows if value is not None}


def parse_euribor(text):
    root = ET.fromstring(text)
    periods = [p for p in root.iter() if p.tag.split("}")[-1] == "period"]
    if not periods:
        raise ValueError("Missing Euribor period")
    period = max(periods, key=lambda p: p.attrib["value"])
    rates = {}
    for rate in period.iter():
        if rate.tag.split("}")[-1] == "rate":
            name = rate.attrib["name"]
            if name.endswith("month (act/360)"):
                rates[name.split()[0] + "m"] = number(next(iter(rate)).attrib["value"])
    if set(rates) != {"1m", "3m", "6m", "12m"}:
        raise ValueError("Missing/changed Euribor ACT/360 tenors")
    return period.attrib["value"], rates


def collect(now):
    start = (now.date() - timedelta(days=35)).isoformat()
    # Providers are isolated: an outage cannot suppress the other data or the 25 tickers.
    tasks = {
        "treasury": (TREASURY.format(year=now.year), parse_treasury),
        "fed": (FED, json.loads),
        "euribor": (EURIBOR, parse_euribor),
        "pt_10y": (BP.format(start=start), parse_bp),
    }
    for name, code in {"ecb_deposit": "DFR", "ecb_main_refinancing": "MRR_FR", "ecb_marginal_lending": "MLFR"}.items():
        key = f"B.U2.EUR.4F.KR.{code}.LEV"
        tasks[name] = (ECB.format(key=key), lambda text, key=key: parse_ecb(text, key, now.date().isoformat()))
    for name, code in {"de_2y": "A610.000000WT0202", "de_10y": "A630.000000WT1010"}.items():
        tasks[name] = (BUND.format(key=f"D.REN.EUR.{code}.A", start=start), parse_bund)

    def run(item):
        name, (url, parser) = item
        try:
            return name, parser(download(url)), None
        except Exception as exc:
            return name, None, f"{type(exc).__name__}: {exc}"

    results = {name: (data, error) for name, data, error in ThreadPoolExecutor(max_workers=6).map(run, tasks.items())}
    rates, euribor, bonds = {}, {}, {}

    def put(dest, name, provider, origin, selector, policy=False):
        data, error = results[provider]
        try:
            if error:
                raise ValueError(error)
            day, value = selector(data)
            dest[name] = record(value, day, origin, now)
            if policy:
                # This is a change-event series. A rate remains effective until superseded;
                # its effective date is NOT its publication freshness date.
                dest[name].update(status="fresh", usable=True, error=None, effective_date=day)
                dest[name]["freshness"] = {"basis": "successful_query_of_current_change_event_series",
                                          "checked_at_utc": now.isoformat(), "max_retrieval_age_hours": 36}
        except Exception as exc:
            dest[name] = missing(origin, now, exc)

    for name, pos in (("us_2y", 1), ("us_10y", 2)):
        put(bonds, name, "treasury", source("US Treasury", tasks["treasury"][0], "BC_2YEAR" if pos == 1 else "BC_10YEAR"),
            lambda data, pos=pos: (data[0], data[pos]))
    for name, field in (("fed_target_lower", "targetRateFrom"), ("fed_target_upper", "targetRateTo"), ("fed_effective", "percentRate")):
        put(rates, name, "fed", source("Federal Reserve Bank of New York", FED, field),
            lambda data, field=field: (max(data["refRates"], key=lambda r: r["effectiveDate"])["effectiveDate"],
                                      max(data["refRates"], key=lambda r: r["effectiveDate"])[field]))
    if rates["fed_target_lower"]["usable"] and rates["fed_target_upper"]["usable"]:
        if rates["fed_target_lower"]["value"] > rates["fed_target_upper"]["value"]:
            for key in ("fed_target_lower", "fed_target_upper"):
                rates[key] = missing(rates[key]["source"], now, "Inverted Fed target range")
    for name in ("ecb_deposit", "ecb_main_refinancing", "ecb_marginal_lending"):
        put(rates, name, name, source("European Central Bank", tasks[name][0], tasks[name][0].split("/FM/")[1].split("?")[0]), lambda data: data, policy=True)
    for tenor in ("1m", "3m", "6m", "12m"):
        put(euribor, "euribor_" + tenor, "euribor",
            source("Bank of Finland / EMMI", EURIBOR, tenor + " ACT/360", publication_delay="24 hours", terms_url="https://www.suomenpankki.fi/en/statistics/interest-rates-and-exchange-rates/euribor-rates/"),
            lambda data, tenor=tenor: (data[0], data[1][tenor]))
    for name in ("pt_10y", "de_2y", "de_10y"):
        put(bonds, name, name, source("Banco de Portugal / LSEG" if name == "pt_10y" else "Deutsche Bundesbank", tasks[name][0],
                                     "12099459" if name == "pt_10y" else tasks[name][0].split("/BBSSY/")[1].split("?")[0]), lambda data: (max(data), data[max(data)]))
    bonds["us_2s10s"] = spread(bonds["us_10y"], bonds["us_2y"], "us_10y", "us_2y", now)
    aligned = {name: bonds[name] for name in ("pt_10y", "de_10y")}
    if all(results[name][0] for name in aligned):
        common = set(results["pt_10y"][0]) & set(results["de_10y"][0])
        if common:
            day = max(common)
            aligned = {name: record(results[name][0][day], day, bonds[name]["source"], now) for name in aligned}
    bonds["pt_de_10y_spread"] = spread(aligned["pt_10y"], aligned["de_10y"], "pt_10y", "de_10y", now)
    bonds["pt_de_10y_spread"]["input_observations"] = {name: {"value": r["value"], "observation_date": r["observation_date"]} for name, r in aligned.items()}
    return {"interest_rates": document(rates, now), "euribor": document(euribor, now), "sovereign_bonds": document(bonds, now)}


def main():
    now = utcnow()
    for name, payload in collect(now).items():
        write_json(name, payload, now)
        print(name, payload["status"], json.dumps(payload["errors"], ensure_ascii=True))


if __name__ == "__main__":
    main()
