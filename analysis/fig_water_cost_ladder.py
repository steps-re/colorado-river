#!/usr/bin/env python3
"""The cost-of-water ladder: every way to get an acre-foot, on one axis.

The single most robust result in the floating-solar work, and the one that does not depend on
any of the contested modelling: covering a reservoir to stop evaporation costs roughly ten to
fifty times what it costs to pay a farmer not to irrigate. That holds whichever cover you pick
and however you size it.

Everything is annualised at 7% over its own service life, so a 10-year shade ball and a 25-year
solar array are comparable.

Outputs: figures/water_cost_ladder.png
"""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import crstyle; crstyle.apply()
FIG = ROOT / "figures"; OUT = ROOT / "outputs"
FIG.mkdir(exist_ok=True)

cmp = json.loads((OUT / "evap_cover_comparison.json").read_text())
by = {o["name"]: o["usd_per_af"] for o in cmp["options"]}

# (label, low, high, group). Conservation/desal anchors come from the site's own price
# observatory; cover costs from analysis/evap_cover_comparison.py.
ROWS = [
    ("Fallowing pilot, 2017 contract",            80,    80,  "buy"),
    ("Pay a farmer to conserve (SCIA)",          325,   400,  "buy"),
    ("Federal payment to MWD, 2026",             365,   365,  "buy"),
    ("Conserved water, all-in delivered",        600,  1000,  "buy"),
    ("Imperial Irrigation District transfer",    700,   700,  "buy"),
    ("Desalination",                            2500,  3500,  "make"),
    ("Shade balls (cheapest credible cover)",   by["Shade balls (hollow HDPE spheres)"],
                                                by["Shade balls (hollow HDPE spheres)"], "cover"),
    ("Floating solar, baseline cost",           by["Floating PV (this model, baseline cost)"],
                                                by["Floating PV (this model, baseline cost)"], "cover"),
    ("Floating cover / geomembrane",            by["Floating modular cover / geomembrane"],
                                                by["Floating modular cover / geomembrane"], "cover"),
    ("Floating solar, harsh cost case",         by["Floating PV (reviewers' harsh cost case)"],
                                                by["Floating PV (reviewers' harsh cost case)"], "cover"),
]
COLOR = {"buy": crstyle.WATER, "make": crstyle.AMBER, "cover": crstyle.RUST}
LABEL = {"buy": "Buy water that already exists", "make": "Make new water",
         "cover": "Cover the reservoir to stop evaporation"}

fig, ax = plt.subplots(figsize=(9.6, 5.4))
y = np.arange(len(ROWS))[::-1]
for i, (name, lo, hi, grp) in enumerate(ROWS):
    yy = y[i]
    c = COLOR[grp]
    if hi > lo:
        ax.plot([lo, hi], [yy, yy], color=c, lw=7, solid_capstyle="butt", alpha=.85)
        txt = f"${lo:,}–{hi:,}"
    else:
        ax.plot([lo, lo * 1.02], [yy, yy], color=c, lw=7, solid_capstyle="butt", alpha=.85)
        txt = f"${lo:,}"
    ax.text(hi * 1.13, yy, txt, va="center", fontsize=9.5, color=crstyle.DEEP, fontweight="bold")

ax.set_yticks(y)
ax.set_yticklabels([r[0] for r in ROWS], fontsize=10)
ax.set_xscale("log")
ax.set_xlim(50, 90000)
ax.set_xticks([100, 300, 1000, 3000, 10000, 30000])
ax.set_xticklabels(["$100", "$300", "$1,000", "$3,000", "$10,000", "$30,000"])
ax.set_xlabel("Cost per acre-foot of water, log scale (annualised at 7% over each option's life)")
ax.set_title("Every way to get an acre-foot on the Colorado River")
ax.grid(axis="x", alpha=.25)
ax.grid(axis="y", visible=False)

handles = [plt.Line2D([0], [0], color=COLOR[g], lw=7, label=LABEL[g]) for g in ("buy", "make", "cover")]
# no corner of this chart is free, so the legend sits below the axis
ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.13),
          ncol=3, fontsize=9, frameon=False)

ax.text(0.005, -0.24,
        "Covering water to stop evaporation costs 10-50x what it costs to pay a farmer not to irrigate. "
        "That holds for every cover,\nat every size. Shade-ball cost is LADWP's actual 2015 deployment "
        "($34.5M / 175 acres); floating-cover cost is LADWP's own\nquote for the same reservoir "
        "($250M / 175 acres). Floating solar is the only option here that also earns revenue.",
        transform=ax.transAxes, fontsize=8.2, color=crstyle.MUTED, va="top")

fig.tight_layout()
fig.savefig(FIG / "water_cost_ladder.png", dpi=200, bbox_inches="tight")
print("WROTE figures/water_cost_ladder.png")
for name, lo, hi, grp in ROWS:
    print(f"  {name:44} ${lo:>7,}" + (f" - ${hi:,}" if hi > lo else ""))
