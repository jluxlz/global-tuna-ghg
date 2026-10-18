# Organisation summaries plus old Fig.5d fleet-object heterogeneity.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
theme_pub<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),axis.line=element_line(linewidth=.18),axis.ticks=element_line(linewidth=.18),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_text(size=7),legend.key.size=unit(3,'mm'),panel.spacing=unit(3,'mm'),plot.margin=margin(4,5,4,4,'pt'))
read_panel<-function(label){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig16_',label,'.csv')));write.csv(d,file.path(HERE,paste0('Supplementary_Fig16_',label,'_Render_Data.csv')),row.names=FALSE);d}
a<-read_panel('PanelA_Organizations')%>%pivot_longer(-Organization,names_to='Measure',values_to='Reduction');a$Measure<-gsub('_pct','',a$Measure);a$Organization<-factor(a$Organization,levels=rev(c('WCPFC','IATTC','ICCAT','IOTC','CCSBT')))
measure_cols<-c(Consolidation='#E69F00',Fuel='#009E73',Fuel.Refrigerant='#56B4E9',Fuel.Refrigerant.Consolidation='#D55E00',Refrigerant='#0072B2')
pa<-ggplot(a,aes(Reduction,Organization,colour=Measure))+geom_vline(xintercept=0,colour='grey60',linewidth=.2)+geom_point(size=1.8,position=position_dodge(width=.55))+scale_colour_manual(values=measure_cols,labels=function(v)gsub('\\.',' + ',v))+labs(tag='(a)',x='Median cumulative object-level GHG reduction (%)',y=NULL)+theme_pub+guides(colour=guide_legend(nrow=2))
b<-read_panel('PanelB_Object_Effects');b$obj<-factor(b$obj,levels=rev(unique(b$obj)));b$Mitigation_Pathway<-factor(b$Mitigation_Pathway,levels=c('Consolidation','Fuel','Refrigerant'))
# One signed value scale: increases are red, zero is neutral, reductions blue.
# Symmetric limits give equal colour strength to equal absolute changes.
lim<-ceiling(max(abs(b$red))/10)*10
pal<-scales::div_gradient_pal(low='#B45C58',mid='#F7F7F5',high='#24658B',space='Lab')
rgb<-grDevices::col2rgb(pal((b$red+lim)/(2*lim)))/255
linear<-ifelse(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)^2.4)
lum<-as.numeric(c(.2126,.7152,.0722)%*%linear)
b$label_colour<-ifelse((lum+.05)/.05>=1.05/(lum+.05),'black','white')
pb<-ggplot(b,aes(Mitigation_Pathway,obj,fill=red))+geom_tile(colour='white',linewidth=.25)+geom_text(aes(label=sprintf('%.1f',red),colour=label_colour),size=2.2,show.legend=FALSE)+scale_colour_identity()+scale_fill_gradient2(low='#B45C58',mid='#F7F7F5',high='#24658B',midpoint=0,limits=c(-lim,lim),breaks=c(-lim,0,lim),labels=c(paste0('-',lim,'\nIncrease'),'0\nNo change',paste0('+',lim,'\nReduction')),name='Cumulative GHG reduction (%)',guide=guide_colourbar(title.position='top',barwidth=unit(55,'mm'),barheight=unit(2.5,'mm')))+labs(tag='(b)',x=NULL,y=NULL)+theme_pub+theme(legend.key.width=unit(12,'mm'))
fig<-pa/pb+plot_layout(heights=c(1,1.65))
for(ext in c('pdf','png','tiff')){
 options<-list(filename=file.path(HERE,paste0('Supplementary_Fig16_Organization_Mitigation.',ext)),plot=fig,width=183,height=185,units='mm',bg='white')
 if(ext=='pdf')options$device<-cairo_pdf
 if(ext=='png')options$dpi<-300
 if(ext=='tiff'){options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
