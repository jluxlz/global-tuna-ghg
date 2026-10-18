"""ICCAT Task-II extraction with separate catch units and shared-effort accounting."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

SPECIES = ["ALB", "YFT", "BET", "SKJ"]
SOURCE = Path(__file__).resolve().parent / "source_data/t2ce_20260130web.mdb"


def extract_tables(raw, flags):
    raw, flags = raw.copy(), flags.copy()
    raw["FleetID"] = raw["FleetID"].astype(str).str.strip()
    flags["FleetID"] = flags["FleetID"].astype(str).str.strip()
    if flags["FleetID"].duplicated().any():
        raise ValueError("ICCAT Flags dictionary has duplicate FleetID")
    d = raw.merge(flags[["FleetID", "FlagName", "FleetName"]], on="FleetID", how="left", validate="many_to_one")
    d["Flag"] = d["FlagName"].apply(normalize_flag_to_iso3)
    valid = d["Flag"].apply(is_allowed_iso3) & d["QuadID"].isin([1,2,3,4]) & d["Lat"].between(0,90) & d["Lon"].between(0,180)
    rejected = d.loc[~valid].copy()
    d = d.loc[valid].copy()
    d["Lat"] *= np.where(d["QuadID"].isin([2,3]), -1, 1)
    d["Lon"] *= np.where(d["QuadID"].isin([3,4]), -1, 1)
    d["Eff1Type"] = d["Eff1Type"].fillna("Unknown")
    d["Eff1"] = pd.to_numeric(d["Eff1"], errors="coerce").fillna(0)
    unit = d["CatchUnit"].astype(str).str.strip().str.lower()
    unknown_units = d.loc[~unit.isin(["kg","t","mt","nr","no","n"])].copy()
    for s in SPECIES:
        values = pd.to_numeric(d[s], errors="coerce").fillna(0)
        d[s+"n"] = values.where(unit.isin(["nr","no","n"]),0)
        d[s] = values.where(unit.isin(["t","mt"]),0) + values.where(unit.eq("kg"),0)/1000
    keys = ["YearC","Flag","FleetName","GearCode","Lat","Lon","SquareTypeCode","Eff1Type"]
    # Match at the original time/dataset/stratum dimensions, before annual aggregation.
    operation = [c for c in ["DSetID","FleetID","GearCode","YearC","TimePeriodID","SquareTypeCode",
                 "Lat","Lon","SchoolTypeCode","FileTypeCode","DSetTypeID","Eff1Type","Eff2","Eff2Type"] if c in d]
    counts = d.groupby(operation+["Eff1","CatchUnit"], dropna=False).size().rename("Occurrences").reset_index()
    # Duplicate units describing the same effort contribute once; preserve repeated rows within a unit.
    effort = counts.groupby(operation+["Eff1"],dropna=False).Occurrences.max().reset_index()
    effort["Eff1"] *= effort["Occurrences"]
    identities = d[operation+["Flag","FleetName"]].drop_duplicates(operation)
    effort = effort.merge(identities,on=operation,how="left",validate="many_to_one")
    effort = effort.groupby(keys,dropna=False)["Eff1"].sum()
    catch = d.groupby(keys,dropna=False)[SPECIES+[s+"n" for s in SPECIES]].sum()
    out = catch.join(effort, how="outer").fillna(0).reset_index()
    out["CatchUnit"] = "t"  # Weight columns are tonnes; *n columns remain fish counts.
    qc = pd.DataFrame([dict(Raw_Rows=len(raw),Accepted_Rows=len(d),Rejected_Rows=len(rejected),
            Raw_Effort=d.Eff1.sum(),Unique_Effort=out.Eff1.sum(),Rows=len(out))])
    return out, qc, rejected, unknown_units


def build_iccat(output_dir=None, source=SOURCE):
    import pyodbc
    conn = pyodbc.connect("DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ="+str(source)+";", readonly=True)
    try:
        conn.setdecoding(pyodbc.SQL_CHAR,encoding="latin1")
        # Unicode columns use the driver's Unicode decoder, not a Latin-1 byte decoder.
        raw = pd.read_sql("SELECT * FROM t2ce WHERE GearCode IN ('LL','PS')",conn)
        flags = pd.read_sql("SELECT * FROM Flags",conn)
    finally:
        conn.close()
    out, qc, rejected, unknown = extract_tables(raw,flags)
    dest = Path(output_dir or Path(__file__).resolve().parent)
    dest.mkdir(parents=True,exist_ok=True)
    for name, df in [("ICCAT_Grid_Catch_Effort.csv",out),("ICCAT_Extraction_QC.csv",qc),
                     ("ICCAT_Rejected_Rows.csv",rejected),("ICCAT_Unknown_Catch_Units.csv",unknown)]:
        df.to_csv(dest/name,index=False,encoding="utf-8-sig")
    return out


if __name__ == "__main__":
    import argparse
    sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir")
    args=parser.parse_args()
    result=build_iccat(args.output_dir)
    print(f"ICCAT extraction: {len(result)} annual grid records")
