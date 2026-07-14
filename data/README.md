# Data

Small, central inputs are committed here. Large raw grids are fetched from their
public source (they do not belong in git).

| Dataset | Status | Source |
|---|---|---|
| LCRAS Lower Basin consumptive use, 1971–2024 | **included** (`lcras/CUL_1971-2024.xlsx`) | U.S. Bureau of Reclamation, Decree Accounting |
| Stakeholder map (sanitized) | **included** (`stakeholders.json`) | Public roles/positions, AI-enriched, human-checked |
| GRACE/GRACE-FO terrestrial water storage | fetch | NASA PO.DAAC `TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4` |
| GLDAS-2.1 Noah monthly | fetch | NASA GES DISC `GLDAS_NOAH025_M v2.1` |

GRACE/GLDAS need a free NASA Earthdata login. Put `EARTHDATA_TOKEN=...` in a local
`.env` (never commit it) and run `python data/fetch_data.py`.

The stakeholder map carries public positions only. It does not include private
outreach strategy, contact details, or negotiation tactics.
