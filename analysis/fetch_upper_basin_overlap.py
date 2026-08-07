#!/usr/bin/env python3
"""Build defensible full-year price series for the two Upper Basin reservoirs whose own
markets only recently started producing day-ahead prices.

The problem: Flaming Gorge sits in PacifiCorp East, which only entered a day-ahead market when
CAISO's EDAM went live in mid-2026, and Blue Mesa sits in the SPP West footprint, whose
predecessor market (Western Energy Imbalance Service) was real-time imbalance only and had no
day-ahead product at all until SPP RTO West started in April 2026. Neither has a full year.

Using a Desert Southwest node for them instead is what the referees objected to, and they were
right: the measured midday gap is large.

The fix, which is standard practice and is labelled as such: pull a reference node over the SAME
window the local data covers, compute the hour-of-day price ratio between them, and apply that
ratio to the reference node's full year. The result is a shape-transferred series, not a
measurement, and the model records it that way.

Outputs: outputs/nodal_prices_upper.json
"""
import io, json, csv, time, zipfile, urllib.request, datetime as dt
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
YEAR_REF = 2024                      # the full year the model runs on
WIN = (dt.datetime(2026, 6, 1), dt.datetime(2026, 8, 1))   # window where local data exists
UA = {"User-Agent": "steps-colorado-river/1.0 (research contact mike@stepsventures.com)"}


def oasis_span(node, s, e, tries=5):
    u = ("http://oasis.caiso.com/oasisapi/SingleZip?queryname=PRC_LMP&version=12"
         f"&startdatetime={s:%Y%m%d}T07:00-0000&enddatetime={e:%Y%m%d}T07:00-0000"
         f"&market_run_id=DAM&node={node}&resultformat=6")
    for a in range(tries):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=180).read()
            z = zipfile.ZipFile(io.BytesIO(raw)); nm = z.namelist()[0]
            if nm.endswith(".xml"):
                time.sleep(45 * (a + 1)); continue
            rows = z.read(nm).decode().splitlines()
            ci = {h: i for i, h in enumerate(rows[0].split(","))}
            out = {}
            for r in rows[1:]:
                c = r.split(",")
                if len(c) <= max(ci["MW"], ci["LMP_TYPE"]) or c[ci["LMP_TYPE"]] != "LMP":
                    continue
                t = dt.datetime.strptime(c[ci["INTERVALSTARTTIME_GMT"]][:19],
                                         "%Y-%m-%dT%H:%M:%S") - dt.timedelta(hours=7)
                try:
                    out[f"{t.month:02d}-{t.day:02d}-{t.hour:02d}"] = float(c[ci["MW"]])
                except ValueError:
                    pass
            return out
        except Exception:
            time.sleep(60 * (a + 1))
    return {}


def spp_day(date, locations):
    """SPP RTO West day-ahead LMP. Returns {hour: mean price} for the SWPW footprint."""
    u = ("https://portal.spp.org/file-browser-api/download/da-lmp-by-settlement-location"
         f"?path=/{date:%Y}/{date:%m}/By_Day/DA-LMP-SL-{date:%Y%m%d}0100.csv")
    try:
        raw = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=180).read()
    except Exception:
        return {}
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8", "replace"))))
    if not rows:
        return {}
    # SPP alternates between two header conventions across days: "Settlement Location"
    # (title case, spaces) and "SETTLEMENT_LOCATION" (upper, underscores). Normalise both.
    def norm(h):
        return h.strip().upper().replace(" ", "").replace("_", "")
    hdr = [norm(h) for h in rows[0]]
    try:
        iI, iB, iS, iL = (hdr.index("INTERVAL"), hdr.index("BAA"),
                          hdr.index("SETTLEMENTLOCATION"), hdr.index("LMP"))
    except ValueError:
        return {}
    acc = {}
    for r in rows[1:]:
        if len(r) <= iL or r[iB].strip() != "SWPW":
            continue
        if locations and r[iS].strip() not in locations:
            continue
        try:
            h = dt.datetime.strptime(r[iI].strip(), "%m/%d/%Y %H:%M:%S").hour
            acc.setdefault(h, []).append(float(r[iL]))
        except (ValueError, IndexError):
            continue
    return {h: float(np.mean(v)) for h, v in acc.items()}


def hour_profile(series):
    """Mean price by hour of day from a {'MM-DD-HH': price} dict."""
    acc = {}
    for k, v in series.items():
        acc.setdefault(int(k[-2:]), []).append(v)
    return {h: float(np.mean(v)) for h, v in acc.items()}


def transfer(ref_full_year, ratio_by_hour):
    """Apply an hour-of-day ratio to a full-year reference series."""
    return {k: v * ratio_by_hour.get(int(k[-2:]), 1.0) for k, v in ref_full_year.items()}


def main():
    base = json.loads((OUT / "nodal_prices_2024.json").read_text())
    pace_local = base.get("PACE_2026", {})
    out = {}

    # ---- reference node over the SAME window, so the ratio is like-for-like ----
    print("pulling Palo Verde over the 2026-06..07 window as the reference ...", flush=True)
    cache = OUT / "_ref_win_2026.json"
    ref_win = json.loads(cache.read_text()) if cache.exists() else {}
    cur = WIN[0]
    while cur < WIN[1]:
        nxt = min(cur + dt.timedelta(days=7), WIN[1])
        got = oasis_span("PALOVRDE_ASR-APND", cur, nxt) if len(ref_win) < 1400 else {}
        if len(ref_win) < 1400:
            ref_win.update(got)
            print(f"  {cur:%m-%d}: +{len(got)} -> {len(ref_win)}", flush=True)
            cache.write_text(json.dumps(ref_win))
            time.sleep(40)
        cur = nxt

    if len(ref_win) > 500 and len(pace_local) > 500:
        pp, rp = hour_profile(pace_local), hour_profile(ref_win)
        ratio = {h: (pp[h] / rp[h] if rp.get(h) and abs(rp[h]) > 1e-6 else 1.0)
                 for h in range(24) if h in pp and h in rp}
        out["PACE_transferred"] = dict(
            ratio_by_hour={str(h): round(r, 4) for h, r in sorted(ratio.items())},
            reference="PALOVRDE_ASR-APND (has both the 2026 overlap window and a full 2024 year)",
            overlap_hours=min(len(pace_local), len(ref_win)),
            series=transfer(base["PALOVERDE"], ratio),
            method="Hour-of-day ratio of measured PacifiCorp East day-ahead prices to the "
                   "reference node over 2026-06-01..07-31, applied to the reference node's full "
                   "2024 year. Shape-transferred, NOT measured.",
        )
        print(f"PACE ratio by hour: {ratio.get(12, float('nan')):.2f} at noon, "
              f"{ratio.get(19, float('nan')):.2f} at 19h")

    # ---- SPP West for Blue Mesa, same treatment ----
    print("\npulling SPP RTO West day-ahead over the same window ...", flush=True)
    CRSP = {"CRSP.PRPA.FSE", "CRSP.TSGT.FSE"}
    spp_hours, spp_all = {}, {}
    d = WIN[0]
    n = 0
    while d < WIN[1]:
        try:
            prof = spp_day(d, CRSP)
        except Exception:
            prof = {}
        if not prof:                       # fall back to the whole SWPW footprint
            try:
                prof = spp_day(d, None)
            except Exception:
                prof = {}
            if prof:
                spp_all[d] = prof
        else:
            spp_hours[d] = prof
        n += 1
        if n % 10 == 0:
            print(f"  {d:%m-%d}: crsp-days={len(spp_hours)} swpw-days={len(spp_all)}", flush=True)
        d += dt.timedelta(days=3)          # every third day is plenty for an hour-of-day mean
        time.sleep(2)

    use = spp_hours if len(spp_hours) >= 8 else spp_all
    label = "CRSP settlement points" if use is spp_hours else "SWPW footprint mean"
    if use and len(ref_win) > 500:
        acc = {}
        for prof in use.values():
            for h, v in prof.items():
                acc.setdefault(h, []).append(v)
        sp = {h: float(np.mean(v)) for h, v in acc.items()}
        rp = hour_profile(ref_win)
        ratio = {h: (sp[h] / rp[h] if rp.get(h) and abs(rp[h]) > 1e-6 else 1.0)
                 for h in range(24) if h in sp and h in rp}
        out["SWPW_transferred"] = dict(
            ratio_by_hour={str(h): round(r, 4) for h, r in sorted(ratio.items())},
            reference="PALOVRDE_ASR-APND (has both the 2026 overlap window and a full 2024 year)",
            source=label, days_sampled=len(use),
            series=transfer(base["PALOVERDE"], ratio),
            method="Hour-of-day ratio of measured SPP RTO West day-ahead prices to the reference "
                   "node over 2026-06..07, applied to the reference node's full 2024 year. "
                   "Shape-transferred, NOT measured. SPP RTO West only began publishing "
                   "day-ahead prices for this footprint in April 2026.",
        )
        print(f"SWPW ({label}, {len(use)} days) ratio: "
              f"{ratio.get(12, float('nan')):.2f} at noon, {ratio.get(19, float('nan')):.2f} at 19h")

    out["_reference_window"] = dict(node="PALOVRDE_ASR-APND", hours=len(ref_win),
                                    window="2026-06-01..2026-07-31")
    (OUT / "nodal_prices_upper.json").write_text(json.dumps(out))
    print(f"\nWROTE outputs/nodal_prices_upper.json  keys={[k for k in out]}")


if __name__ == "__main__":
    main()
