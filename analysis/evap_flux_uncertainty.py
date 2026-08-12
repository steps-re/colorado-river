#!/usr/bin/env python3
"""How uncertain each measured evaporation depth actually is, per lake.

The model carried one flux uncertainty for both instrumented lakes: 5% at Lake Mead and 5% at
Lake Mohave. That is right at Mead and roughly half the truth at Mohave, and USGS say so plainly.
Energy balance closes almost perfectly at Mead (period EBR 0.98) and badly at Mohave (0.82),
because a larger share of Mohave's measured turbulent flux comes off the surrounding desert. The
gap between probable minimum and probable maximum evaporation is the direct consequence, and
OFR 2021-1022 puts it at "1-5 percent" of annual evaporation at Mead and "1-22 percent" at Mohave.

Mead is computed from the data release, which publishes all three columns per month. No data
release covers Mohave's 2014-2018 period, so its triples are transcribed from the report's own
table 9 and the transcription is checked by reproducing the period means the report prints
beneath it. A mistyped digit moves those means and fails the check.

Output: outputs/evap_flux_uncertainty.json
"""
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
MM_PER_FT = 304.8

mead = json.loads((OUT / "usgs_mead_evap.json").read_text())

OFR = ("Earp, K.J., and Moreo, M.T., 2021, Evaporation from Lake Mead and Lake Mohave, Nevada and "
       "Arizona, 2010-2019: USGS Open-File Report 2021-1022, https://doi.org/10.3133/ofr20211022")

# OFR 2021-1022 table 9, Lake Mohave annual evaporation in mm: probable minimum, most probable,
# probable maximum. Transcribed because no ScienceBase release covers these years; the release
# that mentions Mohave (doi:10.5066/F79C6VG3) stops in April 2015 and holds one complete year.
MOHAVE_TABLE9 = {2014: (1511, 1601, 1691), 2015: (1414, 1713, 2012), 2016: (1352, 1735, 2118),
                 2017: (1717, 1864, 2010), 2018: (1660, 1676, 1693)}
# The period means the report prints under that table. Reproducing them is the transcription check.
MOHAVE_PERIOD_MEANS = (1531, 1718, 1905)


def half_spread(triples):
    """Half the probable-minimum to probable-maximum gap, as a fraction of most probable. This is
    the closure uncertainty on a single year, which is the quantity the report quotes as a range."""
    per = {y: (hi - lo) / 2 / mp for y, (lo, mp, hi) in triples.items()}
    return per, mean(per.values()), max(per.values())


# --- Lake Mead, from the release ---------------------------------------------------------------
mead_triples = {}
for y in mead["meta"]["qualified_years"]:
    a = mead["annual_ft"][str(y)]
    lo, hi = sorted((a["measured"], a["ebr_adjusted"]))
    mead_triples[y] = (lo * MM_PER_FT, a["corrected"] * MM_PER_FT, hi * MM_PER_FT)
mead_per, mead_mean, mead_max = half_spread(mead_triples)

# --- Lake Mohave, from table 9, transcription checked ------------------------------------------
recomputed = tuple(round(mean(t[i] for t in MOHAVE_TABLE9.values())) for i in range(3))
transcription_ok = all(abs(a - b) <= 1 for a, b in zip(recomputed, MOHAVE_PERIOD_MEANS))
if not transcription_ok:
    raise SystemExit(f"[evap-flux-unc] table 9 transcription does not reproduce the report's own "
                     f"period means: got {recomputed}, report prints {MOHAVE_PERIOD_MEANS}")
moh_per, moh_mean, moh_max = half_spread(MOHAVE_TABLE9)

# The sigma the model should carry. At Mead the report's own stated measurement uncertainty (5-7%)
# is WIDER than the closure spread we measure (2.1% mean), so 5% already covers it and is kept. At
# Mohave the closure spread alone is double that, so closure, not instrument precision, is the
# binding term and sets the sigma.
MEAD_STATED = 0.05          # Moreo & Swancar evaporation uncertainty, 5-7%, low end
sigma = {"Lake Mead": round(max(MEAD_STATED, mead_mean), 3),
         "Lake Mohave": round(max(MEAD_STATED, moh_mean), 3)}

doc = {
    "meta": {
        "what": "per-lake evaporation-depth uncertainty, from the gap between probable minimum "
                "and probable maximum evaporation",
        "why": "the Monte Carlo carried one sigma for both instrumented lakes; energy balance "
               "closes at Mead and does not at Mohave",
        "source": OFR,
        "report_says": {
            "Lake Mead": "differences between minimum and most probable annual evaporation "
                         "'ranging from 25 to 86 mm ... or 1-5 percent of the annual evaporation'",
            "Lake Mohave": "'the difference is greater, ranging from 16 to 383 mm (0.63 to 15.08 "
                           "in.) or 1-22 percent of annual evaporation'"},
        "period_ebr": {"Lake Mead": 0.98, "Lake Mohave": 0.82},
        "mohave_transcription_check": {
            "recomputed_period_means_mm": recomputed,
            "report_period_means_mm": list(MOHAVE_PERIOD_MEANS),
            "agrees": transcription_ok,
            # Second, independent check: the report states Mohave's range in words as 1-22 percent
            # of annual evaporation. Our per-year figures must land on that, and they do (1.0-22.1).
            # Reproducing both the printed means AND the quoted range makes a transcription error
            # or a wrong definition of the metric very hard to hide.
            "recomputed_range_pct": [round(100 * min(moh_per.values()), 1),
                                     round(100 * max(moh_per.values()), 1)],
            "report_quoted_range_pct": [1, 22]}},
    "lakes": {
        "Lake Mead": {
            "provenance": "computed from the ScienceBase releases (all three columns published)",
            "years": sorted(mead_triples),
            "half_spread_pct_by_year": {y: round(100 * v, 2) for y, v in mead_per.items()},
            "mean_half_spread_pct": round(100 * mead_mean, 2),
            "max_half_spread_pct": round(100 * mead_max, 2)},
        "Lake Mohave": {
            "provenance": "OFR 2021-1022 table 9; no data release covers 2014-2018",
            "years": sorted(MOHAVE_TABLE9),
            "half_spread_pct_by_year": {y: round(100 * v, 2) for y, v in moh_per.items()},
            "mean_half_spread_pct": round(100 * moh_mean, 2),
            "max_half_spread_pct": round(100 * moh_max, 2)}},
    "model_sigma": sigma,
    "verdict": {
        "ratio_mohave_to_mead": round(moh_mean / mead_mean, 1),
        "statement": (
            f"Closure uncertainty at Lake Mohave averages {100 * moh_mean:.0f}% of its annual "
            f"evaporation against {100 * mead_mean:.0f}% at Lake Mead, "
            f"{moh_mean / mead_mean:.0f} times as much, because a larger share of Mohave's "
            f"measured turbulent flux comes off the surrounding desert (period energy balance "
            f"ratio 0.82 against 0.98). The model now carries "
            f"{100 * sigma['Lake Mohave']:.0f}% at Mohave rather than the "
            f"{100 * MEAD_STATED:.0f}% it used to share with Mead.")}}

(OUT / "evap_flux_uncertainty.json").write_text(json.dumps(doc, indent=2))
print(f"[evap-flux-unc] Mead   mean half-spread {100 * mead_mean:.1f}%  max {100 * mead_max:.1f}%  "
      f"(from the data release, {len(mead_triples)} years)")
print(f"[evap-flux-unc] Mohave mean half-spread {100 * moh_mean:.1f}%  max {100 * moh_max:.1f}%  "
      f"(OFR table 9, transcription reproduces {recomputed} vs {MOHAVE_PERIOD_MEANS})")
print(f"[evap-flux-unc] model sigma: {sigma}")
print("[evap-flux-unc] wrote outputs/evap_flux_uncertainty.json")
