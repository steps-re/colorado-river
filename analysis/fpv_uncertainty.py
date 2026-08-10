#!/usr/bin/env python3
"""Monte Carlo uncertainty propagation for the reservoir FPV model.

The explorer reports point estimates with user-set sensitivities. That is fine for exploring a
trade-off and inadequate for a result anyone should cite. This propagates the uncertainty in
every parameter that is not directly measured, and reports P10/P50/P90 on the quantities the
conclusions rest on.

Parameters treated as uncertain, with the reason:
  evaporation rate   measured by eddy covariance at Mead/Mohave (~5% flux uncertainty); an area
                     quotient at Havasu (bracket 5.2-7.4); unmeasured screening values in the
                     Upper Basin (wide)
  suppression        0.60-0.90; sub-linear in coverage because heat not lost as vapour mixes into
                     the bulk water and raises evaporation on the surrounding open surface
  areal density      80-160 MW/km2 once mooring corridors, navigation and intake exclusion are
                     allowed for
  capex, O&M         $1.23-2.50/W and 1-3x O&M for deep dynamic mooring and quagga mussel fouling
  WACC               6-9%
  line share         0.10-1.00 of the dam's idle line, standing in for the interconnection study
                     this model does not have
  load coincidence   0.25-1.00 of on-shore pumping load actually available to the array
  surface area       +/-6%. Added 2026-08-10. Previously treated as exact because it is
                     "measured", but it is a fitted hypsometry evaluated off Reclamation's
                     elevation and storage, and the model's own out-of-sample test against
                     published full-pool area missed by +5.5, +5.0, +7.5 and -4.8% at the four
                     reservoirs where that test is possible. Mead and Powell cannot be tested at
                     all, so carrying them as exact was the least defensible thing in here.
  solar resource     +/-4%, interannual variability of annual irradiance. PVGIS gives one year.
  price level        +/-20%, one traded year (2024) standing in for a 25-year asset. Widened to
                     +/-30% at Flaming Gorge and Blue Mesa, whose price shape is transferred from
                     another node rather than measured locally.
  asset life         20-30 years. Was fixed at 25. Floats and mooring in a mussel-infested
                     reservoir are exactly where a life assumption should not be a constant.

Note on area, corrected after measuring it. It multiplies both the water saved and the array cost,
so it cancels in cost per acre-foot: PRCC -0.03 at Mead. That much was predicted. The prediction
that it would still drive absolute acre-feet was WRONG, and the PRCC on evap_saved_af is -0.03 as
well. The reason is the right-sizing loop: a larger surface builds a larger array at the same
coverage, which spills sooner, so the search stops at a lower coverage and gives back what the area
gave. What actually sets the water saved is the tie, and line_share carries PRCC 0.98.

Area does matter, linearly and without feedback, for acre-feet at a FIXED coverage, which is what
fpv_coverage_scenarios.py computes. So sampling it was still right. It just tells us the opposite
of what the first version of this note claimed.

Outputs: outputs/fpv_uncertainty.json
"""
import json, base64
from pathlib import Path
import numpy as np
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
EXTREMES = {}     # cheapest single draw per reservoir; see _min_af() on the capital page
RNG = np.random.default_rng(20260807)      # fixed seed: results are reproducible
N = 2000

model = json.loads((OUT / "fpv_coverage_explorer.json").read_text())
meta = model["meta"]
ORDER = [k for k in model if k != "meta"]

ACRE_KM2 = 0.00404686
AF_PER_KM2_PER_FT = 1e6 * 0.3048 / 1233.48

# evaporation-rate uncertainty by provenance
EVAP_UNC = {
    "Lake Mead":        ("flux", 0.05),
    "Lake Powell":      ("flux", 0.08),
    "Lake Mohave":      ("flux", 0.05),
    "Lake Havasu":      ("bracket", (5.2, 7.4)),
    "Flaming Gorge":    ("screen", 0.30),
    "Navajo Reservoir": ("screen", 0.30),
    "Blue Mesa":        ("screen", 0.30),
}


def dec(b64s, scale):
    return np.frombuffer(base64.b64decode(b64s), dtype="<i2").astype(float) / scale


def tri(lo, mode, hi, n):
    return RNG.triangular(lo, mode, hi, n)


# Both referees: drawing these independently is wrong, because several are driven by the same
# underlying site conditions and their correlations widen the tails that matter. We impose a
# correlation structure with a Gaussian copula: draw correlated standard normals, map to uniforms,
# then invert each marginal.
#
#   capex, O&M          strongly correlated (rho 0.75): a reservoir that is deep, storm-exposed
#                       and mussel-infested raises construction cost AND maintenance cost together
#   density, capex      negatively correlated (rho -0.35): wide mooring corridors lower density
#                       and raise cost per watt at the same time
#   suppression, evap   weakly positive (rho 0.20): a hotter, higher-flux surface has more latent
#                       heat available to suppress, but advective recirculation offsets part of it
#   WACC, capex         weakly positive (rho 0.25): perceived project risk moves both
COPULA_VARS = ["capex", "om", "density", "supp", "evap", "wacc"]
COPULA_RHO = {
    ("capex", "om"): 0.75,
    ("capex", "density"): -0.35,
    ("capex", "wacc"): 0.25,
    ("supp", "evap"): 0.20,
}


def correlated_uniforms(n):
    """Gaussian copula over the correlated parameters; returns {name: U(0,1) array}."""
    k = len(COPULA_VARS)
    idx = {v: i for i, v in enumerate(COPULA_VARS)}
    C = np.eye(k)
    for (a, b), r in COPULA_RHO.items():
        C[idx[a], idx[b]] = C[idx[b], idx[a]] = r
    # nearest positive-definite repair, in case the specified matrix is not PD
    w, Vt = np.linalg.eigh(C)
    if w.min() < 1e-8:
        w = np.clip(w, 1e-8, None)
        C = Vt @ np.diag(w) @ Vt.T
        d = np.sqrt(np.diag(C))
        C = C / np.outer(d, d)
    L = np.linalg.cholesky(C)
    # numpy raises spurious divide/overflow/invalid warnings from this matmul on some BLAS
    # builds even though C is positive definite and L is finite. Verified empirically: the
    # achieved Spearman correlations match the targets to within 0.015 and the marginals are
    # clean U(0,1). Suppressed deliberately rather than left to alarm a reader.
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        z = L @ RNG.standard_normal((k, n))
    from math import erf, sqrt
    phi = np.vectorize(lambda x: 0.5 * (1 + erf(x / sqrt(2))))
    return {v: phi(z[idx[v]]) for v in COPULA_VARS}


def inv_tri(u, lo, mode, hi):
    """Inverse CDF of a triangular distribution, for copula sampling."""
    fc = (mode - lo) / (hi - lo)
    out = np.where(u < fc,
                   lo + np.sqrt(np.clip(u * (hi - lo) * (mode - lo), 0, None)),
                   hi - np.sqrt(np.clip((1 - u) * (hi - lo) * (hi - mode), 0, None)))
    return out


def sample(name, n=N):
    """Draw every uncertain parameter for one reservoir.

    Split out of run_reservoir so the right-sizing search here and the fixed-coverage scenarios in
    fpv_coverage_scenarios.py share ONE set of draws and ONE cost kernel. They used to be two hand
    written copies of the same arithmetic, which is a divergence waiting to happen: a change to the
    cost terms here would silently not reach the scenario table on the paper page.
    """
    p = model[name]["params"]
    h = model[name]["hourly"]
    solar = dec(h["solar_b64"], h["solar_scale"])
    hydro = dec(h["hydro_b64"], h["hydro_scale"])
    price = dec(h["price_b64"], h["price_scale"])
    day = dec(h["daylight_b64"], 1)

    U = correlated_uniforms(n)
    kind, spec = EVAP_UNC[name]
    if kind == "bracket":
        evap = spec[0] + U["evap"] * (spec[1] - spec[0])
    else:
        # normal marginal via the copula uniform
        from scipy.special import erfinv  # noqa: F401
        evap = p["evap_ft"] * (1 + spec * np.sqrt(2) * erfinv(2 * np.clip(U["evap"], 1e-9, 1 - 1e-9) - 1))
    # Widened downward after round 6. Both reviewers, independently, said instrumented
    # evaporation-suppression results from real floating PV cluster nearer 30-60% than 75%, and
    # that 75% is an engineering assumption rather than a measured central value. The old floor of
    # 0.60 sat AT the top of the range they described, so the interval could not contain the
    # likely truth. An uncertainty range that excludes the plausible answer is not one. The mode
    # stays at the design assumption; the lower tail now reaches what the field reports.
    # Direction matters: suppression is a divisor on cost per acre-foot, so a lower value makes
    # FPV look WORSE. Widening here strengthens the paper's conclusion rather than protecting it.
    supp = inv_tri(U["supp"], 0.30, 0.75, 0.90)
    dens = inv_tri(U["density"], 80, 120, 160)
    capex_w = inv_tri(U["capex"], 1.23, 1.50, 2.50)
    om_mult = inv_tri(U["om"], 1.0, 1.3, 3.0)
    wacc = 0.06 + U["wacc"] * 0.03
    # NOTE: capacity value is deliberately NOT sampled here. This Monte Carlo sizes SOLAR-ONLY
    # arrays with no battery, and the model credits firm capacity to storage only, so a capacity
    # value would have no effect. An earlier version sampled it and passed it to the sensitivity
    # analysis without ever using it in a cost or revenue term, which reported it as a driver of an
    # output it could not touch. Removed rather than left dangling.
    linef = RNG.uniform(0.10, 1.00, n)
    coinc = RNG.uniform(0.25, 1.00, n)

    # ---- parameters added 2026-08-10; see the module docstring for why each ----
    # Area: sigma from this model's OWN out-of-sample test against published full-pool area
    # (+5.5, +5.0, +7.5, -4.8% at the four testable reservoirs). Havasu is a static published
    # area on a reservoir held within 4 ft, so it is tighter than a fitted hypsometry.
    area_sigma = 0.04 if p.get("area_swing_pct") is None else 0.06
    area_mult = np.clip(RNG.normal(1.0, area_sigma, n), 0.75, 1.25)
    solar_mult = np.clip(RNG.normal(1.0, 0.04, n), 0.85, 1.15)
    # One traded year standing in for a 25-year asset. Wider where the price SHAPE is transferred
    # from another node rather than measured at this one.
    price_sigma = 0.30 if p.get("price_is_proxy") else 0.20
    price_mult = np.clip(RNG.normal(1.0, price_sigma, n), 0.3, 2.0)
    life = inv_tri(RNG.random(n), 20, 25, 30)

    crf = wacc * (1 + wacc) ** life / ((1 + wacc) ** life - 1)
    area_km2 = p["surface_acres"] * ACRE_KM2 * area_mult

    # keep the sampled inputs so we can attribute output variance to them afterwards
    inputs = dict(evaporation=evap, suppression=supp, density=dens, capex=capex_w,
                  om_multiplier=om_mult, wacc=wacc,
                  line_share=linef, load_coincidence=coinc,
                  surface_area=area_mult, solar_resource=solar_mult,
                  price_level=price_mult, asset_life=life)
    return dict(name=name, p=p, n=n, solar=solar, hydro=hydro, price=price, day=day,
                area_km2=area_km2, evap=evap, supp=supp, dens=dens, capex_w=capex_w,
                om_mult=om_mult, wacc=wacc, crf=crf, linef=linef, coinc=coinc,
                solar_mult=solar_mult, price_mult=price_mult, life=life, inputs=inputs)


def evaluate(s, i, cov):
    """One draw, one coverage. Returns (mw, acre_feet, net_cost_usd, spill_fraction).

    The single place the FPV cost and revenue terms live. Net cost is gross annualised cost minus
    power revenue, so it is negative when an array more than pays for itself.
    """
    p = s["p"]
    load = p["onsite_load_mw"] * s["coinc"][i]
    head = np.maximum(0, p["tie_mw"] - s["hydro"]) * s["linef"][i] + np.where(s["day"] > 0, load, 0)
    solar = s["solar"] * s["solar_mult"][i]
    price = s["price"] * s["price_mult"][i]

    mw = cov * s["area_km2"][i] * s["dens"][i]
    gross = (solar * mw).sum()
    if gross <= 0:
        return mw, 0.0, 0.0, None       # None spill = "no generation", distinct from zero spill
    ac = min(mw, p["tie_mw"] * s["linef"][i] + load)
    deliv = np.minimum(np.minimum(solar * mw, ac), head)
    spill = (gross - deliv.sum()) / gross
    af = cov * s["supp"][i] * s["area_km2"][i] * s["evap"][i] * AF_PER_KM2_PER_FT
    rev = float((np.where(price > 0, deliv, 0) * price).sum())
    cost = mw * 1e6 * s["capex_w"][i] * s["crf"][i] + mw * 25_000 * s["om_mult"][i]
    return mw, af, cost - rev, spill


def run_reservoir(name, n=N):
    s = sample(name, n)
    p, inputs = s["p"], s["inputs"]
    right_mw = np.empty(n); af = np.empty(n); usd_af = np.empty(n)

    covs = np.arange(0.0025, 0.2501, 0.0025)
    for i in range(n):
        best_mw, best_af, best_cost = 0.0, 0.0, 0.0
        # largest array whose spill (inverter clip + line) stays under 5%
        for c in covs:
            mw, a, net, spill = evaluate(s, i, c)
            if spill is None:
                continue
            if spill > 0.05:
                break
            best_mw, best_af, best_cost = mw, a, net
        right_mw[i] = best_mw
        af[i] = best_af
        usd_af[i] = best_cost / best_af if best_af > 0 else np.nan

    def pct(a):
        a = a[np.isfinite(a)]
        return dict(p10=round(float(np.percentile(a, 10)), 1),
                    p50=round(float(np.percentile(a, 50)), 1),
                    p90=round(float(np.percentile(a, 90)), 1)) if len(a) else None

    # Partial rank correlation coefficients: which inputs drive the output variance.
    # Rank-based, so it is robust to the monotone-but-nonlinear responses here, and standard
    # practice for this kind of screening model.
    def prcc(y):
        ok = np.isfinite(y)
        names = list(inputs)
        X = np.array([rankdata(inputs[k][ok]) for k in names]).T
        yr = rankdata(y[ok])
        out = {}
        for i, nm in enumerate(names):
            others = np.delete(X, i, axis=1)
            A = np.column_stack([np.ones(len(others)), others])
            # residualise both the input and the output on the remaining inputs
            bx, *_ = np.linalg.lstsq(A, X[:, i], rcond=None)
            by, *_ = np.linalg.lstsq(A, yr, rcond=None)
            rx = X[:, i] - A @ bx
            ry = yr - A @ by
            d = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
            out[nm] = round(float((rx * ry).sum() / d), 3) if d > 0 else 0.0
        # A parameter with no causal path to the output still gets a small non-zero coefficient
        # from sampling noise, and printing it implies a dependence that cannot exist. Six of the
        # seven reservoirs have no shoreline load at all, so load coincidence multiplies zero and
        # can move nothing. Drop it there rather than report noise as a driver. (An unused
        # parameter was already caught once in this model; this is the conditional version of the
        # same defect.)
        if not p.get("onsite_load_mw"):
            out.pop("load_coincidence", None)
        return dict(sorted(out.items(), key=lambda kv: -abs(kv[1])))

    EXTREMES[p['dam']] = float(np.nanmin(usd_af))
    # evap_saved_af is attributed too, because the docstring makes a falsifiable claim about area:
    # it should cancel in $/AF and NOT cancel in absolute acre-feet. Asserting that in a comment
    # and never testing it is how an unchecked belief ends up published.
    return dict(right_sized_mw=pct(right_mw), evap_saved_af=pct(af), usd_per_af=pct(usd_af),
                sensitivity_prcc=dict(right_sized_mw=prcc(right_mw), usd_per_af=prcc(usd_af),
                                      evap_saved_af=prcc(af)),
                n=n)


def main():
    out = {"meta": dict(
        draws=N, seed=20260807,
        note=["Right-sized array = largest whose spill (inverter clipping plus line) stays "
              "under 5% for that draw.",
              "usd_per_af is a PUBLIC cost-effectiveness shadow cost net of power sales, not "
              "project revenue: suppressed evaporation cannot be owned or sold.",
              "Distributions are stated in the module docstring. Line share carries the largest "
              "single uncertainty and stands in for the interconnection study this model lacks."],
        distributions=dict(
            suppression="triangular(0.30, 0.75, 0.90); mode is a design assumption, not a measurement. Instrumented field results are scarce and cluster lower",
            density_mw_km2="triangular(80, 120, 160)",
            capex_per_w="triangular(1.23, 1.50, 2.50)",
            om_multiplier="triangular(1.0, 1.3, 3.0)",
            wacc="uniform(0.06, 0.09)",
            line_share="uniform(0.10, 1.00)",
            load_coincidence="uniform(0.25, 1.00)",
            evaporation="flux sites normal(mu, 5-8%); Havasu uniform(5.2, 7.4); "
                        "Upper Basin normal(mu, 30%)",
            surface_area="normal(1.00, 6%) on the modelled surface, 4% where the area is a static "
                         "published figure. Sigma is this model's own out-of-sample error against "
                         "published full-pool area (+5.5, +5.0, +7.5, -4.8% at the four testable "
                         "reservoirs). Added 2026-08-10; previously treated as exact",
            solar_resource="normal(1.00, 4%), interannual variability of annual irradiance "
                           "against the single PVGIS year",
            price_level="normal(1.00, 20%), or 30% where the price shape is transferred from "
                        "another node (Flaming Gorge, Blue Mesa). One traded year stands in for a "
                        "25-year asset",
            asset_life="triangular(20, 25, 30) years; was a fixed 25"),
        correlations={f"{a}-{b}": r for (a, b), r in COPULA_RHO.items()},
        correlation_note=(
            "Parameters are NOT drawn independently. A Gaussian copula links capex to O&M "
            "(rho 0.75, since a deep, storm-exposed, mussel-infested site raises both), capex to "
            "areal density (rho -0.35, since wide mooring corridors lower density and raise cost "
            "per watt together), capex to WACC (rho 0.25, perceived project risk), and suppression "
            "to evaporation rate (rho 0.20). Independent draws would understate the tails."))}
    print(f"{'reservoir':18} {'right-sized MW (P10/50/90)':>34} {'$/AF (P10/50/90)':>30}")
    for name in ORDER:
        r = run_reservoir(name)
        out[name] = r
        m, u = r["right_sized_mw"], r["usd_per_af"]
        print(f"{name:18} {m['p10']:>10,.0f} {m['p50']:>10,.0f} {m['p90']:>10,.0f}   "
              f"{u['p10']:>9,.0f} {u['p50']:>9,.0f} {u['p90']:>9,.0f}")
        top = list(r["sensitivity_prcc"]["usd_per_af"].items())[:3]
        print(f"{'':18}   drivers of $/AF: " + ", ".join(f"{k} {v:+.2f}" for k, v in top))
    (OUT / "fpv_uncertainty_extremes.json").write_text(json.dumps(EXTREMES, indent=1))
    (OUT / "fpv_uncertainty.json").write_text(json.dumps(out, indent=1))
    print("\nWROTE outputs/fpv_uncertainty.json")


if __name__ == "__main__":
    main()
