from pathlib import Path
import sys,contextlib,io,hashlib
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'scenario'));sys.path.insert(0,str(ROOT/'figures/Fig5'))
import fleet_model as fm
import fig5_run as F

def main():
    with contextlib.redirect_stdout(io.StringIO()):fleet,pm=fm.load_baseline_fleet()
    original=fleet.copy(deep=True)
    def run(qt='C',days=365,tc=.024):
        p=F.make_params(weo='APS',ret=3,growth=.0136,tc=tc,quota_type=qt,
                        msy='C2024' if qt=='C' else 'MSY_100',forced=0)
        p['fishery_coupling']=dict(stock_parameters=str(ROOT/'scenario/output/schaefer_projection_parameters.csv'),max_operating_days=days)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return fm.run_scenario_simulation(fleet,pm,p,start_year=2025,random_seed=42)[0]
    first=run();run('F');run('C',280);run('F',365,.043);second=run()
    pd.testing.assert_frame_equal(first,second,check_exact=True,check_flags=False)
    pd.testing.assert_frame_equal(first.attrs['stock_ledger'],second.attrs['stock_ledger'],check_exact=True)
    pd.testing.assert_frame_equal(original,fleet,check_exact=True)
    (HERE/'Coupled_Order_QC.txt').write_text('PASS: bit-identical annual GHG/catch/stocks before and after other futures; input fleet unchanged.',encoding='utf-8')
    print('PASS: coupled-state run-order invariance and baseline input preservation')

if __name__=='__main__':main()
