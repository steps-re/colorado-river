#!/usr/bin/env python3
"""Per-reservoir hourly power prices, instead of blanketing seven reservoirs with one
California node.

Adversarial review (both reviewers, independently): using CAISO SP15 for the whole basin
imports California's duck curve into balancing authorities that do not have it. Flaming Gorge
is PacifiCorp East, Navajo is PNM, Blue Mesa is WAPA Rocky Mountain -- none of them see SP15's
midday price collapse. The bias runs one way: SP15 overstates midday collapse, so it
understates Upper Basin capture.

CAISO OASIS carries WEIM/EDAM external interties, so real hourly day-ahead LMP is available for
Palo Verde and several Southwest balancing authorities. Pull what resolves, cache it, and record
honestly which reservoirs still fall back to a proxy.

Outputs: outputs/nodal_prices_<YEAR>.json  {node: {"MM-DD-HH": price}}, plus a resolution report.
Public API, ZERO Claude tokens.
"""
import io, json, time, zipfile, urllib.request, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"; CACHE = ROOT / "cache"
OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
YEAR = 2024

# Candidate nodes per region, tried in order. First that resolves wins.
# Prioritised: Palo Verde covers four of the seven reservoirs and is the one that matters
# most; PACE gives the Upper Basin contrast. OASIS throttles hard, so keep the list short.
REGIONS = {
    "PALOVERDE": ["PALOVRDE_ASR-APND"],           # Lower Basin desert SW hub
    "PACE":      ["PACE_ASR-APND"],               # PacifiCorp East (Flaming Gorge)
}


def pull_span(node, s, e):
    u = ("http://oasis.caiso.com/oasisapi/SingleZip?queryname=PRC_LMP&version=12"
         f"&startdatetime={s:%Y%m%d}T07:00-0000&enddatetime={e:%Y%m%d}T07:00-0000"
         f"&market_run_id=DAM&node={node}&resultformat=6")
    for attempt in range(6):
        try:
            raw = urllib.request.urlopen(u, timeout=120).read()
            z = zipfile.ZipFile(io.BytesIO(raw)); nm = z.namelist()[0]
            if nm.endswith(".xml"):
                msg = z.read(nm).decode()[:200]
                time.sleep(45 * (attempt + 1)); continue
            rows = z.read(nm).decode().splitlines()
            ci = {h: i for i, h in enumerate(rows[0].split(","))}
            if "MW" not in ci:
                return None, "no MW column"
            idt, ival, itype = ci["INTERVALSTARTTIME_GMT"], ci["MW"], ci["LMP_TYPE"]
            out = {}
            for r in rows[1:]:
                c = r.split(",")
                if len(c) <= max(ival, itype) or c[itype] != "LMP":
                    continue
                t = dt.datetime.strptime(c[idt][:19], "%Y-%m-%dT%H:%M:%S") - dt.timedelta(hours=7)
                try:
                    out[f"{t.month:02d}-{t.day:02d}-{t.hour:02d}"] = float(c[ival])
                except ValueError:
                    pass
            return out, None
        except Exception as ex:
            time.sleep(60 * (attempt + 1)); continue
    return None, "throttled out"


def main():
    path = OUT / f"nodal_prices_{YEAR}.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    report = {}
    for region, nodes in REGIONS.items():
        if region in data and len(data[region]) > 7000:
            report[region] = f"cached ({len(data[region])} h)"
            print(f"{region:11} cached {len(data[region])} h"); continue
        got = dict(data.get(region, {}))    # resume from whatever already landed
        used = None
        for node in nodes:
            print(f"{region:11} trying {node} (have {len(got)} h) ...", flush=True)
            cur = dt.datetime(YEAR, 1, 1); fails = 0
            while cur < dt.datetime(YEAR + 1, 1, 1):
                nxt = min(cur + dt.timedelta(days=7), dt.datetime(YEAR + 1, 1, 1))
                px, err = pull_span(node, cur, nxt)
                if px is None:
                    fails += 1
                    print(f"  {cur:%m-%d}: {str(err)[:70]}", flush=True)
                    if fails > 12: break
                else:
                    got.update(px)
                    print(f"  {cur:%m-%d}: +{len(px)} -> {len(got)} h", flush=True)
                # persist after EVERY chunk: a partial year is still useful, and the old
                # code only checkpointed in the first week of a month then threw the rest away
                data[region] = got
                path.write_text(json.dumps(data))
                cur = nxt
                time.sleep(40)
            print(f"{region:11} finished {node} with {len(got)} h", flush=True)
            if len(got) > 7000:
                used = node; break
        if used:
            data[region] = got
            report[region] = f"{used}: {len(got)} h"
            print(f"{region:11} OK {used} -> {len(got)} hours", flush=True)
            path.write_text(json.dumps(data))
        else:
            report[region] = "UNRESOLVED"
            print(f"{region:11} UNRESOLVED", flush=True)
    path.write_text(json.dumps(data))
    (OUT / f"nodal_prices_{YEAR}_report.json").write_text(json.dumps(report, indent=1))
    print("\n" + json.dumps(report, indent=1))
    for k, v in data.items():
        vals = list(v.values())
        neg = sum(1 for x in vals if x < 0)
        print(f"{k:11} n={len(vals):5}  mean=${sum(vals)/len(vals):6.2f}  neg_hours={neg}")


if __name__ == "__main__":
    main()
