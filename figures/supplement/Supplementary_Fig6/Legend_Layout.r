# Publication legend layout. This local copy keeps this figure self-contained.
# Measure guides at the actual export width; keep rows horizontal until full.
legend_guides <- function(p) {
  out <- list()
  for (s in p$scales$scales) {
    for (a in s$aesthetics) out[[a]] <- s$guide
  }
  for (a in names(p$guides$guides)) out[[a]] <- p$guides$guides[[a]]
  out
}
legend_objects <- function(p) {
  g <- ggplot2::ggplotGrob(p)
  idx <- which(g$layout$name == "guide-box-bottom")
  if (!length(idx)) return(list())
  box <- g$grobs[[idx[1]]]
  if (!inherits(box, "gtable")) return(list())
  box$grobs[box$layout$name == "guides"]
}
guide_with_rows <- function(g, n) {
  params <- if (inherits(g, "GuideLegend")) g$params else list()
  params <- params[intersect(names(params), names(formals(ggplot2::guide_legend)))]
  params$nrow <- n; params$ncol <- NULL; params$direction <- "horizontal"
  do.call(ggplot2::guide_legend, params)
}
prepare_horizontal_guides <- function(p, width_mm) {
  p <- p + ggplot2::theme(legend.position="bottom", legend.direction="horizontal",
    legend.box="horizontal", legend.justification="centre",
    legend.spacing.x=grid::unit(2,"mm"),
    legend.spacing.y=grid::unit(1,"mm"),
    legend.title=ggplot2::element_text(margin=ggplot2::margin(r=2,unit="mm")), axis.title.x=ggplot2::element_text(hjust=.5))
  all <- legend_guides(p)
  for (a in names(all)) {
    guide <- all[[a]]
    discrete <- inherits(guide,"GuideLegend") || (is.character(guide) && identical(guide,"legend"))
    if (inherits(guide,c("GuideColourbar","GuideColoursteps","GuideColorbar","GuideColorsteps"))) discrete <- FALSE
    if (!discrete) next
    for (n in 1:12) {
      isolated <- as.list(setNames(rep("none",length(all)),names(all)))
      isolated[[a]] <- guide_with_rows(guide,n)
      single <- p + do.call(ggplot2::guides,isolated)
      gs <- legend_objects(single)
      w <- if(length(gs)) max(vapply(gs,function(g)grid::convertWidth(sum(g$widths),"mm",TRUE),numeric(1))) else 0
      if (w <= width_mm || n==12) break
    }
    p <- p + do.call(ggplot2::guides,setNames(list(guide_with_rows(guide,n)),a))
  }
  p
}
pack_legend_rows <- function(guides, width_mm, gap_mm=4, row_gap_mm=.8) {
  if (!length(guides)) return(NULL)
  widths <- vapply(guides,function(g)grid::convertWidth(sum(g$widths),"mm",TRUE),numeric(1))
  heights <- vapply(guides,function(g)grid::convertHeight(sum(g$heights),"mm",TRUE),numeric(1))
  rows <- list(); remaining <- seq_along(guides)
  # First-fit packing also lets a short later guide share an earlier row.
  while(length(remaining)) {
    chosen <- integer(); used <- 0
    for (j in remaining) {
      need <- widths[j] + if(length(chosen)) gap_mm else 0
      if (!length(chosen) || used+need <= width_mm) {
        chosen <- c(chosen,j); used <- used+need
      }
    }
    rows[[length(rows)+1]] <- chosen; remaining <- setdiff(remaining,chosen)
  }
  hs <- vapply(rows,function(ids)max(heights[ids]),numeric(1))
  outer <- gtable::gtable(widths=grid::unit(width_mm,"mm"),
    heights=grid::unit(as.vector(rbind(hs,rep(row_gap_mm,length(hs))))[-(2*length(hs))],"mm"))
  for(i in seq_along(rows)) {
    ids <- rows[[i]]
    ws <- grid::unit(.5,"null")
    for(k in seq_along(ids)) {
      ws <- grid::unit.c(ws,grid::unit(widths[ids[k]],"mm"))
      if(k<length(ids)) ws <- grid::unit.c(ws,grid::unit(gap_mm,"mm"))
    }
    ws <- grid::unit.c(ws,grid::unit(.5,"null"))
    row <- gtable::gtable(widths=ws,heights=grid::unit(hs[i],"mm"))
    for(k in seq_along(ids)) row <- gtable::gtable_add_grob(row,guides[[ids[k]]],t=1,l=2*k,clip="off")
    outer <- gtable::gtable_add_grob(outer,row,t=2*i-1,l=1,clip="off")
  }
  attr(outer,"row_count") <- length(rows)
  attr(outer,"guide_widths_mm") <- widths
  outer
}
legend_layout_record <- function(label, packed, width_mm) {
  if(is.null(packed)) return(invisible(NULL))
  path <- Sys.getenv("LEGEND_LAYOUT_AUDIT")
  if(nzchar(path)) utils::write.table(data.frame(Panel=label,Available_mm=width_mm,
    Rows=attr(packed,"row_count"),Guide_Widths_mm=paste(round(attr(packed,"guide_widths_mm"),2),collapse=";")),
    path,sep="\t",row.names=FALSE,col.names=!file.exists(path),append=file.exists(path),quote=TRUE)
}
horizontal_legend_plot <- function(p, width_mm, label="") {
  p <- prepare_horizontal_guides(p,width_mm)
  g <- ggplot2::ggplotGrob(p)
  packed <- pack_legend_rows(legend_objects(p),width_mm)
  if(!is.null(packed)) {
    i <- which(g$layout$name=="guide-box-bottom")[1]
    packed$vp <- grid::viewport(x=.5,y=.5,width=grid::unit(width_mm,"mm"),height=sum(packed$heights))
    g$grobs[[i]] <- packed; g$heights[g$layout$t[i]] <- sum(packed$heights)
    g$layout$l[i] <- 1; g$layout$r[i] <- length(g$widths)
    legend_layout_record(label,packed,width_mm)
  }
  patchwork::wrap_elements(full=g)
}
shared_horizontal_legend <- function(body, guide_plot, width_mm, label="") {
  guide_plot <- prepare_horizontal_guides(guide_plot,width_mm)
  packed <- pack_legend_rows(legend_objects(guide_plot),width_mm)
  if(is.null(packed)) return(body)
  legend_layout_record(label,packed,width_mm)
  # The strip spans the complete assembled row, including independently scaled facets.
  patchwork::wrap_elements(full=patchwork::patchworkGrob(body)) /
    patchwork::wrap_elements(full=packed) +
    patchwork::plot_layout(heights=grid::unit.c(grid::unit(1,"null"),sum(packed$heights)))
}
