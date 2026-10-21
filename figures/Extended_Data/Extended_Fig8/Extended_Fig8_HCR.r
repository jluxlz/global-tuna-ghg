suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_blank(),plot.margin=margin(5,5,5,5),panel.spacing=unit(3,'mm'))
d<-read.csv(file.path(HERE,'Extended_Fig8_HCR_Shapley.csv'))
d$Measure<-factor(d$Measure,levels=c('Fuel transition','Refrigeration transition','Fleet consolidation'),labels=c('Fuel','Refrigeration','Consolidation'))
cc<-c(Fuel='#D55E00',Refrigeration='#56B4E9',Consolidation='#9B6BA8')
draw<-function(z,value,tag,title){
 write.csv(z,file.path(HERE,paste0('Extended_Fig8_HCR_Panel',tag,'_Render_Data.csv')),row.names=FALSE,na='')
 ggplot(z,aes(Measure,.data[[value]],fill=Measure))+
 geom_hline(yintercept=0,colour='grey65',linewidth=.2)+geom_boxplot(width=.55,outlier.size=.35,linewidth=.25,na.rm=TRUE)+
 facet_wrap(~Rule,nrow=1)+scale_fill_manual(values=cc,guide='none')+
 labs(tag=paste0('(',tolower(tag),')'),x=NULL,y=title)+th
}
pa<-draw(d[d$Metric=='GHG_2050_Mt',],'Contribution_Mt','A','2050 Shapley contribution (Mt CO2e)')
pb<-draw(d[d$Metric=='GHG_Mt',],'Contribution_Mt','B','Cumulative contribution (Mt CO2e)')
pc<-draw(d[d$Metric=='GHG_Mt',],'Share_pct','C','Share of cumulative technical abatement (%)')
fig<-pa/pb/pc
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Extended_Fig8_Shapley_Abatement_Decomposition.',ext)),plot=fig,width=183,height=205,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
