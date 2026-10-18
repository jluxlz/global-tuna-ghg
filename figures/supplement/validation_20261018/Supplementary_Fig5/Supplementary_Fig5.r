library(ggplot2);library(dplyr);library(tidyr);library(patchwork)
args<-commandArgs(FALSE);self<-sub('--file=','',args[grepl('^--file=',args)])[1];setwd(dirname(normalizePath(self)))
read_panel<-function(letter,name)read.csv(paste0('Supplementary_Fig5_Panel',letter,'_',name,'.csv'))
th<-theme_classic(base_size=7,base_family='sans')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.text=element_text(size=7,face='bold'),legend.position='bottom',legend.title=element_blank(),legend.text=element_text(size=6),plot.title=element_text(size=8,face='bold'),plot.tag=element_text(size=8,face='bold'),plot.margin=margin(5,7,5,5))
cols<-c('Effort / catch'='#C17C43','GHG / effort'='#367D99','CEI'='#494949')
a<-read_panel('A','Rates')%>%pivot_longer(c(X,Y,CEI),names_to='Factor',values_to='Trend')%>%mutate(Factor=recode(Factor,X='Effort / catch',Y='GHG / effort'))
pa<-ggplot(a,aes(d_pct,Trend,colour=Factor))+geom_hline(yintercept=0,linewidth=.25,colour='grey70')+geom_line(linewidth=.4)+geom_point(aes(shape=Rate_Label=='Adopted'),size=1.3)+facet_grid(Gear~Era)+scale_colour_manual(values=cols)+scale_shape_manual(values=c(16,8),guide='none')+labs(x='Effort-correction parameter d (% per year)',y='GHG-weighted log trend (% per year)',title='Factor trends depend on the effort correction')+th
b<-read_panel('B','Fractions')%>%select(Gear,d_pct,Effort_up_count_pct,Offset_count_pct)%>%pivot_longer(ends_with('_pct'),names_to='Measure',values_to='Percent')
# d_pct was kept as the x coordinate, not a response.
b<-read_panel('B','Fractions')%>%pivot_longer(c(Effort_up_count_pct,Offset_count_pct),names_to='Measure',values_to='Percent')%>%mutate(Measure=recode(Measure,Effort_up_count_pct='Effort / catch increases',Offset_count_pct='Effort rises, GHG / effort falls'))
pb<-ggplot(b,aes(d_pct,Percent,colour=Measure))+geom_line(linewidth=.45)+geom_point(size=1.1)+facet_wrap(~Gear)+scale_colour_manual(values=c('#C17C43','#367D99'))+scale_y_continuous(limits=c(0,100),breaks=c(0,50,100))+labs(x='Correction parameter d (% per year)',y='Grid proportion (%)',title='Recent-period signs change across assumptions')+th
c<-read_panel('C','Thresholds')%>%mutate(Era=factor(Era,levels=c('1970-1990','1991-2005','2006-2024')))
pc<-ggplot(c,aes(Era,Critical_d_pct,fill=Gear))+geom_col(position=position_dodge(width=.7),width=.6)+geom_text(aes(label=sprintf('%.2f',Critical_d_pct)),position=position_dodge(width=.7),vjust=-.5,size=2)+scale_fill_manual(values=c(LL='#367D99',PS='#4C9B8C'))+scale_y_continuous(expand=expansion(mult=c(0,.22)))+labs(x=NULL,y='Critical correction d (%)',title='Minimum rate for a positive mean effort trend')+th+theme(axis.text.x=element_text(size=5.8))
d<-read_panel('D','Stock_Context');stock<-d%>%select(Stock,Year,Stock_index)%>%distinct()%>%mutate(Metric='Assessment index',Value=Stock_index)
eff<-d%>%mutate(Metric=ifelse(Rate_Label=='Adopted','Adjusted effort / catch','Nominal effort / catch'),Value=Effort_index)
dd<-bind_rows(stock,eff)
pd<-ggplot(dd,aes(Year,Value,colour=Metric,linetype=Metric))+geom_hline(yintercept=1,colour='grey85',linewidth=.25)+geom_line(linewidth=.5)+facet_wrap(~Stock,scales='free_x')+scale_colour_manual(values=c('Assessment index'='#367D99','Adjusted effort / catch'='#C17C43','Nominal effort / catch'='#868686'))+scale_linetype_manual(values=c('Assessment index'='solid','Adjusted effort / catch'='solid','Nominal effort / catch'='dashed'))+labs(x='Year',y='Index (first year = 1)',title='Stock context supports heterogeneous effort responses')+th
fig<-pa/(pb|pc)/pd+plot_layout(heights=c(1.28,1,1.05),guides='keep')+plot_annotation(tag_levels='a',tag_prefix='(',tag_suffix=')')
for(letter in c('A','B','C','D')){f<-list.files(pattern=paste0('Panel',letter,'_.*csv$'));z<-read.csv(f);write.csv(z,f,row.names=FALSE)}
ggsave('Supplementary_Fig5_Validation.pdf',fig,width=183,height=239,units='mm',device=cairo_pdf,bg='white')
ggsave('Supplementary_Fig5_Validation.png',fig,width=183,height=239,units='mm',dpi=300,bg='white')
ggsave('Supplementary_Fig5_Validation.tiff',fig,width=183,height=239,units='mm',dpi=900,compression='lzw',bg='white')
