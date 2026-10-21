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

a<-read_panel(13,'PanelA_MC');b<-read_panel(13,'PanelB_Scenarios')
p_a<-ggplot(a,aes(Year,Total_median/1e6))+geom_ribbon(aes(ymin=Total_p5/1e6,ymax=Total_p95/1e6),fill='#0072B2',alpha=.2)+
 geom_line(colour='#0072B2',linewidth=.5)+labs(tag='(a)',x='Year',y='Historical emissions (Mt CO2e)',title='Central 90% Monte Carlo range')+theme_pub
p_b<-ggplot(b,aes(Year,Median))+geom_ribbon(aes(ymin=p5,ymax=p95),fill='#DAE6EB')+
 geom_ribbon(aes(ymin=p25,ymax=p75),fill='#98B6C4')+geom_line(linewidth=.5,colour='#355E72')+
 facet_wrap(~Rule,nrow=1)+labs(tag='(b)',x='Year',y='No-transition emissions (Mt CO2e)',title='81 specified futures within each HCR')+theme_pub
fig<-p_a/p_b

for(ext in c('pdf','png','tiff')) {
 options<-list(filename=file.path(HERE,paste0('Supplementary_Fig13_Uncertainty_Ranges.',ext)),plot=fig,width=183,height=150,units='mm',bg='white')
 if(ext=='pdf') options$device<-cairo_pdf
 if(ext=='png') options$dpi<-300
 if(ext=='tiff') {options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
