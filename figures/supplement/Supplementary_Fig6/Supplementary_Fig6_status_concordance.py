"""Verified RFMO context; no conversion to global total-biomass B/K."""
from pathlib import Path
import pandas as pd,hashlib,json,sys
sys.stdout.reconfigure(encoding="utf-8",errors="replace")
HERE=Path(__file__).resolve().parent
ref=pd.read_csv(HERE/"Verified_Assessment_References.csv")
assert not ref[["Stock","Organization","Metric"]].duplicated().any()
ref.to_csv(HERE/"Supplementary_Fig6_Official_Context.csv",index=False)
metadata=dict(Comparison="Context only: population and biomass definitions differ",
 No_Conversion_to_Global_BK=True,Calibration_Claim_Unsupported=True,
 Reference_SHA256=hashlib.sha256((HERE/"Verified_Assessment_References.csv").read_bytes()).hexdigest())
(HERE/"Supplementary_Fig6_Reference_QC.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
print("Verified reference context exported; unsupported concordance retired")
