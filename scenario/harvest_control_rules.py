"""Representative C/F/T targets for the existing annual harvest-pulse model.

The 40-10 structure is a total-biomass/K scenario proxy, inspired by published
threshold rules. It does not reproduce any RFMO management procedure or equate
total biomass to assessed spawning biomass. Thresholds are fixed before runs.
"""
import math

def target_from_rule(biomass,r,capacity,rule):
    b,r,k=map(float,(biomass,r,capacity))
    if not all(math.isfinite(x) for x in (b,r,k)) or b<0 or r<=0 or k<=0:
        raise ValueError('Finite nonnegative biomass and positive r/K required')
    kind=str(rule['type']).upper()
    if kind not in ('C','F','T'):raise ValueError('HCR type must be C, F or T')
    alpha=float(rule.get('alpha',1.));beta=float(rule.get('beta',1.))
    trigger=float(rule.get('b_trigger_k',.4));lower=float(rule.get('b_close_k',.1))
    if not all(math.isfinite(x) for x in (alpha,beta,trigger,lower)) or alpha<0 or beta<0:
        raise ValueError('Finite nonnegative HCR fractions required')
    if not 0<=lower<trigger<=1:raise ValueError('Require 0 <= closure < trigger <= K')
    if kind!='T' or b>=trigger*k:multiplier=1.
    elif b<=lower*k:multiplier=0.
    else:multiplier=(b-lower*k)/((trigger-lower)*k)
    nominal=beta*r/2*multiplier
    target=alpha*r*k/4 if kind=='C' else nominal*b
    return float(target),dict(HCR=kind,HCR_Alpha=alpha,HCR_Beta=beta,
        B_Trigger_Mt=trigger*k,B_Closure_Mt=lower*k,HCR_Rate_Multiplier=multiplier,
        HCR_Triggered=bool(kind=='T' and b<trigger*k),
        HCR_Closed=bool(kind=='T' and b<=lower*k),
        Nominal_HCR_F=nominal if kind!='C' else float('nan'))
