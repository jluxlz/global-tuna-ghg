suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork);library(scales)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
rd<-function(s){d<-read.csv(file.path(HERE,paste0('Extended_Fig6_',s,'.csv')));write.csv(d,file.path(HERE,paste0('Extended_Fig6_',s,'_Render_Data.csv')),row.names=FALSE);d}
th<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.title=element_blank(),legend.text=element_text(size=6),legend.key.size=unit(2.5,'mm'),panel.spacing=unit(3,'mm'),plot.margin=margin(5,5,5,5))
cc<-c(CF='#0072B2',CT='#009E73',FT='#A77749');ll<-c(CF='F relative to C',CT='T relative to C',FT='T relative to F')
a<-rd('PanelA_Contributions')
terms<-c('Support vessels','LL/PS fixed processes','Structural-zero cells','GHG per effort','Effort per catch','Within-species catch timing','Species composition','Cumulative catch scale')
a$Term<-factor(a$Term,levels=terms,labels=c('Support vessels','LL/PS fixed processes','Zero-catch transitions','GHG / physical effort','Physical effort / catch','Catch timing','Species composition','Total catch'))
a$Comparison<-factor(a$Comparison,levels=names(cc))
pa<-ggplot(a,aes(Percent_Base_GHG,Term,colour=Comparison))+
 geom_vline(xintercept=0,colour='grey65',linetype='dashed',linewidth=.25)+
 geom_boxplot(orientation='y',width=.5,outlier.shape=NA,linewidth=.3)+
 geom_point(position=position_jitter(height=.12,width=0,seed=17),size=.7,alpha=.7)+
 facet_wrap(~Comparison,nrow=1,scales='free_x',labeller=as_labeller(ll))+
 scale_colour_manual(values=cc,guide='none')+
 labs(tag='(a)',title='Effort requirements dominate the larger C-based contrasts',x='Accounting contribution (% of reference GHG; negative lowers emissions)',y=NULL)+th
b<-rd('PanelB_Biomass');c<-rd('PanelC_Effort')
ratio_plot<-function(d,value,tag,title,ylabel){
 d$Stock<-factor(d$Stock,levels=c('SKJ','YFT','BET','ALB','SBT'));d$Comparison<-factor(d$Comparison,levels=names(cc))
 ggplot(d,aes(Stock,.data[[value]],colour=Comparison))+
  geom_hline(yintercept=1,colour='grey55',linetype='dashed',linewidth=.25)+
  geom_boxplot(position=position_dodge(.7),width=.6,outlier.shape=NA,linewidth=.3)+
  geom_point(position=position_jitterdodge(jitter.width=.10,dodge.width=.7,seed=17),size=.65,alpha=.6)+
  scale_colour_manual(values=cc,labels=ll)+scale_y_log10(labels=label_number(accuracy=.01))+
  labs(tag=tag,title=title,x=NULL,y=ylabel)+th+guides(colour=guide_legend(nrow=1))
}
pb<-ratio_plot(b,'Biomass_Ratio','(b)','Stock responses differ among species','Mean annual biomass ratio')
pc<-ratio_plot(c,'Effort_Ratio','(c)','Catch can require less physical effort','Period effort / catch ratio')
fig<-pa/pb/pc+plot_layout(heights=c(1.6,.9,.9),guides='collect')&theme(legend.position='bottom')
for(ext in c('pdf','png','tiff')){op<-list(filename=file.path(HERE,paste0('Extended_Fig6_Matched_Mechanisms.',ext)),plot=fig,width=183,height=224,units='mm',bg='white');if(ext=='pdf')op$device<-cairo_pdf;if(ext=='png')op$dpi<-300;if(ext=='tiff'){op$dpi<-900;op$compression<-'lzw'};do.call(ggsave,op)}
