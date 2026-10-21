library(JABBA)
root<-normalizePath('.',winslash='/')
path<-file.path(root,'analysis','si_rebuild_20261012','Prior_Semantics.txt')
sink(path);print(JABBA::plot_lnorm)
for(s in c('SKJ','SBT')) {
 x<-readRDS(file.path(root,'figures','Extended_Data','Extended_Fig5','jabba_diagnostics',paste0(s,'_fit.rds')))
 cat(s,'\n');print(x$input$jagsdata$K.pr)
}
sink()
