suppressPackageStartupMessages({library(ggplot2);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
d<-read.csv(file.path(HERE,'Supplementary_Fig15_Current_Price_Sensitivity.csv'))
d$WEO<-factor(d$WEO,levels=c('STEPS','APS','NZE'))
cc<-c(MGO='#444444',HFO='#B8860B',FAME='#66A61E',HVO='#1B9E77',LNG_Fossil='#377EB8',H2_Fossil='#984EA3',NH3_Green='#00A0A8',H2_Green='#80CDC1')
labs<-c(MGO='MGO',HFO='HFO',FAME='FAME',HVO='HVO',LNG_Fossil='Fossil LNG',H2_Fossil='Fossil H2',NH3_Green='Green NH3',H2_Green='Green H2')
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_blank(),plot.margin=margin(5,5,5,5),panel.spacing=unit(3,'mm'))
draw<-function(value,tag,label){write.csv(d,file.path(HERE,paste0('Supplementary_Fig15_Panel',toupper(tag),'_Render_Data.csv')),row.names=FALSE);ggplot(d,aes(Elasticity,.data[[value]],colour=Fuel,linetype=Fuel))+geom_vline(xintercept=-.3,linetype='dotted',colour='grey65',linewidth=.25)+geom_line(linewidth=.5)+facet_wrap(~WEO,nrow=1)+scale_colour_manual(values=cc,labels=labs)+scale_linetype_manual(values=c(MGO='solid',HFO='solid',FAME='dashed',HVO='dashed',LNG_Fossil='solid',H2_Fossil='longdash',NH3_Green='dotted',H2_Green='dotted'),labels=labs)+labs(tag=paste0('(',tag,')'),x='Prescribed cost elasticity',y=label)+th+guides(colour=guide_legend(nrow=2),linetype=guide_legend(nrow=2))}
a<-draw('Raw_Response','a','Raw cost response (same-year MGO = 1)')
b<-draw('Adjusted_Intensity','b','Adjusted GHG intensity (g CO2e/engine-kWh)')
fig<-a/b+plot_layout(guides='collect')&theme(legend.position='bottom')
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Supplementary_Fig15_Economic_Elasticity_Sensitivity.',ext)),plot=fig,width=183,height=155,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
