suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
rd<-function(s){d<-read.csv(file.path(HERE,paste0('Extended_Fig7_HCR_Panel',s,'.csv')));write.csv(d,file.path(HERE,paste0('Extended_Fig7_HCR_Panel',s,'_Render_Data.csv')),row.names=FALSE);d}
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_blank(),plot.margin=margin(5,5,5,5),panel.spacing=unit(3,'mm'))
cc<-c(C='#666F77',F='#0072B2',T='#009E73')
a<-rd('A_Baselines')%>%group_by(Rule,TechCreep)%>%summarise(Median=median(Period_CEI),P5=quantile(Period_CEI,.05),P95=quantile(Period_CEI,.95),.groups='drop')
pa<-ggplot(a,aes(100*TechCreep,Median,colour=Rule))+geom_line(linewidth=.5)+geom_point(size=1.3)+geom_errorbar(aes(ymin=P5,ymax=P95),width=.05,linewidth=.25)+
 scale_colour_manual(values=cc)+scale_x_continuous(breaks=c(1.9,2.4,4.3))+
 labs(tag='(a)',x='Technology creep (% per year)',y='Period CEI (t CO2e/t catch)')+th
b<-rd('B_Fuel');b$Rate<-factor(100*b$TechCreep);b$WEO<-factor(b$WEO,levels=c('STEPS','APS','NZE'))
pb<-ggplot(b,aes(Rate,Cumulative_Reduction_pct,fill=Rule))+
 geom_hline(yintercept=0,colour='grey65',linewidth=.2)+geom_boxplot(width=.55,outlier.size=.3,linewidth=.25)+
 facet_grid(Rule~WEO)+scale_fill_manual(values=cc,guide='none')+
 labs(tag='(b)',x='Technology creep (% per year)',y='Cumulative fuel-transition reduction (%)')+th
fig<-pa/pb+plot_layout(heights=c(.8,1.8))
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Extended_Fig7_Technology_Creep_Robustness.',ext)),plot=fig,width=183,height=200,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
