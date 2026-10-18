# Convergence is screened on actual chain arrays, not pooled draws or draw count.
# Fixed parameters are excluded. Source: Vehtari et al. (2021); posterior.
rank_mcmc_qc<-function(b,lib=NULL,trajectory=FALSE) {
  if(!is.null(lib)) .libPaths(c(lib,.libPaths()))
  if(!requireNamespace('posterior',quietly=TRUE)) stop('Install posterior for MCMC quality control, or set JABBA_DIAGNOSTIC_LIB.')
  a<-b$sims.array;nms<-dimnames(a)[[3]]
  selected<-grep('^(r|K|psi|sigma2|q\\[[0-9]+\\]|P\\[55\\]|F\\[55\\]|MSY)$',nms,value=TRUE)
  stopifnot(all(c('r','K','psi','sigma2','P[55]','MSY')%in%selected))
  matrices<-setNames(lapply(selected,function(p)a[,,p]),selected)
  matrices[['Terminal_B']]<-a[,,'K']*a[,,'P[55]']
  if(trajectory) {
    states<-grep('^P\\[[0-9]+\\]$',nms,value=TRUE)
    for(p in states) {
      matrices[[p]]<-a[,,p]
      if(p!='P[55]')matrices[[sub('P','B',p,fixed=TRUE)]]<-a[,,'K']*a[,,p]
    }
  }
  d<-do.call(rbind,lapply(names(matrices),function(p) {
    m<-matrices[[p]]
    classical<-if(p%in%rownames(b$summary)) b$summary[p,c('Rhat','n.eff')] else c(Rhat=NA_real_,n.eff=NA_real_)
    data.frame(Parameter=p,Rank_Rhat=posterior::rhat(m),ESS_Bulk=posterior::ess_bulk(m),ESS_Tail=posterior::ess_tail(m),
      Classical_Rhat=classical['Rhat'],Classical_ESS=classical['n.eff'],
      Chains=ncol(m),Draws_Per_Chain=nrow(m),Median=median(m),MCSE_Median=posterior::mcse_quantile(m,probs=.5))
  }))
  d$Screen_Fail<-!is.finite(d$Rank_Rhat)|!is.finite(d$ESS_Bulk)|!is.finite(d$ESS_Tail)|
    d$Rank_Rhat>1.01|d$ESS_Bulk<400|d$ESS_Tail<400|d$Chains<4
  d
}
