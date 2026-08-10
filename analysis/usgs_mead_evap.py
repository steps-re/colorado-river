#!/usr/bin/env python3
"""Pull the USGS Lake Mead eddy-covariance evaporation record from ScienceBase and aggregate
to annual feet. Two data releases cover 2015-2020 and 2021-2023, extending the Earp & Moreo
(2021) 2010-2019 series the model's 6.22 ft/yr depth comes from.
Surfaced by USGS personal communication, 2026-08-10. Output: outputs/usgs_mead_evap.json"""
import json,re,sys,zipfile,urllib.request
from collections import defaultdict
from pathlib import Path
from statistics import mean
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parent.parent; OUT,CACHE=ROOT/"outputs",ROOT/"cache"
for d in(OUT,CACHE):d.mkdir(exist_ok=True)

# ScienceBase item ids. Data are updated approximately annually; 2024-2025 were said to be a
# few months out as of 2026-08-10, so re-running this will pick them up once released.
ITEMS={"2015-2020":"618579f2d34ec04fc9c1bd5f","2021-2023":"68af8573d4be02645f9ab55b"}
UA={"User-Agent":"Mozilla/5.0 (steps-ventures colorado-river analysis)"}
T="{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
O="{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
NS={"table":T[1:-1],"text":"urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
MONTHS={m:i+1 for i,m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}

def fetch(url,dest):
    if dest.exists() and dest.stat().st_size>0: return dest
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=120) as r:
        dest.write_bytes(r.read())
    return dest

def item(iid):
    """Resolve the .ods through the item API; the file URLs carry disk hashes that move
    when a release is revised, so never hardcode them."""
    with urllib.request.urlopen(urllib.request.Request(
            f"https://www.sciencebase.gov/catalog/item/{iid}?format=json",headers=UA),timeout=90) as r:
        meta=json.load(r)
    ods=[f for f in meta.get("files",[]) if f.get("name","").lower().endswith(".ods")]
    if len(ods)!=1:
        raise SystemExit(f"[mead-evap] expected exactly one .ods in item {iid}, got {[f.get('name') for f in ods]}")
    return meta,fetch(ods[0]["url"],CACHE/ods[0]["name"])

def safe_parse(xml):
    """A spreadsheet body never legitimately declares a DTD, so refusing one closes both
    XXE and entity-expansion without pulling in defusedxml."""
    if re.search(rb"<!DOCTYPE|<!ENTITY",xml[:8192],re.I):
        raise SystemExit("[mead-evap] downloaded .ods declares a DTD; refusing to parse")
    return ET.fromstring(xml)

def sheet_rows(path,want):
    root=safe_parse(zipfile.ZipFile(path).read("content.xml"))
    for t in root.iter(T+"table"):
        if want.lower() not in (t.get(T+"name") or "").lower(): continue
        for r in t.findall("table:table-row",NS):
            if int(r.get(T+"number-rows-repeated","1"))>50: continue   # trailing filler rows
            cells=[]
            for c in r.findall("table:table-cell",NS):
                rep=min(int(c.get(T+"number-columns-repeated","1")),20)
                v=c.get(O+"value")
                v=float(v) if v is not None else " ".join(
                    "".join(p.itertext()).strip() for p in c.findall("text:p",NS))
                cells+=[v]*rep
            yield cells

def parse(path):
    """Monthly_Evaporation_Estimates: month, measured, corrected (most probable), EBR-adjusted,
    then an optional 'E' qualifier marking a month with substantially estimated daily values."""
    out={}
    for c in sheet_rows(path,"Monthly_Evaporation"):
        if not c or not isinstance(c[0],str): continue
        parts=c[0].split()
        if len(parts)!=2 or parts[0] not in MONTHS or not parts[1].isdigit(): continue
        try: meas,corr,ebr=float(c[1]),float(c[2]),float(c[3])
        except (IndexError,TypeError,ValueError): continue
        est=len(c)>4 and str(c[4]).strip().upper()=="E"
        out[(int(parts[1]),MONTHS[parts[0]])]={"measured":meas,"corrected":corr,
                                               "ebr_adjusted":ebr,"estimated":est}
    if not out: raise SystemExit(f"[mead-evap] no monthly rows parsed from {path.name}")
    return out

monthly={}; releases=[]
for label,iid in ITEMS.items():
    meta,ods=item(iid)
    rows=parse(ods)
    overlap=sorted(set(rows)&set(monthly))
    if overlap: raise SystemExit(f"[mead-evap] releases overlap at {overlap[0]}; dedupe rule needed")
    monthly.update(rows)
    releases.append({"period":label,"title":meta.get("title"),"citation":meta.get("citation"),
                     "sciencebase":f"https://www.sciencebase.gov/catalog/item/{iid}",
                     "file":ods.name,"months":len(rows)})
    print(f"[mead-evap] {label}: {len(rows)} months from {ods.name}")

annual=defaultdict(lambda:{"measured":0.0,"corrected":0.0,"ebr_adjusted":0.0,
                           "months":0,"estimated_months":0})
for ym,v in monthly.items():
    a=annual[ym[0]]
    for k in ("measured","corrected","ebr_adjusted"): a[k]+=v[k]
    a["months"]+=1; a["estimated_months"]+=int(v["estimated"])
annual={y:{**{k:round(v,3) for k,v in a.items() if isinstance(v,float)},
           "months":a["months"],"estimated_months":a["estimated_months"]}
        for y,a in sorted(annual.items())}

full=[y for y,a in annual.items() if a["months"]==12]
if not full: raise SystemExit("[mead-evap] no complete years; refusing to write a mean")
means={k:round(mean(annual[y][k] for y in full),3)
       for k in ("measured","corrected","ebr_adjusted")}

# The model's published depth. Recomputing a mean off a data release is weaker provenance than
# the peer-reviewed OFR value, so this is a corroboration test, not a replacement.
PUBLISHED_FT=6.22; FLUX_UNCERTAINTY=0.08
delta=means["corrected"]-PUBLISHED_FT
corroborates=abs(delta)<=FLUX_UNCERTAINTY*PUBLISHED_FT

doc={"meta":{
        "what":"USGS Lake Mead evaporation, monthly, from eddy covariance at land-based station "
               "360500114465601 with an energy-balance correction",
        "why":"extends the Earp & Moreo (2021) 2010-2019 record the model's Mead depth rests on",
        "record_years":[min(annual),max(annual)],
        "complete_years":full,
        "source_note":"USGS confirmed (personal communication, 2026-08-10) that no new Lake Mohave "
                      "data are being collected, that no Lake Havasu flux measurement exists though "
                      "one is in planning, and that 2024-2025 Mead data should publish within months.",
        "releases":releases},
     "annual_ft":annual,
     "period_mean_ft":means,
     "published_depth_check":{
        "model_uses_ft":PUBLISHED_FT,
        "model_source":"Earp & Moreo 2021, OFR 2021-1022 (2010-2019), 1,896 mm/yr",
        "recomputed_corrected_ft":means["corrected"],
        "delta_ft":round(delta,3),
        "delta_pct":round(100*delta/PUBLISHED_FT,2),
        "flux_uncertainty_pct":round(100*FLUX_UNCERTAINTY,1),
        "corroborates":corroborates,
        "verdict":("The extended record sits inside the flux uncertainty the model already carries, "
                   "so it corroborates the published depth rather than replacing it."
                   if corroborates else
                   "The extended record falls OUTSIDE the model's stated flux uncertainty. The "
                   "published depth needs revisiting before the next build.")}}
(OUT/"usgs_mead_evap.json").write_text(json.dumps(doc,indent=2))

print(f"[mead-evap] {len(annual)} years, {len(full)} complete: "
      f"corrected mean {means['corrected']:.2f} ft/yr vs published {PUBLISHED_FT} "
      f"({doc['published_depth_check']['delta_pct']:+.1f}%)")
print(f"[mead-evap] {'CORROBORATES' if corroborates else 'CONFLICTS WITH'} the published depth")
print("[mead-evap] wrote outputs/usgs_mead_evap.json")
if not corroborates: sys.exit(1)
