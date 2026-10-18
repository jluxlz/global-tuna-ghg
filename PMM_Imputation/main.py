"""PMM command entry point using the same implementation as both core models."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "GHG_Calculation"))
import ghg_lca


def main():
    pm = ghg_lca.load_prior_matrix(ghg_lca.PRIOR_MATRIX_PATH)
    return ghg_lca.run_imputation_pipeline(ghg_lca.VESSEL_REGISTRY_PATH, pm, random_seed=42)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
