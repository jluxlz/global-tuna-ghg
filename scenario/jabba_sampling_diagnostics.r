# Published rank-normalised split/folded Rhat and bulk/tail ESS.
# Uses the official posterior package, not split pooled chains.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)>=2)
input<-normalizePath(args[1],winslash='/');output<-normalizePath(args[2],winslash='/')
root<-normalizePath('.',winslash='/')
.libPaths(c(file.path(root,'audits','si_rebuild_20261012','R_lib'),.libPaths()))
library(posterior)
stocks<-if(length(args)>2) args[-(1:2)] else c('SKJ','YFT','BET','ALB','SBT');rows<-sums<-list()
for(s in stocks) {
  b<-readRDS(file.path(input,paste0(s,'_BUGSoutput.rds')))
  x<-readRDS(file.path(input,paste0(s,'_fit.rds')))
  a<-b$sims.array;nms<-dimnames(a)[[3]]
  # Core parameters plus terminal latent states affecting the projection.
  keep<-grep('^(r|K|psi|sigma2|q\\[[0-9]+\\]|P\\[55\\]|F\\[55\\]|MSY)$',nms,value=TRUE)
  stopifnot(all(c('r','K','psi','sigma2')%in%keep))
  ds<-do.call(rbind,lapply(keep,function(p) {
    d<-a[,,p];sm<-b$summary[p,]
    data.frame(Stock=s,Parameter=p,Rank_Rhat=posterior::rhat(d),
      ESS_Bulk=posterior::ess_bulk(d),ESS_Tail=posterior::ess_tail(d),
      Classical_Rhat=sm['Rhat'],Classical_ESS=sm['n.eff'],
      Draws_Per_Chain=nrow(d),Chains=ncol(d),Median=median(d),
      MCSE_Mean=posterior::mcse_mean(d),Posterior_SD=sd(as.numeric(d)))
  }))
  ds$Fail<-!is.finite(ds$Rank_Rhat)|!is.finite(ds$ESS_Bulk)|!is.finite(ds$ESS_Tail)|
    ds$Rank_Rhat>1.01|ds$ESS_Bulk<400|ds$ESS_Tail<400|ds$Chains<4
  rows[[s]]<-ds
  f<-x$fit;t<-f$timeseries
  sums[[s]]<-data.frame(Stock=s,r=f$estimates['r','mu'],K_Mt=f$estimates['K','mu'],
    B2024_Mt=tail(t[,'mu','B'],1),B2024_K=tail(t[,'mu','BB0'],1),
    B2024_K_lo=tail(t[,'lci','BB0'],1),B2024_K_hi=tail(t[,'uci','BB0'],1),
    Max_Rank_Rhat=max(ds$Rank_Rhat),Min_ESS_Bulk=min(ds$ESS_Bulk),
    Min_ESS_Tail=min(ds$ESS_Tail),Fail=any(ds$Fail),Chains=dim(a)[2],
    Draws_Per_Chain=dim(a)[1],Posterior_Version=as.character(packageVersion('posterior')))
}
write.csv(do.call(rbind,rows),file.path(output,'Rank_Diagnostics.csv'),row.names=FALSE)
write.csv(do.call(rbind,sums),file.path(output,'Rank_Diagnostic_Summary.csv'),row.names=FALSE)
print(do.call(rbind,sums));cat('DIAGNOSTICS_COMPLETE\n')
