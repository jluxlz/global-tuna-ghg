import pandas as pd
import numpy as np

# ==========================================
# 🚨 极其关键：强制 Matplotlib 在后台绘图，彻底解决 Tkinter 崩溃问题
# ==========================================
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt

import shap
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error, mean_absolute_percentage_error
import time
import warnings
warnings.filterwarnings('ignore')


# ==========================================
# 0. 全局参数配置区 (供快速调参)
# ==========================================
# 🌲 随机森林代理模型超参数 (Random Forest Hyperparameters)
RF_PARAMS = {
    'n_estimators': 200,      # 决策树的数量 (越大模型越稳定，但训练越慢)
    'max_depth': 12,          # 树的最大深度 (控制模型复杂度，捕捉非线性交互)
    'min_samples_split': 2,   # 节点分裂所需的最小样本数
    'random_state': 42,       # 随机种子，确保结果可复现
    'n_jobs': -1              # 调用所有 CPU 核心进行并行计算
}

# 🎯 蒙特卡洛引擎参数
GSA_CONFIG = {
    'n_simulations': 2000,    # 蒙特卡洛采样的总次数
    'target_year': 2025,      # 提取敏感性切片的基准年份
    'seed': 42                # 全局随机种子
}


# ==========================================
# 1. 基础映射与核心参数定义
# ==========================================
FC_LOOKUP = {
    1950: 1.21, 1951: 1.21, 1952: 1.20, 1953: 1.20, 1954: 1.20, 1955: 1.20,
    1956: 1.20, 1957: 1.20, 1958: 1.20, 1959: 1.19, 1960: 1.19, 1961: 1.19,
    1962: 1.19, 1963: 1.18, 1964: 1.18, 1965: 1.18, 1966: 1.18, 1967: 1.17,
    1968: 1.16, 1969: 1.16, 1970: 1.15, 1971: 1.14, 1972: 1.14, 1973: 1.13,
    1974: 1.12, 1975: 1.11, 1976: 1.11, 1977: 1.10, 1978: 1.09, 1979: 1.09,
    1980: 1.08, 1981: 1.07, 1982: 1.07, 1983: 1.06, 1984: 1.06, 1985: 1.05,
    1986: 1.05, 1987: 1.04, 1988: 1.04, 1989: 1.04, 1990: 1.03, 1991: 1.03,
    1992: 1.03, 1993: 1.02, 1994: 1.02, 1995: 1.02, 1996: 1.01, 1997: 1.01,
    1998: 1.01, 1999: 1.00, 2000: 1.00, 2001: 1.00, 2002: 1.00, 2003: 1.00,
    2004: 0.99, 2005: 0.99, 2006: 0.99, 2007: 0.99, 2008: 0.99, 2009: 0.99,
    2010: 0.99, 2011: 0.99, 2012: 0.99, 2013: 0.99, 2014: 0.99, 2015: 0.99,
    2016: 0.99
}

def get_fc_val(year):
    if year < 1950: return 1.21
    if year > 2016: return 0.99
    return FC_LOOKUP.get(year, 0.99)

T_map_base = {'LL': 334, 'PS': 195, 'TS': 300}
H_map = {'LL': 6, 'PS': 24, 'TS': 24}
SFR_map_base = {'< 12m': 0.00035, '>= 12m': 0.0002}

EF_fuel_base = {'< 12m': 3.01, '>= 12m': 3.17}
EF_gear_base = 8.63211   
EF_bait_base = 0.454     
EF_build_base = 2.228    

# ==========================================
# 2. 极速 LCA-GSA 蒙特卡洛引擎
# ==========================================
def generate_gsa_dataset(pmm_files, n_simulations=2000, target_year=2025, min_n=5, seed=42):
    print(f"\n🚀 启动全生命周期 (LCA) GSA 数据收集引擎 ({n_simulations} 次模拟)...")
    rng = np.random.RandomState(seed)
    
    pmm_dfs = []
    for file in pmm_files:
        df = pd.read_csv(file)
        df.columns = df.columns.str.lower().str.strip()
        df.rename(columns={
            'length(m)': 'Length(m)', 
            'tonnage(t)': 'Tonnage(t)', 
            'enginepower(kw)': 'Enginepower(kw)', 
            'builtdate': 'Builtdate',
            'vesseltype': 'VesselType', 
            'flag': 'Flag'
        }, inplace=True)
        
        df['Length(m)'].fillna(df['Length(m)'].mean(), inplace=True)
        df['Tonnage(t)'].fillna(df['Tonnage(t)'].mean(), inplace=True)
        df['Enginepower(kw)'].fillna(df['Enginepower(kw)'].mean(), inplace=True)

        df['VesselType'] = df['VesselType'].astype(str).str.upper().str.strip()
        df['Flag'] = df['Flag'].astype(str).str.strip()
        df['LengthCategory'] = np.where(df['Length(m)'] < 12, '< 12m', '>= 12m')
        df['Builtdate'] = pd.to_numeric(df['Builtdate'], errors='coerce')
        
        mask_remove = ((df['LengthCategory'] == '< 12m') & (df['Builtdate'] < 1960)) | (df['Builtdate'] <= 1900)
        df = df[~mask_remove].copy()
        pmm_dfs.append(df)
            
    base_df = pmm_dfs[0]
    valid_data = base_df.dropna(subset=['Builtdate'])
    pool_dict = {}
    for _, row in base_df[['VesselType', 'LengthCategory', 'Flag']].drop_duplicates().iterrows():
        t, l, f = row['VesselType'], row['LengthCategory'], row['Flag']
        pool = valid_data[(valid_data['VesselType'] == t) & (valid_data['LengthCategory'] == l) & (valid_data['Flag'] == f)]['Builtdate'].values
        if len(pool) < min_n: pool = valid_data[(valid_data['VesselType'] == t) & (valid_data['LengthCategory'] == l)]['Builtdate'].values
        if len(pool) < min_n: pool = valid_data[valid_data['VesselType'] == t]['Builtdate'].values
        pool_dict[(t, l, f)] = pool if len(pool) > 0 else valid_data['Builtdate'].values

    missing_idx = np.where(base_df['Builtdate'].isna())[0]
    missing_types = base_df.iloc[missing_idx]['VesselType'].values
    missing_lens = base_df.iloc[missing_idx]['LengthCategory'].values
    missing_flags = base_df.iloc[missing_idx]['Flag'].values

    gsa_features, gsa_targets = [], []
    num_pmm = len(pmm_dfs)
    start_time = time.time()

    for i in range(n_simulations):
        pmm_idx = rng.randint(0, num_pmm)
        current_df = pmm_dfs[pmm_idx]
        
        power = np.maximum(current_df['Enginepower(kw)'].values, 0)
        length = current_df['Length(m)'].values
        tonnage = current_df['Tonnage(t)'].values
        v_type = current_df['VesselType'].values
        size_cat = current_df['LengthCategory'].values
        
        mean_fleet_power = np.mean(power)

        t_mult = rng.triangular(0.85, 1.0, 1.15)       
        sfr_mult = rng.triangular(0.85, 1.0, 1.15)     
        ef_fuel_mult = rng.triangular(0.95, 1.0, 1.05) 
        
        gear_wear_mult = rng.triangular(0.80, 1.0, 1.20) 
        ef_gear_mult = rng.triangular(0.90, 1.0, 1.10)   
        
        bait_use_mult = rng.triangular(0.80, 1.0, 1.20)  
        ef_bait_mult = rng.triangular(0.90, 1.0, 1.10)   
        
        ef_build_mult = rng.triangular(0.90, 1.0, 1.10)  

        current_builtdate = current_df['Builtdate'].values.copy()
        sampled_years = [rng.choice(pool_dict[(mt, ml, mf)]) for mt, ml, mf in zip(missing_types, missing_lens, missing_flags)]
        current_builtdate[missing_idx] = sampled_years
        avg_imputed_year = np.mean(sampled_years)

        active_mask = current_builtdate <= target_year
        built_mask = current_builtdate == target_year
        fc_array = np.array([get_fc_val(y) for y in current_builtdate])
        
        T_val = np.array([T_map_base.get(t, 0) for t in v_type]) * t_mult
        H_val = np.array([H_map.get(t, 0) for t in v_type])
        SFR_val = np.array([SFR_map_base.get(s, 0) for s in size_cat]) * sfr_mult
        EF_fuel_val = np.array([EF_fuel_base.get(s, 0) for s in size_cat]) * ef_fuel_mult
        Current_Fuel = power * T_val * SFR_val * H_val * EF_fuel_val * fc_array
        
        gear_int = np.zeros(len(current_df))
        gear_int[(v_type == 'PS') & (size_cat == '< 12m')] = (17.9+9.12)/(2*1000)
        gear_int[(v_type == 'PS') & (size_cat == '>= 12m')] = (251+54)/(2*1000)
        gear_int[v_type == 'LL'] = (0.49+0.12)/(2*0.0036*1000)
        GearBase = length * gear_int * gear_wear_mult * (EF_gear_base * ef_gear_mult)
        
        BaitBase = np.where(v_type == 'LL', (length / 0.0036) * 0.1 * bait_use_mult * (EF_bait_base * ef_bait_mult) * 0.01, 0)
        
        BuildBase = tonnage * (EF_build_base * ef_build_mult)
        
        Total_LCA_GHG = np.nansum(Current_Fuel * active_mask) + \
                        np.nansum(GearBase * active_mask) + \
                        np.nansum(BaitBase * active_mask) + \
                        np.nansum(BuildBase * built_mask)

        gsa_features.append({
            'PMM_Mean_Power': mean_fleet_power,
            'Activity_Days_Mult': t_mult,
            'SFR_Mult': sfr_mult,
            'EF_Fuel_Mult': ef_fuel_mult,
            'Gear_Wear_Mult': gear_wear_mult,
            'EF_Gear_Mult': ef_gear_mult,
            'Bait_Usage_Mult': bait_use_mult,
            'EF_Bait_Mult': ef_bait_mult,
            'EF_Build_Mult': ef_build_mult,
            'Imputed_Age_Shift': avg_imputed_year
        })
        gsa_targets.append(Total_LCA_GHG) 
        
        if (i + 1) % 500 == 0:
            print(f"   已完成 {i+1} / {n_simulations} 次... 耗时: {time.time()-start_time:.1f}s")

    return pd.DataFrame(gsa_features), pd.Series(gsa_targets, name='Total_LCA_GHG')


# ==========================================
# 3. 随机森林与 SHAP 解释引擎 (标题精细分离与对齐版)
# ==========================================
def run_rf_shap_analysis(X, y, rf_params):
    print("\n🌲 正在清理数据并训练随机森林代理模型...")
    
    valid_mask = ~y.isna()
    X_clean = X[valid_mask]
    y_clean = y[valid_mask]
    dropped = len(y) - len(y_clean)
    if dropped > 0:
        print(f"⚠️ 警告: 已剔除 {dropped} 条包含 NaN 的异常模拟数据。")

    X_train, X_test, y_train, y_test = train_test_split(X_clean, y_clean, test_size=0.2, random_state=42)
    
    rf = RandomForestRegressor(**rf_params)
    rf.fit(X_train, y_train)
    
    y_pred = rf.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = mean_absolute_error(y_test, y_pred)
    mape = mean_absolute_percentage_error(y_test, y_pred) * 100 
    
    print("\n📊 === 随机森林代理模型评价指标 (Test Set) ===")
    print(f"✅ R² (决定系数)        : {r2:.4f}")
    print(f"🎯 RMSE (均方根误差)    : {rmse/1e6:.4f} Mt")
    print(f"🎯 MAE (平均绝对误差)   : {mae/1e6:.4f} Mt")
    print(f"📉 MAPE (平均百分比误差): {mape:.3f}%")
    print("================================================\n")
    
    metrics_df = pd.DataFrame({
        'Metric': ['R-squared (R2)', 'RMSE (Million tonnes)', 'MAE (Million tonnes)', 'MAPE (%)'],
        'Value': [r2, rmse/1e6, mae/1e6, mape]
    })
    metrics_df.to_csv('RF_Surrogate_Model_Metrics.csv', index=False)
    
    print("🧠 正在计算 SHAP 值并进行顶刊级排版渲染...")
    explainer = shap.TreeExplainer(rf)
    shap_values = explainer.shap_values(X_clean)
    
    shap_values_scaled = shap_values / 1e6 
    
    feature_names = {
        'PMM_Mean_Power': 'Imputed Fleet Power (PMM)',
        'Activity_Days_Mult': 'Activity Days (Effort)',
        'SFR_Mult': 'Specific Fuel Consumption',
        'EF_Fuel_Mult': 'Fuel Emission Factor',
        'Gear_Wear_Mult': 'Gear Wear & Replacement Rate',
        'EF_Gear_Mult': 'Gear Material Carbon Footprint',
        'Bait_Usage_Mult': 'Bait Usage Intensity (LL only)',
        'EF_Bait_Mult': 'Bait Supply Chain Emission',
        'EF_Build_Mult': 'Shipbuilding Emission Factor',
        'Imputed_Age_Shift': 'Imputed Vessel Vintage'
    }
    X_renamed = X_clean.rename(columns=feature_names)
    
    plt.rcParams.update({
        'font.size': 14,             
        'ytick.labelsize': 12,       
        'axes.titlepad': 20,         
        'font.family': 'sans-serif'
    })
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 14))
    
    # ==========================================
    # --- 绘制图 (a) ---
    # ==========================================
    plt.sca(ax1) 
    shap.summary_plot(shap_values_scaled, X_renamed, plot_type="bar", show=False, color="#2c7fb8", plot_size=None)
    
    # 🚨 关键分离：(a) 靠左并保留偏移，主标题居中对齐
    ax1.set_title("(a)", fontsize=20, fontweight='bold', loc='left', x=-0.25)
    ax1.set_title("Global Sensitivity Analysis: Feature Importance", fontsize=18, fontweight='bold', loc='center')
    ax1.set_xlabel("mean(|SHAP value|) (Impact on Total GHG in Million tonnes)", fontsize=14)
    
    # ==========================================
    # --- 绘制图 (b) ---
    # ==========================================
    plt.sca(ax2) 
    shap.summary_plot(shap_values_scaled, X_renamed, show=False, cmap='Spectral_r', plot_size=None)
    
    # 🚨 关键分离：(b) 靠左并保留偏移，主标题居中对齐
    ax2.set_title("(b)", fontsize=20, fontweight='bold', loc='left', x=-0.25)
    ax2.set_title("Global Sensitivity Analysis: Beeswarm Plot", fontsize=18, fontweight='bold', loc='center')
    ax2.set_xlabel("SHAP value (Impact on Total GHG in Million tonnes)", fontsize=14)
    
    # 先应用自动排版以分配基本间距
    plt.tight_layout(pad=4.0)
    
    # 终极对齐术：提取 Bbox，强制统一左边缘和宽度
    fig.canvas.draw()
    pos1 = ax1.get_position()
    pos2 = ax2.get_position()
    
    align_left = max(pos1.x0, pos2.x0)
    align_right = min(pos1.x1, pos2.x1)
    new_width = align_right - align_left
    
    ax1.set_position([align_left, pos1.y0, new_width, pos1.height])
    ax2.set_position([align_left, pos2.y0, new_width, pos2.height])
    
    plt.savefig('Final_Combined_SHAP_Plot.png', dpi=600, bbox_inches='tight', transparent=False, facecolor='white')
    plt.savefig('Final_Combined_SHAP_Plot.svg', format='svg', bbox_inches='tight', transparent=False, facecolor='white')
    plt.close()
    
    print("📁 终极全生命周期 SHAP 拼图及指标报告已成功导出（标题完美分离对齐版）！")


# ==========================================
# 主执行入口
# ==========================================
if __name__ == "__main__":
    pmm_file_list = [
        "Imputed_Vessels_PMM_1.csv",
        "Imputed_Vessels_PMM_2.csv",
        "Imputed_Vessels_PMM_3.csv",
        "Imputed_Vessels_PMM_4.csv",
        "Imputed_Vessels_PMM_5.csv"
    ]
    
    X_features, y_target = generate_gsa_dataset(
        pmm_file_list, 
        n_simulations=GSA_CONFIG['n_simulations'], 
        target_year=GSA_CONFIG['target_year'], 
        seed=GSA_CONFIG['seed']
    )
    
    run_rf_shap_analysis(X_features, y_target, RF_PARAMS)