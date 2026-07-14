#!/usr/bin/env python3
"""Pull Lake Mead + Lake Powell reservoir evaporation from Reclamation's RISE API (data.usbr.gov),
aggregate to annual acre-feet, and plot in the site style. Live-sourced Reclamation data.
Output: figures/rise_evap.png, outputs/rise_evap.json"""
import json,urllib.request,os,sys
from collections import defaultdict
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from crstyle import apply,WATER,RUST,DEEP,SAND; apply()
ROOT=Path(__file__).resolve().parent.parent; FIG,OUT=ROOT/"figures",ROOT/"outputs"
for d in(FIG,OUT):d.mkdir(exist_ok=True)
def get(path):
    r=urllib.request.Request("https://data.usbr.gov"+path,headers={"Accept":"application/vnd.api+json"})
    return json.load(urllib.request.urlopen(r,timeout=90))
def find_evap_item(loc):
    # list catalog items at the location, pick the evaporation series reported in acre-feet
    d=get(f"/rise/api/catalog-item?itemsPerPage=200&query%5Blocation%5D={loc}")
    cands=[]
    for x in d.get("data",[]):
        a=x["attributes"]; nm=(a.get("parameterName") or "")
        if "evaporation" in nm.lower():
            cands.append((x["id"].split("/")[-1],a.get("parameterUnit") or a.get("unit") or ""))
    return cands
def annual(itemid):
    yr=defaultdict(float); n=defaultdict(int)
    page=1
    while True:
        d=get(f"/rise/api/result?itemId={itemid}&itemsPerPage=10000&page={page}")
        rows=d.get("data",[])
        if not rows: break
        for x in rows:
            a=x["attributes"]; dt=a.get("dateTime",""); v=a.get("result")
            if dt and v is not None:
                y=int(dt[:4]); yr[y]+=float(v); n[y]+=1
        if len(rows)<10000: break
        page+=1
        if page>6: break
    return yr,n
res={}
for name,loc in [("Lake Mead",3514),("Lake Powell",3540)]:
    cands=find_evap_item(loc)
    print(name,"evap candidates:",cands)
    # pick the AF one if labeled, else the larger-magnitude series (AF not rate)
    picked=None
    for iid,unit in cands:
        if "acre" in unit.lower() or "af" in unit.lower(): picked=iid;break
    if not picked and cands: picked=cands[0][0]
    if not picked: print("  no evap item"); continue
    yr,n=annual(picked)
    # keep only reasonably complete years (>=350 daily obs) and magnitude in AF (thousands+)
    full={y:v for y,v in yr.items() if n[y]>=300 and 100000<v<2000000}
    res[name]={"itemId":picked,"annual_af":dict(sorted(full.items()))}
    print(f"  item {picked}: {len(full)} full years; recent:",dict(list(sorted(full.items()))[-3:]))
(OUT/"rise_evap.json").write_text(json.dumps(res,indent=2))
# plot
fig,ax=plt.subplots(figsize=(10,5.6))
col={"Lake Mead":RUST,"Lake Powell":WATER}
for name,d in res.items():
    a=d["annual_af"]; xs=sorted(a); ys=[a[x]/1e6 for x in xs]
    if xs: ax.plot(xs,ys,marker="o",ms=4,lw=2.2,color=col[name],label=name)
ax.set_ylabel("Evaporation loss (million acre-feet / yr)")
ax.set_title("Reservoir evaporation, live from Reclamation RISE  (Mead + Powell)")
ax.legend(); ax.grid(alpha=.25)
plt.tight_layout(); plt.savefig(FIG/"rise_evap.png",dpi=140); plt.close()
tot={y:round((res.get("Lake Mead",{}).get("annual_af",{}).get(y,0)+res.get("Lake Powell",{}).get("annual_af",{}).get(y,0))/1e6,2) for y in range(2015,2026)}
print("combined MAF/yr 2015-2025:",{k:v for k,v in tot.items() if v})
print("[done] figures/rise_evap.png + outputs/rise_evap.json")
