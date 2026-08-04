"""Co-located behind-the-meter load at Glen Canyon: does it help, and does its cooling
water eat the water benefit it is supposed to enable?

This backs the claims published in post-2026.html section 9 and in the NSF one-pager.
It was originally worked out inline, which meant a public claim with no reproducible
script behind it. This is that script.

Three questions:
  1. What does behind-the-meter load actually solve that grid export does not?
  2. A data centre in northern Arizona needs cooling, and cooling consumes water.
     At what cooling intensity does the load consume more than the array saves?
  3. Closed-loop cooling raises power usage effectiveness, so the same computing needs
     more electricity. Does that extra demand help or hurt the water balance?

Published cooling intensities disagree by about a factor of two, so both are carried
rather than picking the convenient one.

Pure stdlib. ZERO LLM tokens.
"""
from __future__ import annotations

import json
import os

REPO = os.path.expanduser("~/code/steps/colorado-river")
OUT = os.path.join(REPO, "outputs")

AF_PER_L = 1 / 1.233e6
GAL_TO_AF = 1 / 325851.0

# Water saved per GWp of floating array, from fpv_water_benefit.py (Powell/Mead mean).
FPV_SAVED_PER_GWP = 11_000.0

# Two published cooling intensities that disagree:
#   (a) ~18,400 gal/day/MW of evaporative cooling  -> 20.6 AF/MW-yr
#   (b) ~1.8 L/kWh industry-average WUE            -> 10.2 AF/MW-yr at 80% utilisation
UTIL = 0.80
COOLING = {
    "evaporative (18,400 gal/day/MW)": 18_400 * 365 * GAL_TO_AF,
    "evaporative (1.8 L/kWh)": 1.8 * 1000 * 8760 * UTIL * AF_PER_L,
    "hybrid (0.5 L/kWh)": 0.5 * 1000 * 8760 * UTIL * AF_PER_L,
    "closed-loop / dry": 0.3,
}

# The retired Navajo Generating Station drew this from Lake Powell before 2019.
# Secondary source, not verified against a primary document.
NGS_WATER_AFY = 34_100.0

PUE_EVAP, PUE_CLOSED = 1.15, 1.5


def main():
    res = {}

    print("=== 1. WHAT BEHIND-THE-METER LOAD SOLVES ===")
    for a, b in [
        ("Export path", "capped by AVAILABLE TRANSFER CAPABILITY, not by spare nameplate. "
                        "WAPA firm rights persist even when the dam runs low."),
        ("Behind the meter", "touches none of WAPA's wires, so ATC stops being the constraint."),
        ("Negative prices", "self-consumption has no exposure to them."),
        ("Water benefit", "only becomes material above the scale the grid can absorb."),
    ]:
        print(f"  {a:<18} {b}")

    print("\n=== 2. COOLING WATER vs WATER SAVED, load matched 1:1 with array ===")
    print(f"{'cooling design':<34}{'AF/MW-yr':>10}{'1 GW uses':>12}{'array saves':>13}{'net':>11}")
    per_gw = {}
    for label, af_mw in COOLING.items():
        use = af_mw * 1000
        net = FPV_SAVED_PER_GWP - use
        per_gw[label] = {"af_per_mw_yr": af_mw, "af_yr_at_1gw": use, "net_af_yr": net}
        print(f"{label:<34}{af_mw:>10.1f}{use:>12,.0f}{FPV_SAVED_PER_GWP:>13,.0f}{net:>+11,.0f}")
    res["per_gw"] = per_gw

    breakeven = FPV_SAVED_PER_GWP / 1000  # AF/MW-yr at which use == saving
    breakeven_l_kwh = (breakeven / AF_PER_L) / (1000 * 8760 * UTIL)
    res["breakeven"] = {"af_per_mw_yr": breakeven, "l_per_kwh": breakeven_l_kwh}
    print(f"\n  Break-even cooling intensity: {breakeven:.1f} AF/MW-yr "
          f"({breakeven_l_kwh:.2f} L/kWh at {UTIL:.0%} utilisation).")
    print("  Evaporative cooling sits at or above that on both published figures, so it")
    print("  ranges from a wash to roughly twice the deficit. Closed-loop keeps almost all")
    print("  of the benefit. Cooling design, not the array, decides the water outcome.")

    print("\n=== 3. WHERE THE WATER WOULD COME FROM ===")
    worst = COOLING["evaporative (18,400 gal/day/MW)"] * 1000
    print(f"  NGS drew {NGS_WATER_AFY:,.0f} AF/yr from Lake Powell before retiring in 2019.")
    print(f"  A 1 GW evaporatively-cooled load needs ~{worst:,.0f} AF/yr, "
          f"{worst/NGS_WATER_AFY:.0%} of that retired allocation.")
    print("  The Navajo Nation is seeking to reclaim it, so the water is available on")
    print("  paper and contested in practice. Secondary sourcing, verify before citing.")
    res["ngs"] = {"retired_allocation_af_yr": NGS_WATER_AFY,
                  "share_needed_1gw_evaporative": worst / NGS_WATER_AFY}

    print("\n=== 4. THE PUE LOOP ===")
    it_mw = 1000 / PUE_EVAP
    closed_mw = it_mw * PUE_CLOSED
    extra = closed_mw - 1000
    extra_saved = extra / 1000 * FPV_SAVED_PER_GWP
    print(f"  Closed-loop raises PUE from {PUE_EVAP} to {PUE_CLOSED}, so a 1,000 MW")
    print(f"  evaporative load becomes ~{closed_mw:,.0f} MW closed-loop.")
    print(f"  That is {extra:,.0f} MW of additional on-site demand, which is "
          f"{extra/1000:.2f} GWp more array")
    print(f"  that can be self-consumed, saving a further ~{extra_saved:,.0f} AF/yr.")
    print("  Going water-free raises the water benefit rather than trading against it.")
    res["pue_loop"] = {"pue_evap": PUE_EVAP, "pue_closed": PUE_CLOSED,
                       "load_mw_closed_loop": closed_mw, "extra_mw": extra,
                       "extra_water_saved_af_yr": extra_saved}

    res["caveats"] = [
        "Cooling intensities are published ranges that disagree by ~2x. Both carried.",
        "FPV_SAVED_PER_GWP comes from fpv_water_benefit.py and inherits its uncertainty "
        "on suppression efficiency and the open-water offset.",
        "NGS allocation and transmission figures are secondary-sourced, not verified "
        "against Reclamation or SRP documents.",
        "Assumes the load is matched 1:1 with array nameplate. Real siting would size "
        "the array to the load's actual profile, which a 24/7 load makes harder, not easier.",
        "Ignores whether the water right could legally follow the load at all.",
    ]
    with open(os.path.join(OUT, "colocated_load.json"), "w") as f:
        json.dump(res, f, indent=1)
    print("\nwrote outputs/colocated_load.json")


if __name__ == "__main__":
    main()
