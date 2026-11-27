"""Offline example using the unchanged production stock-effort modules.

All input records are synthetic. This is a mechanism demonstration, not a new
stock assessment, emission estimate, or reproduction of the complete paper.
"""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import sys
import time
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scenario"))


def main():
    started = time.perf_counter()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "demo/input")
    parser.add_argument("--output", type=Path, default=ROOT / "demo/output")
    args = parser.parse_args()
    import numpy as np
    import pandas as pd
    from fishery_coupling import FisheryCoupling
    from harvest_control_rules import target_from_rule

    inputs = args.input.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fleet = pd.read_csv(inputs / "fleet.csv")
    stock_frames, effort_frames = [], []
    for rule in ("C", "F", "T"):
        model = FisheryCoupling(
            fleet.copy(),
            {"stock_parameters": str(inputs / "stocks.csv"),
             "allocation_file": str(inputs / "allocation.csv"),
             "max_operating_days": 280},
            {"hcr": {"type": rule, "alpha": 1., "beta": 1.,
                     "b_trigger_k": .4, "b_close_k": .1},
             "tech_creep": .01, "consolidation_type": 0},
        )
        for year in range(2025, 2031):
            model.begin_year(year)
            econ = pd.DataFrame({"M_econ_raw": np.ones(len(fleet))}, index=fleet.index)
            resolved = model.resolve(fleet.copy(), econ)
            if not resolved.Operating_Days.between(0, 280 + 1e-10).all():
                raise AssertionError("Operating-day bounds failed")
        stock_frames.append(pd.DataFrame(model.ledger).assign(Rule=rule))
        effort_frames.append(pd.DataFrame(model.effort_ledger).assign(Rule=rule))
    stocks = pd.concat(stock_frames, ignore_index=True)
    effort = pd.concat(effort_frames, ignore_index=True)
    balance = stocks.B_Start_Mt + stocks.Growth_Mt - stocks.Realised_Stock_Catch_Mt - stocks.B_End_Mt
    if not np.allclose(balance, 0, atol=1e-12, rtol=0):
        raise AssertionError("Stock mass balance failed")
    if not (stocks.Realised_Stock_Catch_Mt <= stocks.Target_Catch_Mt + 1e-12).all():
        raise AssertionError("Catch exceeded target")
    if not (effort.Realised_kW_days <= effort.Capacity_kW_days + 1e-8).all():
        raise AssertionError("Effort exceeded physical capacity")
    if not (stocks.loc[stocks.HCR_Closed, "Realised_Stock_Catch_Mt"] == 0).all():
        raise AssertionError("Directed catch during closure")
    # Independent boundary examples exercise the threshold branches explicitly.
    closed, _ = target_from_rule(.1, .4, 1., {"type": "T"})
    open_t, _ = target_from_rule(.6, .4, 1., {"type": "T"})
    open_f, _ = target_from_rule(.6, .4, 1., {"type": "F"})
    if closed != 0 or open_t != open_f:
        raise AssertionError("HCR boundary cases failed")
    # Hand-calculated first-year state and rule-specific targets for DEMO_A.
    # B2025 = .2 + .4*.2*(1-.2/1) - .015 = .249 Mt.
    default_inputs = inputs == (ROOT / "demo/input").resolve()
    if default_inputs:
        first = stocks.loc[(stocks.Year == 2025) & (stocks.Stock == "DEMO_A")].set_index("Rule")
        if not np.allclose(first.B_Start_Mt, .249, atol=1e-12, rtol=0):
            raise AssertionError("Reference-year transition failed")
        if not np.allclose(first.loc[["C", "F", "T"], "Target_Catch_Mt"],
                           [.1, .0498, .024734], atol=1e-12, rtol=0):
            raise AssertionError("Hand-calculated HCR targets failed")
    summary = stocks.groupby("Rule", sort=True).agg(
        Cumulative_Catch_Mt=("Realised_Stock_Catch_Mt", "sum"),
        Minimum_B_Bmsy=("B_Bmsy_Start", "min"),
    ).reset_index()
    for filename, frame in [("stocks.csv", stocks), ("effort.csv", effort), ("summary.csv", summary)]:
        frame.to_csv(output / filename, index=False, float_format="%.12g")
    reference = ROOT / "demo/expected/summary.csv"
    reference_checked = reference.is_file() and default_inputs
    if reference_checked:
        expected = pd.read_csv(reference)
        pd.testing.assert_frame_equal(summary, expected, check_exact=False, rtol=1e-9, atol=1e-11)
    paths = [ROOT / "scenario/fishery_coupling.py", ROOT / "scenario/harvest_control_rules.py"]
    paths += [inputs / name for name in ("fleet.csv", "stocks.csv", "allocation.csv")]
    report = {
        "Passed": True, "Synthetic_Data": True, "Years": [2025, 2030],
        "Rules": ["C", "F", "T"], "Stock_Rows": len(stocks), "Effort_Rows": len(effort),
        "Maximum_Biomass_Balance_Error_Mt": float(balance.abs().max()),
        "Expected_Summary_Checked": reference_checked,
        "Default_Input_Hand_Calculations_Checked": default_inputs,
        "Python": platform.python_version(), "Platform": platform.platform(),
        "Packages": {name: version(name) for name in ("numpy", "pandas")},
        "Input_and_Model_SHA256": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name:
                                  hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "Elapsed_Seconds": time.perf_counter() - started,
    }
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: synthetic C/F/T demonstration; {len(stocks)} stock rows and {len(effort)} effort rows.")
    print(f"Output: {output}")
    print(f"Runtime including imports: {report['Elapsed_Seconds']:.3f} seconds")


if __name__ == "__main__":
    main()
