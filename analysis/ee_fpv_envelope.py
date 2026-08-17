"""Earth Engine test of the two load-bearing physical claims in the NSF FPV white paper.

CLAIM 1 (siting): a candidate portfolio at Mead and Powell can carry enough FPV to
matter, at 10-20% surface cover.
  TEST: a moored array has to stay afloat through the reservoir's operating range.
  Surface area in any single year overstates what is buildable, because the shallow
  margins go dry on drawdown. The deployable footprint is the PERSISTENTLY INUNDATED
  area -- pixels wet in every year of the record -- not the current water surface.
  Coverage fractions should be quoted against that, and they are not.

CLAIM 2 (water): evaporation suppression at that scale yields ~300,000 AF/yr.
  TEST: replace Reclamation's static ft/yr evaporation coefficients with a
  gridMET-derived reference-ET series over each lake, so the evaporation prize is
  measured year by year rather than assumed, and check how much it moves.

Outputs:
  outputs/ee_fpv_envelope.json
  outputs/ee_fpv_envelope_masks/*.png  (persistent vs max extent, for the site)

Runs on Earth Engine via the configured project. ZERO LLM tokens.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import ee

EE_PROJECT = os.environ.get("EE_PROJECT", "")
OUT = Path(os.path.expanduser("~/code/steps/colorado-river/outputs"))
IMG = OUT / "ee_fpv_envelope_masks"
IMG.mkdir(parents=True, exist_ok=True)

YEARS = list(range(2019, 2027))
M2_ACRE = 4046.8564

LAKE_BBOX = {
    "Lake Mead":   [-114.90, 35.95, -114.05, 36.62],
    "Lake Powell": [-111.55, 36.80, -110.30, 37.95],
}
# Reclamation static rates for comparison (ft/yr)
STATIC_FT = {"Lake Mead": 6.3, "Lake Powell": 3.9}
# open-water coefficient applied to grass-reference ET in an arid climate
KW_RANGE = (1.05, 1.25)


def water_mask(geom, year):
    """Summer median MNDWI water mask, same method as ee_reservoirs.py."""
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(geom)
          .filterDate(f"{year}-05-01", f"{year}-09-30")
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
          .select(["B3", "B11"]))          # select BEFORE median: much cheaper
    return s2.median().normalizedDifference(["B3", "B11"]).gt(0).rename("water")


def acres(mask, geom, scale=60):
    a = (mask.multiply(ee.Image.pixelArea())
         .reduceRegion(ee.Reducer.sum(), geom, scale, maxPixels=1e10, bestEffort=True)
         .get("water"))
    return ee.Number(a).divide(M2_ACRE)


def grid_eto(geom, year):
    """gridMET grass-reference ET summed over the year, mm -> ft, lake mean."""
    coll = (ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
            .filterDate(f"{year}-01-01", f"{year}-12-31")
            .select("eto"))
    total_mm = coll.sum()
    v = total_mm.reduceRegion(ee.Reducer.mean(), geom, 4000, maxPixels=1e10).get("eto")
    return ee.Number(v).multiply(0.00328084)   # mm -> ft


def thumb(mask, geom, path, palette):
    url = mask.selfMask().getThumbURL(
        {"region": geom, "dimensions": 700, "format": "png", "palette": palette})
    urllib.request.urlretrieve(url, path)


def main():
    ee.Initialize(project=EE_PROJECT)
    res = {}
    for lake, bbox in LAKE_BBOX.items():
        geom = ee.Geometry.Rectangle(bbox)
        # One pass: count how many years each pixel is wet. A long .And()/.Or()
        # chain over 8 S2 median composites blows the EE user-memory limit.
        counts = ee.ImageCollection([water_mask(geom, y) for y in YEARS]).sum().rename("water")
        persistent = counts.eq(len(YEARS)).rename("water")   # wet EVERY year
        anyw = counts.gte(1).rename("water")                 # wet in ANY year

        per_ac = acres(persistent, geom).getInfo()
        max_ac = acres(anyw, geom).getInfo()
        cur_ac = acres(water_mask(geom, 2026), geom).getInfo()

        # gridMET reference ET, converted to an open-water estimate
        eto = {y: float(grid_eto(geom, y).getInfo()) for y in YEARS}
        eto_mean = sum(eto.values()) / len(eto)
        lo, hi = KW_RANGE
        evap_lo, evap_hi = eto_mean * lo, eto_mean * hi

        res[lake] = {
            "persistent_acres": per_ac,
            "max_acres": max_ac,
            "current_2026_acres": cur_ac,
            "persistent_frac_of_max": per_ac / max_ac if max_ac else None,
            "persistent_frac_of_current": per_ac / cur_ac if cur_ac else None,
            "gridmet_eto_ft_by_year": eto,
            "gridmet_eto_ft_mean": eto_mean,
            "open_water_evap_ft_range": [evap_lo, evap_hi],
            "reclamation_static_ft": STATIC_FT[lake],
        }
        print(f"\n{lake}")
        print(f"  max extent (any year 2019-26)   {max_ac:>10,.0f} acres")
        print(f"  current (2026)                  {cur_ac:>10,.0f} acres")
        print(f"  PERSISTENT (wet every year)     {per_ac:>10,.0f} acres "
              f"= {per_ac/max_ac*100:.0f}% of max, {per_ac/cur_ac*100:.0f}% of current")
        print(f"  gridMET reference ET            {eto_mean:>10.2f} ft/yr "
              f"(range {min(eto.values()):.2f}-{max(eto.values()):.2f})")
        print(f"  implied open-water evaporation  {evap_lo:>10.2f}-{evap_hi:.2f} ft/yr "
              f"vs Reclamation static {STATIC_FT[lake]:.1f}")
        try:
            thumb(persistent, geom, IMG / f"{lake.replace(' ','_')}_persistent.png", ["#1d4ed8"])
            thumb(anyw, geom, IMG / f"{lake.replace(' ','_')}_max.png", ["#93c5fd"])
        except Exception as e:  # noqa: BLE001
            print(f"  (thumbnail skipped: {str(e)[:80]})")

    # --- what the persistent footprint does to the deployment story
    per_total = sum(v["persistent_acres"] for v in res.values())
    cur_total = sum(v["current_2026_acres"] for v in res.values())
    ACRES_PER_GWP = 2471.0
    print("\n--- DEPLOYABLE FOOTPRINT, PERSISTENT WATER ONLY ---")
    print(f"  persistent area, both lakes     {per_total:>10,.0f} acres "
          f"({per_total/cur_total*100:.0f}% of current surface)")
    for cov in (0.10, 0.20):
        gw = per_total * cov / ACRES_PER_GWP
        print(f"  {cov*100:.0f}% of PERSISTENT water -> {gw:>5.1f} GWp deployable")
    print(f"  ... for reference, 300,000 AF/yr needs about 31 GWp")
    print(f"  ... and the existing ties carry    2.0 GWp")

    res["_summary"] = {
        "persistent_acres_both": per_total,
        "current_acres_both": cur_total,
        "acres_per_gwp": ACRES_PER_GWP,
        "gwp_at_10pct_persistent": per_total * 0.10 / ACRES_PER_GWP,
        "gwp_at_20pct_persistent": per_total * 0.20 / ACRES_PER_GWP,
        "method": [
            "Sentinel-2 summer median MNDWI>0 water masks, 2019-2026, 30 m.",
            "Persistent = wet in EVERY year; max = wet in ANY year.",
            "gridMET grass-reference ET summed annually, x an open-water coefficient "
            "of 1.05-1.25 for an arid climate.",
        ],
        "caveats": [
            "Persistent water is a necessary but not sufficient condition for siting: "
            "it does not test depth, anchoring, navigation, recreation zones, intake "
            "exclusion areas or NPS restrictions, all of which subtract further.",
            "MNDWI at 30 m under-detects narrow canyon arms at Powell.",
            "Reference ET times an open-water coefficient is a screening estimate, "
            "not an energy-balance evaporation model.",
        ],
    }
    with open(OUT / "ee_fpv_envelope.json", "w") as f:
        json.dump(res, f, indent=1)
    print("\nwrote outputs/ee_fpv_envelope.json")


if __name__ == "__main__":
    main()
