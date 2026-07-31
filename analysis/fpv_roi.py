"""FPV ROI at Mead/Powell: LCOE vs realized capture price. Uses generation + capture from the models."""
import json, os
OUT=os.path.expanduser("~/code/steps/colorado-river/outputs")
GEN = 1522.6            # MWh per MW_dc-yr (from PVGIS 2015 shape, fixed 30deg, 14% loss; CF~17.4%)
WACC, LIFE = 0.07, 25
CRF = WACC*(1+WACC)**LIFE/((1+WACC)**LIFE-1)
OM = 25000             # $/MW-yr, marine-premium O&M
def lcoe(capex, itc=0.0, om=OM):
    return (CRF*capex*(1-itc)+om)/GEN
# capex scenarios ($/MW installed)
CAPEX={"generic FPV (+12% vs ground $1.1/W)":1_250_000,
       "hard reservoir site (mooring+NEPA+new supply chain)":1_600_000}
# realized capture price scenarios ($/MWh)
CAP={"2024 merchant (curtail neg)":23.81,"2023 merchant":31.27,
     "FPV+storage effective (needs storage capex, not incl.)":36.09}
rows=[]
for cxn,cx in CAPEX.items():
  for itc in [0.0,0.40]:
    l=lcoe(cx,itc)
    for cpn,cp in CAP.items():
      net=(cp-l)*GEN
      rows.append(dict(capex=cxn,itc=f"{int(itc*100)}%",lcoe=round(l,1),
                       capture=cpn,capture_price=cp,
                       net_annual_per_MW=round(net,0),
                       revenue_covers_pct=round(cp/l*100,0),
                       simple_roi=f"{round((cp/l-1)*100)}%"))
res={"assumptions":dict(gen_mwh_per_mw_yr=GEN,cf=round(GEN/8760,3),wacc=WACC,life=LIFE,
     crf=round(CRF,4),om_per_mw_yr=OM,
     note="Evaporation ~11 AF/MW-yr not monetized (no water-benefit market); capacity credit for midday solar is LOW (solar gone at evening peak)."),
     scenarios=rows}
json.dump(res,open(os.path.join(OUT,"fpv_roi.json"),"w"),indent=2)
print(f"CRF={CRF:.4f}  GEN={GEN} MWh/MW-yr (CF {GEN/8760:.1%})\n")
print(f"{'capex':52} {'ITC':4} {'LCOE':>7} {'capture':>8} {'covers':>7} {'ROI':>6}")
for r in rows:
  print(f"{r['capex'][:52]:52} {r['itc']:4} ${r['lcoe']:>6} ${r['capture_price']:>7} {r['revenue_covers_pct']:>6.0f}% {r['simple_roi']:>6}")
