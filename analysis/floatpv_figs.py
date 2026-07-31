"""On-brand figures for the reservoir-solar (FPV) page. Reads the model JSON outputs.
Outputs figures/fpv_*.png. Run after hourly_fpv_hydro.py / fpv_revenue_hourly.py / fpv_roi.py."""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import crstyle
crstyle.apply()
W, R, D, A, S, M = crstyle.WATER, crstyle.RUST, crstyle.DEEP, crstyle.AMBER, crstyle.SAND, crstyle.MUTED
REPO = os.path.expanduser("~/code/steps/colorado-river")
OUT, FIG = REPO + "/outputs", REPO + "/figures"
def jload(n): return json.load(open(f"{OUT}/{n}"))

# 1) OFFTAKE CEILING — curtailment vs FPV array size
d = jload("hourly_fpv_hydro.json"); sw = d["interconnection_sweep"]
gw = [s["fpv_gw"] for s in sw]
ca = [s["curtail_pct_actual_ops"] for s in sw]
cs = [s["curtail_pct_hydro_shifted"] for s in sw]
fig, ax = plt.subplots(figsize=(7, 4.3))
ax.plot(gw, ca, "o-", color=R, lw=2.4, ms=7, label="hydro runs its actual (evening-peaked) schedule")
ax.plot(gw, cs, "s--", color=W, lw=2, ms=6, label="hydro pushed to its obligatory midday floor")
ax.axvspan(0, 1.05, color=W, alpha=0.08)
ax.annotate("~1 GW fits the dam's\ninterconnection at ~2% loss",
            xy=(1, 2.2), xytext=(1.7, 16), color=D, fontsize=9,
            arrowprops=dict(arrowstyle="->", color=M))
ax.set_xlabel("Floating-solar array size on Glen Canyon's 1,320 MW tie (GW)")
ax.set_ylabel("Share of solar energy curtailed (%)")
ax.set_title("The offtake ceiling: the wires fill up fast")
ax.legend(loc="upper left")
fig.tight_layout(); fig.savefig(f"{FIG}/fpv_offtake.png", dpi=200, bbox_inches="tight"); plt.close(fig)

# 2) THE MARKET SOLAR SELLS INTO IS DETERIORATING (reconciled rational-merchant numbers)
yrs = ["2023", "2024"]
avg = [52.73, 28.61]          # SP15 average day-ahead price
cap = [31.27, 23.81]          # price FPV captures curtailing negative hours (2024 = dispatch model)
neg = [115, 1156]             # negative-price hours
x = np.arange(len(yrs)); bw = 0.36
fig, (ax, ax2) = plt.subplots(1, 2, figsize=(8.4, 4.2))
ax.bar(x - bw/2, avg, bw, color=S, label="average market price")
ax.bar(x + bw/2, cap, bw, color=R, label="price floating solar captures")
for i in range(len(yrs)):
    ax.text(x[i]+bw/2, cap[i]+1, f"${cap[i]:.0f}", ha="center", fontsize=9, color=D)
    ax.text(x[i]-bw/2, avg[i]+1, f"${avg[i]:.0f}", ha="center", fontsize=9, color=M)
ax.set_xticks(x); ax.set_xticklabels(yrs); ax.set_ylabel("$/MWh (SP15 day-ahead)")
ax.set_title("Solar captures below average,\nand the whole market is sinking", fontsize=11.5)
ax.legend(loc="upper right")
ax2.bar(x, neg, 0.5, color=R)
for i in range(len(yrs)):
    ax2.text(x[i], neg[i]+30, f"{neg[i]}", ha="center", fontsize=9.5, color=D)
ax2.set_xticks(x); ax2.set_xticklabels(yrs); ax2.set_ylabel("negative-price hours / year")
ax2.set_title("Midday negative-price hours\njumped 10x in one year", fontsize=11.5)
fig.suptitle("The midday glut floating solar produces into (SP15, Desert Southwest)", color=D, fontweight="bold")
fig.tight_layout(); fig.savefig(f"{FIG}/fpv_capture.png", dpi=200, bbox_inches="tight"); plt.close(fig)

# 3) ROI — LCOE vs capture band
roi = jload("fpv_roi.json")["scenarios"]
labels, lcoes = [], []
seen = set()
for s in roi:
    k = (s["capex"], s["itc"])
    if k in seen: continue
    seen.add(k)
    short = ("Generic" if s["capex"].startswith("generic") else "Hard site") + f" · ITC {s['itc']}"
    labels.append(short); lcoes.append(s["lcoe"])
fig, ax = plt.subplots(figsize=(7, 4.3))
xb = np.arange(len(labels))
ax.bar(xb, lcoes, 0.55, color=D, label="LCOE (cost of the solar)")
ax.axhspan(23.81, 36.09, color=R, alpha=0.18)
ax.axhline(36.09, color=R, lw=1, ls="--")
ax.axhline(23.81, color=R, lw=1, ls="--")
ax.text(len(labels)-0.5, 30, "price it can capture\n$24-36/MWh", color=R, fontsize=9, ha="right", va="center")
for i, v in enumerate(lcoes):
    ax.text(xb[i], v+2, f"${v:.0f}", ha="center", fontsize=9, color=D)
ax.set_xticks(xb); ax.set_xticklabels(labels, fontsize=8.5, rotation=12)
ax.set_ylabel("$/MWh"); ax.set_title("Cost is 2-4x the revenue: ROI is negative in every case")
ax.legend(loc="upper left")
fig.tight_layout(); fig.savefig(f"{FIG}/fpv_roi.png", dpi=200, bbox_inches="tight"); plt.close(fig)

# 4) GLOBAL SCALE
names = ["Global FPV\nbuilt/yr (2024)", "Our bounded\n~1 GW (1 dam)", "Global FPV\never built (2024)",
         "Lall's 15-20%\ncover (~tens GW)"]
vals = [1.5, 1.0, 9.16, 40]
cols = [M, W, D, R]
fig, ax = plt.subplots(figsize=(7, 4.3))
ax.bar(names, vals, color=cols)
for i, v in enumerate(vals):
    ax.text(i, v+0.8, f"{v:g} GW", ha="center", fontsize=9, color=D)
ax.set_ylabel("Gigawatts")
ax.set_title("Even the bounded case rivals the entire global floating-solar fleet")
fig.tight_layout(); fig.savefig(f"{FIG}/fpv_scale.png", dpi=200, bbox_inches="tight"); plt.close(fig)

# 5) WATER IMPACT — FPV evaporation vs release vs basin gap (log scale)
labels = ["FPV evaporation\nsaved (~1 GW)", "Basin structural\ngap", "Glen Canyon\nannual release"]
vals = [0.011, 3.0, 8.9]   # MAF
cols = [W, A, D]
fig, ax = plt.subplots(figsize=(7, 4.3))
ax.bar(labels, vals, color=cols)
ax.set_yscale("log")
for i, v in enumerate(vals):
    ax.text(i, v*1.15, f"{v:g} MAF" if v >= 0.1 else f"{v*1000:.0f}k AF", ha="center", fontsize=9, color=D)
ax.set_ylabel("Million acre-feet per year (log scale)")
ax.set_title("Solar's only real water effect is evaporation — a rounding error on the deficit")
fig.tight_layout(); fig.savefig(f"{FIG}/fpv_water.png", dpi=200, bbox_inches="tight"); plt.close(fig)

print("wrote fpv_offtake / fpv_capture / fpv_roi / fpv_scale / fpv_water .png")
