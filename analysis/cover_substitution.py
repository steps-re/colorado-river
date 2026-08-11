#!/usr/bin/env python3
"""If a reservoir gets covered anyway, what is floating PV actually competing against?

Raised by Upmanu Lall (ASU), personal communication 11 Aug 2026: reservoir covers are being
considered for TEMPERATURE and biodiversity management, not for evaporation. If a cover goes in for
that reason, FPV is not competing against bare water. It substitutes for a cover that was going to
be bought regardless, and the avoided cost belongs on FPV's side of the ledger.

That matters here because this site already carries the thermal story: as Powell fell, Glen Canyon
released warmer water, bass-suitable days went from ~2 to ~41 a year, and smallmouth bass reached
the last humpback-chub stronghold. Cool-mix flows work and are contested by hydropower. So surface
thermal management is a live objective on this river, not a hypothetical.

WHAT THIS DOES NOT DO. It does not claim a cover will be deployed, or price one. The only published
anchor for a floating cover is LADWP's $1.43M/acre, and evap_cover_comparison.py already flags that
as a POTABLE-WATER product and an upper bound rather than a measurement. So this computes a
BREAK-EVEN instead: how expensive would the avoided cover have to be for the substitution argument
to change FPV's answer? A break-even is honest where a point estimate would not be.

Output: outputs/cover_substitution.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
WACC = 0.07
MW_PER_ACRE = 120.0 * 0.00404686          # 120 MW/km2 -> MW/acre, as in evap_cover_comparison
EVAP_FT = json.loads((OUT / "fpv_coverage_explorer.json").read_text())["Lake Mead"]["params"]["evap_ft"]
REUSE_BAND = (2_500, 3_500)               # analysis/reuse_resource.py


def crf(n):
    return WACC * (1 + WACC) ** n / ((1 + WACC) ** n - 1)


# FPV and the cover, on the one basis evap_cover_comparison uses: gross of power revenue, each
# annualised over its own life. Revenue is handled separately and deliberately not mixed in here.
FPV_ANN = 1.23e6 * MW_PER_ACRE * crf(25) + 25_000 * MW_PER_ACRE
FPV_SUPP, COVER_SUPP = 0.75, 0.90
FPV_AF = EVAP_FT * FPV_SUPP

# The published anchor, and what it annualises to.
COVER_CAPEX_ANCHOR = 250_000_000 / 175    # LADWP's own alternative quote, $1.43M/acre
COVER_ANN_ANCHOR = COVER_CAPEX_ANCHOR * crf(20) + 2_000


def fpv_net_per_af(avoided_annual_per_acre):
    """FPV's cost per acre-foot once an avoided cover is credited against it."""
    return (FPV_ANN - avoided_annual_per_acre) / FPV_AF


def breakeven_avoided(target_usd_per_af):
    """Avoided cover cost, $/acre-yr, at which FPV lands on a target $/AF."""
    return FPV_ANN - target_usd_per_af * FPV_AF


def capex_for_annual(annual, life=20, om=2_000):
    return (annual - om) / crf(life)


rows = []
for label, ann in [("no cover avoided (status quo)", 0.0),
                   ("cover at 25% of the published anchor", 0.25 * COVER_ANN_ANCHOR),
                   ("cover at 50% of the published anchor", 0.50 * COVER_ANN_ANCHOR),
                   ("cover at the published anchor (LADWP potable-water quote)", COVER_ANN_ANCHOR)]:
    rows.append(dict(scenario=label,
                     avoided_annual_per_acre=round(ann),
                     fpv_usd_per_af=round(fpv_net_per_af(ann))))

targets = {}
for name, tgt in [("cheapest_credible_cover_shade_balls", 5_014),
                  ("reuse_high_end", REUSE_BAND[1]),
                  ("reuse_low_end", REUSE_BAND[0]),
                  ("free", 0.0)]:
    ann = breakeven_avoided(tgt)
    targets[name] = dict(target_usd_per_af=tgt,
                         avoided_annual_per_acre_required=round(ann),
                         implied_cover_capex_per_acre=round(capex_for_annual(ann)),
                         share_of_published_anchor=round(ann / COVER_ANN_ANCHOR, 2))

doc = {
    "meta": {
        "question": "If a reservoir is covered anyway for thermal or biodiversity reasons, FPV "
                    "substitutes for that cover and the avoided cost accrues to FPV. How much "
                    "would the avoided cover have to cost to change FPV's answer?",
        "raised_by": "Upmanu Lall, ASU, personal communication 2026-08-11",
        "basis": "Gross of power revenue, annualised at 7% WACC over each option's own life, "
                 "identical to analysis/evap_cover_comparison.py so the rows are comparable.",
        "evaporation_ft": EVAP_FT,
        "fpv_annual_cost_per_acre": round(FPV_ANN),
        "fpv_suppression": FPV_SUPP,
        "cover_suppression": COVER_SUPP,
        "published_cover_anchor_capex_per_acre": round(COVER_CAPEX_ANCHOR),
        "published_cover_anchor_annual_per_acre": round(COVER_ANN_ANCHOR),
        "caveats": [
            "The cover anchor is LADWP's published quote for a POTABLE-WATER floating cover on a "
            "175-acre reservoir. evap_cover_comparison.py already labels it a ceiling, not a "
            "price. A raw-water evaporation or thermal cover is a different and cheaper product, "
            "and no published cost for one at reservoir scale was found.",
            "Substituting FPV for a solid cover LOSES suppression: 75% against 90%. The trade is "
            "cheaper surface plus power revenue in exchange for less water saved per acre.",
            "The credit only applies to surface that would have been covered anyway. Covering 7% "
            "of Mead for power is not the same intervention, or the same placement, as covering "
            "it for temperature control, and nothing here establishes that the two coincide.",
            "No cover programme is funded or announced. This is a conditional, not a forecast.",
        ],
        "thermal_context": "Site-internal and already cited: as Powell fell, Glen Canyon released "
                           "warmer water, bass-suitable days rose from about 2 to about 41 a year, "
                           "and smallmouth bass reached the last humpback-chub stronghold. Cool-mix "
                           "flows work and are contested by hydropower.",
    },
    "scenarios": rows,
    "breakevens": targets,
}
(OUT / "cover_substitution.json").write_text(json.dumps(doc, indent=1))

print(f"FPV annualised {FPV_ANN:,.0f} $/acre-yr, {FPV_AF:.2f} AF/acre-yr -> {FPV_ANN/FPV_AF:,.0f} $/AF")
print(f"published cover anchor {COVER_ANN_ANCHOR:,.0f} $/acre-yr (capex {COVER_CAPEX_ANCHOR:,.0f}/acre)\n")
for r in rows:
    print(f"  {r['scenario']:<58} avoided {r['avoided_annual_per_acre']:>8,} -> "
          f"{r['fpv_usd_per_af']:>8,} $/AF")
print()
for k, v in targets.items():
    print(f"  to reach {v['target_usd_per_af']:>6,} $/AF, FPV must displace "
          f"{v['avoided_annual_per_acre_required']:>8,} $/acre-yr "
          f"({v['share_of_published_anchor']:.2f}x the anchor, capex "
          f"{v['implied_cover_capex_per_acre']:,}/acre)")
print("\nwrote outputs/cover_substitution.json")
