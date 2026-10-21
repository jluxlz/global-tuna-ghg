library(ggplot2);library(dplyr);library(tidyr);library(patchwork)
args<-commandArgs(FALSE);self<-sub('--file=','',args[grepl('^--file=',args)])[1];setwd(dirname(normalizePath(self)))
read_panel<-function(letter,name)read.csv(paste0('Supplementary_Fig19_Panel',letter,'_',name,'.csv'))
th<-theme_classic(base_size=7,base_family='sans')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.text=element_text(size=7,face='bold'),legend.position='bottom',legend.title=element_blank(),legend.text=element_text(size=6),plot.title=element_text(size=8,face='bold'),plot.tag=element_text(size=8,face='bold'),plot.margin=margin(5,6,5,5))
a<-read_panel('A','Global_Clocks')%>%mutate(Scenario=factor(Scenario,levels=rev(Scenario)))
pa<-ggplot(a,aes(Cumulative_Median_Mt,Scenario))+geom_errorbar(aes(xmin=Cumulative_P5_Mt,xmax=Cumulative_P95_Mt),orientation='y',width=.12,colour='#367D99')+geom_point(size=1.8,colour='#367D99')+geom_text(aes(label=round(Cumulative_Median_Mt,1)),nudge_y=.18,size=2.2)+labs(x=expression('1950-2025 GHG (Mt CO'[2]*'e)'),y='Industrial / coastal clock',title='Historical clock sensitivity')+th
b<-read_panel('B','Fuel_Phases')%>%mutate(Phase=factor(Phase,levels=rev(Phase)))
pb<-ggplot(b,aes(Median,Phase))+geom_col(width=.55,fill='#81AFBC')+geom_errorbar(aes(xmin=P5,xmax=P95),orientation='y',width=.13)+geom_text(aes(label=sprintf('%.1f%%',Median)),hjust=-.25,size=2.2)+scale_x_continuous(limits=c(0,82))+labs(x='Share of modelled LL fuel (%)',y=NULL,title='Fuel by operating phase')+th
c<-read_panel('C','FI_Diagnostics')%>%mutate(Case=factor(Case,levels=rev(Case)),Type=ifelse(Case=='Baseline','Reference','Diagnostic'))
pc<-ggplot(c,aes(FI_median,Case))+geom_vline(xintercept=1523.3,linetype='dashed',colour='#BB6B5B',linewidth=.45)+geom_errorbar(aes(xmin=FI_p5,xmax=FI_p95),orientation='y',width=.14,colour='#367D99')+geom_point(aes(shape=Type),size=1.7,colour='#367D99')+scale_shape_manual(values=c(16,18),guide='none')+scale_y_discrete(labels=c('Transit half + aux half + activity 0.75'='Transit 50%, auxiliary 50%, activity 75%'))+labs(x=expression('Diagnostic fuel intensity (L t'^{-1}*')'),y=NULL,title='Separate phase and activity assumptions change fuel intensity')+th+theme(axis.text.y=element_text(size=6))
d<-read_panel('D','Flag_Coverage')%>%select(Flag,Fuel_share_pct,Catch_share_pct)%>%pivot_longer(ends_with('_pct'),names_to='Measure',values_to='Percent')%>%mutate(Measure=recode(Measure,Fuel_share_pct='Fuel',Catch_share_pct='Catch'))
pd<-ggplot(d,aes(reorder(Flag,-Percent),Percent,fill=Measure))+geom_col(position='dodge',width=.7)+scale_fill_manual(values=c(Fuel='#367D99',Catch='#D6AE7C'))+labs(x='Flag',y='Share of matched scope (%)',title='Fuel and catch have different flag compositions')+th
fig<-(pa|pb)/pc/pd+plot_layout(heights=c(.85,1.5,.8))+plot_annotation(tag_levels='a',tag_prefix='(',tag_suffix=')')
for(letter in c('A','B','C','D')){f<-list.files(pattern=paste0('Panel',letter,'_.*csv$'));z<-read.csv(f);write.csv(z,f,row.names=FALSE)}
ggsave('Supplementary_Fig19_Validation.pdf',fig,width=183,height=222,units='mm',device=cairo_pdf,bg='white')
ggsave('Supplementary_Fig19_Validation.png',fig,width=183,height=222,units='mm',dpi=300,bg='white')
ggsave('Supplementary_Fig19_Validation.tiff',fig,width=183,height=222,units='mm',dpi=900,compression='lzw',bg='white')
