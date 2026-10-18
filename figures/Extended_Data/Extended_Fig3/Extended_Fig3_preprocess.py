#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
preprocess_extended_fig3.py - Panel CSVs for Extended Data Fig. 2
(Scale vs structure: emissions and emission intensity by RFMO region and species).

BASIS (area-based / RFMA waters, LL+PS fishing fleet):
  All panels use Base_3 grid rows attributed to the RFMA in whose waters the
  activity occurs (Organization column of the grid), with the same species
  attribution recipe as Fig1 Panel C:
      GHG_species = GHG_row * (Catch_species_row / Total_Catch_row)

  NOTE on attribution: Fig1d now uses the same book-based (effort-allocated)
  attribution as this figure, so the two agree by construction (WCPFC
  156.1 Mt). Support vessels (TP/SA) and records without grid coverage cannot
  be spatially assigned and are excluded from both (coverage: Extended Data
  Fig. 4).

Outputs (this folder):
  ExtFig3_PanelA_Org_Fleet_GHG.csv     (fleet-based org x gear-sector, Mt; Base_5)
  ExtFig3_PanelB_Org_Species_GHG.csv   (RFMA x species GHG, Mt)
  ExtFig3_PanelC_Org_Species_CEI.csv   (RFMA x species CEI, t/t; masked cells)
  ExtFig3_PanelD_Org_Year_GHG.csv      (RFMA annual GHG 1950-2025, Mt, area-based)
"""
import os, sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BASE3 = os.path.join(ROOT, "GHG_Calculation", "Base_3_Spatial_Grid_Enriched.csv")

SP = ["SKJ", "YFT", "BET", "ALB", "SBT"]
ORG = ["WCPFC", "IATTC", "ICCAT", "IOTC", "CCSBT"]

print("Reading Base_3 ...")
d = pd.read_csv(BASE3)
d = d[(d.Year >= 1950) & (d.Year <= 2025) &
      (d.Gear.isin(["LL", "PS"])) &
      (d.GHG_emissions_median > 0) &
      (d.Organization.isin(ORG))].copy()
d_all = d.copy()
d = d[d.Total_Catch > 0].copy()

# species attribution (same recipe as Fig1 Panel C)
rows = []
for sp in SP:
    c = d[sp + "_Tonnes"].fillna(0)
    ok = c > 0
    sub = d[ok]
    rows.append(pd.DataFrame({
        "Organization": sub.Organization.values,
        "Gear": sub.Gear.values,
        "Species": sp,
        "Catch_Mt": (sub[sp + "_Tonnes"].values) / 1e6,
        "GHG_Mt": (sub.GHG_emissions_median.values * c[ok].values /
                   sub.Total_Catch.values) / 1e6,
    }))
att = pd.concat(rows, ignore_index=True)

# ---- Panel A: fleet-based organisation composition (fractional equal-split) ----
# (2026-09-21: replaces the scale-vs-CEI scatter; each vessel's emissions are
#  split equally across the organisations listed in its authorisation record,
#  produced by ghg_lca as Base_5. Full 692 Mt fleet footprint, all gears.)
B5 = os.path.join(ROOT, "GHG_Calculation", "Base_5_Org_Fleet_GHG.csv")
d5 = pd.read_csv(B5)
d5 = d5[(d5.Year >= 1950) & (d5.Year <= 2025)]
pa = d5.groupby(["Organization", "Gear_Sector"]).agg(
    Total_Mt=("Total_median", "sum"),
    Total_lo=("Total_p5", "sum"),
    Total_hi=("Total_p95", "sum")).reset_index()
pa[["Total_Mt", "Total_lo", "Total_hi"]] /= 1e6
raw = np.load(os.path.join(ROOT,"GHG_Calculation","GHG_LCA_Total_Draws.npz"), allow_pickle=False)
period = (raw["years"] >= 1950) & (raw["years"] <= 2025)
cube = raw["authorized_org_sector_total"][:,:,:,period]
fleet_totals = []
for oi, org in enumerate(raw["authorized_organizations"]):
    for ci, category in enumerate(raw["gear_sectors"]):
        lo, hi = np.percentile(cube[oi,ci].sum(axis=1), [5,95]) / 1e6
        mask = pa.Organization.eq(org) & pa.Gear_Sector.eq(category)
        pa.loc[mask,["Total_lo","Total_hi"]] = [lo,hi]
    med,lo,hi = np.percentile(cube[oi].sum(axis=(0,2)),[50,5,95]) / 1e6
    fleet_totals.append(dict(Organization=org,MC_Total=med,lo=lo,hi=hi))
pd.DataFrame(fleet_totals).to_csv(os.path.join(HERE,"ExtFig3_PanelA_Total_MC.csv"), index=False)
org_order_a = (pa.groupby("Organization").Total_Mt.sum()
                 .sort_values(ascending=False).index.tolist())
pa["Organization"] = pd.Categorical(pa["Organization"], categories=org_order_a, ordered=True)
pa = pa.sort_values(["Organization", "Gear_Sector"])
pa.to_csv(os.path.join(HERE, "ExtFig3_PanelA_Org_Fleet_GHG.csv"), index=False)
print("\nPanel A (fleet-based fractional org x gear-sector, Mt):")
print(pa.pivot_table(index="Organization", columns="Gear_Sector",
                     values="Total_Mt", aggfunc="sum").round(1).to_string())

# ---- Panel B: RFMA x species GHG (Mt) ----
pb = att.groupby(["Organization", "Species"]).GHG_Mt.sum().reset_index()
pb = pb.pivot(index="Organization", columns="Species", values="GHG_Mt").reindex(ORG)[SP]
pb.to_csv(os.path.join(HERE, "ExtFig3_PanelB_Org_Species_GHG.csv"))
print("\nPanel B (GHG Mt):\n", pb.round(1).to_string())

# ---- Panel C: RFMA x species CEI (t/t; masked if catch<0.05 Mt) ----
gc = att.groupby(["Organization", "Species"]).agg(
    Catch_Mt=("Catch_Mt", "sum"), GHG_Mt=("GHG_Mt", "sum")).reset_index()
gc["CEI"] = gc.GHG_Mt / gc.Catch_Mt.where(gc.Catch_Mt > 0)
gc["Masked"] = (gc.Catch_Mt < 0.05) | (gc.CEI < 0.05)
gc.loc[gc.Masked, "CEI"] = np.nan
gc = gc[gc.Catch_Mt > 0]
gc.to_csv(os.path.join(HERE, "ExtFig3_PanelC_Org_Species_CEI.csv"), index=False)
print("\nPanel C (CEI t/t; blank = catch < 0.05 Mt):\n",
      gc.pivot(index="Organization", columns="Species", values="CEI").reindex(ORG)[SP].round(2).to_string())

# ---- Panel D: RFMA annual emissions, 1950-2025 (area-based, LL+PS) ----
# (2026-09-21: replaces the RFMA x gear bar chart now that Fig. 1d uses the
#  same book-based attribution; this panel shows when each region's emissions
#  rose. Bounds scale the flag-level p5/p95 by the same Effort_Prop weights
#  used for the median.)
ts = d_all.copy()
ts["GHG_p5"] = ts.Nat_GHG_p5 * ts.Effort_Prop
ts["GHG_p95"] = ts.Nat_GHG_p95 * ts.Effort_Prop
pd_ts = ts.groupby(["Organization", "Year"]).agg(
    GHG_Mt=("GHG_emissions_median", "sum"),
    GHG_lo=("GHG_p5", "sum"),
    GHG_hi=("GHG_p95", "sum")).reset_index()
pd_ts[["GHG_Mt", "GHG_lo", "GHG_hi"]] /= 1e6
intervals = pd.read_csv(os.path.join(ROOT,"figures/Fig1/Fig1_Org_Annual_MC.csv"))
pd_ts = pd_ts.drop(columns=["GHG_lo","GHG_hi"]).merge(
    intervals,on=["Organization","Year"],how="left",validate="one_to_one")
assert pd_ts[["GHG_lo","GHG_hi"]].notna().all().all()
pd_ts = pd_ts.sort_values(["Organization", "Year"])
pd_ts.to_csv(os.path.join(HERE, "ExtFig3_PanelD_Org_Year_GHG.csv"), index=False)
print("\nPanel D (area-based annual series, Mt CO2e):")
print(pd_ts.groupby("Organization").agg(
    Total=("GHG_Mt", "sum"), Peak=("GHG_Mt", "max")).round(1).to_string())

print("\nSanity vs Fig1 PanelC (global species GHG):",
      att.groupby("Species").GHG_Mt.sum()[SP].round(1).to_dict())
print("Sanity vs Fig1 PanelC (global species catch):",
      att.groupby("Species").Catch_Mt.sum()[SP].round(2).to_dict())
print("Done.")
