# Quota assignment and the full species/technology screen from old Fig.5b.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
theme_pub<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),axis.line=element_line(linewidth=.18),axis.ticks=element_line(linewidth=.18),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_text(size=7),legend.key.size=unit(3,'mm'),panel.spacing=unit(4,'mm'),plot.margin=margin(4,5,4,4,'pt'))
read_panel<-function(label){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig11_',label,'.csv')));write.csv(d,file.path(HERE,paste0('Supplementary_Fig11_',label,'_Render_Data.csv')),row.names=FALSE);d}
a<-read_panel('PanelA_Choices');a$Species<-factor(a$Species,levels=c('SKJ','YFT','BET','ALB','SBT'))
pa<-ggplot(a,aes(Species,Fraction_FMSY))+geom_col(fill='#0072B2',width=.55)+labs(tag='(a)',x=NULL,y=expression(Assigned~fraction~of~F[MSY]))+theme_pub
pb<-ggplot(a,aes(Species,Biomass_K_2050))+geom_hline(yintercept=.25,linetype='dashed',colour='grey50',linewidth=.2)+geom_col(fill='#009E73',width=.55)+labs(tag='(b)',x=NULL,y='Projected 2050 B / K')+theme_pub
c<-read_panel('PanelC_Quota_Screen');c$Species<-factor(c$Species,levels=levels(a$Species));c$TechCreep<-factor(c$TechCreep,levels=c('Slow: 1.9%/yr','Steady: 2.4%/yr','Rapid: 4.3%/yr'));c$QuotaType<-factor(c$QuotaType,levels=c('C','F'))
pc<-ggplot(c,aes(Species,Meco,fill=QuotaType))+geom_col(position=position_dodge(width=.7),width=.6,alpha=.85)+
 geom_point(data=c%>%filter(Collapse),aes(group=QuotaType),position=position_dodge(width=.7),shape=21,size=2,fill='white',colour='black')+
 facet_wrap(~TechCreep,ncol=3)+scale_fill_manual(values=c(C='#4477AA',F='#EE7733'),name='Quota rule',labels=c(C='C: 100% MSY',F='F: selected species fractions'))+
 labs(tag='(c)',x=NULL,y=expression(Ecological~effort~multiplier~M[eco]))+theme_pub
# Guard-marker positions must retain both groups during dodging. Draw explicit
# numeric x positions, avoiding the missing-group shift in a filtered layer.
pc<-ggplot(c,aes(as.numeric(Species),Meco,fill=QuotaType))+geom_col(aes(group=QuotaType),position=position_dodge(width=.7),width=.6,alpha=.85)+
 geom_point(data=c%>%filter(Collapse),inherit.aes=FALSE,mapping=aes(x=as.numeric(Species)+ifelse(QuotaType=='C',-.175,.175),y=Meco),shape=21,size=2,fill='white',colour='black')+
 facet_wrap(~TechCreep,ncol=3)+scale_fill_manual(values=c(C='#4477AA',F='#EE7733'),name='Quota rule',labels=c(C='C: 100% MSY',F='F: selected species fractions'))+scale_x_continuous(breaks=seq_along(levels(c$Species)),labels=levels(c$Species))+
 labs(tag='(c)',x=NULL,y=expression(Ecological~effort~multiplier~M[eco]))+theme_pub
fig<-(pa|pb)/pc+plot_layout(heights=c(1,1.2))
for(ext in c('pdf','png','tiff')){
 options<-list(filename=file.path(HERE,paste0('Supplementary_Fig11_Quota_Protocol.',ext)),plot=fig,width=183,height=155,units='mm',bg='white')
 if(ext=='pdf')options$device<-cairo_pdf
 if(ext=='png')options$dpi<-300
 if(ext=='tiff'){options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
