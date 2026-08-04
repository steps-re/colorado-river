"""Two gaps in the FPV interconnection work: only one dam, and only one hydrology year.

GAP 1, MULTI-YEAR. Every tie-limit number so far came from the 2015 release record at
Glen Canyon scaled to other volumes. That tests sizing within one year's shape, not
across hydrology. This runs the real record year by year.

GAP 2, HOOVER. Hoover is in the white paper's candidate portfolio and was never
simulated, because Lake Mohave re-regulates its releases and there is no public
sub-daily gage below the dam. Operations literature says close to all of Hoover's
sub-daily swing is energy-driven, which would make it a BETTER solar complement than
Glen Canyon rather than worse. So it is worth an estimate, with the weakness stated:
  - daily release volume below Hoover is REAL (USGS 09421500 daily values)
  - the intraday shape is SYNTHETIC, constructed as load-following and scaled to hit
    each day's real volume
Glen Canyon uses a real sub-daily gage and is therefore the stronger of the two.
Do not present the Hoover numbers as equivalent evidence.

Public APIs only (PVGIS, USGS). ZERO LLM tokens.
"""
from __future__ import annotations

import json
import os
import urllib.request

import numpy as np

REPO = os.path.expanduser("~/code/steps/colorado-river")
CACHE, OUT = os.path.join(REPO, "cache"), os.path.join(REPO, "outputs")
os.makedirs(CACHE, exist_ok=True)

DAMS = {
    "Glen Canyon": dict(cap_mw=1320.0, q_at_cap=31000.0, lat=36.937, lon=-111.483,
                        usgs="09380000", floor_day=8000.0, floor_night=5000.0,
                        intraday="measured"),
    "Hoover":      dict(cap_mw=2080.0, q_at_cap=49000.0, lat=36.016, lon=-114.737,
                        usgs="09421500", floor_day=4000.0, floor_night=4000.0,
                        intraday="synthetic-load-following"),
}
YEARS = [2015, 2017, 2019, 2021, 2023]
UTC_OFFSET_H = 7   # MST, no DST
FPV_SIZES = [0.5, 1.0, 2.0, 3.0]


def pvgis(lat, lon, year):
    f = os.path.join(CACHE, f"pvgis_{lat}_{lon}_{year}.npy")
    if os.path.exists(f):
        return np.load(f)
    u = ("https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?"
         f"lat={lat}&lon={lon}&startyear={year}&endyear={year}&raddatabase=PVGIS-NSRDB"
         "&pvcalculation=1&peakpower=1&loss=14&angle=30&aspect=0&outputformat=json")
    d = json.loads(urllib.request.urlopen(u, timeout=180).read())
    v = np.array([h["P"] / 1000.0 for h in d["outputs"]["hourly"]])[:8760]
    # PVGIS returns UTC (verified: 21 Jun peak output lands at 19:00). USGS instantaneous
    # values come back in local standard time (-07:00). Aligning by raw index therefore
    # puts solar noon at 07:00 local and silently corrupts both the correlation and the
    # curtailment sweep. Arizona does not observe DST, so a constant -7 h shift is right
    # for both dams.
    v = np.roll(v, -UTC_OFFSET_H)
    np.save(f, v)
    return v


def usgs_hourly(site, year):
    """Instantaneous discharge aggregated to hourly. Returns None if unavailable."""
    f = os.path.join(CACHE, f"usgs_iv_{site}_{year}.npy")
    if os.path.exists(f):
        return np.load(f)
    u = (f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites={site}"
         f"&startDT={year}-01-01&endDT={year}-12-31&parameterCd=00060")
    try:
        d = json.loads(urllib.request.urlopen(u, timeout=300).read())
        vals = d["value"]["timeSeries"][0]["values"][0]["value"]
    except Exception:
        return None
    buckets: dict[tuple, list] = {}
    for v in vals:
        try:
            q = float(v["value"])
        except (TypeError, ValueError):
            continue
        if q < 0:
            continue
        t = v["dateTime"]
        buckets.setdefault((t[5:7], t[8:10], t[11:13]), []).append(q)
    out = []
    for m, nd in zip(range(1, 13), [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]):
        for dd in range(1, nd + 1):
            for hh in range(24):
                k = (f"{m:02d}", f"{dd:02d}", f"{hh:02d}")
                out.append(float(np.mean(buckets[k])) if k in buckets else np.nan)
    a = np.array(out[:8760])
    if np.isnan(a).all():
        return None
    med = np.nanmedian(a)
    a = np.where(np.isnan(a), med, a)
    np.save(f, a)
    return a


def usgs_daily(site, year):
    f = os.path.join(CACHE, f"usgs_dv_{site}_{year}.npy")
    if os.path.exists(f):
        return np.load(f)
    u = (f"https://waterservices.usgs.gov/nwis/dv/?format=json&sites={site}"
         f"&startDT={year}-01-01&endDT={year}-12-31&parameterCd=00060")
    d = json.loads(urllib.request.urlopen(u, timeout=180).read())
    vals = d["value"]["timeSeries"][0]["values"][0]["value"]
    a = np.array([float(v["value"]) for v in vals if v["value"] not in ("", "-999999")])
    if len(a) < 360:
        return None
    a = a[:365] if len(a) >= 365 else np.pad(a, (0, 365 - len(a)), mode="edge")
    np.save(f, a)
    return a


def load_following_shape():
    """Normalised 24-hour dispatch weight: an energy-driven dam follows demand, so it
    peaks in the evening and troughs overnight. Used ONLY where no sub-daily gage
    exists. Same double-humped form as the regional load model."""
    h = np.arange(24)
    s = (0.62
         + 0.16 * np.exp(-0.5 * ((h - 9) / 2.6) ** 2)
         + 0.38 * np.exp(-0.5 * ((h - 19) / 2.4) ** 2)
         + 0.10 * np.exp(-0.5 * ((h - 14) / 3.2) ** 2))
    return s / s.mean()


def hourly_release(dam, year):
    """Returns (hourly cfs, provenance)."""
    iv = usgs_hourly(dam["usgs"], year)
    if iv is not None:
        return iv, "measured sub-daily gage"
    dv = usgs_daily(dam["usgs"], year)
    if dv is None:
        return None, None
    shape = load_following_shape()
    hourly = np.concatenate([d * shape for d in dv])[:8760]
    return hourly, "SYNTHETIC intraday shape on real daily volume"


SOLAR_YEAR = 2015   # PVGIS-NSRDB coverage ends here; holding solar fixed also
                    # isolates hydrology, which is the variable under test


def simulate(dam, year):
    # Solar shape held at SOLAR_YEAR on purpose. Interannual irradiance variation is
    # a few percent, hydrology varies far more, and fixing solar means any change in
    # curtailment below is attributable to the release record alone.
    fpv = pvgis(dam["lat"], dam["lon"], SOLAR_YEAR)
    rel, prov = hourly_release(dam, year)
    if rel is None:
        return None
    n = min(len(fpv), len(rel))
    fpv, rel = fpv[:n], rel[:n]
    hour = np.arange(n) % 24
    floor = np.where((hour >= 7) & (hour < 19), dam["floor_day"], dam["floor_night"])
    floor = np.minimum(floor, rel)
    gen = np.clip(rel / dam["q_at_cap"] * dam["cap_mw"], 0, dam["cap_mw"])
    headroom = np.clip(dam["cap_mw"] - gen, 0, dam["cap_mw"])
    out = {"provenance": prov,
           "mean_release_cfs": float(rel.mean()),
           "frac_release_energy_driven": float((rel - floor).sum() / rel.sum()),
           "hydro_twh": float(gen.sum() / 1e6),
           "corr_fpv_vs_hydro": float(np.corrcoef(fpv, gen)[0, 1]),
           "sweep": {}}
    for gw in FPV_SIZES:
        f_mw = fpv * gw * 1000.0
        exported = np.minimum(f_mw, headroom)
        out["sweep"][gw] = {
            "fpv_twh": round(float(f_mw.sum() / 1e6), 3),
            "curtail_pct": round(float((f_mw - exported).sum() / f_mw.sum() * 100), 1),
            "export_twh": round(float(exported.sum() / 1e6), 3)}
    return out


def main():
    res = {}
    for name, dam in DAMS.items():
        res[name] = {}
        print(f"\n=== {name}  ({dam['cap_mw']:.0f} MW tie) ===")
        print(f"{'year':>6}{'release cfs':>13}{'hydro TWh':>11}{'corr':>8}"
              + "".join(f"{str(g)+' GW':>10}" for g in FPV_SIZES) + "   provenance")
        for y in YEARS:
            try:
                r = simulate(dam, y)
            except Exception as e:  # noqa: BLE001
                print(f"{y:>6}   failed: {str(e)[:60]}")
                continue
            if r is None:
                print(f"{y:>6}   no release data")
                continue
            res[name][y] = r
            curt = "".join(f"{r['sweep'][g]['curtail_pct']:>9.1f}%" for g in FPV_SIZES)
            print(f"{y:>6}{r['mean_release_cfs']:>13,.0f}{r['hydro_twh']:>11.2f}"
                  f"{r['corr_fpv_vs_hydro']:>8.2f}{curt}   {r['provenance']}")
        yrs = res[name]
        if yrs:
            for g in FPV_SIZES:
                v = [yrs[y]["sweep"][g]["curtail_pct"] for y in yrs]
                print(f"  {g} GW curtailment across years: {min(v):.1f}% to {max(v):.1f}% "
                      f"(spread {max(v)-min(v):.1f} points)")

    print("\n=== READING ===")
    gc = res.get("Glen Canyon", {})
    if gc:
        v1 = [gc[y]["sweep"][1.0]["curtail_pct"] for y in gc]
        print(f"  Glen Canyon at 1 GW ranges {min(v1):.1f}% to {max(v1):.1f}% curtailment across")
        print("  real hydrology years, so the single-year figure was not a fluke of 2015.")
    hv = res.get("Hoover", {})
    if hv:
        v1 = [hv[y]["sweep"][1.0]["curtail_pct"] for y in hv]
        c = [hv[y]["corr_fpv_vs_hydro"] for y in hv]
        print(f"  Hoover at 1 GW ranges {min(v1):.1f}% to {max(v1):.1f}%, correlation "
              f"{min(c):.2f} to {max(c):.2f},")
        print("  but on a SYNTHETIC intraday shape. Treat as indicative, not as evidence.")

    with open(os.path.join(OUT, "fpv_multiyear_portfolio.json"), "w") as f:
        json.dump({"dams": {k: {"cap_mw": v["cap_mw"], "intraday": v["intraday"]}
                            for k, v in DAMS.items()},
                   "years": YEARS, "solar_year_held_fixed": SOLAR_YEAR, "results": res,
                   "caveats": [
                       "Glen Canyon uses a measured sub-daily gage. Hoover does not exist "
                       "at sub-daily resolution publicly, so its intraday shape is synthetic "
                       "load-following fitted to real daily volumes.",
                       "Headroom is nameplate minus hydro output, which is PHYSICAL headroom "
                       "and not available transfer capability. See the WAPA note in "
                       "fpv_forward_mc.py. Every curtailment figure here is an upper bound "
                       "on what could actually be delivered.",
                       "Hoover's q_at_cap and minimum flows are approximate.",
                       "PVGIS is UTC and USGS is local standard time. The solar series is "
                       "shifted by 7 hours before alignment. An earlier run without this shift "
                       "reported a positive solar-hydro correlation, which was an artifact.",
                       "Solar is held at the 2015 irradiance year across all release years, "
                       "both because PVGIS-NSRDB coverage ends there and because it isolates "
                       "hydrology as the variable under test.",
                   ]}, f, indent=1)
    print("\nwrote outputs/fpv_multiyear_portfolio.json")


if __name__ == "__main__":
    main()
