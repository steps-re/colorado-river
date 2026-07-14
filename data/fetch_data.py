#!/usr/bin/env python3
"""Fetch the raw datasets from their public sources (kept out of git by size).
LCRAS consumptive-use is already included (data/lcras/). GRACE/GLDAS need a free
NASA Earthdata token — set EARTHDATA_TOKEN in a local .env, then run this."""
import os, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent
def earthdata_token():
    envs = [ROOT.parent / ".env", Path.home() / ".env"]
    for e in envs:
        if e.exists():
            for l in e.read_text().splitlines():
                if l.startswith("EARTHDATA_TOKEN="):
                    return l.split("=", 1)[1].strip()
    raise SystemExit("Set EARTHDATA_TOKEN in a .env (free: https://urs.earthdata.nasa.gov/)")
# GRACE mascon (JPL RL06.3): https://podaac.jpl.nasa.gov/dataset/TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4
print("See data/README.md for GRACE/GLDAS granule URLs. LCRAS is already in data/lcras/.")
