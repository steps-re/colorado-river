# Colorado River Basin — evidence, models, and a proposal

Independent analysis of the Colorado River's structural water deficit, what it costs to keep ignoring it, and a concrete way to close it. This repository holds the data, the code, and the figures behind the site so you can check the numbers and extend them.

**Live site:** https://steps-re.github.io/colorado-river/

This is independent work. It is not affiliated with, endorsed by, or produced for any agency, district, utility, or investor.

## What the analysis finds

Four load-bearing findings, each reproducible from the scripts in `analysis/`:

- **M1 — the deficit has an owner nobody named.** Reservoir evaporation and system losses run roughly 1.2 to 1.5 million acre-feet a year, and the current accounting does not clearly assign about a million of it. See `analysis/m1_structural_deficit.py`.
- **M2 — the water is worth far more than the crop grown with it.** On a large share of Lower Basin consumptive use, the marginal acre-foot produces low-value forage while cities and industry would pay many times more. See `analysis/m2_water_value.py`.
- **M3 — the losses are showing up in the ground, not just the reservoirs.** GRACE and GLDAS show sustained terrestrial water-storage decline across the basin. See `analysis/m3_grace.py` and `analysis/m3_gldas.py`.
- **M4 — low reservoirs are a thermal problem, not only a supply problem.** Falling head pushes release temperatures past ecological thresholds. See `analysis/m4_ecology.py`.

## The proposal

Pay water users to conserve, verify it with satellite evapotranspiration, shepherd the saved water to storage, and pair it with a large solar-plus-storage buildout that fills stranded transmission at the basin dams. The financial and buildability models are in `analysis/solutions_finance.py`, `analysis/solutions_model.py`, `analysis/pv_deployment_model.py`, and `analysis/pv_backtest.py`. Read the full write-up on the site.

## Reproduce it

```bash
pip install -r requirements.txt
python analysis/m1_structural_deficit.py     # or any module in analysis/
```

Each module reads from `data/` and writes its numbers to `outputs/` and its chart to `figures/`. The LCRAS consumptive-use record is included. GRACE and GLDAS grids are large, so they are fetched from NASA rather than committed. See `data/README.md`.

For the methods, assumptions, and what is verified versus estimated, read `METHODOLOGY.md`.

## What is here, and what is not

Here: the datasets, the analysis code, the computed outputs, the figures, and a stakeholder map built from public roles and positions.

Not here, by design: private outreach strategy, contact details, and negotiation tactics. The stakeholder map shows where parties stand and what a good outcome looks like for each of them. It does not include how anyone plans to move them.

## Data sources

U.S. Bureau of Reclamation (Decree Accounting, LCRAS), NASA (GRACE/GRACE-FO, GLDAS), OpenET, USGS, and EIA. All are public. Cite them, not us, when you build on the raw data.
