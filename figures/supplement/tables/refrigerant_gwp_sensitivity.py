"""Recalculate historical GWP100 cases on identical vessel-inventory draws."""

from pathlib import Path
import os

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    inventory_dir = Path(os.environ.get("TUNA_INVENTORY_DIR", ROOT / "GHG_Calculation"))
    with np.load(inventory_dir / "GHG_LCA_Total_Draws.npz") as inventory:
        years = inventory["years"]
        total = inventory["global_Total"]
        reference = inventory["global_Refrig"]
    old_factor = 1810
    assert total.shape == reference.shape and (total >= reference - 1e-9).all()
    rows = []
    for period, mask in [("1950–2025", years >= 1950), ("2025", years == 2025)]:
        all_ghg = total[:, mask].sum(axis=1)
        old_leakage = reference[:, mask].sum(axis=1)
        for label, factor in [("No direct leakage", 0), ("IPCC AR5", 1760),
                              ("IPCC AR4 (inventory)", old_factor), ("IPCC AR6", 1960)]:
            leakage = old_leakage * (factor / old_factor)
            adjusted = all_ghg + leakage - old_leakage
            metrics = {"Total_Mt": adjusted / 1e6, "Leakage_Mt": leakage / 1e6,
                       "Leakage_share_pct": 100 * leakage / adjusted,
                       "Paired_total_change_pct": 100 * (adjusted / all_ghg - 1)}
            for metric, draws in metrics.items():
                p5, med, p95 = np.percentile(draws, [5, 50, 95])
                rows.append([period, label, factor, metric, med, p5, p95, len(draws)])
    pd.DataFrame(rows, columns=["Period", "Case", "R22_GWP100", "Metric", "Median", "P05", "P95", "Draws"]).to_csv(
        HERE / "Refrigerant_GWP100_Sensitivity.csv", index=False)

    for panel, file, col in [("B", "Fig1_PanelB_CEI_Line.csv", "GHG_With_Leakage"),
                             ("C", "Fig1_PanelC_Bubble.csv", "GHG_With_Leakage_Mt")]:
        data = pd.read_csv(ROOT / "figures/Fig1" / file)
        catch = "Total_Catch" if panel == "B" else "Total_Catch_Mt"
        keys = ["Year", "Gear"] if panel == "B" else ["Species"]
        data["CEI_With_Leakage"] = data[col] / data[catch]
        data[keys + ["CEI", "CEI_With_Leakage"]].rename(columns={"CEI": "CEI_Excluding_Direct_Leakage"}).to_csv(
            HERE / f"Fig1{panel}_Paired_Leakage_CEI.csv", index=False)


if __name__ == "__main__":
    main()
