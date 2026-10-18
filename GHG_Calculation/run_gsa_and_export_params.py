"""Compatibility entry point: delegate to the single canonical historical model."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("ghg_lca.py")), run_name="__main__")
