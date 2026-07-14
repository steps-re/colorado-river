#!/usr/bin/env python3
"""
Financial model for the Colorado River solution options: NPV, benefit-cost ratio (BCR), and
economic IRR per option and for the recommended package, with sensitivity on the value of water
and the discount rate. Monetizes water freed at avoided-marginal-supply value, plus per-option
co-benefits (hydropower, recreation/ecology). Flags which options carry a genuine private cash
flow (investable) vs. public-good returns. Grounded cost/yield priors from research/solutions_out.
Output: figures/fin_bcr_irr.png, outputs/finance_numbers.json
"""
import json, sys, os, numpy as np
from pathlib import Path
from scipy.optimize import brentq
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crstyle import apply, WATER, RUST, DEEP, SAND; apply()
ROOT=Path(__file__).resolve().parent.parent; FIG,OUT=ROOT/"figures",ROOT/"outputs"
for d in (FIG,OUT): d.mkdir(exist_ok=True)
T=30  # analysis horizon (years)

# name, capex$B, opex$B/yr, first-benefit yr, full-scale yr, water AF/yr (VERIFIED CU reduction),
#       co-benefit $B/yr, payment_program?, investable?
#
# ---- POST ADVERSARIAL-REVIEW DISCIPLINE (July 2026) ----
# The water column is NOT face-value diversion "savings." It is verified, additional, shepherded
# reduction in CONSUMPTIVE USE delivered to system storage, after three honest haircuts the review
# forced: (1) additionality — only savings that would not have happened anyway; (2) diversion-vs-CU —
# strip return flow a downstream right already uses; (3) a 25% uncertainty holdback on satellite-ET
# measured volumes. Tamarisk and cloud seeding carry ~zero bankable water (USGS: tamarisk salvage
# 0-1.5 AF/acre & inconsistent; WWMPP cloud seeding ~3%, statistically insignificant) -> habitat/
# research grants, not supply. Glen Canyon retrofit creates NO new water (temperature/hydropower/
# safety); its co-benefit is realistic hydropower + ecosystem value only. Aquifer recharge is net of
# ~75% recovery efficiency (clogging/subsurface loss) and is regional supply firming. O&M raised to
# reflect perpetual re-treatment, well rehab, pumping, and flux-tower ground-truthing.
O=[
 ("Measurement & accounting ledger",   0.10,0.10, 1, 3,        0, 0.00, False, True),   # enabler; no direct water (avoids double count)
 ("Consumptive-use conservation market",0.30,0.30, 1, 4,  500_000, 0.00, True,  True),  # verified CU retirement ~$600/AF, shepherded+protected
 ("Agricultural efficiency at scale",   3.75,0.11, 2, 8,  120_000, 0.00, False, True),  # only the genuine CU portion, not return flow
 ("Glen Canyon temp + outlet retrofit", 3.50,0.12, 4,10,        0, 0.35, False, False), # no water; hydropower reliability + ecosystem
 ("Cloud seeding + snow monitoring",    0.05,0.05, 1, 3,        0, 0.00, False, False), # ~zero bankable water -> research
 ("Phreatophyte / tamarisk control",    2.40,0.12, 1, 5,        0, 0.05, False, False), # ~zero bankable water -> habitat; perpetual O&M
 ("Dust-on-snow source control",       15.00,0.30, 3,10,        0, 0.10, False, False), # unverified -> grant/pilot only
 ("Desalination exchange",              4.50,0.35, 5,10,  180_000, 0.00, False, True),  # energy+brine disposal -> higher O&M
 ("Managed aquifer recharge",           8.00,0.35, 3,10,  400_000, 0.00, False, True),  # net of ~75% recovery; regional supply firming
 ("Tribal infrastructure + leasing",   28.50,0.20, 4,12,  600_000, 0.20, False, True),  # senior tribal water to beneficial use, w/ tribes as partners
]
PACKAGE={0,1,2,3,8}  # DEFENSIBLE core: ledger + verified CU conservation + genuine-CU ag efficiency +
                     # Glen Canyon (ecosystem/hydropower, grant) + aquifer recharge. Tamarisk & cloud
                     # seeding removed from bankable water (habitat/research grants); dust dropped.

def cashflow(o, wval):
    capex,opex,fb,fs,waf,cob=o[1],o[2],o[3],o[4],o[5],o[6]
    cf=np.zeros(T+1)
    for y in range(1,fs+1): cf[y]-=capex/fs                 # capex spread over build
    for y in range(fb,T+1): cf[y]-=opex                     # O&M once operational
    full_ben=waf*wval/1e9 + cob                             # $B/yr at full scale
    for y in range(fb,T+1):
        ramp=min(1.0,(y-fb+1)/max(1,(fs-fb+1)))
        cf[y]+=full_ben*ramp
    return cf
def npv(cf,r): return sum(cf[y]/(1+r)**y for y in range(len(cf)))
def irr(cf):
    if not (min(cf)<0<max(cf)): return None
    try: return float(brentq(lambda r: npv(cf,r), -0.9, 10))
    except Exception: return None
def bcr(o,wval,r):
    capex,opex,fb,fs,waf,cob=o[1],o[2],o[3],o[4],o[5],o[6]
    pvc=sum((capex/fs)/(1+r)**y for y in range(1,fs+1))+sum(opex/(1+r)**y for y in range(fb,T+1))
    pvb=0
    for y in range(fb,T+1):
        ramp=min(1.0,(y-fb+1)/max(1,(fs-fb+1)))
        pvb+=(waf*wval/1e9+cob)*ramp/(1+r)**y
    return pvb/pvc if pvc>0 else np.nan

WVAL={"low_800":800,"central_1500":1500,"high_2500":2500}; DISC={"d3":.03,"d5":.05,"d7":.07}
rows=[]
for o in O:
    cf=cashflow(o,1500); r=irr(cf)
    rows.append({"option":o[0],"capex_B":o[1],"investable":o[8],
      "irr_central":(round(r*100,1) if r is not None and r<10 else (">100" if r is not None else "n/a")),
      "npv_5pct_central_B":round(npv(cf,.05),1),
      "bcr":{k:round(bcr(o,v,.05),2) for k,v in WVAL.items()},
      "bcr_by_discount_central_wval":{k:round(bcr(o,1500,v),2) for k,v in DISC.items()}})
    print(f"[fin] {o[0][:34]:34s} IRR {rows[-1]['irr_central']:>6}%  NPV5 ${rows[-1]['npv_5pct_central_B']:>6}B  BCR@1500 {rows[-1]['bcr']['central_1500']}")

# package aggregate. NOTE: NPV/BCR here are on a NARROW water-value-only basis ($1,500/AF avoided
# supply + named co-benefits). Most of the package is public goods, so this basis is deliberately
# conservative and runs negative for the capital-heavy pieces -- that is the honest signal that they
# need grant/public finance, not equity. The societal case (avoided cost of inaction) lives in
# cost_of_inaction.py. For a corporate replenishment funder (e.g. AWS) the decision metric is the
# levelized cost per VERIFIED acre-foot, computed below.
pcf=sum(cashflow(O[i],1500) for i in PACKAGE); pr=irr(pcf)
# gross-benefit / gross-cost BCR (real ratio, not the buggy net-year split)
def pv_ben_cost(i,r=.05):
    capex,opex,fb,fs,waf,cob=O[i][1],O[i][2],O[i][3],O[i][4],O[i][5],O[i][6]
    pvc=sum((capex/fs)/(1+r)**y for y in range(1,fs+1))+sum(opex/(1+r)**y for y in range(fb,T+1))
    pvb=sum((waf*1500/1e9+cob)*min(1.0,(y-fb+1)/max(1,(fs-fb+1)))/(1+r)**y for y in range(fb,T+1))
    return pvb,pvc
pvb=sum(pv_ben_cost(i)[0] for i in PACKAGE); pvc=sum(pv_ben_cost(i)[1] for i in PACKAGE)
water_afy=sum(O[i][5] for i in PACKAGE)
to_storage_afy=O[1][5]+O[2][5]           # conservation + ag efficiency = shepherded to storage
# levelized $/AF: PV of all costs over PV of all water delivered (both discounted, 5%)
pv_water=sum(sum(O[i][5]*min(1.0,(y-O[i][3]+1)/max(1,(O[i][4]-O[i][3]+1)))/(1.05)**y for y in range(O[i][3],T+1)) for i in PACKAGE)
lcoe_af=round(pvc*1e9/pv_water) if pv_water>0 else None
pkg={"options":[O[i][0] for i in PACKAGE],
     "total_capex_B":round(sum(O[i][1] for i in PACKAGE),1),
     "verified_water_afy":water_afy,"to_storage_afy":to_storage_afy,
     "npv_water_only_5pct_B":round(npv(pcf,.05),1),
     "irr_pct":(round(pr*100,1) if pr is not None and pr<10 else (">100" if pr is not None else "n/a")),
     "bcr_water_only_central":round(pvb/pvc,2),
     "levelized_cost_per_verified_af":lcoe_af}
print(f"[fin] PACKAGE: capex ${pkg['total_capex_B']}B  verified {water_afy:,} AF/yr ({to_storage_afy:,} to storage)  "
      f"water-only NPV5 ${pkg['npv_water_only_5pct_B']}B  BCR {pkg['bcr_water_only_central']}  ${lcoe_af}/verified-AF")

# figure: BCR (central) sorted, colored by investable
names=[r["option"].split(" (")[0] for r in rows]
bcrv=[r["bcr"]["central_1500"] for r in rows]; inv=[o[8] for o in O]
order=np.argsort(bcrv)
fig,ax=plt.subplots(figsize=(10,6))
ax.barh([names[i][:30] for i in order],[bcrv[i] for i in order],
        color=["#2C7A87" if inv[i] else "#B9885A" for i in order])
ax.axvline(1,color="#A8432B",ls="--",lw=1.3,label="break-even (BCR=1)")
for i,idx in enumerate(order):
    lbl=rows[idx]["irr_central"]; ax.text(bcrv[idx]+0.05,i,f"IRR {lbl}%",va="center",fontsize=7,color="#333")
ax.set_xlabel("Benefit-cost ratio (water @ $1,500/AF, 5% discount)")
ax.set_title("Colorado River solutions: benefit-cost ratio and IRR  (teal = privately investable)")
ax.legend(loc="lower right"); plt.tight_layout(); plt.savefig(FIG/"fin_bcr_irr.png",dpi=140); plt.close()

# ---- Financing structure (HONEST split: what is collectible revenue vs. what needs an assessment) ----
# The prior "coverage ratio" wrongly counted social water value as if it were collectible cash flow.
# Correct framing: revenue-backed options (leases/fees/water sales) self-fund; public-good options must be
# repaid by a beneficiary surcharge levied by a basin authority that does NOT yet exist.
def pmt(P,r,n): return P*r/(1-(1+r)**-n)
BASIN_CU_MAF=13.0
capex=pkg["total_capex_B"]
rev_capex=round(sum(O[i][1] for i in PACKAGE if O[i][8]),1)      # investable -> serviced by own revenue
assess_capex=round(capex-rev_capex,1)                            # public goods -> need an assessment
social_value=round(sum(O[i][5] for i in PACKAGE)/1e6*1.5 + sum(O[i][6] for i in PACKAGE),2)  # context only, NOT revenue
bond_fin={"package_capex_B":round(capex,1),"revenue_backed_capex_B":rev_capex,"assessment_backed_capex_B":assess_capex,
          "social_benefit_B_yr_context_only":social_value,"by_rate":{}}
for rate in (0.04,0.05,0.06):
    total_ds=pmt(capex,rate,30); assess_ds=pmt(assess_capex,rate,30)
    surcharge=assess_ds*1e9/(BASIN_CU_MAF*1e6)                   # $/AF on the ASSESSMENT portion only
    bond_fin["by_rate"][f"r{int(rate*100)}"]={"total_debt_service_B_yr":round(total_ds,2),
        "assessment_surcharge_per_af":round(surcharge),
        "social_benefit_to_debt_service_ratio":round(social_value/total_ds,2)}
b=bond_fin["by_rate"]["r5"]
print(f"[bond] capex ${capex:.0f}B = revenue-backed ${rev_capex}B (self-funding) + assessment ${assess_capex}B; "
      f"@5%/30yr assessment surcharge ${b['assessment_surcharge_per_af']}/AF; "
      f"social benefit/debt-service {b['social_benefit_to_debt_service_ratio']}x (context, not collectible)")

(OUT/"finance_numbers.json").write_text(json.dumps({"blue_bond":bond_fin,"blue_bond_assumptions":{
   "basin_consumptive_use_maf":BASIN_CU_MAF,"term_yr":30,
   "note":"revenue-backed = capex of options with a direct cash flow (water sales/leasing/fees), self-funding; "
          "assessment-backed = public-good options repaid by a per-AF surcharge that requires a basin authority with "
          "assessment power (does not yet exist). Social benefit is context only, not collectible revenue."},
   "assumptions":{"horizon_yr":T,
   "water_value_per_af":WVAL,"discount":DISC,"note":"water freed valued at avoided marginal supply; co-benefits per option; grounded cost priors"},
   "per_option":rows,"package":pkg},indent=2))
print("[done] wrote fin_bcr_irr.png + finance_numbers.json")
