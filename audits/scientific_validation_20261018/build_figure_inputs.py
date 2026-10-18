"""Versioned SI figure bridges; originals and numbering are preserved."""
from pathlib import Path
import shutil
import pandas as pd
import numpy as np
H=Path(__file__).resolve().parent;R=H.parents[1];A=H/'analysis'
V=R/'figures/supplement/validation_20261018'

def folder(n):
    p=V/f'Supplementary_Fig{n}';p.mkdir(parents=True,exist_ok=True);return p
def save(df,p,n,letter,name):df.to_csv(p/f'Supplementary_Fig{n}_Panel{letter}_{name}.csv',index=False)

def main():
    p=folder(5);d=pd.read_csv(A/'Creep_Trends_Fractions.csv');all_=d[d.Species=='All'].copy()
    all_['Era']=all_.Era.replace({'2006-2025':'2006-2024'})
    save(all_,p,5,'A','Rates');save(all_[all_.Era=='2006-2024'],p,5,'B','Fractions')
    crit=pd.read_csv(A/'Creep_Thresholds.csv').query('Species=="All"').copy();crit['Era']=crit.Era.replace({'2006-2025':'2006-2024'})
    save(crit,p,5,'C','Thresholds')
    sb=pd.read_csv(A/'SBT_Stock_Effort_Comparison.csv').query('Rate_Label in ["Uncorrected","Adopted"]').copy()
    sb['Stock']='CCSBT SBT (TRO, digitised)';sb['Stock_index']=sb.TRO_index;sb['Window']='2009-2022';sb['Gear']='LL'
    yf=pd.read_csv(A/'YFT_Stock_Effort_Comparison.csv').query('Window=="2006-2020" and Gear=="LL"')
    stock=pd.concat([sb[['Stock','Year','Rate_Label','Effort_index','Stock_index']],yf[['Stock','Year','Rate_Label','Effort_index','Stock_index']]])
    save(stock,p,5,'D','Stock_Context')
    for f in ['Creep_Fixed_Grid_Fits.csv','Creep_RFMO_Weighted_Trends.csv','Creep_Trends_Fractions.csv','SBT_Official_TRO_Digitised.csv','SBT_Associations.csv','YFT_Associations.csv']:
        shutil.copy2(A/f,p/f)
    p=folder(15)
    save(pd.read_csv(R/'figures/supplement/Supplementary_Fig15/Supplementary_Table11_Engine_Clock.csv'),p,15,'A','Global_Clocks')
    draw=pd.read_csv(R/'audits/si_order_fuel_diagnosis_20261016/LL23_Diagnostic_Draws.csv')
    sh=[]
    for name,label in [('Main_transit','Main-engine transit'),('Main_fishing','Main-engine fishing'),('Auxiliary','Auxiliary engines')]:
        v=draw[name+'_share_pct'];sh.append(dict(Phase=label,Median=v.median(),P5=v.quantile(.05),P95=v.quantile(.95)))
    save(pd.DataFrame(sh),p,15,'B','Fuel_Phases')
    cases=['Baseline','Transit clock x0.5','Fishing clock x0.5','Auxiliary clock x0.5','Transit load x0.75','Fishing load x0.75','Auxiliary load x0.75',
           'Active fraction 0.75','Active fraction 0.50','Transit half + aux half + activity 0.75']
    d=pd.read_csv(A/'Fuel_Phase_Sensitivity.csv').set_index('Case').loc[cases].reset_index();save(d,p,15,'C','FI_Diagnostics')
    flags=pd.read_csv(R/'audits/si_order_fuel_diagnosis_20261016/LL23_Flag_Attribution.csv').sort_values('Production_Fuel_L',ascending=False)
    save(flags,p,15,'D','Flag_Coverage')
    for f in ['Fuel_Phase_Sensitivity.csv','Fuel_Cohort_Composition.csv','Fuel_Catch_Denominator.csv','Fuel_LOA_Class.csv','Fuel_Identifier_QC.csv']:
        shutil.copy2(A/f,p/f)
    p=folder(19);annual=pd.read_csv(A/'Matched_Annual.csv').query('Future=="F41"')
    save(annual,p,19,'A','Central_Annual')
    summ=pd.read_csv(A/'Matched_Mechanism_Summary.csv');save(summ,p,19,'B','Matched_Pairs')
    terms=pd.read_csv(A/'Matched_LMDI_Terms.csv');save(terms,p,19,'C','Decomposition')
    save(summ,p,19,'D','Standardisation')
    bio=pd.read_csv(A/'Matched_Stock_Effort.csv').query('Future=="F41"');save(bio,p,19,'E','Stock_Effort')
    for f in ['Matched_Closure.csv','Matched_Species.csv','Matched_Savings_Period.csv','Matched_Stock_Mechanism.csv','Matched_Processes.csv']:
        shutil.copy2(A/f,p/f)
    for n in [5,15,19]:
        p=folder(n)
        code='''"""Recreate this figure's input CSVs from the preserved validation results.
Run the audit analysis first if recomputing; see README.md for scope.
"""
from pathlib import Path
import runpy
R=Path(__file__).resolve().parents[4]
runpy.run_path(str(R/'audits/scientific_validation_20261018/build_figure_inputs.py'),run_name='__main__')
'''
        (p/f'Supplementary_Fig{n}_preprocess.py').write_text(code,encoding='utf-8')
        (p/'README.md').write_text(f'# Supplementary Fig. {n}, validation release 2026-10-18\n\nIndependent revision; original figure folder and production results preserved. Panel CSVs ship with this folder. Render the local R script to reproduce the figure without model execution. The Python bridge refreshes panel inputs from `audits/scientific_validation_20261018/analysis/`. Full computational provenance and limitations are in the audit report.\n',encoding='utf-8')
    print('Prepared three versioned SI figures; existing numbering unchanged.')
if __name__=='__main__':main()
