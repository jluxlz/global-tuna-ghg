# Preview alternative: grid-era background bubbles and RFMO ratios of totals.
# Sourced by Fig3_Phase_Decoupling.r with bc-era or era-background.
cat("Building era-background Panels (b) and (c)...\n")
era_levels <- c("1970-1990","1991-2005","2006-2025")
era_labels <- c("1970\u20131990","1991\u20132005","2006\u20132024")
era_files <- c("Fig3_PanelB_Era_Grid_Factors.csv","Fig3_PanelC_Era_Grid_Factors.csv",
               "Fig3_PanelB_Era_Regional_Factors.csv","Fig3_PanelC_Era_Regional_Factors.csv")
stopifnot(all(file.exists(era_files)))
source("Fig3_Input_Provenance.r")
verify_fig3_source("Fig3_PanelBC_Era_Audit.json")
bg <- bind_rows(read.csv(era_files[1]),read.csv(era_files[2]))
fg <- bind_rows(read.csv(era_files[3]),read.csv(era_files[4]))
for(d in list(bg,fg)) {
  s <- ifelse(d$Gear=="LL",100,1)
  stopifnot(all(d$Xm>0),all(d$Ym>0),all(d$GHG>0),
    max(abs(d$Xm*d$Ym/s^2/d$CEI-1))<1e-10,
    max(abs(d$Xm/(s*d$Sum_Corrected_Effort/d$Sum_Catch)-1))<1e-10,
    max(abs(d$Ym/(s*d$Sum_GHG/d$Sum_Corrected_Effort)-1))<1e-10)
}
stopifnot(!anyDuplicated(bg[c("Gear","Organization","Era","lon","lat")]),
          !anyDuplicated(fg[c("Gear","Organization","Era")]))
totals <- bg %>% group_by(Gear,Organization,Era) %>%
  summarise(across(c(Sum_Catch,Sum_Corrected_Effort,Sum_GHG),sum),.groups="drop")
checked <- inner_join(fg,totals,by=c("Gear","Organization","Era"),suffix=c("","_grid"))
stopifnot(nrow(checked)==nrow(fg))
for(col in c("Sum_Catch","Sum_Corrected_Effort","Sum_GHG"))
  stopifnot(max(abs(checked[[col]]/checked[[paste0(col,"_grid")]]-1))<1e-10)
bg$Organization <- factor(bg$Organization,levels=names(org_cb_cols))
fg$Organization <- factor(fg$Organization,levels=names(org_cb_cols))
bg$Era <- factor(bg$Era,levels=era_levels,ordered=TRUE)
fg$Era <- factor(fg$Era,levels=era_levels,ordered=TRUE)
fg <- fg[order(fg$Gear,fg$Organization,fg$Era),]

era_fill <- unlist(lapply(org_cb_cols,function(hex) {
  base <- as.numeric(col2rgb(hex))/255
  light <- rgb(base[1]*.4+.6,base[2]*.4+.6,base[3]*.4+.6)
  dark <- rgb(base[1]*.65,base[2]*.65,base[3]*.65)
  c(light,hex,dark)
}))
names(era_fill) <- unlist(lapply(names(org_cb_cols),function(o) paste(o,era_levels,sep="_")))
bg_size_limits <- c(0,max(bg$GHG))
view_records <- list()

# A central display keeps low-catch ratio tails from flattening the regional
# paths. Limits use GHG weights, include EVERY foreground point, and only crop
# the view. Complete grid data still enter both sums and exported CSVs.
weighted_quantile <- function(x,w,p) {
  idx <- order(x)
  approx(c(0,cumsum(w[idx])/sum(w)),c(x[idx[1]],x[idx]),xout=p,rule=2)$y
}
factor_view <- function(d,f,key) {
  bounds <- lapply(c("Xm","Ym"),function(col) {
    r <- if(nrow(d)>10) weighted_quantile(log10(d[[col]]),d$GHG,c(.025,.975)) else range(log10(d[[col]]))
    r <- range(c(r,log10(f[[col]])))
    padding <- max(diff(r)*.07,.08)
    10^(r+c(-padding,padding))
  })
  # Focus the LL display on regional trajectories; all regional points and
  # every source grid still enter the calculations and preserved input tables.
  if(key=="LL") bounds[[2]][2] <- min(bounds[[2]][2],max(f$Ym)*1.6)
  stopifnot(all(f$Ym>=bounds[[2]][1]),all(f$Ym<=bounds[[2]][2]))
  outside <- d$Xm<bounds[[1]][1] | d$Xm>bounds[[1]][2] |
             d$Ym<bounds[[2]][1] | d$Ym>bounds[[2]][2]
  view_records[[key]] <<- data.frame(View=key,N_Grid_Era=nrow(d),N_Outside=sum(outside),
    GHG_Outside_pct=100*sum(d$GHG[outside])/sum(d$GHG),
    Xmin=bounds[[1]][1],Xmax=bounds[[1]][2],Ymin=bounds[[2]][1],Ymax=bounds[[2]][2])
  bounds
}

mk_era_row <- function(d,f,xt,yt,tag=NULL,ncol=5,key,legend=FALSE,bounds=NULL) {
  lim <- if(is.null(bounds)) factor_view(d,f,key) else bounds
  ends <- f %>% group_by(Organization) %>% filter(Era==min(Era)|Era==max(Era)) %>% ungroup()
  ends$Period_Label <- c("1970\u201390","1991\u201305","2006\u201324")[match(ends$Era,era_levels)]
  arrows <- f %>% group_by(Organization) %>% mutate(NextX=lead(Xm),NextY=lead(Ym)) %>%
    filter(!is.na(NextX)) %>% ungroup() %>% mutate(
      Xstart=10^(.7*log10(Xm)+.3*log10(NextX)),Xend=10^(.3*log10(Xm)+.7*log10(NextX)),
      Ystart=10^(.7*log10(Ym)+.3*log10(NextY)),Yend=10^(.3*log10(Ym)+.7*log10(NextY)))
  # All periods remain in the shape legend even for the sparse CCSBT facet.
  p <- ggplot()+
    geom_point(data=d,aes(Xm,Ym,size=GHG),shape=16,colour="grey55",alpha=.22)+
    geom_path(data=f,aes(Xm,Ym,group=Organization),colour="grey25",linewidth=.5)+
    geom_segment(data=arrows,aes(x=Xstart,y=Ystart,xend=Xend,yend=Yend),colour="grey25",linewidth=.5,
      arrow=arrow(length=unit(.08,"cm"),type="closed"))+
    geom_point(data=f,aes(Xm,Ym,shape=Era,fill=interaction(Organization,Era,sep="_")),
      size=2.8,colour="grey20",stroke=.45,show.legend=c(shape=TRUE,fill=TRUE,size=FALSE))+
    geom_text_repel(data=ends,aes(Xm,Ym,label=Period_Label),size=1.7,family="sans",
      colour="grey20",seed=42,max.overlaps=Inf,box.padding=.3,point.padding=.35,
      min.segment.length=.1,segment.size=.25,show.legend=FALSE)+
    scale_size_area(name=expression(Grid~era~GHG~(Mt~CO[2]*e)),limits=bg_size_limits,
      max_size=4.5,breaks=c(.1,1,5),guide=guide_legend(order=3,nrow=1,
      override.aes=list(alpha=.55,shape=16,colour="grey60")))+
    scale_shape_manual(name="Regional era",values=setNames(c(21,24,22),era_levels),
      limits=era_levels,labels=era_labels,drop=FALSE,
      guide=guide_legend(order=2,nrow=1,override.aes=list(fill="grey70",size=2.8)))+
    scale_fill_manual(values=era_fill,limits=names(era_fill),name="RFMO",
      breaks=paste(names(org_cb_cols),"1991-2005",sep="_"),labels=names(org_cb_cols),
      guide=guide_legend(order=1,nrow=1,
        override.aes=list(fill=unname(org_cb_cols),shape=21,size=2.8)))+
    (if(key=="LL") scale_x_log10(breaks=c(1e5,1e6,1e7),labels=c("100k","1M","10M"))
      else scale_x_log10(labels=comma_format()))+
    (if(key=="LL") scale_y_log10(breaks=c(.1,.2,.3,.4,.6),labels=comma_format()) else scale_y_log10(labels=comma_format()))+
    coord_cartesian(xlim=lim[[1]],ylim=lim[[2]])+
    facet_wrap(~Organization,ncol=ncol)+labs(tag=tag,x=xt,y=yt)+theme_pub+
    theme(legend.position=if(legend)"bottom" else "none",legend.box="vertical",
      legend.spacing.y=unit(1,"pt"),plot.margin=margin(4,2,1,2,unit="pt"))
  if(key=="PS_CCSBT") p <- p+annotate("text",x=lim[[1]][1]*1.1,y=lim[[2]][1]*1.9,
    label="No retained data\n1991\u20132005",hjust=0,size=1.65,colour="grey45",family="sans")
  p
}
p_b <- mk_era_row(bg[bg$Gear=="LL",],fg[fg$Gear=="LL",],
  "Standardized hooks per 100 t of catch",expression(t~CO[2]*e~per~100~standardized~hooks),
  "(b)",key="LL")
p_c_main <- mk_era_row(bg[bg$Gear=="PS" & bg$Organization!="CCSBT",],
  fg[fg$Gear=="PS" & fg$Organization!="CCSBT",],"Standardized sets per metric ton of catch",
  expression(t~CO[2]*e~per~standardized~set),"(c)",ncol=4,key="PS",legend=TRUE)
p_c_ccsbt <- mk_era_row(bg[bg$Gear=="PS" & bg$Organization=="CCSBT",],
  fg[fg$Gear=="PS" & fg$Organization=="CCSBT",],"Standardized sets per metric ton of catch",NULL,ncol=1,key="PS_CCSBT")
# Collect identical x titles across the four main facets AND the CCSBT facet.
# Give the shared guides the same full width instead of attaching them to only
# the four left-hand facets.
p_c_body <- (p_c_main+theme(legend.position="none")) + p_c_ccsbt +
  plot_layout(widths=c(4,1),axis_titles="collect_x") &
  theme(axis.title.x=element_text(hjust=.5))
p_c <- shared_horizontal_legend(p_c_body,p_c_main,174,"Fig3c")
bc_caption <- NULL
preview <- (p_b/p_c)+plot_layout(heights=c(1,1))
for(gear in c("LL","PS")) {
  letter <- if(gear=="LL")"B" else "C"
  write.csv(bg[bg$Gear==gear,],paste0("Fig3_Panel",letter,"_Era_Grid_Factors.csv"),row.names=FALSE)
  write.csv(fg[fg$Gear==gear,],paste0("Fig3_Panel",letter,"_Era_Regional_Factors.csv"),row.names=FALSE)
}
write.csv(bind_rows(view_records),"Fig3_PanelBC_Era_Display_Coverage.csv",row.names=FALSE)
ggsave("Fig3_PanelBC_Era_Background.png",preview,width=183,height=125,units="mm",dpi=300,
       device=grDevices::png,type="cairo",bg="white")
ggsave("Fig3_PanelBC_Era_Background.pdf",preview,width=183,height=125,units="mm",device=cairo_pdf,bg="white")
cat("  Era-background preview complete.\n")
