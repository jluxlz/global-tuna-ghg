# C/F, C/T and F/T matching and exact whole-fleet accounting.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
rd<-function(s){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig21_Panel',s,'.csv')));write.csv(d,file.path(HERE,paste0('Supplementary_Fig21_Panel',s,'_Render_Data.csv')),row.names=FALSE,na='');d}
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=6.5,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.title=element_blank(),legend.key.size=unit(2.5,'mm'),plot.margin=margin(5,5,5,5),panel.spacing=unit(2,'mm'))
cc<-c(CF='#0072B2',CT='#009E73',FT='#B57A4A')
a<-rd('A_Matching')
pa<-ggplot(a,aes(Base_Catch_Mt,Policy_Catch_Mt,colour=Comparison))+
 geom_abline(slope=1,intercept=0,linetype='dashed',colour='grey55',linewidth=.25)+geom_point(size=1.4)+
 scale_colour_manual(values=cc,labels=c(CF='C/F',CT='C/T',FT='F/T'))+
 labs(tag='(a)',x='Reference cumulative catch (Mt)',y='Compared-rule catch (Mt)')+th
b<-rd('B_Emissions')
pb<-ggplot(b,aes(Comparison,Whole_Fleet_GHG_Reduction_pct,colour=Comparison))+
 geom_hline(yintercept=0,colour='grey60',linetype='dashed',linewidth=.25)+
 geom_boxplot(width=.5,outlier.shape=NA,linewidth=.25)+geom_point(position=position_jitter(width=.08,seed=17),size=.9)+
 scale_colour_manual(values=cc,guide='none')+
 labs(tag='(b)',x=NULL,y='Whole-fleet GHG reduction (%)')+th
c<-rd('C_Decomposition')
terms<-c('Cumulative catch scale','Species composition','Within-species catch timing','Effort per catch','GHG per effort','Structural-zero cells','LL/PS fixed processes','Support vessels')
short<-c('Catch scale','Species mix','Catch timing','Effort/catch','GHG/effort','Structural zeros','LL/PS fixed','Support vessels')
c$Term<-factor(c$Term,levels=terms,labels=short)
cs<-c%>%group_by(Comparison,Term)%>%summarise(Mean=mean(Delta_Mt),.groups='drop')
write.csv(cs,file.path(HERE,'Supplementary_Fig21_PanelC_Mean_Contributions.csv'),row.names=FALSE)
pc<-ggplot(cs,aes(Term,Mean,fill=Comparison))+geom_hline(yintercept=0,colour='grey60',linewidth=.2)+
 geom_col(position=position_dodge(.75),width=.7)+coord_flip()+scale_fill_manual(values=cc)+
 labs(tag='(c)',x=NULL,y='Mean GHG difference (Mt CO2e)')+th
d<-rd('D_Weights')%>%pivot_longer(c(Whole_Fleet_GHG_Reduction_pct,Variable_GHG_Reduction_pct,Common_Species_Intensity_Reduction_pct,Common_Species_Year_Intensity_Reduction_pct),names_to='Scope',values_to='Reduction')
d$Scope<-factor(d$Scope,levels=c('Whole_Fleet_GHG_Reduction_pct','Variable_GHG_Reduction_pct','Common_Species_Intensity_Reduction_pct','Common_Species_Year_Intensity_Reduction_pct'),labels=c('Whole fleet','LL/PS activity','Common species','Common species-year'))
pd<-ggplot(d,aes(Scope,Reduction,colour=Comparison))+
 geom_hline(yintercept=0,colour='grey60',linewidth=.2)+
 geom_boxplot(position=position_dodge(.7),width=.65,outlier.size=.3,linewidth=.25)+coord_flip()+
 scale_colour_manual(values=cc)+labs(tag='(d)',x=NULL,y='GHG or intensity reduction (%)')+th
e<-rd('E_Stock_Effort')%>%filter(Future=='F41',Comparison=='FT')
if(nrow(e)>0){
 el<-e%>%select(Year,Stock,Pair_Member,B_Bmsy_Start,Effort_per_t)%>%pivot_longer(c(B_Bmsy_Start,Effort_per_t),names_to='Metric',values_to='Value')
 el$Stock<-factor(el$Stock,levels=c('SKJ','YFT','BET','ALB','SBT'))
 el$Metric<-factor(el$Metric,levels=c('B_Bmsy_Start','Effort_per_t'),labels=c('B / BMSY','Effort/catch (kW-days/t)'))
 pe<-ggplot(el,aes(Year,Value,colour=Pair_Member))+
  geom_line(linewidth=.45,na.rm=TRUE)+facet_wrap(vars(Metric,Stock),ncol=5,scales='free_y')+
  scale_colour_manual(values=c(Base='#0072B2',Policy='#009E73'),labels=c(Base='Adjusted F',Policy='Adjusted T'))+
  scale_x_continuous(breaks=c(2025,2050))+
  labs(tag='(e)',x='Year',y=NULL)+th+theme(strip.text=element_text(size=5.7))
}else pe<-ggplot()+annotate('text',x=0,y=0,label='Central F41 F/T matching did not meet the catch criterion',size=2.5)+theme_void()+labs(tag='(e)')
fig<-(pa|pb)/(pc|pd)/pe+plot_layout(heights=c(.8,1.15,1.2))
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Supplementary_Fig21_HCR_Matched_Mechanisms.',ext)),plot=fig,width=183,height=247,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
