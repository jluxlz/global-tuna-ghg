library(ggplot2)
library(patchwork)
args<-commandArgs(trailingOnly=FALSE)
HERE<-normalizePath(dirname(sub('^--file=','',grep('^--file=',args,value=TRUE)[1])))
setwd(HERE)
a<-read.csv('Supplementary_Fig15_Annual.csv')
b<-read.csv('Supplementary_Table11_Engine_Clock.csv')
c<-read.csv('Supplementary_Fig15_LL_Benchmark.csv')
lev<-c('24/12 h','18/9 h','12/6 h')
for(n in c('a','b','c')) {d<-get(n);d$Scenario<-factor(d$Scenario,levels=lev);assign(n,d)}
cols<-setNames(c('#444444','#0072B2','#009E73'),lev)
base<-theme_classic(base_size=7,base_family='sans')+theme(
 plot.tag=element_text(face='bold',size=8),plot.title=element_text(face='bold',size=7),
 axis.text=element_text(size=6,colour='black'),axis.title=element_text(size=7),
 legend.position='bottom',legend.direction='horizontal',legend.title=element_text(size=7),
 legend.text=element_text(size=6),plot.margin=margin(4,5,3,4,'pt'))
pa<-ggplot(a,aes(Year,Median_Mt,colour=Scenario,fill=Scenario))+
 geom_ribbon(aes(ymin=P5_Mt,ymax=P95_Mt),alpha=.12,colour=NA)+geom_line(linewidth=.5)+
 scale_colour_manual(values=cols)+scale_fill_manual(values=cols)+
 labs(tag='a',title='Annual inventory at fixed vessel states',x='Year',y=expression(GHG~(Mt~CO[2]*e)),colour='Engine clock: industrial/coastal',fill='Engine clock: industrial/coastal')+base
pb<-ggplot(b,aes(Scenario,Cumulative_Median_Mt,colour=Scenario))+
 geom_errorbar(aes(ymin=Cumulative_P5_Mt,ymax=Cumulative_P95_Mt),width=.16,linewidth=.4)+geom_point(size=2)+
 scale_colour_manual(values=cols,guide='none')+labs(tag='b',title='Cumulative GHG, 1950-2025',x=NULL,y=expression(GHG~(Mt~CO[2]*e)))+base
pc<-ggplot(c,aes(Scenario,Model_Fuel_L_t,fill=Scenario))+
 geom_col(width=.52)+scale_fill_manual(values=cols,guide='none')+
 geom_hline(yintercept=unique(c$Literature_Fuel_L_t),linetype='dashed',linewidth=.4)+
 annotate('text',x=2.7,y=unique(c$Literature_Fuel_L_t)+220,label='Survey: 1,523.3',size=2,hjust=1)+
 labs(tag='c',title='Pacific longline fuel, 2023',x=NULL,y=expression(Fuel~(L~t^{-1}~catch)))+base
fig<-pa/(pb|pc)+plot_layout(heights=c(1.1,1))
for(ext in c('pdf','png','tiff')) {
 f<-paste0('Supplementary_Fig15_Engine_Clock.',ext)
 if(ext=='pdf')ggsave(f,fig,width=183,height=140,units='mm',device=cairo_pdf,bg='white')
 else if(ext=='png')ggsave(f,fig,width=183,height=140,units='mm',dpi=300,bg='white')
 else ggsave(f,fig,width=183,height=140,units='mm',dpi=900,compression='lzw',bg='white')
}
