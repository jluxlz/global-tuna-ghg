# Restored archives have new filesystem timestamps. Verify source content
# rather than treating extraction order as evidence of stale calculations.
verify_fig3_source <- function(record) {
  if (!requireNamespace("jsonlite",quietly=TRUE) || !requireNamespace("digest",quietly=TRUE))
    stop("Install jsonlite and digest to verify Fig. 3 input provenance.")
  if (!file.exists(record)) stop("Missing Fig. 3 provenance: ",record)
  expected <- jsonlite::fromJSON(record)$source_sha256
  source_file <- file.path(DATA_DIR,"Base_3_Spatial_Grid_Enriched.csv")
  if (!exists(".fig3_source_sha256",envir=.GlobalEnv,inherits=FALSE)) {
    actual_hash <- tryCatch(
      digest::digest(file=source_file,algo="sha256",serialize=FALSE),
      error=function(e) {
        # Some Windows ACL environments report file.access=-1 even though
        # ordinary read connections succeed. Reading bytes still verifies
        # content; a real permission or I/O failure propagates here.
        con <- file(source_file,"rb");on.exit(close(con))
        digest::digest(readBin(con,what="raw",n=file.info(source_file)$size),
                       algo="sha256",serialize=FALSE)
      })
    assign(".fig3_source_sha256",actual_hash,envir=.GlobalEnv)
  }
  actual <- get(".fig3_source_sha256",envir=.GlobalEnv)
  if (!is.character(expected) || length(expected)!=1 || !identical(actual,expected))
    stop("Fig. 3 source checksum differs from preserved calculations. Rerun preprocess_fig3.py.")
  invisible(TRUE)
}
