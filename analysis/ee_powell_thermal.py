"""Does the Lake Powell forebay actually warm as the reservoir declines?

The NSF white paper argues that falling Powell elevations brought the warm epilimnion
close to Glen Canyon's penstock intakes, which let smallmouth bass establish below the
dam and threaten humpback chub, and that shading the surface addresses this at source.
That is a claim about temperature at intake depth. A satellite sees skin temperature
only, so this tests a necessary condition rather than the whole claim: is the surface
warming, and does it warm faster near the dam than up-lake?

A first attempt used an NDWI band-ratio water mask and returned physically impossible
values for the mid-lake control (0.82 C in 2020, 13.4 C in 2022), because cloud and
shadow leaked through. This version:
  - masks on the Landsat QA_PIXEL bit flags (cloud, dilated cloud, cirrus, cloud
    shadow, snow) rather than a band ratio,
  - takes water from the QA_PIXEL water bit,
  - returns the VALID PIXEL COUNT alongside every temperature so thin years can be
    thrown out instead of silently reported,
  - refuses to report a trend if too few years survive.

Landsat 8/9 Collection 2 Level 2, summer only. ZERO LLM tokens.
"""
from __future__ import annotations

import json
import os

import ee


def ee_init():
    """Initialise Earth Engine against whichever project the current ADC can actually
    use. The ADC identity flips between Mike's Airloom and Steps accounts depending on
    which one last ran `gcloud auth application-default login`, and each can only reach
    its own org's EE-enabled project."""
    import ee as _ee
    last = None
    for proj in [p for p in [os.environ.get("EE_PROJECT"),
                             "ai-engineering-team-491520",
                             "forge-steps-ventures"] if p]:
        try:
            _ee.Initialize(project=proj)
            _ee.Number(1).getInfo()
            print(f"[ee] using project {proj}")
            return proj
        except Exception as e:  # noqa: BLE001
            last = f"{proj}: {str(e)[:70]}"
    raise RuntimeError(f"no usable Earth Engine project. last error {last}")

EE_PROJECT = os.environ.get("EE_PROJECT", "ai-engineering-team-491520")
OUT = os.path.expanduser("~/code/steps/colorado-river/outputs")
YEARS = list(range(2014, 2027))
MIN_PIXELS = 400            # below this a year is untrustworthy at 120 m
PLAUSIBLE_C = (12.0, 40.0)  # summer skin temp bounds for a desert reservoir

ZONES = {
    # immediately upstream of Glen Canyon Dam
    "forebay": [-111.52, 36.90, -111.44, 36.98],
    # open water up-lake, well away from the dam
    "midlake": [-110.95, 37.20, -110.75, 37.40],
}


def scene(img):
    """Surface temperature in Celsius over clear water, per scene."""
    qa = img.select("QA_PIXEL")
    # Collection 2 QA_PIXEL bits: 1 dilated cloud, 2 cirrus, 3 cloud,
    # 4 cloud shadow, 5 snow, 7 water
    clear = (qa.bitwiseAnd(1 << 1).eq(0)
             .And(qa.bitwiseAnd(1 << 2).eq(0))
             .And(qa.bitwiseAnd(1 << 3).eq(0))
             .And(qa.bitwiseAnd(1 << 4).eq(0))
             .And(qa.bitwiseAnd(1 << 5).eq(0)))
    water = qa.bitwiseAnd(1 << 7).neq(0)
    st = (img.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15)
          .updateMask(clear.And(water)).rename("lst"))
    return st.updateMask(st.gt(PLAUSIBLE_C[0])).updateMask(st.lt(PLAUSIBLE_C[1]))


def summer(year):
    col = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
           .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
           .filterDate(f"{year}-06-15", f"{year}-09-15")
           .filter(ee.Filter.lt("CLOUD_COVER", 40))
           .map(scene))
    return col.median().rename("lst")


def measure(geom, year):
    img = summer(year)
    stats = img.reduceRegion(
        ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
        geom, 120, maxPixels=1e9, bestEffort=True).getInfo()
    return stats.get("lst_mean"), stats.get("lst_count")


def theil_sen(pairs):
    """Median of pairwise slopes. Robust to the odd bad year in a way OLS is not."""
    slopes = []
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            (x1, y1), (x2, y2) = pairs[i], pairs[j]
            if x2 != x1:
                slopes.append((y2 - y1) / (x2 - x1))
    if not slopes:
        return None
    slopes.sort()
    n = len(slopes)
    return slopes[n // 2] if n % 2 else (slopes[n // 2 - 1] + slopes[n // 2]) / 2


def main():
    ee_init()
    res = {z: {} for z in ZONES}
    print(f"{'year':>6}" + "".join(f"{z+' C':>13}{'px':>8}" for z in ZONES))
    for y in YEARS:
        row = f"{y:>6}"
        for z, bbox in ZONES.items():
            try:
                t, n = measure(ee.Geometry.Rectangle(bbox), y)
            except Exception as e:  # noqa: BLE001
                t, n = None, 0
                print(f"  ({z} {y} failed: {str(e)[:50]})")
            ok = t is not None and n is not None and n >= MIN_PIXELS
            res[z][y] = {"c": round(float(t), 2) if t is not None else None,
                         "pixels": int(n or 0), "usable": bool(ok)}
            row += f"{(f'{t:.2f}' if t is not None else 'n/a'):>13}{int(n or 0):>8}"
        print(row + ("" if all(res[z][y]["usable"] for z in ZONES) else "   <- thin"))

    print(f"\nYears dropped for fewer than {MIN_PIXELS} valid pixels:")
    for z in ZONES:
        bad = [y for y in YEARS if not res[z][y]["usable"]]
        print(f"  {z:<9} {bad if bad else 'none'}")

    summary = {}
    for z in ZONES:
        pairs = [(y, res[z][y]["c"]) for y in YEARS if res[z][y]["usable"]]
        slope = theil_sen(pairs)
        summary[z] = {"n_usable_years": len(pairs),
                      "theil_sen_c_per_decade": round(slope * 10, 2) if slope else None,
                      "mean_c": round(sum(p[1] for p in pairs) / len(pairs), 2) if pairs else None}
        print(f"\n  {z}: {len(pairs)} usable years, "
              f"trend {summary[z]['theil_sen_c_per_decade']} C/decade, "
              f"mean {summary[z]['mean_c']} C")

    # the claim needs the forebay to warm FASTER than open water, not just to warm
    f, m = summary["forebay"], summary["midlake"]
    verdict = None
    if f["n_usable_years"] >= 6 and m["n_usable_years"] >= 6 \
            and f["theil_sen_c_per_decade"] is not None and m["theil_sen_c_per_decade"] is not None:
        diff = f["theil_sen_c_per_decade"] - m["theil_sen_c_per_decade"]
        verdict = {"forebay_minus_midlake_c_per_decade": round(diff, 2),
                   "reads_as": ("forebay warming faster than open water" if diff > 0.3
                                else "no differential warming detectable")}
        print(f"\n  Differential: forebay minus mid-lake = {diff:+.2f} C/decade")
        print(f"  Reads as: {verdict['reads_as']}")
    else:
        print("\n  Not enough usable years in both zones to compare. Reporting no verdict.")

    out = {"by_zone": res, "summary": summary, "verdict": verdict,
           "method": [
               "Landsat 8/9 C2 L2, 15 Jun to 15 Sep, scene CLOUD_COVER < 40%.",
               "QA_PIXEL bit mask: drop dilated cloud, cirrus, cloud, cloud shadow, snow. "
               "Keep the water bit only.",
               f"Temperatures outside {PLAUSIBLE_C[0]}-{PLAUSIBLE_C[1]} C discarded as unphysical.",
               f"Years with fewer than {MIN_PIXELS} valid 120 m pixels marked unusable.",
               "Trend by Theil-Sen (median pairwise slope), not least squares.",
           ],
           "caveats": [
               "Skin temperature only. This cannot see epilimnion depth or the temperature "
               "at the penstock intakes, which is what the white paper's claim is actually about.",
               "A warming surface is consistent with the claim but does not establish it.",
               "The forebay polygon shrinks as the pool drops, so some apparent change may be "
               "the sampled area moving rather than the water warming.",
           ]}
    with open(os.path.join(OUT, "ee_powell_thermal.json"), "w") as f2:
        json.dump(out, f2, indent=1)
    print("\nwrote outputs/ee_powell_thermal.json")


if __name__ == "__main__":
    main()
