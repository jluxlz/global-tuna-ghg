#!/usr/bin/env python
# -*- coding: utf-8 -*-
'\n================================================================================\nmain_v3.py \u2014 \u5168\u751f\u547d\u5468\u671f LCA GHG \u6392\u653e\u6a21\u578b\uff08\u57fa\u4e8e Prior_Matrix \u53c2\u6570\u5316\uff09\n================================================================================\n\n\u5c06 Unified_Vessel_Registry.csv (GT) \u8f6c\u6362\u4e3a\u5b8c\u6574\u7684\u5168\u751f\u547d\u5468\u671f\u6e29\u5ba4\u6c14\u4f53\u6392\u653e\u4f30\u7b97\uff1a\n  1. GT\u2192LSW \u8f6c\u6362 (Prior_Matrix Section K)\n  2. \u63d2\u503c\u7ba1\u9053: \u5747\u503c(Length) \u2192 PMM(Tonnage, Enginepower) \u2192 \u5206\u5c42\u70ed\u5361(Builtdate)\n  3. \u53cc\u673a\u53cc\u76f8\u71c3\u6cb9\u6a21\u578b: \u4e3b\u673a(move/work) + \u8f85\u673a(\u6052\u5b9a) \u2192 CO2/CH4/N2O \u5206\u8f68\n  4. \u8239\u4f53\u5efa\u9020+\u7ef4\u62a4 (Section E)\n  5. \u7f51\u5177\u5efa\u9020+\u7ef4\u62a4 (Section F)\n  6. \u9975\u6599\u6392\u653e (Section G, \u4ec5LL)\n  7. \u5236\u51b7\u5242\u6cc4\u6f0f (Section H)\n  8. \u8499\u7279\u5361\u6d1b\u4e0d\u786e\u5b9a\u6027\u91cf\u5316 (GSA + RF + SHAP, per-process Top-2 \u5e76\u96c6)\n  9. \u7f51\u683c\u5206\u914d (\u6cbf\u7528\u73b0\u6709 Effort \u6807\u51c6\u5316\u903b\u8f91)\n\n\u6240\u6709\u53c2\u6570\u6765\u81ea model_parameters/Prior_Matrix.csv\uff0c\u5728\u4ee3\u7801\u4e2d\u6807\u6ce8\u4e86 Param_Code \u548c Sheet Row\u3002\n\n\u7528\u6cd5:\n  cd GHG_Calculation && python main_v3.py\n\n\u8f93\u51fa:\n  Base_1_LCA_Global_Process.csv    \u2014 \u5168\u7403\u8fc7\u7a0b\u6392\u653e\u65f6\u95f4\u5e8f\u5217\n  Base_2_Fleet_GHG.csv             \u2014 \u8239\u961f (Flag\xd7Gear\xd7Year)\n  Base_3_Spatial_Grid_Enriched.csv \u2014 \u7a7a\u95f4\u7f51\u683c\u5bcc\u96c6\u6570\u636e\n  Base_4_Organization_GHG.csv      \u2014 RFMO \u7ec4\u7ec7\u5c42\u9762\uff08\u9996\u4f4d\u6388\u6743\uff09\n  Base_5_Org_Fleet_GHG.csv         \u2014 RFMO \xd7 \u6e14\u5177\u90e8\u95e8\uff08\u591a\u7ec4\u7ec7\u7b49\u5206\u6743\u91cd\uff09\n  GSA_*.csv / GSA_SHAP_*.png       \u2014 \u654f\u611f\u6027\u5206\u6790\u7ed3\u679c\n================================================================================\n'

import os
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ============================================================

# ============================================================

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
import shap
import time


from power_discount_factor import (
    query_power_discount_vectorized,
    init_power_discount_lookup,
)
from operational_hours_lookup import (
    query_alpha_work_vectorized,
    init_time_profile_lookup,
    route_vessel_to_sector,
)
from ghost_fleet import build_ghost_vessels
from fuel_operation import draw_operating_days, operation_classes

# ============================================================

# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

PRIOR_MATRIX_PATH = os.path.join(ROOT_DIR, "model_parameters", "Prior_Matrix.csv")
VESSEL_REGISTRY_PATH = os.path.join(ROOT_DIR, "vessel_data_extract", "Unified_Vessel_Registry.csv")
PNAS_POWER_PATH = os.path.join(SCRIPT_DIR, "TotalEffortby_FishingCountry_LengthBoat_Gear_Sector.csv")
CATCH_ALLOCATION_PATH = os.path.join(ROOT_DIR, "effort_data", "Grid_Catch_Allocation.csv")
PMM_OUTPUT_PATH = os.path.join(ROOT_DIR, "PMM_Imputation", "After_PMM_Vessels.csv")
SHARE5_LOOKUP_PATH = os.path.join(ROOT_DIR, "effort_data", "Share5_Lookup_FlagGearYear.csv")

OUTPUT_DIR = SCRIPT_DIR  

# ============================================================

# ============================================================

def load_prior_matrix(path=PRIOR_MATRIX_PATH):
    '\n    \u52a0\u8f7d Prior_Matrix.csv \u5e76\u6784\u5efa\u7ed3\u6784\u5316\u67e5\u627e\u8868\u3002\n\n    \u8fd4\u56de dict:\n      params: DataFrame (\u539f\u59cb\u5168\u90e8\u53c2\u6570)\n      lookup: dict of dict \u2014 \u6309 Param_Section \u7ec4\u7ec7\n      by_code: dict \u2014 \u6309 Param_Code \u5feb\u901f\u67e5\u627e\n    '
    print(f"[Prior_Matrix] \u52a0\u8f7d\u53c2\u6570\u8868: {path}")
    pm = pd.read_csv(path, encoding="utf-8-sig")

    
    for col in ["Value_Best", "Value_Low", "Value_High"]:
        if col in pm.columns:
            pm[col] = pd.to_numeric(pm[col], errors="coerce")

    for col in ["Flag", "Gear", "Sector", "Length_Category"]:
        if col in pm.columns:
            pm[col] = pm[col].astype(str).str.strip().str.upper()

    
    by_code = {}
    for _, row in pm.iterrows():
        code = str(row.get("Param_Code", "")).strip()
        if code and code != "NAN":
            if code not in by_code:
                by_code[code] = []
            by_code[code].append(row.to_dict())

    
    lookup = {}
    for section in pm["Param_Section"].dropna().unique():
        lookup[section] = pm[pm["Param_Section"] == section]

    print(f"  \u52a0\u8f7d\u5b8c\u6210: {len(pm)} \u6761\u53c2\u6570, {len(by_code)} \u4e2a\u552f\u4e00 Param_Code, "
          f"{len(lookup)} \u4e2a Section ({sorted(lookup.keys())})")
    return {"params": pm, "lookup": lookup, "by_code": by_code}


def get_best(pm_dict, code, default=None):
    '\u4ece by_code \u83b7\u53d6\u53c2\u6570\u7684\u6700\u4f73\u4f30\u8ba1\u503c (Value_Best)\u3002\u5927\u5c0f\u5199\u4e0d\u654f\u611f\u3002'
    
    entries = pm_dict["by_code"].get(code, [])
    if not entries:
        
        code_upper = code.upper()
        for key, val in pm_dict["by_code"].items():
            if key.upper() == code_upper:
                entries = val
                break
    if entries:
        val = entries[0].get("Value_Best")
        if pd.notna(val):
            return float(val)
    return default


def get_distribution(row):
    '\u4ece Prior_Matrix \u884c\u63d0\u53d6\u5206\u5e03\u53c2\u6570 (best, low, high, dist_type)\u3002'
    best = row.get("Value_Best")
    low = row.get("Value_Low")
    high = row.get("Value_High")
    dist = str(row.get("Distribution", "Discrete")).strip()
    if pd.isna(best):
        return None
    return {
        "best": float(best),
        "low": float(low) if pd.notna(low) else float(best) * 0.9,
        "high": float(high) if pd.notna(high) else float(best) * 1.1,
        "dist": dist,
    }


def sample_from_distribution(dist_info, rng=None):
    '\u4ece\u5206\u5e03\u4e2d\u91c7\u6837\u4e00\u4e2a\u503c\u3002'
    if rng is None:
        rng = np.random
    if dist_info is None:
        return None
    best, low, high = dist_info["best"], dist_info["low"], dist_info["high"]
    dist = dist_info["dist"]

    try:
        if dist in ("Triangular", "triangular"):
            return rng.triangular(low, best, high)
        elif dist in ("Lognormal", "lognormal"):
            # low/high as 95% CI → mu=ln(best), sigma=(ln(high)-ln(low))/3.92
            mu = np.log(max(best, 1e-10))
            sigma = (np.log(max(high, 1e-10)) - np.log(max(low, 1e-10))) / 3.92
            return rng.lognormal(mu, max(sigma, 0.001))
        elif dist in ("Normal", "normal"):
            sigma = (high - low) / 3.92  # 95% CI → sigma
            return rng.normal(best, max(sigma, 0.001))
        elif dist in ("Uniform", "uniform"):
            return rng.uniform(low, high)
        else:  # Discrete / fixed
            return best
    except (ValueError, OverflowError):
        return best


# ============================================================

# ============================================================

def convert_gt_to_lsw(df, pm_dict):
    '\n    GT \u2192 LSW \u8f6c\u6362 (Prior_Matrix Section K, Row 89-90).\n\n    \u8239\u578b\u5dee\u5f02 (MEPC/IMO vessel statistics):\n      - \u6e14\u8239 (LL/PS):   LDT/GT = 0.859  (Row 90: LDT_GT_RATIO_FISHING)\n      - \u8d27\u8239/\u8f6c\u8fd0\u8239 (TP/TS): LDT/GT = 0.287 (Row 89: LDT_GT_RATIO_CARGO_REF, Triangular 0.22-0.55)\n      - \u8f85\u52a9\u8239 (SA):    \u540c\u6e14\u8239 0.859\n\n    TS/TP \u5728\u7ed3\u6784\u4e0a\u66f4\u63a5\u8fd1\u8d27\u8239 (\u5927\u8d27\u8231\u3001\u4f4e\u7ed3\u6784\u91cd\u91cf\u6bd4)\uff0c\u4e0d\u80fd\u5957\u7528\u6e14\u8239\u7cfb\u6570\u3002\n    '
    ldt_fishing = get_best(pm_dict, "LDT_GT_RATIO_FISHING", 0.859)    # Row 90
    ldt_cargo = get_best(pm_dict, "LDT_GT_RATIO_CARGO_REF", 0.287)     # Row 89

    df["LSW"] = np.where(
        df["VesselType"].isin(["TP", "TP"]),
        df["Tonnage"] * ldt_cargo,
        df["Tonnage"] * ldt_fishing
    )

    n_cargo = df["VesselType"].isin(["TP", "TP"]).sum()
    n_fishing = (~df["VesselType"].isin(["TP", "TP"])).sum()
    print(f"\n[GT→LSW] Fishing LDT/GT = {ldt_fishing:.3f} (n={n_fishing}), "
          f"Cargo LDT/GT = {ldt_cargo:.3f} (n={n_cargo})")
    print(f"  Prior_Matrix K, Row 90: LDT_GT_RATIO_FISHING (LL/PS/SA)")
    print(f"  Prior_Matrix K, Row 89: LDT_GT_RATIO_CARGO_REF (TS/TP)")
    return df


# ============================================================

# ============================================================

class OLS:
    """Simple OLS regression via numpy.linalg.lstsq"""
    def __init__(self, fit_intercept=True):
        self.fit_intercept = fit_intercept
        self.beta = None
        self.intercept_ = 0.0

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if self.fit_intercept:
            X = np.column_stack([np.ones(len(X)), X])
        self.beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        if self.fit_intercept:
            self.intercept_ = self.beta[0]
            self.beta = self.beta[1:]
        return self

    def predict(self, X):
        X = np.asarray(X, dtype=float)
        if self.fit_intercept:
            return self.intercept_ + X @ self.beta
        return X @ self.beta


def pmm_impute(df, target_col, predictor_cols, n_donors=5, log_target=True,
               extra_mask=None, rng=None):
    '\n    Predictive Mean Matching \u63d2\u503c\u3002\n    \u4fdd\u6301\u5206\u5e03\u5f62\u6001\u548c\u65b9\u5dee\uff0c\u907f\u514d\u56de\u5f52\u5747\u503c\u95ee\u9898\u3002\n    '
    if rng is None:
        rng = np.random.default_rng(42)
    df = df.copy()

    is_nan = df[target_col].isna()
    is_zero = (df[target_col].fillna(1) == 0)
    is_extra = extra_mask if extra_mask is not None else pd.Series(False, index=df.index)
    is_missing = is_nan | is_zero | is_extra

    n_missing = is_missing.sum()
    if n_missing == 0:
        return df, {"target": target_col, "n_missing": 0, "n_imputed": 0}

    mask_obs = ~is_missing.values
    mask_mis = is_missing.values

    
    feature_df = pd.DataFrame(index=df.index)
    for col in predictor_cols:
        if col == "VesselType":
            dummies = pd.get_dummies(df["VesselType"].fillna("LL"), prefix="vt")
            for dc in dummies.columns:
                feature_df[dc] = dummies[dc].astype(float)
        elif col.startswith("log_"):
            src_col = col[4:]
            feature_df[col] = np.log(df[src_col].replace(0, np.nan).fillna(1))
        else:
            feature_df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(float)

    feature_cols = list(feature_df.columns)
    X_all = feature_df.values
    y_raw = pd.to_numeric(df[target_col], errors="coerce").copy()
    y_raw[is_zero] = np.nan

    X_obs = X_all[mask_obs]
    X_mis = X_all[mask_mis]
    y_obs = y_raw[mask_obs].values.copy()

    if mask_obs.sum() < 10:
        median_val = np.nanmedian(y_obs)
        df.loc[mask_mis, target_col] = median_val
        return df, {"target": target_col, "n_missing": int(n_missing),
                    "n_imputed": int(mask_mis.sum()), "fallback": "median"}

    if log_target:
        min_pos = y_obs[y_obs > 0].min() if (y_obs > 0).any() else 0.1
        y_obs_fit = np.log(np.maximum(y_obs, min_pos))
    else:
        y_obs_fit = y_obs

    model = OLS(fit_intercept=True)
    model.fit(X_obs, y_obs_fit)
    y_pred_obs = model.predict(X_obs)
    y_pred_mis = model.predict(X_mis)

    # Store ALL n_donors for downstream MC uncertainty
    imputed_values = np.empty(len(y_pred_mis))
    donor_columns = {}
    for j in range(n_donors):
        donor_columns[f"{target_col}_D{j+1}"] = np.empty(len(y_pred_mis))

    for i in range(len(y_pred_mis)):
        dists = np.abs(y_pred_obs - y_pred_mis[i])
        donor_indices = np.argpartition(dists, min(n_donors, len(dists) - 1))[:n_donors]
        donor_vals = y_obs[donor_indices]
        for j in range(n_donors):
            donor_columns[f"{target_col}_D{j+1}"][i] = donor_vals[j]
        # Default: mean of donors (deterministic, uses full information)
        imputed_values[i] = float(np.mean(donor_vals))

    df.loc[mask_mis, target_col] = imputed_values
    for col_name, col_vals in donor_columns.items():
        df.loc[mask_mis, col_name] = col_vals

    print(f"  [{target_col}] PMM: {mask_mis.sum()} imputed "
          f"(orig mean={y_obs.mean():.1f}, imp mean={imputed_values.mean():.1f})")
    return df, {"target": target_col, "n_missing": int(n_missing),
                "n_imputed": int(mask_mis.sum())}


def run_imputation_pipeline(vessel_path=VESSEL_REGISTRY_PATH,
                            pm_dict=None, random_seed=42, write_output=True):
    '\n    \u5b8c\u6574\u63d2\u503c\u7ba1\u9053:\n      3a. Length \u2192 VesselType \u5206\u7ec4\u5747\u503c\n      3b. Tonnage \u2192 PMM\n      3c. Enginepower \u2192 PMM\n      3d. Builtdate \u2192 \u5206\u5c42\u70ed\u5361 (\u6784\u5efa\u4f9b\u4f53\u6c60)\n    '
    rng = np.random.default_rng(random_seed)
    print("\n" + "=" * 60)
    print("  IMPUTATION PIPELINE")
    print("=" * 60)

    print(f"\n[Load] {vessel_path}")
    df = pd.read_csv(vessel_path, encoding="utf-8-sig")
    n_total = len(df)
    print(f"  {n_total} vessels loaded.")

    
    df.columns = df.columns.str.strip()
    rename_map = {}
    has_flag = "Flag" in df.columns or "flag" in df.columns
    for col in df.columns:
        cl = col.lower().strip()
        if cl in ("length", "length(m)"):
            rename_map[col] = "Length"
        elif cl in ("tonnage", "tonnage(t)"):
            rename_map[col] = "Tonnage"
        elif cl in ("enginepower", "enginepower(kw)"):
            rename_map[col] = "Enginepower"
        elif cl in ("builtdate",):
            rename_map[col] = "Builtdate"
        elif cl in ("vesseltype",):
            rename_map[col] = "VesselType"
        elif cl == "flagcode" and not has_flag:
            rename_map[col] = "Flag"
        elif cl == "flag":
            rename_map[col] = "Flag"  # normalize case
    if rename_map:
        df.rename(columns=rename_map, inplace=True)
    
    for col in df.columns:
        if col.lower() == "flagcode" and "Flag" in df.columns:
            df.drop(columns=[col], inplace=True)

    
    for col in ["Length", "Tonnage", "Enginepower", "Builtdate"]:
        if col not in df.columns:
            raise KeyError(f"Missing required column: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "VesselType" not in df.columns:
        raise KeyError("Missing required column: VesselType")
    df["VesselType"] = df["VesselType"].astype(str).str.upper().str.strip()
    # TS → TP
    df["VesselType"] = df["VesselType"].replace({"TS": "TP"})

    if "Flag" not in df.columns:
        raise KeyError("Missing required column: Flag")
    df["Flag"] = df["Flag"].astype(str).str.strip()

    # Physical observations must be standardized before serving as PMM donors.
    # Existing complete PMM donor columns establish the unit of already-imputed values.
    for field, unit_col, valid_units, label in [
            ("Enginepower", "PowerType", {"KW"}, "kW"),
            ("Tonnage", "TonnageType", {"GT", "GRT"}, "GT")]:
        if unit_col not in df:
            continue
        donor_cols = [f"{field}_D{j}" for j in range(1, 6)]
        known_imputed = df[donor_cols].notna().all(axis=1) if all(c in df for c in donor_cols) else pd.Series(False,index=df.index)
        unresolved = df[field].gt(0) & ~df[unit_col].fillna("").str.upper().isin(valid_units) & ~known_imputed
        df.loc[unresolved, field] = np.nan
        df.loc[known_imputed, unit_col] = label
        if unresolved.any():
            print(f"  Unit QC: {field}: {unresolved.sum()} observations excluded from donor pool (unknown/nonstandard unit)")

    
    print("\n--- Before Imputation ---")
    for col in ["Length", "Tonnage", "Enginepower", "Builtdate"]:
        n_miss = df[col].isna().sum()
        n_zero = ((df[col].fillna(1) == 0) & df[col].notna()).sum()
        print(f"  {col}: {n_miss} NaN + {n_zero} zero = {n_miss + n_zero} "
              f"({(n_miss + n_zero) / n_total * 100:.1f}%)")

    
    print('\n--- 3a. Length (VesselType \u5747\u503c) ---')
    len_missing = df["Length"].isna() | (df["Length"] == 0)
    n_len = len_missing.sum()
    for vt in df["VesselType"].unique():
        mask_vt = (df["VesselType"] == vt)
        mask_mis = mask_vt & len_missing
        if mask_mis.sum() == 0:
            continue
        obs = df.loc[mask_vt & ~len_missing, "Length"]
        if len(obs) > 0:
            df.loc[mask_mis, "Length"] = obs.mean()  
    print(f"  Length: {n_len} imputed via VesselType mean")

    # ---- 3b. Tonnage PMM ----
    print("\n--- 3b. Tonnage (PMM) ---")
    ton_zero = (df["Tonnage"].fillna(1) == 0) & df["Tonnage"].notna()
    df, _ = pmm_impute(df, "Tonnage",
                       predictor_cols=["Length", "log_Length", "VesselType"],
                       n_donors=5, log_target=True, extra_mask=ton_zero, rng=rng)

    # ---- 3c. Enginepower PMM ----
    print("\n--- 3c. Enginepower (PMM) ---")
    pow_zero = (df["Enginepower"].fillna(1) == 0) & df["Enginepower"].notna()
    df, _ = pmm_impute(df, "Enginepower",
                       predictor_cols=["Length", "log_Tonnage", "VesselType"],
                       n_donors=5, log_target=True, extra_mask=pow_zero, rng=rng)

    
    print('\n--- 3d. Builtdate (\u5206\u5c42\u70ed\u5361\u4f9b\u4f53\u6c60) ---')
    df["LengthCategory"] = np.where(df["Length"] < 12, "< 12m", ">= 12m")

    
    mask_remove = ((df["LengthCategory"] == "< 12m") & (df["Builtdate"] < 1960)) | \
                  (df["Builtdate"] <= 1900)
    n_remove = mask_remove.sum()
    if n_remove > 0:
        print(f"  \u79fb\u9664 {n_remove} \u6761\u4e0d\u5408\u7406\u7684\u65e7\u8239\u8bb0\u5f55")
        df = df[~mask_remove].copy()

    
    valid = df.dropna(subset=["Builtdate"])
    min_n = 5

    def get_donor_pool(v_type, len_cat, flag):
        pool = valid[(valid["VesselType"] == v_type) &
                     (valid["LengthCategory"] == len_cat) &
                     (valid["Flag"] == flag)]["Builtdate"].values
        if len(pool) >= min_n:
            return pool, "L1 (VT+LC+Flag)"
        pool = valid[(valid["VesselType"] == v_type) &
                     (valid["LengthCategory"] == len_cat)]["Builtdate"].values
        if len(pool) >= min_n:
            return pool, "L2 (VT+LC)"
        pool = valid[valid["VesselType"] == v_type]["Builtdate"].values
        if len(pool) >= min_n:
            return pool, "L3 (VT only)"
        return valid["Builtdate"].values, "L4 (Global)"

    pool_dict = {}
    strata = df[["VesselType", "LengthCategory", "Flag"]].drop_duplicates()
    for _, row in strata.iterrows():
        vt, lc, fl = row["VesselType"], row["LengthCategory"], row["Flag"]
        if pd.isna(vt) or pd.isna(lc):
            continue
        pool, level = get_donor_pool(vt, lc, fl)
        pool_dict[(vt, lc, fl)] = pool

    n_pools = len(pool_dict)
    print(f"  \u4f9b\u4f53\u6c60: {n_pools} strata, {len(valid)} vessels with known Builtdate")

    
    print("\n--- After Imputation ---")
    for col in ["Length", "Tonnage", "Enginepower", "Builtdate"]:
        n_miss = df[col].isna().sum()
        n_zero = ((df[col].fillna(1) == 0) & df[col].notna()).sum()
        print(f"  {col}: {n_miss} NaN + {n_zero} zero = {n_miss + n_zero} "
              f"({(n_miss + n_zero) / len(df) * 100:.1f}%)")

    # Unit metadata follows the standardized PMM values as well as observed values.
    for field, unit_col, label in [("Length","LengthType","m"), ("Tonnage","TonnageType","GT"), ("Enginepower","PowerType","kW")]:
        if unit_col not in df:
            df[unit_col] = ""
        donors = [f"{field}_D{j}" for j in range(1,6)]
        imputed = df[donors].notna().all(axis=1) if all(c in df for c in donors) else pd.Series(False,index=df.index)
        # Length is deterministically imputed rather than PMM sampled.
        if field == "Length":
            imputed = df[unit_col].fillna("").eq("") & df[field].gt(0)
        df.loc[imputed, unit_col] = label

    
    df_out = df.copy()
    if write_output:
        df_out.to_csv(PMM_OUTPUT_PATH, index=False, encoding="utf-8-sig")
        print(f"\n  \u5df2\u4fdd\u5b58: {PMM_OUTPUT_PATH}")

    return df, pool_dict


def impute_builtdate_deterministic(df, pool_dict):
    '\n    \u786e\u5b9a\u6027\u5730\u63d2\u8865\u7f3a\u5931\u7684\u5efa\u9020\u65e5\u671f (Builtdate)\u3002\n\n    \u7b56\u7565\uff08\u6309 Flag \xd7 VesselType \xd7 LengthCategory \u5206\u5c42\uff09:\n      1. \u53d6\u4f9b\u4f53\u6c60\u7684 \u4f17\u6570(mode)\n      2. \u82e5\u65e0\u4f17\u6570\uff08\u6240\u6709\u503c\u552f\u4e00\uff09\uff0c\u53d6 \u4e2d\u4f4d\u503c\n\n    \u63d2\u8865\u540e\u7684\u6570\u636e\u4e0d\u518d\u53c2\u4e0e MC \u91c7\u6837 \u2014 Builtdate \u5bf9\u603b GHG \u4e0d\u786e\u5b9a\u6027\u7684\n    \u8d21\u732e <0.02%\uff08vs SFCbase 12%\uff09\uff0c\u53ef\u5ffd\u7565\u3002\n\n    Returns: df with Builtdate filled (no NaN)\n    '
    from scipy import stats as sp_stats

    df = df.copy()
    missing_mask = df["Builtdate"].isna()
    n_missing = missing_mask.sum()

    if n_missing == 0:
        print("[Builtdate] All vessels have Builtdate — nothing to impute.")
        return df

    n_mode = 0
    n_median = 0
    for idx in df[missing_mask].index:
        vt = df.at[idx, "VesselType"]
        lc = df.at[idx, "LengthCategory"]
        fl = df.at[idx, "Flag"]
        key = (vt, lc, fl)
        pool = pool_dict.get(key)
        if pool is None or len(pool) == 0:
            pool = df["Builtdate"].dropna().values

        # Mode → Median fallback
        mode_result = sp_stats.mode(pool, keepdims=False)
        if hasattr(mode_result, 'mode'):
            # scipy >= 1.9: returns ModeResult namedtuple
            mode_val = mode_result.mode
            count = mode_result.count
        else:
            # scipy < 1.9: returns (mode_array, count_array)
            mode_val = mode_result[0]
            count = mode_result[1]

        if count > 1:
            df.at[idx, "Builtdate"] = float(mode_val)
            n_mode += 1
        else:
            df.at[idx, "Builtdate"] = float(np.median(pool))
            n_median += 1

    print(f"[Builtdate] Deterministic imputation: {n_missing} missing → "
          f"{n_mode} mode + {n_median} median")
    return df


# ============================================================

# ============================================================



# Asia, Africa, Europe, North America, South America, Australia & Oceania
FLAG_TO_REGION = {
    
    "CHN": "Asia", "JPN": "Asia", "KOR": "Asia", "TWN": "Asia",
    "PRK": "Asia", "MNG": "Asia", "HKG": "Asia", "MAC": "Asia",
    
    "IDN": "Asia", "MYS": "Asia", "PHL": "Asia", "THA": "Asia",
    "VNM": "Asia", "SGP": "Asia", "BRN": "Asia", "MMR": "Asia",
    "KHM": "Asia", "LAO": "Asia",
    
    "IND": "Asia", "LKA": "Asia", "BGD": "Asia", "PAK": "Asia",
    "MDV": "Asia", "NPL": "Asia", "BTN": "Asia",
    
    "IRN": "Asia", "IRQ": "Asia", "SAU": "Asia", "ARE": "Asia",
    "QAT": "Asia", "KWT": "Asia", "BHR": "Asia", "OMN": "Asia",
    "YEM": "Asia", "JOR": "Asia", "LBN": "Asia", "SYR": "Asia",
    "ISR": "Asia", "PSE": "Asia", "TUR": "Asia",
    
    "KAZ": "Asia", "UZB": "Asia", "TKM": "Asia", "KGZ": "Asia",
    "TJK": "Asia", "AZE": "Asia", "ARM": "Asia", "GEO": "Asia",
    
    "ZAF": "Africa", "MAR": "Africa", "DZA": "Africa", "TUN": "Africa",
    "LBY": "Africa", "EGY": "Africa", "SDN": "Africa", "SSD": "Africa",
    "ETH": "Africa", "KEN": "Africa", "TZA": "Africa", "UGA": "Africa",
    "SOM": "Africa", "DJI": "Africa", "ERI": "Africa",
    "NGA": "Africa", "GHA": "Africa", "CIV": "Africa", "SEN": "Africa",
    "CMR": "Africa", "COD": "Africa", "AGO": "Africa", "MOZ": "Africa",
    "ZWE": "Africa", "ZMB": "Africa", "MWI": "Africa", "TGO": "Africa",
    "BEN": "Africa", "BFA": "Africa", "MLI": "Africa", "NER": "Africa",
    "TCD": "Africa", "CAF": "Africa", "GAB": "Africa", "COG": "Africa",
    "GNB": "Africa", "GIN": "Africa", "LBR": "Africa", "SLE": "Africa",
    "MRT": "Africa", "NAM": "Africa", "BWA": "Africa", "LSO": "Africa",
    "SWZ": "Africa", "MDG": "Africa", "MUS": "Africa", "SYC": "Africa",
    "COM": "Africa", "STP": "Africa", "CPV": "Africa", "GNQ": "Africa",
    "BDI": "Africa", "RWA": "Africa", "GMB": "Africa",
    
    "GBR": "Europe", "FRA": "Europe", "DEU": "Europe", "ITA": "Europe",
    "ESP": "Europe", "NLD": "Europe", "BEL": "Europe", "LUX": "Europe",
    "IRL": "Europe", "PRT": "Europe", "GRC": "Europe", "CYP": "Europe",
    "MLT": "Europe", "AUT": "Europe", "CHE": "Europe",
    "DNK": "Europe", "SWE": "Europe", "NOR": "Europe", "FIN": "Europe",
    "ISL": "Europe", "FRO": "Europe",
    "POL": "Europe", "CZE": "Europe", "SVK": "Europe", "HUN": "Europe",
    "ROU": "Europe", "BGR": "Europe", "HRV": "Europe", "SVN": "Europe",
    "SRB": "Europe", "ALB": "Europe", "MNE": "Europe", "MKD": "Europe",
    "BIH": "Europe", "UKR": "Europe", "BLR": "Europe", "MDA": "Europe",
    "LTU": "Europe", "LVA": "Europe", "EST": "Europe",
    "RUS": "Europe",  
    
    "USA": "North America", "CAN": "North America", "MEX": "North America",
    "BMU": "North America", "GRL": "North America",
    
    "BRA": "South America", "ARG": "South America", "CHL": "South America",
    "PER": "South America", "ECU": "South America", "COL": "South America",
    "VEN": "South America", "GUY": "South America", "SUR": "South America",
    "PRY": "South America", "URY": "South America", "BOL": "South America",
    
    "PAN": "South America", "CRI": "South America", "NIC": "South America",
    "HND": "South America", "SLV": "South America", "GTM": "South America",
    "BLZ": "South America", "CUB": "South America", "DOM": "South America",
    "JAM": "South America", "HTI": "South America", "BHS": "South America",
    "BRB": "South America", "TTO": "South America", "ATG": "South America",
    "DMA": "South America", "GRD": "South America", "KNA": "South America",
    "LCA": "South America", "VCT": "South America",
    
    "AUS": "Australia & Oceania", "NZL": "Australia & Oceania",
    "FJI": "Australia & Oceania", "PNG": "Australia & Oceania",
    "SLB": "Australia & Oceania", "VUT": "Australia & Oceania",
    "WSM": "Australia & Oceania", "TON": "Australia & Oceania",
    "KIR": "Australia & Oceania", "FSM": "Australia & Oceania",
    "MHL": "Australia & Oceania", "PLW": "Australia & Oceania",
    "NRU": "Australia & Oceania", "TUV": "Australia & Oceania",
    "COK": "Australia & Oceania", "NCL": "Australia & Oceania",
    "PYF": "Australia & Oceania",
    
    "REU": "Africa", "MYT": "Africa", "ATF": "Africa",
    "BLM": "North America", "SPM": "North America", "CUW": "South America",
    "ABW": "South America",
    
    "BLZ": "South America",
    
    "CUW": "South America", "BES": "South America", "BLM": "North America",
    "SHN": "Africa", "IOT": "Asia", "HMD": "Australia & Oceania",
    "FLK": "South America", "GUF": "South America", "GLP": "North America",
    "MTQ": "North America", "REU": "Africa", "MYT": "Africa",
}


def get_flag_region(flag_iso3):
    'ISO3 \u2192 Prior_Matrix \u533a\u57df'
    if not flag_iso3 or pd.isna(flag_iso3):
        return None
    return FLAG_TO_REGION.get(str(flag_iso3).strip().upper(), None)


def get_ocean_for_ps(flag_iso3, authorized_oceans=""):
    '\n    \u4e3a PS \u8239\u786e\u5b9a\u4e3b\u8981\u6d77\u6d0b (\u7528\u4e8e Parker PS T_map)\u3002\n    \u4ece Authorized_Oceans \u5b57\u6bb5\u63d0\u53d6\u4e3b\u6d77\u6d0b\uff0c\u6216\u4ece Flag \u63a8\u65ad\u3002\n    \u8fd4\u56de: "Atlantic", "Indian", "Pacific", \u6216 None\n    '
    oceans_str = str(authorized_oceans).upper() if pd.notna(authorized_oceans) else ""

    # CCSBT
    # IATTC → Pacific, ICCAT → Atlantic, IOTC → Indian, WCPFC → Pacific

    
    atl = oceans_str.count("ICCAT")
    ind = oceans_str.count("IOTC")
    pac = oceans_str.count("WCPFC") + oceans_str.count("IATTC")
    # CCSBT
    sbt = oceans_str.count("CCSBT")

    if atl > 0 and atl >= ind and atl >= pac:
        return "Atlantic"
    if ind > 0 and ind >= atl and ind >= pac:
        return "Indian"
    if pac > 0 and pac >= atl and pac >= ind:
        return "Pacific"

    # CCSBT
    region = get_flag_region(flag_iso3)
    if region in ("Africa",):
        return "Atlantic"  
    if region in ("Asia",):
        return "Indian"    
    if region in ("Australia & Oceania",):
        return "Pacific"
    if region in ("North America", "South America"):
        return "Pacific"   

    return None  


def resolve_t_map(row, pm_dict):
    '\n    \u89e3\u6790\u5355\u8258\u8239\u7684 T_map (\u5e74\u51fa\u6d77\u5929\u6570)\u3002\n\n    Prior_Matrix Section B: T_map_DAS\n    \u6570\u636e\u4f18\u5148\u7ea7\u4f53\u7cfb:\n      PS, Builtdate >= 1990 (FAD \u65f6\u4ee3):\n        1. Parker \u5927\u6d0b\u7279\u5b9a\u503c (Atlantic/Indian/Pacific) \u2014 Tier 1\n        2. Flag Region \xd7 Gear \xd7 Sector \u2014 Tier 3 Anticamara\n        3. ALL \xd7 Gear \xd7 ALL \u2014 \u5168\u7403\u515c\u5e95\n      PS, Builtdate < 1990 (\u524d FAD \u65f6\u4ee3):\n        1. Flag Region \xd7 Gear \xd7 Sector \u2014 Tier 3 Anticamara\n        2. ALL \xd7 Gear \xd7 ALL \u2014 \u5168\u7403\u515c\u5e95\n      LL / TS / TP:\n        1. Flag Region \xd7 Gear \xd7 Sector \u2014 Tier 3 Anticamara\n        2. ALL \xd7 Gear \xd7 ALL \u2014 \u5168\u7403\u515c\u5e95\n      \u786c\u7f16\u7801\u5e38\u91cf\u515c\u5e95\n    '
    gear = row["VesselType"]
    sector = row["Sector"]
    region = row.get("GeoRegion", "ALL")
    builtdate = row.get("Builtdate", 1950)

    
    ocean = row.get("Ocean", None)

    
    entries = pm_dict["by_code"].get("T_map_DAS", [])

    def pick(flag_value, allow_parker=False):
        candidates = []
        for e in entries:
            ef = str(e.get("Flag", "ALL")).upper()
            eg = str(e.get("Gear", "ALL")).upper()
            es = str(e.get("Sector", "ALL")).upper()
            lc = str(e.get("LengthCategory", "ALL")).replace(" ", "")
            if ef != str(flag_value).upper() or eg not in (gear.upper(), "ALL") or es not in (sector.upper(), "ALL"):
                continue
            if lc not in ("ALL", str(row.get("LengthCategory", "ALL")).replace(" ", "")):
                continue
            label = str(e.get("Note", "")) + str(e.get("Param_Name", "")) + str(e.get("Reference", ""))
            if "Parker" in label and not allow_parker:
                continue
            # The existing China consultation is stored under Asia, but is explicitly country-specific.
            china = "China" in label
            if china and str(row.get("Flag", "")).upper() != "CHN":
                continue
            if pd.notna(e.get("Value_Best")):
                candidates.append(((int(china), int(eg == gear.upper()), int(es == sector.upper()),
                                    int(lc != "ALL")), e))
        if not candidates:
            return None
        rank = max(k for k, _ in candidates)
        values = {float(e["Value_Best"]) for k, e in candidates if k == rank}
        if len(values) != 1:
            raise ValueError(f"Ambiguous T_map_DAS for {flag_value}/{gear}/{sector}: {values}")
        return values.pop()

    if gear == "PS" and pd.notna(builtdate) and builtdate >= 1990 and ocean:
        value = pick(ocean, allow_parker=True)
        if value is not None:
            return value
    for flag_value in dict.fromkeys([row.get("Flag", "ALL"), region or "ALL", "ALL"]):
        value = pick(flag_value)
        if value is not None:
            return value
    return {"LL": 299.9, "PS": 211.0, "TP": 180.0}.get(gear, 200.0)


def resolve_lf(row, pm_dict, phase="move"):
    '\n    \u89e3\u6790\u8d1f\u8377\u56e0\u5b50 LF \u2014 v3.0 (Section C3 + R22 EMEP/EEA)\u3002\n\n    >=12m \u67f4\u6cb9/\u91cd\u6cb9:\n      LF_move = LF_MAIN_MOVE = 0.80 (Cruise, EMEP/EEA R22)\n      LF_work = LF_MAIN_WORK = 0.20 (Manoeuvring, EMEP/EEA R22)\n      LF_aux  = LF_AUX = Uniform(0.30, 0.50), Best=0.40\n    <12m \u6c7d\u6cb9:\n      LF_move = LF_MAIN_MOVE_GASOLINE = 0.80\n      LF_work = LF_MAIN_WORK_GASOLINE = 0.201 (EPA)\n      LF_aux  = 0.0 (\u65e0\u8f85\u673a)\n    '
    engine_type = get_engine_type(row, pm_dict)

    if engine_type == "GASOLINE":
        if phase == "move":
            return get_best(pm_dict, "LF_MAIN_MOVE_GASOLINE", 0.80)
        elif phase == "work":
            return get_best(pm_dict, "LF_MAIN_WORK_GASOLINE", 0.201)
        else:  # aux
            return 0.0  
    else:
        
        if phase == "move":
            return get_best(pm_dict, "LF_MAIN_MOVE", 0.80)
        elif phase == "work":
            return get_best(pm_dict, "LF_MAIN_WORK", 0.20)
        else:  # aux
            has_aux = get_best(pm_dict, "HAS_AUX_ENGINE", 1.0)
            if has_aux > 0:
                return get_best(pm_dict, "LF_AUX", 0.40)
            return 0.0


def resolve_hours(row, pm_dict, engine="main"):
    '\n    \u89e3\u6790\u65e5\u8fd0\u884c\u5c0f\u65f6 H\u3002\n\n    \u4e3b\u673a (main):  Sector=I \u2192 24h, APW \u2192 12h\n    \u8f85\u673a (aux):   Sector=I \u2192 24h, APW \u2192 12h\n    (2026-09-21: the former PS 4h/15h override was removed \u2014 erroneous;\n     PS is always routed to sector I and now follows the same rule.)\n    '
    sector = row["Sector"]
    return 24.0 if sector == "I" else 12.0


def get_engine_type(row, pm_dict):
    '\n    \u89e3\u6790\u53d1\u52a8\u673a\u7c7b\u578b\u3002\n\n    Prior_Matrix Section C0:\n      >=12m LL/PS/SA \u2192 MSD (\u4e2d\u901f\u56db\u51b2\u7a0b\u67f4\u6cb9\u673a)\n      TP \u2192 SSD (\u4f4e\u901f\u4e8c\u51b2\u7a0b\u67f4\u6cb9\u673a, \u91cd\u6cb9)\n      <12m APW \u2192 GASOLINE (\u6c7d\u6cb9\u8237\u5916\u673a)\n    '
    vt = str(row.get("VesselType", "")).upper()
    sector = str(row.get("Sector", "")).upper()
    length_m = row.get("Length", 12)

    if vt == "TP":
        return "SSD"
    if sector == "APW" and length_m < 12:
        return "GASOLINE"
    # LL/PS/SA, >=12m, I → MSD
    return "MSD"


def get_fuel_type(row, pm_dict):
    '\n    \u89e3\u6790\u71c3\u6599\u7c7b\u578b\u3002\n\n    Prior_Matrix Section C0:\n      >=12m LL/PS/SA \u2192 MDO (\u8239\u7528\u67f4\u6cb9)\n      TP \u2192 HFO (\u91cd\u8d28\u71c3\u6599\u6cb9)\n      <12m APW \u2192 GASOLINE (\u6c7d\u6cb9)\n    '
    vt = str(row.get("VesselType", "")).upper()
    engine_type = get_engine_type(row, pm_dict)

    if engine_type == "GASOLINE":
        return "GASOLINE"
    if vt == "TP":
        return "HFO"
    return "MDO"  # LL/PS/SA, >=12m


def get_sfcbase(engine_type, fuel_type, built_year, pm_dict):
    '\n    \u6309 IMO \u5e74\u4ee3\u5206\u6bb5\u67e5\u8be2 SFCbase (g/kWh)\u3002\n\n    Prior_Matrix Section C1:\n      SFC_BASE_{Engine}_{Fuel}_{Era}\n      Era: PRE1983 (Builtdate <= 1983)\n           1984_2000 (1984 <= Builtdate <= 2000)\n           2001PLUS (Builtdate >= 2001)\n    '
    if engine_type == "GASOLINE":
        return None  

    if pd.isna(built_year) or built_year <= 0:
        built_year = 2005  

    if built_year <= 1983:
        era = "PRE1983"
    elif built_year <= 2000:
        era = "1984_2000"
    else:
        era = "2001PLUS"

    code = f"SFC_BASE_{engine_type}_{fuel_type}_{era}"
    val = get_best(pm_dict, code)

    if val is None or pd.isna(val):
        # Fallback: MSD/MDO/2001PLUS = 175 g/kWh
        code_fb = "SFC_BASE_MSD_MDO_2001PLUS"
        val = get_best(pm_dict, code_fb, 175.0)

    return float(val)


def apply_sfoc_formula(sfcbase, lf, pm_dict):
    '\n    \u5e94\u7528 SFOC \u8d1f\u8377\u4fee\u6b63\u516c\u5f0f (Jalkanen et al. 2012):\n      SFC_actual = SFCbase \xd7 (A\xd7L\xb2 + B\xd7L + C)\n\n    Prior_Matrix Section C2:\n      A = 0.455, B = -0.71, C = 1.28\n    \u4ec5\u9002\u7528\u4e8e >=12m \u67f4\u6cb9\u673a; \u6c7d\u6cb9\u4e0d\u4f7f\u7528\u6b64\u516c\u5f0f\u3002\n\n    \u8fd4\u56de: SFC_actual (g/kWh)\n    '
    A = get_best(pm_dict, "SFOC_LOAD_COEFF_A", 0.455)
    B = get_best(pm_dict, "SFOC_LOAD_COEFF_B", -0.71)
    C = get_best(pm_dict, "SFOC_LOAD_COEFF_C", 1.28)
    factor = A * lf * lf + B * lf + C
    return sfcbase * factor
def resolve_sfr(row, pm_dict, engine="main", phase="move"):
    """
    Resolve SFR (Specific Fuel Consumption Rate) - v3.0 SFOC methodology.

    >=12m diesel/HFO: SFCbase lookup -> SFOC load correction -> actual SFC
    <12m gasoline: EPA direct SFR (no SFOC formula)
    """
    engine_type = get_engine_type(row, pm_dict)

    if engine_type == "GASOLINE":
        # <12m APW gasoline: direct EPA SFR, no phase split, no aux
        if engine == "aux":
            return 0.0
        return get_best(pm_dict, "SFR_GASOLINE_4STROKE", 0.000319)

    # >=12m diesel/HFO: SFCbase + SFOC formula
    fuel_type = get_fuel_type(row, pm_dict)
    built_year = row.get("Builtdate", 2000)
    sfcbase = get_sfcbase(engine_type, fuel_type, built_year, pm_dict)  # g/kWh

    if engine == "aux":
        lf = row.get("LF_aux", 0.40)
    elif phase == "work":
        lf = row.get("LF_work", 0.20)
    else:
        lf = row.get("LF_move", 0.80)

    # SFOC load correction: g/kWh -> tFuel/kWh
    sfc_actual_g_kwh = apply_sfoc_formula(sfcbase, lf, pm_dict)
    return sfc_actual_g_kwh / 1_000_000


def resolve_aux_power_ratio(row, pm_dict, rng=None):
    '\n    \u89e3\u6790\u8f85\u673a/\u4e3b\u673a\u529f\u7387\u6bd4 \u2014 v3.0 (Section D \u2014 \u6309 VesselType)\u3002\n\n    Prior_Matrix Section D (R56 \u2014 2010\u5e74\u5168\u7403\u8239\u961f):\n      AUX_POWER_RATIO_FISHING: \u6e14\u8239 (LL/PS) = 0.39\n      AUX_POWER_RATIO_TP:      \u8f6c\u8fd0\u8239 (TP) = 0.23 (\u4ef6\u6742\u8d27\u8239)\n      AUX_POWER_RATIO_SA:      \u8f85\u52a9\u8239 (SA) = 0.35 (\u5176\u4ed6)\n    \u7eaf\u79bb\u6563\u503c, \u65e0\u5206\u5e03\u91c7\u6837\u3002\n    '
    vt = str(row.get("VesselType", "")).upper()

    if vt == "TP":
        return get_best(pm_dict, "AUX_POWER_RATIO_TP", 0.23)
    elif vt == "SA":
        return get_best(pm_dict, "AUX_POWER_RATIO_SA", 0.35)
    else:
        # LL/PS
        return get_best(pm_dict, "AUX_POWER_RATIO_FISHING", 0.39)


_ALPHA_LOOKUP = None

def assign_operational_params(df, pm_dict, rng=None, lookup_data_alpha=None, alpha_year=2025):
    '\n    \u4e3a\u6240\u6709\u8239\u53ea\u5206\u914d\u8fd0\u8425\u53c2\u6570\u5411\u91cf\u3002\n    \u8fd4\u56de\u589e\u5f3a\u540e\u7684 DataFrame\uff0c\u6dfb\u52a0\u6240\u6709\u8fd0\u8425\u53c2\u6570\u5b57\u6bb5\u3002\n    '
    if rng is None:
        rng = np.random.RandomState(42)
    print('\n[\u8fd0\u8425\u53c2\u6570] \u5206\u914d T_map, H, LF, SFR, Alpha, AUX_Ratio...')

    n = len(df)
    df = df.copy()

    
    df["Sector"] = df.apply(
        lambda r: route_vessel_to_sector(r["Length"], r["VesselType"]), axis=1
    )
    n_i = (df["Sector"] == "I").sum()
    n_apw = (df["Sector"] == "APW").sum()
    print(f"  Sector: I={n_i}, APW={n_apw}")

    # Flag Region
    df["GeoRegion"] = df["Flag"].apply(get_flag_region)
    # Ocean for PS
    df["Ocean"] = df.apply(
        lambda r: get_ocean_for_ps(r["Flag"],
                                   r.get("Authorized_Oceans", ""))
        if r["VesselType"] == "PS" else None, axis=1
    )

    # T_map
    df["T_map"] = df.apply(lambda r: resolve_t_map(r, pm_dict), axis=1)

    # H_main, H_aux
    df["H_main"] = df.apply(lambda r: resolve_hours(r, pm_dict, "main"), axis=1)
    df["H_aux"] = df.apply(lambda r: resolve_hours(r, pm_dict, "aux"), axis=1)

    # LF
    df["LF_move"] = df.apply(lambda r: resolve_lf(r, pm_dict, "move"), axis=1)
    df["LF_work"] = df.apply(lambda r: resolve_lf(r, pm_dict, "work"), axis=1)
    df["LF_aux"] = df.apply(lambda r: resolve_lf(r, pm_dict, "aux"), axis=1)

    
    df["Engine_Type"] = df.apply(lambda r: get_engine_type(r, pm_dict), axis=1)
    df["Fuel_Type"] = df.apply(lambda r: get_fuel_type(r, pm_dict), axis=1)
    df["Has_Aux"] = df.apply(lambda r: 0.0 if get_engine_type(r, pm_dict) == "GASOLINE" else 1.0, axis=1)

    # SFR — v3.0
    df["SFR_main_move"] = df.apply(lambda r: resolve_sfr(r, pm_dict, "main", "move"), axis=1)
    df["SFR_main_work"] = df.apply(lambda r: resolve_sfr(r, pm_dict, "main", "work"), axis=1)
    df["SFR_aux"] = df.apply(lambda r: resolve_sfr(r, pm_dict, "aux"), axis=1)

    # AUX power ratio (v3.0
    df["AUX_Ratio"] = df.apply(lambda r: resolve_aux_power_ratio(r, pm_dict, rng), axis=1)

    
    df["Lifespan_Hull"] = get_best(pm_dict, "LIFESPAN_HULL", 30)
    df["Lifespan_Engine"] = get_best(pm_dict, "LIFESPAN_ENGINE", 10)  

    
    ps_mask = df["VesselType"] == "PS"
    ps_small = ps_mask & (df["Length"] < 12)
    ps_large = ps_mask & (df["Length"] >= 12)
    ll_mask = df["VesselType"] == "LL"

    df["Gear_Lifespan"] = 5.0
    df.loc[ps_mask, "Gear_Lifespan"] = get_best(pm_dict, "LIFESPAN_GEAR_PS", 5)
    df.loc[ll_mask, "Gear_Lifespan"] = get_best(pm_dict, "LIFESPAN_GEAR_LL", 5)

    df["Gear_Maint_Rate"] = 0.25
    df.loc[ps_mask, "Gear_Maint_Rate"] = get_best(pm_dict, "MAINTENANCE_RATE_GEAR_PS", 0.25)
    df.loc[ll_mask, "Gear_Maint_Rate"] = get_best(pm_dict, "MAINTENANCE_RATE_GEAR_LL", 0.25)

    # Gear Intensity
    gear_int_ps_small = get_best(pm_dict, "GEAR_INT_PS", 0.01351)
    gear_int_ps_large = (54.0 + 251.0) / (2 * 1000)  # 0.1525
    gear_int_ll = (0.120 + 0.490) / (2 * 0.0036 * 1000)  # 0.08472

    df["Gear_Intensity"] = 0.0
    df.loc[ps_small, "Gear_Intensity"] = gear_int_ps_small
    df.loc[ps_large, "Gear_Intensity"] = gear_int_ps_large
    df.loc[ll_mask, "Gear_Intensity"] = gear_int_ll

    
    # Industrial
    df["EF_Build"] = 2.421  # default PS steel
    df.loc[(df["VesselType"] == "LL") & (df["Sector"] == "I"), "EF_Build"] = \
        get_best(pm_dict, "EF_BUILD_LL_STEEL", 1.956)
    df.loc[(df["VesselType"] == "PS") & (df["Sector"] == "I"), "EF_Build"] = \
        get_best(pm_dict, "EF_BUILD_PS_STEEL", 2.421)
    df.loc[(df["VesselType"] == "TP") & (df["Sector"] == "I"), "EF_Build"] = \
        get_best(pm_dict, "EF_BUILD_TS", 2.421)  # = PS steel
    # APW: wood
    df.loc[df["Sector"] == "APW", "EF_Build"] = get_best(pm_dict, "EF_BUILD_PS_WOOD", 0.578)

    df["EF_Maint"] = 6.744  # default PS steel
    df.loc[(df["VesselType"] == "LL") & (df["Sector"] == "I"), "EF_Maint"] = \
        get_best(pm_dict, "EF_MAINT_LL_STEEL", 4.45)
    df.loc[(df["VesselType"] == "PS") & (df["Sector"] == "I"), "EF_Maint"] = \
        get_best(pm_dict, "EF_MAINT_PS_STEEL", 6.744)
    df.loc[(df["VesselType"] == "TP") & (df["Sector"] == "I"), "EF_Maint"] = \
        get_best(pm_dict, "EF_MAINT_TS", 6.744)  # = PS steel
    df.loc[df["Sector"] == "APW", "EF_Maint"] = get_best(pm_dict, "EF_MAINT_PS_WOOD", 1.289)

    
    
    
    
    df["R22_Leak"] = 200.0  # default for APW coastal
    df.loc[df["Sector"] == "I", "R22_Leak"] = \
        get_best(pm_dict, "R22_LEAK_DISTANT_PS", 500)
    df.loc[df["VesselType"] == "SA", "R22_Leak"] = \
        get_best(pm_dict, "R22_LEAK_DISTANT_PS", 500)  
    df.loc[(df["VesselType"] == "PS") & (df["Sector"] == "APW"), "R22_Leak"] = \
        get_best(pm_dict, "R22_LEAK_COASTAL_PS", 10)

    global _ALPHA_LOOKUP
    if lookup_data_alpha is None:
        if _ALPHA_LOOKUP is None:
            _ALPHA_LOOKUP = init_time_profile_lookup(PNAS_POWER_PATH, verbose=False)
        lookup_data_alpha = _ALPHA_LOOKUP
    df["Alpha"] = np.clip(query_alpha_work_vectorized(
        df["Flag"].to_numpy(), df["VesselType"].to_numpy(), df["Length"].to_numpy(),
        np.full(n, alpha_year), lookup_data_alpha, sectors=df["Sector"].to_numpy()), 0.0, 1.0)

    print(f"  T_map range: {df['T_map'].min():.0f} - {df['T_map'].max():.0f} days")
    print(f"  H_main range: {df['H_main'].min():.0f} - {df['H_main'].max():.0f} h")
    print(f"  AUX_Ratio range: {df['AUX_Ratio'].min():.3f} - {df['AUX_Ratio'].max():.3f}")
    print(f"  \u8fd0\u8425\u53c2\u6570\u5206\u914d\u5b8c\u6210。")

    return df


# ============================================================

# ============================================================


# ============================================================

# ============================================================

def run_monte_carlo_lca(df, pm_dict, end_year=2025,
                        n_simulations=1000, random_seed=42,
                        lookup_data_power=None, lookup_data_alpha=None,
                        important_params=None, start_year=None, return_draws=False,
                        draw_export_path=None, ll_operation_samples=None, multi_mode_fuel=False):
    '\n    NumPy \u77e9\u9635\u5316\u8499\u7279\u5361\u6d1b LCA \u5f15\u64ce\u3002\n\n    \u8ba1\u7b97\u4ee5\u4e0b\u6392\u653e\u5206\u91cf (tCO2e):\n      - Fuel_CO2:  \u4e3b\u673a(move+work) + \u8f85\u673a CO2 \u6392\u653e\n      - Fuel_CH4:  \u4e3b\u673a + \u8f85\u673a CH4 \u6392\u653e (g/kWh \u2192 tCO2e via GWP)\n      - Fuel_N2O:  \u4e3b\u673a + \u8f85\u673a N2O \u6392\u653e (g/kWh \u2192 tCO2e via GWP)\n      - Build:     \u8239\u4f53\u5efa\u9020 (\u94a2+\u94f8\u94c1+\u94dc, \u6309\u5bff\u547d\u5468\u671f\u6362\u4ee3)\n      - Maint:     \u8239\u4f53\u7ef4\u62a4 (\u6bcf2\u5e74, 12% \u94a2\u6750\u66f4\u6362)\n      - Gear_Build: \u7f51\u5177\u5efa\u9020 (\u6309\u7f51\u5177\u5bff\u547d\u6362\u4ee3)\n      - Gear_Maint: \u7f51\u5177\u7ef4\u62a4 (\u5e74\u5ea6, \u975e\u6362\u4ee3\u5e74)\n      - Bait:      \u9975\u6599 (LL only, \u5728\u7f51\u683c\u5206\u914d\u9636\u6bb5\u8ba1\u7b97)\n      - Refrig:    \u5236\u51b7\u5242\u6cc4\u6f0f (\u5e74\u5ea6\u6052\u5b9a)\n    '
    print(f"\n{'=' * 60}")
    print(f"  MONTE CARLO LCA ENGINE")
    print(f"  {n_simulations} simulations, {end_year} end year")
    print(f"{'=' * 60}")

    if random_seed is not None:
        np.random.seed(random_seed)
    rng = np.random.RandomState(random_seed)

    min_year = int(df["Builtdate"].min())
    if ll_operation_samples is not None and len(ll_operation_samples) != n_simulations:
        raise ValueError("One longline operating profile is required per Monte Carlo draw")
    years_range = np.arange(min_year if start_year is None else max(min_year, int(start_year)), end_year + 1)
    power_years = np.arange(min_year, end_year + 1)
    if len(years_range) == 0:
        raise ValueError("No evaluation years in the requested LCA window")
    n_years = len(years_range)
    n_ships = len(df)

    
    v_type = df["VesselType"].values
    flags = df["Flag"].values
    length = df["Length"].values
    power = np.maximum(df["Enginepower"].values, 0.0)
    tonnage = np.maximum(df["Tonnage"].values, 0.0)
    lsw = np.maximum(df["LSW"].values, 0.0)

    
    
    has_pmm_power = "Enginepower_D1" in df.columns
    has_pmm_tonnage = "Tonnage_D1" in df.columns
    pmm_power_donors = None
    pmm_tonnage_donors = None
    pmm_power_mask = np.zeros(n_ships, dtype=bool)
    pmm_tonnage_mask = np.zeros(n_ships, dtype=bool)

    if has_pmm_power:
        pmm_power_donors = np.column_stack([
            df[f"Enginepower_D{j}"].values for j in range(1, 6)
        ])
        pmm_power_mask = ~np.isnan(pmm_power_donors).any(axis=1)
        n_pmm_power = pmm_power_mask.sum()
        if n_pmm_power > 0:
            print(f"[MC] PMM Enginepower donors: {n_pmm_power} vessels "
                  f"({n_pmm_power/n_ships*100:.1f}%)")

    if has_pmm_tonnage:
        pmm_tonnage_donors = np.column_stack([
            df[f"Tonnage_D{j}"].values for j in range(1, 6)
        ])
        pmm_tonnage_mask = ~np.isnan(pmm_tonnage_donors).any(axis=1)
        n_pmm_ton = pmm_tonnage_mask.sum()
        if n_pmm_ton > 0:
            print(f"[MC] PMM Tonnage donors: {n_pmm_ton} vessels "
                  f"({n_pmm_ton/n_ships*100:.1f}%)")
    
    # 2026-09-21: also keep the full authorisation list per vessel for the
    # fractional (equal-split) organisation account exported as Base_5.
    if "Organization" in df.columns:
        orgs = df["Organization"].astype(str).values
        org_lists = [[str(o)] for o in orgs]
    elif "Authorized_Oceans" in df.columns:
        
        orgs = df["Authorized_Oceans"].astype(str).str.split(";").str[0].str.strip().values
        orgs = np.where(pd.isna(orgs) | (orgs == ""), "GLOBAL", orgs)
        org_lists = []
        for _s_ao in df["Authorized_Oceans"].astype(str).values:
            _l_ao = [x.strip() for x in _s_ao.split(";") if x.strip()]
            org_lists.append(_l_ao if _l_ao else ["GLOBAL"])
    else:
        orgs = np.full(n_ships, "GLOBAL", dtype=object)
        org_lists = [["GLOBAL"]] * n_ships

    
    T_map = df["T_map"].values
    H_main = df["H_main"].values
    H_aux = df["H_aux"].values
    LF_move = df["LF_move"].values
    LF_work = df["LF_work"].values
    LF_aux = df["LF_aux"].values
    
    SFR_main_move = df["SFR_main_move"].values
    SFR_main_work = df["SFR_main_work"].values
    SFR_aux = df["SFR_aux"].values
    
    engine_type = df["Engine_Type"].values
    fuel_type = df["Fuel_Type"].values
    has_aux = df["Has_Aux"].values
    aux_ratio = df["AUX_Ratio"].values
    lifespan_hull = df["Lifespan_Hull"].values
    lifespan_eng = df["Lifespan_Engine"].values  
    gear_lifespan = df["Gear_Lifespan"].values
    gear_maint_rate = df["Gear_Maint_Rate"].values
    gear_intensity = df["Gear_Intensity"].values
    ef_build = df["EF_Build"].values
    ef_maint = df["EF_Maint"].values
    r22_leak = df["R22_Leak"].values

    
    # CO2 EF (
    EF_CO2_HFO = get_best(pm_dict, "EF_CO2_HFO", 3.114)
    EF_CO2_MDO = get_best(pm_dict, "EF_CO2_MDO", 3.206)
    EF_CO2_GASOLINE = get_best(pm_dict, "EF_CO2_Gasoline", 3.158)

    # CH4 EF (
    EF_CH4_SSD = get_best(pm_dict, "EF_CH4_SSD", 0.010)
    EF_CH4_MSD = get_best(pm_dict, "EF_CH4_MSD", 0.010)
    EF_CH4_AUX = get_best(pm_dict, "EF_CH4_AUX", 0.010)
    
    EF_CH4_GASOLINE_4STROKE = get_best(pm_dict, "EF_CH4_GASOLINE_4STROKE", 1.50)

    # N2O EF (
    EF_N2O_SSD_HFO = get_best(pm_dict, "EF_N2O_SSD_HFO", 0.031)
    EF_N2O_SSD_MDO = get_best(pm_dict, "EF_N2O_SSD_MDO", 0.030)
    EF_N2O_MSD_MDO = get_best(pm_dict, "EF_N2O_MSD_MDO", 0.030)
    EF_N2O_AUX_MDO = get_best(pm_dict, "EF_N2O_AUX_MDO", 0.036)
    
    EF_N2O_GASOLINE = get_best(pm_dict, "EF_N2O_GASOLINE", 0.04)

    GWP_CH4 = get_best(pm_dict, "GWP_CH4_100YR", 28.5)
    GWP_N2O = get_best(pm_dict, "GWP_N2O_100YR", 273.0)
    R22_GWP = get_best(pm_dict, "R22_GWP", 1810)

    # WtT (Well-to-Tank) upstream emission factors (kgCO2eq/kg fuel)
    # Source: Scenario_Fuel_Parameters.xlsx > ecoinvent (overridden in Prior_Matrix)
    EF_WTT_DIESEL = get_best(pm_dict, "EF_WTT_DIESEL", 0.369)
    EF_WTT_HFO = get_best(pm_dict, "EF_WTT_HFO", 0.252)
    EF_WTT_GASOLINE = get_best(pm_dict, "EF_WTT_GASOLINE", 0.535)

    
    MAINT_INTERVAL = 2
    MAINT_RATE_STEEL = 0.12

    
    BAIT_WEIGHT = get_best(pm_dict, "BAIT_WEIGHT_PER_HOOK_KG", 0.1)
    EF_BAIT = get_best(pm_dict, "EMISSION_FACTOR_BAIT", 1.606)
    HOOKS_PER_DAY_LL = get_best(pm_dict, "HOOKS_PER_DAY", 3000.0)

    
    NYLON_FRAC_PS = get_best(pm_dict, "GEAR_MATERIAL_NYLON_PS", 0.739)
    STEEL_FRAC_PS = get_best(pm_dict, "GEAR_MATERIAL_STEEL_PS", 0.261)
    NYLON_FRAC_LL = get_best(pm_dict, "GEAR_MATERIAL_NYLON_LL", 0.739)
    STEEL_FRAC_LL = get_best(pm_dict, "GEAR_MATERIAL_STEEL_LL", 0.261)
    EF_NYLON = get_best(pm_dict, "EMISSION_FACTOR_NYLON_PA6", 9.885)
    EF_STEEL_GEAR = get_best(pm_dict, "EMISSION_FACTOR_STEEL_GEAR", 3.07)

    # PS
    EF_GEAR_PS = NYLON_FRAC_PS * EF_NYLON + STEEL_FRAC_PS * EF_STEEL_GEAR
    # LL
    EF_GEAR_LL = NYLON_FRAC_LL * EF_NYLON + STEEL_FRAC_LL * EF_STEEL_GEAR

    ef_gear_vec = np.where(v_type == "PS", EF_GEAR_PS,
                           np.where(v_type == "LL", EF_GEAR_LL, EF_GEAR_PS))

    
    is_gasoline = (engine_type == "GASOLINE")
    is_ssd = (engine_type == "SSD")
    is_msd = (engine_type == "MSD") & ~is_gasoline
    if multi_mode_fuel:
        if ll_operation_samples is not None:
            raise ValueError("Select either multi-mode fuel or the legacy longline trial")
        sfoc = lambda load: apply_sfoc_formula(1.0, load, pm_dict)
        operating_draws = draw_operating_days(n_simulations, random_seed, sfoc)
        classes = operation_classes(v_type, is_gasoline)
        fuel_groups = {group: classes == group for group in operating_draws}
        base_main_sfc = SFR_main_move / np.where(is_gasoline, 1., sfoc(LF_move))
        base_aux_sfc = SFR_aux / sfoc(LF_aux)
    if ll_operation_samples is not None:
        from ll_operation import operation_day

        ll_diesel = np.flatnonzero((v_type == "LL") & ~is_gasoline)
        ll_regions = np.array([get_flag_region(flag) or "Global" for flag in flags[ll_diesel]])
        sfoc_factor = lambda load: apply_sfoc_formula(1.0, load, pm_dict)
        ll_sfcbase = SFR_main_move[ll_diesel] / sfoc_factor(LF_move[ll_diesel])

    ef_co2_vec = np.where(is_gasoline, EF_CO2_GASOLINE,
                  np.where(is_ssd, EF_CO2_HFO, EF_CO2_MDO))

    # CH4
    ef_ch4_main_vec = np.where(is_gasoline, EF_CH4_GASOLINE_4STROKE,
                       np.where(is_ssd, EF_CH4_SSD, EF_CH4_MSD))
    ef_ch4_aux_vec = np.where(has_aux > 0, EF_CH4_AUX, 0.0)

    # N2O
    ef_n2o_main_vec = np.where(is_gasoline, EF_N2O_GASOLINE,
                       np.where(is_ssd, EF_N2O_SSD_HFO, EF_N2O_MSD_MDO))
    ef_n2o_aux_vec = np.where(has_aux > 0, EF_N2O_AUX_MDO, 0.0)

    # WtT EF vector: map engine_type → fuel → WtT EF
    wtt_ef_vec = np.where(is_gasoline, EF_WTT_GASOLINE,
                  np.where(is_ssd, EF_WTT_HFO, EF_WTT_DIESEL))

    
    if lookup_data_alpha is not None:
        print('[LCA]   \u67e5\u8be2 alpha_work (\u6355\u635e\u65f6\u95f4\u6bd4\u4f8b)...')
        alpha_vec = query_alpha_work_vectorized(
            flags, v_type, length,
            np.full(n_ships, min_year),  # use min_year for alpha lookup
            lookup_data_alpha
        )
        alpha_vec = np.nan_to_num(alpha_vec, nan=0.3125)  
    else:
        alpha_vec = np.full(n_ships, 0.3125)

    
    if lookup_data_power is not None:
        print('[LCA]   \u9884\u8ba1\u7b97 PNAS \u529f\u7387\u6298\u6263\u77e9\u9635...')
        all_flags_flat = np.repeat(flags, len(power_years))
        all_gears_flat = np.repeat(v_type, len(power_years))
        all_lengths_flat = np.repeat(length, len(power_years))
        all_years_flat = np.tile(power_years, n_ships)

        all_factors = query_power_discount_vectorized(
            all_flags_flat, all_gears_flat, all_lengths_flat,
            all_years_flat, lookup_data_power
        )
        discount_matrix = all_factors.reshape(n_ships, len(power_years))
        print(f"   \u6298\u6263\u77e9\u9635: {discount_matrix.shape}")
    else:
        discount_matrix = None

    
    sector_col = df["Sector"].values if "Sector" in df.columns else np.full(n_ships, "I")
    group_names = np.array([f"{f}_{t}_{s}" for f, t, s in zip(flags, v_type, sector_col)])
    unique_groups, group_inv = np.unique(group_names, return_inverse=True)
    num_groups = len(unique_groups)

    unique_orgs = np.unique([o for items in org_lists for o in items])
    org_inv = np.searchsorted(unique_orgs, orgs)
    num_orgs = len(unique_orgs)

    
    _org_index = {o: i for i, o in enumerate(unique_orgs)}
    org_w = np.zeros((n_ships, num_orgs), dtype=float)
    for _i_w, _lst_w in enumerate(org_lists):
        _uniq_w = [o for o in dict.fromkeys(_lst_w) if o in _org_index]
        if not _uniq_w:
            _uniq_w = ["GLOBAL"] if "GLOBAL" in _org_index else [str(unique_orgs[0])]
        _w_org = 1.0 / len(_uniq_w)
        for _o_w in _uniq_w:
            org_w[_i_w, _org_index[_o_w]] = _w_org

    
    _cat_names = []
    for _t_c, _s_c in zip(v_type, sector_col):
        if _t_c in ("LL", "PS"):
            _cat_names.append(f"{_t_c}_DW" if _s_c == "I" else f"{_t_c}_CO")
        else:
            _cat_names.append(str(_t_c))
    unique_cats, cat_inv = np.unique(np.array(_cat_names), return_inverse=True)
    num_cats = len(unique_cats)
    _cat_mask = [cat_inv == _c_i for _c_i in range(num_cats)]
    _org_w_cat = [org_w[_cat_mask[_c_i]] for _c_i in range(num_cats)]

    # ---- share5: allocate fleet emissions to the 5 market species (E_tuna) ----
    # factor[group, year] loaded from effort_data/Share5_Lookup_FlagGearYear.csv
    share5_factor = np.ones((num_groups, n_years), dtype=float)
    try:
        s5 = pd.read_csv(SHARE5_LOOKUP_PATH)
        s5.columns = [str(c).strip() for c in s5.columns]
        s5['flag'] = s5['flag'].astype(str)
        s5['gear'] = s5['gear'].astype(str)
        years_int = years_range.astype(int)
        s5_pivot = {}
        for (fl, gr), grp in s5.groupby(['flag', 'gear']):
            ymap = {int(y): float(v) for y, v in zip(grp['Year'], grp['share5']) if pd.notna(v)}
            if not ymap:
                continue
            arr = np.ones(n_years, dtype=float)
            ys = list(ymap.keys())
            for yi, yr in enumerate(years_int):
                if yr in ymap:
                    arr[yi] = ymap[yr]
                else:
                    arr[yi] = ymap[min(ys, key=lambda y: abs(y - int(yr)))]
            s5_pivot[(fl, gr)] = arr
        n_match = 0
        for gi, gname in enumerate(unique_groups):
            parts_g = gname.rsplit('_', 2)
            if len(parts_g) == 3:
                arr = s5_pivot.get((parts_g[0], parts_g[1]))
                if arr is not None:
                    share5_factor[gi, :] = arr
                    n_match += 1
        print(f"[share5] species-share allocation: {n_match}/{num_groups} groups matched, "
              f"{len(s5)} lookup rows")
    except FileNotFoundError:
        raise FileNotFoundError(f"Required five-species allocation input missing: {SHARE5_LOOKUP_PATH}. Restore the scientific data before running the model.") from None

    # ---- FC Lookup ----
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
        2016: 0.99,
    }

    def get_fc_array(years):
        fc = np.ones_like(years, dtype=float)
        fc[years < 1950] = 1.21
        fc[years > 2016] = 0.99
        for y, val in FC_LOOKUP.items():
            fc[years == y] = val
        return fc

    
    
    
    gear_w = length * gear_intensity

    
    processes = ["Fuel_CO2", "Fuel_CH4", "Fuel_N2O", "Fuel_WTT",
                 "Build", "Maint", "Gear_Build", "Gear_Maint", "Refrig", "Bait"]
    results_cube = {p: np.zeros((num_groups, n_simulations, n_years))
                    for p in processes}
    results_cube["Total"] = np.zeros((num_groups, n_simulations, n_years))

    org_results = {p: np.zeros((num_orgs, n_simulations, n_years))
                   for p in processes}
    org_results["Total"] = np.zeros((num_orgs, n_simulations, n_years))

    # 2026-09-21: org x gear-sector cube (fractional equal-split weights)
    org_cat_results = np.zeros((num_orgs, num_cats, n_simulations, n_years))

    global_results = {p: np.zeros((n_simulations, n_years)) for p in processes}
    global_results["Total"] = np.zeros((n_simulations, n_years))

    
    current_builtdate = df["Builtdate"].values.astype(float)

    # ================================================================
    # MC
    # ================================================================
    
    #   PM
    #   PM
    #   PM Discrete /
    
    # ================================================================
    PARAM_DISTS = {
        
        "T_map":    ("Triangular",  dict(left=0.85, mode=1.00, right=1.15)),
        "SFCbase":  ("Triangular",  dict(left=0.80, mode=1.00, right=1.20)),
        "H_map":    ("Triangular",  dict(left=0.85, mode=1.00, right=1.15)),
        "LF_move":  ("Triangular",  dict(left=0.80, mode=1.00, right=1.20)),
        "LF_work":  ("Triangular",  dict(left=0.80, mode=1.00, right=1.20)),
        "AUX":      ("Triangular",  dict(left=0.80, mode=1.00, right=1.20)),
        "Alpha":    ("Triangular",  dict(left=0.80, mode=1.00, right=1.20)),
        "Power":    ("Triangular",  dict(left=0.80, mode=1.00, right=1.20)),
        "R22":      ("Triangular",  dict(left=0.80, mode=1.00, right=1.20)),
        # --- PM Lognormal (sigma from PM [Low, High] bounds) ---
        # EF_Build PS Steel: [2.332, 2.528] → σ=ln(2.528/2.332)/3.92≈0.021
        "EF_Build": ("Lognormal",   dict(mean=0.0, sigma=0.021)),
        # EF_Maint: avg across PS Steel [6.63,6.88] & LL Steel [3.78,5.38] → σ≈0.050
        "EF_Maint": ("Lognormal",   dict(mean=0.0, sigma=0.050)),
        # Gear: Steel gear EF [2.819, 3.374] dominates over Nylon → σ≈0.045
        "Gear":     ("Lognormal",   dict(mean=0.0, sigma=0.045)),
        # Bait EF: [1.548, 1.67] → σ=ln(1.67/1.548)/3.92≈0.019
        "Bait_EF":  ("Lognormal",   dict(mean=0.0, sigma=0.019)),
        # --- PM Triangular with explicit bounds ---
        # PM: Tri(0.05,0.10,0.15) ABS kg/hook → multiplier vs Best=0.10
        "Bait_Wt":  ("Triangular",  dict(left=0.50, mode=1.00, right=1.50)),
    }

    if important_params is None:
        important_params = set(PARAM_DISTS.keys())
    print(f"[MC] \u91c7\u6837\u53c2\u6570 ({len(important_params)}): {sorted(important_params)}")
    print(f"[MC] \u56fa\u5b9a\u53c2\u6570 (\u4e58\u6570=1.0): {sorted(set(PARAM_DISTS.keys()) - important_params)}")

    def sample_multipliers(rng):
        '\u6bcf\u4e2a MC \u8fed\u4ee3\u4ec5\u91c7\u6837 GSA \u8bc6\u522b\u7684\u5173\u952e\u53c2\u6570\u3002\u672a\u8bc6\u522b\u53c2\u6570 = 1.0\u3002'
        mul = {k: 1.0 for k in PARAM_DISTS}
        for key in sorted(important_params):   # sorted: set iteration order is hash-randomized per process (PYTHONHASHSEED) -> non-deterministic rng consumption
            if key not in PARAM_DISTS:
                continue
            dist_type, args = PARAM_DISTS[key]
            if dist_type == "Triangular":
                mul[key] = rng.triangular(args["left"], args["mode"], args["right"])
            elif dist_type == "Lognormal":
                mul[key] = rng.lognormal(args["mean"], args["sigma"])
            elif dist_type == "Uniform":
                mul[key] = rng.uniform(args["low"], args["high"])
        return mul

    multiplier_draws = []
    
    for sim in range(n_simulations):
        
        mul = sample_multipliers(rng)
        if ll_operation_samples is not None:
            ll_days, ll_fishing_days, main_daily_load_h, main_daily_fuel_h = operation_day(
                ll_operation_samples, ll_regions, sim, sfoc_factor
            )
        if return_draws:
            multiplier_draws.append(mul.copy())

        
        current_power = power.copy()
        current_tonnage = tonnage.copy()
        current_lsw = lsw.copy()
        if pmm_power_donors is not None:
            col_idx = rng.randint(0, 5, size=n_ships)
            sampled = pmm_power_donors[np.arange(n_ships), col_idx]
            current_power[pmm_power_mask] = np.maximum(
                sampled[pmm_power_mask], 0.0)
        if pmm_tonnage_donors is not None:
            col_idx = rng.randint(0, 5, size=n_ships)
            sampled = pmm_tonnage_donors[np.arange(n_ships), col_idx]
            current_tonnage[pmm_tonnage_mask] = np.maximum(
                sampled[pmm_tonnage_mask], 0.0)
            # LSW
            ldt_gt_fishing = get_best(pm_dict, "LDT_GT_RATIO_FISHING", 0.859)
            ldt_gt_cargo = get_best(pm_dict, "LDT_GT_RATIO_CARGO_REF", 0.287)
            is_tp_ts = np.isin(v_type, ["TP", "TS"])
            ldt_ratio = np.where(is_tp_ts, ldt_gt_cargo, ldt_gt_fishing)
            current_lsw[pmm_tonnage_mask] = (
                current_tonnage[pmm_tonnage_mask] * ldt_ratio[pmm_tonnage_mask])

        
        # FC
        fc_array = get_fc_array(current_builtdate)
        fc_array[np.isnan(fc_array)] = 1.0

        
        latest_engine_year = current_builtdate + \
            ((end_year - current_builtdate) // lifespan_eng) * lifespan_eng
        latest_engine_year = np.clip(latest_engine_year, min_year, end_year)

        retire_year_arr = (pd.to_numeric(df["Retire_Year"], errors="coerce").fillna(np.inf).to_numpy()
                           if "Retire_Year" in df.columns
                           else np.full(n_ships, 9999.0))

        for y_idx, year in enumerate(years_range):
            age = year - current_builtdate
            active_mask = (age >= 0) & (year < retire_year_arr)

            
            if discount_matrix is not None:
                curr_eng_year = current_builtdate + (age // lifespan_eng) * lifespan_eng
                curr_eng_year = np.clip(curr_eng_year, min_year, end_year)

                ship_idx = np.arange(n_ships)
                curr_col = np.clip(curr_eng_year - min_year, 0, len(power_years) - 1).astype(int)
                latest_col = np.clip(latest_engine_year - min_year, 0, len(power_years) - 1).astype(int)

                factor_curr = discount_matrix[ship_idx, curr_col]
                factor_latest = discount_matrix[ship_idx, latest_col]

                factor_latest_safe = np.where(factor_latest <= 0.01, 1.0, factor_latest)
                ratio = np.where(factor_latest <= 0.01, 1.0,
                                 factor_curr / factor_latest_safe)
                adj_power = current_power * ratio
            else:
                adj_power = current_power

            P_main = adj_power * mul["Power"]
            P_aux = P_main * aux_ratio * mul["AUX"]

            
            total_days = T_map * mul["T_map"]
            H_main_day = H_main * mul["H_map"]
            H_aux_day = H_aux

            alpha = np.clip(alpha_vec * mul["Alpha"], 0.0, 1.0)
            hours_main_move = (1.0 - alpha) * total_days * H_main_day
            hours_main_work = alpha * total_days * H_main_day
            hours_aux = total_days * H_aux_day  

            
            lf_move_m = LF_move * mul["LF_move"]
            lf_work_m = LF_work * mul["LF_work"]
            # LF_aux: per-vessel Uniform(0.3, 0.5) per PM Section C (NOT a global multiplier)
            lf_aux_m  = rng.uniform(0.3, 0.5, size=n_ships) * active_mask
            
            sfc_m_move = SFR_main_move * mul["SFCbase"]
            sfc_m_work = SFR_main_work * mul["SFCbase"]
            sfc_a      = SFR_aux * mul["SFCbase"]

            # ====================================================
            
            # ====================================================
            co2_main_move = (P_main * lf_move_m * sfc_m_move * hours_main_move *
                            ef_co2_vec * fc_array * active_mask)
            co2_main_work = (P_main * lf_work_m * sfc_m_work * hours_main_work *
                            ef_co2_vec * fc_array * active_mask)
            co2_aux = (P_aux * lf_aux_m * sfc_a * hours_aux *
                      ef_co2_vec * fc_array * active_mask)
            fuel_co2 = co2_main_move + co2_main_work + co2_aux

            # ====================================================
            
            # ====================================================
            total_hours_main = hours_main_move + hours_main_work
            lf_main_avg = np.where(total_hours_main > 0,
                                   (lf_move_m * hours_main_move + lf_work_m * hours_main_work) /
                                   total_hours_main, 0)

            
            ch4_main_diesel = np.where(~is_gasoline,
                P_main * lf_main_avg * total_hours_main *
                ef_ch4_main_vec / 1_000_000 * GWP_CH4 * fc_array * active_mask, 0.0)
            ch4_aux_diesel = np.where(~is_gasoline & (has_aux > 0),
                P_aux * lf_aux_m * hours_aux *
                ef_ch4_aux_vec / 1_000_000 * GWP_CH4 * fc_array * active_mask, 0.0)

            
            fuel_move_gas = P_main * lf_move_m * sfc_m_move * hours_main_move
            fuel_work_gas = P_main * lf_work_m * sfc_m_work * hours_main_work
            fuel_total_gas = (fuel_move_gas + fuel_work_gas) * fc_array * active_mask
            ch4_gasoline = np.where(is_gasoline,
                fuel_total_gas * 1000 * ef_ch4_main_vec / 1_000_000 * GWP_CH4, 0.0)

            fuel_ch4 = ch4_main_diesel + ch4_aux_diesel + ch4_gasoline

            # ====================================================
            
            # ====================================================
            n2o_main_diesel = np.where(~is_gasoline,
                P_main * lf_main_avg * total_hours_main *
                ef_n2o_main_vec / 1_000_000 * GWP_N2O * fc_array * active_mask, 0.0)
            n2o_aux_diesel = np.where(~is_gasoline & (has_aux > 0),
                P_aux * lf_aux_m * hours_aux *
                ef_n2o_aux_vec / 1_000_000 * GWP_N2O * fc_array * active_mask, 0.0)

            
            n2o_gasoline = np.where(is_gasoline,
                fuel_total_gas * 1000 * ef_n2o_main_vec / 1_000_000 * GWP_N2O, 0.0)

            fuel_n2o = n2o_main_diesel + n2o_aux_diesel + n2o_gasoline

            # ====================================================
            # 6d. Fuel WtT (Well-to-Tank upstream, v3.0)
            # fuel_total [t] = P × LF × SFR × hours × FC
            # fuel_wtt [tCO2e] = fuel_total × WtT_EF [kgCO2eq/kg]
            # ====================================================
            fuel_t_move = P_main * lf_move_m * sfc_m_move * hours_main_move * fc_array * active_mask
            fuel_t_work = P_main * lf_work_m * sfc_m_work * hours_main_work * fc_array * active_mask
            fuel_t_aux  = P_aux * lf_aux_m * sfc_a * hours_aux * fc_array * active_mask
            fuel_total_t = fuel_t_move + fuel_t_work + fuel_t_aux
            fuel_wtt = fuel_total_t * wtt_ef_vec  # tCO2eq

            if multi_mode_fuel:
                for group, ii in fuel_groups.items():
                    days, main_ld, main_sfr, aux_ld, aux_sfr = operating_draws[group][sim]
                    scale = days * fc_array[ii] * active_mask[ii]
                    main_energy = P_main[ii] * main_ld * scale
                    aux_energy = P_aux[ii] * aux_ld * scale
                    fuel = (P_main[ii] * main_sfr * base_main_sfc[ii] +
                            P_aux[ii] * aux_sfr * base_aux_sfc[ii]) * mul["SFCbase"] * scale
                    fuel_co2[ii] = fuel * ef_co2_vec[ii]
                    fuel_wtt[ii] = fuel * wtt_ef_vec[ii]
                    if group == "LL_gasoline":
                        fuel_ch4[ii] = fuel * ef_ch4_main_vec[ii] * GWP_CH4 / 1000
                        fuel_n2o[ii] = fuel * ef_n2o_main_vec[ii] * GWP_N2O / 1000
                    else:
                        fuel_ch4[ii] = (main_energy * ef_ch4_main_vec[ii] + aux_energy * ef_ch4_aux_vec[ii]) * GWP_CH4 / 1e6
                        fuel_n2o[ii] = (main_energy * ef_n2o_main_vec[ii] + aux_energy * ef_n2o_aux_vec[ii]) * GWP_N2O / 1e6

            if ll_operation_samples is not None:
                # Effective sea days already include annual fleet utilisation.
                ii = ll_diesel
                scale = fc_array[ii] * active_mask[ii]
                main_energy = P_main[ii] * ll_days * main_daily_load_h * scale
                main_fuel = P_main[ii] * ll_days * main_daily_fuel_h * ll_sfcbase * mul["SFCbase"] * scale
                aux_energy = P_aux[ii] * lf_aux_m[ii] * ll_days * H_aux_day[ii] * scale
                combined_fuel = main_fuel + aux_energy * sfc_a[ii]
                fuel_co2[ii] = combined_fuel * ef_co2_vec[ii]
                fuel_wtt[ii] = combined_fuel * wtt_ef_vec[ii]
                fuel_ch4[ii] = (main_energy * ef_ch4_main_vec[ii] + aux_energy * ef_ch4_aux_vec[ii]) * GWP_CH4 / 1e6
                fuel_n2o[ii] = (main_energy * ef_n2o_main_vec[ii] + aux_energy * ef_n2o_aux_vec[ii]) * GWP_N2O / 1e6

            # ====================================================
            
            # ====================================================
            build_annual = (age == 0) * current_lsw * ef_build * mul["EF_Build"] * active_mask

            # ====================================================
            
            # ====================================================
            is_steel_maint = ((age % MAINT_INTERVAL == 0) &
                             (age >= 2) & active_mask)
            maint_annual = (is_steel_maint * current_lsw * MAINT_RATE_STEEL *
                           ef_maint * mul["EF_Maint"])

            # ====================================================
            
            # ====================================================
            is_gear_repl = (age % gear_lifespan == 0) & active_mask
            gear_build_annual = is_gear_repl * gear_w * ef_gear_vec * mul["Gear"]

            # ====================================================
            
            # ====================================================
            is_gear_maint = (age % gear_lifespan != 0) & active_mask
            gear_maint_annual = is_gear_maint * gear_w * gear_maint_rate * ef_gear_vec * mul["Gear"]

            # ====================================================
            
            # ====================================================
            refrig_annual = r22_leak * R22_GWP / 1000.0 * mul["R22"] * active_mask

            # ====================================================
            
            # ====================================================
            is_ll = (v_type == "LL")
            bait_annual = np.where(
                is_ll & active_mask,
                total_days * (H_main / 24.0) * HOOKS_PER_DAY_LL *
                BAIT_WEIGHT * mul["Bait_Wt"] * EF_BAIT * mul["Bait_EF"] / 1000.0,
                0.0
            )

            if ll_operation_samples is not None:
                bait_annual[ll_diesel] = (
                    ll_fishing_days * active_mask[ll_diesel] * HOOKS_PER_DAY_LL *
                    BAIT_WEIGHT * mul["Bait_Wt"] * EF_BAIT * mul["Bait_EF"] / 1000.0
                )

            # ---- share5: allocate ship emissions to the 5 market species (E_tuna) ----
            sf = share5_factor[group_inv, y_idx]
            if "Ghost_Weight" in df:
                sf = sf * df["Ghost_Weight"].fillna(1.0).to_numpy()
            fuel_co2 *= sf
            fuel_ch4 *= sf
            fuel_n2o *= sf
            fuel_wtt *= sf
            build_annual *= sf
            maint_annual *= sf
            gear_build_annual *= sf
            gear_maint_annual *= sf
            refrig_annual *= sf
            bait_annual *= sf

            
            def agg(w):
                return np.bincount(group_inv, weights=w, minlength=num_groups)

            def agg_org(w):
                return np.bincount(org_inv, weights=w, minlength=num_orgs)

            results_cube["Fuel_CO2"][:, sim, y_idx] = agg(fuel_co2)
            results_cube["Fuel_CH4"][:, sim, y_idx] = agg(fuel_ch4)
            results_cube["Fuel_N2O"][:, sim, y_idx] = agg(fuel_n2o)
            results_cube["Fuel_WTT"][:, sim, y_idx] = agg(fuel_wtt)
            results_cube["Build"][:, sim, y_idx] = agg(build_annual)
            results_cube["Maint"][:, sim, y_idx] = agg(maint_annual)
            results_cube["Gear_Build"][:, sim, y_idx] = agg(gear_build_annual)
            results_cube["Gear_Maint"][:, sim, y_idx] = agg(gear_maint_annual)
            results_cube["Refrig"][:, sim, y_idx] = agg(refrig_annual)
            results_cube["Bait"][:, sim, y_idx] = agg(bait_annual)

            total_annual = (fuel_co2 + fuel_ch4 + fuel_n2o + fuel_wtt + build_annual +
                           maint_annual + gear_build_annual + gear_maint_annual +
                           refrig_annual + bait_annual)
            results_cube["Total"][:, sim, y_idx] = agg(total_annual)

            # Dispatch table for process → array
            process_arrays = {
                "Fuel_CO2": fuel_co2, "Fuel_CH4": fuel_ch4,
                "Fuel_N2O": fuel_n2o, "Fuel_WTT": fuel_wtt,
                "Build": build_annual, "Maint": maint_annual,
                "Gear_Build": gear_build_annual,
                "Gear_Maint": gear_maint_annual,
                "Refrig": refrig_annual, "Bait": bait_annual,
            }
            for p in processes:
                org_results[p][:, sim, y_idx] = agg_org(process_arrays[p])
            org_results["Total"][:, sim, y_idx] = agg_org(total_annual)
            for _c_i in range(num_cats):
                _m_c = _cat_mask[_c_i]
                if _m_c.any():
                    org_cat_results[:, _c_i, sim, y_idx] = \
                        _org_w_cat[_c_i].T @ total_annual[_m_c]

            for p in processes:
                global_results[p][sim, y_idx] = process_arrays[p].sum()
            global_results["Total"][sim, y_idx] = total_annual.sum()

        if (sim + 1) % 100 == 0:
            print(f"  \u5df2\u5b8c\u6210 {sim + 1} / {n_simulations} \u6b21\u6a21\u62df...")

    if return_draws:
        return years_range, pd.DataFrame(multiplier_draws), global_results

    if draw_export_path is not None:
        # Preserve paired Monte Carlo draws so downstream aggregation happens
        # before taking quantiles. Marginal p5/p95 values cannot be added.
        np.savez_compressed(draw_export_path, years=years_range,
                            groups=np.asarray(unique_groups, dtype=str),
                            total_by_group=results_cube["Total"],
                            refrigerant_by_group=results_cube["Refrig"],
                            authorized_organizations=np.asarray(unique_orgs, dtype=str),
                            gear_sectors=np.asarray(unique_cats, dtype=str),
                            authorized_org_sector_total=org_cat_results,
                            **{"global_"+p: v for p, v in global_results.items()})

    # ============================================================
    
    # ============================================================
    print('\n[\u540e\u5904\u7406] \u751f\u6210\u6c47\u603b\u8868...')

    # Fleet GHG (Flag × Gear × Year) — median + CI
    total_median = np.percentile(results_cube["Total"], 50, axis=1)
    total_p5 = np.percentile(results_cube["Total"], 5, axis=1)
    total_p95 = np.percentile(results_cube["Total"], 95, axis=1)
    records = []
    for g_idx, g_name in enumerate(unique_groups):
        # v3.0: group_name = "Flag_Gear_Sector"
        parts = g_name.rsplit("_", 2)
        if len(parts) == 3:
            flag, gear, sector = parts
        else:
            flag, gear = parts[0], parts[1]
            sector = "I"
        for y_idx, year in enumerate(years_range):
            rec = {"Flag": flag, "Gear": gear, "Sector": sector, "Year": year,
                   "Nat_GHG_median": total_median[g_idx, y_idx],
                   "Nat_GHG_p5":    total_p5[g_idx, y_idx],
                   "Nat_GHG_p95":   total_p95[g_idx, y_idx]}
            for p in processes:
                rec[f"{p}_median"] = np.percentile(
                    results_cube[p][g_idx, :, y_idx], 50)
                rec[f"{p}_p5"] = np.percentile(
                    results_cube[p][g_idx, :, y_idx], 5)
                rec[f"{p}_p95"] = np.percentile(
                    results_cube[p][g_idx, :, y_idx], 95)
            records.append(rec)
    df_fleet = pd.DataFrame(records)

    
    flag_to_org = {}
    for flag in np.unique(flags):
        mask = flags == flag
        orgs_for_flag = orgs[mask]
        
        unique_o, counts_o = np.unique(orgs_for_flag, return_counts=True)
        flag_to_org[flag] = unique_o[np.argmax(counts_o)]
    df_fleet["Organization"] = df_fleet["Flag"].map(flag_to_org)

    # Global Process Timeseries
    global_records = []
    for y_idx, year in enumerate(years_range):
        row = {"Year": year}
        for p in list(processes) + ["Total"]:
            row[f"{p}_median"] = np.percentile(global_results[p][:, y_idx], 50)
            row[f"{p}_p5"] = np.percentile(global_results[p][:, y_idx], 5)
            row[f"{p}_p95"] = np.percentile(global_results[p][:, y_idx], 95)
        global_records.append(row)
    df_global = pd.DataFrame(global_records)

    # Organization GHG
    org_records = []
    for o_idx, o_name in enumerate(unique_orgs):
        for y_idx, year in enumerate(years_range):
            rec = {"Organization": o_name, "Year": year,
                   "Total_median": np.percentile(
                       org_results["Total"][o_idx, :, y_idx], 50)}
            for p in processes:
                rec[f"{p}_median"] = np.percentile(
                    org_results[p][o_idx, :, y_idx], 50)
            org_records.append(rec)
    df_org = pd.DataFrame(org_records)

    # Organization x gear-sector (fractional equal-split weights, 2026-09-21)
    org_cat_records = []
    for _o_idx, _o_name in enumerate(unique_orgs):
        for _c_idx, _c_name in enumerate(unique_cats):
            for _y_idx, _year in enumerate(years_range):
                _vals = org_cat_results[_o_idx, _c_idx, :, _y_idx]
                org_cat_records.append({
                    "Organization": _o_name,
                    "Gear_Sector": _c_name,
                    "Year": _year,
                    "Total_median": np.percentile(_vals, 50),
                    "Total_p5": np.percentile(_vals, 5),
                    "Total_p95": np.percentile(_vals, 95),
                })
    df_org_cat = pd.DataFrame(org_cat_records)

    return (years_range, df_fleet, df_global, df_org, df_org_cat,
            global_results, results_cube)


# ============================================================

# ============================================================

# ============================================================

# ============================================================

def process_catch_and_cei(catch_file, df_fleet, pm_dict):
    '\n    \u57fa\u4e8e Catch \u6570\u636e\u6d4b\u7b97\u7f51\u683c\u7ea7 GHG \u5206\u914d & CEI\u3002\n\n    \u6cbf\u7528\u73b0\u6709 Effort \u6807\u51c6\u5316\u903b\u8f91\uff0c\u66f4\u65b0\u9975\u6599 EF \u4e3a Prior_Matrix \u503c\u3002\n    '
    print(f"\n[Catch] \u8bfb\u53d6 Catch \u6570\u636e & \u7a7a\u95f4\u5206\u914d...")
    print(f"  \u6587\u4ef6: {catch_file}")

    
    BAIT_WEIGHT = get_best(pm_dict, "BAIT_WEIGHT_PER_HOOK_KG", 0.1)  # kg/hook, Row 114
    EF_BAIT = get_best(pm_dict, "EMISSION_FACTOR_BAIT", 1.606)       # kgCO2/kg, Row 115
    HOOKS_PER_DAY = get_best(pm_dict, "HOOKS_PER_DAY", 3000.0)       # Row 123
    HOURS_PER_SET = get_best(pm_dict, "HOURS_PER_SET", 12.0)         # Row 124

    print(f"  \u9975\u6599 EF: {EF_BAIT} kgCO2/kg bait (Prior_Matrix G, Row 115)")
    print(f"  \u5355\u94a9\u9975\u91cd: {BAIT_WEIGHT} kg/hook (Prior_Matrix G, Row 114)")

    catch_df = pd.read_csv(catch_file)
    catch_df.columns = catch_df.columns.str.lower().str.strip()
    catch_df.rename(columns={"organization": "Organization"}, inplace=True)

    
    
    if "flag" not in catch_df.columns and "country" in catch_df.columns:
        catch_df.rename(columns={"country": "flag"}, inplace=True)

    
    sys.path.insert(0, os.path.join(ROOT_DIR, "effort_data"))
    from flag_utils import normalize_flag_to_iso3
    catch_df["flag"] = catch_df["flag"].astype(str).str.strip().apply(normalize_flag_to_iso3)
    
    catch_df = catch_df[catch_df["flag"] != ""].copy()

    catch_col_mapping = {
        "gear": "Gear", "flag": "Flag", "year": "Year",
        "efforttype": "EffortType", "effortvalue": "EffortValue",
        "sbt_tonnes": "SBT_Tonnes", "skj_tonnes": "SKJ_Tonnes",
        "bet_tonnes": "BET_Tonnes", "yft_tonnes": "YFT_Tonnes",
        "alb_tonnes": "ALB_Tonnes",
    }
    catch_df.rename(columns=catch_col_mapping, inplace=True)
    catch_df["Gear"] = catch_df["Gear"].astype(str).str.upper().str.strip()
    catch_df["Flag"] = catch_df["Flag"].astype(str).str.strip()

    species_cols = ["SBT_Tonnes", "SKJ_Tonnes", "BET_Tonnes", "YFT_Tonnes", "ALB_Tonnes"]
    for col in species_cols:
        catch_df[col] = pd.to_numeric(catch_df[col], errors="coerce").fillna(0)
    catch_df["Total_Catch"] = catch_df[species_cols].sum(axis=1)

    
    catch_df["Standard_Effort"] = 0.0
    mask_ll = catch_df["Gear"] == "LL"
    mask_ps = catch_df["Gear"] == "PS"

    mask_hooks = mask_ll & catch_df["EffortType"].isin(
        ["HOOKS", "NO.HOOKS", "Number of Hooks"])
    catch_df.loc[mask_hooks, "Standard_Effort"] = catch_df.loc[mask_hooks, "EffortValue"]

    mask_hhooks = mask_ll & (catch_df["EffortType"] == "HHOOKS")
    catch_df.loc[mask_hhooks, "Standard_Effort"] = \
        catch_df.loc[mask_hhooks, "EffortValue"] * 100.0

    mask_ll_days = mask_ll & catch_df["EffortType"].isin(
        ["DAYS", "FDAYS", "D.FISH", "D.AT SEA", "SETS", "NO.SETS"])
    catch_df.loc[mask_ll_days, "Standard_Effort"] = \
        catch_df.loc[mask_ll_days, "EffortValue"] * HOOKS_PER_DAY

    mask_ps_sets = mask_ps & catch_df["EffortType"].isin(
        ["SETS", "NO.SETS", "SUC.SETS", "DAYS", "FDAYS", "D.FISH", "D.AT SEA"])
    catch_df.loc[mask_ps_sets, "Standard_Effort"] = \
        catch_df.loc[mask_ps_sets, "EffortValue"]

    mask_hours = mask_ps & catch_df["EffortType"].isin(
        ["FISH.HOUR", "FHOURS", "HOURS", "STDHR", "Hours Searched"])
    catch_df.loc[mask_hours, "Standard_Effort"] = \
        catch_df.loc[mask_hours, "EffortValue"] / HOURS_PER_SET

    # ------------------------------------------------------------------
    # DQ fix: verified historical reporting errors (2026-09-17)
    # BLZ "extra-zero" effort errors were confirmed against neighbouring
    # years (see DataQuality_Scan_FlagGearYear.csv):
    #   BLZ PS 2020/2021/2022 (ICCAT, NO.SETS): 175k/147k/172k -> /1000
    #   BLZ LL 2013 (ICCAT, NO.HOOKS): 27,713,000 -> /100 (0.84x of 2012)
    #   BLZ LL 2013 (IATTC, NO.HOOKS):  5,130,550 -> /10  (1.56x of 2012)
    # Other >10x jumps were reviewed and left unchanged (real fleet changes
    # or coordinate-coverage artefacts), with a detection log printed below.
    # ------------------------------------------------------------------
    _dq_fixes = [
        (2020, "BLZ", "PS", "ICCAT", 1000.0),
        (2021, "BLZ", "PS", "ICCAT", 1000.0),
        (2022, "BLZ", "PS", "ICCAT", 1000.0),
        (2013, "BLZ", "LL", "ICCAT", 100.0),
        (2013, "BLZ", "LL", "IATTC", 10.0),
    ]
    for _yr, _fl, _gr, _org, _div in _dq_fixes:
        _m = ((catch_df["Year"] == _yr) & (catch_df["Flag"] == _fl)
              & (catch_df["Gear"] == _gr) & (catch_df["Organization"] == _org))
        _n = int(_m.sum())
        if _n:
            catch_df.loc[_m, "Standard_Effort"] = catch_df.loc[_m, "Standard_Effort"] / _div
            print(f"[DQ] fix applied: {_yr} {_fl} {_gr} {_org} /{_div:.0f} ({_n} rows)")

    # detection log only (no modification): remaining >10x effort jumps
    _ag = catch_df.groupby(["Year", "Flag", "Gear"]).agg(
        eff=("Standard_Effort", "sum"), cat=("Total_Catch", "sum")
    ).reset_index().sort_values(["Flag", "Gear", "Year"])
    _ag["eff_prev"] = _ag.groupby(["Flag", "Gear"]).eff.shift(1)
    _ag["cat_prev"] = _ag.groupby(["Flag", "Gear"]).cat.shift(1)
    _ag["is_jump"] = (
        (_ag.eff > _ag.eff_prev * 10) & (_ag.eff > 1000)
        & (_ag.cat_prev > 0) & (_ag.cat > 0)
        & (_ag.cat < _ag.cat_prev * 2) & (_ag.cat > _ag.cat_prev * 0.5)
    )
    _nj = int(_ag.is_jump.sum())
    print(f"[DQ] remaining >10x effort jumps (kept, reviewed): {_nj} group-years")


    
    catch_df["Nat_Total_Effort"] = catch_df.groupby(
        ["Year", "Flag", "Gear"])["Standard_Effort"].transform("sum")
    catch_df["Nat_Total_Catch"] = catch_df.groupby(
        ["Year", "Flag", "Gear"])["Total_Catch"].transform("sum")

    catch_df["Effort_Prop"] = np.where(
        catch_df["Nat_Total_Effort"] > 0,
        catch_df["Standard_Effort"] / catch_df["Nat_Total_Effort"],
        np.where(catch_df["Nat_Total_Catch"] > 0,
                 catch_df["Total_Catch"] / catch_df["Nat_Total_Catch"], 0.0)
    )
    catch_df["Effort_Prop"] = catch_df["Effort_Prop"].fillna(0.0)

    
    # Drop Organization from fleet to avoid merge conflict (catch data already has it)
    _catch_cols = list(catch_df.columns)
    df_fleet_merge = df_fleet.drop(columns=["Organization"], errors="ignore")
    catch_df = catch_df.merge(df_fleet_merge, on=["Year", "Flag", "Gear"], how="left")

    # 2026-09-20 FIX: the fleet file carries up to two Sector rows per
    # (Year, Flag, Gear) (I and APW); the merge above duplicated every catch
    # record (catch/effort kept twice, GHG split between the sector copies),
    # which inflated species catch and CPUE numerators by ~30% in multi-sector
    # flags and distorted CEI. Collapse back to ONE row per catch record:
    # catch/effort kept once, GHG and process columns summed over the sectors.
    _fleet_cols = [c for c in catch_df.columns if c not in _catch_cols]
    _dup_key = ["Year", "Flag", "Gear", "squaretypecode", "lat", "lon",
                "EffortType", "Organization"]
    _agg = {c: "first" for c in _catch_cols if c != "Organization"}
    _agg.update({c: "sum" for c in _fleet_cols if c != "Sector"})
    catch_df = catch_df.groupby(_dup_key, as_index=False, dropna=False).agg(_agg)
    catch_df["Sector"] = "ALL"
    catch_df["Nat_GHG_median"] = catch_df["Nat_GHG_median"].fillna(0)

    
    
    
    catch_df["GHG_emissions_median"] = (
        catch_df["Nat_GHG_median"] * catch_df["Effort_Prop"]
    )

    # 2026-09-21 FIX: allocate the per-process fleet columns with the same
    # Effort_Prop weights as the total (they were previously copied onto every
    # record unallocated); Nat_* columns remain fleet-level values.
    _proc_bases = ["Fuel_CO2", "Fuel_CH4", "Fuel_N2O", "Fuel_WTT",
                   "Build", "Maint", "Gear_Build", "Gear_Maint",
                   "Refrig", "Bait"]
    for _pb in _proc_bases:
        for _sfx in ("_median", "_p5", "_p95"):
            _pc = _pb + _sfx
            if _pc in catch_df.columns:
                catch_df[_pc] = (catch_df[_pc] * catch_df["Effort_Prop"]).fillna(0.0)

    # CEI
    valid_catch = catch_df["Total_Catch"] > 0
    catch_df["Grid_CEI"] = np.where(
        valid_catch,
        catch_df["GHG_emissions_median"] / catch_df["Total_Catch"],
        np.nan
    )

    # CPUE
    catch_df["CPUE"] = np.where(
        catch_df["Standard_Effort"] > 0,
        catch_df["Total_Catch"] / catch_df["Standard_Effort"],
        np.nan
    )

    
    for sp in species_cols:
        prop_col = sp.replace("_Tonnes", "_Prop")
        catch_df[prop_col] = np.where(
            valid_catch,
            catch_df[sp] / catch_df["Total_Catch"],
            0.0
        )

    catch_df["Dominant_Species"] = np.where(
        valid_catch,
        catch_df[species_cols].idxmax(axis=1).str.replace("_Tonnes", ""),
        "None"
    )

    return catch_df


# ============================================================

# ============================================================

def run_gsa_analysis(df, pm_dict, end_year=2025,
                     n_simulations=2000, random_seed=42,
                     lookup_data_power=None, lookup_data_alpha=None,
                     top_n=5):
    '\n    \u5168\u5c40\u654f\u611f\u6027\u5206\u6790:\n      1. N \u6b21\u8499\u7279\u5361\u6d1b\u91c7\u6837\uff0c\u6240\u6709\u53c2\u6570\u6309\u5206\u5e03\u53d8\u5316\n      2. \u8bad\u7ec3 Random Forest \u4ee3\u7406\u6a21\u578b\n      3. SHAP \u5206\u6790 \u2192 \u63d0\u53d6 Top N \u53c2\u6570\n    '
    print(f"\n{'=' * 60}")
    print(f"  GSA: \u5168\u5c40\u654f\u611f\u6027\u5206\u6790 ({n_simulations} MC, Top {top_n})")
    print(f"{'=' * 60}")

    # Use the production MC engine for every target, including fuel classes,
    # PMM donors, construction/maintenance events, ghost retirement and share5.
    years, draws, raw = run_monte_carlo_lca(
        df, pm_dict, end_year=end_year, start_year=end_year,
        n_simulations=n_simulations, random_seed=random_seed,
        lookup_data_power=lookup_data_power, lookup_data_alpha=lookup_data_alpha,
        important_params=None, return_draws=True)
    feature_names = {
        "T_map": "T_map_Mult", "SFCbase": "SFCbase_Mult", "H_map": "H_map_Mult",
        "LF_move": "LF_Move_Mult", "LF_work": "LF_Work_Mult", "AUX": "AUX_Ratio_Mult",
        "EF_Build": "EF_Build_Mult", "EF_Maint": "EF_Maint_Mult", "Gear": "Gear_Intensity_Mult",
        "Alpha": "Alpha_Mult", "R22": "R22_Leak_Mult", "Power": "Power_Discount_Mult",
        "Bait_EF": "Bait_EF_Mult", "Bait_Wt": "Bait_Wt_Mult"}
    X = draws.rename(columns=feature_names)
    process_names = ["Fuel_CO2", "Fuel_CH4", "Fuel_N2O", "Fuel_WTT", "Build",
                     "Maint", "Gear", "Bait", "Refrig", "Total"]
    targets_by_process = {p: (raw["Gear_Build"][:, -1] + raw["Gear_Maint"][:, -1]
                             if p == "Gear" else raw[p][:, -1]) for p in process_names}
    pd.DataFrame(targets_by_process).to_csv(os.path.join(OUTPUT_DIR, "GSA_Targets_Per_Process.csv"), index=False)

    
    X.to_csv(os.path.join(OUTPUT_DIR, "GSA_Input_Features.csv"), index=False)
    pd.Series(targets_by_process["Total"], name="Total_GHG").to_csv(
        os.path.join(OUTPUT_DIR, "GSA_Target_GHG.csv"), index=False, header=True)
    print(f"  GSA \u6570\u636e\u5df2\u4fdd\u5b58: GSA_Input_Features.csv, GSA_Target_GHG.csv")

    # ================================================================
    
    # ================================================================
    print('\n[GSA] \u5206\u8fc7\u7a0b SHAP \u5206\u6790 (per-process Top-2):')
    print(f"  {'Process':<12s} {'Top-1 Param':<22s} {'SHAP':>8s}  {'Top-2 Param':<22s} {'SHAP':>8s}")
    print(f"  {'-'*12} {'-'*22} {'-'*8}  {'-'*22} {'-'*8}")

    gsa_top_params = {}  # process → [param1_code, param2_code]

    
    param_code_map = {
        "T_map_Mult": "T_map", "SFCbase_Mult": "SFCbase",
        "H_map_Mult": "H_map",
        "LF_Move_Mult": "LF_move", "LF_Work_Mult": "LF_work",
        "AUX_Ratio_Mult": "AUX",
        "EF_Build_Mult": "EF_Build", "EF_Maint_Mult": "EF_Maint",
        "Gear_Intensity_Mult": "Gear", "Alpha_Mult": "Alpha",
        "R22_Leak_Mult": "R22", "Power_Discount_Mult": "Power",
        "Bait_EF_Mult": "Bait_EF", "Bait_Wt_Mult": "Bait_Wt",
    }

    for proc in process_names:
        y_p = pd.Series(targets_by_process[proc])
        rf_p = RandomForestRegressor(n_estimators=200, max_depth=12,
                                     random_state=random_seed, n_jobs=-1)
        rf_p.fit(X, y_p)
        explainer_p = shap.TreeExplainer(rf_p)
        shap_p = explainer_p.shap_values(X)
        imp_p = np.abs(shap_p).mean(axis=0)
        ranked_p = sorted(zip(X.columns, imp_p), key=lambda x: x[1], reverse=True)

        top2_names = [ranked_p[0][0], ranked_p[1][0]]
        top2_codes = [param_code_map.get(n, n) for n in top2_names]
        gsa_top_params[proc] = top2_codes

        print(f"  {proc:<12s} {top2_names[0]:<22s} {ranked_p[0][1]/1e6:>7.3f}Mt  "
              f"{top2_names[1]:<22s} {ranked_p[1][1]/1e6:>7.3f}Mt")

    
    all_important = set()
    for codes in gsa_top_params.values():
        all_important.update(codes)
    all_important.discard("Total")  

    print(f"\n  MC \u9700\u91c7\u6837\u7684\u53c2\u6570 ({len(all_important)} \u4e2a): {sorted(all_important)}")
    print(f"  \u672a\u8fdb\u5165\u4efb\u4f55\u8fc7\u7a0b Top-2 \u7684\u53c2\u6570\u4f7f\u7528 Best \u503c (\u4e58\u6570=1.0)")

    
    gsa_proc_csv = os.path.join(OUTPUT_DIR, "GSA_Per_Process_Top2.csv")
    pd.DataFrame([
        {"Process": p, "Top1": gsa_top_params[p][0], "Top2": gsa_top_params[p][1]}
        for p in process_names
    ]).to_csv(gsa_proc_csv, index=False)
    print(f"  \u5206\u8fc7\u7a0b Top-2 \u5df2\u4fdd\u5b58: {gsa_proc_csv}")

    # SHAP
    y_total = pd.Series(targets_by_process["Total"])
    rf_total = RandomForestRegressor(n_estimators=200, max_depth=12,
                                     random_state=random_seed, n_jobs=-1)
    rf_total.fit(X, y_total)
    explainer_total = shap.TreeExplainer(rf_total)
    shap_values = explainer_total.shap_values(X)
    importance = np.abs(shap_values).mean(axis=0)
    ranked = sorted(zip(X.columns, importance), key=lambda x: x[1], reverse=True)

    feature_display_names = {
        "T_map_Mult": "Days at Sea (T_map)",
        "SFR_Mult": "Specific Fuel Consumption",
        "LF_Move_Mult": "Load Factor (Transit)",
        "LF_Work_Mult": "Load Factor (Fishing)",
        "LF_Aux_Mult": "Aux Engine Load Factor",
        "AUX_Ratio_Mult": "Aux Power Ratio",
        "EF_Build_Mult": "Build Emission Factor",
        "EF_Maint_Mult": "Maintenance Emission Factor",
        "Gear_Intensity_Mult": "Gear Intensity",
        "Alpha_Mult": "Fishing Time Fraction (alpha)",
        "R22_Leak_Mult": "Refrigerant Leak Rate",
        "Power_Discount_Mult": "Historical Power Discount",
    }
    X_display = X.rename(columns=feature_display_names)

    # Python exports the bridge; scientific plots are rendered exclusively in R.
    pd.DataFrame(shap_values, columns=X.columns).to_csv(
        os.path.join(OUTPUT_DIR, "GSA_SHAP_Values.csv"), index=False)
    pd.DataFrame(ranked, columns=["Parameter", "Mean_SHAP"]).to_csv(
        os.path.join(OUTPUT_DIR, "GSA_SHAP_Importance.csv"), index=False)

    top_params = pd.DataFrame(ranked[:top_n],
                              columns=["Parameter", "Mean_SHAP"])
    top_params["Mean_SHAP_Mt"] = top_params["Mean_SHAP"] / 1e6
    top_csv = os.path.join(OUTPUT_DIR, "GSA_Top5_Parameters.csv")
    top_params.to_csv(top_csv, index=False)
    print(f"  Top {top_n} \u53c2\u6570\u5df2\u4fdd\u5b58: {top_csv}")

    return X, y_total, rf_total, ranked[:top_n], gsa_top_params, all_important


# ============================================================

# ============================================================

# ============================================================

# ============================================================

PARAMETER_USAGE = {
    
    "T_map_DAS":             'Section 4: resolve_t_map() \u2014 \u5e74\u51fa\u6d77\u5929\u6570 (Flag\xd7Gear\xd7Sector\xd7Ocean)',
    "H_map_Day":             'Section 4: resolve_hours() \u2014 \u4e3b\u673a\u65e5\u8fd0\u884c\u5c0f\u65f6 (I=24h, APW=12h, PS=4h)',
    "H_map_Aux":             "Section 4: resolve_hours(engine='aux') \u2014 \u8f85\u673a\u65e5\u8fd0\u884c\u5c0f\u65f6",
    
    "LF_MAIN_MOVE":          "Section 4: resolve_lf(phase='move') \u2014 >=12m\u4e3b\u673a\u822a\u884c\u8d1f\u8377 (0.80, R22)",
    "LF_MAIN_WORK":          "Section 4: resolve_lf(phase='work') \u2014 >=12m\u4e3b\u673a\u4f5c\u4e1a\u8d1f\u8377 (0.20, R22)",
    "LF_AUX":                "Section 4: resolve_lf(phase='aux') \u2014 \u8f85\u673a\u8d1f\u8377 Uniform(0.30,0.50)",
    "LF_MAIN_MOVE_GASOLINE": "Section 4: resolve_lf(phase='move') \u2014 <12m\u6c7d\u6cb9\u822a\u884c\u8d1f\u8377 (0.80)",
    "LF_MAIN_WORK_GASOLINE": "Section 4: resolve_lf(phase='work') \u2014 <12m\u6c7d\u6cb9\u4f5c\u4e1a\u8d1f\u8377 (0.201, EPA)",
    "HAS_AUX_ENGINE":        'Section 4: \u8f85\u673a\u6807\u8bb0 \u2014 >=12m=1, <12m=0',
    "ENGINE_TYPE_*":         'Section 4: get_engine_type() \u2014 MSD/SSD/GASOLINE \u53d1\u52a8\u673a\u7c7b\u578b',
    "FUEL_TYPE_*":           'Section 4: get_fuel_type() \u2014 MDO/HFO/GASOLINE \u71c3\u6599\u7c7b\u578b',
    "SFC_BASE_*":            'Section 4: get_sfcbase() \u2014 IMO SFCbase \u57fa\u51c6\u6cb9\u8017\u7387 (g/kWh)',
    "SFOC_LOAD_COEFF_A":     'Section 4: apply_sfoc_formula() \u2014 SFOC\u4e8c\u6b21\u9879\u7cfb\u6570 (0.455) [v3.0 \u542f\u7528]',
    "SFOC_LOAD_COEFF_B":     'Section 4: apply_sfoc_formula() \u2014 SFOC\u4e00\u6b21\u9879\u7cfb\u6570 (-0.71) [v3.0 \u542f\u7528]',
    "SFOC_LOAD_COEFF_C":     'Section 4: apply_sfoc_formula() \u2014 SFOC\u5e38\u6570\u9879 (1.28) [v3.0 \u542f\u7528]',
    "SFOC_LOAD_APPLICABILITY":'Section 4: SFOC-\u8d1f\u8377\u516c\u5f0f\u9002\u7528\u8303\u56f4 \u2014 >=12m\u67f4\u6cb9\u673a=1, <12m\u6c7d\u6cb9=0',
    "SFR_Gasoline_4STROKE":  'Section 4: resolve_sfr() \u2014 <12m \u6c7d\u6cb9 EPA \u76f4\u63a5 SFR (0.000319 t/kWh)',
    "EF_CO2_HFO":            'Section 6a: HFO CO2 \u6392\u653e\u56e0\u5b50 (3.114 tCO2/tFuel)',
    "EF_CO2_MDO":            'Section 6a: MDO CO2 \u6392\u653e\u56e0\u5b50 (3.206 tCO2/tFuel)',
    "EF_CO2_Gasoline":       'Section 6a: \u6c7d\u6cb9 CO2 \u6392\u653e\u56e0\u5b50 (3.158 tCO2/tFuel)',
    "EF_CH4_SSD":            "Section 6b: SSD CH4 EF (0.010 g/kWh, IMO Table 58)",
    "EF_CH4_MSD":            "Section 6b: MSD CH4 EF (0.010 g/kWh, IMO Table 58)",
    "EF_CH4_AUX":            'Section 6b: \u8f85\u673a CH4 EF (0.010 g/kWh, IMO Table 58)',
    "EF_CH4_GASOLINE_*":    'Section 6b: \u6c7d\u6cb9 CH4 EF (g/kgFuel, EPA 2025)',
    "EF_N2O_SSD_HFO":       "Section 6c: SSD/HFO N2O EF (0.031 g/kWh, IMO Table 59)",
    "EF_N2O_SSD_MDO":       "Section 6c: SSD/MDO N2O EF (0.030 g/kWh, IMO Table 59)",
    "EF_N2O_MSD_MDO":       "Section 6c: MSD/MDO N2O EF (0.030 g/kWh, IMO Table 59)",
    "EF_N2O_AUX_MDO":       'Section 6c: \u8f85\u673a/MDO N2O EF (0.036 g/kWh, IMO Table 59)',
    "EF_N2O_GASOLINE":      'Section 6c: \u6c7d\u6cb9 N2O EF (0.04 g/kgFuel, EPA 2025)',
    "GWP_CH4_100YR":         'Section 6b: CH4 \u5168\u7403\u53d8\u6696\u6f5c\u52bf (28.5)',
    "GWP_N2O_100YR":         'Section 6c: N2O \u5168\u7403\u53d8\u6696\u6f5c\u52bf (273)',
    "FC_LOOKUP":             'Section 6: \u71c3\u6cb9\u6548\u7387\u65f6\u95f4\u7cfb\u6570 (1950\u21921.21, 2016\u21920.99)',
    
    "AUX_POWER_RATIO_FISHING":'Section 4: resolve_aux_power_ratio() \u2014 \u6e14\u8239=0.39 (R56 2010\u4e16\u754c\u8239\u961f)',
    "AUX_POWER_RATIO_TP":    'Section 4: resolve_aux_power_ratio() \u2014 \u8f6c\u8fd0\u8239=0.23 (\u4ef6\u6742\u8d27\u8239)',
    "AUX_POWER_RATIO_SA":    'Section 4: resolve_aux_power_ratio() \u2014 \u8f85\u52a9\u8239=0.35 (\u5176\u4ed6)',
    
    "EF_BUILD_PS_STEEL":     'Section 4: EF_Build \u2014 PS \u94a2\u8239\u5efa\u9020 (2.421 kgCO2/kg)',
    "EF_BUILD_PS_WOOD":      'Section 4: EF_Build \u2014 PS/LL \u6728\u8239\u5efa\u9020 (0.578)',
    "EF_BUILD_LL_STEEL":     'Section 4: EF_Build \u2014 LL \u94a2\u8239\u5efa\u9020 (1.956)',
    "EF_BUILD_LL_WOOD":      'Section 4: EF_Build \u2014 LL \u6728\u8239\u5efa\u9020 (\u540c PS_WOOD)',
    "EF_BUILD_TS":            'Section 4: EF_Build \u2014 TS/TP \u5efa\u9020 (\u540c PS_STEEL 2.421)',
    "EF_MAINT_PS_STEEL":     'Section 4: EF_Maint \u2014 PS \u94a2\u8239\u7ef4\u62a4 (6.744)',
    "EF_MAINT_PS_WOOD":      'Section 4: EF_Maint \u2014 PS/LL \u6728\u8239\u7ef4\u62a4 (1.289)',
    "EF_MAINT_LL_STEEL":     'Section 4: EF_Maint \u2014 LL \u94a2\u8239\u7ef4\u62a4 (4.45)',
    "EF_MAINT_LL_WOOD":      'Section 4: EF_Maint \u2014 LL \u6728\u8239\u7ef4\u62a4 (\u540c PS_WOOD)',
    "EF_MAINT_TS":            'Section 4: EF_Maint \u2014 TS/TP \u7ef4\u62a4 (\u540c PS_STEEL 6.744)',
    "LIFESPAN_HULL":         'Section 4: \u8239\u4f53\u5bff\u547d (30\u5e74) \u2014 \u4ec5\u7528\u4e8e\u4fe1\u606f, \u5efa\u9020\u4ec5\u7b97 age==0',
    
    "GEAR_INT_PS":           'Section 4: PS \u7f51\u5177\u5f3a\u5ea6 (t/m)',
    "GEAR_INT_LL":           'Section 4: LL \u7f51\u5177\u5f3a\u5ea6 (t/m)',
    "GEAR_MATERIAL_NYLON_PS":'Section 6: PS\u5c3c\u9f99\u5360\u6bd4 0.739 (PA6+EVA\u5408\u5e76)',
    "GEAR_MATERIAL_STEEL_PS":'Section 6: PS\u94a2\u5360\u6bd4 0.261',
    "GEAR_MATERIAL_NYLON_LL":'Section 6: LL\u5c3c\u9f99\u5360\u6bd4 0.739 (\u540cPS)',
    "GEAR_MATERIAL_STEEL_LL":'Section 6: LL\u94a2\u5360\u6bd4 0.261 (\u540cPS)',
    "EMISSION_FACTOR_NYLON_PA6": 'Section 6: \u5c3c\u9f99\u7f51\u5177 EF (9.885 kgCO2/kg)',
    "EMISSION_FACTOR_STEEL_GEAR": 'Section 6: \u6e14\u5177\u94a2 EF (3.07 kgCO2/kg)',
    "LIFESPAN_GEAR_PS":      'Section 4: PS \u7f51\u5177\u5bff\u547d (5\u5e74)',
    "LIFESPAN_GEAR_LL":      'Section 4: LL \u7f51\u5177\u5bff\u547d (5\u5e74)',
    "MAINTENANCE_RATE_GEAR_PS": 'Section 4: PS \u7f51\u5177\u5e74\u5ea6\u66f4\u6362\u7387 (0.25)',
    "MAINTENANCE_RATE_GEAR_LL": 'Section 4: LL \u7f51\u5177\u5e74\u5ea6\u66f4\u6362\u7387 (0.25)',
    
    "BAIT_WEIGHT_PER_HOOK_KG": 'Section 6j: LL \u5355\u94a9\u9975\u91cd (0.1 kg/hook)',
    "EMISSION_FACTOR_BAIT":  'Section 6j: \u9975\u6599 EF (1.606 kgCO2/kg bait)',
    "HOOKS_PER_DAY":         'Section 6j: LL \u65e5\u5747\u6295\u94a9\u6570 (3000 hooks/day)',
    
    "R22_GWP":               "Section 6i: R22 GWP-100 (1810)",
    "R22_LEAK_DISTANT_PS":   'Section 4: \u8fdc\u6d0b PS \u5e74\u6cc4\u6f0f\u7387 (500 kg/yr)',
    "R22_LEAK_COASTAL_PS":   'Section 4: \u6cbf\u6d77 PS \u5e74\u6cc4\u6f0f\u7387 (10 kg/yr)',
    # Section K — GT→LSW
    "LDT_GT_RATIO_FISHING":  'Section 2: convert_gt_to_lsw() \u2014 \u6e14\u8239 GT\u2192LSW (0.859)',
    "LDT_GT_RATIO_CARGO_REF":'Section 2: convert_gt_to_lsw() \u2014 TS/TP \u8d27\u8239 GT\u2192LSW (0.287)',
    
    "MATERIAL_RATIO_STEEL":  '\u3010\u5df2\u5e9f\u5f03\u3011\u4e0d\u518d\u6309 \u94a285%/\u94f8\u94c110%/\u94dc5% \u62c6\u5206 LSW, \u76f4\u63a5 LSW\xd7EF',
    "MATERIAL_RATIO_ENGINE": '\u3010\u5df2\u5e9f\u5f03\u3011\u540c\u4e0a',
    "MATERIAL_RATIO_COPPER": '\u3010\u5df2\u5e9f\u5f03\u3011\u540c\u4e0a',
    "LIFESPAN_ENGINE":       '\u3010\u5df2\u5e9f\u5f03\u3011\u4e0d\u518d\u5355\u72ec\u8ba1\u7b97\u53d1\u52a8\u673a/\u94dc\u7cfb\u7edf\u6362\u4ee3',
    "LIFESPAN_COPPER":       '\u3010\u5df2\u5e9f\u5f03\u3011\u540c\u4e0a',
}


def print_parameter_usage(pm_dict):
    '\u6253\u5370\u53c2\u6570\u4f7f\u7528\u8bf4\u660e\u8868\uff0c\u6807\u6ce8\u6bcf\u4e2a\u53c2\u6570\u5728\u6a21\u578b\u4e2d\u7684\u4f7f\u7528\u4f4d\u7f6e\u6216\u5e9f\u5f03\u72b6\u6001\u3002'
    print("\n" + "=" * 70)
    print("  PARAMETER USAGE REPORT")
    print("=" * 70)
    print(f"  {'Status':<12s} {'Param_Code':<30s} {'Location'}")
    print(f"  {'-'*12} {'-'*30} {'-'*40}")

    all_codes = set()
    for entries in pm_dict["by_code"].values():
        for e in entries:
            code = str(e.get("Param_Code", "")).strip()
            if code and code != "NAN":
                all_codes.add(code)

    used_count = 0
    deprecated_count = 0
    undocumented_count = 0

    for code in sorted(all_codes):
        if code in PARAMETER_USAGE:
            usage = PARAMETER_USAGE[code]
            if usage.startswith('\u3010\u672a\u4f7f\u7528\u3011'):
                status = "NOT USED"
            elif usage.startswith('\u3010\u5df2\u5e9f\u5f03\u3011'):
                status = "DEPRECATED"
                deprecated_count += 1
            else:
                status = "IN USE"
                used_count += 1
        else:
            status = "UNDOCUMENTED"
            usage = '(\u672a\u5728 PARAMETER_USAGE \u4e2d\u8bb0\u5f55, \u53ef\u80fd\u4ec5\u5728 Prior_Matrix \u4e2d\u5b9a\u4e49)'
            undocumented_count += 1

        print(f"  {status:<12s} {code:<30s} {usage[:60]}")

    print(f"\n  Summary: {used_count} in use, {deprecated_count} deprecated, "
          f"{undocumented_count} undocumented")
    print(f"  Note: SFOC_LOAD_* coefficients now in use (v3.0 SFOC methodology).")
    print("=" * 70)


if __name__ == "__main__":
    print("=" * 70)
    print('  main_v3.py \u2014 \u5168\u751f\u547d\u5468\u671f LCA GHG \u6392\u653e\u6a21\u578b')
    print('  \u57fa\u4e8e Prior_Matrix \u53c2\u6570\u5316')
    print("=" * 70)

    
    TARGET_YEAR = 2025
    N_SIMULATIONS = 500
    N_GSA_SIMULATIONS = 2000
    TOP_N_GSA = 5
    SEED = 42

    
    pm_dict = load_prior_matrix(PRIOR_MATRIX_PATH)

    
    df_vessels, pool_dict = run_imputation_pipeline(
        VESSEL_REGISTRY_PATH, pm_dict, random_seed=SEED
    )

    # ---- Step 2: GT→LSW ----
    df_vessels = convert_gt_to_lsw(df_vessels, pm_dict)

    
    
    df_vessels = impute_builtdate_deterministic(df_vessels, pool_dict)

    
    
    
    df_ghosts = build_ghost_vessels(df_vessels, PNAS_POWER_PATH, CATCH_ALLOCATION_PATH,
                                   qc_path=os.path.join(OUTPUT_DIR, "Ghost_Fleet_Capacity_QC.csv"))
    if df_ghosts is not None:
        df_ghosts.to_csv(os.path.join(OUTPUT_DIR, "Ghost_Fleet_Reconstructed.csv"), index=False, encoding="utf-8-sig")

    
    df_vessels = assign_operational_params(df_vessels, pm_dict)

    
    print('\n[Init] \u521d\u59cb\u5316 PNAS \u529f\u7387\u6298\u6263 & Alpha \u67e5\u8be2\u8868...')
    lookup_power = init_power_discount_lookup(PNAS_POWER_PATH, baseline_year=2015)
    lookup_alpha = init_time_profile_lookup(PNAS_POWER_PATH, verbose=False)

    
    print("\n" + "=" * 60)
    print('  STAGE 1: GSA \u2014 \u5206\u8fc7\u7a0b\u53c2\u6570\u654f\u611f\u6027\u5206\u6790')
    print("=" * 60)
    gsa_X, gsa_y, gsa_rf, gsa_ranked, gsa_top_params, important_params = \
        run_gsa_analysis(
            df=df_vessels,
            pm_dict=pm_dict,
            end_year=TARGET_YEAR,
            n_simulations=N_GSA_SIMULATIONS,
            random_seed=SEED,
            lookup_data_alpha=lookup_alpha,
            lookup_data_power=lookup_power,
            top_n=TOP_N_GSA,
        )

    
    if df_ghosts is not None and len(df_ghosts) > 0:
        df_ghosts = assign_operational_params(df_ghosts, pm_dict)
        df_vessels["Retire_Year"] = 9999
        df_vessels = pd.concat([df_vessels, df_ghosts], ignore_index=True, sort=False)
        print(f"[Ghost] fleet augmented: {len(df_ghosts):,} ghosts -> "
              f"{len(df_vessels):,} vessels total")

    
    print("\n" + "=" * 60)
    print('  STAGE 2: MC LCA \u2014 \u4ec5\u91c7\u6837 GSA \u5173\u952e\u53c2\u6570')
    print("=" * 60)
    years, df_fleet, df_global, df_org, df_org_cat, global_res, _ = run_monte_carlo_lca(
        df=df_vessels,
        pm_dict=pm_dict,
        end_year=TARGET_YEAR,
        n_simulations=N_SIMULATIONS,
        random_seed=SEED,
        lookup_data_power=lookup_power,
        lookup_data_alpha=lookup_alpha,
        important_params=important_params,
        draw_export_path=os.path.join(OUTPUT_DIR, "GHG_LCA_Total_Draws.npz"),
        multi_mode_fuel=True,
    )

    
    df_spatial = process_catch_and_cei(CATCH_ALLOCATION_PATH, df_fleet, pm_dict)

    
    print("\n" + "=" * 60)
    print("  EXPORT RESULTS")
    print("=" * 60)

    df_global.to_csv(os.path.join(OUTPUT_DIR, "Base_1_LCA_Global_Process.csv"),
                     index=False, encoding="utf-8-sig")
    print(f"  Base_1_LCA_Global_Process.csv — {len(df_global)} rows")

    df_fleet.to_csv(os.path.join(OUTPUT_DIR, "Base_2_Fleet_GHG.csv"),
                    index=False, encoding="utf-8-sig")
    print(f"  Base_2_Fleet_GHG.csv — {len(df_fleet)} rows")

    df_spatial.to_csv(os.path.join(OUTPUT_DIR, "Base_3_Spatial_Grid_Enriched.csv"),
                      index=False, encoding="utf-8-sig")
    print(f"  Base_3_Spatial_Grid_Enriched.csv — {len(df_spatial)} rows")

    df_org.to_csv(os.path.join(OUTPUT_DIR, "Base_4_Organization_GHG.csv"),
                  index=False, encoding="utf-8-sig")
    print(f"  Base_4_Organization_GHG.csv — {len(df_org)} rows")

    df_org_cat.to_csv(os.path.join(OUTPUT_DIR, "Base_5_Org_Fleet_GHG.csv"),
                      index=False, encoding="utf-8-sig")
    print(f"  Base_5_Org_Fleet_GHG.csv — {len(df_org_cat)} rows")

    
    print("\n" + "=" * 60)
    print("  SUMMARY — Global GHG (Median)")
    print("=" * 60)
    last_year = df_global[df_global["Year"] == TARGET_YEAR]
    if len(last_year) > 0:
        row = last_year.iloc[0]
        total = row.get("Total_median", 0)
        print(f"  Year {TARGET_YEAR} Total GHG: {total / 1e6:.2f} Mt CO2eq")
        for p in ["Fuel_CO2", "Fuel_CH4", "Fuel_N2O", "Fuel_WTT", "Build", "Maint",
                   "Gear_Build", "Gear_Maint", "Refrig", "Bait"]:
            key = f"{p}_median"
            if key in row:
                print(f"    {p:15s}: {row[key] / 1e6:10.3f} Mt")

    print("\n" + "=" * 70)
    print('  DONE \u2014 main_v3.py \u5168\u751f\u547d\u5468\u671f LCA \u5b8c\u6210')
    print("=" * 70)

    
    print_parameter_usage(pm_dict)
