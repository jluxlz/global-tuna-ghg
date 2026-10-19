# =============================================================================
# Supplementary Fig. 17 | Decomposition of the projected baseline emission
# increase, 2025-2050 (SF7)
# Data: local SF7_*.csv snapshots of the plotted production inputs.
# Output: Supplementary_Fig17_Emission_Growth_Decomposition.{pdf,png}
# =============================================================================
suppressMessages({
library(ggplot2); library(dplyr); library(tidyr); library(patchwork); library(scales)
})
args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
HERE <- normalizePath(dirname(sub("^--file=", "", file_arg)))
OUT <- HERE

theme_pub <- theme_classic(base_size = 7, base_family = "Arial") + theme(
  plot.tag = element_text(face = "bold", size = 8),
  plot.tag.position = c(0, 1), plot.title = element_text(size = 7, face = "bold"),
  axis.title = element_text(size = 7, face = "bold"),
  axis.text = element_text(size = 6, colour = "black"),
  axis.line = element_line(linewidth = 0.18, colour = "black"),
  axis.ticks = element_line(linewidth = 0.18), axis.ticks.length = unit(1.3, "mm"),
  strip.background = element_blank(), strip.text = element_text(size = 7, face = "bold"),
  legend.title = element_text(size = 7, face = "bold"), legend.text = element_text(size = 6),
  legend.position = "bottom", legend.box = "vertical", legend.key.size = unit(3, "mm"),
  legend.spacing = unit(2, "pt"), legend.margin = margin(2, 0, 0, 0),
  panel.grid.major = element_blank(), panel.grid.minor = element_blank(),
  panel.spacing = unit(3, "mm"), plot.margin = margin(4, 5, 3, 4, "pt"))
WEO_COLS <- c(STEPS = "#D55E00", APS = "#0072B2", NZE = "#009E73")

save_png_pdf <- function(p, name, w = 183, h = 120) {
  ggsave(file.path(HERE, paste0(name, ".pdf")), p, width = w, height = h, units = "mm", device = cairo_pdf, bg = "white")
  ggsave(file.path(HERE, paste0(name, ".png")), p, width = w, height = h, units = "mm", dpi = 300, bg = "white")
  ggsave(file.path(HERE, paste0(name, ".tiff")), p, width = w, height = h,
         units = "mm", dpi = 900, compression = "lzw", bg = "white")
  cat("saved", name, "\n")
}

# ---- SF7 panels ----
dec <- read.csv(file.path(OUT, "SF7_Increase_Decomposition.csv"))
weo <- read.csv(file.path(OUT, "SF7_WEO_dE.csv"))
weo$WEO <- factor(weo$WEO,levels=c('STEPS','APS','NZE'))
mec <- read.csv(file.path(OUT, "SF7_Meco_Trajectory.csv"))
fue <- read.csv(file.path(OUT, "SF7_Fuel_Intensity.csv"))

dec$Factor <- factor(dec$Factor, levels = dec$Factor)
p7a <- ggplot(dec, aes(Factor, contribution_Mt, fill = contribution_Mt > 0)) +
  geom_col(width = 0.6) + coord_flip() +
  scale_fill_manual(values = c("TRUE" = "#B81D0A", "FALSE" = "#4D4D4D"), guide = "none") +
  labs(tag = "(a)", x = NULL, y = expression("Contribution to 2025-2050 increase (Mt CO"[2]*"e)")) +
  theme_pub
p7b <- ggplot(weo, aes(WEO, dE_mean, fill = WEO)) +
  geom_col(width = 0.6) +
  geom_errorbar(aes(ymin = dE_p5, ymax = dE_p95), width = 0.25, linewidth = 0.3) +
  scale_fill_manual(values = WEO_COLS, guide = "none") +
  labs(tag = "(b)", x = NULL, y = expression("2050 minus 2025 emissions (Mt CO"[2]*"e)")) +
  theme_pub
p7c <- ggplot(mec, aes(Year, E_req, colour = Gear, linetype = Design)) +
  geom_line(linewidth = 0.5) +
  scale_colour_manual(values = c(LL = "#B81D0A", PS = "#1A7A8A"), name = NULL) +
  scale_linetype_manual(values = c(C = "solid", F = "dashed"),
                        labels = c(C = "C-type quota rule", F = "F-type harvest-rate rule"), name = NULL) +
  labs(tag = "(c)", x = NULL, y = expression("Required effort multiplier " * M[eco])) +
  theme_pub
p7d <- ggplot(fue, aes(Year, E_adj_min, colour = WEO)) +
  geom_line(linewidth = 0.5) +
  scale_colour_manual(values = WEO_COLS, name = NULL) +
  labs(tag = "(d)", x = NULL, y = expression("Fuel-path intensity (g CO"[2]*"e kWh"^-1*")")) +
  theme_pub
save_png_pdf((p7a | p7b) / (p7c | p7d), "Supplementary_Fig17_Emission_Growth_Decomposition", h = 150)

# Full plotted source data; no subset is silently discarded.
if (exists("dec")) write.csv(dec, file.path(HERE, "Supplementary_Fig17_PanelA_Render_Data.csv"), row.names = FALSE)
if (exists("weo")) write.csv(weo, file.path(HERE, "Supplementary_Fig17_PanelB_Render_Data.csv"), row.names = FALSE)
if (exists("mec")) write.csv(mec, file.path(HERE, "Supplementary_Fig17_PanelC_Render_Data.csv"), row.names = FALSE)
if (exists("fue")) write.csv(fue, file.path(HERE, "Supplementary_Fig17_PanelD_Render_Data.csv"), row.names = FALSE)
