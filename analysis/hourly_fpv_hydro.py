"""FULL-YEAR chronological (8760-hour) FPV vs Glen Canyon Dam release/generation.

Answers Lall (2026-07-30): does FPV output line up in time with the dam's generation/release
decisions, and can solar EXPORT on the dam's interconnection (vs curtail) while the water the dam
would have released for MIDDAY energy is held for the evening ramp?

Method (chronological, NOT hour-of-day averaged — the joint distribution of solar, release and
transmission headroom moves together across seasons):
  - FPV(t): PVGIS hourly PV (PVGIS-NSRDB radiation DB, real weather) at the lake, 2015, per-MW,
      with a small floating water-cooling uplift.
  - Release(t): USGS NWIS 15-min discharge below Glen Canyon (09380000 Lees Ferry), 2015,
      aggregated to hourly mean cfs -> hydropower generation proxy (MW ~ Q, capped at nameplate).
  - Release decomposition: LTEMP obligatory floor (8000 cfs day / 5000 cfs night) = FPV-IMMUNE;
      release above floor = energy-driven peaking = FPV-REPLACEABLE (per grounded ops research).
  - Interconnection headroom(t) = nameplate - hydro_gen(t). Shared-interconnection export sim:
      export(t)=min(FPV(t), headroom(t)); curtail(t)=FPV(t)-export(t). Swept over FPV array size.

Outputs: outputs/hourly_fpv_hydro.json + figures/hourly_fpv_hydro*.png. Public APIs, ZERO Claude tokens.
"""
import os, sys, json, urllib.request, urllib.parse, datetime as dt
import numpy as np

REPO = os.path.expanduser("~/code/steps/colorado-river")
sys.path.insert(0, REPO)
OUT = os.path.join(REPO, "outputs"); FIG = os.path.join(REPO, "figures")
os.makedirs(OUT, exist_ok=True); os.makedirs(FIG, exist_ok=True)

YEAR = 2015
LAT, LON = 36.937, -111.483          # Glen Canyon / Lake Powell
USGS = "09380000"                    # Colorado R at Lees Ferry (below Glen Canyon)
CAP_MW = 1320                        # Glen Canyon nameplate
Q_AT_CAP = 31000.0                   # ~cfs at full powerplant capacity (approx, high pool)
FLOOR_DAY, FLOOR_NIGHT = 8000.0, 5000.0   # LTEMP min flows (cfs), day 7a-7p / night

# ---------- FPV from PVGIS (weather-driven hourly, full year) ----------
def pvgis_hourly(lat, lon, year):
    u = ("https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?"
         f"lat={lat}&lon={lon}&startyear={year}&endyear={year}&raddatabase=PVGIS-NSRDB"
         "&pvcalculation=1&peakpower=1&loss=14&angle=30&aspect=0&outputformat=json")
    d = json.loads(urllib.request.urlopen(u, timeout=120).read())
    rows = d["outputs"]["hourly"]
    ts, p, tair, gi = [], [], [], []
    for r in rows:
        # PVGIS timestamps are UTC; Lees Ferry/Lake Powell is MST (UTC-7, no DST) -> shift to local.
        t = dt.datetime.strptime(r["time"], "%Y%m%d:%H%M") - dt.timedelta(hours=7)
        ts.append(t); p.append(r["P"]); tair.append(r.get("T2m", 20.0)); gi.append(r.get("G(i)", 0.0))
    return ts, np.array(p), np.array(tair), np.array(gi)

ts_s, p_kw, tair, gi = pvgis_hourly(LAT, LON, YEAR)   # P = W per 1 kWp installed
# PVGIS 'free' mount ~ ground; floating runs cooler -> small uplift on irradiated hours
gamma = -0.0035
cell_ground = tair + gi / 800.0 * (44 - 20)
cell_float = tair + gi / 800.0 * (44 - 20) * 0.82
uplift = np.where(gi > 5, (1 + gamma * (cell_float - 25)) / (1 + gamma * (cell_ground - 25)), 1.0)
fpv_per_mw = (p_kw / 1000.0) * uplift            # AC MW per installed MW_dc, hourly, full year
fpv_cf = float(fpv_per_mw.mean())
print(f"FPV: {len(fpv_per_mw)} h, CF={fpv_cf:.3f}, cooling uplift avg={float(uplift[gi>5].mean()):.3f}")

# ---------- Release from USGS 15-min -> hourly, full year ----------
def usgs_hourly(site, year):
    u = ("https://waterservices.usgs.gov/nwis/iv/?format=json"
         f"&sites={site}&parameterCd=00060&startDT={year}-01-01&endDT={year}-12-31")
    d = json.loads(urllib.request.urlopen(u, timeout=180).read())
    vals = d["value"]["timeSeries"][0]["values"][0]["value"]
    bucket = {}
    for v in vals:
        q = float(v["value"])
        if q < 0:
            continue
        t = dt.datetime.strptime(v["dateTime"][:13], "%Y-%m-%dT%H")  # truncate to hour
        bucket.setdefault(t, []).append(q)
    hrs = sorted(bucket)
    return hrs, np.array([np.mean(bucket[h]) for h in hrs])

hrs_r, rel_cfs = usgs_hourly(USGS, YEAR)
print(f"Release: {len(rel_cfs)} h, mean={rel_cfs.mean():.0f} cfs, min={rel_cfs.min():.0f}, max={rel_cfs.max():.0f}")

# ---------- align FPV and release on common hourly index ----------
# PVGIS stamps HH:10; USGS truncated to HH:00 -> key both by (month,day,hour), ignore minutes/year.
def key(t): return (t.month, t.day, t.hour)
idx = {key(t): i for i, t in enumerate(ts_s)}
hrs_r_arr = np.array(hrs_r)
mask = np.array([key(t) in idx for t in hrs_r])
rel = rel_cfs[mask]
fpv = np.array([fpv_per_mw[idx[key(t)]] for t in hrs_r_arr[mask]])
hours = np.array([h.hour for h in hrs_r_arr[mask]])
N = len(rel)
print(f"Aligned {N} hours")

# ---------- release decomposition: obligatory floor vs energy-driven swing ----------
floor = np.where((hours >= 7) & (hours < 19), FLOOR_DAY, FLOOR_NIGHT)
floor = np.minimum(floor, rel)                    # can't exceed actual release
energy_swing = np.clip(rel - floor, 0, None)      # FPV-replaceable component (cfs)
frac_energy = float(energy_swing.sum() / rel.sum())
# hydro generation proxy (MW), capped at nameplate
gen_mw = np.clip(rel / Q_AT_CAP * CAP_MW, 0, CAP_MW)
gen_floor_mw = np.clip(floor / Q_AT_CAP * CAP_MW, 0, CAP_MW)

# ---------- shared-interconnection export vs curtail, swept over FPV size ----------
def sim(fpv_gw):
    fmw = fpv * fpv_gw * 1000.0                    # FPV AC MW time series for this array size
    headroom = np.clip(CAP_MW - gen_mw, 0, CAP_MW) # path free after actual (evening-peaked) hydro
    export = np.minimum(fmw, headroom)
    curtail = np.clip(fmw - export, 0, None)
    # scenario B: hydro shifted to obligatory floor during solar hours -> more midday headroom
    headroom_shift = np.clip(CAP_MW - gen_floor_mw, 0, CAP_MW)
    export_shift = np.minimum(fmw, headroom_shift)
    curtail_shift = np.clip(fmw - export_shift, 0, None)
    tot = fmw.sum()
    return dict(fpv_gw=fpv_gw,
                fpv_twh=round(tot/1e6, 3),
                curtail_pct_actual_ops=round(float(curtail.sum()/tot*100), 1),
                curtail_pct_hydro_shifted=round(float(curtail_shift.sum()/tot*100), 1),
                export_twh_actual=round(float(export.sum()/1e6), 3))

sweep = [sim(g) for g in [0.5, 1.0, 2.0, 3.0, 5.0]]

# correlation FPV vs hydro generation (full chronological year, hourly)
corr = float(np.corrcoef(fpv, gen_mw)[0, 1])
# midday (10-15) vs evening (17-21) shares from the FULL series
mid = (hours >= 10) & (hours <= 15); eve = (hours >= 17) & (hours <= 21)
res = {
    "site": "Glen Canyon Dam / Lake Powell", "year": YEAR, "cap_mw": CAP_MW,
    "n_hours": N,
    "fpv_capacity_factor": round(fpv_cf, 3),
    "fpv_cooling_uplift_mean": round(float(uplift[gi > 5].mean()), 3),
    "release_mean_cfs": round(float(rel.mean()), 0),
    "release_min_cfs": round(float(rel.min()), 0),
    "release_max_cfs": round(float(rel.max()), 0),
    "frac_release_energy_driven": round(frac_energy, 3),
    "frac_release_obligatory_floor": round(1 - frac_energy, 3),
    "corr_fpv_vs_hydrogen_hourly": round(corr, 3),
    "hydro_gen_midday_share_mwh": round(float(gen_mw[mid].sum() / gen_mw.sum() * 100), 1),
    "hydro_gen_evening_share_mwh": round(float(gen_mw[eve].sum() / gen_mw.sum() * 100), 1),
    "fpv_output_midday_share": round(float(fpv[mid].sum() / fpv.sum() * 100), 1),
    "fpv_output_evening_share": round(float(fpv[eve].sum() / fpv.sum() * 100), 1),
    "interconnection_sweep": sweep,
    "notes": [
        "Chronological full-year sim, not hour-of-day averaged.",
        "Release floor = LTEMP 8000 day / 5000 night cfs = FPV-immune obligatory flow.",
        "corr<0 => FPV midday output is anti-correlated with the dam's evening-peaked generation "
        "=> they complement on the shared interconnection rather than compete.",
        "FPV does NOT reduce total release volume (delivery+LTEMP set it); it reshapes hourly "
        "release and supplies midday energy the dam would otherwise generate, freeing the water "
        "budget for the evening ramp and avoiding replacement-power purchases (ANL bug-flow finding).",
        "Hoover not simulated: Lake Mohave buffers it, no public high-res gage below the dam; "
        "ops research => ~100% of Hoover sub-daily swing is energy-driven (strongest FPV complement).",
    ],
}
with open(os.path.join(OUT, "hourly_fpv_hydro.json"), "w") as f:
    json.dump(res, f, indent=2)
print(json.dumps({k: res[k] for k in [
    "frac_release_energy_driven", "corr_fpv_vs_hydrogen_hourly",
    "hydro_gen_evening_share_mwh", "fpv_output_midday_share"]}, indent=2))
print("SWEEP:", json.dumps(sweep, indent=2))
print("WROTE outputs/hourly_fpv_hydro.json")

# ---------- figures (full-year, not averaged) ----------
try:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ORANGE, TEAL, RUST = "#c8632b", "#2b6b6b", "#8a3b1e"
    # (1) a representative summer week, chronological
    fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=False)
    # find a July week
    jul = [i for i, h in enumerate(np.array(hrs_r)[mask]) if h.month == 7 and 8 <= h.day <= 15]
    j0, j1 = jul[0], jul[-1]
    tt = np.arange(j1 - j0 + 1)
    ax[0].plot(tt, fpv[j0:j1+1] * CAP_MW, color=ORANGE, lw=1.8, label=f"FPV output (per {CAP_MW} MW array)")
    ax[0].plot(tt, gen_mw[j0:j1+1], color=TEAL, lw=1.8, label="Glen Canyon generation (proxy)")
    ax[0].fill_between(tt, gen_floor_mw[j0:j1+1], color=TEAL, alpha=0.15, label="obligatory floor (FPV-immune)")
    ax[0].set_title("Representative summer week (Jul 8-15, 2015) — chronological, hourly")
    ax[0].set_ylabel("MW"); ax[0].legend(fontsize=8, ncol=2); ax[0].grid(alpha=0.25)
    ax[0].set_xlabel("hour of week")
    # (2) FPV size vs curtailment (the offtake ceiling), from full-year sim
    gws = [s["fpv_gw"] for s in sweep]
    ax[1].plot(gws, [s["curtail_pct_actual_ops"] for s in sweep], "o-", color=RUST,
               label="hydro runs actual (evening-peaked) ops")
    ax[1].plot(gws, [s["curtail_pct_hydro_shifted"] for s in sweep], "s--", color=TEAL,
               label="hydro shifted to obligatory floor midday")
    ax[1].set_title("FPV curtailment vs array size on the dam's shared interconnection (full-year)")
    ax[1].set_xlabel("FPV array size (GW)"); ax[1].set_ylabel("% FPV energy curtailed")
    ax[1].legend(fontsize=8); ax[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "hourly_fpv_hydro.png"), dpi=160, bbox_inches="tight")
    print("WROTE figures/hourly_fpv_hydro.png")
except Exception as e:
    print("FIG FAIL:", str(e)[:200])
