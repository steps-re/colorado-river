#!/usr/bin/env python3
"""
Scenario & stress calculations for the solution portfolio and the blue-bond structure.
Adds: (1) break-even water value per option (the $/AF at which each pays for itself),
(2) package NPV across water-value x discount, (3) blue-bond coverage & surcharge across
bond rate x water value, incl. the scarcity paradox (worse hydrology raises water value ->
raises coverage), and (4) a robustness ledger (which options stay BCR>1 across the range).
Output: figures/scn_breakeven.png, figures/scn_bond_heatmap.png, outputs/scenario_numbers.json
"""
import json, numpy as np
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import sys as _sys, os as _os; _sys.path.insert(0,_os.path.dirname(_os.path.abspath(__file__)))
from crstyle import apply as _ap; _ap()
ROOT=Path(__file__).resolve().parent.parent; FIG,OUT=ROOT/"figures",ROOT/"outputs"
for d in (FIG,OUT): d.mkdir(exist_ok=True)
T=30
# name, capex$B, opex$B/yr, first-yr, full-yr, water AF/yr, cobenefit$B/yr
# ALIGNED WITH solutions_finance.py HONEST NUMBERS (July 2026 adversarial review)
O=[
 ("Measurement & accounting ledger",0.10,0.10,1,3,0,0.00),
 ("Consumptive-use conservation market",0.30,0.30,1,4,500_000,0.00),
 ("Agricultural efficiency at scale",3.75,0.11,2,8,120_000,0.00),
 ("Glen Canyon temp + outlet retrofit",3.50,0.12,4,10,0,0.35),
 ("Cloud seeding + snow monitoring",0.05,0.05,1,3,0,0.00),
 ("Phreatophyte / tamarisk control",2.40,0.12,1,5,0,0.05),
 ("Dust-on-snow source control",15.00,0.30,3,10,0,0.10),
 ("Desalination exchange",4.50,0.35,5,10,180_000,0.00),
 ("Managed aquifer recharge",8.00,0.35,3,10,400_000,0.00),
 ("Tribal infrastructure + leasing",28.50,0.20,4,12,600_000,0.20),
]
PACKAGE={0,1,2,3,8}
def pvc(o,r):
    capex,opex,fb,fs=o[1],o[2],o[3],o[4]
    return sum((capex/fs)/(1+r)**y for y in range(1,fs+1))+sum(opex/(1+r)**y for y in range(fb,T+1))
def pv_water_factor(o,r):   # PV of 1$/AF*AF stream (i.e., per $1/AF water value) in $B units
    fb,fs,waf=o[3],o[4],o[5]
    return sum(min(1.0,(y-fb+1)/max(1,(fs-fb+1)))*(waf/1e9)/(1+r)**y for y in range(fb,T+1))
def pv_cobenefit(o,r):
    fb,fs,cob=o[3],o[4],o[6]
    return sum(min(1.0,(y-fb+1)/max(1,(fs-fb+1)))*cob/(1+r)**y for y in range(fb,T+1))

# ---- (1) break-even water value per option (BCR=1) at 5% ----
be={}
for o in O:
    c=pvc(o,.05); wf=pv_water_factor(o,.05); cb=pv_cobenefit(o,.05)
    if wf<=0: be[o[0]]=None if cb<c else 0     # no water; worth it iff cobenefit covers
    else: be[o[0]]=max(0.0,(c-cb)/wf)          # $/AF at which it breaks even
print("[breakeven $/AF at 5%]")
for k,v in be.items(): print(f"   {k:24s} {'covered by co-benefits' if v==0 else ('n/a' if v is None else f'${v:,.0f}/AF')}")

# ---- (2) package NPV across water value x discount ----
def npv_pkg(wval,r):
    tot=0
    for i in PACKAGE:
        o=O[i]; tot+= pv_water_factor(o,r)*wval + pv_cobenefit(o,r) - pvc(o,r)
    return tot
grid={f"wv{w}":{f"d{int(d*100)}":round(npv_pkg(w,d),1) for d in (.03,.05,.07)} for w in (800,1500,2500)}
print("[package NPV $B]  (rows=water value, cols=discount)")
for w in (800,1500,2500): print(f"   ${w}/AF: "+" ".join(f"d{int(d*100)}={npv_pkg(w,d):+.0f}" for d in (.03,.05,.07)))

# ---- (3) blue-bond coverage & surcharge across rate x water value ----
def pmt(P,r,n): return P*r/(1-(1+r)**-n)
BOND=round(sum(O[i][1] for i in PACKAGE),1); BASIN=13.0; FREED=1.02; COB=sum(O[i][6] for i in PACKAGE)
rates=[.04,.05,.06,.07]; wvals=[800,1500,2500]
cover=np.zeros((len(wvals),len(rates))); surch=np.zeros(len(rates))
for j,r in enumerate(rates):
    ds=pmt(BOND,r,30); surch[j]=ds*1e9/(BASIN*1e6)
    for i,w in enumerate(wvals):
        cover[i,j]=(FREED*w/1000+COB)/ds
print(f"[blue bond] ${BOND}B, freed {FREED:.2f} MAF")
for j,r in enumerate(rates): print(f"   rate {int(r*100)}%: surcharge ${surch[j]:.0f}/AF, coverage "+" ".join(f"@${w}={cover[i,j]:.1f}x" for i,w in enumerate(wvals)))

# ---- (4) robustness: which options BCR>1 across $800-2500 ----
def bcr(o,wval,r):
    c=pvc(o,r); return (pv_water_factor(o,r)*wval+pv_cobenefit(o,r))/c if c>0 else np.nan
robust={o[0]:{"bcr_800":round(bcr(o,800,.05),2),"bcr_2500":round(bcr(o,2500,.05),2),
              "robust_positive":bool(bcr(o,800,.05)>=1)} for o in O}

# figure 1: break-even water value
names=[o[0] for o in O]; vals=[ (be[n] if be[n] not in (None,0) else 0) for n in names]
fig,ax=plt.subplots(figsize=(10,6))
order=np.argsort(vals)
cols=["#2C7A87" if (be[names[i]]==0) else ("#B9885A" if (vals[i]<=1500) else "#A8432B") for i in order]
ax.barh([names[i] for i in order],[max(vals[i],20) for i in order],color=cols)
for x0,lab in [(362,"forage $362"),(1500,"central $1,500"),(2500,"desal $2,500")]:
    ax.axvline(x0,ls="--",lw=1,color="#555"); ax.text(x0,len(names)-0.4,f" {lab}",rotation=90,va="top",fontsize=7,color="#555")
ax.set_xlabel("Break-even water value ($/acre-foot)  — teal = already covered by co-benefits")
ax.set_title("What water has to be worth for each option to pay for itself")
plt.tight_layout(); plt.savefig(FIG/"scn_breakeven.png",dpi=140); plt.close()
# figure 2: bond coverage heatmap
fig,ax=plt.subplots(figsize=(7.5,4.5))
im=ax.imshow(cover,cmap="YlGnBu",aspect="auto",vmin=1,vmax=8)
ax.set_xticks(range(len(rates)),[f"{int(r*100)}%" for r in rates]); ax.set_yticks(range(len(wvals)),[f"${w}/AF" for w in wvals])
for i in range(len(wvals)):
    for j in range(len(rates)): ax.text(j,i,f"{cover[i,j]:.1f}x",ha="center",va="center",fontsize=9,color="#12343b")
ax.set_xlabel("bond interest rate"); ax.set_ylabel("value of freed water")
ax.set_title(f"Social benefit / debt service (${BOND}B) — context, NOT collectible coverage")
plt.colorbar(im,label="social benefit / debt service (not collectible)"); plt.tight_layout()
plt.savefig(FIG/"scn_bond_heatmap.png",dpi=140); plt.close()

(OUT/"scenario_numbers.json").write_text(json.dumps({
  "breakeven_water_value_per_af":{k:(None if v is None else round(v)) for k,v in be.items()},
  "package_npv_grid_B":grid,
  "blue_bond":{"bond_B":BOND,"freed_maf":round(FREED,2),
     "by_rate":{f"r{int(r*100)}":{"surcharge_per_af":round(surch[j]),
        "coverage":{f"wv{w}":round(cover[i,j],2) for i,w in enumerate(wvals)}} for j,r in enumerate(rates)}},
  "robustness":robust},indent=2))
print("[done] wrote scn_breakeven.png, scn_bond_heatmap.png, scenario_numbers.json")
