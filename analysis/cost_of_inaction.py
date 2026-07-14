#!/usr/bin/env python3
"""
Cost of inaction / avoided-cost calculation — the insurance case for the package.
Assembles the value-at-risk on the Colorado River from grounded figures (research/deepen_out),
and compares it to the package's annual debt service. Framing is conservative: these are
gross economic-activity and asset figures with wide ranges, so the package is presented as
insurance (cost vs. damages averted), not a claim of net benefit equal to the activity at risk.
Output: figures/inaction_var.png, outputs/inaction_numbers.json
"""
import json, numpy as np
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import sys as _sys, os as _os; _sys.path.insert(0,_os.path.dirname(_os.path.abspath(__file__)))
from crstyle import apply as _ap; _ap()
ROOT=Path(__file__).resolve().parent.parent; FIG,OUT=ROOT/"figures",ROOT/"outputs"
for d in (FIG,OUT): d.mkdir(exist_ok=True)

# Value-at-risk (annual, $B) — grounded figures with sources in research/deepen_out
VAR={
 "Glen Canyon hydropower value":              (0.15, 0.30),      # ~$153M/yr market value (adversarial-corrected)
 "Agricultural output at risk (basin)":       (5.0, 5.0),        # ~$5B/yr basin ag production
 "Recreation / tourism (Grand Canyon etc.)":  (1.0, 1.1),        # ~$1.1B/yr Grand Canyon output
}
# macro and natural-capital figures kept separate (broader, not summed into the annual stack)
MACRO_10PCT_SHORTFALL_B = 143.0     # $ activity lost in one 10%-shortfall year (+1.6M jobs)
MACRO_JOBS_M = 1.6
NATCAP_ANNUAL_B = (69.2, 496.4)     # Earth Economics annual ecosystem-service value
REGION_ECONOMY_T = 1.4; PEOPLE_M = 40

# Package cost (honest): capital $15.65B, debt service on a 30-yr bond @5%
BOND_B=15.65
def pmt(P,r,n): return P*r/(1-(1+r)**-n)
DEBT_SVC=pmt(BOND_B,0.05,30)
PKG_FREED_MAF=1.02
TOTAL_SUPPLY_MAF=14.0

annual_var_low=sum(v[0] for v in VAR.values()); annual_var_high=sum(v[1] for v in VAR.values())
# per-MAF activity-at-risk implied by the 10%-shortfall macro figure
per_maf_activity_B = MACRO_10PCT_SHORTFALL_B/(0.10*TOTAL_SUPPLY_MAF)   # $B activity per MAF of shortfall
pkg_activity_protected_B = PKG_FREED_MAF*per_maf_activity_B            # gross activity the freed water buffers

insurance_ratio_annual = DEBT_SVC/annual_var_high                     # cost vs directly-attributable exposure
insurance_ratio_macro  = DEBT_SVC/MACRO_10PCT_SHORTFALL_B             # cost vs one severe-year activity

print(f"[inaction] directly-attributable annual VaR ${annual_var_low:.1f}-{annual_var_high:.1f}B/yr")
print(f"[inaction] one 10%-shortfall year = ${MACRO_10PCT_SHORTFALL_B}B activity + {MACRO_JOBS_M}M jobs")
print(f"[inaction] implied ~${per_maf_activity_B:.0f}B activity per MAF of shortfall -> package buffers ~${pkg_activity_protected_B:.0f}B")
print(f"[inaction] package debt service ${DEBT_SVC:.2f}B/yr = {insurance_ratio_annual*100:.0f}% of annual VaR, {insurance_ratio_macro*100:.1f}% of a severe-year")

# figure: annual VaR stack + debt-service line, with macro context
fig,ax=plt.subplots(figsize=(10,5.2))
labels=list(VAR.keys()); lows=[VAR[k][0] for k in labels]; highs=[VAR[k][1] for k in labels]
y=np.arange(len(labels))
ax.barh(y,highs,color="#A8432B",alpha=.35,label="high estimate")
ax.barh(y,lows,color="#A8432B",label="low estimate")
ax.axvline(DEBT_SVC,color="#2C7A87",lw=2.5,label=f"package debt service ${DEBT_SVC:.1f}B/yr")
ax.set_yticks(y,labels,fontsize=9); ax.set_xlabel("Annual value-at-risk ($B/yr)")
ax.set_title("The cost of inaction dwarfs the cost of the fix")
ax.legend(loc="lower right",fontsize=8)
ax.text(0.98,0.06,f"one 10%-shortfall year: ${MACRO_10PCT_SHORTFALL_B:.0f}B activity + {MACRO_JOBS_M}M jobs\n"
        f"basin natural capital: ${NATCAP_ANNUAL_B[0]:.0f}-{NATCAP_ANNUAL_B[1]:.0f}B/yr",
        transform=ax.transAxes,ha="right",va="bottom",fontsize=7.5,color="#555",
        bbox=dict(boxstyle="round",fc="#F4F0E7",ec="#C6BBA4"))
plt.tight_layout(); plt.savefig(FIG/"inaction_var.png",dpi=140); plt.close()

(OUT/"inaction_numbers.json").write_text(json.dumps({
  "value_at_risk_annual_B":{k:{"low":v[0],"high":v[1]} for k,v in VAR.items()},
  "directly_attributable_annual_var_B":[round(annual_var_low,1),round(annual_var_high,1)],
  "severe_year_activity_B":MACRO_10PCT_SHORTFALL_B,"severe_year_jobs_M":MACRO_JOBS_M,
  "activity_per_maf_shortfall_B":round(per_maf_activity_B,0),
  "package_activity_buffered_B":round(pkg_activity_protected_B,0),
  "natural_capital_annual_B":list(NATCAP_ANNUAL_B),
  "package_debt_service_B_yr":round(DEBT_SVC,2),
  "insurance_ratio_vs_annual_var":round(insurance_ratio_annual,3),
  "insurance_ratio_vs_severe_year":round(insurance_ratio_macro,4),
  "note":"gross economic-activity and asset figures with wide ranges; framed as insurance (cost vs damages averted), not net benefit"},indent=2))
print("[done] wrote inaction_var.png + inaction_numbers.json")
