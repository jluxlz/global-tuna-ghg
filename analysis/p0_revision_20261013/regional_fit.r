# Independent regional fits; existing production JABBA outputs are read-only.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)>=1)
stock<-args[1];mode<-if(length(args)>1)args[2] else 'base'
root<-normalizePath('.',winslash='/');base<-file.path(root,'analysis/p0_revision_20261013')
out<-file.path(base,'regional_fits',paste0(stock,'_',mode));dir.create(out,recursive=TRUE,showWarnings=FALSE)
library(JABBA);.libPaths(c(file.path(root,'scenario/r_lib'),.libPaths()));library(posterior)
catch<-read.csv(file.path(base,'regional_inputs',paste0(stock,'_catch.csv')))
cpue<-read.csv(file.path(base,'regional_inputs',paste0(stock,'_cpue.csv')))
se<-read.csv(file.path(base,'regional_inputs',paste0(stock,'_se.csv')))
isbet<-grepl('BET',stock)
# Original r and K priors retained for a controlled regional-data comparison.
# Weak initial depletion is an assumption, not current official stock status.
rp<-if(isbet)c(.35,.3) else c(.4,.3)
if(mode=='wide_r')rp[2]<-.6
jb<-build_jabba(catch=catch,cpue=cpue,se=se,assessment=stock,model.type='Schaefer',
 r.prior=rp,r.dist='lnorm',K.prior=c(2,80),K.dist='lnorm',
 psi.prior=c(.8,1),psi.dist='lnorm',verbose=FALSE)
source(file.path(root,'scenario/jabba_qK_sampler.r'))
fit_jabba<-make_qK_fit(if(isbet)1 else 4)
ftext<-paste(deparse(body(fit_jabba)),collapse='\n')
# JABBA's downstream curve grid starts at 1 even when K<1 Mt, giving a
# wrong-sign seq() error after successful sampling. This only fixes that grid.
ftext<-gsub('Bit = seq(1, median(posteriors$K), median(posteriors$K)/500)',
 'Bit = seq(0, median(posteriors$K), length.out = 501)',ftext,fixed=TRUE)
body(fit_jabba)<-parse(text=ftext)[[1]]
regional_capture_file<-file.path(out,'BUGSoutput.rds')
trace('fit_jabba',where=.GlobalEnv,print=FALSE,exit=quote({
 b<-mod$BUGSoutput;saveRDS(list(sims.array=b$sims.array,summary=b$summary),get('regional_capture_file',envir=.GlobalEnv))
}))
ni<-as.integer(Sys.getenv('REGIONAL_JABBA_NI','120000'))
nb<-as.integer(Sys.getenv('REGIONAL_JABBA_NB','30000'));nt<-10L
fit<-fit_jabba(jb,quickmcmc=FALSE,ni=ni,nb=nb,nt=nt,nc=4,seed=42013,
 save.csvs=FALSE,output.dir=out,verbose=FALSE)
untrace('fit_jabba',where=.GlobalEnv)
saveRDS(list(input=jb,fit=fit,catch=catch,cpue=cpue,se=se,seed=42013),file.path(out,'fit.rds'))
b<-readRDS(file.path(out,'BUGSoutput.rds'));a<-b$sims.array;nms<-dimnames(a)[[3]]
terminal<-paste0('P[',nrow(catch),']')
selected<-grep('^(r|K|psi|sigma2|q\\[[0-9]+\\]|MSY|P\\[[0-9]+\\])$',nms,value=TRUE)
qc<-do.call(rbind,lapply(selected,function(p){m<-a[,,p];data.frame(Parameter=p,Rhat=posterior::rhat(m),ESS_Bulk=posterior::ess_bulk(m),ESS_Tail=posterior::ess_tail(m))}))
qc$Pass<-with(qc,is.finite(Rhat)&Rhat<=1.01&ESS_Bulk>=400&ESS_Tail>=400)
write.csv(qc,file.path(out,'Rank_Diagnostics.csv'),row.names=FALSE)
scale<-mean(catch$Catch)
draws<-data.frame(r=as.vector(a[,,'r']),K_Mt=as.vector(a[,,'K'])*scale,B_Terminal_Mt=as.vector(a[,,'K']*a[,,terminal])*scale)
write.csv(draws,file.path(out,'Parameter_Draws.csv'),row.names=FALSE)
ts<-fit$timeseries
write.csv(data.frame(Year=catch$Year,B_Mt=ts[,'mu','B'],B_Lower=ts[,'lci','B'],B_Upper=ts[,'uci','B'],B_K=ts[,'mu','BB0']),file.path(out,'Fitted_Trajectory.csv'),row.names=FALSE)
summary<-data.frame(Stock=stock,First_Year=min(catch$Year),Terminal_Year=max(catch$Year),
 r=median(draws$r),K_Mt=median(draws$K_Mt),B_Terminal_Mt=median(draws$B_Terminal_Mt),
 Catch_Terminal_Mt=tail(catch$Catch,1),Max_Rhat=max(qc$Rhat),Min_Bulk=min(qc$ESS_Bulk),Min_Tail=min(qc$ESS_Tail),
 QC_Pass=all(qc$Pass),Prior_Mode=mode)
write.csv(summary,file.path(out,'Summary.csv'),row.names=FALSE)
cat('FIT_COMPLETE',stock,mode,'QC',all(qc$Pass),'\n')
