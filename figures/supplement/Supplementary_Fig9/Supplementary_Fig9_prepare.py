"""Rebuild fuel-screen and transition proxy inputs from current source tables.

Panel d scales a same-WEO annual BAU median by the analytical intensity ratio.
It is an emission proxy, not a new whole-fleet simulation.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=ROOT/'scenario/output/fig5'

def main():
    pd.read_csv(ROOT/'figures/Fig4/Fig4_PanelE_Intensity.csv').to_csv(HERE/'Supplementary_Fig9_PanelA_Fuel_Intensity.csv',index=False)
    selected=json.loads((SOURCE/'Fig5_Final_Fuel.json').read_text())
    rows=[]
    for weo,settings in selected.items():
        for kind,fuel,nodes in [('Drop-in blend',settings['biofuel_type'],settings['biofuel_nodes']),
                                ('Newbuild fuel',settings['newfuel_type'],settings['newfuel_nodes'])]:
            for year,share in nodes.items():rows.append(dict(WEO=weo,Fuel=fuel,Path=kind,Year=int(year),Share=share))
    pd.DataFrame(rows).to_csv(HERE/'Supplementary_Fig9_PanelB_Adoption.csv',index=False)
    screen=pd.read_csv(SOURCE/'Fig5_Fuel_Options.csv')
    short={'LNG_Fossil':'LNG','NH3_Green':'NH3','H2_Fossil':'H2','H2_Green':'H2G'}
    screen['FuelOption_Raw']=screen.FuelOption
    def display(row):
        if row.Type=='Bio':return row.BioFuel
        device=short[row.DevFuel]
        return row.BioFuel+'+'+device if row.Type=='Dual' else device
    screen['FuelOption']=screen.apply(display,axis=1)
    if screen.FuelOption.isna().any() or screen.FuelOption.nunique()!=14:
        raise ValueError('Fuel screen display aliases do not cover all options')
    screen.to_csv(HERE/'Supplementary_Fig9_PanelC_Fuel_Screen.csv',index=False)
    curves=pd.read_csv(SOURCE/'Fig5_Fuel_Curves.csv')
    level={'STEPS':'Low','APS':'Medium','NZE':'High'}
    d=curves[(curves.Intensity==curves.WEO.map(level))&((curves.Type!='Dual')|(curves.BioFuel=='HVO'))].copy()
    d['Family']=np.where(d.Type=='Bio',d.BioFuel,d.DevFuel)
    d['Path']=np.where(d.Type=='Dual','Dual','Single')
    bau=pd.read_csv(SOURCE/'BAU_81_Annual.csv')
    med=bau.groupby(['WEO','Year']).GHG_Mt.median().rename('bmid').reset_index()
    d=d.merge(med,on=['WEO','Year'],validate='many_to_one')
    if d.bmid.isna().any() or len(d)!=780 or d.duplicated(['WEO','Year','Family','Path']).any():
        raise ValueError('Incomplete or duplicated transition proxy support')
    d['GHG_Mt']=d.bmid*(1-d.Reduction_pct/100)
    d.to_csv(HERE/'Supplementary_Fig9_PanelD_Transition_Curves.csv',index=False)
if __name__=='__main__':main()
