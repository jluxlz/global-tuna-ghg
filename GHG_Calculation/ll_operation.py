"""Literature-informed operating priors for the historical diesel longline trial."""

from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_PRIORS = Path(__file__).resolve().parents[1] / "model_parameters" / "LL_Operation_Priors.csv"


def sample_operations(path, draws, seed):
    """Draw one set of uncertain fleet parameters per replicate, shared across years."""
    table = pd.read_csv(path)
    rng = np.random.default_rng(seed)
    samples = {}
    mixed_hours = []
    for row in table.itertuples(index=False):
        if row.Parameter == "Fishing_day_profile":
            mixed_hours.append((row.Min, row.Mode, row.Max))
            continue
        key = f"{row.Parameter}:{row.Region}"
        if key in samples or not row.Min < row.Mode < row.Max:
            raise ValueError(f"Duplicate or invalid triangular bounds: {key}")
        if row.Parameter == "Effective_days":
            if not (0 < row.Min < row.Max <= 365):
                raise ValueError(f"Operating days outside the calendar year: {key}")
        elif not (0 <= row.Min < row.Max <= 1):
            raise ValueError(f"Invalid fractional input: {key}")
        samples[key] = rng.triangular(row.Min, row.Mode, row.Max, size=draws)
    hours = np.asarray(mixed_hours)
    if hours.ndim != 2 or hours.shape[0] < 2 or np.any(hours < 0) or np.any(hours.sum(axis=1) > 24):
        raise ValueError("Expected at least two valid literature-based daily profiles")
    weights = rng.dirichlet(np.ones(len(hours)), size=draws)
    set_h, haul_h, wait_h = (weights @ hours).T
    samples.update(Setting_h=set_h, Hauling_h=haul_h, Waiting_h=wait_h,
                   Steaming_h=24 - set_h - haul_h - wait_h)
    return pd.DataFrame(samples).rename_axis("Draw")


def operation_day(samples, regions, draw, sfoc_factor):
    """Return annual effective sea days, fishing days and daily engine totals."""
    row = samples.iloc[draw]
    effective_days = row["Effective_days:Global"]
    days = np.full(len(regions), effective_days)
    for region in set(regions):
        days[regions == region] = row.get(f"Effective_days:{region}", effective_days)
    transit_fraction = row["Transit_only_fraction:Global"]
    hours = np.array([row.Steaming_h * (1 - transit_fraction) + 24 * transit_fraction,
                      row.Setting_h * (1 - transit_fraction),
                      row.Hauling_h * (1 - transit_fraction),
                      row.Waiting_h * (1 - transit_fraction)])
    loads = row[[f"{mode}_load:Global" for mode in ("Steaming", "Setting", "Hauling", "Waiting")]].to_numpy()
    assert np.isclose(hours.sum(), 24) and np.all(hours >= 0)
    return days, days * (1 - transit_fraction), float(hours @ loads), float(hours @ (loads * sfoc_factor(loads)))
