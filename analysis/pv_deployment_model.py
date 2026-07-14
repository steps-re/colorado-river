#!/usr/bin/env python3
"""Model PV+BESS installations that MAXIMIZE existing Colorado River transmission headroom, with
solar seasonality, then trace the downstream cascade (energy split -> hydro backfill / datacenter /
water manufactured), jobs, economics, CO2. Output: figures/pv_deploy.png, outputs/pv_deployment.json"""
import json,os,sys,numpy as np
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from crstyle import apply,WATER,RUST,DEEP,SAND,STONE; apply()
ROOT=Path(__file__).resolve().parent.parent; FIG,OUT=ROOT/"figures",ROOT/"outputs"

# --- transmission nodes: headroom MW that is stranding as dams derate / NGS retired ---
NODES=[
 ("Hoover (Mead) 230kV -> LA/Vegas",        776),
 ("Glen Canyon 345/230kV -> Phoenix",       485),
 ("Davis + Parker (Parker-Davis)",           40),
 ("Navajo (NGS) 500kV -> Phoenix & Vegas", 2250),
]
HEADROOM=sum(m for _,m in NODES)     # MW total ~3551

# --- energy-maximizing design: oversize PV vs POI + BESS to fill the line ---
PV_TO_POI=1.45         # PV(AC) nameplate per MW of interconnection
DC_AC=1.30             # DC:AC ratio
BESS_HOURS=6           # storage duration at POI power
LINE_CF=0.55           # resulting transmission utilization (vs ~0.29 PV-alone)  [grounded to research]
# seasonality: desert SW monthly capacity factor (Page/Phoenix/Vegas), monsoon dip Jul-Aug
MONTH_CF=np.array([0.20,0.24,0.29,0.33,0.34,0.33,0.28,0.27,0.30,0.28,0.22,0.19])
MONTH_CF=MONTH_CF/ MONTH_CF.mean()*0.55   # scale so annual mean = LINE_CF

pv_ac=HEADROOM*PV_TO_POI; pv_dc=pv_ac*DC_AC
bess_mw=HEADROOM; bess_mwh=bess_mw*BESS_HOURS
annual_gwh=HEADROOM*8760*LINE_CF/1000
month_gwh=(annual_gwh*MONTH_CF/MONTH_CF.sum())

# capex (2026): PV ~$1.05/W-dc, BESS ~$225/kWh
capex_pv=pv_dc*1e6*1.05/1e9          # $B  (MW * 1e6 W/MW * $1.05/W)
capex_bess=bess_mwh*1000*225/1e9
capex=capex_pv+capex_bess

# --- downstream energy cascade ---
hydro_backfill=4.573                 # TWh/yr to replace lost Hoover+Glen Canyon generation (from backtest)
dc_load=6.0                          # TWh/yr to hyperscaler datacenters (illustrative ~700 MW of 24/7 load)
water_energy=max(0,annual_gwh/1000-hydro_backfill-dc_load)   # TWh left for water
# water manufactured from the remainder (blend: brackish/drainage desal ~2500 kWh/AF, reuse/MAR cheaper)
BLEND_KWH_AF=2200
water_ceiling_af=water_energy*1e9/BLEND_KWH_AF   # if ALL surplus energy -> desal
water_realistic_af=900_000   # bounded by brine disposal, capital, and water-source availability (see PV_WATER_NEXUS)
water_af=water_realistic_af

# --- jobs / economics / CO2 ---
constr_jobyears=pv_ac*5.5            # ~5.5 construction job-years per MW-ac
om_jobs=pv_ac*0.35 + water_af/50000  # ~0.35 permanent/MW + water O&M
co2_avoided=annual_gwh*0.40/1000     # MtCO2/yr displacing gas (~0.4 t/MWh)
gas_avoided_bn=annual_gwh*1000*45/1e9  # $B/yr avoided market power @ ~$45/MWh

res={"transmission_headroom_MW":HEADROOM,"by_node":{n:m for n,m in NODES},
 "design":{"pv_ac_MW":round(pv_ac),"pv_dc_MW":round(pv_dc),"bess_MW":round(bess_mw),"bess_MWh":round(bess_mwh),
   "pv_to_poi_ratio":PV_TO_POI,"line_capacity_factor":LINE_CF},
 "annual_energy_TWh":round(annual_gwh/1000,1),
 "capex_B":{"pv":round(capex_pv,1),"bess":round(capex_bess,1),"total":round(capex,1),"note":"transmission reused = $0"},
 "energy_cascade_TWh":{"hydro_backfill":hydro_backfill,"datacenter_load":dc_load,"available_for_water":round(water_energy,1)},
 "water_energy_ceiling_AF_yr":round(water_ceiling_af),"water_realistic_AF_yr":water_realistic_af,
 "water_note":"energy is NOT the binding constraint - surplus energy could desalinate ~3 MAF, but brine disposal, capital, and source availability bound the realistic add/free to ~0.5-1.0 MAF/yr",
 "jobs":{"construction_job_years":round(constr_jobyears),"permanent":round(om_jobs)},
 "co2_avoided_MtCO2_yr":round(co2_avoided,1),"gas_purchases_avoided_B_yr":round(gas_avoided_bn,2),
 "seasonality":{"winter_min_cf":round(MONTH_CF.min(),2),"spring_max_cf":round(MONTH_CF.max(),2),
   "monsoon_dip":"Jul-Aug afternoon clouds cut ~15-20% vs May peak"}}
(OUT/"pv_deployment.json").write_text(json.dumps(res,indent=2))
for k in ["transmission_headroom_MW","annual_energy_TWh","water_energy_ceiling_AF_yr","water_realistic_AF_yr","co2_avoided_MtCO2_yr"]:
    print(f"  {k}: {res.get(k)}")
print("  design:",res["design"]); print("  capex $B:",res["capex_B"]); print("  cascade TWh:",res["energy_cascade_TWh"]); print("  jobs:",res["jobs"])

# --- figure: monthly energy + line utilization, and the cascade ---
fig,(ax1,ax2)=plt.subplots(1,2,figsize=(12,5))
mn=["J","F","M","A","M","J","J","A","S","O","N","D"]
ax1.bar(mn,month_gwh,color=WATER); ax1.axhline(month_gwh.mean(),color=RUST,ls="--",lw=1.3,label="annual mean")
ax1.set_ylabel("Monthly energy through the lines (GWh)"); ax1.set_title(f"Seasonality: {round(annual_gwh/1000,1)} TWh/yr, monsoon dip Jul-Aug")
ax1.legend(fontsize=8)
casc=[hydro_backfill,dc_load,water_energy]; labs=["Backfill\nlost hydro","Datacenter\nload","Manufacture\nwater"]
ax2.bar(labs,casc,color=[SAND,DEEP,WATER])
for i,v in enumerate(casc): ax2.text(i,v+0.2,f"{v:.1f} TWh",ha="center",fontsize=9)
ax2.set_ylabel("TWh / yr"); ax2.set_title(f"Where {round(annual_gwh/1000,1)} TWh goes  (~0.5-1.0M AF of water)")
plt.tight_layout(); plt.savefig(FIG/"pv_deploy.png",dpi=140); plt.close()
print("[done] figures/pv_deploy.png + outputs/pv_deployment.json")
