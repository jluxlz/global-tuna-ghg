# =============================================================================
# Extended Data Fig. 6 | Economic effort elasticity sensitivity (SF5)
# Data: scenario/output/fig5/SF5_Panel{A,B,C}_*.csv (builders in this folder)
# Output: Extended_Fig6_Economic_Elasticity_Sensitivity.{pdf,png}
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
WEO_COLS <- c(STEPS = "#D55E00", APS = "#0072B2", NZE = "#009E73")

save_png_pdf <- function(p, name, w = 183, h = 120) {
  ggsave(file.path(HERE, paste0(name, ".pdf")), p, width = w, height = h, units = "mm", device = cairo_pdf, bg = "white")
  ggsave(file.path(HERE, paste0(name, ".png")), p, width = w, height = h, units = "mm", dpi = 300, bg = "white")
  ggsave(file.path(HERE, paste0(name, ".tiff")), p, width = w, height = h,
         units = "mm", dpi = 900, compression = "lzw", bg = "white")
  cat("saved", name, "\n")
}

# ---- SF5 panels ----
pa <- read.csv(file.path(OUT, "SF5_PanelA_Multiplier.csv"))
pb <- read.csv(file.path(OUT, "SF5_PanelB_Abatement.csv"))
pc <- read.csv(file.path(OUT, "SF5_PanelC_Rebound.csv"))

p5a <- ggplot(pa, aes(Beta, M_econ_2050, colour = WEO)) +
  geom_line(linewidth = 0.5) + geom_point(size = 0.8) +
  facet_wrap(~Arm, labeller = as_labeller(c(BAU = "Baseline fuel (MGO)", fuel = "WEO-bound fuel"))) +
  scale_colour_manual(values = WEO_COLS, name = NULL) +
  labs(tag = "(a)", x = expression("Effort elasticity " * beta), y = expression(M[econ] * " (2050)")) +
  theme_pub

pb2 <- pb %>% select(Beta, Fuel_red, Quota_red) %>%
  pivot_longer(c(Fuel_red, Quota_red), names_to = "Arm", values_to = "Reduction") %>%
  mutate(Arm = recode(Arm, Fuel_red = "Fuel transition", Quota_red = "Quota reform"))
p5b <- ggplot(pb2, aes(factor(Beta), Reduction, fill = Arm)) +
  geom_boxplot(outlier.size = 0.2, linewidth = 0.25, width = 0.62) +
  scale_fill_manual(values = c("Fuel transition" = "#1A7A8A", "Quota reform" = "#B81D0A"), name = NULL) +
  labs(tag = "(b)", x = expression("Effort elasticity " * beta), y = "2050 reduction vs own baseline (%)") +
  theme_pub

p5c <- ggplot(pc, aes(factor(Beta), Rebound)) +
  geom_boxplot(fill = "grey75", outlier.size = 0.2, linewidth = 0.25, width = 0.55) +
  geom_hline(yintercept = 0, linetype = "dashed", colour = "grey40", linewidth = 0.3) +
  labs(tag = "(c)", x = expression("Effort elasticity " * beta),
       y = "Fuel-arm rebound fraction") +
  theme_pub
save_png_pdf(p5a / (p5b | p5c) + plot_layout(heights = c(0.85, 1)),
             "Extended_Fig6_Economic_Elasticity_Sensitivity", h = 145)

# Full plotted source data; no subset is silently discarded.
if (exists("pa")) write.csv(pa, file.path(HERE, "Extended_Fig6_PanelA_Render_Data.csv"), row.names = FALSE)
if (exists("pb2")) write.csv(pb2, file.path(HERE, "Extended_Fig6_PanelB_Render_Data.csv"), row.names = FALSE)
if (exists("pc")) write.csv(pc, file.path(HERE, "Extended_Fig6_PanelC_Render_Data.csv"), row.names = FALSE)
