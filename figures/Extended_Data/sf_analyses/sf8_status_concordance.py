"""Compatibility route to verified references; no synthetic concordance."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parent.parent/"Supplementary_Fig6"/"Supplementary_Fig6_status_concordance.py"),run_name="__main__")
