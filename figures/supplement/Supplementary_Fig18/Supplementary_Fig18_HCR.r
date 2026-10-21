suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
rd<-function(s){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig18_HCR_Panel',s,'.csv')));write.csv(d,file.path(HERE,paste0('Supplementary_Fig18_HCR_Panel',s,'_Render_Data.csv')),row.names=FALSE);d}
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=6.5,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_blank(),legend.key.size=unit(2.5,'mm'),plot.margin=margin(5,5,5,5),panel.spacing=unit(3,'mm'))
cc<-c(C='#666F77',F='#0072B2',T='#009E73')
a<-rd('A_Catch_GHG')
pa<-ggplot(a,aes(Catch_Mt,GHG_Mt,colour=Rule,shape=factor(Max_Days)))+geom_point(size=.9,alpha=.55)+
 scale_colour_manual(values=cc)+scale_shape_manual(values=c('280'=1,'365'=16),labels=c('280-day bound','365-day bound'))+
 labs(tag='(a)',x='Cumulative catch (Mt)',y='Cumulative GHG (Mt CO2e)')+th
b<-rd('B_Day_Effects');b$Measure<-factor(sprintf('%03d',b$Technical),levels=c('100','111'),labels=c('Fuel','Combined technical'))
pb<-ggplot(b,aes(Condition,Reduction_pct,fill=Measure))+
 geom_hline(yintercept=0,colour='grey65',linewidth=.2)+
 geom_boxplot(position=position_dodge(.7),width=.65,outlier.size=.25,linewidth=.25)+facet_wrap(~Rule,nrow=1)+
 scale_fill_manual(values=c('Fuel'='#D55E00','Combined technical'='#555555'))+
 labs(tag='(b)',x=NULL,y='Cumulative GHG reduction (%)')+th+theme(axis.text.x=element_text(angle=45,hjust=1,size=5.5))
c<-rd('C_Fraction_Effects')%>%pivot_longer(c(Catch_Mt_Change_pct,GHG_Mt_Change_pct,Period_CEI_Change_pct),names_to='Metric',values_to='Change')
c$Metric<-factor(c$Metric,levels=c('Catch_Mt_Change_pct','GHG_Mt_Change_pct','Period_CEI_Change_pct'),labels=c('Cumulative catch','Cumulative GHG','Period CEI'))
pc<-ggplot(c,aes(Rule,Change,fill=Rule))+geom_hline(yintercept=0,colour='grey65',linewidth=.2)+
 geom_boxplot(width=.5,outlier.size=.25,linewidth=.25)+facet_wrap(~Metric,nrow=1,scales='free_y')+
 scale_fill_manual(values=cc,guide='none')+labs(tag='(c)',x=NULL,y='80% vs 100% fraction change (%)')+th
d<-rd('D_Thresholds')%>%pivot_longer(c(Catch_Mt,GHG_Mt,Period_CEI,Minimum_Stock_Bmsy2050),names_to='Metric',values_to='Value')
d$Metric<-factor(d$Metric,levels=c('Catch_Mt','GHG_Mt','Period_CEI','Minimum_Stock_Bmsy2050'),labels=c('Catch (Mt)','GHG (Mt CO2e)','Period CEI','Lowest B2050/BMSY'))
# Main period calls this stock endpoint Min_Stock_Bmsy_2050; use the explicit
# common name written by the preparation step.
pd<-ggplot(d,aes(Threshold,Value))+geom_boxplot(width=.5,outlier.size=.25,fill='#B2D4C9',linewidth=.25)+
 facet_wrap(~Metric,nrow=1,scales='free_y')+
 labs(tag='(d)',x='T-type trigger / closure (fractions of K)',y=NULL)+th+theme(axis.text.x=element_text(angle=35,hjust=1))
fig<-(pa|pb)/pc/pd+plot_layout(heights=c(1.3,1,1))
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Supplementary_Fig18_Constrained_Baseline.',ext)),plot=fig,width=183,height=225,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
