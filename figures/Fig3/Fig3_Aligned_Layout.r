# Align the plot boundaries of (a)-(c), and all five RFMO panels in (b)/(c).
# Each regional panel receives exactly the same gtable column widths. The
# independent CCSBT PS axes occupy a reserved gutter, not extra panel width.
# Data, common LL/PS limits, all centroids and the CCSBT exception are unchanged.
view_limits <- function(key) {
  v <- view_records[[key]]
  list(c(v$Xmin,v$Xmax),c(v$Ymin,v$Ymax))
}
org_order <- names(org_cb_cols)
region_plots <- list()
for(gear in c("LL","PS")) for(org in org_order) {
  key <- if(gear=="LL") "LL" else if(org=="CCSBT") "PS_CCSBT" else "PS"
  p <- mk_era_row(bg[bg$Gear==gear & bg$Organization==org,],
    fg[fg$Gear==gear & fg$Organization==org,],NULL,NULL,ncol=1,
    key=key,bounds=view_limits(key))+
    theme(plot.margin=margin(1,6,1,1,"pt"),
      axis.title=element_blank(),legend.position="none")
  if(org!="WCPFC" && !(gear=="PS" && org=="CCSBT"))
    p <- p+theme(axis.text.y=element_blank(),axis.ticks.y=element_blank(),
      axis.line.y=element_blank())
  region_plots[[paste(gear,org,sep="_")]] <- p
}
regional_grobs <- lapply(region_plots,ggplotGrob)
stopifnot(length(unique(vapply(regional_grobs,function(g)length(g$widths),integer(1))))==1)
regional_widths <- do.call(grid::unit.pmax,lapply(regional_grobs,`[[`,"widths"))
regional_heights <- do.call(grid::unit.pmax,lapply(regional_grobs,`[[`,"heights"))
for(k in names(regional_grobs)) {
  regional_grobs[[k]]$widths <- regional_widths
  regional_grobs[[k]]$heights <- regional_heights
}
panel_span <- function(g) {
  ids <- grep("^panel",g$layout$name)
  c(min(g$layout$l[ids]),max(g$layout$r[ids]))
}
mm <- function(u) grid::convertWidth(u,"mm",valueOnly=TRUE)
gt_a <- horizontal_legend_gtable(p_a,174,"Fig3a_aligned")
span_a <- panel_span(gt_a)
left_a <- mm(sum(gt_a$widths[seq_len(span_a[1]-1)]))
right_a <- mm(sum(gt_a$widths[(span_a[2]+1):length(gt_a$widths)]))
span_r <- panel_span(regional_grobs[[1]])
left_r <- mm(sum(regional_widths[seq_len(span_r[1]-1)]))
right_r <- mm(sum(regional_widths[(span_r[2]+1):length(regional_widths)]))
ytitle_mm <- 4.5
left_common <- max(left_a,ytitle_mm+left_r)
right_common <- max(right_a,right_r)
pad_gtable <- function(g,left,right) {
  if(left>0) g <- gtable::gtable_add_cols(g,unit(left,"mm"),pos=0)
  if(right>0) g <- gtable::gtable_add_cols(g,unit(right,"mm"),pos=-1)
  g
}
gt_a <- pad_gtable(gt_a,left_common-left_a,right_common-right_a)
make_aligned_row <- function(gear,tag,xt,yt) {
  gs <- regional_grobs[paste(gear,org_order,sep="_")]
  # Five equal cells, each containing identical panel/axis/margin widths.
  g <- gtable::gtable(widths=unit(rep(1,5),"null"),
    heights=grid::unit.c(unit(3,"mm"),unit(1,"null"),unit(4,"mm")))
  for(i in seq_along(gs)) g <- gtable::gtable_add_grob(g,gs[[i]],t=2,l=i,clip="off")
  # Centre the common x title between the first and last plotting boundaries.
  title_row <- gtable::gtable(widths=grid::unit.c(unit(left_r,"mm"),unit(1,"null"),unit(right_r,"mm")),heights=unit(4,"mm"))
  title_row <- gtable::gtable_add_grob(title_row,grid::textGrob(xt,gp=grid::gpar(fontfamily="sans",fontsize=7,fontface="bold")),t=1,l=2)
  g <- gtable::gtable_add_grob(g,title_row,t=3,l=1,r=5)
  g <- gtable::gtable_add_cols(g,unit(ytitle_mm,"mm"),pos=0)
  g <- gtable::gtable_add_grob(g,grid::textGrob(yt,rot=90,gp=grid::gpar(fontfamily="sans",fontsize=7,fontface="bold")),t=2,l=1)
  g <- pad_gtable(g,left_common-ytitle_mm-left_r,right_common-right_r)
  g <- gtable::gtable_add_grob(g,grid::textGrob(tag,x=unit(1,"mm"),just="left",gp=grid::gpar(fontfamily="sans",fontsize=8,fontface="bold")),t=1,l=1,r=length(g$widths),clip="off")
  g
}
gt_b <- make_aligned_row("LL","(b)","Standardized hooks per 100 t of catch",
  expression(atop(t~CO[2]*e~per~100,standardized~hooks)))
gt_c <- make_aligned_row("PS","(c)","Standardized sets per metric ton of catch",
  expression(t~CO[2]*e~per~standardized~set))
bc_guides <- pack_legend_rows(legend_objects(prepare_horizontal_guides(p_c_main,174)),174)
legend_layout_record("Fig3bc_aligned",bc_guides,174)
fig3 <- gtable::gtable(widths=unit(1,"null"),
  heights=grid::unit.c(unit(1.8,"null"),unit(.60,"null"),unit(.85,"null"),sum(bc_guides$heights)))
for(i in 1:4) fig3 <- gtable::gtable_add_grob(fig3,list(gt_a,gt_b,gt_c,bc_guides)[[i]],t=i,l=1,clip="off")
aligned_bc <- gtable::gtable(widths=unit(1,"null"),
  heights=grid::unit.c(unit(1,"null"),unit(1,"null"),sum(bc_guides$heights)))
for(i in 1:3) aligned_bc <- gtable::gtable_add_grob(aligned_bc,list(gt_b,gt_c,bc_guides)[[i]],t=i,l=1,clip="off")
ggsave("Fig3_PanelBC_Era_Background.png",aligned_bc,width=183,height=125,units="mm",dpi=300,bg="white",device=grDevices::png,type="cairo")
ggsave("Fig3_PanelBC_Era_Background.pdf",aligned_bc,width=183,height=125,units="mm",device=cairo_pdf,bg="white")
layout_audit <- data.frame(Panel=c("a","b","c"),Left_Plot_Boundary_mm=left_common,
  Right_Plot_Margin_mm=right_common,RFMO_Columns=c(NA,5,5),Equal_RFMO_Column_Widths=c(NA,TRUE,TRUE))
write.csv(layout_audit,"Fig3_Alignment_Layout.csv",row.names=FALSE)
