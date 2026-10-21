suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(tidyr);library(patchwork)})
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE);HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
rp<-function(x){d<-read.csv(file.path(HERE,paste0('Supplementary_Fig22_Panel',x,'.csv')),colClasses=c(Combo='character'));write.csv(d,file.path(HERE,paste0('Supplementary_Fig22_Panel',x,'_Render_Data.csv')),row.names=FALSE);d}
tp<-theme_classic(base_size=7,base_family='Arial')+theme(axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),plot.tag=element_text(size=8,face='bold'),legend.position='bottom',legend.text=element_text(size=6),legend.key.size=unit(3,'mm'),plot.margin=margin(5,5,5,5,'pt'))
display_labs<-c('Constrained BAU'='Feasible-catch BAU','C-type quota'='C-type quota','F-type quota'='F-type quota')
cols<-c('Constrained BAU'='#222222','C-type quota'='#CC79A7','F-type quota'='#0072B2')
a<-rp('A_LMDI')%>%filter(Max_Days==365,Combo%in%c('C_type','1000'))%>%mutate(Rule=ifelse(Combo=='1000','F-type quota','C-type quota'))%>%pivot_longer(c(Catch_Effect_Mt,CEI_Effect_Mt),names_to='Factor',values_to='Effect')
a$Factor<-factor(a$Factor,levels=c('Catch_Effect_Mt','CEI_Effect_Mt'),labels=c('Catch scale','Period CEI'))
pa<-ggplot(a,aes(Factor,Effect,fill=Factor))+geom_hline(yintercept=0,linewidth=.2,colour='grey55')+geom_boxplot(width=.6,outlier.size=.35,linewidth=.25)+facet_wrap(~Rule)+scale_fill_manual(values=c('Catch scale'='#E69F00','Period CEI'='#0072B2'),guide='none')+labs(tag='(a)',x=NULL,y=expression('LMDI change (Mt CO'[2]*'e)'))+tp
b<-rp('B_Catch_CEI')%>%filter(Max_Days==365,Combo%in%c('0000','C_type','1000'))%>%mutate(Rule=recode(Combo,'0000'='Constrained BAU','C_type'='C-type quota','1000'='F-type quota'))
pb<-ggplot(b,aes(Cumulative_Fleet_Catch_Mt,Period_CEI,colour=Rule))+geom_point(size=1,alpha=.6)+scale_colour_manual(values=cols,labels=display_labs)+labs(tag='(b)',x='Cumulative LL/PS catch (Mt)',y=expression('Period CEI (t CO'[2]*'e / t catch)'))+tp
c<-rp('C_Matched')
pairs<-bind_rows(transmute(c,Future,Catch_Mt=C_Catch_Mt,GHG_Mt=C_GHG_Mt,Rule='C-type quota'),transmute(c,Future,Catch_Mt=F_Catch_Mt,GHG_Mt=F_GHG_Mt,Rule='F-type quota'))
pc<-ggplot(pairs,aes(Catch_Mt,GHG_Mt,group=Future))+geom_line(linewidth=.25,colour='grey65')+geom_point(aes(colour=Rule,shape=Rule),size=1.6)+scale_colour_manual(values=cols,labels=display_labs)+scale_shape_manual(values=c('C-type quota'=16,'F-type quota'=17))+labs(tag='(c)',x='Matched cumulative LL/PS catch (Mt)',y=expression('Cumulative GHG (Mt CO'[2]*'e)'))+tp
d<-rp('D_Closest')
pd<-ggplot(d,aes(100*Relative_Catch_Gap,GHG_Reduction_pct))+geom_vline(xintercept=c(-1,1),linetype='dotted',linewidth=.25,colour='grey50')+geom_point(size=1.8,colour='#0072B2')+labs(tag='(d)',x='F minus C cumulative catch difference (%)',y='F versus C cumulative GHG reduction (%)')+tp
fig<-(pa/pb/(pc|pd))+plot_layout(heights=c(1,1,1.1),guides='collect')&theme(legend.position='bottom')
for(ext in c('pdf','png','tiff')){opt<-list(filename=file.path(HERE,paste0('Supplementary_Fig22_Catch_Efficiency_Decomposition.',ext)),plot=fig,width=183,height=200,units='mm',bg='white');if(ext=='pdf')opt$device<-cairo_pdf;if(ext=='png')opt$dpi<-300;if(ext=='tiff'){opt$dpi<-900;opt$compression<-'lzw'};do.call(ggsave,opt)}
