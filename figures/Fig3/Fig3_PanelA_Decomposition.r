# Sourced by Fig3_Phase_Decoupling.r after its path, palette and theme setup.
cat("Reading decomposed annual trends...\n")
trend_file <- "Fig3_PanelA_Factor_Trends.csv"
if (!file.exists(trend_file)) stop("Run C:/CONDA/python preprocess_fig3.py first.")
if (file.info(trend_file)$mtime < file.info(file.path(DATA_DIR,"Base_3_Spatial_Grid_Enriched.csv"))$mtime)
  stop("Fig3 trends are older than Base_3. Rerun preprocess_fig3.py.")
df_c<-read.csv(trend_file)
stopifnot(all(is.finite(df_c$Effort_log_trend_pct)), all(is.finite(df_c$GHG_Effort_log_trend_pct)),
          all(df_c$Total_GHG>0), !anyDuplicated(df_c[c("Gear","lon","lat","Era")]),
          max(abs(df_c$Effort_log_trend_pct + df_c$GHG_Effort_log_trend_pct - df_c$CEI_log_trend_pct)) < 1e-10)
era_levels<-c("1970-1990","1991-2005","2006-2025")
df_c$Era<-factor(df_c$Era,levels=era_levels)
make_era_cols<-function(hex){rgb0<-col2rgb(hex)/255;c(rgb(rgb0[1]*.7+.3,rgb0[2]*.7+.3,rgb0[3]*.7+.3),rgb(rgb0[1],rgb0[2],rgb0[3]),rgb(rgb0[1]*.45,rgb0[2]*.45,rgb0[3]*.45))}

# Each grid x gear contributes up to 3 log-trend bubbles.
# Hooks and sets are never summed; both trend axes have units % yr^-1.
sp_levels<-c("All","SKJ","YFT","BET","ALB","SBT")
stopifnot(all(df_c$Dominant_Species %in% sp_levels))
df_ca<-df_c;df_ca$Dominant_Species<-factor("All",levels=sp_levels)
df_c$Dominant_Species<-factor(df_c$Dominant_Species,levels=sp_levels)
df_c<-rbind(df_ca,df_c)
# Full-data emission-weighted centroids, before any display zoom.
cent<-df_c%>%group_by(Dominant_Species,Era)%>%summarise(
  Xc=weighted.mean(Effort_log_trend_pct,Total_GHG),
  Yc=weighted.mean(GHG_Effort_log_trend_pct,Total_GHG),
  CEIc=weighted.mean(CEI_log_trend_pct,Total_GHG),
  Total_GHG=sum(Total_GHG),N_Grid_Gear=n(),
  N_LL=sum(Gear=="LL"),N_PS=sum(Gear=="PS"),.groups="drop")%>%arrange(Dominant_Species,Era)
stopifnot(max(abs(cent$Xc+cent$Yc-cent$CEIc))<1e-10)
# Symmetric common axes; 99% view only, with all centroids visible.
# coord_cartesian clips the view without removing or altering observations.
lim<-ceiling(max(quantile(abs(c(df_c$Effort_log_trend_pct,df_c$GHG_Effort_log_trend_pct)),.99),
                 abs(c(cent$Xc,cent$Yc)))/5)*5
df_c$In_View<-abs(df_c$Effort_log_trend_pct)<=lim & abs(df_c$GHG_Effort_log_trend_pct)<=lim
view_counts<-df_c%>%group_by(Dominant_Species,Era)%>%summarise(
  N_Total=n(),N_Outside_View=sum(!In_View),
  GHG_Outside_View=sum(Total_GHG[!In_View]),Total_GHG=sum(Total_GHG),.groups="drop")
write.csv(view_counts,"Fig3_PanelA_Display_Coverage.csv",row.names=FALSE)

spk<-c();for(s in names(species_cols))for(e in era_levels)spk<-c(spk,paste(s,e,sep="_"))
spc<-unlist(lapply(species_cols,make_era_cols));names(spc)<-spk
p_a<-ggplot(df_c,aes(x=Effort_log_trend_pct,y=GHG_Effort_log_trend_pct))+
  geom_abline(slope=-1,intercept=0,linetype="dotted",colour="grey40",linewidth=0.4)+
  geom_vline(xintercept=0,linetype="dashed",colour="grey50",linewidth=0.4)+
  geom_hline(yintercept=0,linetype="dashed",colour="grey50",linewidth=0.4)+
  geom_point(aes(size=Total_GHG,fill=interaction(Dominant_Species,Era,sep="_")),shape=21,colour="transparent",stroke=0,alpha=0.25)+
  geom_path(data=cent,aes(x=Xc,y=Yc,group=Dominant_Species),colour="grey20",linewidth=0.6,arrow=arrow(length=unit(0.12,"cm"),type="closed"))+
  geom_point(data=cent,aes(x=Xc,y=Yc,shape=Era,fill=interaction(Dominant_Species,Era,sep="_")),size=3,colour="grey10",stroke=0.5,alpha=1)+
  facet_wrap(~Dominant_Species,ncol=3)+
  scale_fill_manual(values=spc,name="Dominant species",
    breaks=c("SKJ_1991-2005","YFT_1991-2005","BET_1991-2005","ALB_1991-2005","SBT_1991-2005"),
    labels=c("SKJ","YFT","BET","ALB","SBT"),
    guide=guide_legend(override.aes=list(alpha=1,size=3,shape=21,colour="grey30"),nrow=1))+
  scale_shape_manual(values=c(21,24,22),name="Centroid era",labels=c("1970-1990","1991-2005","2006-2024"),guide=guide_legend(nrow=1,override.aes=list(fill="grey70")))+
  scale_size_area(max_size=6,breaks=c(1e5,1e6,1e7),labels=c("0.1","1","10"),name=expression(Grid~era~GHG~(Mt~CO[2]*e)),guide=guide_legend(override.aes=list(fill="grey50",alpha=1)))+
  scale_x_continuous(labels=comma_format(),expand=expansion(mult=c(.04,.04)))+
  scale_y_continuous(labels=comma_format(),expand=expansion(mult=c(.04,.04)))+
  coord_cartesian(xlim=c(-lim,lim),ylim=c(-lim,lim))+
  labs(tag="(a)",x=expression("Trend in standardised effort per tonne of catch ("*"%"~yr^{-1}*"; log trend)"),
       y=expression(atop("Trend in GHG per unit of standardised effort","("*"%"~yr^{-1}*"; log trend)")))+
  theme_pub+theme(panel.spacing=unit(1,"lines"),legend.box="vertical",legend.box.spacing=unit(3,"pt"),
                  plot.caption=element_text(size=6,hjust=0),legend.justification="centre")
write.csv(df_c,"Fig3_PanelA_Phase_Space.csv",row.names=FALSE)
write.csv(cent,"Fig3_PanelA_Weighted_Centroids.csv",row.names=FALSE)
p_a_plot <- horizontal_legend_plot(p_a,174,"Fig3a")
ggsave("Fig3_PanelA_Decomposition.png",plot=p_a_plot,width=183,height=145,units="mm",dpi=300,bg="white",device=grDevices::png,type="cairo")
ggsave("Fig3_PanelA_Decomposition.pdf",plot=p_a_plot,width=183,height=145,units="mm",device=cairo_pdf,bg="white")
cat("  Panel (a) complete.\n")
