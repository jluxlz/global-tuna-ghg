"""Select the current nine matched-rule pairs without manuscript dependencies."""
from pathlib import Path
import json
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
ENSEMBLE=ROOT/'analysis/p0_revision_20261013/ensemble'
def main():
    selected=pd.read_csv(ENSEMBLE/'Equal_Catch_Matched.csv')
    if len(selected)!=9 or selected.Future.duplicated().any() or (selected.Relative_Catch_Gap.abs()>.01).any():
        raise ValueError('Nine unique matched pairs within 1% cumulative catch required')
    rows=[]
    for row in selected.sort_values('Future').itertuples():
        for rule,key in [('C',f'Matched_{row.Future}_0.65'),('F',f'EqualCatch_{row.Future}_trial{int(row.Trial)}')]:
            folder=ENSEMBLE/key
            marker=json.loads((folder/'Complete.json').read_text(encoding='utf-8'))
            if any(not (folder/name).is_file() for name in ['Annual.csv','Stocks.csv','Effort.csv']):
                raise FileNotFoundError('Incomplete matched-rule checkpoint: '+key)
            rows.append(dict(Future=row.Future,Rule=rule,Folder=folder.relative_to(ROOT).as_posix(),
                             Seed=marker['seed'],Parameters=marker['params'],Metadata=marker['meta']))
    (HERE/'Saved_Matched_Runs.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
if __name__=='__main__':main()
