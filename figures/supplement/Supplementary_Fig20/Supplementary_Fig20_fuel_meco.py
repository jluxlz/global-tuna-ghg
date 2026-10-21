# -*- coding: utf-8 -*-
"""Supplementary Fig. 16 data: SF7_Fuel_Intensity + SF7_Meco_Trajectory.
Meco_Trajectory = Fig4 PanelC STEADY (2.4%/yr) E_req series;
Fuel_Intensity  = E_adj min/median across fuels per WEO x year
(from Fig4_PanelE_Intensity.csv)."""
import os, sys, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')
import pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
OUT = os.path.join(ROOT, 'scenario', 'output', 'fig5')
F4 = os.path.join(ROOT, 'figures', 'Fig4')

pe = pd.read_csv(os.path.join(F4, 'Fig4_PanelE_Intensity.csv'))
fi = pe.groupby(['WEO', 'Year']).Intensity_gCO2e_kWh.agg(['min', 'median']).reset_index()
fi.columns = ['WEO', 'Year', 'E_adj_min', 'E_adj_med']
fi.to_csv(os.path.join(OUT, 'SF7_Fuel_Intensity.csv'), index=False)

pc = pd.read_csv(os.path.join(F4, 'Fig4_PanelC_Effort_Required.csv'))
st = pc[pc.Tech_Creep == 'steady'][['Year', 'Gear', 'Design', 'E_req']].copy()
st.to_csv(os.path.join(OUT, 'SF7_Meco_Trajectory.csv'), index=False)
print('SF7_Fuel_Intensity + SF7_Meco_Trajectory written')