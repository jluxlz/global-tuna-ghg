"""Replay 2023 vessel fuel with paired operating assumptions. No inventory writes."""

from pathlib import Path
import inspect
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CALC = ROOT / "GHG_Calculation"
BENCH = ROOT / "figures/supplement/Supplementary_Fig18"
sys.path.insert(0, str(CALC))
import ghg_lca as lca

YEAR, DRAWS, SEED = 2023, 500, 42
CLASSES = ("PS", "LL_diesel", "LL_gasoline")
ARMS = ("Original", "Days_only", "Hours_only", "Load_only", "All")
SCOPES = {"PS23": ("PS",), "PS23I": ("PS",), "LL23": ("LL_diesel", "LL_gasoline")}


def sample_priors():
    priors = pd.read_csv(HERE / "Operating_Priors.csv")
    random = np.random.default_rng(SEED + 1)
    assert not priors.duplicated(["Class", "Parameter"]).any()
    assert ((priors.Low <= priors.Mode) & (priors.Mode <= priors.High) & (priors.Low < priors.High)).all()
    draws = {}
    for group, rows in priors.groupby("Class", sort=False):
        bounds = rows.set_index("Parameter")[["Low", "Mode", "High"]]
        frame = pd.DataFrame({p: random.triangular(*row, DRAWS) for p, row in bounds.iterrows()})
        if group == "LL_diesel":
            stages = ["setting_h", "hauling_h", "inactive_h"]
            invalid = frame[stages].sum(axis=1) > 24
            while invalid.any():
                for stage in stages:
                    frame.loc[invalid, stage] = random.triangular(*bounds.loc[stage], invalid.sum())
                invalid = frame[stages].sum(axis=1) > 24
        draws[group] = frame
    pd.concat(draws, names=["Class", "Draw"]).to_csv(HERE / "Operating_Draws.csv")
    return draws


def daily_hours(group, draw):
    """Cruising, setting (or zero), gear work, engine-on low activity."""
    if group == "PS":
        hours = [24 - draw.work_h - draw.inactive_h, 0, draw.work_h, draw.inactive_h * draw.idle_on]
    elif group == "LL_diesel":
        fish = 1 - draw.transit_days
        cruise = 24 - draw.setting_h - draw.hauling_h - draw.inactive_h
        hours = [cruise * fish + 24 * draw.transit_days, draw.setting_h * fish,
                 draw.hauling_h * fish, draw.inactive_h * fish * draw.idle_on]
    else:
        hours = [draw.cruise_h, 0, draw.work_h, draw.idle_h]
    return np.array(hours)


class Capture:
    def __init__(self, fleet, matrix, w, draws):
        fuel = fleet.Fuel_Type.to_numpy()
        gear = fleet.VesselType.to_numpy()
        assert np.all(fuel[gear == "PS"] == "MDO")
        self.indices = {"PS": np.flatnonzero(gear == "PS"),
                        "LL_diesel": np.flatnonzero((gear == "LL") & (fuel == "MDO")),
                        "LL_gasoline": np.flatnonzero((gear == "LL") & (fuel == "GASOLINE"))}
        assert sum(map(len, self.indices.values())) == np.isin(gear, ["PS", "LL"]).sum()
        self.weights, self.draws, self.matrix = w, draws, matrix
        self.results = []

    def record(self, x):
        sim = x["sim"]
        for group, idx in self.indices.items():
            draw = self.draws[group].iloc[sim]
            gas = group == "LL_gasoline"
            density = .746269 if gas else .830565
            new_h = daily_hours(group, draw)
            aux_h = 0.0 if gas else draw.aux_h
            assert new_h.min() >= 0 and new_h.sum() <= 24 and 0 <= aux_h <= 24

            def select(name):
                return x[name][idx]

            days = select("total_days")
            h = select("H_main_day")
            alpha = select("alpha")
            setting_share = new_h[1] / (new_h[1] + new_h[2])
            old_h = np.column_stack([h * (1 - alpha), h * alpha * setting_share,
                                     h * alpha * (1 - setting_share), np.zeros(len(idx))])
            old_lf = np.column_stack([select("lf_move_m"), select("lf_work_m"),
                                      select("lf_work_m"), select("lf_move_m")])
            new_lf = np.array([draw.cruise_load, draw.get("setting_load", draw.work_load),
                               draw.work_load, draw.idle_load])
            old_sfc = np.column_stack([select("sfc_m_move"), select("sfc_m_work"),
                                       select("sfc_m_work"), select("sfc_m_move")])

            def sfoc(load):
                return lca.apply_sfoc_formula(1.0, load, self.matrix)

            new_sfc = old_sfc if gas else (
                select("sfc_m_move") / sfoc(select("LF_move")))[:, None] * sfoc(new_lf)
            old_aux_h = select("H_aux_day")
            old_aux_lf = select("lf_aux_m")
            old_aux_sfc = select("sfc_a")
            if gas:
                new_aux_lf = new_aux_sfc = 0.0
            else:
                new_aux_lf = draw.aux_load
                new_aux_sfc = old_aux_sfc / sfoc(select("LF_aux")) * sfoc(new_aux_lf)
            # The same vessel, fuel allocation, activity mask, power and base SFC draw enter every arm.
            scale = select("fc_array") * select("active_mask") * select("sf") * 1000 / density
            main = select("P_main")
            aux = select("P_aux")
            original = sum(select(name) for name in ("fuel_t_move", "fuel_t_work", "fuel_t_aux"))
            base_main = main * np.sum(old_h * old_lf * old_sfc, axis=1)
            base_aux = aux * old_aux_h * old_aux_lf * old_aux_sfc
            np.testing.assert_allclose((base_main + base_aux) * days * scale,
                                       (original * select("sf") * 1000 / density), rtol=1e-11, atol=1e-6)
            configurations = [
                (days, old_h, old_lf, old_sfc, old_aux_h, old_aux_lf, old_aux_sfc),
                (draw.days, old_h, old_lf, old_sfc, old_aux_h, old_aux_lf, old_aux_sfc),
                (days, new_h, old_lf, old_sfc, aux_h, old_aux_lf, old_aux_sfc),
                (days, old_h, new_lf, new_sfc, old_aux_h, new_aux_lf, new_aux_sfc),
                (draw.days, new_h, new_lf, new_sfc, aux_h, new_aux_lf, new_aux_sfc),
            ]
            groups = {"Global": np.ones(len(idx))}
            groups.update({scope: self.weights[scope][idx] for scope, types in SCOPES.items() if group in types})
            for arm, settings in zip(ARMS, configurations, strict=True):
                d, mh, ml, ms, ah, al, rate = settings
                main_l = main * np.sum(mh * ml * ms, axis=1) * d * scale
                aux_l = aux * ah * al * rate * d * scale
                assert np.isfinite(main_l).all() and np.isfinite(aux_l).all()
                for scope, weights in groups.items():
                    self.results.append([sim, group, scope, arm, main_l @ weights, aux_l @ weights])


def report(capture, benchmark):
    result = pd.DataFrame(capture.results, columns=["Draw", "Class", "Scope", "Arm", "Main_L", "Aux_L"])
    ll = result.loc[result.Class.isin(CLASSES[1:])].groupby(["Draw", "Scope", "Arm"], as_index=False)[
        ["Main_L", "Aux_L"]].sum().assign(Class="LL_all")
    result = pd.concat([result, ll], ignore_index=True)
    result["Fuel_L"] = result.Main_L + result.Aux_L
    base = result.loc[result.Arm.eq("Original"), ["Draw", "Class", "Scope", "Fuel_L"]]
    result = result.merge(base.rename(columns={"Fuel_L": "Original_L"}), on=["Draw", "Class", "Scope"],
                          validate="many_to_one")
    assert result.Original_L.gt(0).all()
    result["Change_pct"] = (result.Fuel_L / result.Original_L - 1) * 100
    result.to_csv(HERE / "Paired_Fuel_Draws.csv", index=False)
    rows = []
    references = {"PS23": 496.3, "LL23": 1523.3}
    for (group, scope, arm), values in result.groupby(["Class", "Scope", "Arm"], sort=False):
        assert len(values) == DRAWS
        quantiles = values[["Fuel_L", "Change_pct"]].quantile([.05, .5, .95])
        row = {"Class": group, "Scope": scope, "Arm": arm}
        for i, label in enumerate(("P05", "Median", "P95")):
            row[f"Fuel_ML_{label}"] = quantiles.Fuel_L.iloc[i] / 1e6
            row[f"Change_pct_{label}"] = quantiles.Change_pct.iloc[i]
        row["Aux_share_pct_median"] = (100 * values.Aux_L / values.Fuel_L).median()
        if group in ("PS", "LL_all") and scope in SCOPES:
            for i, label in enumerate(("P05", "Median", "P95")):
                row[f"FUI_L_t_{label}"] = quantiles.Fuel_L.iloc[i] / benchmark.loc[scope, "Model_catch_t"]
            row["ISSF_L_t"] = references.get(scope, np.nan)
            row["Archived_model_FUI_L_t"] = benchmark.loc[scope, "Model_FUI_L_t"]
        rows.append(row)
    pd.DataFrame(rows).to_csv(HERE / "Fuel_Trial_Summary.csv", index=False)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pm = lca.load_prior_matrix(lca.PRIOR_MATRIX_PATH)
    fleet, pools = lca.run_imputation_pipeline(lca.VESSEL_REGISTRY_PATH, pm, random_seed=SEED, write_output=False)
    fleet = lca.impute_builtdate_deterministic(lca.convert_gt_to_lsw(fleet, pm), pools)
    fleet["Retire_Year"], fleet["Is_Ghost"] = 9999, 0
    ghost = pd.read_csv(CALC / "Ghost_Fleet_Reconstructed.csv")
    fleet = pd.concat([lca.assign_operational_params(table, pm) for table in (fleet, ghost)], ignore_index=True)
    scopes = pd.read_csv(BENCH / "Matched_Flag_Gear_Sector_Audit.csv")
    benchmark = pd.read_csv(BENCH / "Model_Matched_Summaries.csv").set_index("Benchmark_ID")
    keys = ["Flag", "Gear", "Sector"]
    weights = {}
    for scope in SCOPES:
        subset = scopes.loc[scopes.Benchmark_ID.eq(scope) & scopes.Year.eq(YEAR), keys + ["Scope_share"]]
        weights[scope] = (fleet.rename(columns={"VesselType": "Gear"})[keys]
                          .merge(subset, on=keys, how="left", validate="many_to_one").Scope_share.fillna(0).to_numpy())
        assert np.all((weights[scope] >= 0) & (weights[scope] <= 1 + 1e-8))

    capture = Capture(fleet, pm, weights, sample_priors())
    # Instrument the same calculation used by the previous read-only diagnostic.
    # The hook never changes normal LCA variables or consumes its random stream.
    source = inspect.getsource(lca.run_monte_carlo_lca)
    marker = '            fuel_co2 *= sf'
    assert source.count(marker) == 1
    source = source.replace(marker, f"            if year == {YEAR}:\n                _capture.record(locals())\n" + marker)
    namespace = dict(lca.__dict__, _capture=capture)
    exec(compile(source, "<paired_fuel_diagnostic>", "exec"), namespace)
    selection = pd.read_csv(CALC / "GSA_Per_Process_Top2.csv")
    namespace["run_monte_carlo_lca"](
        fleet, pm, start_year=YEAR, end_year=2025, n_simulations=DRAWS, random_seed=SEED,
        lookup_data_power=lca.init_power_discount_lookup(lca.PNAS_POWER_PATH, baseline_year=2015),
        lookup_data_alpha=lca.init_time_profile_lookup(lca.PNAS_POWER_PATH, verbose=False),
        important_params=set(selection.Top1) | set(selection.Top2),
    )
    report(capture, benchmark)


if __name__ == "__main__":
    main()
