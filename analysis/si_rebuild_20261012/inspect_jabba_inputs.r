library(JABBA)
root<-normalizePath('.')
dest<-file.path(root,'analysis','si_rebuild_20261012')
sink(file.path(dest,'JABBA_Build_Source.txt'));print(formals(build_jabba));print(build_jabba);sink()
rows<-list()
for(s in c('SKJ','YFT','BET','ALB','SBT')) {
 x<-readRDS(file.path(root,'figures','Extended_Data','Extended_Fig5','jabba_diagnostics',paste0(s,'_fit.rds')))
 rows[[s]]<-data.frame(Stock=s,K_prior=paste(x$input$settings$K.prior.raw,collapse=';'),r_prior=paste(x$input$settings$r.prior.raw,collapse=';'),psi_prior=paste(x$input$settings$psi.prior.raw,collapse=';'))
 saveRDS(x$input$settings,file.path(dest,paste0(s,'_Input_Settings.rds')))
}
write.csv(do.call(rbind,rows),file.path(dest,'JABBA_Prior_Distributions.csv'),row.names=FALSE)
writeLines(c(paste('posterior',requireNamespace('posterior',quietly=TRUE)),paste('rstan',requireNamespace('rstan',quietly=TRUE))),file.path(dest,'Diagnostic_Packages.txt'))
