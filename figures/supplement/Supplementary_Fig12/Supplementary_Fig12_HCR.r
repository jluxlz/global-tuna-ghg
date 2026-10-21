suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
rd<-function(s){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig12_',s,'.csv')));write.csv(d,file.path(HERE,paste0('Supplementary_Fig12_',s,'_Render_Data.csv')),row.names=FALSE);d}
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_text(size=6),plot.margin=margin(5,5,5,5))
cc<-c(C='#666F77',F='#0072B2',T='#009E73')
a<-rd('PanelA_HCR_Shapes')
pa<-ggplot(a,aes(B_Bmsy,Target_MSY,colour=Rule))+geom_line(linewidth=.6)+
 geom_vline(xintercept=c(.2,.8),linetype='dotted',colour='grey55',linewidth=.25)+
 scale_colour_manual(values=cc,name='HCR')+labs(tag='(a)',x=expression(B[t]/B[MSY]),y=expression(Target~catch/MSY))+th
b<-rd('PanelB_Activation')%>%pivot_longer(c(HCR_Triggered,HCR_Closed),names_to='State',values_to='Fraction')
b$Stock<-factor(b$Stock,levels=rev(c('SKJ','YFT','BET','ALB','SBT')))
b$State<-factor(b$State,levels=c('HCR_Triggered','HCR_Closed'),labels=c('Below trigger','At closure'))
pb<-ggplot(b,aes(Year,Stock,fill=Fraction))+geom_tile()+facet_wrap(~State,ncol=1)+
 scale_fill_gradient(low='#F3F5F5',high='#00796B',limits=c(0,1),name='Fraction of futures')+
 scale_x_continuous(breaks=c(2025,2030,2040,2050),expand=c(0,0))+
 labs(tag='(b)',x='Year',y=NULL)+th
c<-rd('PanelC_Stock_Endpoints');c$Rule<-factor(c$Rule,levels=names(cc));c$Stock<-factor(c$Stock,levels=c('SKJ','YFT','BET','ALB','SBT'))
pc<-ggplot(c,aes(Rule,B_Bmsy_Start,fill=Rule))+
 geom_hline(yintercept=1,linetype='dashed',colour='grey60',linewidth=.25)+
 geom_boxplot(width=.5,outlier.size=.3,linewidth=.25)+facet_wrap(~Stock,nrow=1)+
 scale_fill_manual(values=cc,guide='none')+labs(tag='(c)',x=NULL,y=expression(B[2050]/B[MSY]))+th
fig<-(pa|pb)/pc+plot_layout(heights=c(1.4,1))
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Supplementary_Fig12_Quota_Protocol.',ext)),plot=fig,width=183,height=170,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
