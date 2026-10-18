# =============================================================================
# Extended Data Fig. 7 | Technology-creep robustness (SF9)
# Data: scenario/output/fig5/SF9_Creep_Robustness.csv (builder in this folder)
# Output: Extended_Fig7_Technology_Creep_Robustness.{pdf,png}
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

# ---- SF9 panel ----
cr <- read.csv(file.path(OUT, "SF9_Creep_Robustness.csv"))
crl <- cr %>% select(TechCreep, Fuel = Fuel_red, Quota = QuotaOnly_red, Final = Final_red) %>%
  pivot_longer(-TechCreep, names_to = "Arm", values_to = "Reduction")
crl$Rate_pct <- 100 * crl$TechCreep
p9 <- ggplot(crl, aes(Rate_pct, Reduction, colour = Arm)) +
  geom_line(linewidth = 0.45) + geom_point(size = 1.7) +
  scale_x_continuous(breaks = c(1.9, 2.4, 4.3)) +
  scale_colour_manual(values = c(Fuel = "#1A7A8A", Quota = "#B81D0A", Final = "#4D4D4D"),
                    labels = c(Final = "Final portfolio", Fuel = "Fuel transition", Quota = "Quota reform"),
                    name = NULL) +
  labs(tag = "(a)", x = "Technology-creep rate (%/yr)", y = "2050 reduction vs own baseline (%)") +
  theme_pub
bau <- read.csv(file.path(OUT, "BAU_81_Annual.csv")) %>% filter(Year == 2050) %>% select(BAU_ID, WEO, TechCreep)
fuel <- read.csv(file.path(OUT, "Mitigation_Results_Annual.csv")) %>% filter(Year == 2050, Mitigation_Pathway == "Fuel") %>%
  transmute(BAU_ID, Arm = "Fuel", Reduction = GHG_Reduction_pct)
quota <- read.csv(file.path(OUT, "Fig5_QuotaOnly_Annual.csv")) %>% filter(Year == 2050) %>%
  transmute(BAU_ID, Arm = "Quota", Reduction = Reduction_pct)
final <- read.csv(file.path(OUT, "Fig5_Final_Combination_Annual.csv")) %>% filter(Year == 2050) %>%
  transmute(BAU_ID, Arm = "Final", Reduction = Reduction_pct)
all_futures <- bind_rows(fuel, quota, final) %>% left_join(bau, by = "BAU_ID") %>%
  mutate(WEO = factor(WEO, levels = c("STEPS", "APS", "NZE")), Arm = factor(Arm, levels = c("Fuel", "Quota", "Final")))
stopifnot(nrow(all_futures) == 81 * 3, !anyNA(all_futures$Reduction))
p9b <- ggplot(all_futures, aes(Arm, Reduction, fill = Arm)) +
  geom_boxplot(width = 0.55, linewidth = 0.25, outlier.shape = NA, alpha = 0.7) +
  geom_point(aes(shape = factor(TechCreep)), position = position_jitter(width = 0.12, seed = 42), size = 0.65, alpha = 0.55) +
  facet_wrap(~WEO, nrow = 1) +
  scale_fill_manual(values = c(Fuel = "#1A7A8A", Quota = "#B81D0A", Final = "#4D4D4D"), guide = "none") +
  scale_shape_manual(values = c(16, 17, 15), labels = c("1.9% yr-1", "2.4% yr-1", "4.3% yr-1"), name = "Technology creep") +
  labs(tag = "(b)", x = NULL, y = "2050 paired reduction (%)") + theme_pub
save_png_pdf(p9 / p9b + plot_layout(heights = c(0.7, 1)), "Extended_Fig7_Technology_Creep_Robustness", h = 145)
write.csv(all_futures, file.path(HERE, "Extended_Fig7_PanelB_Render_Data.csv"), row.names = FALSE)

# Full plotted source data; no subset is silently discarded.
if (exists("crl")) write.csv(crl, file.path(HERE, "Extended_Fig7_PanelA_Render_Data.csv"), row.names = FALSE)
