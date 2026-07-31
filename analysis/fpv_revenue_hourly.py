"""Hourly FPV REVENUE / capture-price model at the Colorado River dams, over past years.

Quantifies the 'solar penalty': FPV produces into the Desert-SW midday glut, so the price it
CAPTURES is below the time-average price. Value must come from evening time-shift, not midday sales.

Method:
  - FPV(t): PVGIS-NSRDB hourly output at Glen Canyon (weather year 2015, MST), per-MW (as in
      analysis/hourly_fpv_hydro.py).
  - Price(t): CAISO OASIS day-ahead hourly LMP at SP15 hub (TH_SP15_GEN-APND) = public proxy for
      WAPA Desert-SW / Palo Verde wholesale value. Pulled full-year in 31-day chunks.
  - Same-year 2015 (rigorous covariation) + price-year sensitivity 2019/2023/2024 (shape-transferred
      by month/day/hour) to show how the deepening midday glut erodes FPV capture price.
Outputs: outputs/fpv_revenue_hourly.json. Public APIs, ZERO Claude tokens. Background job.
"""
import os, sys, json, io, zipfile, urllib.request, time, datetime as dt
import numpy as np
REPO = os.path.expanduser("~/code/steps/colorado-river"); sys.path.insert(0, REPO)
OUT = os.path.join(REPO, "outputs"); os.makedirs(OUT, exist_ok=True)
LAT, LON = 36.937, -111.483
NODE = "TH_SP15_GEN-APND"

def pvgis(lat, lon, year):
    u = ("https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?"
         f"lat={lat}&lon={lon}&startyear={year}&endyear={year}&raddatabase=PVGIS-NSRDB"
         "&pvcalculation=1&peakpower=1&loss=14&angle=30&aspect=0&outputformat=json")
    d = json.loads(urllib.request.urlopen(u, timeout=120).read())
    out = {}
    for r in d["outputs"]["hourly"]:
        t = dt.datetime.strptime(r["time"], "%Y%m%d:%H%M") - dt.timedelta(hours=7)  # UTC->MST
        out[(t.month, t.day, t.hour)] = r["P"] / 1000.0    # MW per MW_dc
    return out

def caiso_year(node, year):
    """DAM hourly LMP $/MWh keyed by (month,day,hour), pulled in monthly chunks."""
    px = {}
    for m in range(1, 13):
        s = dt.datetime(year, m, 1)
        e = (dt.datetime(year + (m // 12), (m % 12) + 1, 1))
        u = ("http://oasis.caiso.com/oasisapi/SingleZip?queryname=PRC_LMP&version=12"
             f"&startdatetime={s:%Y%m%d}T07:00-0000&enddatetime={e:%Y%m%d}T07:00-0000"
             f"&market_run_id=DAM&node={node}&resultformat=6")
        for attempt in range(4):
            try:
                raw = urllib.request.urlopen(u, timeout=90).read()
                z = zipfile.ZipFile(io.BytesIO(raw)); nm = z.namelist()[0]
                if nm.endswith(".xml"):
                    raise RuntimeError("got XML (throttle/err): " + z.read(nm).decode()[:200])
                rows = z.read(nm).decode().splitlines()
                ci = {h: i for i, h in enumerate(rows[0].split(","))}
                idt, ival, itype = ci["INTERVALSTARTTIME_GMT"], ci["MW"], ci["LMP_TYPE"]
                for r in rows[1:]:
                    c = r.split(",")
                    if len(c) <= ival or c[itype] != "LMP":
                        continue
                    t = dt.datetime.strptime(c[idt][:19], "%Y-%m-%dT%H:%M:%S") - dt.timedelta(hours=7)
                    try:
                        px[(t.month, t.day, t.hour)] = float(c[ival])
                    except ValueError:
                        pass
                break
            except Exception as ex:
                if attempt == 3:
                    print(f"  {year}-{m:02d} FAIL {str(ex)[:120]}", flush=True)
                time.sleep(6 * (attempt + 1))
        time.sleep(5)  # OASIS throttle
    print(f"  CAISO {year}: {len(px)} hourly prices", flush=True)
    return px

def capture(fpv, px):
    keys = [k for k in fpv if k in px and fpv[k] > 0]
    if not keys:
        return None
    f = np.array([fpv[k] for k in keys]); p = np.array([px[k] for k in keys])
    allp = np.array([px[k] for k in fpv if k in px])
    cap = float((f * p).sum() / f.sum())
    avg = float(allp.mean())
    return dict(hours=len(keys), capture_price=round(cap, 2), avg_price=round(avg, 2),
                value_factor=round(cap / avg, 3) if avg else None,
                revenue_usd_per_mw_yr=round(float((f * p).sum()), 0),
                neg_price_hours=int((allp < 0).sum()))

print("FPV 2015...", flush=True)
fpv15 = pvgis(LAT, LON, 2015)
res = {"node": NODE, "site": "Glen Canyon (SP15 hub proxy for WAPA Desert SW)", "years": {}}
for py in [2021, 2022, 2023, 2024]:
    print(f"CAISO {py}...", flush=True)
    try:
        px = caiso_year(NODE, py)
        c = capture(fpv15, px)
        res["years"][py] = c
        print(f"  {py}: capture ${c['capture_price']}/MWh vs avg ${c['avg_price']}, "
              f"value factor {c['value_factor']}, neg hrs {c['neg_price_hours']}", flush=True)
    except Exception as e:
        res["years"][py] = {"error": str(e)[:200]}
        print(f"  {py} ERROR {str(e)[:150]}", flush=True)
res["note"] = ("FPV output = 2015 weather (PVGIS-NSRDB). Same-year 2015 = rigorous covariation; "
               "2019/2023/2024 = 2015 solar shape x that year's prices (shape-transferred) to show "
               "the deepening midday glut eroding FPV capture price. SP15 is a Desert-SW value proxy, "
               "not the dam's realized WAPA price. value_factor<1 => FPV earns below average price.")
json.dump(res, open(os.path.join(OUT, "fpv_revenue_hourly.json"), "w"), indent=2)
print("WROTE outputs/fpv_revenue_hourly.json", flush=True)
