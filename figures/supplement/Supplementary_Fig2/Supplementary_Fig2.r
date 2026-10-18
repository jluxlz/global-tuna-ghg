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

a<-read_panel(2,'PanelA_Distributions'); b<-read_panel(2,'PanelB_Missingness')
p_a<-ggplot(a,aes(Value,colour=Series,linetype=Series=='Observed'))+stat_ecdf(geom='step',linewidth=.4)+
 facet_wrap(~Parameter,scales='free_x')+scale_x_log10()+scale_linetype_manual(values=c('TRUE'='solid','FALSE'='dashed'),guide='none')+
 scale_colour_manual(values=c(Observed='black','Donor 1'='#0072B2','Donor 2'='#D55E00','Donor 3'='#009E73','Donor 4'='#CC79A7','Donor 5'='#E69F00'))+
 labs(tag='(a)',x='Positive observed or donor value (GT; kW)',y='Cumulative fraction')+theme_pub
p_b<-ggplot(b,aes(Parameter,100*Imputed/Total))+geom_col(fill='#0072B2',width=.55)+
 geom_text(aes(label=paste0(Imputed,' / ',Total)),vjust=-.5,size=2.3)+scale_y_continuous(limits=c(0,65))+
 labs(tag='(b)',x=NULL,y='PMM-imputed records (%)')+theme_pub
fig<-p_a/p_b+plot_layout(heights=c(1.6,1))

for(ext in c('pdf','png','tiff')) {
 options<-list(filename=file.path(HERE,paste0('Supplementary_Fig2_Imputation_Diagnostics.',ext)),plot=fig,width=183,height=145,units='mm',bg='white')
 if(ext=='pdf') options$device<-cairo_pdf
 if(ext=='png') options$dpi<-300
 if(ext=='tiff') {options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
