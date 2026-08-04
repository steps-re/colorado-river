"""Forward-market Monte Carlo for FPV (+ optional BESS) at Glen Canyon Dam.

Answers the question the NSF white paper needs and the prior static model could not:
what happens to FPV economics as grid-scale PV and BESS keep arriving, and as the
post-2026 Colorado River guidelines reset Lake Powell releases.

Structure (reduced form, screening grade -- NOT a production-cost model):

  1. Net load      NL(h) = Load(h) - Solar(h) - Wind(h)     [regional, GW]
     Load  = stylized WECC-DSW/CAISO shape scaled to a regional peak, grown per scenario.
     Solar = real PVGIS irradiance shape at the lake, diversity-smoothed, x installed GW.
  2. Storage       daily greedy arbitrage on NL: charge in the lowest-NL hours,
                   discharge in the highest, subject to power (GW), 4h energy, eta.
  3. Price         monotone map NL -> $/MWh, fitted by quantile matching on the base
                   year (2024 SP15 observed prices vs base-year NL), then applied to
                   future NL. Extrapolates: deeper surplus -> more negative hours,
                   tighter net peak -> scarcity prices. Scaled by a gas-price factor.
  4. Dam           Lake Powell annual release (maf) -> hourly release -> hydro MW ->
                   tie headroom for FPV. Release scenarios follow the Post-2026
                   Final EIS (31 Jul 2026) sideboards.

                   IMPORTANT CAVEAT (added 2026-08-04 after checking the actual
                   transmission position): "headroom" here is PHYSICAL headroom,
                   nameplate minus hydro output. It is NOT available transfer
                   capability. WAPA owns the Glen Canyon switchyard and the outgoing
                   345 kV / 230 kV lines, and its firm-electric-service preference
                   customers hold contractual Existing Transmission Commitments on
                   them even in hours when the dam is generating far below nameplate,
                   because WAPA must be able to deliver when water IS released.
                   ATC = TTC - ETC - TRM - CBM, and on a fully subscribed CRSP system
                   the real number available to a new injector is plausibly near zero
                   without a negotiated arrangement. The named pathway is Surplus
                   Interconnection Service under FERC Order 845, which WAPA has adopted
                   and processes out-of-queue -- but Glen Canyon predates modern LGIAs,
                   so it needs a bespoke multi-party agreement between Reclamation,
                   WAPA merchant, WAPA transmission and the developer.
                   Treat every tie-limited number in this model as an UPPER BOUND.
  5. Economics     FPV export limited by headroom, economic curtailment below $0,
                   optional co-located BESS, energy + capacity (RA) revenue,
                   capex/O&M/ITC -> NPV and IRR over the asset life.

Monte Carlo samples buildout rates, load growth, gas, RA price, capex and hydrology.

Runs on cached public data (PVGIS, USGS, CAISO). Pure numpy. ZERO LLM tokens.

Usage:  python3 analysis/fpv_forward_mc.py [n_draws]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

REPO = os.path.expanduser("~/code/steps/colorado-river")
CACHE, OUT = os.path.join(REPO, "cache"), os.path.join(REPO, "outputs")
os.makedirs(OUT, exist_ok=True)

RNG = np.random.default_rng(20260804)

# ---------------------------------------------------------------- dam constants
CAP_MW = 1320.0          # Glen Canyon nameplate
Q_AT_CAP = 31000.0       # cfs at full powerplant capacity
FLOOR_DAY, FLOOR_NIGHT = 8000.0, 5000.0   # LTEMP minimum flows
MAF_PER_CFS_YR = 1.9835 * 365 / 1e6       # 1 cfs sustained for a year = 723.9 AF

# Post-2026 Final EIS (31 Jul 2026) Preferred Alternative sideboards on Powell release.
# Adaptive 2-year framework: 8.0 maf if Powell >= 3,540 ft on Oct 1, else 7.0 maf,
# with outer sideboards of 5.0 to 12.0 maf. Verify against the Final EIS before citing.
RELEASE_SCENARIOS = {
    "consensus_8.23maf": dict(maf=8.23, p=0.05, note="legacy 2007-guidelines normal year"),
    "prefalt_wet_8.0":   dict(maf=8.00, p=0.28, note="Powell >= 3,540 ft on Oct 1"),
    "prefalt_dry_7.0":   dict(maf=7.00, p=0.43, note="Powell < 3,540 ft on Oct 1"),
    "prefalt_deep_6.0":  dict(maf=6.00, p=0.19, note="sustained drought inside sideboards"),
    "prefalt_floor_5.0": dict(maf=5.00, p=0.05, note="lower sideboard, protects 3,490 ft power pool"),
}

# --------------------------------------------------------------- base-year grid
# Regional slice this FPV would sell into (CAISO + Desert SW merchant footprint).
BASE_YEAR = 2024
BASE_PEAK_LOAD_GW = 75.0     # CAISO + Desert SW coincident peak, GW
BASE_SOLAR_GW = 32.0         # installed utility-scale PV in the slice, 2024
BASE_STORAGE_GW = 11.0       # installed 4h BESS power, 2024 (CAISO ~16.1 GW by mid-2026)
BASE_WIND_GW = 6.0
STORAGE_HOURS, ETA_RT = 4.0, 0.85
SOLAR_DIVERSITY = 0.82       # fleet-wide shape is flatter than one site's irradiance


def load_cached():
    fpv = np.load(os.path.join(CACHE, "fpv_per_mw_2015.npy"))      # MW per MW installed
    rel = np.load(os.path.join(CACHE, "rel_cfs_2015.npy"))
    hrs = json.load(open(os.path.join(CACHE, "ts_rel.json")))
    hour = np.array([int(h[11:13]) for h in hrs])
    month = np.array([int(h[5:7]) for h in hrs])
    doy = np.arange(len(hour)) // 24
    return fpv, rel, hour, month, doy


def base_prices():
    """Observed SP15 2024 hourly LMP laid onto the 2015 (365-day) calendar used by the
    cached solar and release series, gap-filled by month/hour-of-day means."""
    import csv
    raw = {}
    with open(os.path.join(OUT, "sp15_2024_hourly.csv")) as f:
        for m, d, h, p in csv.reader(f):
            raw[(int(m), int(d), int(h))] = float(p)
    mean_all = float(np.mean(list(raw.values())))
    by_mh = {}
    for (m, _, h), p in raw.items():
        by_mh.setdefault((m, h), []).append(p)
    by_mh = {k: float(np.mean(v)) for k, v in by_mh.items()}
    out = []
    for m, ndays in zip(range(1, 13), [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]):
        for d in range(1, ndays + 1):
            for h in range(24):
                out.append(raw.get((m, d, h), by_mh.get((m, h), mean_all)))
    return np.array(out)


def load_shape(hour, month, peak_gw):
    """Stylized regional load: summer-peaking, evening-peaking, in GW."""
    seas = np.array([0.86, 0.84, 0.83, 0.84, 0.92, 1.06, 1.00, 1.00, 0.95, 0.85, 0.83, 0.88])[month - 1]
    # double-humped diurnal with a dominant evening peak
    diur = (0.62
            + 0.16 * np.exp(-0.5 * ((hour - 9) / 2.6) ** 2)
            + 0.38 * np.exp(-0.5 * ((hour - 19) / 2.4) ** 2)
            + 0.10 * np.exp(-0.5 * ((hour - 14) / 3.2) ** 2))
    s = seas * diur
    return s / s.max() * peak_gw


def wind_shape(hour, doy, gw):
    d = 0.55 + 0.30 * np.sin(2 * np.pi * (hour - 3) / 24) + 0.15 * np.sin(2 * np.pi * doy / 365)
    return np.clip(d, 0.05, 1.0) * gw * 0.9


def dispatch_storage(nl, power_gw, hours=STORAGE_HOURS, eta=ETA_RT, slices=16,
                     price_map=None, gas_factor=1.0, cycle_cost=4.0):
    """Daily storage arbitrage on net load, as valley-filling / peak-shaving.

    Storage moves energy from the highest-net-load hour to the lowest, one slice at a
    time, and STOPS when the spread closes. That saturation matters: a naive
    "charge in the N cheapest hours, discharge in the N dearest" rule keeps pushing
    once storage is large relative to the system and inverts the duck curve, which
    produces nonsense prices at high penetration. Respects per-hour power limits and
    the daily energy budget. Vectorized across days.
    """
    if power_gw <= 0:
        return nl.copy()
    day = nl.copy().reshape(-1, 24)
    nd = day.shape[0]
    chg_used = np.zeros_like(day)     # GWh charged into each hour
    dis_used = np.zeros_like(day)     # GWh discharged out of each hour
    budget = np.full(nd, power_gw * hours)   # GWh/day of charging energy
    step = power_gw * hours / slices
    rows = np.arange(nd)
    for _ in range(slices):
        # cheapest hour that still has charging headroom, dearest with discharge headroom
        lo = np.where(chg_used < power_gw - 1e-9, day, np.inf)
        hi = np.where(dis_used < power_gw - 1e-9, day, -np.inf)
        ci, di = np.argmin(lo, axis=1), np.argmax(hi, axis=1)
        pc, pd = day[rows, ci], day[rows, di]
        # stop on days where the spread has closed or headroom/budget is gone
        room_c = power_gw - chg_used[rows, ci]
        room_d = (power_gw - dis_used[rows, di]) / eta
        # do not overshoot equalization: moving `s` closes the gap by s*(1+eta)
        gap = np.clip((pd - pc) / (1.0 + eta), 0, None)
        s = np.minimum.reduce([np.full(nd, step), budget, room_c, room_d, gap])
        ok = np.isfinite(pc) & np.isfinite(pd) & (pd > pc)
        if price_map is not None:
            # merchant stopping rule: eta*P_sell - P_buy - cycle_cost > 0
            nlk, pk, peak = price_map
            p_buy = apply_price_map(pc / peak, nlk, pk, gas_factor)
            p_sell = apply_price_map(pd / peak, nlk, pk, gas_factor)
            ok &= (eta * p_sell - p_buy - cycle_cost) > 0
        s = np.where(ok, s, 0.0)
        day[rows, ci] += s
        day[rows, di] -= s * eta
        chg_used[rows, ci] += s
        dis_used[rows, di] += s * eta
        budget -= s
    return day.reshape(-1)


def fit_price_map(nl_base, p_base):
    """Monotone NL -> price via quantile matching on the base year."""
    return np.sort(nl_base), np.sort(p_base)


def apply_price_map(nl, nl_knots, p_knots, gas_factor=1.0,
                    floor=-60.0, ceil=350.0):
    """Interpolate, and extrapolate linearly at both tails so that structurally
    new surplus produces new negative hours and new tightness produces scarcity.

    `nl` and `nl_knots` are NORMALIZED net load (net load / regional peak load).
    Normalizing is what makes this a capacity-expansion-consistent model: pure load
    growth scales numerator and denominator together and leaves prices flat, which is
    what happens in reality when firm capacity is built to hold the reserve margin.
    Only CHANGES IN SHAPE -- solar depth, storage fill -- move the price series."""
    p = np.interp(nl, nl_knots, p_knots)
    lo_slope = (p_knots[len(p_knots) // 20] - p_knots[0]) / max(
        1e-6, nl_knots[len(nl_knots) // 20] - nl_knots[0])
    hi_slope = (p_knots[-1] - p_knots[-len(p_knots) // 20]) / max(
        1e-6, nl_knots[-1] - nl_knots[-len(nl_knots) // 20])
    below, above = nl < nl_knots[0], nl > nl_knots[-1]
    p[below] = p_knots[0] + lo_slope * (nl[below] - nl_knots[0])
    p[above] = p_knots[-1] + hi_slope * (nl[above] - nl_knots[-1])
    # Gas sets the marginal energy cost when thermal is on the margin. Negative
    # prices come from surplus/PTC bidding, not from gas, so do not scale them.
    p = np.where(p > 0, p * gas_factor, p)
    return np.clip(p, floor, ceil)


def hydro_mw(rel_cfs, target_maf):
    """Scale the observed release shape to a scenario annual volume, keeping the
    LTEMP floor intact, then convert to generation MW."""
    base_maf = rel_cfs.mean() * MAF_PER_CFS_YR
    hour = np.arange(len(rel_cfs)) % 24
    floor = np.where((hour >= 7) & (hour < 19), FLOOR_DAY, FLOOR_NIGHT)
    floor = np.minimum(floor, rel_cfs)
    swing = rel_cfs - floor
    # shrink or grow the energy-driven swing to hit the target volume; if the target
    # is below the floor volume, scale the floor down too (deep-shortage operations)
    floor_maf = floor.mean() * MAF_PER_CFS_YR
    if target_maf >= floor_maf:
        k = (target_maf - floor_maf) / max(1e-9, base_maf - floor_maf)
        rel = floor + swing * k
    else:
        rel = floor * (target_maf / floor_maf)
    return np.clip(rel / Q_AT_CAP * CAP_MW, 0, CAP_MW), rel


# ------------------------------------------------------------------- scenarios
BUILDOUT = {
    #                     solar GW/yr, storage GW/yr, load growth %/yr
    # DSW alone realistically adds 1.5-2.5 GW/yr of solar through 2030 (WECC 2024);
    # CAISO storage grew 42% YoY to 16.1 GW by early 2026. These span CAISO + DSW.
    # organic = shape-following load growth/yr; dc = ANNOUNCED flat data-center GW/yr
    # (multiplied by a separately sampled realization factor)
    "conservative": dict(solar=2.0, stor=1.5, organic=0.006, dc=1.0),
    "moderate":     dict(solar=3.5, stor=2.8, organic=0.009, dc=2.0),
    "aggressive":   dict(solar=5.5, stor=5.0, organic=0.012, dc=3.2),
}


def run_year(years_out, draw, fpv_gw, fpv_shape, hour, month, doy, rel_cfs,
             nl_knots, p_knots, bess_mw=0.0, bess_h=4.0):
    """One realization of one future year. Returns economics for the FPV asset."""
    solar_gw = BASE_SOLAR_GW + draw["solar_rate"] * years_out
    stor_gw = BASE_STORAGE_GW + draw["stor_rate"] * years_out
    # Load = organic (shape-following) growth + a FLAT data-center block.
    # The data-center block is the single largest swing factor and the one most
    # exposed to policy: large-load tariffs, interconnection moratoria and
    # bring-your-own-generation rules can defer or kill announced load.
    peak_organic = BASE_PEAK_LOAD_GW * (1 + draw["organic_growth"]) ** years_out
    dc_flat = draw["dc_gw_per_yr"] * years_out * draw["dc_realization"]
    peak_gw = peak_organic + dc_flat

    # Load growth splits into a shape-following part and a FLAT 24/7 part (data
    # centers). Flat load raises midday net load and is the main structural reason
    # the duck curve may not keep deepening, so it has to be modelled explicitly.
    load = load_shape(hour, month, peak_organic) + dc_flat
    solar = fpv_shape * SOLAR_DIVERSITY * solar_gw
    wind = wind_shape(hour, doy, BASE_WIND_GW * (1 + 0.02) ** years_out)
    nl = load - solar - wind
    nl_post = dispatch_storage(nl, stor_gw,
                               price_map=(nl_knots, p_knots, peak_gw),
                               gas_factor=draw["gas_factor"])
    # normalize by regional peak so load growth alone does not drift the price level
    price = apply_price_map(nl_post / peak_gw, nl_knots, p_knots, draw["gas_factor"])

    # dam side: release scenario -> hydro MW -> tie headroom
    gen_mw, _ = hydro_mw(rel_cfs, draw["release_maf"])
    headroom = np.clip(CAP_MW - gen_mw, 0, CAP_MW)

    fpv_mw = fpv_shape * fpv_gw * 1000.0 * draw["cf_scale"]
    exportable = np.minimum(fpv_mw, headroom)
    tie_curtail = fpv_mw - exportable
    # economic curtailment: do not deliver into negative prices
    econ_ok = price > 0
    delivered = np.where(econ_ok, exportable, 0.0)

    # optional co-located BESS: soak surplus (tie- or price-curtailed) FPV, discharge at peak
    bess_rev, bess_mwh = 0.0, 0.0
    if bess_mw > 0:
        n = int(bess_h)
        e_cap = bess_mw * bess_h
        pr = price.reshape(-1, 24)
        sur = (fpv_mw - delivered).reshape(-1, 24)      # FPV energy otherwise lost
        room = (headroom - delivered).reshape(-1, 24)   # tie space left after direct sales
        for d in range(pr.shape[0]):
            top = np.argsort(pr[d])[-n:]
            charged = min(e_cap, float(np.minimum(sur[d], bess_mw).sum()))
            dischargeable = min(charged * ETA_RT,
                                float(np.minimum(room[d][top], bess_mw).sum()))
            if dischargeable <= 0:
                continue
            # spread the discharge evenly over the n highest-priced hours
            per_hr = dischargeable / n
            bess_mwh += dischargeable
            bess_rev += float(per_hr * pr[d][top].sum())
    gen_mwh = float(delivered.sum())
    exportable_mwh = float(exportable.sum())   # contractable under a fixed-price PPA
    energy_rev = float((delivered * price).sum()) + bess_rev
    total_gen = float(fpv_mw.sum())
    # PRIMARY metric: revenue per MWh the array actually generates. Dividing by
    # delivered-only MWh flatters the result, because curtailed hours are exactly
    # the worthless ones -- that ratio rises with penetration even as revenue falls.
    capture = energy_rev / total_gen if total_gen > 0 else 0.0
    capture_delivered = energy_rev / gen_mwh if gen_mwh > 0 else 0.0
    return dict(
        solar_gw=solar_gw, stor_gw=stor_gw, peak_gw=peak_gw,
        neg_hours=int((price < 0).sum()),
        dc_flat_gw=float(dc_flat), peak_gw_total=float(peak_gw),
        atc_price=float(price.mean()),
        capture=capture, capture_delivered=capture_delivered,
        fpv_mwh=float(fpv_mw.sum()), delivered_mwh=gen_mwh,
        tie_curtail_pct=float(tie_curtail.sum() / fpv_mw.sum() * 100),
        econ_curtail_pct=float((exportable - delivered).sum() / fpv_mw.sum() * 100),
        energy_rev=energy_rev, bess_mwh=bess_mwh, bess_rev=bess_rev,
        exportable_mwh=exportable_mwh,
    )


def economics(res, draw, fpv_gw, bess_mw, life=25, degr=0.005, ppa_basis="exportable"):
    """NPV, IRR and breakeven PPA. Revenue may be a scalar (single-year, held flat)
    or a per-year path of length `life` (lifecycle mode)."""
    mw = fpv_gw * 1000.0
    # $/W x W  (1 MW = 1e6 W);  $/kWh x kWh (bess_mw MW x 4 h x 1000 kWh/MWh)
    capex = mw * 1e6 * draw["fpv_capex_per_w"] + bess_mw * 4 * 1000 * draw["bess_capex_per_kwh"]
    capex *= (1 - draw["itc"])
    om = mw * draw["om_per_mw_yr"] + bess_mw * 8000.0
    # Capacity / resource-adequacy revenue. Does NOT decay at the module
    # degradation rate -- RA price and accredited capacity follow their own paths.
    cap_rev = (mw * draw["solar_capacity_credit"] + bess_mw * draw["bess_capacity_credit"]) \
        * 1000.0 * draw["ra_per_kw_yr"]
    r = draw["wacc"]

    path = res.get("energy_rev_path")
    e_path = res.get("contract_mwh_path")
    if path is None:
        path = [res["energy_rev"] * (1 - degr) ** (t - 1) for t in range(1, life + 1)]
        base_e = res["exportable_mwh"] if ppa_basis == "exportable" else res["delivered_mwh"]
        e_path = [base_e * (1 - degr) ** (t - 1) for t in range(1, life + 1)]

    def npv_at(x):
        v = -capex
        for t in range(1, life + 1):
            v += (path[t - 1] + cap_rev - om) / (1 + x) ** t
        return v

    npv = npv_at(r)
    lo, hi = -0.9, 10.0
    irr = float("nan")
    if npv_at(lo) > 0 > npv_at(hi):
        for _ in range(80):
            md = (lo + hi) / 2
            irr = md
            if npv_at(md) > 0:
                lo = md
            else:
                hi = md
        irr = (lo + hi) / 2

    # Breakeven flat PPA on CONTRACTED energy. A fixed-price offtaker does not
    # curtail on negative hub LMP, so the contract volume is tie-exportable
    # generation. Retained BESS merchant revenue is credited, not double-counted.
    disc = [(1 + r) ** -t for t in range(1, life + 1)]
    need = capex + sum((om - cap_rev) * d for d in disc) \
        - sum(res.get("bess_rev", 0.0) * (1 - degr) ** (t - 1) * disc[t - 1]
              for t in range(1, life + 1))
    denom = sum(e_path[t - 1] * disc[t - 1] for t in range(1, life + 1))
    breakeven_ppa = need / max(1e-9, denom)

    crf = r / (1 - (1 + r) ** -life)
    return dict(capex=capex, npv=npv, irr=irr, cap_rev=cap_rev,
                breakeven_ppa=breakeven_ppa,
                lcoe=(capex * crf + om) / max(1e-9, res["delivered_mwh"]))


def sample(scen_name):
    b = BUILDOUT[scen_name]
    keys = list(RELEASE_SCENARIOS)
    probs = np.array([RELEASE_SCENARIOS[k]["p"] or 0.0 for k in keys])
    probs = probs / probs.sum()
    rel = RELEASE_SCENARIOS[keys[RNG.choice(len(keys), p=probs)]]["maf"]
    return dict(
        solar_rate=max(0.2, RNG.normal(b["solar"], b["solar"] * 0.30)),
        stor_rate=max(0.2, RNG.normal(b["stor"], b["stor"] * 0.35)),
        organic_growth=max(0.0, RNG.normal(b["organic"], b["organic"] * 0.45)),
        dc_gw_per_yr=max(0.0, RNG.normal(b["dc"], b["dc"] * 0.35)),
        dc_realization=float(np.clip(RNG.normal(0.60, 0.22), 0.05, 1.0)),
        gas_factor=float(np.exp(RNG.normal(0.0, 0.28))),
        release_maf=rel,
        fpv_capex_per_w=float(RNG.normal(1.25, 0.18)),
        bess_capex_per_kwh=float(RNG.normal(210, 40)),
        itc=float(RNG.choice([0.30, 0.40, 0.00], p=[0.55, 0.25, 0.20])),
        om_per_mw_yr=float(RNG.normal(25000, 4000)),
        ra_per_kw_yr=float(np.clip(RNG.normal(90, 30), 20, 220)),
        solar_capacity_credit=float(np.clip(RNG.normal(0.10, 0.04), 0.0, 0.3)),
        bess_capacity_credit=float(np.clip(RNG.normal(0.90, 0.08), 0.5, 1.0)),
        wacc=float(np.clip(RNG.normal(0.07, 0.012), 0.04, 0.12)),
        # yield multiplier on the fixed-tilt PVGIS shape (CF 0.20). Ground-mount in
        # this basin uses single-axis tracking (CF ~0.28); tracking on water is rare
        # and costly, so part of FPV's LCOE gap is structural, not a modelling choice.
        cf_scale=float(np.clip(RNG.normal(1.08, 0.10), 0.90, 1.40)),
    )


def main(n=400):
    fpv_shape, rel_cfs, hour, month, doy = load_cached()
    p_base = base_prices()

    # base-year net load, calibrated so 2024 capacities reproduce 2024 prices
    load0 = load_shape(hour, month, BASE_PEAK_LOAD_GW)
    nl0 = load0 - fpv_shape * SOLAR_DIVERSITY * BASE_SOLAR_GW - wind_shape(hour, doy, BASE_WIND_GW)
    nl0_post = dispatch_storage(nl0, BASE_STORAGE_GW)
    nl_knots, p_knots = fit_price_map(nl0_post / BASE_PEAK_LOAD_GW, p_base)

    # sanity: the fitted map must reproduce the base year
    chk = apply_price_map(nl0_post / BASE_PEAK_LOAD_GW, nl_knots, p_knots)
    base_capture = float((fpv_shape * chk).sum() / fpv_shape.sum())
    print(f"[calib] base-year ATC ${chk.mean():.2f}  solar capture ${base_capture:.2f}  "
          f"neg hours {int((chk < 0).sum())}  (observed 2024 SP15: ATC $28.61, capture $23.81, ~1156 neg)")

    cods = [2028, 2031, 2035]
    configs = [("fpv_only", 1000.0, 0.0), ("fpv_plus_bess", 1000.0, 400.0)]
    results = {}
    for scen in BUILDOUT:
        for cod in cods:
            yo = cod - BASE_YEAR
            for cname, fpv_mw, bess_mw in configs:
                rows = []
                for _ in range(n):
                    d = sample(scen)
                    r = run_year(yo, d, fpv_mw / 1000.0, fpv_shape, hour, month, doy,
                                 rel_cfs, nl_knots, p_knots, bess_mw=bess_mw)
                    e = economics(r, d, fpv_mw / 1000.0, bess_mw)
                    rows.append({**r, **e, **{k: d[k] for k in
                                ("release_maf", "itc", "ra_per_kw_yr", "gas_factor")}})
                results[f"{scen}|{cod}|{cname}"] = rows
                q = lambda k, p: float(np.percentile([x[k] for x in rows], p))  # noqa: E731
                irrs = [x["irr"] for x in rows if not np.isnan(x["irr"])]
                print(f"{scen:13s} COD{cod} {cname:14s} "
                      f"capture ${q('capture',50):6.2f} [{q('capture',10):.2f},{q('capture',90):.2f}]  "
                      f"neg {q('neg_hours',50):5.0f}h  "
                      f"tie-curt {q('tie_curtail_pct',50):4.1f}%  "
                      f"econ-curt {q('econ_curtail_pct',50):4.1f}%  "
                      f"NPV p50 ${q('npv',50)/1e6:7.1f}M  "
                      f"P(NPV>0)={np.mean([x['npv']>0 for x in rows]):.2f}  "
                      f"IRR p50 {100*np.median(irrs) if irrs else float('nan'):5.1f}%  "
                      f"LCOE ${q('lcoe',50):5.1f}  "
                      f"breakeven PPA ${q('breakeven_ppa',50):5.1f} "
                      f"[{q('breakeven_ppa',10):.0f},{q('breakeven_ppa',90):.0f}]")

    summary = {}
    for k, rows in results.items():
        summary[k] = {m: {str(p): float(np.percentile([x[m] for x in rows], p))
                          for p in (10, 50, 90)}
                      for m in ("capture", "neg_hours", "tie_curtail_pct", "econ_curtail_pct",
                                "npv", "lcoe", "atc_price", "cap_rev",
                                "capture_delivered", "breakeven_ppa")}
        summary[k]["p_npv_positive"] = float(np.mean([x["npv"] > 0 for x in rows]))
        summary[k]["p_capture_above_35"] = float(np.mean([x["capture"] > 35 for x in rows]))
    meta = dict(n_draws=n, base_year=BASE_YEAR, base_peak_load_gw=BASE_PEAK_LOAD_GW,
                base_solar_gw=BASE_SOLAR_GW, base_storage_gw=BASE_STORAGE_GW,
                release_scenarios=RELEASE_SCENARIOS, buildout=BUILDOUT,
                calibration=dict(atc=float(chk.mean()), solar_capture=base_capture,
                                 neg_hours=int((chk < 0).sum())),
                caveats=[
                    "Reduced-form screening model, not a production-cost / unit-commitment model.",
                    "Price map is quantile-fitted to SP15 2024 and extrapolated at the tails.",
                    "Load and wind shapes are stylized; solar shape is real PVGIS at the lake.",
                    "Release scenarios follow the Post-2026 Final EIS sideboards (31 Jul 2026); "
                    "probabilities are assumed, not published.",
                    "Storage dispatch is greedy daily arbitrage, no ancillary services co-optimization.",
                ])
    with open(os.path.join(OUT, "fpv_forward_mc.json"), "w") as f:
        json.dump({"meta": meta, "summary": summary}, f, indent=1)
    print("\nwrote outputs/fpv_forward_mc.json")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 400)


def storage_ratio_sweep(n=120, cod=2035):
    """How much 4h storage per GW of new solar holds the solar capture price up?

    E3 / Aurora put the rule of thumb at 0.5-0.75 GW of 4h storage per GW of new
    solar to avoid severe capture cannibalization. This tests that directly.
    """
    fpv_shape, rel_cfs, hour, month, doy = load_cached()
    p_base = base_prices()
    load0 = load_shape(hour, month, BASE_PEAK_LOAD_GW)
    nl0 = load0 - fpv_shape * SOLAR_DIVERSITY * BASE_SOLAR_GW - wind_shape(hour, doy, BASE_WIND_GW)
    nl_knots, p_knots = fit_price_map(dispatch_storage(nl0, BASE_STORAGE_GW) / BASE_PEAK_LOAD_GW,
                                      p_base)
    yo = cod - BASE_YEAR
    print(f"\nstorage:solar ratio sweep, COD {cod}, solar +3.5 GW/yr "
          f"(base-year capture $23.3)")
    rows = {}
    for ratio in (0.25, 0.50, 0.75, 1.00, 1.25):
        caps = []
        for _ in range(n):
            d = sample("moderate")
            d["solar_rate"], d["stor_rate"] = 3.5, 3.5 * ratio
            r = run_year(yo, d, 1.0, fpv_shape, hour, month, doy, rel_cfs,
                         nl_knots, p_knots)
            caps.append(r["capture"])
        rows[ratio] = [float(np.percentile(caps, p)) for p in (10, 50, 90)]
        print(f"  {ratio:4.2f} GW storage per GW solar -> capture "
              f"${rows[ratio][1]:6.2f}  [{rows[ratio][0]:.2f}, {rows[ratio][2]:.2f}]")
    with open(os.path.join(OUT, "fpv_storage_ratio_sweep.json"), "w") as f:
        json.dump({"cod": cod, "solar_gw_per_yr": 3.5, "capture_by_ratio": rows}, f, indent=1)
    return rows


if __name__ == "__main__":
    storage_ratio_sweep()


def run_life(years_out, draw, fpv_gw, fpv_shape, hour, month, doy, rel_cfs,
             nl_knots, p_knots, bess_mw=0.0, life=25, degr=0.005,
             anchors=(0, 6, 12)):
    """Operating results across the asset life, with the market continuing to evolve
    after COD. Anchor years are simulated and the revenue path interpolated between
    them -- freezing the COD year for 25 years was the single biggest structural
    error in the first version of this model."""
    sims = {}
    for a in anchors:
        sims[a] = run_year(years_out + a, draw, fpv_gw, fpv_shape, hour, month, doy,
                           rel_cfs, nl_knots, p_knots, bess_mw=bess_mw)
    # Market conditions are held FLAT after the last anchor. Extrapolating a linear
    # buildout 25 years past COD is not credible -- capacity additions would slow
    # long before that, and the price map's tail extrapolation becomes unstable.
    xs = np.array(anchors, dtype=float)
    rev = np.array([sims[a]["energy_rev"] for a in anchors])
    exp_mwh = np.array([sims[a]["exportable_mwh"] for a in anchors])
    t = np.arange(life, dtype=float)
    tc = np.clip(t, 0, xs[-1])          # flat after the last anchor
    rev_path = np.interp(tc, xs, rev) * (1 - degr) ** t
    e_path = np.interp(tc, xs, exp_mwh) * (1 - degr) ** t
    first = dict(sims[anchors[0]])
    first["energy_rev_path"] = rev_path.tolist()
    first["contract_mwh_path"] = e_path.tolist()
    # end-of-life market conditions, worth reporting alongside the COD year
    first["capture_eol"] = sims[anchors[-1]]["capture"]
    first["neg_hours_eol"] = sims[anchors[-1]]["neg_hours"]
    return first


DC_POLICY = {
    # Fraction of ANNOUNCED data-center load that actually energizes on schedule.
    # Anchored on NV Energy's 2026 IRP, which states that historically only ~40% of
    # study-phase large loads move forward, and on Grid Strategies' estimate that the
    # national 2030 data-center forecast is overstated by roughly 40%. Duplicate queue
    # requests across AZ/NV/UT inflate the announced pipeline further.
    # Policy pressure in 2025-26 pushes the low case: Ohio 85% take-or-pay after a
    # 28-month moratorium, Virginia GS-5 (14-yr term, 85%/60% take-or-pay,
    # $1.5M/MW collateral), PJM BYOG-or-curtail, ERCOT SB6 mandatory curtailment,
    # FERC show-cause orders on large-load interconnection (June 2026).
    "policy_hold": (0.20, 0.08),
    "base":        (0.40, 0.12),   # NV Energy's own stated realization rate
    "full_ramp":   (0.85, 0.10),
}


def trajectory(n=250, horizons=(1, 3, 5, 10), base_now=2026):
    """1 / 3 / 5 / 10-year trajectory of the regional grid and of FPV economics,
    with the data-center ramp treated as its own policy-exposed uncertainty."""
    fpv_shape, rel_cfs, hour, month, doy = load_cached()
    p_base = base_prices()
    load0 = load_shape(hour, month, BASE_PEAK_LOAD_GW)
    nl0 = load0 - fpv_shape * SOLAR_DIVERSITY * BASE_SOLAR_GW - wind_shape(hour, doy, BASE_WIND_GW)
    nl_knots, p_knots = fit_price_map(dispatch_storage(nl0, BASE_STORAGE_GW) / BASE_PEAK_LOAD_GW,
                                      p_base)
    out = {}
    print(f"\n{'horizon':>8} {'supply':>12} {'dc policy':>11} | {'solar':>6} {'stor':>6} "
          f"{'peak':>6} {'dcGW':>5} | {'neg h':>6} {'capture':>8} {'breakeven':>9} {'P(NPV>0)':>8}")
    for h in horizons:
        cod = base_now + h
        yo = cod - BASE_YEAR
        for supply in BUILDOUT:
            for pol, (mu, sd) in DC_POLICY.items():
                rows = []
                for _ in range(n):
                    d = sample(supply)
                    d["dc_realization"] = float(np.clip(RNG.normal(mu, sd), 0.0, 1.0))
                    r = run_year(yo, d, 1.0, fpv_shape, hour, month, doy, rel_cfs,
                                 nl_knots, p_knots)
                    e = economics(r, d, 1.0, 0.0)
                    rows.append({**r, **e})
                q = lambda k, p: float(np.percentile([x[k] for x in rows], p))  # noqa: E731
                key = f"{cod}|{supply}|{pol}"
                out[key] = {m: {str(p): q(m, p) for p in (10, 50, 90)}
                            for m in ("capture", "neg_hours", "breakeven_ppa", "npv",
                                      "solar_gw", "stor_gw", "peak_gw", "dc_flat_gw",
                                      "tie_curtail_pct", "econ_curtail_pct", "atc_price")}
                out[key]["p_npv_positive"] = float(np.mean([x["npv"] > 0 for x in rows]))
                print(f"{h:>6}yr {supply:>12} {pol:>11} | {q('solar_gw',50):6.0f} "
                      f"{q('stor_gw',50):6.0f} {q('peak_gw',50):6.0f} {q('dc_flat_gw',50):5.1f} | "
                      f"{q('neg_hours',50):6.0f} ${q('capture',50):7.2f} "
                      f"${q('breakeven_ppa',50):8.1f} {out[key]['p_npv_positive']:8.2f}")
    with open(os.path.join(OUT, "fpv_trajectory.json"), "w") as f:
        json.dump({"base_now": base_now, "dc_policy": DC_POLICY, "buildout": BUILDOUT,
                   "results": out}, f, indent=1)
    print("\nwrote outputs/fpv_trajectory.json")
    return out


def offtake_analysis(n=250, cod=2031, ppa_prices=(50, 60, 65, 70, 80), btm_share=0.7):
    """What offtake structure actually closes the gap?

    Three structures compared at a fixed COD:
      merchant            - sell everything into the hub at hourly prices
      ppa                 - flat-price PPA on delivered energy
      btm_colocated       - a share of output consumed behind the meter by co-located
                            load at the dam, which does NOT use the tie and is not
                            exposed to negative prices, remainder sold merchant
    """
    fpv_shape, rel_cfs, hour, month, doy = load_cached()
    p_base = base_prices()
    load0 = load_shape(hour, month, BASE_PEAK_LOAD_GW)
    nl0 = load0 - fpv_shape * SOLAR_DIVERSITY * BASE_SOLAR_GW - wind_shape(hour, doy, BASE_WIND_GW)
    nl_knots, p_knots = fit_price_map(dispatch_storage(nl0, BASE_STORAGE_GW) / BASE_PEAK_LOAD_GW,
                                      p_base)
    yo = cod - BASE_YEAR
    res = {}
    print(f"\noff-take structures, COD {cod}, 1 GW FPV, moderate buildout")
    merch = []
    for _ in range(n):
        d = sample("moderate")
        r = run_year(yo, d, 1.0, fpv_shape, hour, month, doy, rel_cfs, nl_knots, p_knots)
        merch.append({**r, **economics(r, d, 1.0, 0.0)})
    res["merchant"] = dict(p_npv_pos=float(np.mean([x["npv"] > 0 for x in merch])),
                           npv_p50=float(np.median([x["npv"] for x in merch])),
                           breakeven_ppa_p50=float(np.median([x["breakeven_ppa"] for x in merch])))
    print(f"  merchant                      P(NPV>0)={res['merchant']['p_npv_pos']:.2f}  "
          f"NPV p50 ${res['merchant']['npv_p50']/1e6:7.0f}M  "
          f"breakeven ${res['merchant']['breakeven_ppa_p50']:.0f}")

    for ppa in ppa_prices:
        for structure in ("ppa", "btm_colocated"):
            rows = []
            for _ in range(n):
                d = sample("moderate")
                r = run_year(yo, d, 1.0, fpv_shape, hour, month, doy, rel_cfs, nl_knots, p_knots)
                gen = r["fpv_mwh"]
                if structure == "ppa":
                    # flat price on what the tie can actually deliver
                    energy_rev = r["delivered_mwh"] * ppa
                    delivered = r["delivered_mwh"]
                else:
                    # co-located load takes btm_share of GROSS generation at the PPA price,
                    # bypassing the tie and the negative-price exposure entirely
                    btm = gen * btm_share
                    rest = max(0.0, r["delivered_mwh"] - btm)
                    energy_rev = btm * ppa + rest * max(0.0, r["capture_delivered"])
                    delivered = btm + rest
                r2 = {**r, "energy_rev": energy_rev, "delivered_mwh": delivered}
                rows.append({**r2, **economics(r2, d, 1.0, 0.0)})
            key = f"{structure}@${ppa}"
            res[key] = dict(p_npv_pos=float(np.mean([x["npv"] > 0 for x in rows])),
                            npv_p50=float(np.median([x["npv"] for x in rows])))
            print(f"  {structure:14s} @ ${ppa:3d}/MWh      P(NPV>0)={res[key]['p_npv_pos']:.2f}  "
                  f"NPV p50 ${res[key]['npv_p50']/1e6:7.0f}M")
    with open(os.path.join(OUT, "fpv_offtake.json"), "w") as f:
        json.dump({"cod": cod, "btm_share": btm_share, "results": res}, f, indent=1)
    return res
