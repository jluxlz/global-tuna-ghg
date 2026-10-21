# Fuel properties, screening and transition depth, relocated from old Fig.5a,c.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
theme_pub<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),axis.line=element_line(linewidth=.18),axis.ticks=element_line(linewidth=.18),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_text(size=7),legend.key.size=unit(3,'mm'),legend.box='vertical',panel.spacing=unit(3,'mm'),plot.margin=margin(4,5,4,4,'pt'))
weo_cols<-c(STEPS='#D55E00',APS='#0072B2',NZE='#009E73');lv_cols<-c(Low='#88CCEE',Medium='#DDCC77',High='#CC6677')
read_panel<-function(label){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig10_',label,'.csv')));write.csv(d,file.path(HERE,paste0('Supplementary_Fig10_',label,'_Render_Data.csv')),row.names=FALSE);d}
a<-read_panel('PanelA_Fuel_Intensity')%>%filter(Year==2050);a$WEO<-factor(a$WEO,levels=names(weo_cols))
a$Fuel<-recode(a$Fuel,H2_Fossil='Fossil H2',H2_Green='Green H2',NH3_Green='Green NH3',LNG_Fossil='LNG')
pa<-ggplot(a,aes(Intensity_gCO2e_kWh,reorder(Fuel,Intensity_gCO2e_kWh),colour=WEO))+geom_vline(xintercept=0,colour='grey60',linewidth=.18)+geom_point(size=1.2,position=position_dodge(width=.55))+scale_colour_manual(values=weo_cols,name=NULL)+labs(tag='(a)',x=expression(Adjusted~intensity~(g~CO[2]*e~kWh^{-1})),y=NULL)+theme_pub
b<-read_panel('PanelB_Adoption');b$WEO<-factor(b$WEO,levels=names(weo_cols))
pb<-ggplot(b,aes(Year,100*Share,colour=WEO,linetype=Path))+geom_line(linewidth=.5)+geom_point(size=1.1)+scale_colour_manual(values=weo_cols,name=NULL)+labs(tag='(b)',x='Year',y='Prescribed adoption or blend (%)')+theme_pub
c<-read_panel('PanelC_Fuel_Screen');c$WEO<-factor(c$WEO,levels=names(weo_cols));c$Intensity<-factor(c$Intensity,levels=names(lv_cols))
fuel_order<-c('FAME','HVO','LNG','NH3','H2','H2G','FAME+LNG','FAME+NH3','FAME+H2','FAME+H2G','HVO+LNG','HVO+NH3','HVO+H2','HVO+H2G');c$FuelOption<-factor(c$FuelOption,levels=fuel_order)
pc1<-ggplot(c,aes(FuelOption,Reduction_2050,colour=Intensity))+geom_hline(yintercept=0,colour='grey60',linetype='dashed',linewidth=.2)+geom_point(size=1,position=position_dodge(width=.6))+facet_wrap(~WEO,nrow=1)+scale_colour_manual(values=lv_cols,name='Screening intensity')+labs(tag='(c)',x=NULL,y='2050 proxy reduction (%)')+theme_pub+theme(axis.text.x=element_blank(),axis.ticks.x=element_blank(),legend.position='none')
pc2<-ggplot(c,aes(FuelOption,M_econ_2050,colour=Intensity))+geom_hline(yintercept=1,colour='grey60',linetype='dashed',linewidth=.2)+geom_point(size=1,position=position_dodge(width=.6))+facet_wrap(~WEO,nrow=1)+scale_colour_manual(values=lv_cols,name='Screening intensity')+labs(x=NULL,y=expression(M[econ]~'(2050)'))+theme_pub+theme(axis.text.x=element_text(angle=60,hjust=1,size=5.5))
pc<-pc1/pc2+plot_layout(heights=c(1,1.2))
d<-read_panel('PanelD_Transition_Curves');d$WEO<-factor(d$WEO,levels=names(weo_cols));d$Family<-factor(d$Family,levels=c('FAME','HVO','LNG_Fossil','NH3_Green','H2_Fossil','H2_Green'))
d$Path<-ifelse(d$Type=='Dual','HVO + device','Single fuel')
pd<-ggplot(d,aes(Year,Relative_Intensity_pct,colour=WEO,linetype=Path,group=interaction(WEO,Path,Family)))+geom_hline(yintercept=100,linetype='dotted',colour='grey65',linewidth=.2)+geom_line(linewidth=.5)+facet_wrap(~Family,ncol=3,labeller=as_labeller(c(FAME='FAME',HVO='HVO',LNG_Fossil='LNG',NH3_Green='Green NH3',H2_Fossil='Fossil H2',H2_Green='Green H2')))+scale_colour_manual(values=weo_cols,name='WEO')+scale_linetype_manual(values=c('Single fuel'='solid','HVO + device'='dashed'),name='Fuel path')+scale_x_continuous(breaks=c(2025,2035,2050))+labs(tag='(d)',x='Year',y='Adjusted intensity (same-year MGO = 100)')+theme_pub
fig<-(pa|pb)/pc/pd+plot_layout(heights=c(.8,1.25,1))
for(ext in c('pdf','png','tiff')){
 options<-list(filename=file.path(HERE,paste0('Supplementary_Fig10_Fuel_Properties_and_Adoption.',ext)),plot=fig,width=183,height=240,units='mm',bg='white')
 if(ext=='pdf')options$device<-cairo_pdf
 if(ext=='png')options$dpi<-300
 if(ext=='tiff'){options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
