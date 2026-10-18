# External descriptive benchmarks; no fitting or scenario generation.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
d<-read.csv(file.path(HERE,'Supplementary_Table10_Benchmark.csv'))
theme_pub<-theme_classic(base_size=7,base_family='Arial')+theme(
 axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),
 strip.text=element_text(size=7,face='bold'),plot.title=element_text(size=8,face='bold'),
 plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.title=element_blank(),
 legend.text=element_text(size=7),plot.margin=margin(5,7,5,5,'pt'),axis.line=element_line(linewidth=.2))
col<-c(Model='#0072B2',Literature='#D55E00')
plot_pair<-function(s,tag,title,xlab){
 s$Label<-paste(s$Activity_year,s$Region,sep=' | ')
 s$Label<-factor(s$Label,levels=rev(unique(s$Label)))
 write.csv(s,file.path(HERE,paste0('Supplementary_Fig14_Panel',toupper(tag),'_Render_Data.csv')),row.names=FALSE)
 l<-s%>%pivot_longer(c(Model,Literature),names_to='Estimate',values_to='Value')
 ggplot(s,aes(y=Label))+geom_segment(aes(x=Literature,xend=Model,yend=Label),colour='grey70',linewidth=.5)+
  geom_point(data=l,aes(x=Value,colour=Estimate,shape=Estimate),size=2.2,stroke=.6)+
  scale_colour_manual(values=col)+scale_shape_manual(values=c(Model=16,Literature=1))+
  scale_x_continuous(expand=expansion(mult=c(.05,.1)),limits=c(0,NA))+
  labs(tag=paste0('(',tag,')'),title=title,x=xlab,y=NULL)+theme_pub
}
a<-plot_pair(filter(d,Metric=='Fuel use',Gear=='PS'),'a','Purse-seine fuel use','Fuel (L per t catch)')
b<-plot_pair(filter(d,Metric=='Fuel use',Gear=='LL'),'b','Longline fuel use','Fuel (L per t catch)')
s<-filter(d,Metric=='Fuel combustion GHG');s$Region<-paste(s$Region,s$Gear,sep=' | ')
c<-plot_pair(s,'c','Fuel combustion GHG in 2023',expression(t~CO[2]*e~per~t~catch))
e<-filter(d,Metric=='Full LCA CEI');e$Region<-'Spanish PS'
dd<-plot_pair(e,'d','Full LCA context: different boundaries',expression(t~CO[2]*e~per~t~catch))
fig<-((a|b)/(c|dd))+plot_layout(heights=c(1.1,1),guides='collect') & theme(legend.position='bottom')
for(ext in c('pdf','png','tiff')){
 opts<-list(filename=file.path(HERE,paste0('Supplementary_Fig14_External_Benchmark.',ext)),plot=fig,width=183,height=155,units='mm',bg='white')
 if(ext=='pdf')opts$device<-cairo_pdf
 if(ext=='png')opts$dpi<-300
 if(ext=='tiff'){opts$dpi<-900;opts$compression<-'lzw'}
 do.call(ggsave,opts)
}
