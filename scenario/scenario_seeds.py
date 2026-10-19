"""Explicit seed pairing for the documented 81-future scenario grid.

The future, not its policy package or dispatch position, determines the seed.
Replicate zero preserves the original BAU seeds (42..122) and the existing
resource/capacity ensemble. Other replicates use disjoint 81-seed blocks.
Shared initial seeds do not guarantee draw-by-draw coupling after policies
change fleet size or the number of random draws.
"""
import hashlib
import itertools
import json
from pathlib import Path

PROTOCOL = "future-paired-v1"
BASE_SEED = 42
FUTURES = tuple(itertools.product(
    ("STEPS", "APS", "NZE"), (0.0021, 0.0136, 0.0272), (1, 2, 3),
    (0.019, 0.024, 0.043)))


def future_index(future):
    w, g, r, t = future
    key = (str(w), round(float(g), 8), int(r), round(float(t), 8))
    try:
        return FUTURES.index(key)
    except ValueError as exc:
        raise ValueError(f"Future outside the documented scenario grid: {key}") from exc


def paired_seed(future, replicate=0):
    if not isinstance(replicate, int) or replicate < 0:
        raise ValueError("replicate must be a nonnegative integer")
    return BASE_SEED + future_index(future) + len(FUTURES) * replicate


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def simulation_fingerprint():
    root = Path(__file__).resolve().parents[1]
    files = ("PMM_Imputation/After_PMM_Vessels.csv",
        "vessel_data_extract/Unified_Vessel_Registry.csv",
        "effort_data/Share5_Lookup_FlagGearYear.csv",
        "effort_data/Grid_Catch_Allocation.csv",
        "GHG_Calculation/Base_3_Spatial_Grid_Enriched.csv",
        "GHG_Calculation/operational_hours_lookup.py",
        "GHG_Calculation/power_discount_factor.py",
        "GHG_Calculation/TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv",
        "scenario/fishery_coupling.py", "scenario/fig5_allocation.py",
        "scenario/fleet_model.py", "scenario/price_loader.py",
        "scenario/scenario_seeds.py", "figures/Fig5/fig5_run.py",
        "GHG_Calculation/ghg_lca.py", "model_parameters/Prior_Matrix.csv",
        "model_parameters/Scenario_Fuel_Parameters.xlsx",
        "model_parameters/Scenario_Fuel_Price_Matrix.xlsx",
        "scenario/output/schaefer_biomass_annual.csv",
        "scenario/output/schaefer_biomass_annual_F.csv",
        "scenario/output/fig5/Fig5_Final_Fuel.json",
        "scenario/output/fig5/Fig5_Final_Quota.json")
    return {f:sha256(root/f) for f in files}


def record_seed_protocol(folder, filenames):
    folder = Path(folder)
    path = folder / "Seed_Provenance.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    if data.get("protocol") != PROTOCOL:
        data = {"protocol": PROTOCOL, "files": {}}
    fingerprint = simulation_fingerprint()
    if data.get("inputs") != fingerprint:
        data["files"] = {}
    data["inputs"] = fingerprint
    for name in filenames:
        data["files"][name] = sha256(folder / name)
    data["future_seeds"] = [dict(future=f"F{i+1:02d}",
        configuration=list(f), seed=paired_seed(f)) for i, f in enumerate(FUTURES)]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def require_seed_protocol(folder, filenames):
    folder = Path(folder)
    path = folder / "Seed_Provenance.json"
    if not path.exists():
        raise RuntimeError("Unverified seed pairing. Run the complete paired ensemble before reusing outputs.")
    data = json.loads(path.read_text())
    if data.get("protocol") != PROTOCOL:
        raise RuntimeError("Incompatible seed protocol in saved simulations")
    current = simulation_fingerprint()
    compatible = data.get("distribution_compatible_inputs")
    if data.get("inputs") != current and compatible != current:
        raise RuntimeError("Simulation code/inputs changed; saved baselines require a complete rerun")
    for name in filenames:
        if data.get("files", {}).get(name) != sha256(folder / name):
            raise RuntimeError(f"Saved output changed or lacks seed provenance: {name}")
