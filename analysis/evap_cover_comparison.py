#!/usr/bin/env python3
"""If you only want the water, is floating PV the wrong tool? Cost per acre-foot, one basis.

The question (Mike's): FPV carries the capex of a power plant. If the objective is purely
evaporation suppression, cheaper covers must exist -- they just have no revenue, which is fine
if they save more water per dollar.

The answer is yes, but not the option a first pass suggests. A grounded research agent put
floating modular covers at $140,000/acre, which would have made them the cheapest high-suppression
option. LADWP's own published alternative quote for exactly that technology was $250M for their
175-acre reservoir, i.e. $1.43M/acre -- ten times higher, and the most expensive option here, not
the cheapest. Every capex figure below is therefore anchored to a real deployment or a real
published quote, not to an agent's estimate.

Everything is annualised at the same 7% WACC over its own service life, so a 10-year ball and a
25-year array are comparable. Undiscounted lifetime division (which the research agent used)
understates capital-heavy, long-lived options by roughly 3x.

Outputs: outputs/evap_cover_comparison.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"; OUT.mkdir(exist_ok=True)

WACC = 0.07
# Lake Mead's USGS eddy-covariance depth, read from the model rather than retyped. It was a
# literal 6.22 here, a second copy of a number that lives in fpv_coverage_explorer. A copy that
# nothing reconciles is the same defect as a hardcoded table: when the depth moves (USGS publish
# 2024-2025 within months) this file would have quietly kept the old one.
EVAP_FT = json.loads((OUT / "fpv_coverage_explorer.json").read_text())["Lake Mead"]["params"]["evap_ft"]
MW_PER_ACRE = 120.0 * 0.00404686 / 1000 * 1000   # 120 MW/km2 -> MW per acre = 0.4856


def crf(n):
    return WACC * (1 + WACC) ** n / ((1 + WACC) ** n - 1)


OPTIONS = [
    dict(
        name="Shade balls (hollow HDPE spheres)",
        capex_per_acre=34_500_000 / 175,      # VERIFIED: LADWP, 96M balls, $34.5M, 175 acres
        life=10, suppression=0.90, om_per_acre=0,
        basis="VERIFIED DEPLOYMENT: LADWP Los Angeles Reservoir 2015. 96 million balls at $0.36 "
              "each = $34.5M over 175 acres = $197,143/acre. 10-year life, minimal maintenance.",
        caveat="The project was for BROMATE CONTROL, not evaporation: sunlight reacting with "
               "naturally occurring bromide and chlorine forms a carcinogen. Evaporation was a "
               "side benefit that got the press. LADWP has since moved away from them. Scale is "
               "the killer: LA Reservoir is 175 acres and sheltered; Lake Mead is ~69,600 acres, "
               "400x larger, with heavy wind fetch, 100-ft level swings, boating and navigation, "
               "and quagga mussels. Covering Mead would take on the order of 38 billion balls.",
        verdict="Cheapest credible cover, but never demonstrated beyond a small sheltered "
                "drinking-water reservoir.",
    ),
    dict(
        name="Floating modular cover / geomembrane",
        capex_per_acre=250_000_000 / 175,     # VERIFIED: LADWP's own published alternative quote
        life=20, suppression=0.90, om_per_acre=2_000,
        basis="UPPER BOUND, and the weakest anchor in this table. LADWP priced a floating cover "
              "for the same 175-acre reservoir at $250M = $1.43M/acre, which is why they chose "
              "balls instead. But that quote is for a POTABLE-WATER cover: sealed, tensioned, "
              "food-grade, engineered to keep a treated drinking supply isolated. An evaporation "
              "cover on a raw-water reservoir is a different and cheaper product. Treat $1.43M/acre "
              "as a ceiling on this row, not as its price.",
        caveat="Two estimates for this row have now been wrong in opposite directions. A research "
               "agent put it at $140,000/acre, ten times too low. The verified quote is for a "
               "higher-specification product than the application needs, so it is too high. No "
               "published cost for a raw-water evaporation cover at reservoir scale was found. "
               "This row should be read as unresolved rather than as a measurement.",
        verdict="Real technology, cost genuinely uncertain. The published anchor prices a "
                "potable-water product and overstates what raw-water evaporation cover would cost.",
    ),
    dict(
        name="Floating cover, raw water (Australian verified)",
        capex_per_acre=25.0 * 4046.86 * 0.65,   # A$25/m2 midpoint of A$15-35, at 0.65 AUD/USD
        life=10, suppression=0.90,
        om_per_acre=0.005 * 25.0 * 4046.86 * 0.65,
        basis="VERIFIED, and the row this table said did not exist. University of Southern "
              "Queensland, 'Assessment of Evaporation Mitigation Technologies in Queensland', "
              "funded by the Queensland Government: continuous floating covers cost "
              "'$15/m2 to $35/m2 (May 2020 prices)', lifespan 5 to 10 years, repair and "
              "maintenance 'less than 0.5% of the installation cost', evaporative reduction "
              ">90% of the covered area. Midpoint A$25/m2 at 0.65 AUD/USD = $65,761/acre. "
              "Corroborated independently: EFI quotes HDPE floating cover material at "
              "$0.35-0.60/sq ft ($15,200-26,100/acre) and Spanish irrigation tenders run "
              "EUR 9-11.43/m2.",
        caveat="THE SCALE LIMIT IS THE REAL FINDING. The same assessment puts the effective "
               "upper size limit of floating continuous and modular covers at 5 hectares. Lake "
               "Mead is about 30,900 hectares, roughly 6,000x that. This is a real price for a "
               "real product that has never been deployed at anything like reservoir scale, and "
               "the short 5-to-10-year life is why: debris, weed growth and rainwater drainage "
               "under an impermeable sheet all worsen with area.",
        verdict="Cheaper per acre-foot than floating PV and far cheaper than the potable-water "
                "row below it, but bounded to storages three orders of magnitude smaller than "
                "the reservoirs in question.",
    ),
    dict(
        name="Floating PV (this model, baseline cost)",
        capex_per_acre=1.23e6 * MW_PER_ACRE,
        life=25, suppression=0.75, om_per_acre=25_000 * MW_PER_ACRE,
        basis="Our own model: $1.23/W at 120 MW/km2 = 0.486 MW/acre, $25k/MW-yr O&M.",
        caveat="Unlike every other option here it earns power revenue, which is netted "
               "separately below. Suppression is 75%, lower than a solid cover.",
        verdict="Only option with revenue. Still expensive per acre-foot.",
    ),
    dict(
        name="Floating PV (reviewers' harsh cost case)",
        capex_per_acre=2.50e6 * MW_PER_ACRE,
        life=25, suppression=0.75, om_per_acre=75_000 * MW_PER_ACRE,
        basis="Deep dynamic mooring in 300+ ft of water with 100-ft swings, plus quagga mussel "
              "fouling of floats, lines and anchors: $2.50/W and 3x O&M.",
        caveat="No commercial FPV has been moored in these conditions anywhere.",
        verdict="If the reviewers are right about mooring and fouling, FPV is the worst option.",
    ),
    dict(
        name="Chemical monolayer (cetyl alcohol film)",
        capex_per_acre=200, life=1, suppression=0.20, om_per_acre=0,
        basis="ESTIMATE, not verified against a large deployment.",
        caveat="Wind disperses the film continuously so it needs constant reapplication, and "
               "field suppression is far below laboratory values. Repeatedly trialled and "
               "repeatedly abandoned on open reservoirs.",
        verdict="Cheapest per acre-foot on paper and the least likely to work at scale.",
    ),
]


def main():
    rows = []
    for o in OPTIONS:
        ann = o["capex_per_acre"] * crf(o["life"]) + o["om_per_acre"]
        af = EVAP_FT * o["suppression"]
        rows.append(dict(
            name=o["name"],
            capex_per_acre=round(o["capex_per_acre"]),
            life_yr=o["life"], suppression_pct=round(o["suppression"] * 100),
            annual_cost_per_acre=round(ann),
            af_per_acre_yr=round(af, 2),
            usd_per_af=round(ann / af),
            basis=o["basis"], caveat=o["caveat"], verdict=o["verdict"],
        ))
    rows.sort(key=lambda r: r["usd_per_af"])

    out = dict(
        method=[
            f"Annualised at {WACC:.0%} WACC over each option's own service life, so a 10-year "
            "shade ball and a 25-year array are directly comparable.",
            f"Evaporation {EVAP_FT} ft/yr (Lake Mead, USGS direct eddy-covariance flux).",
            "Cost per acre-foot ignores revenue. Only FPV has any; see the FPV net figure.",
            "Undiscounted lifetime division, which a research agent used, understates "
            "capital-heavy long-lived options by roughly 3x. Not used here.",
        ],
        benchmarks={
            "pay a farmer to conserve": "325-700 $/AF",
            "desalination": "2500-3500 $/AF",
            "FPV net of power sales (our hourly model, best-value sizing at Lake Mead)": "~10,900 $/AF",
        },
        options=rows,
    )
    (OUT / "evap_cover_comparison.json").write_text(json.dumps(out, indent=1))

    print(f"{'option':46} {'$/acre':>10} {'life':>5} {'supp':>5} {'$/ac-yr':>9} {'$/AF':>8}")
    for r in rows:
        print(f"{r['name'][:46]:46} {r['capex_per_acre']:>10,} {r['life_yr']:>5} "
              f"{r['suppression_pct']:>4}% {r['annual_cost_per_acre']:>9,} {r['usd_per_af']:>8,}")
    print("\nBenchmarks: farmer conservation $325-700/AF | desal $2,500-3,500/AF")
    print("WROTE outputs/evap_cover_comparison.json")


if __name__ == "__main__":
    main()
