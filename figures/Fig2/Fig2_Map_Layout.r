# A single physical column grid for both map matrices. Map dimensions must not
# depend on the width or height of their legends. Geographic aspect stays 1:3.
aligned_map_matrices <- function(era_plot, metric_plots, width_mm=183, height_mm=132) {
  margin_mm <- 1.5
  gap_mm <- 1.5
  col_mm <- (width_mm - 2*margin_mm - 2*gap_mm)/3
  eras <- levels(era_plot$data$Era)
  era_plots <- lapply(eras, function(era) {
    p <- unserialize(serialize(era_plot,NULL))
    p$data <- droplevels(era_plot$data[era_plot$data$Era == era,])
    # The species overlay has its own data and must be subset with its base map.
    for (i in seq_along(p$layers)) {
      d <- p$layers[[i]]$data
      if (is.data.frame(d) && "Era" %in% names(d)) {
        p$layers[[i]]$data <- droplevels(d[d$Era == era,])
      }
    }
    p + facet_grid(Gear ~ Era, switch="y")
  })
  metric_plots <- lapply(metric_plots, function(p) {
    p + facet_grid(Gear ~ Metric, switch="y")
  })
  plots <- c(era_plots,metric_plots)
  grobs <- lapply(plots,function(p) ggplot2::ggplotGrob(
    p + labs(tag=NULL,x=NULL,y=NULL) + theme(legend.position="none",
      panel.spacing=grid::unit(2,"mm"),plot.margin=margin(0,0,0,0,"mm"))))
  stopifnot(length(unique(vapply(grobs,function(g)length(g$widths),integer(1)))) == 1)
  common_widths <- do.call(grid::unit.pmax,lapply(grobs,`[[`,"widths"))
  common_heights <- do.call(grid::unit.pmax,lapply(grobs,`[[`,"heights"))
  panel <- grepl("^panel-",grobs[[1]]$layout$name)
  panel_cols <- unique(grobs[[1]]$layout$l[panel])
  panel_rows <- sort(unique(grobs[[1]]$layout$t[panel]))
  stopifnot(length(panel_cols)==1,length(panel_rows)==2)
  fixed_width_mm <- grid::convertWidth(sum(common_widths[-panel_cols]),"mm",TRUE)
  panel_width_mm <- col_mm - fixed_width_mm
  stopifnot(panel_width_mm > 40)
  common_widths[panel_cols] <- grid::unit(panel_width_mm,"mm")
  common_heights[panel_rows] <- grid::unit(panel_width_mm/3,"mm")
  left_in_col <- grid::convertWidth(sum(common_widths[seq_len(panel_cols-1)]),"mm",TRUE)
  grobs <- lapply(grobs,function(g) {
    g$widths <- common_widths;g$heights <- common_heights;g$respect <- FALSE;g
  })
  map_height_mm <- grid::convertHeight(sum(common_heights),"mm",TRUE)
  a_guides <- pack_legend_rows(legend_objects(prepare_horizontal_guides(era_plot,174)),174)
  b_guides <- lapply(metric_plots,function(p) {
    gs <- legend_objects(p + theme(legend.position="bottom"))
    stopifnot(length(gs)==1)
    gs[[1]]
  })
  a_height_mm <- grid::convertHeight(sum(a_guides$heights),"mm",TRUE)
  b_height_mm <- max(vapply(b_guides,function(g)grid::convertHeight(sum(g$heights),"mm",TRUE),numeric(1)))
  # Spare space goes between whole sections, never into their map viewports.
  tag_mm <- 3.5
  used <- 2*margin_mm + 2*tag_mm + 2*map_height_mm + a_height_mm + b_height_mm
  spare <- height_mm-used
  stopifnot(spare >= 0)
  heights <- c(margin_mm,tag_mm,map_height_mm,1,a_height_mm,
               max(0,spare-2),tag_mm,map_height_mm,1,b_height_mm,margin_mm)
  full <- gtable::gtable(widths=grid::unit(c(margin_mm,col_mm,gap_mm,col_mm,gap_mm,col_mm,margin_mm),"mm"),
                        heights=grid::unit(heights,"mm"))
  for (i in 1:3) {
    full <- gtable::gtable_add_grob(full,grobs[[i]],t=3,l=2*i,clip="off")
    full <- gtable::gtable_add_grob(full,grobs[[i+3]],t=8,l=2*i,clip="off")
    legend <- b_guides[[i]]
    legend$vp <- grid::viewport(x=(left_in_col+panel_width_mm/2)/col_mm,
                               width=sum(legend$widths),height=sum(legend$heights))
    full <- gtable::gtable_add_grob(full,legend,t=10,l=2*i,clip="off")
  }
  a_guides$vp <- grid::viewport(width=grid::unit(174,"mm"),height=sum(a_guides$heights))
  full <- gtable::gtable_add_grob(full,a_guides,t=5,l=2,r=6,clip="off")
  for (item in list(list(row=2,label="(a)"),list(row=7,label="(b)"))) {
    tag <- grid::textGrob(item$label,x=0,y=.5,just=c("left","centre"),
                         gp=grid::gpar(fontsize=8,fontface="bold",fontfamily="sans"))
    full <- gtable::gtable_add_grob(full,tag,t=item$row,l=2,r=6,clip="off")
  }
  # Save physical panel bounds so exact alignment is independently reviewable.
  lefts <- margin_mm + (0:2)*(col_mm+gap_mm) + left_in_col
  audit <- data.frame(Panel=rep(c("a","b"),each=3),Column=rep(1:3,2),
    Left_mm=rep(lefts,2),Right_mm=rep(lefts+panel_width_mm,2),
    Map_Width_mm=panel_width_mm,Map_Height_mm=panel_width_mm/3,
    Base_Rows=c(vapply(era_plots,function(p)nrow(p$data),integer(1)),
                vapply(metric_plots,function(p)nrow(p$data),integer(1))))
  write.csv(audit,"Fig2_Layout_Alignment.csv",row.names=FALSE)
  stopifnot(identical(audit$Left_mm[1:3],audit$Left_mm[4:6]),
            identical(audit$Right_mm[1:3],audit$Right_mm[4:6]),
            sum(audit$Base_Rows[1:3])==nrow(era_plot$data))
  full
}
