#!/usr/bin/env python3
"""Backtest: had 1.8 GW of PV been installed at the dams' interconnects (2000-2024), how would the
water & energy budgets have changed? Key physics: Glen Canyon/Hoover releases are set by water-delivery
law (~7.5-8.2 MAF band, roughly flat), so hydro generation fell with HEAD (reservoir elevation), not flow.
PV backfills that head-driven decline with flat output and decouples releases from power.
Output: figures/pv_backtest.png, outputs/pv_backtest.json"""
import json,os,sys,numpy as np
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from crstyle import apply,WATER,RUST,DEEP,SAND,STONE; apply()
ROOT=Path(__file__).resolve().parent.parent; FIG,OUT=ROOT/"figures",ROOT/"outputs"
yrs=list(range(2000,2025))
# Lake Powell annual elevation (ft), authoritative series used across the site (2000-2024)
powell=[3680,3608,3560,3555,3570,3560,3600,3610,3630,3640,3634,3660,3630,3608,3580,3560,3600,3620,3585,3610,3595,3546,3522,3560,3540]
# Lake Mead annual elevation (ft), 2000-2024 (published USBR end-of-year, approx)
mead=[1210,1198,1155,1143,1132,1138,1126,1112,1110,1105,1085,1133,1120,1106,1082,1075,1073,1082,1078,1090,1084,1066,1042,1046,1063]
# heads: Glen Canyon tailwater ~3132 ft; Hoover tailwater ~640 ft
gc_head=[e-3132 for e in powell]; hv_head=[e-640 for e in mead]
# releases stayed in the water-law band; treat as ~flat (Glen Canyon ~7.9 MAF avg, Hoover ~9.0 MAF)
gc_rel=8.23 if False else None
# generation ~ k * head * release ; calibrate so 2000 Glen Canyon=5000 GWh, Hoover=4200 GWh (known)
kGC=5000/(gc_head[0]); kHV=4200/(hv_head[0])   # release folded into k (held ~flat)
gc_gen=[kGC*h for h in gc_head]; hv_gen=[kHV*h for h in hv_head]
hydro=[a+b for a,b in zip(gc_gen,hv_gen)]
# 1.8 GW PV at 29% capacity factor, flat
PV_GW=1.8; CF=0.29; pv=PV_GW*8760*CF/1000*1000  # GWh/yr
pv_gwh=PV_GW*8760*CF   # = GWh
base=hydro[0]
shortfall=[max(0,base-h) for h in hydro]           # vs 2000 baseline
cum_shortfall=sum(shortfall)
# if PV installed in 2010, cumulative PV generation 2010-2024
pv_from=2010; pv_years=[y for y in yrs if y>=pv_from]
cum_pv=pv_gwh*len(pv_years)
res={
 "pv_capacity_GW":PV_GW,"pv_capacity_factor":CF,"pv_annual_GWh":round(pv_gwh),
 "glen_canyon_gen_GWh":{y:round(g) for y,g in zip(yrs,gc_gen)},
 "hoover_gen_GWh":{y:round(g) for y,g in zip(yrs,hv_gen)},
 "combined_hydro_GWh":{y:round(g) for y,g in zip(yrs,hydro)},
 "hydro_decline_2000_to_2024_GWh":round(hydro[0]-hydro[-1]),
 "hydro_decline_pct":round(100*(1-hydro[-1]/hydro[0]),1),
 "cum_hydro_shortfall_vs_2000_GWh":round(cum_shortfall),
 "cum_PV_gen_if_installed_2010_GWh":round(cum_pv),
 "pv_covers_shortfall_x":round(cum_pv/cum_shortfall,1),
 "co2_avoided_MtCO2_yr":round(pv_gwh*0.4/1000,2),  # displacing ~gas 0.4 t/MWh
 "note":"generation modeled from head (elevation - tailwater) with release held in its ~flat water-law band; "
        "annual RELEASE volume is set by delivery law, so PV does NOT change release volume - it changes what "
        "the water is released FOR (decouples ops from power)."}
(OUT/"pv_backtest.json").write_text(json.dumps(res,indent=2))
for k in ["hydro_decline_2000_to_2024_GWh","hydro_decline_pct","pv_annual_GWh","cum_hydro_shortfall_vs_2000_GWh","cum_PV_gen_if_installed_2010_GWh","pv_covers_shortfall_x","co2_avoided_MtCO2_yr"]:
    print(f"  {k}: {res[k]}")
# plot
fig,ax=plt.subplots(figsize=(10,5.6))
ax.plot(yrs,gc_gen,lw=1.6,color=SAND,ls=":",label="Glen Canyon (head-modeled)")
ax.plot(yrs,hv_gen,lw=1.6,color="#8AA9AD",ls=":",label="Hoover (head-modeled)")
ax.plot(yrs,hydro,lw=2.6,color=RUST,label="Combined dam hydropower")
ax.axhline(pv_gwh,color=WATER,lw=2.4,ls="--",label=f"1.8 GW PV, flat ({pv_gwh:.0f} GWh/yr)")
ax.fill_between(yrs,hydro,[hydro[0]]*len(yrs),where=[h<hydro[0] for h in hydro],color=RUST,alpha=.08)
ax.set_ylabel("Annual generation (GWh)"); ax.set_ylim(0,None)
ax.set_title("Dam hydropower fell with reservoir head. 1.8 GW of PV backfills it — flat, and water-blind.")
ax.legend(fontsize=8,loc="lower left"); ax.grid(alpha=.25)
plt.tight_layout(); plt.savefig(FIG/"pv_backtest.png",dpi=140); plt.close()
print("[done] figures/pv_backtest.png + outputs/pv_backtest.json")
