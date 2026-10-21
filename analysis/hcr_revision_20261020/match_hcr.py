"""Catch-only matching across C/F/T, retaining every candidate and failed pair.

Candidates span 0.15--1.00 of MSY or FMSY. GHG is recorded but never used to
choose parameters, targets, brackets or pairs. Nonmonotonic response is handled
by screening adjacent catch brackets, not assuming monotonicity over the range.
"""
from pathlib import Path
import sys,json,time,itertools,os,hashlib
from multiprocessing import Pool
import numpy as np
import pandas as pd
import run_hcr as E
H=E.H;FRACTIONS=(.15,.3,.45,.6,.65,.75,.9,1.)
CENTRAL=[i for i,(w,g,r,t) in enumerate(E.FUTURES) if g==.0136 and r==2]
TRIALS=[];SEEN={};POOL=None

def job(i,rule,fraction):
    return E.make_job(i,rule,fraction=float(fraction),scope='Matching',key=f'Match_F{i+1:02}_{rule}_q{fraction:.9f}')
def candidate(i,rule,fraction):
    key=job(i,rule,fraction)[0]
    if fraction==1.:
        primary=E.OUT/E.make_job(i,rule)[0]
        if (primary/'Complete.json').exists():key=primary.name
    return key
def read_record(i,rule,fraction,key):
    a=pd.read_csv(E.OUT/key/'Annual.csv')
    return dict(Future=f'F{i+1:02}',Index=i,Rule=rule,Fraction=float(fraction),Key=key,
                Catch_Mt=float(a.Realised_Fleet_Catch_Mt.sum()),GHG_Mt=float(a.Total_GHG_tCO2e.sum()/1e6))
def evaluate(requests,stage):
    todo=[]
    for i,rule,f in requests:
        identity=(i,rule,float(f))
        if identity in SEEN:continue
        key=candidate(i,rule,f)
        if key.startswith('Main_'):
            row=read_record(i,rule,f,key);row['Stage']=stage;SEEN[identity]=row;TRIALS.append(row)
        else:todo.append((i,rule,f,job(i,rule,f)))
    for (i,r,f,j),result in zip(todo,POOL.map(E.run_task,[x[3] for x in todo],chunksize=1)):
        row=read_record(i,r,f,result[0]);row['Stage']=stage;SEEN[i,r,float(f)]=row;TRIALS.append(row)
    pd.DataFrame(TRIALS).to_csv(H/'Catch_Matching_All_Candidates.csv',index=False)
def rows(i,rule):return [x for (ii,rr,f),x in SEEN.items() if ii==i and rr==rule]
def best_within(i,rule,target,tol):
    good=[r for r in rows(i,rule) if abs(r['Catch_Mt']/target-1)<=tol]
    return sorted(good,key=lambda r:(abs(r['Fraction']-1),abs(r['Catch_Mt']/target-1)))[0] if good else None
def solve(i,rule,target,tol=.0045):
    result=best_within(i,rule,target,tol)
    if result:return result,'Matched sampled candidate'
    points=sorted(rows(i,rule),key=lambda r:r['Fraction'])
    brackets=[(a,b) for a,b in zip(points,points[1:]) if (a['Catch_Mt']-target)*(b['Catch_Mt']-target)<0]
    brackets.sort(key=lambda x:max(x[0]['Fraction'],x[1]['Fraction']),reverse=True)
    for lower,upper in brackets:
        for step in range(12):
            f=(lower['Fraction']+upper['Fraction'])/2
            evaluate([(i,rule,f)],'Bracket refinement')
            middle=SEEN[i,rule,float(f)]
            if abs(middle['Catch_Mt']/target-1)<=tol:return middle,'Matched refined bracket'
            if (lower['Catch_Mt']-target)*(middle['Catch_Mt']-target)<=0:upper=middle
            else:lower=middle
    return None,'No match within tolerance in sampled/refined admissible brackets'

def main():
    global POOL
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    assert json.loads((H/'Pilot_QC.json').read_text())['Passed']
    cfg=dict(Futures=[f'F{i+1:02}' for i in CENTRAL],Fractions=FRACTIONS,
        Common_Target='C alpha=0.65 catch if inside sampled C/F/T overlap; otherwise nearest interior common target',
        Joint_Target_Tolerance=.0045,Pairwise_Tolerance=.01,Maximum_Bracket_Iterations=12,
        Selection='Closest admissible sampled/refined fraction to 1 among catch-matched candidates; GHG not used',
        Shapes='Shared actual-catch target first, independent pairwise targets only when common matching fails')
    (H/'Catch_Matching_Protocol.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    fleet,pm,grid=E.load_inputs();signature=hashlib.sha256(json.dumps(E.fingerprint(),sort_keys=True).encode()).hexdigest()
    started=time.time();ranges=[];selected=[];triples=[]
    E.configure_spawn_threads()
    with Pool(int(os.environ.get('HCR_MATCH_WORKERS','4')),initializer=E.init_worker,initargs=(fleet,pm,grid,signature)) as pool:
        POOL=pool
        evaluate([(i,r,f) for i in CENTRAL for r in ('C','F','T') for f in FRACTIONS],'Initial attainable-range screen')
        print('RANGE SCREEN COMPLETE',len(TRIALS),'candidates; seconds',round(time.time()-started),flush=True)
        for i in CENTRAL:
            intervals={r:(min(x['Catch_Mt'] for x in rows(i,r)),max(x['Catch_Mt'] for x in rows(i,r))) for r in ('C','F','T')}
            for r,(lo,hi) in intervals.items():ranges.append(dict(Future=f'F{i+1:02}',Rule=r,Minimum_Sampled_Catch_Mt=lo,Maximum_Sampled_Catch_Mt=hi))
            lo=max(v[0] for v in intervals.values());hi=min(v[1] for v in intervals.values())
            anchor=SEEN[i,'C',.65]['Catch_Mt'];target=float(np.clip(anchor,lo+(hi-lo)*.01,hi-(hi-lo)*.01)) if lo<hi else None
            chosen={};status={}
            if target is not None:
                for r in ('C','F','T'):chosen[r],status[r]=solve(i,r,target)
            common=target is not None and all(chosen.get(r) is not None for r in ('C','F','T'))
            triples.append(dict(Future=f'F{i+1:02}',Common_Range_Low_Mt=lo,Common_Range_High_Mt=hi,
                C065_Anchor_Catch_Mt=anchor,Common_Target_Catch_Mt=target,Common_Triple_Matched=common,
                **{r+'_Status':status.get(r,'No sampled common catch range') for r in ('C','F','T')}))
            for a,b in [('C','F'),('C','T'),('F','T')]:
                aa=chosen.get(a);bb=chosen.get(b);design='Common three-rule target'
                if not common:
                    low=max(intervals[a][0],intervals[b][0]);high=min(intervals[a][1],intervals[b][1])
                    if low<high:
                        target_pair=float(np.clip(anchor,low+(high-low)*.01,high-(high-low)*.01))
                        aa,sa=solve(i,a,target_pair);bb,sb=solve(i,b,target_pair)
                        design='Independent pairwise target'
                    else:aa=bb=None;design='No sampled pairwise overlap'
                matched=aa is not None and bb is not None and abs(bb['Catch_Mt']/aa['Catch_Mt']-1)<=.01
                row=dict(Future=f'F{i+1:02}',Comparison=a+b,Base_Rule=a,Policy_Rule=b,Matching_Design=design,Matched=matched)
                for r,label in [(aa,'Base'),(bb,'Policy')]:
                    if r:row.update({label+'_'+k:r[k] for k in ('Key','Fraction','Catch_Mt','GHG_Mt')})
                if matched:row.update(Catch_Gap_pct=100*(bb['Catch_Mt']/aa['Catch_Mt']-1),GHG_Difference_Mt=bb['GHG_Mt']-aa['GHG_Mt'],GHG_Reduction_pct=100*(1-bb['GHG_Mt']/aa['GHG_Mt']))
                selected.append(row)
            pd.DataFrame(ranges).to_csv(H/'Catch_Attainable_Ranges.csv',index=False)
            pd.DataFrame(triples).to_csv(H/'Common_Catch_Triples.csv',index=False)
            pd.DataFrame(selected).to_csv(H/'HCR_Matched_Pairs.csv',index=False)
            print('MATCH',f'F{i+1:02}','common triple',common,'matched pairs',sum(x['Matched'] for x in selected if x['Future']==f'F{i+1:02}'),'seconds',round(time.time()-started),flush=True)
    (H/'Matching_Complete.json').write_text(json.dumps(dict(Attempted_Futures=9,Attempted_Pairs=27,Matched_Pairs=sum(x['Matched'] for x in selected),Common_Triples=sum(x['Common_Triple_Matched'] for x in triples),Total_Candidates=len(TRIALS),Seconds=time.time()-started),indent=2),encoding='utf-8')
    print('MATCHING COMPLETE',flush=True)
if __name__=='__main__':main()
