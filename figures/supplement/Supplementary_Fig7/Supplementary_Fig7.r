# One figure per script; CSV inputs and rendered panel data stay in this folder.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork);library(scales)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
theme_pub<-theme_classic(base_size=7,base_family='Arial')+theme(
 axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),
 axis.line=element_line(linewidth=.2),axis.ticks=element_line(linewidth=.2),
 strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),
 plot.tag=element_text(size=8,face='bold'),legend.position='bottom',
 legend.text=element_text(size=6),legend.title=element_text(size=7,face='bold'),
 legend.key.size=unit(3,'mm'),panel.spacing=unit(3,'mm'),plot.margin=margin(4,5,4,4,'pt'))
cols<-c(LL='#B81D0A',PS='#1A7A8A',TP='#7570B3',SA='#E6AB02')
weo_cols<-c(STEPS='#D55E00',APS='#0072B2',NZE='#009E73')
read_panel<-function(n,label){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig',n,'_',label,'.csv')));write.csv(d,file.path(HERE,paste0('Supplementary_Fig',n,'_',label,'_Render_Data.csv')),row.names=FALSE);d}

b<-read_panel(7,'PanelA_Traces')%>%filter(Parameter%in%c('r','K','psi'))
b$Stock<-factor(b$Stock,levels=c('SKJ','YFT','BET','ALB','SBT'))
b$Parameter<-factor(b$Parameter,levels=c('r','K','psi'),labels=c('r','K (scaled JAGS units)','Initial depletion'))
fig<-ggplot(b,aes(Draw,Value,colour=factor(Chain)))+geom_line(linewidth=.15,alpha=.5)+
 facet_wrap(~Stock+Parameter,ncol=3,scales='free_y')+scale_colour_manual(values=c('1'='#0072B2','2'='#D55E00','3'='#009E73','4'='#CC79A7'),name='Chain')+
 labs(x='Retained draw within chain',y='Parameter value')+theme_pub

for(ext in c('pdf','png','tiff')) {
 options<-list(filename=file.path(HERE,paste0('Supplementary_Fig7_JABBA_Chain_Traces.',ext)),plot=fig,width=183,height=220,units='mm',bg='white')
 if(ext=='pdf') options$device<-cairo_pdf
 if(ext=='png') options$dpi<-300
 if(ext=='tiff') {options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
