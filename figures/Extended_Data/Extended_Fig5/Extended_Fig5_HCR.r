suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
rd<-function(s){d<-read.csv(file.path(HERE,paste0('Extended_Fig5_HCR_Panel',s,'.csv')));write.csv(d,file.path(HERE,paste0('Extended_Fig5_HCR_Panel',s,'_Render_Data.csv')),row.names=FALSE,na='');d}
cc<-c(C='#666F77',F='#0072B2',T='#009E73')
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=6.5,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_blank(),plot.margin=margin(5,5,5,5),panel.spacing=unit(3,'mm'))
sumrange<-function(d,groups,value){d%>%group_by(across(all_of(groups)))%>%summarise(Median=median(.data[[value]],na.rm=TRUE),P5=quantile(.data[[value]],.05,na.rm=TRUE),P95=quantile(.data[[value]],.95,na.rm=TRUE),.groups='drop')}
a<-rd('A_Effort')%>%pivot_longer(c(Demand_Fulfilled,Capacity_Used),names_to='Metric',values_to='Value')
a$Metric<-factor(a$Metric,levels=c('Demand_Fulfilled','Capacity_Used'),labels=c('Requested effort fulfilled','Capacity used'))
as<-sumrange(a,c('Rule','Year','Gear','Metric'),'Value')
pa<-ggplot(as,aes(Year,Median,colour=Rule,fill=Rule))+geom_ribbon(aes(ymin=P5,ymax=P95),alpha=.1,colour=NA)+geom_line(linewidth=.5)+facet_wrap(vars(Metric,Gear),ncol=2)+scale_colour_manual(values=cc)+scale_fill_manual(values=cc)+scale_y_continuous(limits=c(0,1.01))+scale_x_continuous(breaks=c(2025,2035,2050))+labs(tag='(a)',x='Year',y='Fraction')+th
b<-rd('B_Catches');b$Stock<-factor(b$Stock,levels=c('SKJ','YFT','BET','ALB','SBT'))
bs<-sumrange(b,c('Rule','Year','Stock'),'Target_Fulfilled')
pb<-ggplot(bs,aes(Year,Median,colour=Rule,fill=Rule))+geom_ribbon(aes(ymin=P5,ymax=P95),alpha=.1,colour=NA)+geom_line(linewidth=.5)+facet_wrap(~Stock,nrow=1)+scale_colour_manual(values=cc)+scale_fill_manual(values=cc)+scale_y_continuous(limits=c(0,1.01))+scale_x_continuous(breaks=c(2025,2050))+labs(tag='(b)',x='Year',y='Target catch fulfilled')+th
write.csv(as,file.path(HERE,'Extended_Fig5_HCR_PanelA_Summary.csv'),row.names=FALSE,na='');write.csv(bs,file.path(HERE,'Extended_Fig5_HCR_PanelB_Summary.csv'),row.names=FALSE,na='')
fig<-pa/pb+plot_layout(heights=c(1.6,1),guides='collect')&theme(legend.position='bottom')
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Extended_Fig5_Capacity_and_Catch.',ext)),plot=fig,width=183,height=180,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
