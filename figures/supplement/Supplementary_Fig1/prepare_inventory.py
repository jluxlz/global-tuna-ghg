"""Rebuild annual vessel-type totals from the historical inventory."""
from pathlib import Path

import pandas as pd

folder = Path(__file__).resolve().parent
fleet = pd.read_csv(folder.parents[2] / "GHG_Calculation/Base_2_Fleet_GHG.csv")
annual = fleet.groupby(["Year", "Gear"], as_index=False).Nat_GHG_median.sum()
annual.rename(columns={"Nat_GHG_median": "GHG_t"}).to_csv(folder / "Supplementary_Fig1_PanelB_Annual.csv", index=False)
