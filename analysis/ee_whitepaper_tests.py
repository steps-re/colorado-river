"""Earth Engine tests of specific, checkable claims in the ASU/NSF FPV white paper.

Four independent tests, each aimed at an assertion the draft makes without measurement.

A. SITING ENVELOPE across the full candidate portfolio, not just Mead and Powell.
   The draft names Mead, Powell, Flaming Gorge, the reach below Hoover, and Lake Las
   Vegas. A moored array needs water that persists, so we measure persistently
   inundated area per reservoir and convert it to a deployable GWp.

B. EVAPORATION, measured year by year rather than assumed from a static coefficient.
   gridMET reference ET over each reservoir x an arid open-water coefficient.

C. THE THERMAL CLAIM. The draft argues declining Powell elevations brought the warm
   epilimnion close to Glen Canyon's intakes, enabling smallmouth bass below the dam,
   and that FPV shading addresses this at source. Satellite measures SKIN temperature,
   not epilimnion depth, so this tests a necessary condition, not the whole claim:
   is the Powell forebay surface actually warming, and does it track elevation decline?
   Landsat 8/9 Collection 2 Level 2 surface temperature, summer, forebay vs mid-lake.

D. ECOLOGICAL BASELINE. NDCI chlorophyll proxy per reservoir, so any array has a
   pre-installation baseline to be measured against.

Each test is independent and failure-isolated. Runs on the Airloom GfS project.
ZERO LLM tokens.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import ee

EE_PROJECT = os.environ.get("EE_PROJECT", "ai-engineering-team-491520")
OUT = Path(os.path.expanduser("~/code/steps/colorado-river/outputs"))
M2_ACRE = 4046.8564
ACRES_PER_GWP = 2471.0
YEARS = list(range(2019, 2027))
THERMAL_YEARS = list(range(2015, 2027))
KW = (1.05, 1.25)

# Candidate portfolio named in the white paper, plus Mohave for the below-Hoover PSH reach
RESERVOIRS = {
    "Lake Mead":       [-114.90, 35.95, -114.05, 36.62],
    "Lake Powell":     [-111.55, 36.80, -110.30, 37.95],
    "Flaming Gorge":   [-109.90, 40.85, -109.25, 41.32],
    "Lake Mohave":     [-114.72, 35.18, -114.38, 35.92],
    "Lake Las Vegas":  [-114.95, 36.07, -114.88, 36.13],
}
# Glen Canyon forebay (immediately upstream of the dam) vs a mid-lake reference
POWELL_FOREBAY = [-111.52, 36.90, -111.44, 36.98]
POWELL_MIDLAKE = [-110.95, 37.20, -110.75, 37.40]


def water_mask(geom, year):
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(geom)
          .filterDate(f"{year}-05-01", f"{year}-09-30")
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
          .select(["B3", "B11"]))
    return s2.median().normalizedDifference(["B3", "B11"]).gt(0).rename("water")


def acres(mask, geom, scale=60):
    v = (mask.multiply(ee.Image.pixelArea())
         .reduceRegion(ee.Reducer.sum(), geom, scale, maxPixels=1e10, bestEffort=True)
         .get("water"))
    return ee.Number(v).divide(M2_ACRE).getInfo()


def test_a_envelope(name, bbox):
    """One reduceRegion over a 3-band image instead of three separate round trips."""
    geom = ee.Geometry.Rectangle(bbox)
    counts = ee.ImageCollection([water_mask(geom, y) for y in YEARS]).sum()
    stack = (counts.eq(len(YEARS)).rename("persistent")
             .addBands(counts.gte(1).rename("maxext"))
             .addBands(water_mask(geom, 2026).rename("current"))
             .multiply(ee.Image.pixelArea()))
    d = stack.reduceRegion(ee.Reducer.sum(), geom, 60,
                           maxPixels=1e10, bestEffort=True).getInfo()
    per = d["persistent"] / M2_ACRE
    mx = d["maxext"] / M2_ACRE
    cur = d["current"] / M2_ACRE
    return {"persistent_acres": per, "max_acres": mx, "current_acres": cur,
            "persistent_frac_of_max": per / mx if mx else None,
            "persistent_frac_of_current": per / cur if cur else None,
            "gwp_at_10pct_persistent": per * 0.10 / ACRES_PER_GWP,
            "gwp_at_20pct_persistent": per * 0.20 / ACRES_PER_GWP}


def test_b_evap(name, bbox):
    """All years as bands of one image, reduced once."""
    geom = ee.Geometry.Rectangle(bbox)
    img = ee.Image.cat([
        ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
        .filterDate(f"{y}-01-01", f"{y}-12-31").select("eto").sum()
        .multiply(0.00328084).rename(f"y{y}") for y in YEARS])
    d = img.reduceRegion(ee.Reducer.mean(), geom, 4000, maxPixels=1e9).getInfo()
    by_year = {y: float(d[f"y{y}"]) for y in YEARS if d.get(f"y{y}") is not None}
    mean = sum(by_year.values()) / len(by_year)
    return {"eto_ft_by_year": by_year, "eto_ft_mean": mean,
            "open_water_ft_range": [mean * KW[0], mean * KW[1]]}


def _lst_image(year):
    """Landsat 8/9 C2 L2 summer-median surface temperature over water, deg C.
    Returns an unreduced image so many years can be stacked into one request."""
    def prep(img):
        st = img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15)
        ndwi = img.normalizedDifference(["SR_B3", "SR_B5"])
        return st.updateMask(ndwi.gt(0)).rename("lst")
    return (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
            .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
            .filterDate(f"{year}-06-15", f"{year}-09-15")
            .filter(ee.Filter.lt("CLOUD_COVER", 25))
            .map(prep).median())


def _lst_summer(geom, year):
    """Legacy single-region helper, kept for ad-hoc use."""
    def prep(img):
        st = img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15)
        # water mask from the optical bands of the same scene
        ndwi = img.normalizedDifference(["SR_B3", "SR_B5"])
        return st.updateMask(ndwi.gt(0)).rename("lst")
    col = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
           .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
           .filterBounds(geom)
           .filterDate(f"{year}-06-15", f"{year}-09-15")
           .filter(ee.Filter.lt("CLOUD_COVER", 25))
           .map(prep))
    med = col.median()
    v = med.reduceRegion(ee.Reducer.mean(), geom, 120, maxPixels=1e9).get("lst")
    return v


def test_c_thermal():
    """All years as bands, both regions in one reduceRegions call."""
    fore = ee.Geometry.Rectangle(POWELL_FOREBAY)
    mid = ee.Geometry.Rectangle(POWELL_MIDLAKE)
    fc = ee.FeatureCollection([ee.Feature(fore, {"zone": "forebay_c"}),
                               ee.Feature(mid, {"zone": "midlake_c"})])
    stack = ee.Image.cat([_lst_image(y).rename(f"y{y}") for y in THERMAL_YEARS])
    rows = stack.reduceRegions(fc, ee.Reducer.mean(), 120).getInfo()["features"]
    out = {"forebay_c": {}, "midlake_c": {}}
    for f in rows:
        pr = f["properties"]; z = pr["zone"]
        for y in THERMAL_YEARS:
            v = pr.get(f"y{y}")
            out[z][y] = round(float(v), 2) if v is not None else None
    # trend on the forebay series
    ys = [(y, t) for y, t in out["forebay_c"].items() if t is not None]
    if len(ys) >= 4:
        n = len(ys)
        mx = sum(y for y, _ in ys) / n
        my = sum(t for _, t in ys) / n
        num = sum((y - mx) * (t - my) for y, t in ys)
        den = sum((y - mx) ** 2 for y, _ in ys)
        out["forebay_trend_c_per_decade"] = round(num / den * 10, 2) if den else None
    return out


def test_d_ndci(name, bbox):
    geom = ee.Geometry.Rectangle(bbox)
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(geom).filterDate("2024-05-01", "2026-09-30")
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
          .select(["B3", "B4", "B5", "B11"]))
    comp = s2.median()
    water = comp.normalizedDifference(["B3", "B11"]).gt(0)
    ndci = comp.normalizedDifference(["B5", "B4"]).updateMask(water).rename("ndci")
    v = ndci.reduceRegion(ee.Reducer.mean(), geom, 60, maxPixels=1e9, bestEffort=True).get("ndci")
    v = v.getInfo()
    return {"ndci_mean_2024_2026": round(float(v), 4) if v is not None else None}


def main():
    ee.Initialize(project=EE_PROJECT)
    res = {}
    print("=== A. SITING ENVELOPE, full candidate portfolio ===")
    print(f"{'reservoir':<17}{'max ac':>10}{'current':>10}{'persistent':>12}"
          f"{'pers/max':>10}{'GWp @10%':>10}{'GWp @20%':>10}")
    for name, bbox in RESERVOIRS.items():
        try:
            r = test_a_envelope(name, bbox)
            res.setdefault(name, {})["envelope"] = r
            print(f"{name:<17}{r['max_acres']:>10,.0f}{r['current_acres']:>10,.0f}"
                  f"{r['persistent_acres']:>12,.0f}{r['persistent_frac_of_max']*100:>9.0f}%"
                  f"{r['gwp_at_10pct_persistent']:>10.2f}{r['gwp_at_20pct_persistent']:>10.2f}")
        except Exception as e:  # noqa: BLE001
            print(f"{name:<17}FAILED: {str(e)[:60]}")
            res.setdefault(name, {})["envelope"] = {"error": str(e)[:200]}

    print("\n=== B. EVAPORATION, measured per year ===")
    for name, bbox in RESERVOIRS.items():
        try:
            r = test_b_evap(name, bbox)
            res.setdefault(name, {})["evap"] = r
            yrs = r["eto_ft_by_year"]
            print(f"  {name:<17} open-water {r['open_water_ft_range'][0]:.2f}-"
                  f"{r['open_water_ft_range'][1]:.2f} ft/yr   "
                  f"(ETo range {min(yrs.values()):.2f}-{max(yrs.values()):.2f})")
        except Exception as e:  # noqa: BLE001
            print(f"  {name:<17} FAILED: {str(e)[:60]}")

    print("\n=== C. THE THERMAL CLAIM at Glen Canyon ===")
    try:
        t = test_c_thermal()
        res["_thermal"] = t
        print(f"{'year':>6}{'forebay C':>12}{'mid-lake C':>13}")
        for y in THERMAL_YEARS:
            f, m = t["forebay_c"].get(y), t["midlake_c"].get(y)
            print(f"{y:>6}{(f'{f:.2f}' if f is not None else 'n/a'):>12}"
                  f"{(f'{m:.2f}' if m is not None else 'n/a'):>13}")
        tr = t.get("forebay_trend_c_per_decade")
        if tr is not None:
            print(f"\n  forebay summer skin-temperature trend: {tr:+.2f} C/decade")
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED: {str(e)[:120]}")

    print("\n=== D. ECOLOGICAL BASELINE (NDCI) ===")
    for name, bbox in RESERVOIRS.items():
        try:
            r = test_d_ndci(name, bbox)
            res.setdefault(name, {})["ndci"] = r
            print(f"  {name:<17} NDCI {r['ndci_mean_2024_2026']}")
        except Exception as e:  # noqa: BLE001
            print(f"  {name:<17} FAILED: {str(e)[:60]}")

    res["_meta"] = {
        "acres_per_gwp": ACRES_PER_GWP,
        "caveats": [
            "Landsat ST is SKIN temperature. It cannot measure epilimnion depth or "
            "intake-depth temperature, so test C is a necessary-condition check only.",
            "Persistent water is necessary but not sufficient for siting.",
            "Lake Las Vegas is small enough that a 60 m mask is coarse for it.",
            "Reference ET x an open-water coefficient is a screening estimate.",
            "NDCI is a chlorophyll proxy, not a calibrated concentration.",
        ],
    }
    (OUT / "ee_whitepaper_tests.json").write_text(json.dumps(res, indent=1))
    print("\nwrote outputs/ee_whitepaper_tests.json")


if __name__ == "__main__":
    main()
