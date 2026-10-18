#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
analyze_capacity_growth.py — historical fishing-vessel POWER trend analysis.

Purpose: extract the historical engine-power evolution of tuna fishing vessels
(Lines_Longlines, Seine_Purse_Seine) from the SAUP effort table
(GHG_Calculation/TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv —
the same PNAS-based table consumed by power_discount_factor.py) and fit the
annual growth rate, to evaluate whether the model's capacity_growth_rate
(0.02 = 2%/yr in the Fig.5 baseline) is a reasonable assumption.

Outputs (written next to this script):
  CapacityGrowth_Analysis.csv   — year × gear × sector totals and mean power
  CapacityGrowth_Fits.csv       — fitted annual growth rates per window
Console summary + recommendation. This is an ANALYSIS script; no model code
is modified.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.normpath(os.path.join(HERE, "..", "GHG_Calculation",
                                    "TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv"))

GEARS = {"LL": "Lines_Longlines", "PS": "Seine_Purse_Seine"}

df = pd.read_csv(CSV, skiprows=[1])
for col in ["NV", "P", "Year"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")
df["Gear"] = df["Gear"].astype(str).str.strip()
df["Length_Category"] = df["Length_Category"].astype(str).str.strip()
df = df[df["NV"] > 0]
fleet = df[df["Gear"].isin(list(GEARS.values()))].copy()

# ---- yearly totals: total power, vessel count, mean power per vessel ----
g = fleet.groupby(["Year", "Gear"]).agg(
    Total_Power_kW=("P", "sum"),
    N_Vessels=("NV", "sum")).reset_index()
g["Mean_Power_kW"] = g["Total_Power_kW"] / g["N_Vessels"]
g["Model_Label"] = g["Gear"].map({v: k for k, v in GEARS.items()})

g_all = fleet.groupby("Year").agg(
    Total_Power_kW=("P", "sum"),
    N_Vessels=("NV", "sum")).reset_index()
g_all["Mean_Power_kW"] = g_all["Total_Power_kW"] / g_all["N_Vessels"]
g_all["Model_Label"] = "ALL(LL+PS)"

out = pd.concat([g, g_all], ignore_index=True)
out.to_csv(os.path.join(HERE, "CapacityGrowth_Analysis.csv"), index=False)


def fit_growth(series, y0, y1):
    """Annual growth rate of a power series between years [y0, y1] via
    log-linear regression over the window (not just endpoint ratio)."""
    s = series[(series.index >= y0) & (series.index <= y1)]
    if len(s) < 3:
        return np.nan
    x = s.index.values.astype(float)
    y = np.log(np.maximum(s.values, 1e-9))
    b = np.polyfit(x, y, 1)[0]
    return np.exp(b) - 1.0


rows = []
WINDOWS = [(1950, 2017), (1970, 2017), (1980, 2017), (1990, 2017),
           (2000, 2017), (2008, 2017)]
for label, series in [("ALL(LL+PS)", g_all.set_index("Year")["Total_Power_kW"]),
                      ("LL", g[g.Model_Label == "LL"].set_index("Year")["Total_Power_kW"]),
                      ("PS", g[g.Model_Label == "PS"].set_index("Year")["Total_Power_kW"])]:
    for y0, y1 in WINDOWS:
        rows.append({"Fleet": label, "Window": f"{y0}-{y1}",
                     "Growth_pa": round(fit_growth(series, y0, y1), 5)})
    # mean-power per vessel growth (technology component, cf. power discount)
    for y0, y1 in [(1950, 2017), (1970, 2017), (2000, 2017)]:
        rows.append({"Fleet": label + " (mean power/vessel)",
                     "Window": f"{y0}-{y1}",
                     "Growth_pa": round(fit_growth(
                         g_all.set_index("Year")["Mean_Power_kW"]
                         if label == "ALL(LL+PS)"
                         else g[g.Model_Label == label].set_index("Year")["Mean_Power_kW"],
                         y0, y1), 5)})

fits = pd.DataFrame(rows)
fits.to_csv(os.path.join(HERE, "CapacityGrowth_Fits.csv"), index=False)

# ---- print ----
print("=" * 74)
print("  Tuna fishing-fleet POWER history (SAUP 1950-2017, PNAS table)")
print("=" * 74)
for label in ["ALL(LL+PS)", "LL", "PS"]:
    s = g_all.set_index("Year")["Total_Power_kW"] if label == "ALL(LL+PS)" \
        else g[g.Model_Label == label].set_index("Year")["Total_Power_kW"]
    print("\n%s  (total engine power, GW):" % label)
    print("  1950=%.2f  1980=%.2f  2000=%.2f  2010=%.2f  2017=%.2f" % (
        s.get(1950, np.nan) / 1e6, s.get(1980, np.nan) / 1e6,
        s.get(2000, np.nan) / 1e6, s.get(2010, np.nan) / 1e6,
        s.get(2017, np.nan) / 1e6))
print("\n" + "=" * 74)
print("  Fitted annual growth rates (log-linear, total power)")
print("=" * 74)
print(fits.to_string(index=False))
print("\nModel baseline assumption: capacity_growth_rate = 0.02 (2%/yr, Fig.5 BASE_CENTER)")
print("Historical reference (total tuna-fleet power): see Growth_pa rows above.")
print("Outputs: CapacityGrowth_Analysis.csv / CapacityGrowth_Fits.csv")