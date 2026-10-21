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
stopifnot(all(abs(a$Efficiency-(1-.243*a$Schedule))<1e-10),length(unique(b$Installed_kW))==1)
theme_pub<-theme_pub+theme(plot.title=element_text(size=8.5,face='bold'),
 plot.subtitle=element_text(size=7,colour='#52616A'),plot.margin=margin(6,8,5,7,'pt'))
composition<-a%>%transmute(Year,Implemented=Schedule,Remaining=1-Schedule)%>%
 pivot_longer(-Year,names_to='Stage',values_to='Fraction')
composition$Stage<-factor(composition$Stage,levels=c('Implemented','Remaining'))
nodes<-a%>%filter(Year%in%c(2025,2030,2040,2050))
write.csv(composition,file.path(HERE,'Supplementary_Fig11_PanelA_Composition_Render_Data.csv'),row.names=FALSE)
write.csv(nodes,file.path(HERE,'Supplementary_Fig11_Milestones_Render_Data.csv'),row.names=FALSE)
p_a<-ggplot(composition,aes(Year,Fraction,fill=Stage))+
 geom_area(position=position_stack(reverse=TRUE),colour='white',linewidth=.25)+
 geom_line(data=a,aes(Year,Schedule),inherit.aes=FALSE,colour='#0072B2',linewidth=.6)+
 geom_point(data=nodes,aes(Year,Schedule),inherit.aes=FALSE,shape=21,fill='white',colour='#0072B2',size=1.8)+
 scale_fill_manual(values=c(Implemented='#6CA9C6',Remaining='#E9EEF1'))+
 scale_y_continuous(labels=label_percent(),breaks=c(0,.5,1),expand=c(0,0))+
 scale_x_continuous(breaks=c(2025,2030,2040,2050),expand=c(0,0))+
 labs(tag='(a)',title='Prescribed transition',subtitle='Linear implementation over 25 years',x='Year',y='Share of transition completed')+theme_pub+
 theme(legend.title=element_blank())
p_b<-ggplot(a,aes(Year,Efficiency))+
 geom_ribbon(aes(ymin=Efficiency,ymax=1),fill='#B9DCD1',alpha=.8)+
 geom_hline(yintercept=1,colour='#87939A',linetype='dashed',linewidth=.25)+
 geom_line(colour='#00856B',linewidth=.75)+geom_point(data=nodes,size=1.8,colour='#00856B')+
 annotate('text',x=2039,y=.945,label='Prescribed operating-time\nreduction',size=2.5,colour='#287760')+
 annotate('text',x=2049.5,y=.778,label='0.757',hjust=1,size=2.8,fontface='bold',colour='#00856B')+
 scale_y_continuous(limits=c(.73,1.02),breaks=c(.75,.875,1),labels=label_number(accuracy=.001))+
 scale_x_continuous(breaks=c(2025,2030,2040,2050),expand=c(0,0))+
 labs(tag='(b)',title='Operating-time assumption',subtitle='Factor = 1 - 0.243 \u00d7 implemented share',x='Year',y='Operating-time factor')+
 theme_pub+theme(legend.position='none')
# Equal-width bands encode equal installed power, not invented vessel counts.
flow<-data.frame(Stage=c('Retired smaller-vessel capacity','Larger-template replacement capacity'),
 xmin=c(0,6),xmax=c(4,10),ymin=1,ymax=2.05,Power_kW=b$Installed_kW[1])
write.csv(flow,file.path(HERE,'Supplementary_Fig11_PanelC_Power_Flow_Render_Data.csv'),row.names=FALSE)
p_c<-ggplot()+
 geom_rect(data=flow,aes(xmin=xmin,xmax=xmax,ymin=ymin,ymax=ymax),fill=c('#DDE3E8','#C3DFD6'),colour=NA)+
 annotate('segment',x=4.2,xend=5.8,y=1.53,yend=1.53,linewidth=.65,colour='#52616A',arrow=arrow(length=unit(2,'mm')))+
 geom_text(data=flow,aes(x=(xmin+xmax)/2,y=1.64,label=paste0(format(Power_kW,big.mark=','),' kW')),size=4,fontface='bold',colour='#263940')+
 annotate('text',x=c(2,8),y=1.23,label=c('Smaller-vessel capacity','Larger-template capacity'),size=2.8,colour='#334850')+
 annotate('text',x=5,y=2.45,label='Installed power is conserved',size=3,fontface='bold',colour='#334850')+
 annotate('text',x=5,y=.59,label='Replacement stays within the same organization and gear group',size=2.8,colour='#52616A')+
 annotate('text',x=5,y=.19,label='Illustrative accounting; no vessel counts or fleet-wide GHG savings are implied',size=2.5,colour='#52616A')+
 coord_cartesian(xlim=c(-.1,10.1),ylim=c(0,2.7),clip='off')+
 labs(tag='(c)',title='Equal-power replacement, separate from the operating-time factor')+
 theme_void(base_family='Arial')+theme(plot.title=element_text(size=9,face='bold'),plot.tag=element_text(size=10,face='bold'),plot.margin=margin(8,10,6,10,'pt'))
fig<-(p_a|p_b)/p_c+plot_layout(heights=c(1.25,1))

for(ext in c('pdf','png','tiff')) {
 options<-list(filename=file.path(HERE,paste0('Supplementary_Fig11_Consolidation_Protocol.',ext)),plot=fig,width=183,height=153,units='mm',bg='white')
 if(ext=='pdf') options$device<-cairo_pdf
 if(ext=='png') options$dpi<-300
 if(ext=='tiff') {options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
