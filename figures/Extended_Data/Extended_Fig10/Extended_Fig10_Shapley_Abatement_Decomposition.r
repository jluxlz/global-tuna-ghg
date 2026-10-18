# =============================================================================
# Extended Data Fig. 10 | Shapley decomposition of modelled 2050 abatement
# Data: scenario/output/fig5/SF6_Shapley_Contributions.csv, SF6_Combos_2050.csv
#       (builders in this folder)
# Output: Extended_Fig10_Shapley_Abatement_Decomposition.{pdf,png}
# =============================================================================
suppressMessages({
library(ggplot2); library(dplyr); library(tidyr); library(patchwork); library(scales)
})
args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
HERE <- normalizePath(dirname(sub("^--file=", "", file_arg)))
OUT <- file.path(HERE, "..", "..", "..", "scenario", "output", "fig5")

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

save_png_pdf <- function(p, name, w = 183, h = 120) {
  ggsave(file.path(HERE, paste0(name, ".pdf")), p, width = w, height = h, units = "mm", device = cairo_pdf, bg = "white")
  ggsave(file.path(HERE, paste0(name, ".png")), p, width = w, height = h, units = "mm", dpi = 300, bg = "white")
  ggsave(file.path(HERE, paste0(name, ".tiff")), p, width = w, height = h,
         units = "mm", dpi = 900, compression = "lzw", bg = "white")
  cat("saved", name, "\n")
}

# ---- SF6 panels ----
sh <- read.csv(file.path(OUT, "SF6_Shapley_Contributions.csv"))
sh$Measure <- factor(sh$Measure, levels = c("LN2 refrigerant", "Consolidation", "Fuel transition", "Quota reform"))
comb <- read.csv(file.path(OUT, "SF6_Combos_2050.csv"))
comb$Combo <- sprintf("%04d", as.integer(comb$Combo))
stopifnot(all(nchar(comb$Combo) == 4))
comb$Quota <- substr(comb$Combo, 1, 1) == "1"
comb$Fuel  <- substr(comb$Combo, 2, 2) == "1"

measure_cols <- c("Quota reform" = "#B81D0A", "Fuel transition" = "#1A7A8A", "Consolidation" = "#009E73", "LN2 refrigerant" = "#0072B2")
p6a <- ggplot(sh, aes(Measure, Shapley_Mt, fill = Measure)) +
  geom_boxplot(linewidth = 0.25, outlier.size = 0.3, width = 0.55, alpha = 0.8) +
  scale_fill_manual(values = measure_cols, guide = "none") +
  coord_flip() +
  labs(tag = "(a)", x = NULL, y = expression("Shapley contribution (Mt CO"[2]*"e, 2050)")) +
  theme_pub
p6b <- ggplot(sh, aes(Measure, Share_pct, fill = Measure)) +
  geom_boxplot(linewidth = 0.25, outlier.size = 0.3, width = 0.55, alpha = 0.8) +
  scale_fill_manual(values = measure_cols, guide = "none") +
  geom_hline(yintercept = 50, linetype = "dashed", colour = "grey40", linewidth = 0.3) +
  coord_flip() +
  labs(tag = "(b)", x = NULL, y = "Share of total modeled abatement (%)") +
  theme_pub
comb_pure <- comb %>% filter(substr(Combo, 3, 4) == "00")
stopifnot(nrow(comb_pure) == 81 * 4)
p6c <- ggplot(comb_pure, aes(Quota, GHG_2050_Mt, fill = Fuel)) +
  geom_boxplot(linewidth = 0.25, outlier.size = 0.2, width = 0.55) +
  scale_fill_manual(values = c("FALSE" = "#A6CEE3", "TRUE" = "#1A7A8A"),
                    labels = c("No fuel switch", "Fuel transition"), name = NULL) +
  scale_x_discrete(labels = c("Fixed 2024 catch", "Harvest rate")) +
  labs(tag = "(c)", x = "Quota regime", y = expression("2050 emissions (Mt CO"[2]*"e)")) +
  theme_pub
save_png_pdf((p6a | p6b) / p6c + plot_layout(heights = c(1, 0.95)), "Extended_Fig10_Shapley_Abatement_Decomposition", h = 145)

# Full plotted source data; no subset is silently discarded.
if (exists("sh")) write.csv(sh, file.path(HERE, "Extended_Fig10_PanelA_Render_Data.csv"), row.names = FALSE)
if (exists("sh")) write.csv(sh, file.path(HERE, "Extended_Fig10_PanelB_Render_Data.csv"), row.names = FALSE)
write.csv(comb_pure, file.path(HERE, "Extended_Fig10_PanelC_Render_Data.csv"), row.names = FALSE)
