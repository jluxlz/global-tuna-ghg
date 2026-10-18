library(ggplot2);library(dplyr);library(tidyr);library(patchwork)
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
a<-read.csv(file.path(HERE,'Supplementary_Fig4_PanelA_Catch_Coverage.csv'))
b<-read.csv(file.path(HERE,'Supplementary_Fig4_PanelB_GHG_Coverage.csv'))
c<-read.csv(file.path(HERE,'Supplementary_Fig4_PanelC_Ghost_Capacity.csv'))
t<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),
 axis.text=element_text(size=6,colour='black'),plot.tag=element_text(size=8,face='bold'),
 legend.position='bottom',legend.text=element_text(size=6),legend.title=element_blank(),
 axis.line=element_line(linewidth=.18),axis.ticks=element_line(linewidth=.18),plot.margin=margin(4,5,4,4,'pt'))
p_a<-ggplot(a,aes(Year,Catch_Mt,fill=Coverage))+geom_area()+
 scale_fill_manual(values=c('Allocated GHG'='#1A7A8A','No allocated GHG'='#D55E00'))+
 labs(tag='(a)',x=NULL,y='Recorded catch (Mt yr-1)')+t
# 2025 has no spatial observations; absence is not a zero allocation rate.
b$Allocated_pct[b$Year>2024]<-NA_real_
write.csv(b,file.path(HERE,'Supplementary_Fig4_PanelB_Render_Data.csv'),row.names=FALSE)
p_b<-ggplot(b,aes(Year,Allocated_pct))+geom_line(colour='#0072B2',linewidth=.5)+
 scale_y_continuous(limits=c(0,100),breaks=c(0,25,50,75,100))+
 labs(tag='(b)',x=NULL,y='Fleet GHG assigned to grids (%)')+t
cl<-c%>%select(Year,Gap_kW,Ghost_kW)%>%pivot_longer(-Year,names_to='Series',values_to='Capacity')
p_c<-ggplot(cl,aes(Year,Capacity/1e6,colour=Series,linetype=Series))+geom_line(linewidth=.55)+
 scale_colour_manual(values=c(Gap_kW='grey35',Ghost_kW='#009E73'),labels=c('Required gap','Reconstructed capacity'))+
 scale_linetype_manual(values=c(Gap_kW='solid',Ghost_kW='dashed'),labels=c('Required gap','Reconstructed capacity'))+
 labs(tag='(c)',x='Year',y='Ghost capacity (million kW)')+t
fig<-(p_a|p_b)/p_c+plot_layout(heights=c(1,1))
ggsave(file.path(HERE,'Supplementary_Fig4_Historical_Coverage.pdf'),fig,width=183,height=145,units='mm',device=cairo_pdf,bg='white')
ggsave(file.path(HERE,'Supplementary_Fig4_Historical_Coverage.png'),fig,width=183,height=145,units='mm',dpi=300,bg='white')
ggsave(file.path(HERE,'Supplementary_Fig4_Historical_Coverage.tiff'),fig,width=183,height=145,units='mm',dpi=900,compression='lzw',bg='white')
