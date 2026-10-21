# External descriptive benchmarks; preserve partial matches and boundary context.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork);library(scales)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
d<-read.csv(file.path(HERE,'Supplementary_Table10_Benchmark.csv'))
m<-read.csv(file.path(HERE,'Model_Matched_Summaries.csv'))
theme_pub<-theme_classic(base_size=7.5,base_family='Arial')+theme(
 axis.title=element_text(size=7.5),axis.text=element_text(size=6.5,colour='#263940'),
 strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),
 plot.title=element_text(size=8,face='bold'),plot.subtitle=element_text(size=6.5,colour='#52616A'),
 plot.tag=element_text(size=9,face='bold'),legend.position='bottom',legend.title=element_blank(),
 legend.text=element_text(size=6.5),plot.margin=margin(5,9,6,5,'pt'),axis.line=element_line(linewidth=.22))
col<-c(Model='#0072B2',Literature='#D55E00')
fuel<-filter(d,Metric=='Fuel use')%>%mutate(Label=paste(Activity_year,Region,sep=' | '))
plot_pair<-function(s,tag,title){
 s$Label<-factor(s$Label,levels=rev(unique(s$Label)))
 write.csv(s,file.path(HERE,paste0('Supplementary_Fig14_Panel',toupper(tag),'_Render_Data.csv')),row.names=FALSE)
 l<-s%>%pivot_longer(c(Model,Literature),names_to='Estimate',values_to='Value')
 l$Number<-format(round(l$Value),big.mark=',',trim=TRUE)
 ggplot(s,aes(y=Label))+
  geom_segment(aes(x=Literature,xend=Model,yend=Label),colour='#CAD4D9',linewidth=1)+
  geom_point(data=l,aes(x=Value,colour=Estimate,shape=Estimate),size=2.1,stroke=.65)+
  geom_text(data=l,aes(x=Value,label=Number,colour=Estimate,vjust=ifelse(Estimate=='Model',-1,1.7)),size=2.2,show.legend=FALSE)+
  scale_colour_manual(values=col)+scale_shape_manual(values=c(Model=16,Literature=1))+
  scale_x_continuous(expand=expansion(mult=c(0,.18)),limits=c(0,NA),labels=label_number(big.mark=','),n.breaks=4)+
  scale_y_discrete(expand=expansion(add=.7))+
  labs(tag=paste0('(',tag,')'),title=title,x='Fuel (L per t catch)',y=NULL)+theme_pub
}
pa<-plot_pair(filter(fuel,Gear=='PS'),'a','Purse-seine fuel comparisons')
pb<-plot_pair(filter(fuel,Gear=='LL'),'b','Longline fuel comparisons')
# All six fuel gaps, with exact benchmark populations retained.
gaps<-fuel%>%mutate(Label=paste(Gear,Label,sep=' | '),
 Evidence=ifelse(Independent_outcome,'External fuel outcome','Calibration-linked survey'),
 Gap_Label=sprintf('%+.1f%%',Difference_pct))
gaps$Label<-factor(gaps$Label,levels=rev(gaps$Label))
write.csv(gaps,file.path(HERE,'Supplementary_Fig14_PanelC_Render_Data.csv'),row.names=FALSE)
pc<-ggplot(gaps,aes(y=Label,x=Difference_pct))+
 geom_vline(xintercept=0,linetype='dashed',colour='#75858D',linewidth=.3)+
 geom_segment(aes(x=0,xend=Difference_pct,yend=Label,colour=Gear),linewidth=1.05,alpha=.55)+
 geom_point(aes(colour=Gear,shape=Evidence),size=2.2,stroke=.7)+
 geom_text(aes(label=Gap_Label,hjust=ifelse(Difference_pct<0,1.2,-.2)),size=2.6,colour='#263940')+
 scale_colour_manual(values=c(PS='#35968A',LL='#A25B54'))+
 scale_shape_manual(values=c('External fuel outcome'=16,'Calibration-linked survey'=1))+
 scale_x_continuous(limits=c(-55,275),breaks=c(0,100,200),labels=function(x)paste0(x,'%'))+
 labs(tag='(c)',title='Fuel gaps are larger for longline in the retained comparisons',
 subtitle='Descriptive difference = 100 \u00d7 (model / literature - 1); exact fleet coverage remains unmatched',x='Difference from literature',y=NULL)+
 theme_pub+guides(colour='none',shape=guide_legend(nrow=1))
# Derived components share the same matched model numerator/denominator.
parts<-filter(m,Benchmark_ID%in%c('PS23','LL23'))%>%
 transmute(Benchmark_ID,Gear,Combustion=Model_combustion_tCO2e_t,
 'Fuel supply'=Model_fuel_lifecycle_tCO2e_t-Model_combustion_tCO2e_t,
 'Other LCA'=Model_full_CEI_tCO2e_t-Model_fuel_lifecycle_tCO2e_t)%>%
 pivot_longer(c('Combustion','Fuel supply','Other LCA'),names_to='Component',values_to='Value')
parts$Component<-factor(parts$Component,levels=c('Combustion','Fuel supply','Other LCA'))
bench<-filter(d,Metric=='Fuel combustion GHG')
write.csv(parts,file.path(HERE,'Supplementary_Fig14_PanelD_Render_Data.csv'),row.names=FALSE)
write.csv(bench,file.path(HERE,'Supplementary_Fig14_PanelD_Survey_Render_Data.csv'),row.names=FALSE)
pd<-ggplot(parts,aes(y='Model',x=Value,fill=Component))+
 geom_col(width=.4,position=position_stack(reverse=TRUE))+
 geom_point(data=bench,aes(x=Literature,y='Survey combustion'),inherit.aes=FALSE,shape=23,fill='#D55E00',colour='white',size=2.4)+
 facet_wrap(~Gear,nrow=1,scales='free_x')+
 scale_fill_manual(values=c(Combustion='#4F8DAE','Fuel supply'='#9EC1D0','Other LCA'='#DBE4E9'))+
 scale_x_continuous(limits=c(0,NA),n.breaks=3,expand=expansion(mult=c(0,.08)))+
 labs(tag='(d)',title='GHG boundaries are kept separate',subtitle='2023 scopes; separate facet scales',x=expression(t~CO[2]*e~per~t~catch),y=NULL)+theme_pub+
 theme(legend.key.width=unit(4,'mm'))+guides(fill=guide_legend(nrow=1))
# Retain the full-LCA context row, explicitly not an independent validation.
context<-filter(d,Metric=='Full LCA CEI')
write.csv(context,file.path(HERE,'Supplementary_Fig14_PanelE_Render_Data.csv'),row.names=FALSE)
pe<-ggplot(context,aes(y=1))+
 geom_segment(aes(x=Literature,xend=Model,yend=1),colour='#CAD4D9',linewidth=1)+
 geom_point(aes(x=Model),colour=col['Model'],size=2.4)+geom_point(aes(x=Literature),colour=col['Literature'],shape=1,size=2.4,stroke=.7)+
 annotate('text',x=context$Model,y=1.27,label=sprintf('Model %.2f',context$Model),size=2.4,colour=col['Model'])+
 annotate('text',x=context$Literature,y=.73,label=sprintf('Literature %.2f',context$Literature),size=2.4,colour=col['Literature'])+
 scale_x_continuous(limits=c(1.2,2),breaks=c(1.2,1.6,2))+
 scale_y_continuous(limits=c(.5,1.5),breaks=NULL)+
 labs(tag='(e)',title='Full-LCA context: Spanish PS, 2003',subtitle='Delivery boundary and shared sources differ',x=expression(t~CO[2]*e~per~t~catch),y=NULL)+theme_pub+
 theme(axis.line.y=element_blank(),legend.position='none')
top<-((pa|pb)+plot_layout(guides='collect')) & theme(legend.position='bottom')
fig<-(top/pc/(pd|pe))+plot_layout(heights=c(1.1,1.2,1.05))
for(ext in c('pdf','png','tiff')){
 opts<-list(filename=file.path(HERE,paste0('Supplementary_Fig14_External_Benchmark.',ext)),plot=fig,width=183,height=202,units='mm',bg='white')
 if(ext=='pdf')opts$device<-cairo_pdf
 if(ext=='png')opts$dpi<-300
 if(ext=='tiff'){opts$dpi<-900;opts$compression<-'lzw'}
 do.call(ggsave,opts)
}
