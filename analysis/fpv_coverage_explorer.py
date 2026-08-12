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
             tie_MW is the powerplant nameplate, used as a proxy for the rating of the line
             leaving the dam. The two are usually close because the line was built for the
             plant, but they are not the same number and we have no public line rating.
  export(t)  = min(solar(t) x array_MW, headroom(t));  curtail(t) = solar(t) x array_MW - export(t)
             solar(t) is per installed MW, so it MUST be multiplied by array size before being
             compared with headroom in MW. The code does this; this line used to omit it.
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

# The corroboration sentence in Mead's evaporation provenance is built from the ingest output
# rather than typed, because it moves every time USGS publish another year. Missing file is
# fatal: a provenance string that silently drops its corroboration reads as never having had one.
_ME = json.loads((OUT / "usgs_mead_evap.json").read_text())
_MEC = _ME["published_depth_check"]
MEAD_EVAP_SRC = (
    "USGS DIRECT FLUX (eddy covariance + energy balance, Moreo & Swancar; Earp & Moreo 2021): "
    "1,896 mm/yr = 6.22 ft/yr. This is a measured DEPTH, independent of surface area, so it is "
    "valid to apply to a separately-measured area. Reclamation HDB 2017-2021 implies 6.21 ft/yr "
    "over their larger area, which agrees. Corroborated against the two later USGS data releases "
    "(2015-2020 and 2021-2023, ScienceBase doi:10.5066/P99GWPPG and doi:10.5066/P15HFPHB), which "
    f"extend the record from 2019 to {max(int(y) for y in _ME['annual_ft'])}. Aggregated the way "
    f"OFR 2021-1022 aggregates (most probable column, unweighted mean of complete calendar years), "
    f"{_MEC['n_years']} qualifying years give {_MEC['recomputed_corrected_ft']:.2f} ft/yr, "
    f"{abs(_MEC['delta_pct']):.1f}% {'above' if _MEC['delta_pct'] >= 0 else 'below'} the published "
    "depth and well inside the 5-8% flux uncertainty already carried. "
    + " ".join(f"{y} is held out because {r}." for y, r in sorted(_ME["meta"]["excluded_years"].items()))
    + " The published depth is kept because a peer-reviewed OFR value is stronger provenance than "
      "a mean we recompute off a data release; see outputs/usgs_mead_evap.json "
      "(analysis/usgs_mead_evap.py).")

# Lake Havasu's depth is no longer a raw accounting quotient. analysis/havasu_evap_bracket.py
# calibrates the LCRAS convention against measured eddy-covariance flux at the two lakes that have
# it, so what comes back is an estimate OF a flux depth and is area-independent in the way a bare
# quotient was not. Read rather than typed: it moves whenever the accounting series extends.
# The suppression RANGE belongs to the Monte Carlo, which owns the distribution. Restating it here
# is what let the published range sit at 0.60-0.90 for weeks after the floor moved to 0.30.
_SUPP_RANGE = json.loads((OUT / "fpv_uncertainty.json").read_text())["meta"]["distributions"]["suppression"].split(";")[0]

_HB = json.loads((OUT / "havasu_evap_bracket.json").read_text())
HAVASU_EVAP_FT = _HB["havasu"]["calibrated_ft_per_yr"]
HAVASU_EVAP_SRC = (
    "DERIVED from Reclamation's LCRAS accounting, calibrated against measured flux. There is no "
    "Lake Havasu flux station and USGS confirmed (2026-08-10) that one is only in planning, so the "
    "depth cannot be measured directly. LCRAS reports Mead, Mohave and Havasu on one convention "
    "and two of those three have eddy-covariance depths, so the convention is calibrated where it "
    "is checkable. Reclamation's published areas match the mean of their own daily record to 0.2% "
    "at Mead and 0.5% at Mohave, so the denominator is sound; the quotient nonetheless runs "
    f"{_HB['step2_and_3_calibration']['lakes']['Lake Mead']['quotient_vs_measured_pct']:.1f}% and "
    f"{_HB['step2_and_3_calibration']['lakes']['Lake Mohave']['quotient_vs_measured_pct']:.1f}% "
    "below measured flux at the two lakes, and the gap is precipitation, which consumptive-use "
    "accounting nets out. At Mead the mean gap is 0.42 ft/yr against 0.45 ft/yr of rain. The "
    "correction is therefore additive and physical rather than a fitted factor. "
    f"{_HB['verdict']['statement']} This supersedes an asserted 5.2-7.4 bracket. "
    f"{_HB['verdict']['direction_note']} See outputs/havasu_evap_bracket.json "
    "(analysis/havasu_evap_bracket.py).")

SOLAR_YEAR = 2015           # PVGIS-NSRDB radiation year used across the repo
PRICE_YEAR = 2024
# Both reviewers flagged pricing seven reservoirs off one California node. Palo Verde is the
# Desert Southwest trading hub and the correct reference for the Lower Basin; it is now the
# default. CAISO OASIS exposes it as a real intertie, but the Upper Basin balancing authorities
# (PacifiCorp East, PNM, WAPA Rocky Mountain) are not public there, so Flaming Gorge, Navajo and
# Blue Mesa still use Palo Verde as an ACKNOWLEDGED proxy rather than their own market.
# Per-reservoir price node, assigned to the balancing authority the dam actually sits in.
# Found via CAISO's APNode atlas (queryname=ATL_APNODE); the EDAM load aggregation points
# "ELAP_*" carry real prices for external balancing authorities, unlike the EIM intertie names.
# AZPS, NEVP and PNM measure within $0.30/MWh of each other over 2024, so the choice among
# them is immaterial; Palo Verde is the outlier, running $7.91/MWh LOWER at midday with a third
# more negative-price hours, which is why using it basin-wide was wrong.
PRICE_NODE_BY_RESERVOIR = {
    "Lake Mead":        "NEVP",              # Hoover, southern Nevada
    "Lake Mohave":      "AZPS",              # Davis, AZ/NV border
    "Lake Havasu":      "AZPS",              # Parker, Arizona
    "Lake Powell":      "AZPS",              # Glen Canyon, Arizona
    "Navajo Reservoir": "PNM",               # Navajo Dam, New Mexico
    "Flaming Gorge":    "PACE_transferred",  # PacifiCorp East, shape-transferred
    "Blue Mesa":        "SWPW_transferred",  # SPP RTO West, shape-transferred
}
# Series that are shape-transferred rather than measured, and must be labelled as such.
TRANSFERRED = {"PACE_transferred", "SWPW_transferred"}
MW_PER_KM2 = 120.0          # FPV areal density (repo-wide constant)
SUPPRESS = 0.75             # evaporation suppressed over the COVERED area. Cut from 0.90 after
                            # both external reviewers flagged it: edge exchange, altered albedo and
                            # reduced wind mixing pull the basin-wide net below the directly-shaded
                            # figure. This is the MODE. The uncertainty range is owned by
                            # fpv_uncertainty.py and read from it below, never restated here: the
                            # floor was widened 0.60 -> 0.30 in round 6 and this file went on
                            # publishing 0.60 for weeks. Must stay in step with the page's JS.
AF_PER_KM2_PER_FT = 1e6 * 0.3048 / 1233.48   # 1 km2 x 1 ft -> AF
ACRE_KM2 = 0.00404686

# Economics (repo-consistent; see analysis/fpv_roi.py)
#
# NO INVESTMENT TAX CREDIT IS APPLIED, and that is a finding rather than an omission.
# The One Big Beautiful Bill Act (enacted 4 July 2025) terminates the section 48E credit for
# solar placed in service after 31 December 2027, with a carve-out only for projects that began
# construction on or before 4 July 2026. That window has closed. Reservoir FPV has no federal
# surface-leasing path, no completed NEPA review and no interconnection study at any of these
# sites, so no such project began construction before the deadline, and none could be placed in
# service inside 2027 against a 5-10 year development timeline. Modelling a 30-50% ITC here
# would credit these projects with money the law no longer makes available to them.
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
        evap_ft=6.22, evap_src=MEAD_EVAP_SRC,
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
        evap_ft=HAVASU_EVAP_FT, evap_src=HAVASU_EVAP_SRC,
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


def load_price_series():
    """Every available price series, keyed by node label."""
    out = {}
    p1 = OUT / f"nodal_prices_{PRICE_YEAR}.json"
    if p1.exists():
        for node, d in json.loads(p1.read_text()).items():
            if len(d) > 8000:
                out[node] = d
    p2 = OUT / "nodal_prices_upper.json"
    if p2.exists():
        for node, d in json.loads(p2.read_text()).items():
            if isinstance(d, dict) and len(d.get("series", {})) > 8000:
                out[node] = d["series"]
                out[node + "__meta"] = {k: v for k, v in d.items() if k != "series"}
    return out


SERIES = load_price_series()


def hub_prices(keys, reservoir):
    """Hourly day-ahead LMP for this reservoir's own balancing authority.

    Falls back to Palo Verde only if the assigned node is unavailable, and says so, because a
    silent fallback is exactly how the wrong price ended up on seven reservoirs the first time.
    """
    want = PRICE_NODE_BY_RESERVOIR.get(reservoir)
    node = want if want in SERIES else ("PALOVERDE" if "PALOVERDE" in SERIES else None)
    if node is None:
        raise RuntimeError("no price series available; run analysis/fetch_nodal_prices.py")
    raw = SERIES[node]
    px = {}
    for k, v in raw.items():
        m, d_, h = k.split("-")
        px[(int(m), int(d_), int(h))] = v
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
    transferred = node in TRANSFERRED
    meta = SERIES.get(node + "__meta", {})
    if transferred:
        src = (f"{node}: hour-of-day ratio from measured local prices over "
               f"{meta.get('reference','a reference node')} applied to a full {PRICE_YEAR} year. "
               "SHAPE-TRANSFERRED, not measured.")
    elif node != want:
        src = f"{node} (FALLBACK: {want} unavailable)"
    else:
        src = f"CAISO day-ahead LMP, {node} balancing authority, {PRICE_YEAR}"
    return np.array(out), miss, len(px), src, transferred


def glen_canyon_hydro(keys, tie_mw, annual_gwh):
    """MEASURED Glen Canyon generation shape from USGS 15-min release, rescaled to the
    plant's CURRENT average annual energy (releases have fallen since the 2015 gage year)."""
    rel = np.load(CACHE / f"usgs_iv_09380000_{SOLAR_YEAR}.npy")
    if len(rel) != len(keys):
        rel = np.resize(rel, len(keys))
    gen = np.clip(rel / 31000.0 * tie_mw, 0, tie_mw)     # cfs -> MW proxy, capped at nameplate
    scale = (annual_gwh * 1000.0) / gen.sum()
    return np.clip(gen * scale, 0, tie_mw), float(scale)


def measured_release_hydro(keys, tie_mw, annual_gwh, name):
    """Generation shape driven by Reclamation's MEASURED daily releases.

    The synthetic shape below assumes a seasonal weight, summer-heavy, on the reasoning that
    power demand peaks then. Rule-curve reservoirs do not work that way: releases are set by
    water obligations, equalisation tiers and downstream orders, not by power prices, so the
    months when the shared line is busy are an operational fact rather than something to assume.
    Reclamation publishes daily release for six of the seven reservoirs here, so the seasonal and
    day-to-day pattern is now measured and only the within-day shape is still modelled. That is
    the right division: there is no public sub-daily tailrace gage except below Glen Canyon.

    Uses the average release for each calendar day across 2015-2026, so a single wet or dry year
    does not set the pattern.
    """
    f = OUT / "basin_daily.json"
    if not f.exists():
        return None
    B = json.loads(f.read_text())["reservoirs"].get(name)
    if not B:
        return None
    rel = B["daily"].get("release_cfs") or []
    dates = B["daily"]["date"]
    acc = {}
    for dt, v in zip(dates, rel):
        if v is None or not np.isfinite(v) or v < 0:
            continue
        acc.setdefault((int(dt[5:7]), int(dt[8:10])), []).append(v)
    if len(acc) < 300:
        return None
    daily = {k: float(np.mean(v)) for k, v in acc.items()}
    med = float(np.median(list(daily.values()))) or 1.0
    w_day = np.array([daily.get((k[0], k[1]), med) for k in keys], dtype=float)
    diurnal = np.array([0.55, 0.50, 0.48, 0.47, 0.50, 0.60, 0.80, 0.95, 1.00, 0.95, 0.90, 0.88,
                        0.88, 0.90, 0.98, 1.10, 1.30, 1.55, 1.65, 1.55, 1.30, 1.05, 0.80, 0.65])
    hours = np.array([k[2] for k in keys])
    w = w_day * diurnal[hours]
    if not np.isfinite(w).all() or w.sum() <= 0:
        return None
    gen = w / w.sum() * (annual_gwh * 1000.0)
    return np.clip(gen, 0, tie_mw)


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

def bathymetric_areas(window=("2024", "2025", "2026")):
    """Daily surface area from Reclamation's own elevation and storage records.

    Supersedes the satellite composite as the model's area of record. The satellite reads LOW at
    every reservoir, by 4.6% at Mohave up to 25.9% at Powell, because MNDWI at 30 m loses narrow
    canyon arms, shadowed banks and mixed shoreline pixels, and Powell has the most convoluted
    shoreline in the set. Six rounds of review suspected this and none measured it.

    Returns mean area over the same May-September window the composite used, so the comparison is
    like for like, plus the annual mean and the within-year swing. Havasu is excluded: it is held
    within 4 ft, so its hypsometry cannot be recovered and its published area stands.
    """
    f = OUT / "basin_daily.json"
    if not f.exists():
        return {}
    B = json.loads(f.read_text())["reservoirs"]
    out = {}
    for name, r in B.items():
        if not r["stage_area"]["reliable"]:
            continue
        d = r["daily"]
        summer = [a for dt, a in zip(d["date"], d["area_acres"])
                  if dt[:4] in window and "05" <= dt[5:7] <= "09"]
        annual = [a for dt, a in zip(d["date"], d["area_acres"]) if dt[:4] in window]
        if not summer or not annual:
            continue
        out[name] = dict(summer_mean=round(sum(summer) / len(summer)),
                         annual_mean=round(sum(annual) / len(annual)),
                         swing_pct=r["area_acres"]["intra_2024_swing_pct"],
                         hypsometry=r["stage_area"]["hypsometry"])
    return out


BATHY = bathymetric_areas()



def run(p, solar, keys, price) -> dict:
    area_km2 = p["surface_acres"] * ACRE_KM2
    if p["hydro_provenance"].startswith("MEASURED"):
        hydro, _ = glen_canyon_hydro(keys, p["tie_mw"], p["annual_gwh"])
    else:
        meas = measured_release_hydro(keys, p["tie_mw"], p["annual_gwh"], p["_name"])
        if meas is not None:
            hydro = meas
            p["hydro_provenance"] = (
                "MEASURED daily release (Reclamation, 2015-2026 per-calendar-day mean) shaping "
                "the seasonal and day-to-day pattern; within-day shape still modelled as "
                "load-following, since no public sub-daily tailrace gage exists here.")
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
            satellite_acres=p.get("satellite_acres"), satellite_gap_pct=p.get("satellite_gap_pct"),
            area_swing_pct=p.get("area_swing_pct"),
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
        solar_year=SOLAR_YEAR, price_year=PRICE_YEAR, price_nodes=PRICE_NODE_BY_RESERVOIR,
        mw_per_km2=MW_PER_KM2, evap_suppression=SUPPRESS,
        capex_per_w=CAPEX_PER_W, om_per_mw_yr=OM_PER_MW_YR, wacc=WACC, life_yr=LIFE,
        method=[
            "Hourly full-year sim per reservoir on the dam's own interconnection.",
            "area: DAILY surface from Reclamation elevation and storage, with area taken as the "
            "derivative of a fitted hypsometry V=a(h-h0)^b. Supersedes our own Sentinel-2 "
            "composite, which read low at every reservoir (Mohave -4.6% to Powell -25.9%) because "
            "a 30 m water mask loses narrow canyon arms. Lake Havasu keeps a published static "
            "area: it is held within 4 ft so its hypsometry cannot be recovered.",
            "hydro(t): shaped by MEASURED daily release (Reclamation, per-calendar-day mean "
            "2015-2026) at six reservoirs, so the seasonal and day-to-day pattern is operational "
            "fact rather than an assumed summer-heavy weight. Only the within-day shape is still "
            "modelled. Glen Canyon uses its measured 15-minute record. Havasu has no published "
            "release series and keeps a modelled shape.",
            "evaporation drivers: Penman open-water decomposition on NASA POWER daily weather "
            "puts the aerodynamic term at 44-47% of demand depending on reanalysis. Levels still "
            "come from measured flux, because combination equations without a heat-storage term "
            "overestimate by a documented 24-36%.",
            "solar(t): PVGIS-NSRDB per-MW at each reservoir's lat/lon with a floating cooling uplift.",
            "headroom(t) = nameplate - dam generation(t) + on-site load(t). Nameplate is the "
            "powerplant rating used as a proxy for the line out of the dam; no public line rating exists.",
            "export(t) = min(solar(t) x array_MW, headroom(t)); solar(t) is per installed MW and must be "
            "scaled by array size before comparison with headroom in MW. A rational merchant "
            "curtails negative-price hours.",
            "Prices are day-ahead LMP at EACH RESERVOIR'S OWN balancing authority: Lake Mead on "
            "NEVP, the Arizona dams on AZPS, Navajo on PNM, all measured full-year. Flaming Gorge "
            "and Blue Mesa use a series SHAPE-TRANSFERRED from a June-July 2026 hour-of-day ratio "
            "against a reference node, because their markets produced no day-ahead prices before "
            "2026. Those two are modelled, not measured, and winter is the least reliable part.",
            "Wheeling is NOT applicable: transmission access charges in these markets are billed to "
            "load rather than generators, and nodal prices already carry congestion and losses. "
            "Generator interconnection and local network upgrades ARE modelled, from Berkeley Lab "
            "project data, defaulting to the $30/kW median for completed projects.",
            f"Evaporation saved = coverage x {SUPPRESS} suppression x open-water rate x surface "
            f"area ({_SUPP_RANGE}).",
        ],
        caveats=[
            "Curtailment here is the SHARED-LINE ceiling only. It assumes the dam's full nameplate "
            "is available to solar whenever the dam is not using it, which is generous: those lines "
            "carry firm hydropower contracts through 2057 and the region is a net importer at low water.",
            "Upper Basin evaporation rates (Flaming Gorge, Navajo, Blue Mesa) are screening estimates, "
            "not measurements. Reclamation and the UCRC are instrumenting them now.",
            "Only Glen Canyon has a measured sub-daily generation shape. The rest use a documented "
            "load-following profile scaled to published annual energy.",
            "Firm capacity is priced on the BATTERY only, at a CAISO resource-adequacy proxy. The solar "
            "array receives no capacity credit, and no ancillary services or avoided "
            "replacement power are priced anywhere. At the capacity values used, a four-hour "
            "battery covers its own cost from capacity payments alone, so combined figures must "
            "be read alongside the array-only figures rather than instead of them.",
            "No legal path currently exists to lease federal reservoir surface for private solar. "
            "That gate is institutional and is not modelled.",
        ])
    price_reported = False
    for name, p in RES.items():
        p["_name"] = name
        # Prefer the measured surface; keep the published figure for the provenance panel so
        # the difference stays visible rather than being quietly swapped in.
        p["published_acres"] = p["surface_acres"]
        p["published_src"] = p["surface_src"]
        if name in MEASURED:
            p["satellite_acres"] = MEASURED[name]
        if name in BATHY:
            b = BATHY[name]
            p["surface_acres"] = b["annual_mean"]
            p["area_swing_pct"] = b["swing_pct"]
            p["satellite_gap_pct"] = (round(p["satellite_acres"] / b["summer_mean"] * 100 - 100, 1)
                                      if p.get("satellite_acres") else None)
            p["surface_src"] = (
                "MEASURED: annual mean of daily surface area 2024-2026, from Reclamation daily "
                "elevation and storage with area taken as the derivative of a fitted hypsometry "
                "V = a(h-h0)^b (analysis/fetch_basin_daily.py). Supersedes our own Sentinel-2 "
                "composite, which reads low at every reservoir because a 30 m water mask loses "
                "narrow canyon arms and shadowed banks.")
        elif name in MEASURED:
            p["surface_acres"] = MEASURED[name]
            p["surface_src"] = (
                "MEASURED: Sentinel-2 MNDWI summer water extent, 2024-2026 mean. Retained here "
                "because this reservoir is held within a few feet, so its hypsometry cannot be "
                "recovered from the elevation record.")
        solar, keys = pvgis_per_mw(p["lat"], p["lon"])
        price, miss, have, price_src, price_transferred = hub_prices(keys, name)
        if not price_reported:
            price_reported = True
        print(f"  price: {price_src[:96]}" + (f" | {miss} h gap-filled" if miss else ""))
        p["_price_src"] = price_src
        p["_price_proxy"] = price_transferred
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
