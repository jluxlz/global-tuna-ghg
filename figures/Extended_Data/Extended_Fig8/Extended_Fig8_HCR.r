suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
d<-read.csv(file.path(HERE,'Extended_Fig8_Current_Cost_Buffer.csv'))
s<-d%>%group_by(WEO,Year,Assumption)%>%summarise(Raw_Response=mean(Raw_Response),Response_Change_pct=mean(Response_Change_pct),.groups='drop')
s$WEO<-factor(s$WEO,levels=c('STEPS','APS','NZE'))
cc<-c(Unbuffered='#666F77','Half carbon cost'='#0072B2','2023 cost insulation'='#009E73')
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_blank(),plot.margin=margin(5,5,5,5),panel.spacing=unit(3,'mm'))
draw<-function(value,tag,label){write.csv(d,file.path(HERE,paste0('Extended_Fig8_Panel',toupper(tag),'_Render_Data.csv')),row.names=FALSE);ggplot(s,aes(Year,.data[[value]],colour=Assumption))+geom_line(linewidth=.5)+facet_wrap(~WEO,nrow=1)+scale_colour_manual(values=cc)+scale_x_continuous(breaks=c(2023,2030,2040,2050))+labs(tag=paste0('(',tag,')'),x='Year',y=label)+th}
fig<-draw('Raw_Response','a','Mean regional raw response (2023 = 1)')/draw('Response_Change_pct','b','Response change from unbuffered (%)')+plot_layout(guides='collect')&theme(legend.position='bottom')
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Extended_Fig8_Subsidy_Buffer.',ext)),plot=fig,width=183,height=150,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
