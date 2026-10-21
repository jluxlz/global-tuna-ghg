# Independent sampling repair of a preserved biological model.
# Arguments: stock, output directory, iterations, burn-in, thinning, seed.
# Does not overwrite production projections. Prior/data changes are separate runs.
args<-commandArgs(trailingOnly=TRUE)
stopifnot(length(args)%in%c(6,7,8))
stock<-args[1];out<-normalizePath(args[2],winslash='/',mustWork=TRUE)
ni<-as.integer(args[3]);nb<-as.integer(args[4]);nt<-as.integer(args[5]);seed<-as.integer(args[6])
stopifnot(ni>nb,ni>=20000,nb>=5000,nt>=1)
library(JABBA)
root<-normalizePath('.',winslash='/')
src<-file.path(root,'figures','supplement','Supplementary_Fig6','jabba_diagnostics',paste0(stock,'_fit.rds'))
x<-readRDS(src)
prior_mode<-if(length(args)>=7) args[7] else 'lnorm'
sampler<-if(length(args)>=8) args[8] else 'centred'
stopifnot(sampler%in%c('centred','qK','B0'))
stopifnot(prior_mode%in%c('lnorm','range'))
if(prior_mode=='range') {
  r_priors<-list(SKJ=c(.8,.2),YFT=c(.4,.3),BET=c(.35,.3),ALB=c(.25,.3),SBT=c(.1,.3))
  psi_priors<-list(SKJ=c(.45,.3),YFT=c(.5,.3),BET=c(.45,.3),ALB=c(.55,.3),SBT=c(.25,.35))
  original<-x$input
  x$input<-build_jabba(catch=x$catch,cpue=x$cpue,se=x$se,assessment=stock,model.type='Schaefer',
     r.prior=r_priors[[stock]],r.dist='lnorm',psi.prior=psi_priors[[stock]],psi.dist='lnorm',
     K.prior=if(stock=='SBT') c(1,5) else c(2,80),K.dist='range',verbose=FALSE)
  stopifnot(identical(x$input$jagsdata$r.pr,original$jagsdata$r.pr),
            identical(x$input$jagsdata$psi.pr,original$jagsdata$psi.pr))
  x$original_K_prior<-original$jagsdata$K.pr
}
stopifnot(as.character(x$source_md5)==as.character(tools::md5sum(file.path(root,'GHG_Calculation','Base_3_Spatial_Grid_Enriched.csv'))))
capture_path<-file.path(out,paste0(stock,'_BUGSoutput.rds'))
config<-read.csv(file.path(root,'scenario','jabba_sampler_config.csv'))
K_start<-config$Initial_K_Mt[match(stock,config$Stock)]
stopifnot(length(K_start)==1,is.finite(K_start),K_start>0)
# Fixed initialisation makes refits independent of whichever fit is currently
# promoted in ED5. It changes burn-in starts only, never the target density.
if(sampler=='qK') {
  source(file.path(root,'scenario','jabba_qK_sampler.r'))
  fit_jabba<-make_qK_fit(K_start)
} else if(sampler=='B0') {
  source(file.path(root,'scenario','jabba_b0_sampler.r'))
  fit_jabba<-make_b0_fit(K_start)
} else fit_jabba<-JABBA::fit_jabba
trace('fit_jabba',where=.GlobalEnv,print=FALSE,exit=quote({
    b<-mod$BUGSoutput
    nms<-dimnames(b$sims.array)[[3]]
    keep<-rep(TRUE,length(nms))
    # Exact chain identities plus full classical summaries; no synthetic chain splitting.
    compact<-list(sims.array=b$sims.array[,,keep,drop=FALSE],summary=b$summary,
                  n.iter=ni,n.burnin=nb,n.thin=nt,n.chains=nc,
                  original_parameter_names=nms)
    saveRDS(compact,capture_path)
}))
fit<-fit_jabba(x$input,quickmcmc=FALSE,ni=ni,nb=nb,nt=nt,nc=4,seed=seed,
              save.csvs=FALSE,output.dir=out,verbose=FALSE)
untrace('fit_jabba',where=.GlobalEnv)
x$fit<-fit;x$sampling_seed<-seed;x$prior_change<-prior_mode=='range';x$prior_interpretation<-prior_mode;x$sampler<-sampler;x$Initial_K_Mt<-K_start
saveRDS(x,file.path(out,paste0(stock,'_fit.rds')))
b<-readRDS(capture_path);ar<-b$sims.array
stopifnot(dim(ar)[2]==4,dim(ar)[1]==(ni-nb)/nt)
core<-grepl('^(r|K|psi|sigma2|q\\[[0-9]+\\]|P\\[55\\]|F\\[55\\]|MSY)$',dimnames(ar)[[3]])
wide<-do.call(rbind,lapply(seq_len(dim(ar)[2]),function(j) {
    d<-as.data.frame(ar[,j,core]);d$Chain<-j;d$Draw<-seq_len(nrow(d));d
}))
write.csv(wide,file.path(out,paste0(stock,'_Core_Draws.csv')),row.names=FALSE)
ts<-fit$timeseries
write.csv(data.frame(Stock=stock,r=fit$estimates['r','mu'],K_Mt=fit$estimates['K','mu'],
 B2024_Mt=tail(ts[,'mu','B'],1),B2024_K=tail(ts[,'mu','BB0'],1),
 B2024_K_lo=tail(ts[,'lci','BB0'],1),B2024_K_hi=tail(ts[,'uci','BB0'],1),
 MSY_Mt=fit$estimates['MSY','mu'],ni=ni,nb=nb,nt=nt,nc=4,
 Actual_Retained_Draws=prod(dim(ar)[1:2]),Seed=seed),
 file.path(out,paste0(stock,'_Summary.csv')),row.names=FALSE)
writeLines('COMPLETE',file.path(out,paste0(stock,'_Complete.txt')))
cat('REFIT_COMPLETE',stock,'\n')
