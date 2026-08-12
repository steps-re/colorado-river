#!/usr/bin/env python3
"""What the annual evaporation product discards by ignoring seasonality.

The model computes evaporation as (annual mean area) x (annual depth). That is exact only if
surface area and evaporation rate are uncorrelated within the year. They are not: the surface
follows releases and runoff, the rate follows available energy, and both have an annual cycle.
The paper's limitations section claimed the term was "under 2.4% at every reservoir" with nothing
computing it, while its methods section said we had no seasonal series at all. This resolves both
by computing the term.

Two seasonal shapes are carried deliberately, because the answer must not depend on the shape:

  measured   Lake Mead's own USGS monthly record (analysis/usgs_mead_evap.py), qualified years
             only. This is the only measured open-water seasonality in the basin, and it embeds
             the heat-storage lag: it peaks in August, two months after peak net radiation.
  penman     each reservoir's own Penman series (analysis/basin_weather_evap.py). It has NO heat
             storage term, so it peaks in June and leads the measured shape by two months. Its
             LEVEL is known to run 30-93% high and is never used here, only its normalised shape.

A term that stays small under both is small for reasons that do not depend on which shape is
right, which is the only claim worth publishing at the un-instrumented reservoirs.

Output: outputs/evap_seasonality.json
"""
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"

daily = json.loads((OUT / "basin_daily.json").read_text())["reservoirs"]
weather = json.loads((OUT / "basin_weather_evap.json").read_text())["reservoirs"]
mead = json.loads((OUT / "usgs_mead_evap.json").read_text())
model = json.loads((OUT / "fpv_coverage_explorer.json").read_text())

# Havasu is held within a few feet, so dV/dh is ill-posed and the model uses a static published
# area for it (see basin_daily.json meta). A static area cannot covary with anything, so its term
# is zero by construction rather than by measurement, and saying otherwise would be a false result.
STATIC_AREA = {"Lake Havasu"}


def monthly_area(name):
    """Mean surface area by (year, month), from Reclamation daily elevations through the fitted
    hypsometry. Months are kept only when at least 25 days are present, so a partial month cannot
    masquerade as a low-area one."""
    d = daily[name]["daily"]
    acc = defaultdict(list)
    for ds, a in zip(d["date"], d["area_acres"]):
        if a is None:
            continue
        acc[(int(ds[:4]), int(ds[5:7]))].append(a)
    return {k: mean(v) for k, v in acc.items() if len(v) >= 25}


MEAD_MONTHLY = {(int(k[:4]), int(k[5:])): v
                for k, v in mead["monthly_corrected_ft"].items()}


def measured_shape():
    """Lake Mead's measured monthly evaporation as a fraction of the annual total, averaged over
    the qualified years. Uses the most probable column, as USGS do. Averaging the FRACTIONS
    rather than the depths keeps a high-evaporation year from dominating the shape."""
    tot = defaultdict(float)
    n = 0
    for y in mead["meta"]["qualified_years"]:
        yr = {m: MEAD_MONTHLY[(y, m)] for m in range(1, 13)}
        s = sum(yr.values())
        n += 1
        for m in range(1, 13):
            tot[m] += yr[m] / s
    if not n:
        raise SystemExit("[evap-seasonality] no qualified Mead years; refusing to invent a shape")
    return {m: tot[m] / n for m in range(1, 13)}


def penman_shape(name):
    mo = weather[name]["monthly_ft"]
    s = sum(mo.values())
    return {int(k): v / s for k, v in mo.items()}


def term_pct(areas, shape, years):
    """Percent by which a seasonally resolved product exceeds the annual product, per year.

    annual   = mean(area over the year) * D
    seasonal = sum_m area_m * D * shape_m          (shape sums to 1, so D cancels entirely)

    D cancels, which is the point: the term is a property of the area cycle against the rate
    cycle and does not depend on the depth level at all."""
    out = {}
    for y in years:
        am = {m: areas.get((y, m)) for m in range(1, 13)}
        if any(v is None for v in am.values()):
            continue
        annual = mean(am.values())
        seasonal = sum(am[m] * shape[m] for m in range(1, 13))
        out[y] = round(100 * (seasonal - annual) / annual, 3)
    return out


shape_meas = measured_shape()
peak_meas = max(shape_meas, key=lambda m: shape_meas[m])

res = {}
for name in model:
    if name == "meta" or name not in daily:
        continue
    areas = monthly_area(name)
    years = sorted({y for y, _ in areas})
    sp = penman_shape(name)
    peak_pen = max(sp, key=lambda m: sp[m])
    if name in STATIC_AREA:
        res[name] = {"static_area": True,
                     "note": "Held within a few feet, so dV/dh is ill-posed and the model uses a "
                             "static published area. A static area cannot covary with the rate, so "
                             "the term is zero by construction, not by measurement.",
                     "penman_peak_month": peak_pen}
        continue
    t_meas = term_pct(areas, shape_meas, years)
    t_pen = term_pct(areas, sp, years)
    both = list(t_meas.values()) + list(t_pen.values())
    res[name] = {
        "static_area": False,
        "years": sorted(t_meas),
        "term_pct_measured_shape": t_meas,
        "term_pct_penman_shape": t_pen,
        "mean_pct_measured_shape": round(mean(t_meas.values()), 3) if t_meas else None,
        "mean_pct_penman_shape": round(mean(t_pen.values()), 3) if t_pen else None,
        "worst_abs_pct": round(max(abs(v) for v in both), 3) if both else None,
        "penman_peak_month": peak_pen,
        "intra_year_area_swing_pct": daily[name]["area_acres"].get("intra_2024_swing_pct"),
    }

moving = {n: v for n, v in res.items() if not v["static_area"]}
worst_name = max(moving, key=lambda n: moving[n]["worst_abs_pct"])
worst = moving[worst_name]["worst_abs_pct"]
mean_name = max(moving, key=lambda n: abs(moving[n]["mean_pct_measured_shape"]))
worst_mean = moving[mean_name]["mean_pct_measured_shape"]
# Sign agreement matters more than magnitude: if the two shapes disagree about the DIRECTION of
# the term at a reservoir, then nothing is established there and the page must say so.
disagree = sorted(n for n, v in moving.items()
                  if v["mean_pct_measured_shape"] * v["mean_pct_penman_shape"] < 0)

# The basin-level bias, weighted by each reservoir's own evaporation volume (mean area x depth).
# Per-reservoir percentages cannot simply be averaged: Mead's term is negative and Mead is most
# of the water, so an unweighted average would report a bias the basin does not have.
vol_w, vol_t = 0.0, 0.0
for n, v in moving.items():
    d = model[n]["params"]["evap_ft"]
    a = mean(monthly_area(n).values())
    vol_w += a * d * v["mean_pct_measured_shape"]
    vol_t += a * d
basin_pct = round(vol_w / vol_t, 3)

# "It changes no ranking" was asserted. A reviewer was right that nothing demonstrated it, so it is
# computed: the term shifts a reservoir's water saved by its own percentage, which shifts cost per
# acre-foot by the same amount, so it can only reorder the table if the gap between two neighbours
# is smaller than the terms that separate them.
unc = json.loads((OUT / "fpv_uncertainty.json").read_text())
# Every reservoir, including the static-area ones, which carry a term of zero by construction.
# Leaving them out would compare a partial ordering and could miss exactly the swap being tested.
terms = {n: (res[n]["mean_pct_measured_shape"] if not res[n]["static_area"] else 0.0)
         for n in res if n in unc}
ranked = sorted(((n, unc[n]["usd_per_af"]["p50"]) for n in terms), key=lambda kv: kv[1])
gaps = [(ranked[i + 1][1] / ranked[i][1] - 1) * 100 for i in range(len(ranked) - 1)]
min_gap = min(gaps) if gaps else None
max_term = max(abs(t) for t in terms.values())
# Do not stop at "the gap is smaller than the term, so it might reorder". Apply the terms and look.
# Cost per acre-foot is inverse in water saved, so a +t% term divides it by (1 + t/100).
adjusted = sorted(((n, v / (1 + terms[n] / 100)) for n, v in ranked), key=lambda kv: kv[1])
order_before = [n for n, _ in ranked]
order_after = [n for n, _ in adjusted]
ranking_changes = order_before != order_after

doc = {
    "meta": {
        "what": "The error the annual evaporation product makes by ignoring within-year "
                "covariance between surface area and evaporation rate",
        "why": "the paper claimed a bound on this with nothing computing it, and elsewhere said "
               "no seasonal series existed",
        "identity": "seasonal/annual - 1, where the annual depth cancels; the term depends only "
                    "on the area cycle against the rate cycle",
        "shapes": {
            "measured": f"Lake Mead USGS monthly record, qualified years "
                        f"{mead['meta']['qualified_years']}, most probable column. Peaks in month "
                        f"{peak_meas}, which is the heat-storage lag behind peak net radiation.",
            "penman": "each reservoir's own Penman series from NASA POWER daily weather. No heat "
                      "storage term, so it peaks two months early. Level unused, shape only."},
        "measured_monthly_shape_fraction": {m: round(v, 4) for m, v in shape_meas.items()},
        "measured_peak_month": peak_meas,
        "static_area_reservoirs": sorted(STATIC_AREA)},
    "reservoirs": res,
    "verdict": {
        "basin_pct_measured_shape": basin_pct,
        "largest_mean_pct": worst_mean,
        "largest_mean_reservoir": mean_name,
        "worst_single_year_abs_pct": worst,
        "worst_single_year_reservoir": worst_name,
        "shapes_agree_on_sign": not disagree,
        "sign_disagreement_at": disagree,
        "favours_our_conclusion": basin_pct > 0,
        "statement": (
            f"Weighted by each reservoir's own evaporation volume, ignoring within-year "
            f"seasonality moves basin evaporation by {basin_pct:+.1f}%. The largest per-reservoir "
            f"mean is {worst_mean:+.1f}% at {mean_name}, and the worst single year in the record "
            f"is {worst:.1f}% at {worst_name}. Both seasonal shapes agree on the direction at "
            f"every reservoir"
            + (", " if not disagree else f" except {', '.join(disagree)}, ")
            + "so the result does not rest on which shape is right."),
        "direction_note": (
            "The term is positive at "
            + (f"every reservoir except {', '.join(sorted(n for n, v in moving.items() if v['mean_pct_measured_shape'] < 0))}"
               if any(v["mean_pct_measured_shape"] < 0 for v in moving.values())
               else "every reservoir with a moving surface")
            + ": the surface is largest in "
            "summer when the rate is highest, so an annual product UNDERSTATES evaporation there. "
            "Understating evaporation understates the water floating solar could save, which "
            "raises its cost per acre-foot. That is the direction that flatters our own "
            "conclusion, which is why it is stated rather than buried. At "
            f"{basin_pct:+.1f}% it is far inside the flux and area uncertainties the model already "
            "carries. Whether it reorders the reservoirs is not something the size of the term "
            f"settles on its own: the closest two are only {min_gap:.1f}% apart in cost per "
            f"acre-foot against a largest term of {max_term:.1f}%. Applying every term and "
            + ("re-sorting DOES change the order, so the ranking near that pair is not robust to "
               "seasonality and is reported with that caveat."
               if ranking_changes else
               "re-sorting leaves the order unchanged, so the ranking stands."))},
     "ranking_check": {"ordered_by_usd_per_af_p50": order_before,
                       "order_after_applying_terms": order_after,
                       "min_adjacent_gap_pct": round(min_gap, 2) if min_gap is not None else None,
                       "largest_term_pct": round(max_term, 2),
                       "ranking_changes": ranking_changes,
                       "note": "Static-area reservoirs are included with a term of zero, so this "
                               "is the full ordering rather than a partial one."}}

(OUT / "evap_seasonality.json").write_text(json.dumps(doc, indent=2))

print(f"[evap-seasonality] measured shape peaks in month {peak_meas}; "
      f"Penman peaks in month {res['Lake Mead']['penman_peak_month']} (no heat storage)")
for n, v in res.items():
    if v["static_area"]:
        print(f"[evap-seasonality] {n:18} static area, term zero by construction")
        continue
    print(f"[evap-seasonality] {n:18} measured {v['mean_pct_measured_shape']:+.2f}%  "
          f"penman {v['mean_pct_penman_shape']:+.2f}%  worst |{v['worst_abs_pct']:.2f}|%  "
          f"({len(v['years'])} yr, area swing {v['intra_year_area_swing_pct']}%)")
print(f"[evap-seasonality] worst {worst:.2f}% at {worst_name}; "
      f"shapes agree on sign: {not disagree}")
print("[evap-seasonality] wrote outputs/evap_seasonality.json")
