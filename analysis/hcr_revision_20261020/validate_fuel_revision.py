"""Validate fuel-only changes against the saved C/F/T pilot."""

import hashlib
import json

import numpy as np
import pandas as pd

import run_hcr as ensemble


def main():
    assert ensemble.H != ensemble.SOURCE, "Use an isolated HCR_RESULTS_ROOT"
    assert "PASS: deterministic" in (ensemble.H / "order_guard.log").read_text(encoding="utf-8-sig")
    fingerprint = ensemble.fingerprint()
    signature = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    fleet, priors, grid = ensemble.load_inputs()
    ensemble.init_worker(fleet, priors, grid, signature)
    jobs = [ensemble.make_job(40, rule) for rule in ("C", "F", "T")]
    jobs.append(ensemble.make_job(80, "T", "111"))
    checks = []
    combined = {}
    for job in jobs:
        key, _ = ensemble.run_task(job)
        old, new = ((folder / "ensemble" / key) for folder in (ensemble.SOURCE, ensemble.H))
        if job[3]["Technical"] == "000":
            for name in ("Effort.csv", "Stocks.csv"):
                pd.testing.assert_frame_equal(pd.read_csv(old / name), pd.read_csv(new / name), rtol=1e-11, atol=1e-6)
            checks.append(key)
        base, updated = [pd.read_csv(folder / "Annual.csv") for folder in (old, new)]
        assert np.isfinite(updated.Total_GHG_tCO2e).all()
        assert not np.allclose(base.Total_GHG_tCO2e, updated.Total_GHG_tCO2e)
        if job[3]["Technical"] != "000":
            combined = {"Key": key, "Max_abs_annual_catch_delta_Mt": float(
                (base.Realised_Fleet_Catch_Mt - updated.Realised_Fleet_Catch_Mt).abs().max())}
    result = {"Passed": True, "Unchanged_Stock_and_Effort_Ledgers_without_Transition": checks,
              "Combined_Technology_Check": combined, "Input_Fingerprint": fingerprint}
    (ensemble.H / "Pilot_QC.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
