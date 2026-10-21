suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
rd<-function(s){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig16_HCR_Panel',s,'.csv')),colClasses=c(Technical='character'));write.csv(d,file.path(HERE,paste0('Supplementary_Fig16_HCR_Panel',s,'_Render_Data.csv')),row.names=FALSE);d}
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_text(size=6),plot.margin=margin(5,5,5,5),panel.spacing=unit(3,'mm'))
labs_tech<-c('100'='Fuel','010'='Refrigeration','001'='Consolidation','111'='Combined technical')
cols<-c('100'='#D55E00','010'='#56B4E9','001'='#9B6BA8','111'='#333333')
a<-rd('A_Organizations')%>%group_by(Rule,Organization,Technical)%>%summarise(Reduction=median(Reduction_pct),.groups='drop')
a$Measure<-factor(a$Technical,levels=names(labs_tech),labels=labs_tech)
a$Organization<-factor(a$Organization,levels=c('WCPFC','IATTC','ICCAT','IOTC','CCSBT'))
lim<-max(10,ceiling(max(abs(a$Reduction))/10)*10)
pa<-ggplot(a,aes(Organization,Measure,fill=Reduction))+geom_tile(colour='white',linewidth=.25)+
 geom_text(aes(label=sprintf('%.1f',Reduction)),size=2.05)+facet_wrap(~Rule,nrow=1)+
 scale_fill_gradient2(low='#C47B70',mid='#FAFAF8',high='#729EB7',midpoint=0,limits=c(-lim,lim),name='Cumulative GHG reduction (%)',guide=guide_colourbar(title.position='top',barwidth=unit(65,'mm'),barheight=unit(2.5,'mm')))+
 labs(tag='(a)',x=NULL,y=NULL)+th+theme(axis.text.x=element_text(angle=45,hjust=1))
write.csv(a,file.path(HERE,'Supplementary_Fig16_HCR_PanelA_Summary.csv'),row.names=FALSE)
b<-rd('B_Gears');b$Gear<-factor(b$Gear,levels=c('LL','PS','TP','SA'))
b$Technical<-factor(b$Technical,levels=names(cols))
pb<-ggplot(b,aes(Gear,Reduction_pct,fill=Technical))+
 geom_hline(yintercept=0,colour='grey60',linewidth=.25)+
 geom_boxplot(position=position_dodge(.8),width=.65,outlier.size=.25,linewidth=.25)+facet_wrap(~Rule,nrow=1)+
 scale_fill_manual(values=cols,labels=labs_tech,name=NULL)+
 labs(tag='(b)',x='Attributed vessel group',y='Cumulative GHG reduction (%)')+th+
 guides(fill=guide_legend(nrow=1))
fig<-pa/pb+plot_layout(heights=c(1.1,1))
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Supplementary_Fig16_Organization_Mitigation.',ext)),plot=fig,width=183,height=180,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
