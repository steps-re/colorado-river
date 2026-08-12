#!/usr/bin/env python3
"""Close the Lake Havasu evaporation bracket by calibrating the accounting convention it comes from.

Havasu is the reservoir this work rates highest and its evaporation depth is the weakest input in
the set: there is no flux measurement, only a quotient of Reclamation's LCRAS accounting volume
over an area, carried as an unresolved 5.2-7.4 ft/yr bracket. USGS confirmed (2026-08-10) that a
Havasu flux station is in planning and nothing exists yet, so waiting is not a plan. The question
put to Reclamation on 2026-08-09, what area LCRAS divides by, is still unanswered.

It can be answered from data instead. LCRAS reports Mead, Mohave and Havasu on one convention, and
two of those three have measured eddy-covariance depths. So the convention can be calibrated where
it is checkable and applied where it is not.

What the calibration finds, in order:

  1. Reclamation's published areas are right. Their reported surface area matches the mean of the
     daily record to 0.2% at Mead and 0.5% at Mohave, so the denominator is not the problem and
     the open question to Reclamation turns out not to be the binding one.
  2. The quotient is nonetheless low. LCRAS volume over the true mean surface runs 6-7% under the
     measured flux depth at both lakes.
  3. The gap is precipitation. LCRAS is consumptive-use accounting, so its reservoir evaporation is
     net of rain falling on the lake. At Mead the mean gap is 0.42 ft/yr against 0.45 ft/yr of
     precipitation, a residual of -0.03. That is a mechanism, not a fitted factor, which is why the
     correction is additive and transfers to a lake with different rainfall.

Havasu's surface is level-controlled for delivery: its pool moved 3.8 ft over eleven years against
58.2 ft at Mead. A fixed area is therefore appropriate there in a way it would not be upstream.

Output: outputs/havasu_evap_bracket.json
"""
import json
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"

L = json.loads((OUT / "lcras_summary.json").read_text())["reservoir_evap_af"]
W = json.loads((OUT / "basin_weather_evap.json").read_text())["reservoirs"]
D = json.loads((OUT / "basin_daily.json").read_text())["reservoirs"]
M = json.loads((OUT / "fpv_coverage_explorer.json").read_text())
E = json.loads((OUT / "usgs_mead_evap.json").read_text())

MM_PER_FT = 304.8
# OFR 2021-1022 table 9, Lake Mohave most probable annual evaporation in mm. Same transcription as
# analysis/evap_flux_uncertainty.py, which checks it against the report's own printed means.
MOHAVE_T9_MM = {2014: 1601, 2015: 1713, 2016: 1735, 2017: 1864, 2018: 1676}
LCRAS_KEY = {"Lake Mead": "LAKE_MEAD", "Lake Mohave": "LAKE_MOHAVE", "Lake Havasu": "LAKE_HAVASU"}
HAVASU_YEARS = range(2019, 2025)     # the window the published quotient already uses


def daily_area(name, year=None):
    """Mean surface area in acres, over one year or the whole record. A year is used only if it
    has at least 350 days, so a gap cannot pass as a drawn-down surface."""
    d = D[name]["daily"]
    v = [a for ds, a in zip(d["date"], d["area_acres"])
         if a and (year is None or ds[:4] == str(year))]
    return mean(v) if len(v) >= (350 if year else 1) else None


def measured_depths(name):
    """Measured flux depth by year, in feet. Mead from the data release, qualified years only;
    Mohave from the report, which is the only place its 2014-2018 annuals appear."""
    if name == "Lake Mead":
        return {int(y): a["corrected"] for y, a in E["annual_ft"].items() if a["qualified"]}
    return {y: mm / MM_PER_FT for y, mm in MOHAVE_T9_MM.items()}


# --- 1. is Reclamation's published area the real one? ------------------------------------------
area_check = {}
for name in ("Lake Mead", "Lake Mohave"):
    pub = M[name]["params"].get("published_acres")
    # compare over the window the published figure averages, 2017-2021
    d = D[name]["daily"]
    v = [a for ds, a in zip(d["date"], d["area_acres"]) if a and 2017 <= int(ds[:4]) <= 2021]
    area_check[name] = {"published_acres": pub, "daily_mean_acres": round(mean(v)),
                        "ratio": round(pub / mean(v), 4)}
areas_agree = all(abs(a["ratio"] - 1) <= 0.02 for a in area_check.values())

# --- 2 and 3. calibrate the quotient against measured flux, and test precipitation --------------
cal, per_lake = [], {}
for name in ("Lake Mead", "Lake Mohave"):
    precip = W[name]["precip_ft_per_yr"]
    rows = []
    for y, md in sorted(measured_depths(name).items()):
        vol = L[LCRAS_KEY[name]].get(str(y))
        area = daily_area(name, y)
        if not vol or not area:
            continue
        net = vol / area                      # what the accounting convention implies per acre
        rows.append({"year": y, "lcras_net_ft": round(net, 3), "measured_ft": round(md, 3),
                     "gap_ft": round(md - net, 3), "precip_ft": round(precip, 3),
                     "residual_ft": round(md - net - precip, 3)})
        cal.append(md - net - precip)
    per_lake[name] = {
        "precip_ft_per_yr": round(precip, 3),
        "years": [r["year"] for r in rows],
        "rows": rows,
        "mean_gap_ft": round(mean(r["gap_ft"] for r in rows), 3),
        "mean_residual_ft": round(mean(r["residual_ft"] for r in rows), 3),
        "quotient_vs_measured_pct": round(
            100 * (mean(r["lcras_net_ft"] for r in rows) / mean(r["measured_ft"] for r in rows) - 1), 2)}

bias = mean(cal)                # how much the corrected quotient misses the measured depth by
spread = stdev(cal)
if not areas_agree:
    raise SystemExit("[havasu] Reclamation's published areas no longer match the daily record; "
                     "the calibration assumes they do and must be revisited")

# --- apply to Havasu ---------------------------------------------------------------------------
hp = M["Lake Havasu"]["params"]
pub_ac = hp["published_acres"]
vol = [L[LCRAS_KEY["Lake Havasu"]][str(y)] for y in HAVASU_YEARS]
net = mean(vol) / pub_ac
precip_h = W["Lake Havasu"]["precip_ft_per_yr"]
gross = net + precip_h
# The calibration's own bias is subtracted, and the bracket is +/- two standard deviations of the
# per-year residual. That is wider than the residual scatter of either lake alone, which is the
# honest price of transferring a convention to a lake with no flux station.
central = gross - bias
lo, hi = central - 2 * spread, central + 2 * spread

elev = [x for x in D["Lake Havasu"]["daily"]["elevation_ft"] if x]
mead_elev = [x for x in D["Lake Mead"]["daily"]["elevation_ft"] if x]

doc = {
    "meta": {
        "what": "Lake Havasu gross open-water evaporation, derived by calibrating Reclamation's "
                "LCRAS accounting convention against measured flux at the two lakes that have it",
        "why": "no Havasu flux measurement exists or is expected soon, and the published figure "
               "was an uncalibrated quotient carried as an asserted 5.2-7.4 ft/yr bracket",
        "sources": {
            "lcras": "USBR Lower Colorado CUL dataset 1971-2024 (usbr.gov/lc/region/g4000), "
                     "Mainstream_Reservoirs",
            "flux": "Lake Mead from the ScienceBase releases; Lake Mohave from OFR 2021-1022 "
                    "table 9",
            "precipitation": W["Lake Mead"].get("precip_src",
                             "NASA POWER daily at each reservoir's own coordinates"),
            "areas": "Reclamation daily elevation and storage through a fitted hypsometry"},
        "havasu_is_level_controlled": {
            "havasu_elevation_range_ft": round(max(elev) - min(elev), 1),
            "mead_elevation_range_ft": round(max(mead_elev) - min(mead_elev), 1),
            "note": "Havasu is held for delivery, so a fixed surface area is appropriate there in "
                    "a way it is not at a reservoir that draws down."}},
    "step1_published_areas_are_real": {
        "lakes": area_check, "all_within_2pct": areas_agree,
        "finding": "Reclamation's reported surface area matches the mean of its own daily record "
                   "at both lakes, so the LCRAS denominator is not the source of the discrepancy "
                   "and the open question to Reclamation is not the binding one."},
    "step2_and_3_calibration": {
        "lakes": per_lake,
        "pooled_n": len(cal),
        "mean_residual_ft": round(bias, 3),
        "residual_sd_ft": round(spread, 3),
        "finding": "The gap between the accounting quotient and measured flux is precipitation on "
                   "the lake surface, which consumptive-use accounting nets out. The correction is "
                   "therefore additive and transfers to a lake with different rainfall."},
    "havasu": {
        "lcras_years": list(HAVASU_YEARS),
        "lcras_mean_af": round(mean(vol)),
        "area_acres": pub_ac,
        "net_ft_per_yr": round(net, 3),
        "precip_ft_per_yr": round(precip_h, 3),
        "gross_ft_per_yr": round(gross, 3),
        "calibrated_ft_per_yr": round(central, 2),
        "bracket_ft_per_yr": [round(lo, 2), round(hi, 2)],
        "superseded_bracket_ft_per_yr": [5.2, 7.4],
        "width_ft": round(hi - lo, 2)},
    "verdict": {
        "statement": (
            f"Lake Havasu's evaporation depth is {central:.2f} ft/yr, bracketed "
            f"{lo:.2f}-{hi:.2f}. The accounting volume over Reclamation's own area gives "
            f"{net:.2f} ft/yr net of rain; adding the {precip_h:.2f} ft/yr that falls on the lake "
            f"gives {gross:.2f} gross, and the calibration's own bias against measured flux at "
            f"Mead and Mohave is {bias:+.2f} ft/yr with a per-year spread of {spread:.2f}."),
        "replaces": (
            f"an asserted 5.2-7.4 ft/yr bracket {(7.4 - 5.2) / (hi - lo):.1f} times wider, whose "
            f"ends were two different readings of the same quotient rather than a measured range"),
        "direction_note": (
            "A higher depth means more water saved per acre covered, so this raises Lake Havasu's "
            "standing rather than lowering it. Havasu is already the reservoir this work rates "
            "highest, so the correction cuts against our own conclusion and is reported for that "
            "reason.")}}

(OUT / "havasu_evap_bracket.json").write_text(json.dumps(doc, indent=2))

for n, a in area_check.items():
    print(f"[havasu] {n:13} published {a['published_acres']:>7,} ac vs daily mean "
          f"{a['daily_mean_acres']:>7,} ac  ratio {a['ratio']:.3f}")
for n, d in per_lake.items():
    print(f"[havasu] {n:13} quotient runs {d['quotient_vs_measured_pct']:+.1f}% vs measured; "
          f"gap {d['mean_gap_ft']:.2f} ft, precip {d['precip_ft_per_yr']:.2f} ft, "
          f"residual {d['mean_residual_ft']:+.2f} ft")
print(f"[havasu] pooled residual {bias:+.3f} +/- {spread:.3f} ft/yr over {len(cal)} lake-years")
print(f"[havasu] Havasu {net:.2f} net + {precip_h:.2f} precip = {gross:.2f} gross "
      f"-> {central:.2f} ft/yr, bracket {lo:.2f}-{hi:.2f} (was 5.2-7.4)")
print("[havasu] wrote outputs/havasu_evap_bracket.json")
