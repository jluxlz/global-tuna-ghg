"""Recreate this figure's input CSVs from the preserved validation results.
Run the audit analysis first if recomputing; see README.md for scope.
"""
from pathlib import Path
import runpy
R=Path(__file__).resolve().parents[4]
runpy.run_path(str(R/'audits/scientific_validation_20261018/build_figure_inputs.py'),run_name='__main__')
