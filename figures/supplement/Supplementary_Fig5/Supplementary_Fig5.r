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

a<-read_panel(5,'PanelA_Identity');b<-read_panel(5,'PanelB_Regional')
p_a<-ggplot(a,aes(Effort_log_trend_pct+GHG_Effort_log_trend_pct,CEI_log_trend_pct,colour=Gear))+
 geom_abline(slope=1,intercept=0,colour='grey55',linewidth=.25)+geom_point(size=.55,alpha=.4)+
 scale_colour_manual(values=cols,name=NULL)+labs(tag='(a)',x='Sum of factor log trends (% yr-1)',y='CEI log trend (% yr-1)')+theme_pub
p_b<-ggplot(b,aes(Nominal_Xm*Nominal_Ym/10000,Xm*Ym/10000,colour=Gear))+
 geom_abline(slope=1,intercept=0,colour='grey55',linewidth=.25)+geom_point(size=1.5)+scale_x_log10()+scale_y_log10()+
 scale_colour_manual(values=cols,name=NULL)+labs(tag='(b)',x='Nominal factor product / 10,000',y='Corrected factor product / 10,000')+theme_pub
# LL and PS scaling differ; panel B therefore plots dimensionless corrected/nominal identity below.
b$Nominal_CEI<-ifelse(b$Gear=='LL',b$Nominal_Xm*b$Nominal_Ym/10000,b$Nominal_Xm*b$Nominal_Ym)
b$Corrected_CEI<-ifelse(b$Gear=='LL',b$Xm*b$Ym/10000,b$Xm*b$Ym)
p_b<-ggplot(b,aes(Nominal_CEI,Corrected_CEI,colour=Gear))+geom_abline(slope=1,intercept=0,colour='grey55',linewidth=.25)+
 geom_point(size=1.5)+scale_x_log10()+scale_y_log10()+scale_colour_manual(values=cols,name=NULL)+
 labs(tag='(b)',x='Nominal regional CEI (t CO2e t-1)',y='Corrected regional CEI (t CO2e t-1)')+theme_pub
write.csv(b,file.path(HERE,'Supplementary_Fig5_PanelB_Render_Data.csv'),row.names=FALSE)
# Analytical correction comparison on identical cells and fixed saved weights.
# These slopes are derived from existing fits, not newly refitted stock models.
q<-read.csv(file.path(HERE,'Supplementary_Fig5_PanelB_Creep_Comparison.csv'))
q$Era<-factor(q$Era,levels=c('1970-1990','1991-2005','2006-2024'))
nom<-filter(q,Basis=='Nominal');adj<-filter(q,Basis=='Technology-adjusted')
ar<-inner_join(nom,adj,by=c('Gear','Era'),suffix=c('_nom','_adj'))
p_b<-ggplot(q,aes(Effort_trend,GHG_effort_trend,colour=Era,shape=Basis))+
 geom_hline(yintercept=0,colour='grey75',linewidth=.25)+geom_vline(xintercept=0,colour='grey75',linewidth=.25)+
 geom_segment(data=ar,aes(x=Effort_trend_nom,y=GHG_effort_trend_nom,xend=Effort_trend_adj,yend=GHG_effort_trend_adj,colour=Era),inherit.aes=FALSE,
  arrow=arrow(length=unit(1.4,'mm')),linewidth=.4)+
 geom_point(size=2,stroke=.6)+facet_wrap(~Gear)+
 scale_colour_manual(values=c('#56B4E9','#009E73','#D55E00'))+scale_shape_manual(values=c('Nominal'=1,'Technology-adjusted'=16))+
 labs(tag='(b)',x='Effort / catch log trend (% yr-1)',y='GHG / effort log trend (% yr-1)')+theme_pub
write.csv(q,file.path(HERE,'Supplementary_Fig5_PanelB_Creep_Render_Data.csv'),row.names=FALSE)
fig<-p_a+p_b+plot_layout(widths=c(1,1.6),guides='collect') & theme(legend.position='bottom')

for(ext in c('pdf','png','tiff')) {
 options<-list(filename=file.path(HERE,paste0('Supplementary_Fig5_Factor_Identity.',ext)),plot=fig,width=183,height=110,units='mm',bg='white')
 if(ext=='pdf') options$device<-cairo_pdf
 if(ext=='png') options$dpi<-300
 if(ext=='tiff') {options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
