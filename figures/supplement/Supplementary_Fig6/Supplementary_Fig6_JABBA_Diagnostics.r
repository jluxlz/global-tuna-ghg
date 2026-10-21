# Actual JABBA fits and MCMC diagnostics. Official reports supply context.
suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(patchwork);library(scales)})
arg <- grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE <- dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
a <- read.csv(file.path(HERE,'Supplementary_Fig6_PanelA_Biomass.csv'))
b <- read.csv(file.path(HERE,'Supplementary_Fig6_PanelB_CPUE_Fits.csv'))
c <- read.csv(file.path(HERE,'Supplementary_Fig6_PanelCD_Core_MCMC.csv'))
stock_order <- c('SKJ','YFT','BET','ALB','SBT')
for(obj in c('a','b','c')) {d <- get(obj); d$Stock <- factor(d$Stock,levels=stock_order);assign(obj,d)}
sp <- c(SKJ='#984EA3',YFT='#FF7F00',BET='#377EB8',ALB='#E41A1C',SBT='#4DAF4A')
theme_pub <- theme_classic(base_size=7,base_family='Arial') + theme(
  axis.title=element_text(size=7,face='bold'),axis.text=element_text(size=6,colour='black'),
  axis.line=element_line(linewidth=.18),axis.ticks=element_line(linewidth=.18),
  strip.background=element_blank(),strip.text=element_text(size=7,face='bold'),
  plot.tag=element_text(size=8,face='bold'),legend.position='bottom',
  legend.text=element_text(size=6),legend.title=element_text(size=7,face='bold'),
  legend.key.size=unit(3,'mm'),panel.spacing=unit(3,'mm'),plot.margin=margin(4,5,4,4,'pt'))
p_a <- ggplot(a,aes(Year,Median,colour=Stock,fill=Stock)) +
  geom_hline(yintercept=.5,linetype='dotted',colour='grey55',linewidth=.2) +
  geom_ribbon(aes(ymin=Lower,ymax=Upper),alpha=.18,colour=NA) + geom_line(linewidth=.45) +
  facet_wrap(~Stock,nrow=1) + scale_colour_manual(values=sp,guide='none') + scale_fill_manual(values=sp,guide='none') +
  scale_x_continuous(breaks=c(1970,2024),labels=c('1970','2024')) +
  labs(tag='(a)',x=NULL,y='Posterior biomass / K') + theme_pub
b$Series <- ifelse(b$name=='Index',ifelse(b$Stock=='SBT','LL_CCSBT','Index'),b$name)
p_b <- ggplot(b,aes(year,Series,fill=residual)) + geom_tile(height=.88) +
  facet_grid(Stock~.,scales='free_y',space='free_y',switch='y') +
  scale_fill_gradient2(low='#2166AC',mid='white',high='#B2182B',midpoint=0,
    name='log(observed / fitted)',limits=c(-2,2),oob=scales::squish,
    guide=guide_colourbar(barwidth=unit(55,'mm'),barheight=unit(2.5,'mm'))) +
  scale_x_continuous(breaks=c(1970,1985,2000,2015,2024),expand=c(0,0)) +
  labs(tag='(b)',x=NULL,y='CPUE index') + theme_pub +
  theme(axis.line.y=element_blank(),axis.ticks.y=element_blank(),strip.text=element_text(size=6),panel.spacing=unit(1.5,'mm'))
c$Parameter_class <- ifelse(grepl('^q',c$Parameter),'q (indices)',c$Parameter)
c$Parameter_class[c$Parameter=='P[55]']<-'Terminal B / K'
c$Parameter_class[c$Parameter=='F[55]']<-'Terminal F'
c$Parameter_class[c$Parameter=='Terminal_B']<-'Terminal B'
shape_values<-c(K=15,psi=17,'q (indices)'=1,r=16,sigma2=18,MSY=8,'Terminal B / K'=0,'Terminal F'=3,'Terminal B'=2)
p_c <- ggplot(c,aes(Rhat,Stock,colour=Stock,shape=Parameter_class)) +
  geom_vline(xintercept=1.01,linetype='dotted',colour='grey45',linewidth=.2) +
  geom_point(position=position_dodge(width=.55),size=1.7,alpha=.85) +
  scale_colour_manual(values=sp,guide='none') +
  scale_shape_manual(values=shape_values,name='Parameter',guide=guide_legend(nrow=2)) +
  labs(tag='(c)',x='Rank-normalised split/folded Rhat',y=NULL) + theme_pub
p_d <- ggplot(c,aes(n.eff,Stock,colour=Stock,shape=Parameter_class)) +
  geom_vline(xintercept=400,linetype='dotted',colour='grey45',linewidth=.2) +
  geom_point(position=position_dodge(width=.55),size=1.7,alpha=.85) +
  scale_x_log10(breaks=c(400,1000,4000,16000,40000),labels=comma) +
  scale_colour_manual(values=sp,guide='none') +
  scale_shape_manual(values=shape_values,name='Parameter',guide=guide_legend(nrow=2)) +
  labs(tag='(d)',x='Bulk effective sample size',y=NULL) + theme_pub
source(file.path(HERE,'Legend_Layout.r'))
bottom_body <- (p_c | p_d) & theme(legend.position='none')
bottom <- shared_horizontal_legend(bottom_body,p_c,174,'ED5cd')
fig <- p_a / p_b / bottom + plot_layout(heights=c(.75,1.8,1))
for(ext in c('pdf','png','tiff')) {
  opts <- list(filename=file.path(HERE,paste0('Supplementary_Fig6_Stock_Structure_Robustness.',ext)),plot=fig,width=183,height=230,units='mm',bg='white')
  if(ext=='pdf') opts$device <- cairo_pdf
  if(ext=='png') opts$dpi <- 300
  if(ext=='tiff') {opts$dpi<-900;opts$compression<-'lzw'}
  do.call(ggsave,opts)
}
write.csv(a,file.path(HERE,'Supplementary_Fig6_PanelA_Render_Data.csv'),row.names=FALSE)
write.csv(b,file.path(HERE,'Supplementary_Fig6_PanelB_Render_Data.csv'),row.names=FALSE)
write.csv(c,file.path(HERE,'Supplementary_Fig6_PanelC_Render_Data.csv'),row.names=FALSE)
write.csv(c,file.path(HERE,'Supplementary_Fig6_PanelD_Render_Data.csv'),row.names=FALSE)
