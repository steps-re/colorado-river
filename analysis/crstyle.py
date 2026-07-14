"""Shared on-brand matplotlib style for all Colorado River figures (matches the site)."""
import matplotlib as mpl
STONE="#E7E1D4"; PAPER="#F4F0E7"; INK="#1E2B2E"; DEEP="#123137"; MUTED="#5B6A6A"
WATER="#2C7A87"; RUST="#A8432B"; AMBER="#9C7A2E"; LINE="#C6BBA4"; SAND="#B9885A"
def apply():
    mpl.rcParams.update({
        "figure.facecolor":PAPER, "axes.facecolor":PAPER, "savefig.facecolor":PAPER,
        "font.family":"sans-serif", "font.sans-serif":["Helvetica Neue","Helvetica","Arial","DejaVu Sans"],
        "font.size":11, "axes.titlesize":13, "axes.titleweight":"bold", "axes.titlecolor":DEEP,
        "axes.labelcolor":INK, "axes.labelsize":10.5, "text.color":INK,
        "axes.edgecolor":LINE, "axes.linewidth":0.8, "axes.grid":True, "grid.color":"#D8CFBD",
        "grid.linewidth":0.6, "grid.alpha":0.7, "xtick.color":MUTED, "ytick.color":MUTED,
        "xtick.labelsize":9, "ytick.labelsize":9, "axes.spines.top":False, "axes.spines.right":False,
        "legend.frameon":False, "legend.fontsize":8.5, "figure.dpi":140,
    })
CYC=[WATER, RUST, DEEP, AMBER, SAND, MUTED]
