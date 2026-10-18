# This host reports file.access(..., mode > 0) = -1 even for readable R
# package directories. packageVersion then fails although find.package and
# read.dcf both work. Fall back only to a successfully read DESCRIPTION with
# the requested package name. No DLL, dependency or model checks are skipped.
local({
  original <- utils::packageVersion
  compatible <- function(pkg, lib.loc = NULL) {
    tryCatch(original(pkg, lib.loc), packageNotFoundError = function(e) {
      paths <- file.path(if (is.null(lib.loc)) .libPaths() else lib.loc, pkg, "DESCRIPTION")
      for (p in paths[file.exists(paths)]) {
        desc <- tryCatch(read.dcf(p), error = function(e) NULL)
        if (!is.null(desc) && desc[1, "Package"] == pkg)
          return(package_version(desc[1, "Version"]))
      }
      stop(e)
    })
  }
  ns <- asNamespace("utils")
  unlockBinding("packageVersion", ns)
  assign("packageVersion", compatible, envir = ns)
  lockBinding("packageVersion", ns)
})

# Native Cairo cannot overwrite some existing files on this host, despite
# ordinary R/Python file writes being permitted. Render to new sibling files;
# the Python runner validates and atomically promotes them afterwards.
ggsave <- function(filename, ...) {
  target <- normalizePath(filename, winslash = "/", mustWork = FALSE)
  ext <- tools::file_ext(target)
  temporary <- tempfile(".render_", tmpdir = dirname(target), fileext = paste0(".", ext))
  result <- ggplot2::ggsave(filename = temporary, ...)
  manifest <- Sys.getenv("FIGURE_ARTIFACT_MANIFEST")
  if (nzchar(manifest)) {
    utils::write.table(data.frame(Temporary=temporary,Target=target), manifest,
                       sep="\t",row.names=FALSE,col.names=!file.exists(manifest),
                       append=file.exists(manifest),quote=TRUE)
  } else if (!file.copy(temporary, target, overwrite = TRUE)) {
    stop("Could not promote graphic: ", target)
  }
  invisible(result)
}
