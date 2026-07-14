#!/usr/bin/env python3
"""
M1 & M2 Expansions — Hydro-Thermal-Economic Coupling.
1. Couples M1 (Reservoir Evaporation) to M4 (Thermal Warming) using the 
   Clausius-Clapeyron relation, modeling how warmer Glen Canyon discharges 
   increase downstream Lake Mead evaporative losses.
2. Expands M2 (Economic Productivity / Value per Drop) by overlaying 
   exact volumetric crop consumption (Forage vs Produce) and calculating 
   Consumptive Portfolio Shift (CPS) curves to solve the basin deficit.

Output: outputs/expanded_m1_m2_nexus.json
"""
import json
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

# ===========================================================================
# 1. M1 to M4 Coupling: Thermal-Evaporation Feedback Model
# ===========================================================================
def sat_vapor_pressure_kpa(temp_C):
    """Clausius-Clapeyron formulation for saturation vapor pressure (kPa)."""
    return 0.6108 * np.exp((17.27 * temp_C) / (temp_C + 237.3))

def model_evap_increase_pct(base_temp_C, delta_temp_C):
    """
    Computes the percentage increase in evaporation rate due to thermal warming,
    modeled as proportional to the increase in saturation vapor pressure.
    """
    es_base = sat_vapor_pressure_kpa(base_temp_C)
    es_warm = sat_vapor_pressure_kpa(base_temp_C + delta_temp_C)
    return ((es_warm - es_base) / es_base) * 100.0

# Base parameters derived from USGS & USBR Lake Mead climatology
MEAD_BASE_TEMP_C = 22.0  # Average summer/fall surface water temperature
MEAD_ANNUAL_EVAP_AF = 800000.0  # ~0.8 MAF/yr baseline

# Glen Canyon thermal release anomalies (M4)
# When Lake Powell level drops, release temperatures increase by up to 4.5 degC (2022 peak)
temp_anomalies = [0.5, 1.0, 2.0, 3.0, 4.0, 4.5]
thermal_evap_feedback = []

for dt in temp_anomalies:
    increase_pct = model_evap_increase_pct(MEAD_BASE_TEMP_C, dt)
    extra_evap_af = MEAD_ANNUAL_EVAP_AF * (increase_pct / 100.0)
    thermal_evap_feedback.append({
        "glen_canyon_warming_discharge_delta_C": dt,
        "lake_mead_evaporation_increase_pct": round(increase_pct, 2),
        "additional_water_lost_to_atmosphere_af": round(extra_evap_af, 1),
        "additional_water_lost_to_atmosphere_maf": round(extra_evap_af / 1e6, 4)
    })

# ===========================================================================
# 2. M2 Volumetric Crop Mismatch & Consumptive Portfolio Shift (CPS)
# ===========================================================================
# USDA Census of Agriculture & Bureau of Reclamation consumptive use metrics
CROP_DATA = {
    "forage": {
        "crops": ["Alfalfa", "Hay", "Irrigated Pasture"],
        "consumptive_use_maf_yr": 5.5,  # ~80% of Lower Basin supply
        "gross_value_usd_per_af": 360.0,
        "gdp_share_pct": 8.0
    },
    "produce": {
        "crops": ["Lettuce", "Melons", "Onions", "Brassicas"],
        "consumptive_use_maf_yr": 0.9,  # ~12% of Lower Basin supply
        "gross_value_usd_per_af": 3750.0,
        "gdp_share_pct": 92.0
    }
}

# Portfolio optimization: fallow fraction of forage lands (from 0% to 50%)
fallow_fractions = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
portfolio_curves = []

for ff in fallow_fractions:
    # Fallowing forage lands
    water_saved_maf = CROP_DATA["forage"]["consumptive_use_maf_yr"] * ff
    forage_gdp_loss_usd = water_saved_maf * CROP_DATA["forage"]["gross_value_usd_per_af"]
    
    # Total agricultural GDP remaining
    total_gdp_base_usd = (CROP_DATA["forage"]["consumptive_use_maf_yr"] * CROP_DATA["forage"]["gross_value_usd_per_af"] + 
                          CROP_DATA["produce"]["consumptive_use_maf_yr"] * CROP_DATA["produce"]["gross_value_usd_per_af"])
    gdp_remaining_usd = total_gdp_base_usd - forage_gdp_loss_usd
    gdp_retention_pct = (gdp_remaining_usd / total_gdp_base_usd) * 100.0
    
    portfolio_curves.append({
        "forage_fallow_fraction": ff,
        "forage_fallow_percentage": round(ff * 100, 1),
        "water_yield_returned_to_river_maf_yr": round(water_saved_maf, 3),
        "national_agricultural_gdp_loss_usd_millions": round(forage_gdp_loss_usd / 1e6, 2),
        "regional_agricultural_gdp_retention_percentage": round(gdp_retention_pct, 2),
        "system_deficit_solved_percentage": round((water_saved_maf / 0.8) * 100.0, 1)  # 0.8 MAF is the structural deficit
    })

# ===========================================================================
# 3. Write Output
# ===========================================================================
expanded_nexus = {
    "m1_m4_thermal_evaporation_feedback": {
        "description": "Coupled thermodynamic model of Lake Mead evaporation increases due to warmer Glen Canyon discharge temperatures.",
        "lake_mead_baseline_evap_af": MEAD_ANNUAL_EVAP_AF,
        "clausius_clapeyron_sensitivity_at_22C": "An increase of 1 degC in reservoir surface temperature translates to a ~6.8% increase in saturated vapor pressure and evaporative loss.",
        "feedback_scenarios": thermal_evap_feedback
    },
    "m2_volumetric_crop_mismatch_and_portfolio_curves": {
        "description": "Portfolio shift curves modeling water savings and GDP retention from targeted forage land dry-year fallow programs.",
        "structural_deficit_maf_yr": 0.8,
        "crop_allocations": CROP_DATA,
        "portfolio_scenarios": portfolio_curves
    }
}

(OUT / "expanded_m1_m2_nexus.json").write_text(json.dumps(expanded_nexus, indent=2))
print("Successfully wrote outputs/expanded_m1_m2_nexus.json")
