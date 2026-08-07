#!/usr/bin/env python3
"""Measured water-surface area for all seven Colorado River reservoirs in the explorer.

WHY: the coverage explorer was mixing area conventions -- Reclamation five-year operating
averages for the Lower Basin, but FULL POOL for Flaming Gorge, Navajo and Blue Mesa. Full pool
badly overstates reservoirs that have been drawn down for years, which in turn overstates both
the panel area available and the evaporation. Comparing reservoirs in one selector demands one
method for all of them.

METHOD: summer (May-Sep) low-cloud Sentinel-2 median composite -> MNDWI = (B3-B11)/(B3+B11)
-> water where MNDWI > 0 -> area via pixelArea at 30 m. The analysis region is each reservoir's
real OSM full-pool polygon (from fpv_reservoir_outlines.py), NOT a bounding box: Lake Mead's box
overlaps the head of Lake Mohave below Hoover Dam and would double-count it.

Outputs: outputs/ee_reservoir_area_all.csv  (lake, year, water_acres, water_km2)
Earth Engine (forge-steps-ventures, non-commercial). ZERO Claude tokens.
"""
import csv, json
from pathlib import Path
import ee

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
EE_PROJECT = "forge-steps-ventures"
YEARS = list(range(2019, 2027))
M2_ACRE = 4046.8564


def main():
    ee.Initialize(project=EE_PROJECT)
    print(f"EE init {EE_PROJECT}", flush=True)
    outlines = json.loads((OUT / "reservoir_outlines.json").read_text())

    csv_path = OUT / "ee_reservoir_area_all.csv"
    # Resume support: 56 reduceRegion calls at 30 m is a long serial round-trip, so write
    # each result as it lands and skip anything already measured on a re-run.
    done = {}
    if csv_path.exists():
        for r in csv.DictReader(open(csv_path)):
            done[(r["lake"], int(r["year"]))] = r
        print(f"resuming: {len(done)} rows already measured", flush=True)

    f = open(csv_path, "w", newline="")
    w = csv.DictWriter(f, fieldnames=["lake", "year", "water_acres", "water_km2"])
    w.writeheader()
    rows = []
    for lake, meta in outlines.items():
        ring = meta.get("ring_lonlat")
        if not ring:
            print(f"{lake}: no ring, skipped"); continue
        # buffer outward a little so a slightly-simplified shoreline does not clip real water
        geom = ee.Geometry.Polygon([ring], None, False).buffer(300)
        for year in YEARS:
            if (lake, year) in done:
                rows.append(done[(lake, year)]); w.writerow(done[(lake, year)]); f.flush()
                continue
            s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                  .filterBounds(geom)
                  .filterDate(f"{year}-05-01", f"{year}-09-30")
                  .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)))
            mndwi = s2.median().normalizedDifference(["B3", "B11"]).rename("mndwi")
            area_m2 = (mndwi.gt(0).multiply(ee.Image.pixelArea())
                       .reduceRegion(ee.Reducer.sum(), geom, scale=30,
                                     maxPixels=int(1e12), bestEffort=True).get("mndwi"))
            got = ee.Number(area_m2).divide(1e6).getInfo() if area_m2 is not None else None
            km2 = float(got) if got is not None else 0.0
            acres = km2 * 1e6 / M2_ACRE
            row = {"lake": lake, "year": year,
                   "water_acres": round(acres), "water_km2": round(km2, 1)}
            rows.append(row); w.writerow(row); f.flush()
            print(f"  {lake:18} {year}: {km2:>7.1f} km2 ({round(acres):>7,} ac)", flush=True)
    f.close()
    print(f"\nWROTE outputs/ee_reservoir_area_all.csv ({len(rows)} rows)")
    rows = [{**r, "water_acres": int(r["water_acres"]), "year": int(r["year"])} for r in rows]

    # recent mean (the number the explorer should use) vs full-pool/published
    print("\nrecent 3-yr mean (2024-2026):")
    for lake in outlines:
        vals = [r["water_acres"] for r in rows if r["lake"] == lake and r["year"] >= 2024]
        if vals:
            print(f"  {lake:18} {round(sum(vals)/len(vals)):>8,} ac")


if __name__ == "__main__":
    main()
