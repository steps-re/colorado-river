#!/usr/bin/env python3
"""Pull the USGS Lake Mead eddy-covariance evaporation record from ScienceBase and aggregate
to annual feet the way Earp & Moreo (2021) aggregate theirs. Two data releases cover 2015-2020
and 2021-2023, extending the OFR 2021-1022 series the model's 6.22 ft/yr depth comes from.
Surfaced by USGS personal communication, 2026-08-10; method confirmed 2026-08-12.
Output: outputs/usgs_mead_evap.json"""
import calendar,json,re,sys,zipfile,urllib.request
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

# A year is kept only if the evaporation it reports agrees with the latent-heat flux it reports.
# Every sound year in the record closes to better than 0.3%, so 5% is loose by more than an order
# of magnitude and still excludes 2019 (which misses by 33%).
CLOSURE_TOL=0.05
M_PER_FT=0.3048

def fetch(url,dest):
    if dest.exists() and dest.stat().st_size>0: return dest
    if not url:
        raise SystemExit(f"[mead-evap] {dest.name} is not cached and the cached catalog entry "
                         "carries no download URL; re-run when ScienceBase is reachable")
    with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=120) as r:
        dest.write_bytes(r.read())
    return dest

STALE_METADATA=[]

def item(iid):
    """Resolve the .ods through the item API; the file URLs carry disk hashes that move
    when a release is revised, so never hardcode them.

    ScienceBase goes down. The spreadsheets are already cached, so an outage should not be able
    to block a rebuild, but falling back silently would hide a revised release behind stale
    metadata. So the fallback is loud: it warns here, records itself in the output, and the
    caller reports it."""
    cache=CACHE/f"sciencebase_{iid}.json"
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://www.sciencebase.gov/catalog/item/{iid}?format=json",headers=UA),timeout=90) as r:
            meta=json.load(r)
        cache.write_text(json.dumps(meta))
    except Exception as e:
        if not cache.exists():
            raise SystemExit(f"[mead-evap] ScienceBase unreachable ({type(e).__name__}) and no "
                             f"cached metadata for item {iid}; cannot proceed")
        meta=json.loads(cache.read_text())
        STALE_METADATA.append(iid)
        print(f"[mead-evap] WARNING: ScienceBase unreachable ({type(e).__name__}). Using CACHED "
              f"metadata for item {iid}. A revised release would not be noticed. Re-run when the "
              f"catalog is back.",file=sys.stderr)
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

def month_key(cell):
    if not isinstance(cell,str): return None
    p=cell.split()
    if len(p)!=2 or p[0] not in MONTHS or not p[1].isdigit(): return None
    return int(p[1]),MONTHS[p[0]]

def parse_evap(path):
    """Monthly_Evaporation_Estimates, in feet: month, measured, corrected (most probable),
    EBR-adjusted, then an optional 'E' qualifier marking a month with substantially estimated
    daily values."""
    out={}
    for c in sheet_rows(path,"Monthly_Evaporation"):
        ym=month_key(c[0] if c else None)
        if ym is None: continue
        try: meas,corr,ebr=float(c[1]),float(c[2]),float(c[3])
        except (IndexError,TypeError,ValueError): continue
        out[ym]={"measured":meas,"corrected":corr,"ebr_adjusted":ebr,
                 "estimated":len(c)>4 and str(c[4]).strip().upper()=="E"}
    if not out: raise SystemExit(f"[mead-evap] no monthly rows parsed from {path.name}")
    return out

def parse_met(path):
    """Monthly_EC_Met: the uncorrected flux record behind the evaporation columns. Only Qe
    (latent-heat flux, W/m2) and air temperature are needed here, and both are read by header
    name because the sheet carries qualifier columns between them."""
    out={};hdr=None
    for c in sheet_rows(path,"Monthly_EC_Met"):
        if c and isinstance(c[0],str) and c[0].startswith("Month and year"):
            hdr=[str(x).strip() for x in c]; continue
        ym=month_key(c[0] if c else None)
        if ym is None or hdr is None: continue
        d=dict(zip(hdr,c))
        try: out[ym]={"qe":float(d["Qe"]),"air_c":float(d["Air Temperature"])}
        except (KeyError,TypeError,ValueError): continue
    if not out: raise SystemExit(f"[mead-evap] no Monthly_EC_Met rows parsed from {path.name}")
    return out

def implied_ft(year,month,qe,air_c):
    """Depth of water a month of latent-heat flux can evaporate. Latent heat of vaporisation
    from air temperature (Harrison 1963); the sheet publishes no water-surface temperature, and
    the difference is worth well under a percent against a 5% tolerance."""
    lam=(2.501-0.002361*air_c)*1e6                      # J/kg
    secs=calendar.monthrange(year,month)[1]*86400
    return qe*secs/(1000.0*lam)/M_PER_FT                # W/m2 -> kg/m2 -> m -> ft

monthly={};met={};releases=[]
for label,iid in ITEMS.items():
    meta,ods=item(iid)
    rows,mrows=parse_evap(ods),parse_met(ods)
    overlap=sorted(set(rows)&set(monthly))
    if overlap: raise SystemExit(f"[mead-evap] releases overlap at {overlap[0]}; dedupe rule needed")
    monthly.update(rows); met.update(mrows)
    releases.append({"period":label,"title":meta.get("title"),"citation":meta.get("citation"),
                     "sciencebase":f"https://www.sciencebase.gov/catalog/item/{iid}",
                     "file":ods.name,"months":len(rows)})
    print(f"[mead-evap] {label}: {len(rows)} months from {ods.name}")

annual=defaultdict(lambda:{"measured":0.0,"corrected":0.0,"ebr_adjusted":0.0,"qe_implied":0.0,
                           "months":0,"estimated_months":0,"met_months":0})
for ym,v in monthly.items():
    a=annual[ym[0]]
    for k in ("measured","corrected","ebr_adjusted"): a[k]+=v[k]
    a["months"]+=1; a["estimated_months"]+=int(v["estimated"])
    m=met.get(ym)
    if m: a["qe_implied"]+=implied_ft(ym[0],ym[1],m["qe"],m["air_c"]); a["met_months"]+=1

# The energy-closure consistency test. Evaporation and latent-heat flux are two presentations of
# the same measurement, so a year where they disagree is a year where one of the two columns is
# wrong. This is a test of the release against itself, not against our expectations, which is why
# it is allowed to remove a year from the mean.
years={}
for y,a in sorted(annual.items()):
    complete=a["months"]==12
    testable=complete and a["met_months"]==12 and a["measured"]>0
    ratio=round(a["qe_implied"]/a["measured"],4) if testable else None
    years[y]={**{k:round(a[k],3) for k in ("measured","corrected","ebr_adjusted","qe_implied")},
              "months":a["months"],"estimated_months":a["estimated_months"],
              "closure_ratio":ratio,
              "closes":ratio is not None and abs(ratio-1)<=CLOSURE_TOL,
              "complete":complete}
    years[y]["qualified"]=complete and years[y]["closes"]

full=[y for y,v in years.items() if v["complete"]]
qualified=[y for y,v in years.items() if v["qualified"]]
excluded={y:(f"reported evaporation is {abs(1-v['closure_ratio'])*100:.0f}% away from what its own "
             f"latent-heat flux implies ({v['qe_implied']:.2f} vs {v['measured']:.2f} ft measured), "
             f"and {v['estimated_months']} of its 12 months are flagged estimated")
          for y,v in years.items() if v["complete"] and not v["qualified"]}
if not qualified: raise SystemExit("[mead-evap] no year passes the closure test; refusing to write a mean")

means={k:round(mean(years[y][k] for y in qualified),3)
       for k in ("measured","corrected","ebr_adjusted")}
means_all={k:round(mean(years[y][k] for y in full),3)
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
        "record_years":[min(years),max(years)],
        "complete_years":full,
        "qualified_years":qualified,
        "excluded_years":excluded,
        "method":{
          "source":"Earp, K.J., and Moreo, M.T., 2021, Evaporation from Lake Mead and Lake Mohave, "
                   "Nevada and Arizona, 2010-2019: USGS Open-File Report 2021-1022, "
                   "https://doi.org/10.3133/ofr20211022",
          "confirmed":"USGS (Geoffrey Moret) personal communication, 2026-08-12, naming OFR "
                      "2021-1022 as the method used for the final Colorado River basin numbers "
                      "and leaving the weighting to us.",
          "column":"Most probable. The OFR treats evaporation from measured latent-heat flux as a "
                   "probable minimum and the energy-balance-closed value as a probable maximum, and "
                   "states that 'most probable evaporation represents the average between minimum "
                   "and maximum evaporation and is used for all monthly calculations in this study' "
                   "(p. 17). That is the release's 'Corrected (most probable) evaporation' column.",
          "aggregation":"Unweighted mean of complete calendar years. The OFR's own annual table "
                        "(table 8) runs January 2011 through December 2018 and reports the mean of "
                        "those eight years; the partial years at either end of its record, 2010 and "
                        "2019, are excluded rather than scaled up. Years containing gap-filled "
                        "months are kept at full weight, as gap filling is part of the published "
                        "method: the OFR carries 2015 and 2016 at full weight despite multi-week "
                        "outages in both.",
          "closure_test":f"One test is ours and is NOT part of the OFR's method: a complete year is "
                         f"dropped only if the evaporation it reports disagrees with the "
                         f"latent-heat flux it reports by more than {CLOSURE_TOL*100:.0f}%. USGS "
                         f"prescribe no such rule and publish 2019 without qualification beyond "
                         f"its estimated-data flags. We add it because the two columns are "
                         f"presentations of one measurement, so a disagreement means one of them "
                         f"is wrong, and because the alternative is to average a year the release "
                         f"contradicts itself about. The threshold is ours too, and the table "
                         f"below shows every year's ratio so a reader can set it differently.",
          "closure_tolerance":CLOSURE_TOL},
        "sciencebase_metadata_stale_for":STALE_METADATA,
        "source_note":"USGS confirmed (personal communication, 2026-08-10) that no new Lake Mohave "
                      "data are being collected, that no Lake Havasu flux measurement exists though "
                      "one is in planning, and that 2024-2025 Mead data should publish within months.",
        "releases":releases},
     # The monthly series is published, not just the annual aggregate, because seasonality is
     # exactly what the annual aggregate throws away and it is the only measured open-water
     # seasonality in the basin. analysis/evap_seasonality.py consumes it.
     "monthly_corrected_ft":{f"{y}-{m:02d}":round(v["corrected"],3)
                             for (y,m),v in sorted(monthly.items())},
     "annual_ft":years,
     "period_mean_ft":means,
     "all_complete_years_mean_ft":means_all,
     "published_depth_check":{
        "model_uses_ft":PUBLISHED_FT,
        "model_source":"Earp & Moreo 2021, OFR 2021-1022 (2011-2018 annual table), 1,896 mm/yr",
        "recomputed_corrected_ft":means["corrected"],
        "n_years":len(qualified),
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

for y,v in years.items():
    r=f"{v['closure_ratio']:.3f}" if v["closure_ratio"] is not None else "  -  "
    print(f"[mead-evap] {y}: corrected {v['corrected']:.2f} ft, {v['estimated_months']} est months, "
          f"closure {r} {'OK' if v['qualified'] else 'EXCLUDED'}")
print(f"[mead-evap] {len(years)} years, {len(full)} complete, {len(qualified)} qualified: "
      f"corrected mean {means['corrected']:.2f} ft/yr vs published {PUBLISHED_FT} "
      f"({doc['published_depth_check']['delta_pct']:+.1f}%)")
print(f"[mead-evap] {'CORROBORATES' if corroborates else 'CONFLICTS WITH'} the published depth")
print("[mead-evap] wrote outputs/usgs_mead_evap.json")
if not corroborates: sys.exit(1)
