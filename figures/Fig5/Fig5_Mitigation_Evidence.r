# Fig.5: saved paired simulations and cumulative-output experiments.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork);library(scales)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
read_panel<-function(label){d<-read.csv(file.path(HERE,paste0('Fig5_',label,'.csv')));write.csv(d,file.path(HERE,paste0('Fig5_',label,'_Render_Data.csv')),row.names=FALSE);d}
theme_pub<-theme_classic(base_size=7,base_family='Arial')+theme(
 axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),
 axis.line=element_line(linewidth=.18),axis.ticks=element_line(linewidth=.18),
 strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),
 plot.title=element_text(size=8,face='bold',margin=margin(b=4)),
 plot.tag=element_text(size=8,face='bold'),plot.tag.position='topleft',
 legend.position='bottom',legend.text=element_text(size=6),legend.title=element_text(size=7,face='bold'),
 legend.key.size=unit(3,'mm'),legend.box='vertical',panel.spacing=unit(3,'mm'),plot.margin=margin(4,5,4,4,'pt'))
baselines<-c('Fixed-catch pressure test','Resource-and-capacity rerun')
base_cols<-setNames(c('#666666','#0072B2'),baselines)
base_labs<-setNames(c('Fixed-catch target\nsimulation','Feasible-catch\nsimulation'),baselines)
measure_cols<-c(Quota='#AA4499',Fuel='#009E73',Combined='#D55E00')
weo_cols<-c(STEPS='#D55E00',APS='#0072B2',NZE='#009E73')
a<-read_panel('PanelA_BAU_Summary');a$Baseline<-factor(a$Baseline,levels=baselines)
end<-a%>%filter(Year==2050)%>%mutate(label=sprintf('%.1f',Median))
pa<-ggplot(a,aes(Year,Median,colour=Baseline,fill=Baseline))+
 geom_ribbon(aes(ymin=P5,ymax=P95),alpha=.14,colour=NA)+geom_line(linewidth=.7)+
 geom_text(data=end,aes(x=2051,label=label),hjust=0,size=2.5,show.legend=FALSE)+
 scale_colour_manual(values=base_cols,labels=base_labs,name=NULL)+scale_fill_manual(values=base_cols,labels=base_labs,name=NULL)+
 scale_x_continuous(breaks=seq(2025,2050,5),limits=c(2025,2054),expand=expansion(mult=c(.01,.01)))+
 labs(tag='(a)',title='Fishing feasibility changes the emission baseline',x='Year',y=expression(Annual~GHG~(Mt~CO[2]*e)))+theme_pub
b<-read_panel('PanelB_Paired_Reductions');b$Baseline<-factor(b$Baseline,levels=baselines);b$Measure<-factor(b$Measure,levels=names(measure_cols))
bs<-read_panel('PanelB_Reduction_Summary');bs$Baseline<-factor(bs$Baseline,levels=baselines);bs$Measure<-factor(bs$Measure,levels=names(measure_cols))
pb<-ggplot(b,aes(Measure,Reduction_pct,colour=Measure,fill=Measure))+
 geom_hline(yintercept=0,colour='grey65',linewidth=.18)+geom_boxplot(width=.48,outlier.shape=NA,alpha=.13,linewidth=.25)+
 geom_point(position=position_jitter(width=.13,seed=5),size=.62,alpha=.45)+
 geom_text(data=bs,aes(y=Median,label=sprintf('%.1f',Median)),colour='black',nudge_x=.36,hjust=0,size=2.1,show.legend=FALSE)+
 facet_wrap(~Baseline,labeller=as_labeller(base_labs),nrow=1)+
 scale_colour_manual(values=measure_cols,guide='none')+scale_fill_manual(values=measure_cols,guide='none')+
 scale_x_discrete(expand=expansion(add=c(.5,.9)))+
 labs(tag='(b)',title='Paired mitigation benefits',x=NULL,y='2050 GHG reduction (%)')+theme_pub
c<-read_panel('PanelC_Ranking');c$Baseline<-factor(c$Baseline,levels=baselines)
counts<-c%>%group_by(Baseline)%>%summarise(label=paste0(sum(Quota>Fuel),'/81 quota > fuel'),.groups='drop')
lim<-range(c(c$Quota,c$Fuel));lim<-c(floor(min(0,lim[1])/10)*10,ceiling(lim[2]/10)*10)
pc<-ggplot(c,aes(Fuel,Quota,colour=Baseline))+
 geom_abline(slope=1,intercept=0,linetype='dashed',colour='grey50',linewidth=.25)+geom_point(size=.95,alpha=.7)+
 geom_text(data=counts,aes(x=lim[1]+3,y=lim[2]-3,label=label),inherit.aes=FALSE,hjust=0,vjust=1,size=2.15)+
 facet_wrap(~Baseline,labeller=as_labeller(base_labs),nrow=1)+scale_colour_manual(values=base_cols,guide='none')+
 coord_equal(xlim=lim,ylim=lim)+labs(tag='(c)',title='The quota-fuel ordering shifts',x='Fuel reduction in 2050 (%)',y='Quota reduction in 2050 (%)')+theme_pub
d<-read_panel('PanelD_Period_Changes');d$Metric<-factor(d$Metric,levels=c('Catch','GHG','CEI'))
ds<-read_panel('PanelD_Period_Summary');ds$Metric<-factor(ds$Metric,levels=levels(d$Metric))
metric_labs<-c(Catch='Cumulative catch',GHG='Cumulative GHG',CEI='Period CEI')
pd<-ggplot(d,aes(Change_pct,1))+
 geom_vline(xintercept=0,colour='grey60',linetype='dashed',linewidth=.2)+
 geom_boxplot(aes(group=Metric),orientation='y',width=.35,outlier.shape=NA,fill='#E5D1E5',colour=measure_cols['Quota'],linewidth=.25)+
 geom_point(position=position_jitter(height=.09,seed=5),size=.6,alpha=.4,colour=measure_cols['Quota'])+
 geom_text(data=ds,aes(x=Median,y=1.28,label=sprintf('Median: %+.1f%%',Median)),size=2.15,vjust=0)+
 facet_wrap(~Metric,ncol=1,scales='free_x',labeller=as_labeller(metric_labs))+
 scale_y_continuous(limits=c(.77,1.5),breaks=NULL)+scale_x_continuous(labels=label_number(accuracy=1),expand=expansion(mult=c(.08,.12)))+
 labs(tag='(d)',title='Quota changes catch and intensity',x='Change from paired BAU, 2025-2050 (%)',y=NULL)+theme_pub+
 theme(axis.line.y=element_blank(),axis.ticks.y=element_blank(),strip.text=element_text(hjust=0),panel.spacing=unit(2,'mm'))
e<-read_panel('PanelE_Matched_Catch');e$WEO<-factor(e$WEO,levels=names(weo_cols))
el<-e%>%pivot_longer(c(C_GHG_Mt,F_GHG_Mt),names_to='Rule',values_to='GHG_Mt')%>%mutate(Rule=factor(Rule,levels=c('C_GHG_Mt','F_GHG_Mt')))
pe<-ggplot(el,aes(Rule,GHG_Mt,group=Future,colour=WEO))+
 geom_line(linewidth=.4,alpha=.7)+geom_point(aes(shape=factor(TechCreep)),size=1.8)+
 scale_colour_manual(values=weo_cols,name='WEO')+scale_shape_manual(values=c(16,17,15),name='Technology creep',labels=c('1.9%/yr','2.4%/yr','4.3%/yr'))+
 scale_x_discrete(labels=c(C_GHG_Mt='C-type\n65% MSY',F_GHG_Mt='Adjusted\nF-type'))+
 labs(tag='(e)',title='Lower GHG at comparable cumulative catch',subtitle=sprintf('Nine pairs; catch gap <=1%%; median reduction %.1f%%',median(e$GHG_Reduction_pct)),x=NULL,y=expression(Cumulative~GHG~(Mt~CO[2]*e)))+theme_pub+
 theme(plot.subtitle=element_text(size=6),legend.key.width=unit(4,'mm'))+guides(colour=guide_legend(nrow=1),shape=guide_legend(nrow=1))
source(file.path(HERE,"Legend_Layout.r"))
pe_layout<-horizontal_legend_plot(pe,83,"Fig5e")
fig<-pa/(pb|pc)/(pd|pe_layout)+plot_layout(heights=c(.78,1,1.32))
save_plot<-function(p,name,w,h,tif=FALSE){
 ggsave(file.path(HERE,paste0(name,'.pdf')),p,width=w,height=h,units='mm',device=cairo_pdf,bg='white')
 ggsave(file.path(HERE,paste0(name,'.png')),p,width=w,height=h,units='mm',dpi=300,bg='white')
 if(tif)ggsave(file.path(HERE,paste0(name,'.tiff')),p,width=w,height=h,units='mm',dpi=900,compression='lzw',bg='white')
}
save_plot(fig,'Fig5_Mitigation_Evidence',183,230,TRUE)
for(i in seq_along(list(pa,pb,pc,pd,pe)))save_plot(list(pa,pb,pc,pd,pe)[[i]],paste0('Fig5_Story_Panel',LETTERS[i]),if(i==1)183 else 90,if(i==1)65 else 85)
cat('Fig5 evidence layout rendered.\n')
