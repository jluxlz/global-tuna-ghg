library(JABBA)
root<-normalizePath('.',winslash='/')
out<-file.path(root,'analysis','si_rebuild_20261012','sampling_geometry');dir.create(out,showWarnings=FALSE)
x<-readRDS(file.path(root,'figures','supplement','Supplementary_Fig6','jabba_diagnostics','SBT_fit.rds'))
JABBA::jabba2jags(x$input,out)
rows<-list()
for(s in c('SKJ','ALB')) {
 path<-file.path(root,'analysis','si_rebuild_20261012','mcmc_refits','sampling_60000',paste0(s,'_Core_Draws.csv'))
 d<-read.csv(path,check.names=FALSE)
 pars<-c('r','K','psi','sigma2',grep('^q\\[',names(d),value=TRUE))
 cc<-cor(log(as.matrix(d[,pars])),use='complete.obs')
 a<-as.data.frame(as.table(cc));a$Stock<-s;names(a)[1:3]<-c('Parameter1','Parameter2','Correlation_log')
 rows[[s]]<-a
}
write.csv(do.call(rbind,rows),file.path(out,'Posterior_Log_Correlations.csv'),row.names=FALSE)
cat('GEOMETRY_COMPLETE\n')
