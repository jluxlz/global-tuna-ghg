# One figure per script; CSV inputs and rendered panel data stay in this folder.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork);library(scales)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
theme_pub<-theme_classic(base_size=7,base_family='Arial')+theme(
 axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),
 axis.line=element_line(linewidth=.2),axis.ticks=element_line(linewidth=.2),
 strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),
 plot.tag=element_text(size=8,face='bold'),legend.position='bottom',
 legend.text=element_text(size=6),legend.title=element_text(size=7,face='bold'),
 legend.key.size=unit(3,'mm'),panel.spacing=unit(3,'mm'),plot.margin=margin(4,5,4,4,'pt'))
cols<-c(LL='#B81D0A',PS='#1A7A8A',TP='#7570B3',SA='#E6AB02')
weo_cols<-c(STEPS='#D55E00',APS='#0072B2',NZE='#009E73')
read_panel<-function(n,label){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig',n,'_',label,'.csv')));write.csv(d,file.path(HERE,paste0('Supplementary_Fig',n,'_',label,'_Render_Data.csv')),row.names=FALSE);d}

a<-read_panel(10,'PanelA_Schedule');b<-read_panel(10,'PanelB_Illustration')
p_a<-ggplot(a,aes(Year,Schedule))+geom_line(colour='#0072B2',linewidth=.55)+labs(tag='(a)',x='Year',y='Prescribed transition fraction')+theme_pub
p_b<-ggplot(a,aes(Year,Efficiency))+geom_line(colour='#009E73',linewidth=.55)+labs(tag='(b)',x='Year',y='Operating-time factor')+theme_pub
p_c<-ggplot(b,aes(State,Installed_kW))+geom_col(fill='#7570B3',width=.5)+geom_text(aes(label=paste0(Installed_kW,' kW')),vjust=-.4,size=2.4)+
 labs(tag='(c)',x=NULL,y='Illustrative installed power',title='Equal-power replacement example')+theme_pub+theme(axis.text.x=element_text(size=6))
fig<-(p_a|p_b)/p_c

for(ext in c('pdf','png','tiff')) {
 options<-list(filename=file.path(HERE,paste0('Supplementary_Fig10_Consolidation_Protocol.',ext)),plot=fig,width=183,height=135,units='mm',bg='white')
 if(ext=='pdf') options$device<-cairo_pdf
 if(ext=='png') options$dpi<-300
 if(ext=='tiff') {options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
