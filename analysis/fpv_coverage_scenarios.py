#!/usr/bin/env python3
"""Two FPV sizing conventions, run through the same hourly model, priced against reuse.

Reviewers and collaborators keep arriving at FPV areas several times ours, and the reason is
two multiplicative conventions rather than a disagreement about the lake:

  A. ours      coverage bounded by the dam's EXISTING interconnection, on the measured
               (drawn-down) surface from Reclamation elevation and storage
  B. theirs    10-20% of FULL POOL, with no transmission bound

This expresses B as coverage of the real lake and runs it through the same hourly simulation,
so the comparison is like for like. It then prices both against water reuse, because the
question that matters is not which convention is bigger but what a dollar buys.

Output: outputs/fpv_coverage_scenarios.json
"""
import json, os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import fpv_coverage_explorer as X

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
ACRE_KM2 = 0.00404686

# Scenario B needs coverage well past the published explorer's 25% ceiling: 20% of Mead's full
# pool is 42.6% of the lake that is actually there. Extend the grid and send the run to a scratch
# path so the published explorer output is never touched by this script.
MAX_COVERAGE = 0.45
FULL_POOL_CONVENTIONS = (10, 15, 20)      # percent of full pool, per the 10-20% figure quoted
REUSE_USD_PER_AF = (2_500, 3_500)         # analysis/reuse_resource.py, the expensive end of reuse
REUSE_HEADROOM_AF = 1_300_000             # UCLA IoES + NRDC 2025, basin reuse lifted to 50%


def extended_model():
    """Re-run the hourly model on a wider coverage grid, writing nowhere permanent.

    X.main() ends with a hardcoded 'WROTE outputs/fpv_coverage_explorer.json' line. It writes to
    the patched X.OUT, not there, but the message would have a reader believe the published model
    was just overwritten on a 45% grid. Swallow its stdout so nothing claims that.
    """
    X.COVERAGE = [round(x, 4) for x in np.arange(0, MAX_COVERAGE + 0.0001, 0.0025)]
    published = OUT / "fpv_coverage_explorer.json"
    before = published.stat().st_mtime if published.exists() else None
    with tempfile.TemporaryDirectory() as td:
        X.OUT = Path(td)
        buf, sys.stdout = sys.stdout, open(os.devnull, "w")
        try:
            X.main()
        finally:
            sys.stdout.close(); sys.stdout = buf
        model = json.loads((Path(td) / "fpv_coverage_explorer.json").read_text())
    after = published.stat().st_mtime if published.exists() else None
    if before != after:
        raise SystemExit("[scenarios] the published explorer output was modified; aborting")
    print(f"[scenarios] ran {len(X.COVERAGE)} coverage steps to {MAX_COVERAGE*100:.0f}%, "
          "published explorer untouched")
    return model


def mc_sampler(name, n=2000):
    """Draw the uncertainty model's parameters ONCE for a reservoir, so every coverage level is
    evaluated in the same sampled worlds. Paired draws matter here: the finding is how $/AF moves
    WITH coverage, and independent draws would bury that under sampling noise.

    The published p50 is not directly comparable to any of this. fpv_uncertainty.run_reservoir
    RIGHT-SIZES the array, searching upward until spill exceeds 5%, so its $19,038/AF is the cost
    of a spill-constrained array rather than the cost at a stated coverage. Evaluating at a fixed
    coverage is a different question and needs its own run.
    """
    import fpv_uncertainty as Q
    Q.RNG = np.random.default_rng(20260807)          # reseed: identical draws for every reservoir
    p = Q.model[name]["params"]
    h = Q.model[name]["hourly"]
    U = Q.correlated_uniforms(n)
    kind, spec = Q.EVAP_UNC[name]
    if kind == "bracket":
        evap = spec[0] + U["evap"] * (spec[1] - spec[0])
    else:
        from scipy.special import erfinv
        evap = p["evap_ft"] * (1 + spec * np.sqrt(2)
                               * erfinv(2 * np.clip(U["evap"], 1e-9, 1 - 1e-9) - 1))
    wacc = 0.06 + U["wacc"] * 0.03
    return dict(
        p=p, n=n,
        solar=Q.dec(h["solar_b64"], h["solar_scale"]),
        hydro=Q.dec(h["hydro_b64"], h["hydro_scale"]),
        price=Q.dec(h["price_b64"], h["price_scale"]),
        day=Q.dec(h["daylight_b64"], 1),
        area_km2=p["surface_acres"] * Q.ACRE_KM2,
        evap=evap,
        supp=Q.inv_tri(U["supp"], 0.30, 0.75, 0.90),
        dens=Q.inv_tri(U["density"], 80, 120, 160),
        capex_w=Q.inv_tri(U["capex"], 1.23, 1.50, 2.50),
        om_mult=Q.inv_tri(U["om"], 1.0, 1.3, 3.0),
        wacc=wacc,
        crf=wacc * (1 + wacc) ** 25 / ((1 + wacc) ** 25 - 1),
        linef=Q.RNG.uniform(0.10, 1.00, n),
        coinc=Q.RNG.uniform(0.25, 1.00, n),
        af_per=Q.AF_PER_KM2_PER_FT,
    )


def mc_at_coverage(s, cov_frac):
    """Cost per acre-foot at a FIXED coverage, net of power sales, across the sampled draws.
    Same cost and revenue terms as fpv_uncertainty, with the spill constraint removed: the whole
    point of the high-coverage scenarios is that they breach it."""
    p, n = s["p"], s["n"]
    usd_af = np.empty(n)
    for i in range(n):
        load = p["onsite_load_mw"] * s["coinc"][i]
        head = np.maximum(0, p["tie_mw"] - s["hydro"]) * s["linef"][i] + np.where(s["day"] > 0, load, 0)
        mw = cov_frac * s["area_km2"] * s["dens"][i]
        ac = min(mw, p["tie_mw"] * s["linef"][i] + load)
        deliv = np.minimum(np.minimum(s["solar"] * mw, ac), head)
        af = cov_frac * s["supp"][i] * s["area_km2"] * s["evap"][i] * s["af_per"]
        rev = float((np.where(s["price"] > 0, deliv, 0) * s["price"]).sum())
        cost = mw * 1e6 * s["capex_w"][i] * s["crf"][i] + mw * 25_000 * s["om_mult"][i]
        usd_af[i] = (cost - rev) / af if af > 0 else np.nan
    a = usd_af[np.isfinite(usd_af)]
    return {f"p{q}": round(float(np.percentile(a, q))) for q in (10, 50, 90)} if len(a) else None


def row_at(rows, coverage_pct):
    """Nearest simulated row. The grid is 0.25% so this is never more than an eighth of a
    percent of coverage away from the requested point."""
    return min(rows, key=lambda r: abs(r["coverage_pct"] - coverage_pct))


def describe(row, lake_acres):
    """Deterministic economics for one coverage row. net_musd is negative for a net cost, so
    the sign is flipped here to read as a cost."""
    evap = row["evap_saved_af"]
    net_cost_musd = row["annual_cost_musd"] - row["revenue_musd"]
    return {
        "coverage_of_real_lake_pct": round(row["coverage_pct"], 2),
        "fpv_acres": round(row["covered_km2"] / ACRE_KM2),
        "array_gw": round(row["gw"], 2),
        "export_twh": round(row["export_twh"], 2),
        "curtail_tx_pct": round(row["curtail_tx_pct"], 1),
        "curtail_econ_pct": round(row["curtail_econ_pct"], 1),
        "capture_usd_mwh": round(row["capture_usd_mwh"], 2),
        "gross_cost_musd": round(row["annual_cost_musd"], 1),
        "power_revenue_musd": round(row["revenue_musd"], 1),
        "net_cost_musd": round(net_cost_musd, 1),
        "evap_saved_af": evap,
        "usd_per_af_deterministic": round(net_cost_musd * 1e6 / evap) if evap else None,
        "share_of_lake_pct": round(100 * (row["covered_km2"] / ACRE_KM2) / lake_acres, 1),
    }


model = extended_model()
basin = json.loads((OUT / "basin_daily.json").read_text())["reservoirs"]

scenarios, notes = {}, []
for name in ("Lake Mead", "Lake Powell"):
    r = model[name]
    lake_acres = r["params"]["surface_acres"]
    full_pool = basin[name]["full_pool_acres"]
    knee = r["curtail_knee_pct"]

    sampler = mc_sampler(name)
    a = describe(row_at(r["rows"], knee), lake_acres)
    a["usd_per_af_mc"] = mc_at_coverage(sampler, knee / 100)
    b = {}
    for pct in FULL_POOL_CONVENTIONS:
        want_acres = full_pool * pct / 100
        cov_of_real = 100 * want_acres / lake_acres
        if cov_of_real > MAX_COVERAGE * 100:
            notes.append(f"{name}: {pct}% of full pool needs {cov_of_real:.0f}% of the real lake, "
                         f"past the {MAX_COVERAGE*100:.0f}% grid; not simulated")
            continue
        sc = describe(row_at(r["rows"], cov_of_real), lake_acres)
        sc["usd_per_af_mc"] = mc_at_coverage(sampler, cov_of_real / 100)
        b[f"{pct}pct_of_full_pool"] = sc

    scenarios[name] = {
        "measured_acres": lake_acres,
        "full_pool_acres": full_pool,
        "full_pool_over_measured": round(full_pool / lake_acres, 2),
        "transmission_bounded": a,
        "full_pool_convention": b,
    }

# What the same money buys as reuse. This is the comparison that decides it: evaporation
# suppression and reused effluent are both water, and one of them is an order of magnitude
# cheaper per acre-foot.
for name, s in scenarios.items():
    for label, sc in [("transmission_bounded", s["transmission_bounded"])] + \
                     [(k, v) for k, v in s["full_pool_convention"].items()]:
        spend = sc["net_cost_musd"] * 1e6
        sc["reuse_af_for_same_spend"] = {
            f"at_{c}_usd_af": round(spend / c) for c in REUSE_USD_PER_AF}
        # Stated the way the site already states it: how many times more expensive an acre-foot
        # of suppressed evaporation is than an acre-foot of reuse. On the Monte Carlo p50, which
        # is the basis the published "roughly seven times" uses.
        mc = sc["usd_per_af_mc"]
        sc["cost_ratio_vs_reuse"] = {
            f"at_{c}_usd_af": round(mc["p50"] / c, 1) for c in REUSE_USD_PER_AF} if mc else None

doc = {
    "meta": {
        "what": "FPV evaporation and cost under two sizing conventions, same hourly model",
        "why": "collaborators sizing off full pool with no transmission bound land 3-6x higher "
               "on FPV area; this separates the two causes and prices both",
        "convention_a": "coverage at the transmission knee, on the measured drawn-down surface",
        "convention_b": f"{FULL_POOL_CONVENTIONS} percent of published full pool, expressed as "
                        "coverage of the real lake and run through the same hourly simulation",
        "cost_basis": "DETERMINISTIC central case, net of power sales. The published site quotes "
                      "the Monte Carlo p50, which is roughly twice this because it widens "
                      "suppression, line share and capex. Ratios between rows are the finding, "
                      "not the absolute level.",
        "reuse_source": "analysis/reuse_resource.py: reuse or desalination 2,500-3,500 $/AF. "
                        "OCWD delivers at 487-1,073 $/AF, so this is the expensive end of reuse.",
        "reuse_headroom_af": REUSE_HEADROOM_AF,
        "grid": f"coverage 0 to {MAX_COVERAGE*100:.0f}% in 0.25% steps",
        "notes": notes,
    },
    "scenarios": scenarios,
}
(OUT / "fpv_coverage_scenarios.json").write_text(json.dumps(doc, indent=1))

print("\n" + "=" * 104)
for name, s in scenarios.items():
    print(f"\n{name}   measured {s['measured_acres']:,} ac | full pool {s['full_pool_acres']:,} ac "
          f"({s['full_pool_over_measured']}x)")
    print(f"  {'sizing':<26}{'FPV ac':>9}{'GW':>7}{'txCurt':>8}{'evap AF':>10}"
          f"{'det $/AF':>10}{'MC p50 $/AF':>13}{'vs reuse':>10}")
    rows = [("transmission knee", s["transmission_bounded"])] + list(s["full_pool_convention"].items())
    for label, sc in rows:
        lab = label if label == "transmission knee" else label.replace("_", " ")
        print(f"  {lab:<26}{sc['fpv_acres']:>9,}{sc['array_gw']:>7.2f}"
              f"{sc['curtail_tx_pct']:>7.1f}%{sc['evap_saved_af']:>10,}"
              f"{sc['usd_per_af_deterministic']:>10,}{sc['usd_per_af_mc']['p50']:>13,}"
              f"{sc['cost_ratio_vs_reuse']['at_3500_usd_af']:>9.1f}x")
for n in notes:
    print("  note:", n)
print("\nwrote outputs/fpv_coverage_scenarios.json")
