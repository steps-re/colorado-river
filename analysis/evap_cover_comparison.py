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
        caveat="SUPERSEDED as a proxy for raw-water cover, and retained only as the potable-water "
               "ceiling it actually is. This row previously carried the note that no published "
               "cost for a raw-water cover could be found; a global scan on 2026-08-12 found "
               "several, and they sit 8-22x below this quote. Use the industrial-spec row above "
               "for raw-water duty. Two earlier estimates for this row were wrong in opposite "
               "directions: a research agent put it at $140,000/acre, ten times too low, and this "
               "quote prices a sealed food-grade product the application does not need.",
        verdict="Real technology, cost genuinely uncertain. The published anchor prices a "
                "potable-water product and overstates what raw-water evaporation cover would cost.",
    ),
    dict(
        name="Floating cover, raw water (industrial spec)",
        capex_per_acre=75.0 * 1.33 * 4046.86 * 0.65,   # A$75/m2 installed x1.33 escalation to 2026
        life=35, suppression=0.90,
        om_per_acre=0.005 * 75.0 * 1.33 * 4046.86 * 0.65,
        basis="University of Southern Queensland / Queensland Government, 'Assessment of "
              "Evaporation Mitigation Technologies in Queensland' (Schmidt, Pittaway & Scobie, "
              "July 2020). The INDUSTRIAL specification is the relevant duty for a reservoir of "
              "this size: '1,14mm membrane with a 35 year life and an installed cost of $75/m2'. "
              "The agricultural spec is A$23/m2 installed over 15 years and the executive summary "
              "gives A$15-35/m2, which bracket $1,000-2,900/AF across the report's own readings. "
              "May 2020 Australian prices at 0.65 AUD/USD, ESCALATED x1.33 to 2026: Australian "
              "construction input PPI and global HDPE resin both up about 40% since mid-2020, US "
              "construction cost indices up 25-27%, weighted 50/50 between polymer and "
              "installation. A China-supplied cover is far cheaper: BPM Geoliner list "
              "floating-cover-grade LLDPE/HDPE at USD 1.40-3.90/m2 material, which at this "
              "report's own 3.1x material-to-installed ratio implies USD 4.30-12.00/m2 installed. "
              "The true figure is bounded by a high-labour Australian market above and a Chinese "
              "supply chain below, and that spread is roughly 5x.",
        caveat="THE DISQUALIFIER IS LEVEL CHANGE, NOT COST. The same report: covers 'must be "
               "tethered to avoid beaching and obstructing spillways' and 'are not suitable for "
               "storages experiencing large water level fluctuations'. Mead sits 189 ft below "
               "full pool and Powell 179 ft, which is the most extreme fluctuation case in the "
               "basin. Deployment is also in rafts 'covering up to 1ha each', and floating covers "
               "are described elsewhere in the same report as 'generally limited to small storages "
               "less than 2 ha'. The source is internally inconsistent on size limit (2 vs 5 ha) "
               "and service life (5-10 vs 15 vs 35 years), and it misstates LA Reservoir as 175 ha "
               "when it is 175 acres, so treat its precision with care even where its direction is "
               "clear. Independently, a scan for Chinese reservoir-cover deployments found NO "
               "large-scale commercial installation, only pond and evaporator field tests, which "
               "corroborates the scale objection from the country that manufactures most of the "
               "world's geomembrane. Those Chinese field tests also measured 51-75% suppression "
               "for solid and modular covers and 14-60% for spheres, against the 90% assumed "
               "here, so this row's water yield may be optimistic.",
        verdict="Far cheaper per acre-foot than floating PV and than the potable-water row, and "
                "ruled out here by water-level fluctuation rather than by price.",
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
        capex_per_acre=200, life=1, suppression=0.09, om_per_acre=0,
        basis="Suppression is now the MEASURED field result, not an estimate. Lake Hefner, "
              "Oklahoma, 1958: a 1,011-hectare hexadecanol/octadecanol trial, the largest "
              "evaporation-suppression experiment ever run, achieved 9% reduction over 88 days. "
              "This row previously assumed 20%, which was more than double what the only "
              "large-scale field test delivered. Capex remains an estimate.",
        caveat="It failed on WIND, which is the variable Lake Mead has most of. Successful film "
               "application had an upper wind limit of 13 mph, above which the film was driven to "
               "the lee shore, and replacing it took 6.5-8 times the application rate needed on an "
               "experimental pond. Modern practice restricts monolayers to storages under about "
               "100 ha. Repeatedly trialled and repeatedly abandoned on open water.",
        verdict="Cheapest per acre-foot on paper even at the measured 9%, and the one option here "
                "with a large-scale field trial that unambiguously failed.",
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
