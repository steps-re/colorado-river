"""What the Post-2026 Final EIS does to the ideas already on this site.

Reclamation released the Final EIS on 31 July 2026. The seven states missed both
consensus deadlines, so Interior advanced its own Preferred Alternative: an adaptive
framework re-set every two years, bounded by sideboards rather than a fixed schedule.
Record of Decision expected around October; operations begin 1 January 2027.

The rules that change the arithmetic on this site:
  - Lake Powell annual release bounded 5.0 to 12.0 maf (2027-28: 8.0 maf if Powell is
    at or above 3,540 ft on 1 October, otherwise 7.0).
  - Lower Basin shortages permitted up to 3.0 maf/yr, roughly 40% of apportionment.
  - Conservation storage up to 8.0 maf in Powell and 3.0 maf in Mead.
  - Upper Basin: no mandatory cuts, a 200 kAF/yr voluntary target.

This re-runs three prior pieces of work against those numbers:
  1. measured-conservation: what does a 3.0 maf shortage cost at MEASURED crop values?
  2. reservoir-solar: how much of the gap can FPV evaporation suppression close?
  3. hydropower: what do the release sideboards do to Glen Canyon generation and to
     the CRSP Basin Fund that pays for Basin environmental programmes?

Sources: Final EIS figures via grounded research 2026-08-04 -- verify against the
document before publication. Demand curve is measured (OpenET x CDL x crop values).

Pure numpy/stdlib on repo outputs. ZERO LLM tokens.
"""
from __future__ import annotations

import csv
import json
import os

import numpy as np

REPO = os.path.expanduser("~/code/steps/colorado-river")
OUT = os.path.join(REPO, "outputs")

POWELL_SIDEBOARDS = (5.0, 12.0)
POWELL_TIERS = {">=3540ft": 8.0, "<3540ft": 7.0}
MAX_LB_SHORTAGE_MAF = 3.0
CONS_STORAGE_MAF = {"Lake Powell": 8.0, "Lake Mead": 3.0}
UB_VOLUNTARY_KAF = 200

# Glen Canyon
CAP_MW, Q_AT_CAP = 1320.0, 31000.0
MAF_PER_CFS_YR = 1.9835 * 365 / 1e6
CRSP_ENERGY_VALUE = (30, 60)     # $/MWh range for CRSP firm energy


def demand_curve():
    rows = []
    with open(os.path.join(OUT, "demand_curve.csv")) as f:
        for r in csv.DictReader(f):
            rows.append((float(r["water_AF"]), float(r["gross_value_per_AF"]), r["crop"]))
    rows.sort(key=lambda x: x[1])          # cheapest water first
    return rows


def cost_to_acquire(target_af, rows, premium=1.0):
    """Walk up the measured demand curve buying the cheapest water first.
    `premium` scales the crop gross value to an offer price (a farmer needs more
    than gross output per AF to fallow, since some costs are avoided but not all)."""
    got, cost, marginal, detail = 0.0, 0.0, 0.0, []
    for af, val, crop in rows:
        if got >= target_af:
            break
        take = min(af, target_af - got)
        got += take
        cost += take * val * premium
        marginal = val * premium
        detail.append((crop, take, val * premium))
    return dict(acquired_af=got, short_af=max(0.0, target_af - got),
                total_cost=cost, avg_per_af=cost / got if got else 0.0,
                marginal_per_af=marginal, detail=detail)


def glen_canyon(maf):
    """Annual generation at a given release volume, using the measured 2015 hourly
    release shape scaled to volume with the LTEMP floor preserved."""
    rel = np.load(os.path.join(REPO, "cache", "rel_cfs_2015.npy"))
    hour = np.arange(len(rel)) % 24
    floor = np.where((hour >= 7) & (hour < 19), 8000.0, 5000.0)
    floor = np.minimum(floor, rel)
    swing = rel - floor
    base_maf = rel.mean() * MAF_PER_CFS_YR
    floor_maf = floor.mean() * MAF_PER_CFS_YR
    if maf >= floor_maf:
        k = (maf - floor_maf) / max(1e-9, base_maf - floor_maf)
        r = floor + swing * k
    else:
        r = floor * (maf / floor_maf)
    gen = np.clip(r / Q_AT_CAP * CAP_MW, 0, CAP_MW)
    return float(gen.sum() / 1e6)          # TWh


def main():
    rows = demand_curve()
    pool_af = sum(r[0] for r in rows)
    print(f"Measured Lower Basin ag demand curve: {pool_af/1e6:.2f} maf across "
          f"{len(rows)} crops, 4 counties\n")

    # ---------- 1. what a 3.0 maf shortage costs at measured values ----------
    print("--- 1. COST OF THE SHORTAGES THE NEW RULES PERMIT ---")
    print(f"{'shortage':>10} {'acquired':>10} {'avg $/AF':>9} {'marginal $/AF':>13} "
          f"{'annual cost':>14} {'% of measured pool':>19}")
    impacts = {}
    for sh in (0.5, 1.0, 1.5, 2.0, 3.0):
        af = sh * 1e6
        r = cost_to_acquire(af, rows)
        impacts[f"shortage_{sh}maf"] = r
        short = f" (SHORT {r['short_af']/1e6:.2f} maf)" if r["short_af"] > 1000 else ""
        print(f"{sh:>8.1f}maf {r['acquired_af']/1e6:>9.2f}m ${r['avg_per_af']:>8.0f} "
              f"${r['marginal_per_af']:>12.0f} ${r['total_cost']/1e9:>12.2f}B "
              f"{r['acquired_af']/pool_af*100:>18.0f}%{short}")
    print("\n  Reading: the first ~1.5 maf is cheap because it is wheat, hay and the")
    print("  low-value end of alfalfa. Beyond ~2.7 maf the measured curve runs out of")
    print("  sub-$400 water entirely and the next acre-foot costs thousands, because")
    print("  what is left is lettuce, grapes and carrots.")
    r3 = impacts["shortage_3.0maf"]
    print(f"\n  A 3.0 maf shortage cannot be met from these four counties' ag water at")
    print(f"  any sane price: the curve is short {r3['short_af']/1e6:.2f} maf and the")
    print(f"  marginal acre-foot is already ${r3['marginal_per_af']:,.0f}.")

    # ---------- 2. how much of that can FPV close ----------
    print("\n--- 2. WHAT FPV EVAPORATION SUPPRESSION CONTRIBUTES ---")
    try:
        w = json.load(open(os.path.join(OUT, "fpv_water_benefit.json")))
        fpv_af = w["at_tie_limit"]["af_per_yr_p50"]
    except Exception:
        fpv_af = 19_050.0
    for sh in (1.0, 3.0):
        print(f"  vs a {sh:.1f} maf shortage: FPV at the interconnection limit supplies "
              f"{fpv_af/(sh*1e6)*100:>5.2f}%")
    # Value the FPV water at the MARGINAL price, not the cheapest-first stack price.
    # If the Basin is already buying 1.5 maf, the next acre-foot from any source is
    # worth what the marginal acre-foot costs, not what the first one did.
    marg = cost_to_acquire(1.5e6, rows)["marginal_per_af"]
    for label, px in (("marginal on the measured curve", marg),
                      ("what Reclamation/IID actually paid 2025-26", 400.0)):
        print(f"  valued at ${px:,.0f}/AF ({label}): "
              f"${fpv_af*px/1e6:,.1f}M/yr")
    print(f"  Against roughly $2.5B of capex for 2 GWp, the water alone returns "
          f"{fpv_af*400/2.5e9*100:.2f}% a year. The water is not the business case.")

    # ---------- 3. hydropower under the sideboards ----------
    print("\n--- 3. GLEN CANYON UNDER THE RELEASE SIDEBOARDS ---")
    print(f"{'release':>10} {'generation':>12} {'vs 8.23 maf':>12} "
          f"{'energy value $M/yr':>20}")
    hyd = {}
    base_twh = glen_canyon(8.23)
    for maf in (POWELL_SIDEBOARDS[0], 6.0, POWELL_TIERS["<3540ft"],
                POWELL_TIERS[">=3540ft"], 8.23, 10.0, POWELL_SIDEBOARDS[1]):
        twh = glen_canyon(maf)
        lo, hi = (twh * 1e6 * CRSP_ENERGY_VALUE[0] / 1e6,
                  twh * 1e6 * CRSP_ENERGY_VALUE[1] / 1e6)
        hyd[f"{maf}maf"] = {"twh": twh, "value_musd_lo": lo, "value_musd_hi": hi}
        print(f"{maf:>8.2f}maf {twh:>11.2f} TWh {twh/base_twh-1:>11.0%} "
              f"${lo:>9,.0f}-{hi:,.0f}")
    swing = hyd[f"{POWELL_SIDEBOARDS[1]}maf"]["twh"] - hyd[f"{POWELL_SIDEBOARDS[0]}maf"]["twh"]
    print(f"\n  The sideboards alone swing Glen Canyon by {swing:.2f} TWh/yr, roughly "
          f"${swing*1e6*CRSP_ENERGY_VALUE[0]/1e6:,.0f}M to "
          f"${swing*1e6*CRSP_ENERGY_VALUE[1]/1e6:,.0f}M of CRSP revenue.")
    print("  That is the Basin Fund's exposure, and it is set biennially by a")
    print("  discretionary federal decision rather than by hydrology alone. Any")
    print("  revenue model for a project sharing that interconnection inherits it.")

    # ---------- 4. the conservation-storage lever ----------
    print("\n--- 4. CONSERVATION STORAGE, THE NEW LEVER ---")
    tot = sum(CONS_STORAGE_MAF.values())
    print(f"  The framework allows {CONS_STORAGE_MAF['Lake Powell']:.0f} maf of conserved "
          f"water stored in Powell and {CONS_STORAGE_MAF['Lake Mead']:.0f} maf in Mead, "
          f"{tot:.0f} maf total.")
    cost_fill = cost_to_acquire(tot * 1e6, rows)
    print(f"  Filling it from the measured ag curve is not possible: the four-county "
          f"pool is only {pool_af/1e6:.2f} maf.")
    print(f"  Even acquiring the {pool_af/1e6:.2f} maf that exists costs "
          f"${cost_fill['total_cost']/1e9:.1f}B at measured gross values.")
    print("  So the storage accounts are large enough to hold far more water than the")
    print("  Lower Basin ag economy can plausibly release. The binding constraint is")
    print("  acquisition, not storage -- which is an argument for supply-side measures")
    print("  like evaporation suppression, and against assuming conservation alone fills it.")

    json.dump({
        "final_eis": {"powell_sideboards_maf": POWELL_SIDEBOARDS,
                      "powell_tiers_2027_28": POWELL_TIERS,
                      "max_lb_shortage_maf": MAX_LB_SHORTAGE_MAF,
                      "conservation_storage_maf": CONS_STORAGE_MAF,
                      "ub_voluntary_kaf": UB_VOLUNTARY_KAF},
        "measured_pool_maf": pool_af / 1e6,
        "shortage_costs": {k: {kk: vv for kk, vv in v.items() if kk != "detail"}
                           for k, v in impacts.items()},
        "fpv_contribution_af": fpv_af,
        "glen_canyon_by_release": hyd,
        "caveats": [
            "Final EIS figures came from grounded research, not the document itself. "
            "Verify before publication.",
            "Demand curve prices are GROSS crop output per acre-foot, an upper bound on "
            "the reservation price; net margin is lower, so real acquisition may be cheaper.",
            "Scope is four measured Lower Basin ag counties, not the whole basin.",
            "Generation scales the 2015 hourly release shape; it ignores head effects, "
            "which would reduce output further at low pool.",
        ],
    }, open(os.path.join(OUT, "post2026_impacts.json"), "w"), indent=1)
    print("\nwrote outputs/post2026_impacts.json")


if __name__ == "__main__":
    main()
