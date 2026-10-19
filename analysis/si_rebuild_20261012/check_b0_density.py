"""Verify the full transformed state density and Jacobian independently."""
from pathlib import Path
import numpy as np,json
from scipy.stats import lognorm,uniform
HERE=Path(__file__).resolve().parent;rng=np.random.default_rng(42);results=[]
for n in [1,10,55]:
    K=np.exp(rng.normal(1,.8,1000));psi=np.exp(rng.normal(-.7,.3,1000));q=rng.uniform(.01,10,1000)
    P=np.exp(rng.normal(-.7,.3,(1000,n)));B0=K*psi;kappa=q*B0;U=P/psi[:,None]
    means=rng.normal(-.7,.3,(1000,n));sd=.2
    old=lognorm.logpdf(K,s=.8,scale=np.exp(1))+uniform.logpdf(q,loc=.01,scale=9.99)+lognorm.logpdf(P,s=sd,scale=np.exp(means)).sum(axis=1)
    new=lognorm.logpdf(B0,s=.8,scale=np.exp(1)*psi)+uniform.logpdf(kappa,loc=.01*B0,scale=9.99*B0)+lognorm.logpdf(U,s=sd,scale=np.exp(means)/psi[:,None]).sum(axis=1)
    log_jac=(n-1)*np.log(psi)-np.log(B0)
    residual=new-old-log_jac
    observation=np.log(q[:,None]*K[:,None]*P)-np.log(kappa[:,None]*U)
    assert np.allclose(residual,0,atol=1e-10);assert np.allclose(observation,0,atol=1e-12)
    results.append(dict(States=n,Max_Log_Density_Residual=float(np.max(np.abs(residual))),Max_Observation_Residual=float(np.max(np.abs(observation)))))
(HERE/'B0_Density_Equivalence.json').write_text(json.dumps(dict(Cases_Per_Design=1000,Results=results,Prior_Changed=False,Likelihood_Changed=False),indent=2),encoding='utf-8')
print('B0 state, prior and observation density equivalence PASS')
