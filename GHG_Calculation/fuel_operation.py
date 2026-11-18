"""Engine activity priors shared by the historical and projected fuel models."""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd


PRIORS = Path(__file__).resolve().parents[1] / "model_parameters/Fuel_Operating_Priors.csv"


@lru_cache(maxsize=1)
def read_priors():
    table = pd.read_csv(PRIORS)
    assert not table.duplicated(["Class", "Parameter"]).any()
    assert ((table.Low <= table.Mode) & (table.Mode <= table.High) & (table.Low < table.High)).all()
    return {group: rows.set_index("Parameter")[["Low", "Mode", "High"]]
            for group, rows in table.groupby("Class", sort=False)}


def operation_classes(gear, gasoline):
    return np.where(gear == "LL", np.where(gasoline, "LL_gasoline", "LL_diesel"), gear)


def operating_day(group, p, sfoc):
    if group == "LL_diesel":
        fishing = 1 - p["transit_days"]
        cruise = 24 - p["setting_h"] - p["hauling_h"] - p["inactive_h"]
        hours = [cruise * fishing + 24 * p["transit_days"], p["setting_h"] * fishing,
                 p["hauling_h"] * fishing, p["inactive_h"] * fishing * p["idle_on"]]
    elif group == "LL_gasoline":
        hours = [p["cruise_h"], 0, p["work_h"], p["idle_h"]]
    else:
        hours = [24 - p["work_h"] - p["inactive_h"], 0, p["work_h"], p["inactive_h"] * p["idle_on"]]
    loads = np.array([p["cruise_load"], p.get("setting_load", p["work_load"]), p["work_load"], p["idle_load"]])
    assert np.min(hours) >= -1e-12 and sum(hours) <= 24 + 1e-12
    aux_load = p.get("aux_load", 0.)
    aux_energy = p.get("aux_h", 0.) * aux_load
    main_energy = np.dot(hours, loads)
    main_fuel = main_energy if group == "LL_gasoline" else np.dot(hours, loads * sfoc(loads))
    return p["days"], main_energy, main_fuel, aux_energy, aux_energy * sfoc(aux_load)


def draw_operating_days(draws, seed, sfoc):
    """Sample fleet-class parameters on a random stream separate from the inventory."""
    rng = np.random.default_rng(seed + 1)
    results = {}
    for group, bounds in read_priors().items():
        frame = pd.DataFrame({p: rng.triangular(*row, draws) for p, row in bounds.iterrows()})
        if group == "LL_diesel":
            states = ["setting_h", "hauling_h", "inactive_h"]
            invalid = frame[states].sum(axis=1) > 24
            while invalid.any():
                for state in states:
                    frame.loc[invalid, state] = rng.triangular(*bounds.loc[state], invalid.sum())
                invalid = frame[states].sum(axis=1) > 24
        results[group] = np.array([operating_day(group, row, sfoc) for row in frame.to_dict("records")])
    return results


def central_operating_days(sfoc):
    return {group: operating_day(group, rows.Mode.to_dict(), sfoc) for group, rows in read_priors().items()}
