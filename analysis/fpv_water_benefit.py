"""How much water does reservoir FPV actually save, and at what cost per acre-foot?

This is the question the energy modelling kept circling. The NSF white paper frames
evaporation suppression as the water-conserving byproduct of a self-sustaining energy
system, and claims a candidate portfolio "could demonstrate as much as 300,000 acre-feet
per year of evaporation savings, comparable to Nevada's entire annual Colorado River
apportionment." Separately the PI states the design contemplates 10-20% surface cover.

Those two statements are testable against each other, and against the interconnection
limit established in analysis/hourly_fpv_hydro.py (~1 GW per dam on the existing tie).

Method:
  water saved = covered acres x evaporation rate x suppression efficiency
                x (1 - offset from increased evaporation over open water)
  covered acres = FPV MWp / areal power density
  Monte Carlo over evaporation rate, areal density, suppression and offset.

Surface areas are MEASURED (Earth Engine, outputs/ee_reservoir_area.csv), not modelled.

Cost of water is reported three ways, because attribution is the whole argument:
  - full attribution: all capex charged to water (the "FPV as a water project" view)
  - net-of-energy: only the revenue gap charged to water (the honest developer view)
  - free: if the array clears on energy alone, water is a byproduct at zero marginal cost

Pure numpy on cached public data. ZERO LLM tokens.
"""
from __future__ import annotations

import csv
import json
import os

import numpy as np

REPO = os.path.expanduser("~/code/steps/colorado-river")
OUT = os.path.join(REPO, "outputs")
RNG = np.random.default_rng(20260804)

# Annual open-water evaporation, ft/yr.
# CORRECTED 2026-08-04 after an Earth Engine cross-check. A grounded research pass gave
# Powell 3.8-4.0 ft/yr, which we used first and which was almost certainly too low. Two
# independent lines now agree near 6 ft/yr:
#   - gridMET grass-reference ET over the lake, x an arid open-water coefficient of
#     1.05-1.25, gives Powell 5.4-6.4 ft/yr and Mead 6.6-7.9 ft/yr.
#   - Reclamation's REPORTED Powell loss volume (350-386 kAF/yr) divided by the measured
#     surface area (~57,000 acres) implies 6.1-6.8 ft/yr.
# With the low rate we had to invoke bank storage to reconcile the reported volume. At
# ~6 ft/yr no residual is needed, so the bank-storage explanation was probably wrong too.
# See analysis/ee_fpv_envelope.py.
EVAP_FT = {"Lake Mead": (6.5, 0.5), "Lake Powell": (6.0, 0.6)}

# Reclamation-reported annual loss volumes, for cross-checking area x rate.
# With the corrected rates both lakes now reconcile against reported volumes without
# invoking a bank-storage residual.
REPORTED_EVAP_AF = {"Lake Mead": (410_000, 520_000), "Lake Powell": (350_000, 386_000)}

# Basin context
BASIN_CONSUMPTIVE_USE_MAF = 13.0     # roughly, Upper + Lower
NEVADA_APPORTIONMENT_AF = 300_000
MAX_LB_SHORTAGE_AF = 3_000_000       # Post-2026 Final EIS allows up to 3.0 maf/yr
AG_CONSERVATION_USD_PER_AF = (325, 400)   # recent basin transaction range

# Interconnection limit from the hourly model: ~1 GW per dam rides the existing tie
# at ~2% curtailment; 2 GW curtails 32%.
TIE_LIMIT_GW = 1.0


def areas(year=2026, smooth=3):
    """Measured water area. Averaged over the last `smooth` years by default: the
    single-year EE value for Powell 2026 (43,850 ac) is far below 2025 (60,521 ac)
    and looks like a measurement artifact, and area drives every number here."""
    rows = list(csv.DictReader(open(os.path.join(OUT, "ee_reservoir_area.csv"))))
    a = {}
    for lake in {r["lake"] for r in rows}:
        vals = [(int(r["year"]), float(r["water_acres"])) for r in rows
                if r["lake"] == lake and int(r["year"]) <= year]
        vals.sort()
        use = vals[-smooth:] if smooth else vals[-1:]
        a[lake] = sum(v for _, v in use) / len(use)
    return a


def draw(n):
    return dict(
        # MWp per hectare of occupied water surface, including row spacing,
        # walkways and mooring corridors. Large arrays run lower than panel-level
        # density implies.
        density_mw_per_ha=np.clip(RNG.normal(1.0, 0.18, n), 0.5, 1.6),
        # Evaporation suppression over the COVERED area. Physically high directly
        # under panels; the literature's 5-90% spread is mostly about what fraction
        # of the waterbody is covered and how the study defines the denominator.
        suppression=np.clip(RNG.normal(0.85, 0.08, n), 0.4, 0.98),
        # Offset: covering part of a reservoir changes fetch, surface temperature
        # and the energy balance, so evaporation over the OPEN water can rise.
        offset=np.clip(RNG.normal(0.12, 0.07, n), 0.0, 0.35),
    )


def water_per_gw(lake, n=20000, year=2026):
    a = areas(year)[lake]
    mu, sd = EVAP_FT[lake]
    d = draw(n)
    evap_ft = np.clip(RNG.normal(mu, sd, n), 3.5, 8.0)
    covered_ha = 1000.0 / d["density_mw_per_ha"]          # ha per GWp
    covered_acres = covered_ha * 2.4711
    gross = covered_acres * evap_ft * d["suppression"]
    net = gross * (1 - d["offset"])
    return dict(lake=lake, area_acres=a,
                total_evap_af=float(np.median(a * evap_ft)),
                covered_acres=covered_acres, coverage_pct=covered_acres / a * 100,
                af_per_gw=net)


def q(x, p):
    return float(np.percentile(x, p))


def main():
    a = areas()
    print("Measured surface area (Earth Engine, 2026): "
          + ", ".join(f"{k} {v:,.0f} acres" for k, v in a.items()))
    res = {}
    for lake in ("Lake Powell", "Lake Mead"):
        w = water_per_gw(lake)
        res[lake] = w
        print(f"\n{lake}")
        print(f"  total annual evaporation        {w['total_evap_af']:>10,.0f} AF/yr")
        print(f"  1 GWp occupies                  {q(w['covered_acres'],50):>10,.0f} acres "
              f"= {q(w['coverage_pct'],50):.1f}% of surface")
        print(f"  water saved per GWp             {q(w['af_per_gw'],50):>10,.0f} AF/yr "
              f"[p10 {q(w['af_per_gw'],10):,.0f}, p90 {q(w['af_per_gw'],90):,.0f}]")
        print(f"  as % of that lake's evaporation {q(w['af_per_gw']/w['total_evap_af']*100,50):>9.1f}%")

    # --- the deployment the grid can actually absorb
    both = res["Lake Powell"]["af_per_gw"] + res["Lake Mead"]["af_per_gw"]
    tie_af = both * TIE_LIMIT_GW
    print(f"\n--- AT THE INTERCONNECTION LIMIT ({TIE_LIMIT_GW:.0f} GW per dam, 2 dams) ---")
    print(f"  water saved            {q(tie_af,50):>10,.0f} AF/yr "
          f"[p10 {q(tie_af,10):,.0f}, p90 {q(tie_af,90):,.0f}]")
    print(f"  vs basin consumptive use ({BASIN_CONSUMPTIVE_USE_MAF} maf)   "
          f"{q(tie_af,50)/(BASIN_CONSUMPTIVE_USE_MAF*1e6)*100:>6.2f}%")
    print(f"  vs a 3.0 maf Lower Basin shortage          "
          f"{q(tie_af,50)/MAX_LB_SHORTAGE_AF*100:>6.2f}%")
    print(f"  vs Nevada's apportionment (300 kAF)        "
          f"{q(tie_af,50)/NEVADA_APPORTIONMENT_AF*100:>6.2f}%")

    # --- what the white paper's 300,000 AF/yr actually requires
    print("\n--- WHAT 300,000 AF/YR REQUIRES ---")
    tot_evap = res["Lake Powell"]["total_evap_af"] + res["Lake Mead"]["total_evap_af"]
    d = draw(20000)
    eff = np.clip(RNG.normal(0.85, 0.08, 20000), 0.4, 0.98) * (1 - d["offset"])
    cover_needed = NEVADA_APPORTIONMENT_AF / (tot_evap * eff)
    # `both` is AF saved by 1 GWp at Powell PLUS 1 GWp at Mead, i.e. per 2 GWp total.
    af_per_2gwp = both
    gw_for_300k = NEVADA_APPORTIONMENT_AF / af_per_2gwp * 2.0   # -> GWp, not pairs
    print(f"  Mead + Powell evaporation combined        {tot_evap:>10,.0f} AF/yr")
    print(f"  coverage of BOTH lakes required           {q(cover_needed*100,50):>9.0f}% "
          f"[p10 {q(cover_needed*100,10):.0f}%, p90 {q(cover_needed*100,90):.0f}%]")
    print(f"  FPV capacity required                     {q(gw_for_300k,50):>9.1f} GWp "
          f"[p10 {q(gw_for_300k,10):.1f}, p90 {q(gw_for_300k,90):.1f}]")
    print(f"  ... against a tie that carries             {TIE_LIMIT_GW*2:>9.1f} GWp "
          f"({q(gw_for_300k,50)/(TIE_LIMIT_GW*2):.0f}x oversubscribed)")
    print(f"  ... and against the PI's stated cover      {'10-20':>9}%")

    # --- what 10-20% cover actually delivers
    print("\n--- WHAT 10-20% SURFACE COVER DELIVERS ---")
    for cov in (0.10, 0.20):
        acres = (a["Lake Powell"] + a["Lake Mead"]) * cov
        af = acres * np.array([5.7 if i % 2 else 6.0 for i in range(20000)]) * eff
        gw = acres / 2.4711 * d["density_mw_per_ha"] / 1000.0
        print(f"  {cov*100:.0f}% cover -> {q(af,50):>8,.0f} AF/yr, needs {q(gw,50):>5.1f} GWp "
              f"({q(gw,50)/(TIE_LIMIT_GW*2):.0f}x the tie limit)")

    # --- cost of water under three attribution rules
    print("\n--- COST OF WATER ($/AF, 25-year life, 1 GWp per dam x 2) ---")
    capex_per_gw = 1.25e9
    af_yr = q(tie_af, 50)
    lifetime_af = af_yr * 25
    full = capex_per_gw * 2 / lifetime_af
    print(f"  full attribution (all capex on water)     ${full:>9,.0f}/AF")
    for gap in (5, 10, 20):
        # revenue gap in $/MWh on ~1.75 TWh/GW-yr, charged to water
        subsidy = gap * 1.75e6 * 2 * 25
        print(f"  net-of-energy, ${gap:>2}/MWh revenue gap      ${subsidy/lifetime_af:>9,.0f}/AF")
    print(f"  if the array clears on energy alone       {'$0':>10}/AF (byproduct)")
    print(f"  reference: recent basin ag conservation   "
          f"${AG_CONSERVATION_USD_PER_AF[0]:,}-{AG_CONSERVATION_USD_PER_AF[1]:,}/AF")

    summary = {
        "measured_area_acres_2026": a,
        "per_lake": {k: {"total_evap_af": v["total_evap_af"],
                         "af_per_gw_p10": q(v["af_per_gw"], 10),
                         "af_per_gw_p50": q(v["af_per_gw"], 50),
                         "af_per_gw_p90": q(v["af_per_gw"], 90),
                         "coverage_pct_per_gw_p50": q(v["coverage_pct"], 50)}
                     for k, v in res.items()},
        "at_tie_limit": {"gw_per_dam": TIE_LIMIT_GW, "dams": 2,
                         "af_per_yr_p10": q(tie_af, 10), "af_per_yr_p50": q(tie_af, 50),
                         "af_per_yr_p90": q(tie_af, 90),
                         "pct_of_basin_use": q(tie_af, 50) / (BASIN_CONSUMPTIVE_USE_MAF * 1e6) * 100,
                         "pct_of_3maf_shortage": q(tie_af, 50) / MAX_LB_SHORTAGE_AF * 100},
        "for_300kaf": {"coverage_pct_p50": q(cover_needed * 100, 50),
                       "gwp_required_p50": q(gw_for_300k, 50)},
        "cost_per_af": {"full_attribution": full},
        "caveats": [
            "Surface areas measured by Earth Engine; evaporation rates are Reclamation-style "
            "priors with uncertainty, not gauged pan data for the modelled year.",
            "Suppression efficiency is over the COVERED area. The open-water offset term is "
            "poorly constrained empirically -- this is exactly what Tempe Town Lake would measure.",
            "Assumes saved water stays in the reservoir. Whether it becomes a creditable "
            "conserved-water asset, and to whom, is a legal question, not a physical one.",
            "Ignores the negative feedback where higher pool raises surface area and hence "
            "evaporation, which slightly reduces net savings.",
        ],
    }
    with open(os.path.join(OUT, "fpv_water_benefit.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print("\nwrote outputs/fpv_water_benefit.json")


if __name__ == "__main__":
    main()
