"""Recalculate the inventory with revised fuel operations and frozen upstream inputs."""

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

import ghg_lca as lca


SOURCE = Path(__file__).resolve().parent
FILES = ["Base_1_LCA_Global_Process", "Base_2_Fleet_GHG", "Base_3_Spatial_Grid_Enriched",
         "Base_4_Organization_GHG", "Base_5_Org_Fleet_GHG"]


def recalculate(output):
    output.mkdir(parents=True, exist_ok=False)
    matrix = lca.load_prior_matrix(lca.PRIOR_MATRIX_PATH)
    ships, pools = lca.run_imputation_pipeline(lca.VESSEL_REGISTRY_PATH, matrix, random_seed=42, write_output=False)
    ships = lca.impute_builtdate_deterministic(lca.convert_gt_to_lsw(ships, matrix), pools)
    ships["Retire_Year"], ships["Is_Ghost"] = 9999, 0
    ghost = pd.read_csv(SOURCE / "Ghost_Fleet_Reconstructed.csv")
    ships = pd.concat([lca.assign_operational_params(table, matrix) for table in [ships, ghost]], ignore_index=True)
    screening = pd.read_csv(SOURCE / "GSA_Per_Process_Top2.csv")
    _, fleet, global_data, rfmo, sectors, _, _ = lca.run_monte_carlo_lca(
        ships, matrix, end_year=2025, n_simulations=500, random_seed=42,
        lookup_data_power=lca.init_power_discount_lookup(lca.PNAS_POWER_PATH, baseline_year=2015),
        lookup_data_alpha=lca.init_time_profile_lookup(lca.PNAS_POWER_PATH, verbose=False),
        important_params=set(screening.Top1) | set(screening.Top2),
        draw_export_path=output / "GHG_LCA_Total_Draws.npz", multi_mode_fuel=True,
    )
    spatial = lca.process_catch_and_cei(lca.CATCH_ALLOCATION_PATH, fleet, matrix)
    for name, table in zip(FILES, [global_data, fleet, spatial, rfmo, sectors], strict=True):
        table.to_csv(output / (name + ".csv"), index=False, encoding="utf-8-sig")


def verify(output):
    keys = ["Year", "Flag", "Gear", "squaretypecode", "lat", "lon", "EffortType", "Organization"]
    values = ["Total_Catch", "Standard_Effort", "Effort_Prop"] + [s + "_Tonnes" for s in ["SBT", "SKJ", "BET", "YFT", "ALB"]]
    spatial = pd.read_csv(output / (FILES[2] + ".csv"), usecols=keys + values + ["Fuel_CO2_median"])
    old_grid = pd.read_csv(SOURCE / (FILES[2] + ".csv"), usecols=keys + values)
    pd.testing.assert_frame_equal(spatial[keys + values], old_grid[keys + values], rtol=1e-10, atol=1e-8)
    assert not spatial.duplicated(keys).any()
    upstream = pd.read_csv(lca.CATCH_ALLOCATION_PATH).rename(columns={"SquareTypeCode":"squaretypecode", "Lat":"lat", "Lon":"lon"})
    catches = [c for c in values if c.endswith("_Tonnes")]
    old = upstream[keys + catches].sort_values(keys).reset_index(drop=True)
    new = spatial[keys + catches].sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(old, new, rtol=1e-10, atol=1e-8)
    fleet = pd.read_csv(output / (FILES[1] + ".csv"))
    expected = fleet.groupby(["Year", "Flag", "Gear"]).Fuel_CO2_median.sum()
    allocation = spatial.groupby(["Year", "Flag", "Gear"])[["Fuel_CO2_median", "Effort_Prop"]].sum()
    np.testing.assert_allclose(allocation.Fuel_CO2_median, expected.reindex(allocation.index, fill_value=0)*allocation.Effort_Prop)
    with np.load(SOURCE / "GHG_LCA_Total_Draws.npz") as old, np.load(output / "GHG_LCA_Total_Draws.npz") as new:
        np.testing.assert_array_equal(old["years"], new["years"])
        for process in ["Build", "Maint", "Gear_Build", "Gear_Maint", "Refrig", "Bait"]:
            np.testing.assert_allclose(old["global_" + process], new["global_" + process], atol=1e-7)
    (output / "Inventory_QC.txt").write_text("PASS: catch, standard effort, spatial allocation and nonfuel draws.\n", encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        recalculate(args.output)
    verify(args.output)


if __name__ == "__main__":
    main()
