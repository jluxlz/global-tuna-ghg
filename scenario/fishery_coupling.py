"""Optional annual catch/biomass/fleet closure, independent of legacy caches.

This is a capacity-constrained sensitivity model, not a stock assessment.
Effort is kW-days; reference catchability is calibrated once to the explicit
baseline. Realised removals, not requested quotas, update the stock. All model
assumptions and both stock and fleet catch denominators are exported.
"""
from pathlib import Path
import numpy as np
import pandas as pd


class FisheryCoupling:
    def __init__(self, fleet, config, params):
        self.params = params
        self.hcr = params.get('hcr')
        self.max_days = float(config.get('max_operating_days', 365.0))
        if not 0 < self.max_days <= 365:
            raise ValueError('Operating-day bound must be in (0,365]')
        self.stocks = pd.read_csv(config['stock_parameters']).set_index('Stock')
        required = ['r', 'K_Mt', 'B2024_Mt', 'Catch2024_Mt']
        if self.stocks.index.has_duplicates or (self.stocks[required] <= 0).any().any():
            raise ValueError('Unique stocks and strictly positive biological inputs required')
        if not np.isfinite(self.stocks[required]).all().all():
            raise ValueError('Nonfinite biological input')
        if (self.stocks.B2024_Mt > self.stocks.K_Mt).any():
            raise ValueError('Terminal biomass cannot exceed carrying capacity in this sensitivity model')
        # JABBA B[t] is the start-of-year state: its transition subtracts
        # C[t-1]. Advance the fitted 2024 state with the observed 2024 removal
        # once before simulating 2025; never treat it as end-2024 biomass.
        self.b = {}
        for s,row in self.stocks.iterrows():
            b = float(row.B2024_Mt)
            end = b + row.r*b*(1-b/row.K_Mt) - row.Catch2024_Mt
            if end < 0:
                raise ValueError(f'Observed terminal catch exceeds available stock: {s}')
            self.b[s] = float(end)
        self.b0 = self.b.copy()
        self.harvest0 = {}
        for s,row in self.stocks.iterrows():
            available = self.b0[s]+row.r*self.b0[s]*(1-self.b0[s]/row.K_Mt)
            if not 0 < row.Catch2024_Mt < available:
                raise ValueError(f'Reference harvest fraction must be between zero and one: {s}')
            self.harvest0[s] = -np.log1p(-row.Catch2024_Mt/available)
        self.ledger = []
        self.effort_ledger = []
        self.baseline = fleet.copy()
        self.baseline['Weight'] = fleet.get('Accounting_Weight', 1.0)
        self.baseline['E0'] = self.baseline.Power_kW * self.baseline.T_map * self.baseline.Weight
        directed = self.baseline[self.baseline.VesselType.isin(['LL', 'PS'])]
        self.e0 = directed.groupby(['Organization', 'VesselType']).E0.sum().to_dict()
        if 'allocation_file' in config:
            a = pd.read_csv(config['allocation_file'])
        else:
            import fig5_allocation as fa
            p = fa.build_shares()['P']
            a = pd.DataFrame([dict(Stock=s, Organization=o, Gear=g, Share=v)
                              for s in self.stocks.index for (o,g),v in p[s].items() if v>0])
        self.p = {(x.Stock, x.Organization, x.Gear): float(x.Share) for x in a.itertuples()}
        for s in self.stocks.index:
            vals = [v for (ss,o,g),v in self.p.items() if ss==s]
            if not np.isclose(sum(vals), 1) or any(v<0 for v in vals):
                raise ValueError(f'Catch allocation fails conservation: {s}')
        # Fraction of effort assigned to a species within a fleet group. The
        # mass-based partition is explicit and fixed, as in the original model.
        self.w = {}
        for o,g in self.e0:
            c = {s:self.stocks.at[s,'Catch2024_Mt']*self.p.get((s,o,g),0)*self.fraction(s)
                 for s in self.stocks.index}
            total = sum(c.values())
            for s in c:
                self.w[s,o,g] = c[s]/total if total else 0.0
        self.year = None

    def fraction(self, s):
        value = float(self.stocks.at[s,'Fleet_Catch_Fraction']) if 'Fleet_Catch_Fraction' in self.stocks else 1.0
        if not 0 < value <= 1:
            raise ValueError('Fleet_Catch_Fraction must be in (0,1]')
        return value

    def begin_year(self, year):
        if self.year is not None and year != self.year+1:
            raise ValueError('Coupled biology must advance exactly one year')
        self.year = year
        tech = (1+float(self.params.get('tech_creep',0)))**(year-2025)
        cs = {0:0,1:.5,2:1}[int(self.params.get('consolidation_type',0))]
        self.eta = 1-float(self.params.get('upsize_beta',.243))*cs*np.clip((year-2025)/25,0,1)
        self.target, self.growth, self.demand_s, self.harvest_rate = {}, {}, {}, {}
        self.hcr_diagnostics = {}
        for s,row in self.stocks.iterrows():
            b = self.b[s]
            self.growth[s] = row.r*b*(1-b/row.K_Mt)
            qt = self.params.get('quota_type','C')
            qt = qt.get(s,'C') if isinstance(qt,dict) else qt
            sch = self.params.get('schaefer_scenario','C2024')
            value = sch.get(s,1) if isinstance(sch,dict) else sch
            f = (float(str(value).split('_')[-1])/100 if str(value).startswith('MSY_')
                 else (1. if value == 'C2024' else float(value)))
            if self.hcr is not None:
                from harvest_control_rules import target_from_rule
                rule = self.hcr.get(s) if 'type' not in self.hcr else self.hcr
                if rule is None:raise ValueError(f'Missing explicit HCR for stock {s}')
                target, self.hcr_diagnostics[s] = target_from_rule(b,row.r,row.K_Mt,rule)
            elif qt == 'F':
                target = f*row.r/2*b
            elif sch == 'C2024':
                target = row.Catch2024_Mt*float(self.params.get('catch_target_scale',1))
            else:
                target = f*row.r*row.K_Mt/4
            self.target[s] = float(target)
            available = max(b+self.growth[s],0.)
            # Finite fishing mortality cannot remove 100% of an available
            # stock. Annual surplus production precedes the harvest pulse.
            # The inversion tolerance is numerical, not a biomass floor.
            harvest = -np.log1p(-min(target/available,1-1e-12)) if available>0 else 0.
            self.harvest_rate[s] = harvest
            for o,g in self.e0:
                self.demand_s[s,o,g] = self.e0[o,g]*self.w[s,o,g]*harvest/self.harvest0[s]/tech*self.eta
        self.demand = {og:sum(self.demand_s[s,*og] for s in self.stocks.index) for og in self.e0}

    def retire_mask(self, fleet, gamma=.10):
        mask = pd.Series(False,index=fleet.index)
        for (o,g),idx in fleet[fleet.VesselType.isin(['LL','PS'])].groupby(['Organization','VesselType']).groups.items():
            grp = fleet.loc[idx].sort_values('Age',ascending=False)
            weights = grp.get('Accounting_Weight',pd.Series(1.,index=grp.index))
            supply = grp.Power_kW*weights*self.max_days
            required = self.demand.get((o,g),0.)*(1+gamma)
            surplus = max(float(supply.sum())-required,0.)
            count = int(np.searchsorted(supply.cumsum().to_numpy(),surplus,side='right'))
            # Retain at least one engineering template per org/gear.
            mask.loc[grp.index[:min(count,max(len(grp)-1,0))]] = True
        return mask.to_numpy()

    def resolve(self, fleet, econ):
        """Resolve activity before GHG computation; exact annual mass balance."""
        if not np.isfinite(econ.M_econ_raw).all() or (econ.M_econ_raw<0).any():
            raise ValueError('Nonfinite or negative raw cost response cannot drive fleet activity')
        weight = fleet.get('Accounting_Weight',pd.Series(1.,index=fleet.index))
        power = fleet.Power_kW*weight
        catch_sg = {}
        activity = pd.Series(0.,index=fleet.index)
        # Allocate limited vessel capacity in proportion to physical power;
        # economic response can lower utilisation but never exceed the quota.
        for og,idx in fleet[fleet.VesselType.isin(['LL','PS'])].groupby(['Organization','VesselType']).groups.items():
            demand = self.demand.get(og,0.)
            supply = float(power.loc[idx].sum())*self.max_days
            econmean = float(np.average(econ.loc[idx,'M_econ_raw'],weights=power.loc[idx])) if power.loc[idx].sum()>0 else 0.
            used = min(demand,supply,max(demand*econmean,0.))
            ratio = used/demand if demand>0 else 0.
            days = used/float(power.loc[idx].sum()) if power.loc[idx].sum()>0 else 0.
            activity.loc[idx] = days
            for s in self.stocks.index:
                available = max(self.b[s]+self.growth[s],0.)
                catch_sg[s,*og] = available*self.fraction(s)*self.p.get((s,*og),0.)*(-np.expm1(-self.harvest_rate[s]*ratio))
        # Physical effort partition follows demand, while realised catches
        # follow the finite harvest function rather than linear catch ratios.
        for og,idx in fleet[fleet.VesselType.isin(['LL','PS'])].groupby(['Organization','VesselType']).groups.items():
            target_eff = float((power.loc[idx]*activity.loc[idx]).sum())
            self.effort_ledger.append(dict(Year=self.year,Organization=og[0],Gear=og[1],
                 Required_kW_days=self.demand.get(og,0.),Realised_kW_days=target_eff,
                 Capacity_kW_days=float(power.loc[idx].sum())*self.max_days))
        tot_used = float((power*activity).sum())
        base_used = sum(self.e0.values())
        support = ~fleet.VesselType.isin(['LL','PS'])
        support_ratio = tot_used/base_used if base_used else 0.
        activity.loc[support] = np.minimum(self.max_days,fleet.loc[support,'T_map']*support_ratio*econ.loc[support,'M_econ_raw'])
        if not np.isfinite(activity).all() or (activity<0).any():
            raise ValueError('Nonfinite or negative realized operating days')
        econ['Operating_Days'] = activity
        # compute_fleet_ghg multiplies E_final by eta exactly once.
        econ['E_final'] = activity/(fleet.T_map*self.eta)
        econ['Meco'] = 0.
        for og,idx in fleet[fleet.VesselType.isin(['LL','PS'])].groupby(['Organization','VesselType']).groups.items():
            ref = float((power.loc[idx]*fleet.loc[idx,'T_map']).sum())
            econ.loc[idx,'Meco'] = self.demand.get(og,0.)/(ref*self.eta) if ref>0 else 0.
        econ.loc[support,'Meco'] = support_ratio/self.eta
        econ['M_econ_realized'] = np.divide(econ.E_final,econ.Meco,out=np.zeros(len(econ)),where=econ.Meco.to_numpy()>0)
        for s,row in self.stocks.iterrows():
            fleet_catch = sum(v for (ss,o,g),v in catch_sg.items() if ss==s)
            removed = fleet_catch/self.fraction(s)
            next_b = self.b[s]+self.growth[s]-removed
            if next_b < -1e-10 or removed > self.target[s]+1e-10:
                raise AssertionError('Biological conservation or quota ceiling failed')
            self.ledger.append(dict(Year=self.year,Stock=s,B_Start_Mt=self.b[s],Growth_Mt=self.growth[s],
                Target_Catch_Mt=self.target[s],Realised_Stock_Catch_Mt=removed,
                Realised_Fleet_Catch_Mt=fleet_catch,B_End_Mt=max(next_b,0.),K_Mt=row.K_Mt,
                B_Bmsy_Start=2*self.b[s]/row.K_Mt,Tech_Catchability=(1+float(self.params.get('tech_creep',0)))**(self.year-2025),
                Fleet_Catch_Fraction=self.fraction(s)))
            if self.hcr is not None:
                self.ledger[-1].update(self.hcr_diagnostics[s])
                self.ledger[-1]['Target_Harvest_Pulse'] = self.harvest_rate[s]
            self.b[s] = max(next_b,0.)
        self.catch_sg = catch_sg
        return econ

    def attach(self, history):
        catch = pd.DataFrame(self.ledger)
        totals = catch.groupby('Year')[['Realised_Stock_Catch_Mt','Realised_Fleet_Catch_Mt','Target_Catch_Mt']].sum()
        history = history.merge(totals,left_on='Year',right_index=True,validate='one_to_one')
        denominator=(history.Realised_Fleet_Catch_Mt*1e6).where(history.Realised_Fleet_Catch_Mt>0)
        history['CEI_tCO2e_per_t'] = history.Total_GHG_tCO2e/denominator
        history.attrs['stock_ledger'] = catch
        history.attrs['effort_ledger'] = pd.DataFrame(self.effort_ledger)
        return history
