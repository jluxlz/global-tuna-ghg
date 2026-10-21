# Three simplified harvest control rules under common stock-fleet constraints.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork);library(scales)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
read_panel<-function(label){
 path<-file.path(HERE,paste0('Fig5_HCR_',label,'.csv'))
 header<-names(read.csv(path,nrows=0))
 classes<-setNames(rep(NA_character_,length(header)),header)
 classes[intersect(c('Technical','Base_Rule','Policy_Rule'),header)]<-'character'
 d<-read.csv(path,colClasses=classes)
 write.csv(d,file.path(HERE,paste0('Fig5_HCR_',label,'_Render_Data.csv')),row.names=FALSE,na='')
 d
}
theme_pub<-theme_classic(base_size=7,base_family='Arial')+theme(
 axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),
 axis.line=element_line(linewidth=.22),axis.ticks=element_line(linewidth=.22),
 strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),
 plot.title=element_text(size=7.5,face='bold',margin=margin(b=3)),
 plot.tag=element_text(size=8,face='bold'),plot.tag.position='topleft',
 legend.position='bottom',legend.text=element_text(size=6),legend.title=element_blank(),
 legend.key.height=unit(2.5,'mm'),legend.key.width=unit(7,'mm'),legend.box='horizontal',
 legend.margin=margin(0,0,0,0),legend.spacing=unit(1,'mm'),
 panel.spacing=unit(3,'mm'),plot.margin=margin(4,5,4,4,'pt'))
hcr_cols<-c(C='#666F77',F='#0072B2',T='#009E73')
hcr_labs<-c(C='C: constant catch',F='F: harvest rate',T='T: biomass threshold')
measure_cols<-c('Fuel transition'='#D55E00','Refrigeration transition'='#56B4E9',
 'Fleet consolidation'='#9B6BA8','Combined technical measures'='#333333')
col_hcr<-function()scale_colour_manual(values=hcr_cols,labels=hcr_labs,name=NULL)
fill_hcr<-function()scale_fill_manual(values=hcr_cols,labels=hcr_labs,name=NULL)

a<-read_panel('PanelA_Summary');a$Rule<-factor(a$Rule,levels=names(hcr_cols))
pa<-ggplot(a,aes(Year,Median,colour=Rule,fill=Rule))+
 geom_ribbon(aes(ymin=P5,ymax=P95),alpha=.12,colour=NA)+geom_line(linewidth=.65)+
 col_hcr()+fill_hcr()+scale_x_continuous(breaks=seq(2025,2050,5))+
 labs(tag='(a)',title='Quota rules change future emissions',x='Year',y=expression(Annual~GHG~(Mt~CO[2]*e)))+theme_pub+
 guides(colour=guide_legend(nrow=1),fill=guide_legend(nrow=1))

b<-read_panel('PanelB_Period')%>%select(Future,Rule,Catch_Mt,GHG_Mt,Period_CEI,Min_Stock_Bmsy_2050)%>%
 pivot_longer(c(Catch_Mt,GHG_Mt,Period_CEI,Min_Stock_Bmsy_2050),names_to='Metric',values_to='Value')
b$Rule<-factor(b$Rule,levels=names(hcr_cols))
b$Metric<-factor(b$Metric,levels=c('Catch_Mt','GHG_Mt','Period_CEI','Min_Stock_Bmsy_2050'),
 labels=c('Cumulative catch\n(Mt)','Cumulative GHG\n(Mt CO2e)','Period CEI\n(t CO2e/t catch)','Lowest stock ratio\n(B2050 / BMSY)'))
pb<-ggplot(b,aes(Rule,Value,colour=Rule,fill=Rule))+
 geom_boxplot(width=.48,outlier.shape=NA,alpha=.15,linewidth=.3)+
 geom_point(position=position_jitter(width=.12,seed=17),size=.5,alpha=.3)+
 facet_wrap(~Metric,nrow=1,scales='free_y')+col_hcr()+fill_hcr()+
 labs(tag='(b)',title='Output, intensity and stocks distinguish the emission pathways',x=NULL,y='Period total or ratio')+
 theme_pub+theme(legend.position='none',strip.text=element_text(size=6.1))

c<-read_panel('PanelC_Fuel')%>%pivot_longer(c(Cumulative_Abatement_Mt,Cumulative_Reduction_pct),names_to='Metric',values_to='Value')
c$Rule<-factor(c$Rule,levels=names(hcr_cols))
c$Metric<-factor(c$Metric,levels=c('Cumulative_Abatement_Mt','Cumulative_Reduction_pct'),
 labels=c('Avoided GHG (Mt CO2e)','GHG reduction (%)'))
pc<-ggplot(c,aes(Rule,Value,colour=Rule,fill=Rule))+
 geom_hline(yintercept=0,colour='grey70',linewidth=.22)+
 geom_boxplot(width=.48,outlier.shape=NA,alpha=.15,linewidth=.3)+
 geom_point(position=position_jitter(width=.12,seed=17),size=.48,alpha=.3)+
 facet_wrap(~Metric,ncol=2,scales='free_y')+col_hcr()+fill_hcr()+
 labs(tag='(c)',title='Fuel benefits depend on the quota rule',x=NULL,y=NULL)+theme_pub+
 theme(legend.position='none',strip.text=element_text(size=6))

d<-read_panel('PanelD_Technical')
d$Measure<-factor(d$Technical,levels=c('100','010','001','111'),labels=names(measure_cols))
d$Rule<-factor(d$Rule,levels=names(hcr_cols))
# Position all technical measures side by side within each HCR.
pd<-ggplot(d,aes(Rule,Cumulative_Reduction_pct,colour=Measure,fill=Measure))+
 geom_hline(yintercept=0,colour='grey65',linewidth=.22)+
 geom_boxplot(position=position_dodge(.75),width=.62,outlier.shape=NA,alpha=.16,linewidth=.3)+
 scale_colour_manual(values=measure_cols,labels=c('Fuel','Refrigeration','Consolidation','Combined'))+
 scale_fill_manual(values=measure_cols,labels=c('Fuel','Refrigeration','Consolidation','Combined'))+
 labs(tag='(d)',title='Technical measures share a fishing-activity basis',x=NULL,y='Cumulative GHG reduction (%)')+theme_pub+
 guides(colour=guide_legend(ncol=2,byrow=TRUE),fill=guide_legend(ncol=2,byrow=TRUE))

e<-read_panel('PanelE_Matched');es<-read_panel('PanelE_Summary')
# Matched triples retain their absolute GHG and all paired relative effects.
future_order<-c('F13','F14','F15','F40','F41','F42','F67','F68','F69')
future_labels<-paste(rep(c('STEPS','APS','NZE'),each=3),rep(c('1.9%','2.4%','4.3%'),3),sep=' | ')
e$Future<-factor(e$Future,levels=rev(future_order))
e$Comparison<-factor(e$Comparison,levels=c('CF','CT','FT'))
abs_e<-bind_rows(e%>%transmute(Future,Rule=Base_Rule,GHG_Mt=Base_GHG_Mt),
 e%>%transmute(Future,Rule=Policy_Rule,GHG_Mt=Policy_GHG_Mt))%>%distinct()
abs_e$Rule<-factor(abs_e$Rule,levels=names(hcr_cols))
links<-abs_e%>%group_by(Future)%>%summarise(lo=min(GHG_Mt),hi=max(GHG_Mt),.groups='drop')
write.csv(abs_e,file.path(HERE,'Fig5_HCR_PanelE_Absolute_Render_Data.csv'),row.names=FALSE)
pe_abs<-ggplot(abs_e,aes(y=Future))+
 geom_segment(data=links,aes(x=lo,xend=hi,yend=Future),colour='#CFD5D8',linewidth=1)+
 geom_point(aes(x=GHG_Mt,colour=Rule,shape=Rule),size=1.55,stroke=.5)+
 col_hcr()+scale_shape_manual(values=c(C=16,F=17,T=15))+
 scale_y_discrete(labels=setNames(rev(future_labels),rev(future_order)))+
 scale_x_continuous(labels=label_number(accuracy=1),n.breaks=3,expand=expansion(mult=c(.1,.1)))+
 labs(tag='(e)',title='Comparable output: GHG',x=expression(Cumulative~GHG~(Mt~CO[2]*e)),y=NULL)+
 theme_pub+theme(legend.position='none',axis.text.y=element_text(size=5.6),plot.title=element_text(size=6.5,face='bold'))
facet_names<-setNames(sprintf('%s\nMedian +%.1f%%',c('F relative to C','T relative to C','T relative to F'),es$Median_GHG_Reduction_pct),es$Comparison)
pe_rel<-ggplot(e,aes(y=Future,x=Whole_Fleet_GHG_Reduction_pct))+
 geom_segment(aes(x=0,xend=Whole_Fleet_GHG_Reduction_pct,yend=Future),colour='#D9E2E6',linewidth=.8)+
 geom_point(aes(colour=Policy_Rule),size=1.55)+
 scale_colour_manual(values=hcr_cols)+
 facet_wrap(~Comparison,nrow=1,scales='free_x',labeller=as_labeller(facet_names))+
 scale_y_discrete(labels=NULL)+scale_x_continuous(n.breaks=3,expand=expansion(mult=c(.03,.12)))+
 labs(title='Paired GHG savings at comparable output',x='Cumulative reduction (%) | separate scales',y=NULL)+
 theme_pub+theme(legend.position='none',axis.ticks.y=element_blank(),axis.line.y=element_blank(),
 strip.text=element_text(size=5.8,face='bold'),plot.title=element_text(size=6.5,face='bold'))
pe<-(pe_abs|pe_rel)+plot_layout(widths=c(1.05,1.85))

# Legends wrap only where the actual panel width requires it.
source(file.path(HERE,'Legend_Layout.r'))
pa<-horizontal_legend_plot(pa,174,'Fig5a')
pd<-horizontal_legend_plot(pd,83,'Fig5d')
fig<-pa/pb/(pc|pd)/pe+plot_layout(heights=c(.95,.95,1.12,1.28))
ggsave(file.path(HERE,'Fig5_Mitigation_Evidence.pdf'),fig,width=183,height=247,units='mm',device=cairo_pdf,bg='white')
ggsave(file.path(HERE,'Fig5_Mitigation_Evidence.png'),fig,width=183,height=247,units='mm',dpi=300,device=grDevices::png,type='cairo',bg='white')
ggsave(file.path(HERE,'Fig5_Mitigation_Evidence.tiff'),fig,width=183,height=247,units='mm',dpi=900,device=grDevices::tiff,type='cairo',compression='lzw',bg='white')
cat('Fig5 C/F/T evidence rendered; panel data preserved.\n')
