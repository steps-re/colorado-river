#!/usr/bin/env python3
"""
Colorado River solution-portfolio model. Takes the 13 grounded-and-costed options and:
  (1) levelizes cost, ranks benefit-per-dollar,
  (2) optimizes the max-benefit portfolio under a budget envelope with a STAKEHOLDER-EQUITY
      constraint (every stakeholder must clear a benefit floor = "massive benefit for all"),
  (3) Monte-Carlo over cost/yield uncertainty to find no-regret options,
  (4) sweeps the budget ($10B / $25B / $50B).
Cost/yield are grounded-Gemini priors (research/solutions_out/); benefit TYPE distinguishes new
supply / demand reduction / loss avoided / reallocation (summed) from storage (0.3x), and
enabling/protective keystones (measurement, Glen Canyon) that carry stakeholder benefit but no
additive MAF. Outputs figures + JSON + ranked table.
"""
import json, itertools, numpy as np
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import sys as _sys, os as _os; _sys.path.insert(0,_os.path.dirname(_os.path.abspath(__file__)))
from crstyle import apply as _ap; _ap()

ROOT=Path(__file__).resolve().parent.parent
FIG,OUT,REC=ROOT/"figures",ROOT/"outputs",ROOT/"recs"
for d in (FIG,OUT,REC): d.mkdir(exist_ok=True)
STK=["UpperBasin","LB-ag","Cities","Tribes","Hydropower","Environment","Mexico"]

# name, 10yr program cost $B, water AF/yr, benefit_type, stakeholder scores 0-3, cost_cv, yield_cv
# ALIGNED WITH solutions_finance.py HONEST NUMBERS (July 2026 adversarial review)
OPTS=[
 ("Measurement & accounting ledger", 1.0,        0, "enabling",   [3,3,3,3,2,3,2], .3,.4),
 ("Consumptive-use conservation market", 3.0, 500_000,"demand",   [2,3,3,2,2,1,1], .3,.3),
 ("Urban turf buyback + reuse",       30.0, 717_500, "demand",     [1,1,3,1,1,1,1], .3,.3),
 ("Direct potable reuse buildout",    22.0, 500_000, "new_supply", [1,1,3,1,1,2,1], .4,.3),
 ("Agricultural efficiency at scale", 3.75, 120_000, "demand",     [2,3,2,2,1,2,1], .3,.4),
 ("Reservoir evap + floating solar",  30.7, 734_000, "loss_avoid", [2,2,2,1,3,1,1], .4,.5),
 ("Dust-on-snow source control",      15.0,       0, "new_supply", [3,2,2,2,2,2,1], .5,.6),
 ("Phreatophyte / tamarisk control",  2.40,       0, "loss_avoid", [1,2,1,1,1,2,2], .3,.5),
 ("Managed aquifer recharge",         8.0,  400_000,"storage",   [1,2,3,2,1,2,1], .3,.4),
 ("Glen Canyon temp + outlet retrofit",3.5,       0, "protective", [3,2,3,3,3,3,2], .4,.2),
 ("Tribal infrastructure + leasing",  28.5, 600_000,"realloc",   [1,2,2,3,1,1,1], .3,.3),
 ("Cloud seeding + ASO monitoring",   0.05,       0, "new_supply", [3,2,2,1,2,1,1], .4,.7),
 ("Desalination exchange",            4.5,  180_000, "new_supply", [1,1,2,1,1,1,2], .3,.3),
]
ADDITIVE={"new_supply","demand","loss_avoid","realloc"}
def water_credit(t, af):
    if t in ADDITIVE: return af
    if t=="storage": return 0.3*af      # reliability, partial credit
    return 0.0                          # enabling / protective: no additive MAF

names=[o[0] for o in OPTS]; cost=np.array([o[1] for o in OPTS])
yield_af=np.array([o[2] for o in OPTS]); types=[o[3] for o in OPTS]
S=np.array([o[4] for o in OPTS],float)   # (n,7) stakeholder scores
wcred=np.array([water_credit(t,a) for t,a in zip(types,yield_af)])/1e6  # MAF/yr additive
lev_per_af=np.array([ (o[1]*1e9/10)/o[2] if o[2]>0 else np.nan for o in OPTS ])  # $/AF/yr (10yr)
n=len(OPTS)

def optimize(budget, equity_floor, weights=None, cost_v=None, yield_v=None):
    c = cost if cost_v is None else cost_v
    w = wcred if yield_v is None else yield_v
    Sw = S if weights is None else S*weights
    best=None
    for r in range(1<<n):
        idx=[i for i in range(n) if r>>i&1]
        if not idx: continue
        tc=c[idx].sum()
        if tc>budget: continue
        stot=S[idx].sum(axis=0)
        if (stot<equity_floor).any(): continue          # every stakeholder cleared
        water=w[idx].sum()
        score=water + 0.12*Sw[idx].sum()
        if best is None or score>best[0]:
            best=(score,water,tc,stot,tuple(idx))
    return best

# ---- Base optimization at $50B with an equity floor (each stakeholder >= 4 total) ----
FLOOR=4
base=optimize(50.0, FLOOR)
print(f"[opt] $50B envelope, equity floor {FLOOR}/stakeholder")
print(f"[opt] selected: {[names[i] for i in base[4]]}")
print(f"[opt] additive water {base[1]:.2f} MAF/yr, cost ${base[2]:.1f}B, stakeholder mins {base[3].astype(int)}")

# ---- Budget sweep ----
sweep={}
for b in (10,25,50):
    r=optimize(float(b),FLOOR)
    sweep[b]={"cost":round(r[2],1),"water_maf":round(float(r[1]),2),
              "options":[names[i] for i in r[4]],"stakeholder_min":int(r[3].min())}
    print(f"[sweep ${b}B] water {r[1]:.2f} MAF, cost ${r[2]:.1f}B, {len(r[4])} options, min-stakeholder {int(r[3].min())}")

# ---- Monte Carlo: perturb cost & yield, re-optimize, count no-regret options ----
rng=np.random.default_rng(42)
counts=np.zeros(n); NMC=300
for _ in range(NMC):
    cv=cost*np.exp(rng.normal(0,[o[5] for o in OPTS]))
    yv=wcred*np.exp(rng.normal(0,[o[6] for o in OPTS]))
    r=optimize(50.0,FLOOR,cost_v=cv,yield_v=yv)
    if r:
        for i in r[4]: counts[i]+=1
freq=counts/NMC
order=np.argsort(-freq)
print("[MC] no-regret frequency (top):")
for i in order[:8]: print(f"   {freq[i]*100:4.0f}%  {names[i]}")

# ---- Figures ----
# 1) efficiency: cost vs additive water, sized by stakeholder breadth, labeled $/AF
fig,ax=plt.subplots(figsize=(10.5,6))
breadth=(S>=2).sum(axis=1)
sc=ax.scatter(cost, wcred, s=40+breadth*55,
   c=[lev_per_af[i] if np.isfinite(lev_per_af[i]) else 3000 for i in range(n)],
   cmap="RdYlGn_r", vmin=0, vmax=3000, edgecolor="#333", linewidth=.6, zorder=3)
for i in range(n):
    ax.annotate(names[i].split(" (")[0][:22], (cost[i],wcred[i]), fontsize=7,
        xytext=(5,4), textcoords="offset points")
sel=set(base[4])
ax.scatter(cost[list(sel)], wcred[list(sel)], s=[40+breadth[i]*55 for i in sel],
   facecolor="none", edgecolor="#12343b", linewidth=2.4, zorder=4, label="in optimal $50B package")
ax.set_xlabel("10-year program cost ($B)"); ax.set_ylabel("Additive water benefit (MAF/yr)")
ax.set_title("Colorado River solutions: cost vs. water, by $/acre-foot (marker size = stakeholder breadth)")
plt.colorbar(sc,label="levelized $/acre-foot"); ax.legend(loc="upper right"); ax.grid(alpha=.25)
plt.tight_layout(); plt.savefig(FIG/"sol_efficiency.png",dpi=140); plt.close()

# 2) no-regret frequency bars
fig,ax=plt.subplots(figsize=(9,6))
o2=order[::-1]
ax.barh([names[i].split(" (")[0][:26] for i in o2],[freq[i]*100 for i in o2],
        color=["#2C7A87" if i in sel else "#B9A889" for i in o2])
ax.set_xlabel("% of Monte-Carlo trials the option is in the optimal $50B package")
ax.set_title("No-regret options under cost & yield uncertainty (300 trials)")
plt.tight_layout(); plt.savefig(FIG/"sol_noregret.png",dpi=140); plt.close()

numbers={"equity_floor":FLOOR,
  "optimal_50B":{"options":[names[i] for i in base[4]],"additive_water_maf":round(float(base[1]),2),
     "cost_B":round(float(base[2]),1),"stakeholder_min_score":int(base[3].min())},
  "budget_sweep":sweep,
  "no_regret_freq":{names[i]:round(float(freq[i]),2) for i in order},
  "levelized_per_af":{names[i]:(round(float(lev_per_af[i])) if np.isfinite(lev_per_af[i]) else None) for i in range(n)},
  "all_options":[{"name":names[i],"cost10yr_B":float(cost[i]),"yield_af":int(yield_af[i]),
     "type":types[i],"additive_water_maf":round(float(wcred[i]),3),
     "levelized_per_af":(round(float(lev_per_af[i])) if np.isfinite(lev_per_af[i]) else None)} for i in range(n)]}
(OUT/"solutions_numbers.json").write_text(json.dumps(numbers,indent=2))
print(f"[done] wrote sol_efficiency.png, sol_noregret.png, solutions_numbers.json")
