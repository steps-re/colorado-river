"""Marginal value of FPV at Glen Canyon: merchant vs FPV+hydro+storage portfolio (2024 SP15 prices).

Tests Mike's claim that FPV's ~$5/MWh merchant capture understates its value because every FPV MWh
lets a hydro MWh move to the evening. Rigorous marginal-value accounting, honest about configuration:
  - Config A (no storage): FPV sells merchant; hydro dispatches optimally on its own. FPV marginal
      value = its own merchant revenue (the dam shifts to evening without FPV's help).
  - Config B (pumped storage, round-trip eta): midday FPV charges storage, discharges into the day's
      highest-price hours up to the tie -> FPV effectively captures ~evening price x eta.
Prices: CAISO OASIS SP15 day-ahead hourly, 2024, cached to outputs/sp15_2024_hourly.csv.
FPV: 2015 PVGIS-NSRDB shape (MST). Public APIs, ZERO Claude tokens. Background job.
"""
import os, sys, json, io, zipfile, csv, urllib.request, time, datetime as dt
import numpy as np
REPO = os.path.expanduser("~/code/steps/colorado-river"); sys.path.insert(0, REPO)
OUT = os.path.join(REPO, "outputs")
PRICE_CACHE = os.path.join(OUT, "sp15_2024_hourly.csv")
LAT, LON = 36.937, -111.483
TIE_MW = 1320          # Glen Canyon nameplate (interconnection proxy)
P_EFF = 1000           # effective turbine capacity at 2024 low pool (sensitivity below)
FPV_GW = 1.0
ETA_RT = 0.80          # pumped-storage round-trip efficiency

def pvgis_shape(lat, lon):
    u = (f"https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?lat={lat}&lon={lon}"
         "&startyear=2015&endyear=2015&raddatabase=PVGIS-NSRDB&pvcalculation=1&peakpower=1"
         "&loss=14&angle=30&aspect=0&outputformat=json")
    d = json.loads(urllib.request.urlopen(u, timeout=120).read()); o = {}
    for r in d["outputs"]["hourly"]:
        t = dt.datetime.strptime(r["time"], "%Y%m%d:%H%M") - dt.timedelta(hours=7)
        o[(t.month, t.day, t.hour)] = r["P"] / 1000.0   # MW per MW_dc
    return o

def caiso_2024_cached():
    if os.path.exists(PRICE_CACHE):
        px = {}
        for row in csv.reader(open(PRICE_CACHE)):
            px[(int(row[0]), int(row[1]), int(row[2]))] = float(row[3])
        print(f"prices from cache: {len(px)}", flush=True); return px
    px = {}
    for m in range(1, 13):
        s = dt.datetime(2024, m, 1); e = dt.datetime(2024 + (m // 12), (m % 12) + 1, 1)
        u = ("http://oasis.caiso.com/oasisapi/SingleZip?queryname=PRC_LMP&version=12"
             f"&startdatetime={s:%Y%m%d}T07:00-0000&enddatetime={e:%Y%m%d}T07:00-0000"
             "&market_run_id=DAM&node=TH_SP15_GEN-APND&resultformat=6")
        for a in range(6):
            try:
                raw = urllib.request.urlopen(u, timeout=90).read()
                z = zipfile.ZipFile(io.BytesIO(raw)); nm = z.namelist()[0]
                if nm.endswith(".xml"): raise RuntimeError("xml")
                rows = z.read(nm).decode().splitlines(); ci = {h: i for i, h in enumerate(rows[0].split(","))}
                for r in rows[1:]:
                    c = r.split(",")
                    if len(c) <= ci["MW"] or c[ci["LMP_TYPE"]] != "LMP": continue
                    t = dt.datetime.strptime(c[ci["INTERVALSTARTTIME_GMT"]][:19], "%Y-%m-%dT%H:%M:%S") - dt.timedelta(hours=7)
                    try: px[(t.month, t.day, t.hour)] = float(c[ci["MW"]])
                    except ValueError: pass
                break
            except Exception:
                time.sleep(20 * (a + 1))
        time.sleep(12)
        print(f"  month {m}: {len(px)} cum", flush=True)
    with open(PRICE_CACHE, "w", newline="") as f:
        w = csv.writer(f)
        for (mo, d_, h), v in sorted(px.items()): w.writerow([mo, d_, h, v])
    print(f"prices pulled+cached: {len(px)}", flush=True); return px

fpv = pvgis_shape(LAT, LON)
px = caiso_2024_cached()

# group keys by day (month,day) that have a full-ish set of prices and fpv
from collections import defaultdict
days = defaultdict(list)
for (mo, d_, h) in px:
    if (mo, d_, h) in fpv:
        days[(mo, d_)].append(h)

# per-MW FPV -> per-GW MW
def dispatch():
    rev_hydro_only = rev_fpv_merch = rev_fpv_store = fpv_energy = hydro_energy = 0.0
    fpv_merch_num = fpv_store_num = 0.0
    for (mo, d_), hrs in days.items():
        hrs = sorted(hrs)
        price = np.array([px[(mo, d_, h)] for h in hrs])
        f = np.array([fpv[(mo, d_, h)] for h in hrs]) * FPV_GW * 1000.0   # MW FPV this day
        # hydro daily energy budget: proxy = a flat delivery-driven volume -> use effective cap * ~10h equiv.
        # Represent the day's deliverable hydro energy as E_day; set so daily CF ~0.35 of P_EFF (typical).
        E_day = P_EFF * 24 * 0.35
        # --- hydro-only optimal dispatch: fill highest-price hours up to P_EFF until E_day spent ---
        order = np.argsort(-price)
        gen = np.zeros(len(hrs)); rem = E_day
        for i in order:
            if rem <= 0: break
            g = min(P_EFF, rem); gen[i] = g; rem -= g
        rev_hydro_only += float((gen * price).sum())
        hydro_energy += float(gen.sum())
        # --- Config A: FPV merchant (curtail into negative prices) ---
        fpv_sell = np.where(price > 0, f, 0.0)
        rev_fpv_merch += float((fpv_sell * price).sum())
        fpv_merch_num += float(fpv_sell.sum())
        fpv_energy += float(f.sum())
        # --- Config B: pumped storage. Charge all FPV (F_day), discharge F_day*eta into top-price
        #     hours in the headroom left on the tie after hydro (TIE_MW - gen), up to P_EFF pump/gen. ---
        F_day = float(f.sum()) * ETA_RT
        headroom = np.clip(TIE_MW - gen, 0, P_EFF)
        disc = np.zeros(len(hrs)); rem = F_day
        for i in order:  # highest price first
            if rem <= 0: break
            g = min(headroom[i], rem); disc[i] = g; rem -= g
        rev_fpv_store += float((disc * price).sum())
        fpv_store_num += float(f.sum())   # value per FPV MWh generated (pre-eta)
    return dict(
        hydro_only_rev=round(rev_hydro_only, 0),
        fpv_energy_mwh=round(fpv_energy, 0),
        fpv_merchant_capture=round(rev_fpv_merch / fpv_merch_num, 2) if fpv_merch_num else None,
        fpv_storage_effective_capture=round(rev_fpv_store / fpv_store_num, 2) if fpv_store_num else None,
        uplift_x=round((rev_fpv_store / fpv_store_num) / (rev_fpv_merch / fpv_merch_num), 1)
                 if fpv_merch_num and rev_fpv_merch else None,
    )

res = {"year_prices": 2024, "node": "TH_SP15_GEN-APND", "fpv_gw": FPV_GW,
       "tie_mw": TIE_MW, "turbine_eff_mw": P_EFF, "storage_round_trip": ETA_RT}
res.update(dispatch())
res["interpretation"] = (
    "fpv_merchant_capture = what a plain FPV array earns selling into 2024 midday (the ~$5 case). "
    "fpv_storage_effective_capture = $/MWh of FPV GENERATED when midday FPV charges pumped storage and "
    "discharges into the day's highest-price hours at eta=0.8 (Mike's 'FPV enables an evening MWh'). "
    "The gap between them IS the value the storage link unlocks; without storage a run-of-delivery dam "
    "shifts its own water to evening, so FPV stays near merchant.")
json.dump(res, open(os.path.join(OUT, "fpv_hydro_dispatch.json"), "w"), indent=2)
print(json.dumps(res, indent=2), flush=True)
print("WROTE outputs/fpv_hydro_dispatch.json", flush=True)
