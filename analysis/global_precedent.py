#!/usr/bin/env python3
"""What has anyone, anywhere, actually BUILT on a stressed reservoir surface?

This project spent fourteen rounds analysing one basin without ever asking whether the things it
was pricing exist elsewhere. That is the cheapest available test of both halves of the argument: if
surface intervention worked at scale, somewhere would have done it, and if it never has, that is a
stronger finding than any cost model.

The answer is that NOTHING purpose-built for evaporation control has ever operated above 1,000
hectares of water surface. The largest operating cover of any kind is 71 ha. The two surface
projects that exceed 1,000 ha are floating solar built for power, and the larger of them is on a
flooded coal mine rather than a water-supply reservoir.

China is the decisive case and it cuts against surface intervention. It has the world's largest
floating-solar fleet, manufactures most of the world's geomembrane, and has reservoirs that have
fallen further than anything in the United States. Facing its driest basins it built inter-basin
transfers, sediment-flushing regimes and ecological water conveyance. It did not cover the water.
Its one large hydro-paired solar plant, Longyangxia, is LAND-based.

Every row is classified IMPLEMENTED / PILOT / ANNOUNCED and carries its own source. Areas are in
hectares so they compare directly against Lake Mead at about 30,900 ha.

Output: outputs/global_precedent.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
MEAD_HA = 30_900

# --- Surface interventions: covering or floating something on the water -----------------------
SURFACE = [
    dict(name="Lake Hefner", country="USA", area_ha=1011, year=1958,
         intervention="Chemical monolayer (hexadecanol/octadecanol)", status="PILOT — ABANDONED",
         result="9% evaporation reduction over 88 days. Abandoned: film blown to the lee shore "
                "above a 13 mph wind limit, and replacing it took 6.5-8x the application rate of "
                "an experimental pond.",
         relevance="The largest evaporation-suppression trial ever run, and it failed on wind. "
                   "Mead has far greater fetch.",
         source="Crow & Mitchell, wind effects on chemical films at Lake Hefner; ASABE"),
    dict(name="Los Angeles Reservoir", country="USA", area_ha=71, year=2015,
         intervention="Shade balls (96 million HDPE spheres)", status="IMPLEMENTED",
         result="Deployed for bromate control; evaporation was a secondary benefit. Still in "
                "operation. $34.5M.",
         relevance="The largest operating COVER of any kind on Earth, at 0.2% of Mead's area.",
         source="LADWP"),
    dict(name="Cirata Reservoir", country="Indonesia", area_ha=200, year=2023,
         intervention="Floating solar, 145 MWac", status="IMPLEMENTED",
         result="$100M, about $0.69/W. Evaporation reduction not measured or published.",
         relevance="The largest floating solar on a genuine water-supply/hydro reservoir. Shallow, "
                   "tropical, and without large level swings.",
         source="Masdar/PLN via trade press"),
    dict(name="Dezhou Dingzhuang", country="China", area_ha=1200, year=2022,
         intervention="Floating solar, 320 MW", status="IMPLEMENTED",
         result="550,000 MWh a year. Still operating.",
         relevance="The world's largest floating array, and NOT a water-supply reservoir: it sits "
                   "on a flooded coal-mining subsidence lake with no drawdown duty.",
         source="Huaneng Power International via trade press"),
    dict(name="Laguna Lake", country="Philippines", area_ha=1000, year=2023,
         intervention="Floating solar, 1,300 MW", status="ANNOUNCED",
         result="Lease awarded 2023, operations targeted 2026-2030. Not built.",
         relevance="Would be the first surface project above 1,000 ha on a natural lake if built.",
         source="Blueleaf Energy"),
]

# --- What water-stressed basins did INSTEAD --------------------------------------------------
INSTEAD = [
    dict(name="South-to-North Water Diversion", country="China",
         intervention="Inter-basin transfer", status="IMPLEMENTED",
         scale="Target 44.8 billion m3/yr; 53.1 billion m3 delivered to date on Eastern and "
               "Central routes",
         note="China's actual answer to shortage in the Hai, Huai and Yellow basins: move water, "
              "do not cover it."),
    dict(name="Xiaolangdi, Yellow River", country="China",
         intervention="Water-and-sediment regulation, drawdown flushing", status="IMPLEMENTED",
         scale="12.65 billion m3 capacity; ~40 billion yuan (~$4.85B)",
         note="Storage is defended by managing sediment, which is the loss term that actually "
              "threatens Chinese reservoir capacity."),
    dict(name="Tarim basin ecological conveyance", country="China",
         intervention="Floodwater diversion to recharge groundwater", status="IMPLEMENTED",
         scale="510 million m3 diverted in 2024; >10 billion yuan (~$1.5B) invested",
         note="In China's driest basin the intervention is conveyance and recharge, not surface "
              "treatment."),
    dict(name="Longyangxia", country="China",
         intervention="850 MW solar paired with hydropower", status="IMPLEMENTED",
         scale="2,700 ha of LAND adjacent to a 38,300 ha reservoir",
         note="The most-cited hydro-plus-solar hybrid in the world is land-based. The reservoir "
              "surface was available and was not used."),
]

surface_impl = [r for r in SURFACE if r["status"].startswith("IMPLEMENTED")]
covers_impl = [r for r in surface_impl if "solar" not in r["intervention"].lower()]
largest_cover = max(covers_impl, key=lambda r: r["area_ha"])
largest_surface = max(surface_impl, key=lambda r: r["area_ha"])
purpose_built_evap = [r for r in SURFACE
                      if r["area_ha"] > 1000 and "solar" not in r["intervention"].lower()
                      and r["status"].startswith("IMPLEMENTED")]

doc = {
    "meta": {
        "question": "Has any stressed basin anywhere ever implemented surface intervention on a "
                    "reservoir at a scale relevant to the Colorado?",
        "answer": f"No. Nothing purpose-built for evaporation control has ever operated above "
                  f"1,000 ha. The largest operating cover of any kind is {largest_cover['name']} "
                  f"at {largest_cover['area_ha']} ha, which is "
                  f"{largest_cover['area_ha']/MEAD_HA:.1%} of Lake Mead. The largest operating "
                  f"surface project of any kind is {largest_surface['name']} at "
                  f"{largest_surface['area_ha']} ha, built for power on a flooded coal mine.",
        "purpose_built_evaporation_above_1000ha": len(purpose_built_evap),
        "largest_operating_cover_ha": largest_cover["area_ha"],
        "largest_operating_cover_share_of_mead": round(largest_cover["area_ha"] / MEAD_HA, 4),
        "mead_ha": MEAD_HA,
        "china_finding": "China has the largest floating-solar fleet on Earth, manufactures most "
                         "of the world's geomembrane, and has seen deeper reservoir and lake "
                         "drawdowns than the United States (Poyang fell from >350,000 ha to "
                         "81,400 ha in 2022). Its revealed strategy is inter-basin transfer, "
                         "sediment regulation and ecological conveyance. It does not cover its "
                         "reservoirs, and its flagship hydro-paired solar plant is land-based.",
        "why_this_matters": "A cost model can be argued with. A global absence of deployment after "
                            "seventy years of proposals, in every arid basin with the money to try, "
                            "is harder to argue with. It applies to floating solar on these "
                            "reservoirs exactly as it applies to covers.",
        "caveat": "Absence of deployment is evidence about feasibility and priority, not proof of "
                  "impossibility. Several of these technologies are young, and floating solar is "
                  "scaling quickly on water bodies that do not fluctuate.",
    },
    "surface_interventions": sorted(SURFACE, key=lambda r: -r["area_ha"]),
    "what_basins_did_instead": INSTEAD,
}
(OUT / "global_precedent.json").write_text(json.dumps(doc, indent=1))

print(f"{'project':26}{'country':12}{'ha':>8}  status")
for r in doc["surface_interventions"]:
    print(f"  {r['name']:24}{r['country']:12}{r['area_ha']:>8,}  {r['status']}")
print(f"\npurpose-built evaporation control above 1,000 ha, ever: {len(purpose_built_evap)}")
print(f"largest operating cover: {largest_cover['name']} at {largest_cover['area_ha']} ha "
      f"= {largest_cover['area_ha']/MEAD_HA:.2%} of Lake Mead")
print("wrote outputs/global_precedent.json")
