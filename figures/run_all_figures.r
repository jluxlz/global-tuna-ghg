# ==============================================================================
# Master runner: Render all publication figures
# ==============================================================================
# Usage:  Rscript figures/run_all_figures.r
#
# Each script writes its PNG/PDF into its own figure folder (figures/FigN/).
# Fig4 requires figures/Fig4/preprocess_fig4.py run first; Fig5 requires
# figures/Fig5/fig5_run.py run first AND the R conda env (see CLAUDE.md).
# ==============================================================================

# Detect script directory (works with Rscript, source(), RStudio)
args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
if (length(file_arg) > 0) {
  SCRIPT_DIR <- normalizePath(dirname(sub("^--file=", "", file_arg)))
} else if (sys.nframe() > 0) {
  SCRIPT_DIR <- normalizePath(dirname(sys.frame(1)$ofile))
} else {
  SCRIPT_DIR <- normalizePath(getwd())
}
setwd(SCRIPT_DIR)

cat("============================================\n")
cat("Rendering all publication figures\n")
cat("============================================\n\n")

scripts <- c(
  "Fig1/Fig1_Multi_Dimensional.r",
  "Fig2/Fig2_Spatial_Temporal_CEI.r",
  "Fig3/Fig3_Phase_Decoupling.r",
  "Fig4/Fig4_Coupled_Mechanisms.r",
  "Fig5/plot_fig5.r"
)

for (s in scripts) {
  cat(sprintf("\n--- %s ---\n", s))
  t0 <- Sys.time()
  setwd(SCRIPT_DIR)
  source(file.path(SCRIPT_DIR, s), local = TRUE)
  t1 <- Sys.time()
  cat(sprintf("  Elapsed: %.1f s\n", difftime(t1, t0, units = "secs")))
}

cat("\n============================================\n")
cat("All figures complete.\n")
cat("============================================\n")
