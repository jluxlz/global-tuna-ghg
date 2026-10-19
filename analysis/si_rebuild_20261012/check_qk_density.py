"""Check transformed density and observation mapping, independent of fit results."""
from pathlib import Path
from scipy.stats import lognorm,uniform
import numpy as np,json
HERE=Path(__file__).resolve().parent
rng=np.random.default_rng(42);K=np.exp(rng.normal(1,2,1000));q=rng.uniform(.01,10,1000);P=np.exp(rng.normal(-.7,.3,1000))
kappa=q*K
original=lognorm.logpdf(K,s=2,scale=np.exp(1))+uniform.logpdf(q,loc=.01,scale=9.99)
transformed=lognorm.logpdf(K,s=2,scale=np.exp(1))+uniform.logpdf(kappa,loc=.01*K,scale=9.99*K)
residual=transformed+np.log(K)-original
obs_residual=np.log(q*P*K)-np.log(kappa*P)
assert np.allclose(residual,0,atol=1e-12)
assert np.allclose(obs_residual,0,atol=1e-12)
result=dict(Random_Cases=1000,Max_Log_Density_Jacobian_Residual=float(np.max(np.abs(residual))),Max_Observation_Log_Residual=float(np.max(np.abs(obs_residual))),Prior_Changed=False,Likelihood_Changed=False)
(HERE/'qK_Density_Equivalence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('qK prior Jacobian and observation identity PASS')
