import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')

# ============================================================
# Step 1 & 2: Historical Force Evolution Query Table -- Data Pre-processing and Query Functions
# Based PNAS (Rousseau et al., 2019) Real History Fleet Physical Parameters
# ============================================================

# ---- Flag Annotations ----
# vessel Data Flag And now were united ISO3 Code (flag_utils.py)
# No conversion required — Use direct as a query key

# ---- Gear Map ----
# Will vessel Data VesselType (LL, PS, TS) Map to CSV Medium Gear Category
GEAR_MAPPING = {
    'LL': 'Lines_Longlines',
    'PS': 'Seine_Purse_Seine',
    'TS': 'Trawl_Midwater_or_Unsp',
}

# ---- Length(m) -> CSV Length_Category Map ----
def map_length_to_csv_category(length_m):
    """, the value will be added Length(m) Map to CSV Medium Length_Category Boxes"""
    if length_m < 6:
        return '6-12m'   # Take the bottom: A very small ship is kept in the lowest gear
    elif length_m < 12:
        return '6-12m'
    elif length_m < 24:
        return '12-24m'
    elif length_m < 50:
        return '24-50m'
    else:
        return 'Over 50m'


# ============================================================
# Main pre-processing function
# ============================================================

def build_power_discount_lookup(csv_path, baseline_year=2015, verbose=True):
    """
    Build"Historical Force Evolution Query Table". 

    parameter
    ----------
    csv_path : str
        PNAS Historical fleet data CSV Paths of the. 
    baseline_year : int
        Base year (default 2015), For extraction of modern baseline power. 
    verbose : bool
        Whether to print pre-processing logs. 

    Back
    -------
    lookup : dict
        Main Query Dictionary, Keys (Country_ISO3, Gear_CSV, Length_Category, Year), 
        Value is Power_Discount_Factor. 
    fallback_global : dict
        Global Average Dictionary, Keys (Gear_CSV, Length_Category, Year). 
    fallback_group_nearest : dict
        Dictionary by group for the most recent year, Keys (Country_ISO3, Gear_CSV, Length_Category), 
        Value is (years_array, factors_array) Group, For linear plugs or nearest neighbours. 
    fallback_global_nearest : dict
        The latest year of global dimensions, Keys (Gear_CSV, Length_Category). 
    """
    if verbose:
        print(f"[Pre-treatment] Reading PNAS Historical fleet data: {csv_path} ...")

    df_raw = pd.read_csv(csv_path, skiprows=[1])

    # ---- Clean ----
    for col in ['NV', 'P', 'Year']:
        df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce')
    df_raw['Country'] = df_raw['Country'].astype(str).str.strip()
    df_raw['Gear'] = df_raw['Gear'].astype(str).str.strip()
    df_raw['Length_Category'] = df_raw['Length_Category'].astype(str).str.strip()

    # Deleting invalid lines (NV <= 0 or P <= 0)
    df = df_raw[(df_raw['NV'] > 0) & (df_raw['P'] > 0)].copy()

    # ---- Calculating the average real power of a single ship ----
    df['Avg_Power'] = df['P'] / df['NV']

    if verbose:
        print(f"   Number of valid data lines: {len(df):,}")
        print(f"   Year span: {int(df['Year'].min())} - {int(df['Year'].max())}")
        print(f"   Number of only countries: {df['Country'].nunique()}")
        print(f"   Only Gear Type: {df['Gear'].nunique()}")
        print(f"   Only Length_Category: {sorted(df['Length_Category'].unique())}")

    # ---- From base year Base_Power ----
    # If baseline_year Cannot initialise Evolutions mail component, and the most recent valid year of the group
    base_data = df[df['Year'] == baseline_year].copy()

    # Yes baseline_year Missing Group, Forward/Search backwards for the most recent year
    all_groups = df[['Country', 'Gear', 'Length_Category']].drop_duplicates()
    base_power_map = {}

    for _, row in all_groups.iterrows():
        c, g, lc = row['Country'], row['Gear'], row['Length_Category']
        subset = base_data[(base_data['Country'] == c) &
                           (base_data['Gear'] == g) &
                           (base_data['Length_Category'] == lc)]
        if len(subset) > 0:
            # Take the team baseline_year weighted average of all records
            base_power_map[(c, g, lc)] = (subset['P'].sum() / subset['NV'].sum())
        else:
            # Looking for the latest effective year
            hist = df[(df['Country'] == c) &
                      (df['Gear'] == g) &
                      (df['Length_Category'] == lc)]
            if len(hist) > 0:
                # Find the closest baseline_year Year(s)
                hist_years = hist['Year'].values
                nearest_idx = np.argmin(np.abs(hist_years - baseline_year))
                nearest_year = hist_years[nearest_idx]
                nearest_subset = hist[hist['Year'] == nearest_year]
                base_power_map[(c, g, lc)] = (nearest_subset['P'].sum() /
                                              nearest_subset['NV'].sum())

    if verbose:
        print(f"   baseline (Base_Power) Overwrite Cluster Number: {len(base_power_map)}")

    # ---- Merge Base_Power Back to the master table, Calculate Power_Discount_Factor ----
    base_df = pd.DataFrame([
        {'Country': k[0], 'Gear': k[1], 'Length_Category': k[2],
         'Base_Power': v}
        for k, v in base_power_map.items()
    ])
    df = df.merge(base_df, on=['Country', 'Gear', 'Length_Category'], how='inner')
    df['Power_Discount_Factor'] = df['Avg_Power'] / df['Base_Power']

    # Crop Extremes: The discount factor should not > 1.5 (Theres no way history can be so much stronger than modern ships) and > 0
    df['Power_Discount_Factor'] = df['Power_Discount_Factor'].clip(0.01, 1.5)

    if verbose:
        f = df['Power_Discount_Factor']
        print(f"   Power_Discount_Factor Distribution:")
        print(f"      mean={f.mean():.3f}, median={f.median():.3f}, "
              f"P5={f.quantile(0.05):.3f}, P95={f.quantile(0.95):.3f}")

    # ---- Build O(1) Query Dictionary ----
    # Level 1: Accurate Query (Country, Gear, Length_Category, Year) -> Discount Factor
    lookup = {}
    for _, row in df.iterrows():
        key = (row['Country'], row['Gear'], row['Length_Category'], int(row['Year']))
        lookup[key] = row['Power_Discount_Factor']

    # Level 2: Global average (Gear, Length_Category, Year) -> Discount Factor
    global_avg = df.groupby(['Gear', 'Length_Category', 'Year'])['Power_Discount_Factor'].mean()
    fallback_global = {}
    for (g, lc, y), val in global_avg.items():
        fallback_global[(g, lc, int(y))] = val

    # Level 3: Groups by the most recent year of the group (Country, Gear, Length_Category) -> (years_array, factors_array)
    fallback_group_nearest = {}
    for (c, g, lc), grp in df.groupby(['Country', 'Gear', 'Length_Category']):
        grp_sorted = grp.sort_values('Year')
        fallback_group_nearest[(c, g, lc)] = (
            grp_sorted['Year'].values.astype(int),
            grp_sorted['Power_Discount_Factor'].values
        )

    # Level 4: The most recent year of global dimensions
    fallback_global_nearest = {}
    for (g, lc), grp in df.groupby(['Gear', 'Length_Category']):
        grp_sorted = grp.sort_values('Year')
        fallback_global_nearest[(g, lc)] = (
            grp_sorted['Year'].values.astype(int),
            grp_sorted['Power_Discount_Factor'].values
        )

    if verbose:
        print(f"   Level-1 Number of accurate query keys: {len(lookup):,}")
        print(f"   Level-2 Global average number of keys: {len(fallback_global):,}")
        print(f"   Level-3 Group the most recent years: {len(fallback_group_nearest):,}")
        print(f"   Level-4 Recent Global Keys: {len(fallback_global_nearest):,}")

    return (lookup, fallback_global,
            fallback_group_nearest, fallback_global_nearest)


# ============================================================
# Query Functions -- For Monte Carlos main loop call (O(1) amortization)
# ============================================================

def query_power_discount(flag_full, gear_vessel, length_m, year,
                         lookup_data, hard_floor=0.6,
                         annual_decay_rate=0.018):
    """
    Querying the parameters of the given vessel Power_Discount_Factor. 

    parameter
    ----------
    flag_full : str
        vessel Data Flag (Full name, Like 'Australia', 'South Korea'). 
    gear_vessel : str
        vessel Data VesselType (Like 'LL', 'PS', 'TS'). 
    length_m : float
        vessel Data Length(m) Value. 
    year : int
        Target year (Usually Builtdate / year built). 
    lookup_data : tuple
        build_power_discount_lookup() Return value of the. 
    hard_floor : float
        Minimum discount factor for the mandatory base (default 0.6). 
    annual_decay_rate : float
        The annual decay rate of the early global bust (default ~1.8%, Approx. equals 0.982/years). 

    Back
    -------
    discount_factor : float
        Historical power discount multiplier, Scope [hard_floor, 1.5]. 
    """
    (lookup, fallback_global,
     fallback_group_nearest, fallback_global_nearest) = lookup_data

    # ---- Convert Parameter To CSV Key Space ----
    # Country: already ISO3 from unified pipeline
    country_iso3 = flag_full

    # Gear: LL/PS/TS -> CSV Gear Name
    gear_csv = GEAR_MAPPING.get(gear_vessel)
    if gear_csv is None:
        gear_csv = gear_vessel  # Try raw values directly

    # Length_Category: Value -> CSV Boxes
    len_cat_csv = map_length_to_csv_category(length_m)

    # ---- Level 1: Accurate Query (Country, Gear, Length_Category, Year) ----
    if country_iso3 is not None and gear_csv is not None:
        key = (country_iso3, gear_csv, len_cat_csv, int(year))
        if key in lookup:
            return np.clip(lookup[key], hard_floor, 1.5)

    # ---- Level 2: Global average (Gear, Length_Category, Year) ----
    if gear_csv is not None:
        key = (gear_csv, len_cat_csv, int(year))
        if key in fallback_global:
            return np.clip(fallback_global[key], hard_floor, 1.5)

    # ---- Level 3: use the nearest observed year within each group (Country, Gear, Length_Category) ----
    if country_iso3 is not None and gear_csv is not None:
        group_key = (country_iso3, gear_csv, len_cat_csv)
        if group_key in fallback_group_nearest:
            years_arr, factors_arr = fallback_group_nearest[group_key]
            return _nearest_or_interpolate(year, years_arr, factors_arr, hard_floor)

    # ---- Level 4: Label value for the most recent year of global dimensions (Gear, Length_Category) ----
    if gear_csv is not None:
        group_key = (gear_csv, len_cat_csv)
        if group_key in fallback_global_nearest:
            years_arr, factors_arr = fallback_global_nearest[group_key]
            return _nearest_or_interpolate(year, years_arr, factors_arr, hard_floor)

    # ---- Level 5: Its an early global game ----
    # By 2015 For anchor, Annual rate annual_decay_rate Index decay
    ref_year = 2015
    year_diff = max(0, ref_year - int(year))
    hard_decay = np.exp(-annual_decay_rate * year_diff)
    return np.clip(hard_decay, hard_floor, 1.5)


def _nearest_or_interpolate(target_year, years_arr, factors_arr, hard_floor):
    """
    From (years_arr, factors_arr) The nearest extraction target_year The discount factor. 
    Use Recent Neighbours; If target_year linearly interpolate between the two observed years. 
    """
    if len(years_arr) == 0:
        return hard_floor

    # Accurate Match
    exact_idx = np.where(years_arr == int(target_year))[0]
    if len(exact_idx) > 0:
        return np.clip(factors_arr[exact_idx[0]], hard_floor, 1.5)

    # linear interpolation / Nearest neighbor
    idx = np.searchsorted(years_arr, int(target_year))

    if idx == 0:
        # Target year earlier than all known years -> Nearest neighbor (Early years)
        return np.clip(factors_arr[0], hard_floor, 1.5)
    elif idx >= len(years_arr):
        # Target year is later than all known years -> Nearest neighbor (At the latest)
        return np.clip(factors_arr[-1], hard_floor, 1.5)
    else:
        # Between two known years -> linear interpolation
        y1, y2 = years_arr[idx - 1], years_arr[idx]
        f1, f2 = factors_arr[idx - 1], factors_arr[idx]
        frac = (int(target_year) - y1) / (y2 - y1)
        return np.clip(f1 + frac * (f2 - f1), hard_floor, 1.5)


# ============================================================
# Easy Initialisation Function -- Build and return one-time lookup Bag
# ============================================================

def init_power_discount_lookup(csv_path, baseline_year=2015):
    """
    Initialize all query structures at once, Return to direct access query_power_discount of tuple. 
    Usage:
        lookup_data = init_power_discount_lookup(csv_path)
        factor = query_power_discount(flag, gear, length, year, lookup_data)
    """
    return build_power_discount_lookup(csv_path, baseline_year)


# ============================================================
# Quantified Bulk Query -- For the Monte Carlo main loop, efficient call
# ============================================================

def query_power_discount_vectorized(flags_full, gears_vessel, lengths_m, years,
                                    lookup_data, hard_floor=0.6,
                                    annual_decay_rate=0.018):
    """
    Batch Query Power_Discount_Factor, Returns and Enter Long numpy Array. 
    For most hit Take Quick Dictionary Query Path, A few miss Were going to take the elements. 

    parameter -- Theyre all long 1D array-like. 
    """
    n = len(flags_full)
    results = np.full(n, np.nan, dtype=float)

    (lookup, fallback_global,
     fallback_group_nearest, fallback_global_nearest) = lookup_data

    # Pre-processing conversion
    countries_iso3 = np.array(flags_full, dtype=object)  # Already ISO3 from unified pipeline
    gears_csv = np.array([
        GEAR_MAPPING.get(g, g) for g in gears_vessel
    ], dtype=object)
    len_cats_csv = np.array([
        map_length_to_csv_category(l) for l in lengths_m
    ], dtype=object)
    years_int = np.array(years, dtype=int)

    # ---- Pass 1: Level-1 Accurate Query (Quantification) ----
    # Building Query Key List, Bulk Check
    for i in range(n):
        ci = countries_iso3[i]
        gi = gears_csv[i]
        li = len_cats_csv[i]
        yi = years_int[i]
        if ci is not None and gi is not None:
            key = (ci, gi, li, yi)
            if key in lookup:
                results[i] = lookup[key]

    # ---- Pass 2: Level-2 Global average ----
    mask_miss = np.isnan(results)
    for i in np.where(mask_miss)[0]:
        gi = gears_csv[i]
        li = len_cats_csv[i]
        yi = years_int[i]
        if gi is not None:
            key = (gi, li, yi)
            if key in fallback_global:
                results[i] = fallback_global[key]

    # ---- Pass 3-5: Pivot to Element ----
    mask_still_miss = np.isnan(results)
    for i in np.where(mask_still_miss)[0]:
        ci = countries_iso3[i]
        gi = gears_csv[i]
        li = len_cats_csv[i]
        yi = years_int[i]

        # Level 3: By group of most recent years
        found = False
        if ci is not None and gi is not None:
            group_key = (ci, gi, li)
            if group_key in fallback_group_nearest:
                years_arr, factors_arr = fallback_group_nearest[group_key]
                results[i] = _nearest_or_interpolate(yi, years_arr, factors_arr, hard_floor)
                found = True

        # Level 4: Recent global years
        if not found and gi is not None:
            group_key = (gi, li)
            if group_key in fallback_global_nearest:
                years_arr, factors_arr = fallback_global_nearest[group_key]
                results[i] = _nearest_or_interpolate(yi, years_arr, factors_arr, hard_floor)
                found = True

        # Level 5: Its hard
        if not found:
            ref_year = 2015
            year_diff = max(0, ref_year - yi)
            results[i] = np.exp(-annual_decay_rate * year_diff)

    # Global Crop
    results = np.clip(results, hard_floor, 1.5)
    return results


# ============================================================
# Diagnosis / Test Tool
# ============================================================

def print_lookup_summary(lookup_data):
    """Prints the coverage summary of the Query Table"""
    (lookup, fallback_global,
     fallback_group_nearest, fallback_global_nearest) = lookup_data

    print("\n" + "=" * 50)
    print("  Power Discount Factor Query Table -- Coverage Summary")
    print("=" * 50)
    print(f"  Level-1 Accurate key counts:           {len(lookup):>10,}")
    print(f"  Level-2 Global average number of keys:       {len(fallback_global):>10,}")
    print(f"  Level-3 Group the most recent years:     {len(fallback_group_nearest):>10,}")
    print(f"  Level-4 Recent Global Keys:     {len(fallback_global_nearest):>10,}")

    # Each Gear Coverage
    print("\n  Each Gear x Length_Category of Base_Power Overwrite:")
    for gear in sorted(set(k[0] for k in fallback_global_nearest.keys())):
        for lc in sorted(set(k[1] for k in fallback_global_nearest.keys() if k[0] == gear)):
            key = (gear, lc)
            if key in fallback_global_nearest:
                years = fallback_global_nearest[key][0]
                print(f"    {gear:30s} | {lc:16s} | {len(years):4d} yrs  "
                      f"({years.min()}-{years.max()})")
    print("=" * 50)
