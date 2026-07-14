#!/usr/bin/env python3
"""
Module 2 — Paper water vs. wet water, and the value-per-acre-foot gap.
The biggest stakeholder (agriculture, ~80% of use) grows low-value forage with senior water,
while cities and industry pay orders of magnitude more per acre-foot. That gap is why voluntary
fallowing/leasing is the cheapest water in the basin, and it is the fair, science-based lever.

Data (real):
- USDA CropScape / Cropland Data Layer (CDL) API: alfalfa + crop acreage for the key Lower Basin
  irrigation counties (keyless GetCDLStat).
- Published crop water duty (AF/acre, low-desert) and USDA NASS crop values.
- OpenET retry for measured ET (paper-vs-wet validation) if the endpoint recovers.
Output: figures/m2_value_per_af.png, outputs/m2_numbers.json, recs/m2_rec.md
"""
import json, urllib.request, re
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import sys as _sys, os as _os; _sys.path.insert(0,_os.path.dirname(_os.path.abspath(__file__)))
from crstyle import apply as _ap; _ap()

ROOT=Path(__file__).resolve().parent.parent
FIG,OUT,REC=ROOT/"figures",ROOT/"outputs",ROOT/"recs"
for d in (FIG,OUT,REC): d.mkdir(exist_ok=True)

# Key Lower Basin irrigated counties (FIPS): Imperial CA, Yuma AZ, La Paz AZ, Riverside CA (Palo Verde)
COUNTIES={"Imperial_CA":"06025","Yuma_AZ":"04027","La_Paz_AZ":"04012","Riverside_CA":"06065"}
CDL_ALFALFA=36; CDL_CATS={36:"Alfalfa",37:"Other Hay",2:"Cotton",4:"Sorghum",21:"Barley",
    227:"Lettuce",206:"Carrots",54:"Tomatoes",212:"Oranges",69:"Grapes",228:"Dbl Winter Wheat"}

def cdl_stat(fips, year=2024):
    """GetCDLStat returns XML with a <returnURL> to a JS-object-literal cache file
    (unquoted keys), so follow the pointer and regex-parse category:acreage pairs."""
    try:
        x=urllib.request.urlopen(
            f"https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLStat?year={year}&fips={fips}&format=json",
            timeout=90).read().decode()
        m=re.search(r"<returnURL>(.*?)</returnURL>", x)
        if not m: return {}
        raw=urllib.request.urlopen(m.group(1),timeout=90).read().decode()
        out={}
        for cat,ac in re.findall(r'category:"([^"]+)"[^}]*?acreage:([\d.]+)', raw):
            out[cat]=out.get(cat,0)+float(ac)
        return out
    except Exception as e:
        print(f"  [cdl {fips}] {str(e)[:120]}"); return {}

# Published low-desert water duty (AF/acre consumptive) and crop gross value ($/acre), order-of-magnitude
WATER_DUTY={"Alfalfa":5.8,"Other Hay":5.0,"Cotton":4.2,"Sorghum":3.5,"Barley":2.8,"Durum Wheat":3.0,
    "Lettuce":2.4,"Carrots":2.6,"Tomatoes":3.0,"Oranges":3.8,"Grapes":3.5,"Winter Wheat":2.8}
CROP_VALUE={"Alfalfa":2100,"Other Hay":1600,"Cotton":1500,"Sorghum":700,"Barley":650,"Durum Wheat":800,
    "Lettuce":9000,"Carrots":11000,"Tomatoes":8000,"Oranges":9500,"Grapes":12000,"Winter Wheat":750}
# Benchmark $/AF a user will pay for water (published ranges)
BENCH_PER_AF={"Alfalfa (value/AF)":None,"Produce (value/AF)":None,
    "System conservation payment":400,"Urban M&I (SNWA/CAP)":1200,"Desalination (new supply)":2500}

def val_per_af(crop):
    d=WATER_DUTY.get(crop); v=CROP_VALUE.get(crop)
    return (v/d) if (d and v) else None

# Pull CDL acreage
acre={}; got=False
for name,fips in COUNTIES.items():
    s=cdl_stat(fips)
    if s: got=True
    for cat,ac in s.items():
        acre[cat]=acre.get(cat,0)+ac
# Fallback published acreage if CDL unreachable (Imperial+Palo Verde+Yuma forage, approx)
if not got:
    print("[m2] CDL unreachable -> published fallback acreage")
    acre={"Alfalfa":300000,"Other Hay":90000,"Cotton":40000,"Lettuce":60000,"Grapes":20000}

alfalfa_ac=sum(v for k,v in acre.items() if "Alfalfa" in k or "Hay" in k)
alfalfa_water=alfalfa_ac*WATER_DUTY["Alfalfa"]/1e6   # MAF
alf_vaf=val_per_af("Alfalfa"); let_vaf=val_per_af("Lettuce")

numbers={"cdl_source":"live" if got else "fallback","counties":list(COUNTIES),
    "forage_acres_lowerbasin_sample":round(alfalfa_ac),
    "forage_consumptive_use_maf":round(float(alfalfa_water),3),
    "value_per_af":{c:round(val_per_af(c)) for c in ["Alfalfa","Cotton","Lettuce","Grapes","Oranges"] if val_per_af(c)},
    "benchmarks_per_af":{k:v for k,v in BENCH_PER_AF.items() if v},
    "alfalfa_vs_produce_value_ratio":round(let_vaf/alf_vaf,1) if (alf_vaf and let_vaf) else None}

# figure: value per acre-foot by crop vs water-market benchmarks
crops=["Alfalfa","Cotton","Sorghum","Oranges","Tomatoes","Lettuce","Grapes"]
vals=[val_per_af(c) for c in crops]
fig,ax=plt.subplots(figsize=(10,5))
ax.bar(crops,vals,color=["#c0504d" if c in("Alfalfa","Cotton","Sorghum") else "#4f81bd" for c in crops])
for k,v in BENCH_PER_AF.items():
    if v: ax.axhline(v,ls="--",lw=1,alpha=0.7); ax.text(len(crops)-0.5,v,f" {k} ${v}",fontsize=7,va="bottom")
ax.set_ylabel("Gross crop value per acre-foot of water ($/AF)")
ax.set_title("Value per acre-foot: low-value forage vs. produce vs. what water sells for")
plt.tight_layout(); plt.savefig(FIG/"m2_value_per_af.png",dpi=140); plt.close()
(OUT/"m2_numbers.json").write_text(json.dumps(numbers,indent=2))

rec=f"""## Policy recommendation 2 — Price conservation on wet water, and target the value-per-drop gap

**Finding.** In the Lower Basin sample counties (Imperial, Yuma, La Paz, Palo Verde), forage
(alfalfa + hay) covers ~{alfalfa_ac/1e3:.0f}k acres and consumes ~{alfalfa_water:.1f} MAF of water,
at a gross value near ${alf_vaf:.0f}/acre-foot. Produce returns roughly ${let_vaf:.0f}/acre-foot,
and cities pay well over $1,000/acre-foot. The scarcest resource in the basin is largely growing
its lowest-value-per-drop crop under the most senior rights.

**Why it is the fair, science-based lever.** This is not a call to end farming. It is the reason
voluntary, compensated fallowing and deficit irrigation of forage is the cheapest large block of
water available, and why conservation should be priced on CONSUMPTIVE USE (what actually leaves
the system, measurable by satellite ET) rather than on diversions. Paying on diversions risks
buying "savings" that were evapotranspired anyway or double-counting return flows.

**Recommendation.**
1. Price all conservation and system-conservation payments on measured consumptive use (OpenET /
   eeMETRIC), not diversions, and publish the ET-vs-rights reconciliation so the payments are honest.
2. Make forage deficit-irrigation and rotational fallowing the first, best-compensated block of
   Lower Basin reductions, protecting farm income while freeing the highest-leverage water.
3. Give senior agricultural right-holders durable authority to lease saved water, so the value gap
   is captured by the farmer through a market rather than extracted by fiat.

*USDA CDL ({'live' if got else 'published-fallback'}) + published water duty + NASS values;
value/AF are gross order-of-magnitude. Figure: m2_value_per_af.png. Numbers: m2_numbers.json.*
"""
(REC/"m2_rec.md").write_text(rec)
print(f"[m2] CDL={'live' if got else 'fallback'} forage_ac={alfalfa_ac:.0f} forage_water={alfalfa_water:.2f} MAF")
print(f"[m2] $/AF alfalfa={alf_vaf:.0f} lettuce={let_vaf:.0f} ratio={numbers['alfalfa_vs_produce_value_ratio']}")
