# Approved compact layout; shared footer and aligned geographic panels.
compact_map_matrices <- function(p_a,p_cpue,p_cei,p_ghg,output_dir=".") {
# Same aligned map columns and geographic aspect as the approved figure.
era_plots <- lapply(levels(p_a$data$Era),function(era) {
  p <- unserialize(serialize(p_a,NULL))
  p$data <- droplevels(p$data[p$data$Era==era,])
  for(i in seq_along(p$layers)) {
    d <- p$layers[[i]]$data
    if(is.data.frame(d) && "Era" %in% names(d))
      p$layers[[i]]$data <- droplevels(d[d$Era==era,])
  }
  p + facet_grid(Gear~Era,switch="y")
})
metric_plots <- lapply(list(p_cpue,p_cei,p_ghg),function(p)
  p + facet_grid(Gear~Metric,switch="y"))
map_plots <- c(era_plots,metric_plots)
maps <- lapply(map_plots,function(p) ggplotGrob(p+labs(tag=NULL,x=NULL,y=NULL)+
  theme(legend.position="none",panel.spacing=unit(2,"mm"),plot.margin=margin(0,0,0,0,"mm"))))
common_w <- do.call(grid::unit.pmax,lapply(maps,`[[`,"widths"))
common_h <- do.call(grid::unit.pmax,lapply(maps,`[[`,"heights"))
panel_ids <- grepl("^panel-",maps[[1]]$layout$name)
panel_col <- unique(maps[[1]]$layout$l[panel_ids])
panel_rows <- sort(unique(maps[[1]]$layout$t[panel_ids]))
stopifnot(length(panel_col)==1,length(panel_rows)==2)
W_MM <- 183; margin_mm <- 1.5;gap_mm <- 1.5
col_mm <- (W_MM-2*margin_mm-2*gap_mm)/3
panel_mm <- col_mm-grid::convertWidth(sum(common_w[-panel_col]),"mm",TRUE)
common_w[panel_col] <- unit(panel_mm,"mm")
common_h[panel_rows] <- unit(panel_mm/3,"mm")
maps <- lapply(maps,function(g) {g$widths<-common_w;g$heights<-common_h;g$respect<-FALSE;g})
map_h <- grid::convertHeight(sum(common_h),"mm",TRUE)

# Four independent colour bars keep the exact production palettes and limits.
bar_sources <- c(list(p_a),list(p_cpue,p_cei,p_ghg))
bar_titles <- list("a: CEI\n(t CO\u2082e t\u207b\u00b9)",
                   "b: CPUE trend\n(%/yr)","b: CEI trend\n(%/yr)","b: GHG trend\n(%/yr)")
bars <- lapply(seq_along(bar_sources),function(i) {
  p <- unserialize(serialize(bar_sources[[i]],NULL))
  if(i==1) {
    fill_scale <- p$scales$get_scales("fill")
    fill_scale$labels <- function(x)
      vapply(x,function(v)format(v,trim=TRUE,scientific=FALSE),character(1))
  }
  p <- p +
    guides(colour="none",shape="none",fill=guide_colorsteps(title=bar_titles[[i]],even.steps=FALSE,
      show.limits=TRUE,title.position="top",title.hjust=.5,
      barwidth=unit(if(i==1)36 else 32,"mm"),barheight=unit(2.5,"mm"))) +
    theme(legend.position="bottom",legend.direction="horizontal",
          legend.title=element_text(size=7),legend.text=element_text(size=6),
          legend.margin=margin(0,0,0,0,"mm"))
  out <- legend_objects(p)
  stopifnot(length(out)==1)
  out[[1]]
})
stopifnot(length(unique(vapply(bars,function(g)length(g$heights),integer(1))))==1)
bar_heights <- do.call(grid::unit.pmax,lapply(bars,`[[`,"heights"))
bars <- lapply(bars,function(g) {g$heights<-bar_heights;g})
bar_h <- max(vapply(bars,function(g)grid::convertHeight(sum(g$heights),"mm",TRUE),numeric(1)))
symbol_source <- p_a +
  guides(fill="none",colour=guide_legend(title="RFMO",nrow=1,override.aes=list(linewidth=.6)),
         shape=guide_legend(title="Dominant species",nrow=1,override.aes=list(size=2,alpha=1))) +
  theme(legend.position="bottom",legend.direction="horizontal",
        legend.key.width=unit(3,"mm"),legend.title=element_text(size=7,face="bold",margin=margin(r=1,unit="mm")),
        legend.text=element_text(size=6),legend.margin=margin(0,0,0,0,"mm"))
symbols <- pack_legend_rows(legend_objects(symbol_source),177,gap_mm=6)
stopifnot(attr(symbols,"row_count")==1)
symbol_h <- grid::convertHeight(sum(symbols$heights),"mm",TRUE)

# Compact maps-first layout: a, b, then the two-row shared legend footer.
row_h <- c(margin_mm,3.5,map_h,2,3.5,map_h,2,bar_h,1.5,symbol_h,margin_mm)
H_MM <- ceiling(sum(row_h))
row_h[length(row_h)] <- row_h[length(row_h)]+H_MM-sum(row_h)
fig <- gtable::gtable(widths=unit(c(margin_mm,col_mm,gap_mm,col_mm,gap_mm,col_mm,margin_mm),"mm"),
                     heights=unit(row_h,"mm"))
for(i in 1:3) {
  fig <- gtable::gtable_add_grob(fig,maps[[i]],t=3,l=2*i,clip="off")
  fig <- gtable::gtable_add_grob(fig,maps[[i+3]],t=6,l=2*i,clip="off")
}
footer <- gtable::gtable(widths=unit(rep((W_MM-2*margin_mm)/4,4),"mm"),heights=unit(bar_h,"mm"))
for(i in 1:4) {
  b <- bars[[i]]
  stopifnot(grid::convertWidth(sum(b$widths),"mm",TRUE)<(W_MM-2*margin_mm)/4)
  b$vp <- grid::viewport(width=sum(b$widths),height=sum(b$heights))
  footer <- gtable::gtable_add_grob(footer,b,t=1,l=i,clip="off")
}
fig <- gtable::gtable_add_grob(fig,footer,t=8,l=2,r=6,clip="off")
symbols$vp <- grid::viewport(width=unit(177,"mm"),height=sum(symbols$heights))
fig <- gtable::gtable_add_grob(fig,symbols,t=10,l=2,r=6,clip="off")
for(item in list(list(row=2,label="(a)"),list(row=5,label="(b)"))) {
  fig <- gtable::gtable_add_grob(fig,grid::textGrob(item$label,x=0,y=.5,just=c("left","centre"),
    gp=grid::gpar(fontsize=8,fontface="bold",fontfamily="sans")),t=item$row,l=2,r=6,clip="off")
}
left_in_col <- grid::convertWidth(sum(common_w[seq_len(panel_col-1)]),"mm",TRUE)
lefts <- margin_mm+(0:2)*(col_mm+gap_mm)+left_in_col
utils::write.csv(data.frame(Panel=rep(c("a","b"),each=3),Column=rep(1:3,2),
  Left_mm=rep(lefts,2),Right_mm=rep(lefts+panel_mm,2),Map_Width_mm=panel_mm,
  Map_Height_mm=panel_mm/3,Base_Rows=vapply(map_plots,function(p)nrow(p$data),integer(1))),
  file.path(output_dir,"Fig2_Layout_Alignment.csv"),row.names=FALSE)
utils::write.csv(data.frame(Width_mm=W_MM,Height_mm=H_MM,Map_Row_Height_mm=map_h,
  Footer_Height_mm=bar_h+1.5+symbol_h,Font_Label_pt=6,Font_Title_pt=7),
  file.path(output_dir,"Fig2_Layout_Size.csv"),row.names=FALSE)

list(plot=fig,width_mm=W_MM,height_mm=H_MM)
}
