# Reuse supplied artwork without changing original PNG/PDF assets.
# Rasterisation is only for embedding existing PDF artwork in the figure.
read_icon <- function(path) {
  a <- png::readPNG(path)
  if (length(dim(a)) == 3 && dim(a)[3] == 4) {
    ix <- which(a[,,4] > 0.01, arr.ind = TRUE)
    a <- a[min(ix[,1]):max(ix[,1]), min(ix[,2]):max(ix[,2]),,drop=FALSE]
  } else if (length(dim(a)) == 3) {
    ix <- which(apply(a[,,1:3,drop=FALSE],c(1,2),min) < .98,arr.ind=TRUE)
    if (nrow(ix)) a <- a[min(ix[,1]):max(ix[,1]),min(ix[,2]):max(ix[,2]),,drop=FALSE]
  }
  a
}

rfmo_icon_png <- function(org, script_dir) {
  src <- file.path(script_dir, 'RFMO_Icons', paste0('Icon_',org,'.pdf'))
  cache <- file.path(script_dir, 'Icon_Render_Cache')
  dir.create(cache,showWarnings=FALSE)
  dest <- file.path(cache, paste0('Icon_',org,'.png'))
  if (!file.exists(dest) || file.mtime(src) > file.mtime(dest)) {
    exe <- file.path(Sys.getenv('USERPROFILE'),'.cache','codex-runtimes',
      'codex-primary-runtime','dependencies','native','poppler','Library','bin','pdftoppm.exe')
    if (!file.exists(exe)) exe <- Sys.which('pdftoppm')
    if (!file.exists(exe)) stop('pdftoppm is required to render supplied RFMO PDF icons')
    status <- system2(exe,c('-png','-singlefile','-r','300',shQuote(src),
      shQuote(sub('\\.png$','',dest))))
    if (status != 0 || !file.exists(dest)) stop('RFMO icon render failed: ',org)
  }
  dest
}

add_rfmo_icon_column <- function(plot, script_dir) {
  b <- ggplot_build(plot)
  yr <- b$layout$panel_params[[1]]$y.range
  gt <- ggplotGrob(plot)
  panel <- gt$layout[gt$layout$name=='panel',]
  ax <- gt$layout[gt$layout$name=='axis-l',]
  gt <- gtable::gtable_add_cols(gt,grid::unit(11,'mm'),pos=ax$l-1)
  lev <- levels(plot$data$Organization)
  icons <- lapply(seq_along(lev),function(i) {
    a <- read_icon(rfmo_icon_png(lev[i],script_dir))
    ratio <- dim(a)[2]/dim(a)[1]
    w <- min(9,6.5*ratio); h <- w/ratio
    grid::rasterGrob(a,x=.5,y=(i-yr[1])/diff(yr),
      width=grid::unit(w,'mm'),height=grid::unit(h,'mm'),interpolate=TRUE)
  })
  gt <- gtable::gtable_add_grob(gt,do.call(grid::grobTree,icons),
    t=panel$t,b=panel$b,l=ax$l,clip='off',name='supplied-rfmo-icons')
  patchwork::wrap_elements(full=gt)
}
