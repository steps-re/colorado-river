#!/usr/bin/env python3
"""If a reservoir gets covered anyway, what is floating PV actually competing against?

Raised by Upmanu Lall (ASU), personal communication 11 Aug 2026: reservoir covers are being
considered for TEMPERATURE and biodiversity management, not for evaporation. If a cover goes in for
that reason, FPV substitutes for a cover that was going to be bought regardless, and the avoided
cost belongs on FPV's side of the ledger.

The premise is live on this river: as Powell fell, Glen Canyon released warmer water, bass-suitable
days rose from about 2 a year to about 41, and smallmouth bass reached the last humpback-chub
stronghold. Cool-mix flows work and are contested by hydropower.

WHAT CHANGED, 12 Aug 2026. The first version of this analysis had only one cover price: LADWP's
$1.43M/acre, which is a sealed, food-grade POTABLE-WATER product and was flagged in
evap_cover_comparison.py as a ceiling rather than a price. Against that ceiling the substitution
credit looked enormous, and this file reported that FPV's water became free at 46% of it. A global
price scan found the raw-water figures that were previously "not found", and they are 8 to 22
times lower. On verified prices the credit is worth 9 to 26% off FPV's cost per acre-foot, not an
order of magnitude, and FPV does not approach the reuse or desalination band. That conclusion is
reversed from the version published on 11 Aug.

The disqualifier is not price and not size. It is LEVEL CHANGE. The same report states that covers
"must be tethered to avoid beaching and obstructing spillways" and "are not suitable for storages
experiencing large water level fluctuations". Mead sits 189 ft below full pool and Powell 179 ft,
the most extreme fluctuation case in the basin. That is a direct quotation rather than a modelling
assumption, and it rules the technology out here on its own.

HOW FAR TO TRUST THE SOURCE. It is a July 2020 final report by named academics (Schmidt, Pittaway
and Scobie) at the Centre for Agricultural Engineering, University of Southern Queensland, funded by
the Queensland Government, and Pittaway published a peer-reviewed review of the same subject in 2023.
But it is not itself peer reviewed, its prices are May 2020 Australian and are not inflated here, its
scope is farm dams (96% of the 243,000 storages it surveys are under 2 ha), it contradicts itself on
service life (5-10 vs 15 vs 35 years) and on size limit (2 ha vs 5 ha), and it misstates the Los
Angeles Reservoir as 175 ha when it is 175 acres. Its direction is consistent across every reading;
its precision is not, which is why this file carries four readings instead of one.

Output: outputs/cover_substitution.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
WACC = 0.07
M2_PER_ACRE = 4046.86
HA_PER_ACRE = 0.404686
MW_PER_ACRE = 120.0 * 0.00404686
EVAP_FT = json.loads((OUT / "fpv_coverage_explorer.json").read_text())["Lake Mead"]["params"]["evap_ft"]
REUSE_BAND = (2_500, 3_500)

# VERIFIED, University of Southern Queensland "Assessment of Evaporation Mitigation Technologies in
# Queensland", funded by the Queensland Government. Verbatim: continuous floating covers "have a
# high capital cost of $15/m2 to $35/m2 (May 2020 prices)" and are "best suited to storages less
# than 5ha in area"; "The capital cost of floating covers is high, with a lifespan of 5 to 10
# years"; "Repair and maintenance costs are likely to be less than 0.5% of the installation cost".
# The report gives THREE readings and they do not agree. Executive summary A$15-35/m2; supplier
# detail "0.75mm membrane with a 15 year life ... installed cost of $23/m2" for agriculture and
# "1,14mm membrane with a 35 year life and an installed cost of $75/m2" for industrial duty. A
# reservoir of this size is the industrial case, so that is the central figure and the others
# bracket it. Across all three the answer lands between $1,000 and $2,900 per acre-foot.
COVER_READINGS = [(15.0, 10, "executive summary, low"),
                  (35.0, 10, "executive summary, high"),
                  (23.0, 15, "supplier, agricultural spec, installed"),
                  (75.0, 35, "supplier, INDUSTRIAL spec, installed — the relevant duty")]
AUD_USD = 0.65                     # stated, not silently applied; May 2020 and 2026 are both ~0.65
COVER_OM_FRACTION = 0.005          # of installed cost per year
COVER_SIZE_LIMIT_HA = 2   # "generally limited to small storages less than 2 ha"; the report also says 5 ha elsewhere
PRICE_VINTAGE = "May 2020 AUD, not inflated to 2026; the real figure today is higher"

# The old anchor, retained ONLY as a labelled ceiling so the contrast stays visible.
LADWP_CAPEX_PER_ACRE = 250_000_000 / 175
LADWP_LIFE = 20


def crf(n):
    return WACC * (1 + WACC) ** n / ((1 + WACC) ** n - 1)


FPV_ANN = 1.23e6 * MW_PER_ACRE * crf(25) + 25_000 * MW_PER_ACRE
FPV_SUPP, COVER_SUPP = 0.75, 0.90
FPV_AF = EVAP_FT * FPV_SUPP


def usd_per_acre(aud_m2):
    return aud_m2 * M2_PER_ACRE * AUD_USD


def annualised(capex_per_acre, life, om_fraction=COVER_OM_FRACTION):
    return capex_per_acre * crf(life) + capex_per_acre * om_fraction


def fpv_net_per_af(avoided_annual_per_acre):
    return (FPV_ANN - avoided_annual_per_acre) / FPV_AF


# Verified raw-water scenarios: the cheap/long-life corner and the dear/short-life corner bracket
# the range the assessment actually reports.
rows = [dict(scenario="no cover avoided (status quo)", basis="—",
             avoided_annual_per_acre=0, fpv_usd_per_af=round(fpv_net_per_af(0)))]
for aud, life, label in COVER_READINGS:
    capex = usd_per_acre(aud)
    ann = annualised(capex, life)
    rows.append(dict(
        scenario=f"raw-water floating cover: {label}",
        basis=f"A${aud:g}/m2 = ${round(capex):,}/acre, {life}-yr life",
        avoided_annual_per_acre=round(ann),
        fpv_usd_per_af=round(fpv_net_per_af(ann))))
ladwp_ann = LADWP_CAPEX_PER_ACRE * crf(LADWP_LIFE) + 2_000
rows.append(dict(scenario="POTABLE-WATER cover (LADWP quote) — a ceiling, not a comparable product",
                 basis=f"${round(LADWP_CAPEX_PER_ACRE):,}/acre, {LADWP_LIFE}-yr life",
                 avoided_annual_per_acre=round(ladwp_ann),
                 fpv_usd_per_af=round(fpv_net_per_af(ladwp_ann))))

verified = [r for r in rows if r["scenario"].startswith("raw-water")]
best, worst = min(verified, key=lambda r: r["fpv_usd_per_af"]), max(verified, key=lambda r: r["fpv_usd_per_af"])
base = rows[0]["fpv_usd_per_af"]

doc = {
    "meta": {
        "question": "If a reservoir is covered anyway for thermal or biodiversity reasons, FPV "
                    "substitutes for that cover and the avoided cost accrues to FPV. On VERIFIED "
                    "raw-water cover prices, how much does that actually change FPV's answer?",
        "raised_by": "Upmanu Lall, ASU, personal communication 2026-08-11",
        "answer": f"Between {round(100*(1-worst['fpv_usd_per_af']/base))}% and "
                  f"{round(100*(1-best['fpv_usd_per_af']/base))}% off FPV's cost per acre-foot. "
                  f"It does not reach the reuse or desalination band at any verified cover price.",
        "reversal": "The 11 Aug version of this analysis used only LADWP's potable-water quote and "
                    "reported that FPV's water became free at 46% of it. Verified raw-water prices "
                    "are 15-36x lower and the credit is worth tens of per cent, not an order of "
                    "magnitude. That earlier conclusion is withdrawn.",
        "source": "University of Southern Queensland, 'Assessment of Evaporation Mitigation "
                  "Technologies in Queensland', funded by the Queensland Government. Continuous "
                  "floating covers A$15-35/m2 (May 2020), lifespan 5-10 years, repair and "
                  "maintenance under 0.5% of installed cost per year, evaporative reduction >90% "
                  "of the covered area.",
        "source_url": "https://evapadvisor.com/assets/reports/Assessment_of_Evaporation_Mitigation_Technologies_in_Queensland.pdf",
        "corroboration": "Independently, EFI (US manufacturer) quotes HDPE floating cover material "
                         "at $0.35-0.60/sq ft = $15,200-26,100/acre, and Spanish irrigation-"
                         "reservoir tenders run EUR 9-11.43/m2. Both sit inside the Australian band.",
        "price_vintage": PRICE_VINTAGE,
        "aud_usd": AUD_USD,
        "scale_limit_ha": COVER_SIZE_LIMIT_HA,
        "disqualifier": "Not price and not size: the report states covers 'are not suitable for "
                        "storages experiencing large water level fluctuations'. Mead is 189 ft "
                        "below full pool and Powell 179 ft. Direct quotation, not an assumption.",
        "source_reliability": "July 2020, not peer reviewed, farm-dam scope, prices not inflated. "
                              "Self-inconsistent on life (5-10 vs 15 vs 35 yr) and size limit "
                              "(2 vs 5 ha), and misstates LA Reservoir as 175 ha when it is 175 "
                              "acres. Direction consistent, precision not.",
        "scale_limit_note": f"The same assessment puts the effective upper size limit of floating "
                            f"continuous and modular covers at {COVER_SIZE_LIMIT_HA} ha. Lake Mead "
                            f"is about 30,900 ha, roughly 6,000x that. No floating cover has been "
                            f"demonstrated at anything approaching reservoir scale, so the "
                            f"counterfactual this credit depends on is itself unestablished here.",
        "fpv_annual_cost_per_acre": round(FPV_ANN),
        "fpv_suppression": FPV_SUPP,
        "cover_suppression": COVER_SUPP,
        "caveats": [
            "Substituting FPV for a solid cover LOSES suppression, 75% against 90%.",
            "The credit applies only to surface that would have been covered anyway, and covering "
            "part of a reservoir for power need not be the same placement as covering it for "
            "temperature control.",
            "No cover programme on these reservoirs is funded or announced.",
            "Prices are May 2020 Australian, converted at 0.65 and not inflated. Today's figure is "
            "higher, which would increase the credit.",
        ],
    },
    "scenarios": rows,
}
(OUT / "cover_substitution.json").write_text(json.dumps(doc, indent=1))

print(f"FPV annualised {FPV_ANN:,.0f} $/acre-yr over {FPV_AF:.2f} AF/acre-yr -> {base:,} $/AF\n")
for r in rows:
    print(f"  {r['scenario'][:62]:<62} avoided {r['avoided_annual_per_acre']:>9,} -> "
          f"{r['fpv_usd_per_af']:>9,} $/AF")
print(f"\nverified raw-water credit: {round(100*(1-worst['fpv_usd_per_af']/base))}% to "
      f"{round(100*(1-best['fpv_usd_per_af']/base))}% off. Reuse band is {REUSE_BAND[0]:,}-{REUSE_BAND[1]:,} $/AF.")
print(f"scale limit {COVER_SIZE_LIMIT_HA} ha vs Mead ~30,900 ha")
print("wrote outputs/cover_substitution.json")
