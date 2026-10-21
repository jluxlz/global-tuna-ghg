suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
rd<-function(s){d<-read.csv(file.path(HERE,paste0('Extended_Fig9_',s,'.csv')));write.csv(d,file.path(HERE,paste0('Extended_Fig9_',s,'_Render_Data.csv')),row.names=FALSE);d}
cc<-c(C='#666F77',F='#0072B2',T='#009E73');ll<-c(C='C: constant catch',F='F: harvest rate',T='T: biomass threshold')
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.title=element_blank(),legend.text=element_text(size=6),legend.key.size=unit(3,'mm'),panel.spacing=unit(3,'mm'),plot.margin=margin(5,5,5,5))
a<-rd('PanelA_Stocks')%>%group_by(Stock_Source,Rule,Year)%>%summarise(Median=median(B_Bmsy_Start),P5=quantile(B_Bmsy_Start,.05),P95=quantile(B_Bmsy_Start,.95),.groups='drop')
a$Rule<-factor(a$Rule,levels=names(cc));a$Stock_Source<-factor(a$Stock_Source,levels=c('Pooled global BET','Indian Ocean BET'))
pa<-ggplot(a,aes(Year,Median,colour=Rule,fill=Rule,linetype=Rule))+
 geom_hline(yintercept=c(.2,.8,1),linetype='dotted',colour='grey70',linewidth=.23)+
 geom_ribbon(aes(ymin=P5,ymax=P95),alpha=.12,colour=NA,linetype=0)+geom_line(linewidth=.55)+
 facet_wrap(~Stock_Source,nrow=1)+scale_colour_manual(values=cc,labels=ll)+scale_fill_manual(values=cc,labels=ll)+
 scale_linetype_manual(values=c(C='solid',F='solid',T='dashed'),labels=ll)+
 labs(tag='(a)',title='Regional stock conditions alter threshold relevance',x='Year',y=expression(B/B[MSY]))+th+
 guides(colour=guide_legend(nrow=1),fill='none',linetype='none')
b<-rd('PanelB_Quota')%>%filter(Comparison%in%c('CF','CT'))%>%pivot_longer(c(Catch_Mt_Change_pct,GHG_Mt_Change_pct,CEI_Change_pct),names_to='Metric',values_to='Change')
b$Rule<-ifelse(b$Comparison=='CF','F','T');b$Metric<-factor(b$Metric,levels=c('Catch_Mt_Change_pct','GHG_Mt_Change_pct','CEI_Change_pct'),labels=c('Cumulative catch','Cumulative GHG','Period CEI'))
pb<-ggplot(b,aes(Rule,Change,colour=Rule,fill=Rule))+
 geom_hline(yintercept=0,colour='grey65',linetype='dashed',linewidth=.25)+
 geom_boxplot(width=.48,outlier.shape=NA,alpha=.13,linewidth=.3)+geom_point(position=position_jitter(width=.12,seed=17),size=.5,alpha=.35)+
 facet_wrap(~Metric,nrow=1,scales='free_y')+scale_colour_manual(values=cc,guide='none')+scale_fill_manual(values=cc,guide='none')+
 labs(tag='(b)',title='Regional paired outcomes relative to C',x=NULL,y='Change relative to C (%)')+th
c<-rd('PanelC_Fuel');c$Rule<-factor(c$Rule,levels=names(cc))
pc<-ggplot(c,aes(Rule,Reduction_pct,colour=Rule,fill=Rule))+
 geom_hline(yintercept=0,colour='grey65',linewidth=.25)+geom_boxplot(width=.48,outlier.shape=NA,alpha=.13,linewidth=.3)+
 geom_point(position=position_jitter(width=.12,seed=17),size=.6,alpha=.4)+scale_colour_manual(values=cc,guide='none')+scale_fill_manual(values=cc,guide='none')+
 labs(tag='(c)',title='Fuel transition within each regional rule',x=NULL,y='Cumulative GHG reduction (%)')+th
fig<-pa/pb/pc+plot_layout(heights=c(1.1,.9,.8),guides='keep')
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Extended_Fig9_Regional_HCR.',ext)),plot=fig,width=183,height=211,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
