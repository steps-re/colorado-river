#!/usr/bin/env python3
"""Coverage -> consequences, per Colorado River reservoir. Backs the interactive explorer.

THE QUESTION THIS ANSWERS
Upmanu Lall's position is that floating PV should cover 15-20% of reservoir surface, cutting
evaporation ~70% and yielding tens of GW. Our position is that the deployable array is bounded
near ~1-2 GW by OFFTAKE, which is only a couple of percent of surface. Both statements are
about the same slider. This model runs that slider so the divergence is visible instead of
argued: the WATER benefit rises linearly with coverage forever, while the ENERGY value hits a
wall at the dam's interconnection and stops.

METHOD (per reservoir, hourly, full year)
  solar(t)   PVGIS-NSRDB hourly PV per installed MW at the reservoir's own lat/lon (real weather,
             2015 radiation year), with a small floating water-cooling uplift.
  hydro(t)   the dam's own generation on the shared line. Glen Canyon uses a MEASURED sub-daily
             USGS release record; the other dams have no public sub-daily tailrace gage, so they
             use a documented load-following shape scaled to the plant's published average annual
             energy. Provenance is carried per reservoir into the output and shown on the page.
  headroom(t)= tie_MW - hydro(t) + onsite_load(t)   [only Havasu has a real on-site load]
  export(t)  = min(solar(t), headroom(t));  curtail(t) = solar(t) - export(t)
  price(t)   CAISO day-ahead LMP at the Palo Verde hub. A rational merchant curtails at
             negative prices, so revenue counts only positive-price hours.
  evap       coverage x suppression x open-water evaporation rate x surface area.

Outputs: outputs/fpv_coverage_explorer.json  (a coverage sweep per reservoir + parameters/sources)
Public APIs only (PVGIS, USGS, cached CAISO). ZERO Claude tokens.
"""
import json, csv, base64, datetime as dt, urllib.request
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"; CACHE = ROOT / "cache"
OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)

SOLAR_YEAR = 2015           # PVGIS-NSRDB radiation year used across the repo
PRICE_YEAR = 2024
# Both reviewers flagged pricing seven reservoirs off one California node. Palo Verde is the
# Desert Southwest trading hub and the correct reference for the Lower Basin; it is now the
# default. CAISO OASIS exposes it as a real intertie, but the Upper Basin balancing authorities
# (PacifiCorp East, PNM, WAPA Rocky Mountain) are not public there, so Flaming Gorge, Navajo and
# Blue Mesa still use Palo Verde as an ACKNOWLEDGED proxy rather than their own market.
PRICE_NODE = "PALOVERDE"
UPPER_BASIN_PROXY = {"Flaming Gorge", "Navajo Reservoir", "Blue Mesa"}
MW_PER_KM2 = 120.0          # FPV areal density (repo-wide constant)
SUPPRESS = 0.75             # evaporation suppressed over the COVERED area. Cut from 0.90 after
                            # both external reviewers flagged it: edge exchange, altered albedo and
                            # reduced wind mixing pull the basin-wide net below the directly-shaded
                            # figure. Range 0.60-0.90. Must stay in step with the page's JS.
AF_PER_KM2_PER_FT = 1e6 * 0.3048 / 1233.48   # 1 km2 x 1 ft -> AF
ACRE_KM2 = 0.00404686

# Economics (repo-consistent; see analysis/fpv_roi.py)
CAPEX_PER_W = 1.23          # ground-mount ~$1.10/W + ~$0.13/W float+mooring adder (WoodMac 2024)
OM_PER_MW_YR = 25_000.0
WACC, LIFE = 0.07, 25
CRF = WACC * (1 + WACC) ** LIFE / ((1 + WACC) ** LIFE - 1)

# ----------------------------------------------------------------------------------
# Reservoir parameters. Every number carries a source; screening estimates are flagged.
# ----------------------------------------------------------------------------------
RES = {
    "Lake Mead": dict(
        dam="Hoover Dam", lat=36.016, lon=-114.737, tie_mw=2080.0,
        annual_gwh=4000.0,
        surface_acres=83634, surface_src="Reclamation HDB 2017-2021 average surface area (LCR Evaporation Report 2023, Table 7)",
        evap_ft=6.22, evap_src="USGS DIRECT FLUX (eddy covariance + energy balance, Moreo & Swancar; Earp & Moreo 2021): 1,896 mm/yr = 6.22 ft/yr. This is a measured DEPTH, independent of surface area, so it is valid to apply to a separately-measured area. Reclamation HDB 2017-2021 implies 6.21 ft/yr over their larger area, which agrees.",
        evap_measured=True, hydro_provenance="synthetic load-following (no public sub-daily tailrace gage below Hoover)",
        onsite_load_mw=0.0,
        surface_status="NPS Lake Mead National Recreation Area",
        note="Lake Mohave buffers deliveries downstream, so nearly all of Hoover's sub-daily swing is energy-driven. LADWP has proposed a ~$3B / 2,000 MW Mohave-to-Mead pumped-storage scheme, the one real large daytime sink in the basin.",
        measured_area_2026=66975,
    ),
    "Lake Powell": dict(
        dam="Glen Canyon Dam", lat=36.937, lon=-111.483, tie_mw=1320.0,
        annual_gwh=2777.0,
        surface_acres=57342, surface_src="Sentinel-2 MNDWI summer water extent, 2022-2026 mean (analysis/ee_reservoirs.py)",
        evap_ft=5.83, evap_src="~70 in/yr, Reclamation/DRI measured programme (coloradoriverscience.org); our gridMET open-water screen gives 5.4-6.4 ft/yr",
        evap_measured=True, hydro_provenance="MEASURED: USGS 09380000 15-min release below Glen Canyon, 2015, aggregated hourly",
        onsite_load_mw=0.0,
        surface_status="NPS Glen Canyon National Recreation Area",
        note="No lower reservoir (the Grand Canyon is below), so on-site pump-back is unavailable. LTEMP minimum flows of 8,000 cfs day / 5,000 cfs night are FPV-immune. Surface has fallen 52% since 2019 and is the fastest-moving shoreline in the basin.",
        measured_area_2026=43850,
    ),
    "Lake Mohave": dict(
        dam="Davis Dam", lat=35.20, lon=-114.57, tie_mw=240.0,
        annual_gwh=1148.0,
        surface_acres=27022, surface_src="Reclamation LCRAS 2017-2021 average (LCR Evaporation Report 2023, Table 9)",
        evap_ft=5.64, evap_src="USGS DIRECT FLUX (eddy covariance, same programme as Lake Mead): 1,718 mm/yr = 5.64 ft/yr. A measured depth, area-independent. Supersedes the LCRAS area-quotient (140,735 AF / 27,022 ac = 5.21 ft/yr) which is NOT area-independent and should not be applied to a different area.",
        evap_measured=True, hydro_provenance="synthetic load-following (no public sub-daily tailrace gage below Davis)",
        onsite_load_mw=0.0,
        surface_status="NPS Lake Mead National Recreation Area",
        note="Held on a seasonal guide curve, so the surface barely moves year to year. That makes mooring far easier than at Mead or Powell, but the interconnection is small and the plant already runs at a high capacity factor.",
        measured_area_2026=None,
    ),
    "Lake Havasu": dict(
        dam="Parker Dam", lat=34.30, lon=-114.14, tie_mw=120.0,
        annual_gwh=457.0,
        surface_acres=18864, surface_src="Reclamation LCRAS 2017-2021 average (LCR Evaporation Report 2023, Table 10)",
        evap_ft=5.21, evap_src="WEAKEST RATE IN THE SET. No direct flux measurement exists for Havasu. This is an AREA QUOTIENT (LCRAS 98,246 AF / 18,864 ac), so it is only valid over the area it was derived from -- applying it to our smaller measured open water mixes denominators, and the true open-water depth is probably higher. Reclamation's alternative HDB figure (7.40 ft/yr) still uses 1950s pan coefficients and runs ~35% high by their own Table 10. Bracket Havasu as 5.2-7.4 ft/yr, not a point value.",
        evap_measured=True, hydro_provenance="synthetic load-following (no public sub-daily tailrace gage below Parker)",
        onsite_load_mw=300.0,
        onsite_load_src="CAP Mark Wilmer Pumping Plant: six 66,000 hp pumps, ~50 MW each, drawing from Lake Havasu; ~80% of CAP's ~2.8M MWh/yr. MWD's Whitsett Pumping Plant draws from the same reservoir.",
        surface_status="BLM / Arizona State Parks (NOT a National Park Service unit)",
        note="THE EXCEPTION. Havasu is the one Colorado River reservoir with a very large electrical load sitting on its own shoreline: CAP's Mark Wilmer plant lifts water 824 ft out of this lake, and MWD's Whitsett plant pumps into the Colorado River Aqueduct. Solar here can be consumed behind the meter instead of fighting for the dam's 120 MW line, and the surface is not NPS-managed.",
        measured_area_2026=None,
    ),
    "Flaming Gorge": dict(
        dam="Flaming Gorge Dam", lat=41.05, lon=-109.55, tie_mw=152.0,
        annual_gwh=457.0,
        surface_acres=42020, surface_src="Reclamation: surface area at normal water-surface elevation",
        evap_ft=3.3, evap_src="SCREENING ESTIMATE (elevation ~6,040 ft, cool high-desert climate). Not measured: Upper Basin reservoir evaporation is only now being instrumented under the UCRC/Reclamation Reservoir Evaporation Project.",
        evap_measured=False, hydro_provenance="synthetic load-following (no public sub-daily tailrace gage)",
        onsite_load_mw=0.0,
        surface_status="USFS Flaming Gorge National Recreation Area",
        note="Large surface for a small powerplant, which is the worst possible ratio for an offtake-bounded resource: lots of room for panels, almost no line to carry the power. Cold and high, so each covered acre also saves about half the water a Lower Basin acre would.",
        measured_area_2026=None,
    ),
    "Navajo Reservoir": dict(
        dam="Navajo Dam", lat=36.80, lon=-107.61, tie_mw=30.0,
        annual_gwh=90.0,
        surface_acres=15610, surface_src="Reclamation: surface area when filled",
        evap_ft=3.6, evap_src="SCREENING ESTIMATE (elevation ~6,085 ft). Not measured; part of the UCRC/Reclamation Upper Basin evaporation study.",
        evap_measured=False, hydro_provenance="synthetic load-following (no public sub-daily tailrace gage)",
        onsite_load_mw=0.0,
        surface_status="New Mexico / Colorado state parks",
        note="Reclamation's own project description lists no federal powerplant here; the ~30 MW plant was added later and is non-federal. The smallest line in the set against a substantial surface.",
        measured_area_2026=None,
    ),
    "Blue Mesa": dict(
        dam="Blue Mesa Dam", lat=38.45, lon=-107.33, tie_mw=86.4,
        annual_gwh=239.0,
        surface_acres=9180, surface_src="Reclamation: surface area at maximum water-surface elevation",
        evap_ft=2.8, evap_src="SCREENING ESTIMATE (elevation ~7,520 ft, coldest reservoir in the set). Not measured; part of the UCRC/Reclamation Upper Basin evaporation study.",
        evap_measured=False, hydro_provenance="synthetic load-following (no public sub-daily tailrace gage)",
        onsite_load_mw=0.0,
        surface_status="NPS Curecanti National Recreation Area",
        note="Coldest and highest reservoir here, so it evaporates least per acre and the water case is weakest. Deep drawdowns and winter ice add mooring cost that the Lower Basin lakes do not face.",
        measured_area_2026=None,
    ),
}

COVERAGE = [round(x, 4) for x in np.arange(0, 0.2501, 0.0025)]


# ----------------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------------
def pvgis_per_mw(lat, lon, year=SOLAR_YEAR):
    """Hourly AC MW per installed MW_dc, local (MST) hour order, with floating cooling uplift."""
    cf = CACHE / f"pvgis_{lat:.3f}_{lon:.3f}_{year}.npy"
    keyf = CACHE / f"pvgiskey_{lat:.3f}_{lon:.3f}_{year}.json"
    if cf.exists() and keyf.exists():
        return np.load(cf), json.loads(keyf.read_text())
    u = ("https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?"
         f"lat={lat}&lon={lon}&startyear={year}&endyear={year}&raddatabase=PVGIS-NSRDB"
         "&pvcalculation=1&peakpower=1&loss=14&angle=30&aspect=0&outputformat=json")
    d = json.loads(urllib.request.urlopen(u, timeout=180).read())
    ts, p, tair, gi = [], [], [], []
    for r in d["outputs"]["hourly"]:
        t = dt.datetime.strptime(r["time"], "%Y%m%d:%H%M") - dt.timedelta(hours=7)  # UTC -> MST
        ts.append(t); p.append(r["P"]); tair.append(r.get("T2m", 20.0)); gi.append(r.get("G(i)", 0.0))
    p = np.array(p); tair = np.array(tair); gi = np.array(gi)
    gamma = -0.0035
    cell_ground = tair + gi / 800.0 * (44 - 20)
    cell_float = tair + gi / 800.0 * (44 - 20) * 0.82
    uplift = np.where(gi > 5, (1 + gamma * (cell_float - 25)) / (1 + gamma * (cell_ground - 25)), 1.0)
    per_mw = (p / 1000.0) * uplift
    keys = [[t.month, t.day, t.hour] for t in ts]
    np.save(cf, per_mw); keyf.write_text(json.dumps(keys))
    return per_mw, keys


def hub_prices(keys):
    """Hourly day-ahead LMP at Palo Verde, falling back to SP15 only if the pull is incomplete.
    Missing hours take the hour-of-day median so a partial pull cannot silently zero revenue."""
    px, src = {}, None
    nodal = OUT / f"nodal_prices_{PRICE_YEAR}.json"
    if nodal.exists():
        d = json.loads(nodal.read_text()).get(PRICE_NODE, {})
        if len(d) > 8000:
            for k, v in d.items():
                m, dd, h = k.split("-")
                px[(int(m), int(dd), int(h))] = v
            src = f"CAISO OASIS day-ahead LMP at Palo Verde ({PRICE_NODE}), {PRICE_YEAR}"
    if not px:
        with open(OUT / f"sp15_{PRICE_YEAR}_hourly.csv") as f:
            for row in csv.reader(f):
                if len(row) < 4:
                    continue
                try:
                    px[(int(row[0]), int(row[1]), int(row[2]))] = float(row[3])
                except ValueError:
                    continue
        src = f"CAISO SP15 hub, {PRICE_YEAR} (Palo Verde pull incomplete)"
    byhour = {}
    for (m, d_, h), v in px.items():
        byhour.setdefault(h, []).append(v)
    med = {h: float(np.median(v)) for h, v in byhour.items()}
    out, miss = [], 0
    for m, d_, h in keys:
        if (m, d_, h) in px:
            out.append(px[(m, d_, h)])
        else:
            out.append(med.get(h, 0.0)); miss += 1
    return np.array(out), miss, len(px), src


def glen_canyon_hydro(keys, tie_mw, annual_gwh):
    """MEASURED Glen Canyon generation shape from USGS 15-min release, rescaled to the
    plant's CURRENT average annual energy (releases have fallen since the 2015 gage year)."""
    rel = np.load(CACHE / f"usgs_iv_09380000_{SOLAR_YEAR}.npy")
    if len(rel) != len(keys):
        rel = np.resize(rel, len(keys))
    gen = np.clip(rel / 31000.0 * tie_mw, 0, tie_mw)     # cfs -> MW proxy, capped at nameplate
    scale = (annual_gwh * 1000.0) / gen.sum()
    return np.clip(gen * scale, 0, tie_mw), float(scale)


def synthetic_hydro(keys, tie_mw, annual_gwh):
    """Load-following generation shape for dams with no public sub-daily tailrace gage.

    Shape only: a morning shoulder and a larger evening peak (the WAPA dispatch pattern), times
    a mild summer-heavy seasonal weight, normalised to the plant's published average annual
    energy. Deliberately conservative for this analysis -- a peakier dam leaves MORE midday
    headroom for solar, so a smooth shape understates rather than overstates FPV curtailment.
    """
    hours = np.array([k[2] for k in keys])
    months = np.array([k[0] for k in keys])
    diurnal = np.array([0.55, 0.50, 0.48, 0.47, 0.50, 0.60, 0.80, 0.95, 1.00, 0.95, 0.90, 0.88,
                        0.88, 0.90, 0.98, 1.10, 1.30, 1.55, 1.65, 1.55, 1.30, 1.05, 0.80, 0.65])
    seasonal = np.array([0.85, 0.85, 0.90, 0.95, 1.05, 1.20, 1.30, 1.30, 1.10, 0.95, 0.85, 0.85])
    w = diurnal[hours] * seasonal[months - 1]
    gen = w / w.sum() * (annual_gwh * 1000.0)            # MWh per hour == MW
    return np.clip(gen, 0, tie_mw), None


# ----------------------------------------------------------------------------------
# Sweep
# ----------------------------------------------------------------------------------
def measured_areas(recent_from=2024):
    """Sentinel-2 measured water-surface area, recent mean, per reservoir.

    Preferred over the published figures because it is ONE method across all seven. The
    published numbers mix conventions -- Reclamation five-year operating averages in the
    Lower Basin, FULL POOL in the Upper Basin -- and full pool overstates reservoirs that
    have been drawn down for years (Navajo and Blue Mesa are ~36% below it).
    """
    path = OUT / "ee_reservoir_area_all.csv"
    if not path.exists():
        return {}
    acc = {}
    for r in csv.DictReader(open(path)):
        if int(r["year"]) >= recent_from:
            acc.setdefault(r["lake"], []).append(float(r["water_acres"]))
    return {k: round(sum(v) / len(v)) for k, v in acc.items() if v}


MEASURED = measured_areas()


def run(p, solar, keys, price) -> dict:
    area_km2 = p["surface_acres"] * ACRE_KM2
    if p["hydro_provenance"].startswith("MEASURED"):
        hydro, _ = glen_canyon_hydro(keys, p["tie_mw"], p["annual_gwh"])
    else:
        hydro, _ = synthetic_hydro(keys, p["tie_mw"], p["annual_gwh"])
    onsite = p.get("onsite_load_mw", 0.0)
    # On-site pumping is not flat, but it is heavily daytime-weighted and is dispatchable
    # around the canal's own needs. Modelled as available in daylight hours only.
    onsite_t = np.where(solar > 0.02, onsite, 0.0)
    headroom = np.clip(p["tie_mw"] - hydro, 0, None) + onsite_t

    evap_total_af = area_km2 * p["evap_ft"] * AF_PER_KM2_PER_FT
    rows = []
    for c in COVERAGE:
        gw = c * area_km2 * MW_PER_KM2 / 1000.0
        mw = gw * 1000.0
        fpv = solar * mw
        gross = fpv.sum()
        # (1) PHYSICAL curtailment: the shared line is full. This is the offtake ceiling,
        #     and it is the quantity actually in dispute with Lall.
        deliverable = np.minimum(fpv, headroom)
        tx_curtailed = gross - deliverable.sum()
        # (2) ECONOMIC curtailment: deliverable energy a rational merchant declines to sell
        #     because the hub price is negative in that hour. Separate phenomenon, separate number --
        #     lumping the two would let a market artefact masquerade as a transmission limit.
        export = np.where(price > 0, deliverable, 0.0)
        exported = export.sum()
        econ_curtailed = deliverable.sum() - exported
        curtail_tx = 0.0 if gross <= 0 else float(tx_curtailed / gross * 100)
        curtail_econ = 0.0 if gross <= 0 else float(econ_curtailed / gross * 100)
        curtail_pct = curtail_tx + curtail_econ
        rev = float((export * price).sum())
        capture = 0.0 if exported <= 0 else rev / exported
        evap_af = c * SUPPRESS * evap_total_af
        capex = mw * 1e6 * CAPEX_PER_W
        ann_cost = capex * CRF + mw * OM_PER_MW_YR
        rows.append(dict(
            coverage_pct=round(c * 100, 3),
            covered_km2=round(c * area_km2, 2),
            gw=round(gw, 4),
            gross_twh=round(gross / 1e6, 4),
            export_twh=round(exported / 1e6, 4),
            curtail_pct=round(curtail_pct, 1),
            curtail_tx_pct=round(curtail_tx, 1),
            curtail_econ_pct=round(curtail_econ, 1),
            capture_usd_mwh=round(capture, 2),
            revenue_musd=round(rev / 1e6, 2),
            annual_cost_musd=round(ann_cost / 1e6, 2),
            net_musd=round((rev - ann_cost) / 1e6, 2),
            evap_saved_af=round(evap_af),
        ))
    # the coverage at which the shared line starts genuinely spilling solar (>10% physical)
    knee = next((r["coverage_pct"] for r in rows if r["curtail_tx_pct"] >= 10.0), None)

    # Hourly series so the page can re-run this sim live against user-set transmission
    # availability and co-located load, instead of being stuck with the assumptions baked in
    # here. Quantised to Int16 and base64'd: full 8,760-hour resolution matters because the
    # curtailment answer depends on solar, dam output and price moving together.
    def enc(arr, scale):
        q = np.clip(np.round(np.asarray(arr) * scale), -32768, 32767).astype("<i2")
        return base64.b64encode(q.tobytes()).decode()

    hourly = dict(
        n=len(solar),
        solar_b64=enc(solar, 10000), solar_scale=10000,      # AC MW per installed MW
        hydro_b64=enc(hydro, 10), hydro_scale=10,            # dam output, MW
        price_b64=enc(np.clip(price, -3276, 3276), 10), price_scale=10,   # $/MWh
        daylight_b64=base64.b64encode(
            (solar > 0.02).astype("<i2").tobytes()).decode(),
    )
    return dict(
        params=dict(
            dam=p["dam"], lat=p["lat"], lon=p["lon"], tie_mw=p["tie_mw"],
            annual_gwh=p["annual_gwh"],
            hydro_cf=round(p["annual_gwh"] * 1000 / (p["tie_mw"] * 8760), 3),
            surface_acres=p["surface_acres"], surface_km2=round(area_km2, 1),
            surface_src=p["surface_src"],
            published_acres=p.get("published_acres"), published_src=p.get("published_src"),
            evap_ft=p["evap_ft"], evap_src=p["evap_src"], evap_measured=p["evap_measured"],
            evap_total_af=round(evap_total_af),
            hydro_provenance=p["hydro_provenance"],
            onsite_load_mw=onsite, onsite_load_src=p.get("onsite_load_src"),
            surface_status=p["surface_status"], note=p["note"],
            measured_area_2026=p.get("measured_area_2026"),
            solar_cf=round(float(solar.mean()), 4),
            price_src=p.get("_price_src"),
            price_is_proxy=p.get("_price_proxy", False),
        ),
        curtail_knee_pct=knee,
        rows=rows,
        hourly=hourly,
    )


def main():
    out: dict = {}
    out["meta"] = dict(
        solar_year=SOLAR_YEAR, price_year=PRICE_YEAR, price_node=PRICE_NODE,
        mw_per_km2=MW_PER_KM2, evap_suppression=SUPPRESS,
        capex_per_w=CAPEX_PER_W, om_per_mw_yr=OM_PER_MW_YR, wacc=WACC, life_yr=LIFE,
        method=[
            "Hourly full-year sim per reservoir on the dam's own interconnection.",
            "solar(t): PVGIS-NSRDB per-MW at each reservoir's lat/lon with a floating cooling uplift.",
            "headroom(t) = nameplate - dam generation(t) + on-site load(t).",
            "export(t) = min(solar(t), headroom(t)); a rational merchant curtails negative-price hours.",
            "Prices are day-ahead LMP at Palo Verde, the Desert Southwest hub. The three Upper Basin "
            "reservoirs use it as an acknowledged proxy: their balancing authorities (PacifiCorp East, "
            "PNM, WAPA Rocky Mountain) do not publish hourly nodal prices.",
            "Wheeling and basis costs of moving power from each dam to a trading hub are NOT modelled, "
            "so the revenue side is optimistic.",
            "Evaporation saved = coverage x 0.75 suppression x open-water rate x surface area (range 0.60-0.90).",
        ],
        caveats=[
            "Curtailment here is the SHARED-LINE ceiling only. It assumes the dam's full nameplate "
            "is available to solar whenever the dam is not using it, which is generous: those lines "
            "carry firm hydropower contracts through 2057 and the region is a net importer at low water.",
            "Upper Basin evaporation rates (Flaming Gorge, Navajo, Blue Mesa) are screening estimates, "
            "not measurements. Reclamation and the UCRC are instrumenting them now.",
            "Only Glen Canyon has a measured sub-daily generation shape. The rest use a documented "
            "load-following profile scaled to published annual energy.",
            "Nothing here prices firm capacity, ancillary services, or avoided replacement power, "
            "which is where the real value of a dam-coupled array sits.",
            "No legal path currently exists to lease federal reservoir surface for private solar. "
            "That gate is institutional and is not modelled.",
        ])
    price_reported = False
    for name, p in RES.items():
        # Prefer the measured surface; keep the published figure for the provenance panel so
        # the difference stays visible rather than being quietly swapped in.
        p["published_acres"] = p["surface_acres"]
        p["published_src"] = p["surface_src"]
        if name in MEASURED:
            p["surface_acres"] = MEASURED[name]
            p["surface_src"] = (
                "MEASURED: Sentinel-2 MNDWI summer water extent, 2024-2026 mean, clipped to the "
                "reservoir's own footprint (analysis/ee_reservoir_areas.py). Used in preference to "
                "published areas so all seven reservoirs use one method and one recent period.")
        solar, keys = pvgis_per_mw(p["lat"], p["lon"])
        price, miss, have, price_src = hub_prices(keys)
        if not price_reported:
            print(f"PRICES: {price_src} | {have} priced hours, {miss} filled from hour-of-day median")
            price_reported = True
        p["_price_src"] = price_src
        p["_price_proxy"] = name in UPPER_BASIN_PROXY
        r = run(p, solar, keys, price)
        out[name] = r
        row3 = next(x for x in r["rows"] if abs(x["coverage_pct"] - 3.0) < 0.13)
        row15 = next(x for x in r["rows"] if abs(x["coverage_pct"] - 15.0) < 0.13)
        print(f"{name:18} tie={p['tie_mw']:>6.0f}MW  solarCF={r['params']['solar_cf']:.3f}  "
              f"txknee@{r['curtail_knee_pct']}%  | 3%: {row3['gw']:.2f}GW tx={row3['curtail_tx_pct']:>4.1f}% "
              f"evap={row3['evap_saved_af']:>6,}AF | 15%: {row15['gw']:.2f}GW tx={row15['curtail_tx_pct']:>4.1f}% "
              f"evap={row15['evap_saved_af']:>7,}AF")
    (OUT / "fpv_coverage_explorer.json").write_text(json.dumps(out, indent=1))
    print("\nWROTE outputs/fpv_coverage_explorer.json")


if __name__ == "__main__":
    main()
