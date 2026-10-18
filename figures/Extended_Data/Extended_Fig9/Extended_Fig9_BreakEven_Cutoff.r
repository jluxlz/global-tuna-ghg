# =============================================================================
# Extended Data Fig. 9 | Break-even effort-cap cutoff (ED9 data)
# Data: scenario/output/fig5/ED11_BreakEven_Cutoff.csv (builder in this folder)
# Output: Extended_Fig9_BreakEven_Cutoff.{pdf,png}
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

save_png_pdf <- function(p, name, w = 183, h = 85) {
  ggsave(file.path(HERE, paste0(name, ".pdf")), p, width = w, height = h, units = "mm",
         device = cairo_pdf, bg = "white")
  ggsave(file.path(HERE, paste0(name, ".png")), p, width = w, height = h, units = "mm",
         dpi = 300, bg = "white")
  ggsave(file.path(HERE, paste0(name, ".tiff")), p, width = w, height = h,
         units = "mm", dpi = 900, compression = "lzw", bg = "white")
  cat("saved", name, "\n")
}

# ---- break-even panels ----
df <- read.csv(file.path(OUT, "ED11_BreakEven_Cutoff.csv"))
df$TechCreep_lab <- sprintf("%.1f%%/yr", 100 * df$TechCreep)

y50 <- df %>% filter(Year == 2050) %>%
  select(BAU_ID, E_BAU, E_BAU_cap1_5, E_BAU_cap2_0, E_QuotaOnly) %>%
  pivot_longer(c(E_BAU, E_BAU_cap1_5, E_BAU_cap2_0, E_QuotaOnly),
               names_to = "Arm", values_to = "GHG_Mt")
y50$Arm <- factor(y50$Arm, levels = c("E_BAU", "E_BAU_cap1_5", "E_BAU_cap2_0", "E_QuotaOnly"),
                  labels = c("Uncapped", "Cap 1.5x", "Cap 2.0x", "Harvest-rate quota"))

p9a <- ggplot(y50, aes(Arm, GHG_Mt, fill = Arm)) +
  geom_boxplot(outlier.size = 0.3, linewidth = 0.2, width = 0.6) +
  scale_fill_manual(values = c("Uncapped" = "#B81D0A", "Cap 1.5x" = "#E69F00",
                               "Cap 2.0x" = "#56B4E9", "Harvest-rate quota" = "#1A7A8A")) +
  labs(tag = "(a)", x = NULL, y = "2050 emissions (Mt CO2e)") +
  theme_pub + theme(axis.text.x = element_text(angle = 18, hjust = 1), legend.position = "none")

cum <- df %>% group_by(BAU_ID) %>%
  summarise(C = sum(E_BAU), C15 = sum(E_BAU_cap1_5), C20 = sum(E_BAU_cap2_0),
            Q = sum(E_QuotaOnly), .groups = "drop") %>%
  pivot_longer(c(C, C15, C20, Q), names_to = "Arm", values_to = "Mt")
cum$Arm <- factor(cum$Arm, levels = c("C", "C15", "C20", "Q"),
                  labels = c("Uncapped", "Cap 1.5x", "Cap 2.0x", "Harvest-rate quota"))
p9b <- ggplot(cum, aes(Arm, Mt, fill = Arm)) +
  geom_boxplot(outlier.size = 0.3, linewidth = 0.2, width = 0.6) +
  scale_fill_manual(values = c("Uncapped" = "#B81D0A", "Cap 1.5x" = "#E69F00",
                               "Cap 2.0x" = "#56B4E9", "Harvest-rate quota" = "#1A7A8A")) +
  labs(tag = "(b)", x = NULL, y = expression(Cumulative~GHG~(Mt~CO[2]*e))) +
  theme_pub + theme(axis.text.x = element_text(angle = 18, hjust = 1), legend.position = "none")

med <- df %>% group_by(Year, TechCreep_lab) %>%
  summarise(BAU = median(E_BAU), cap15 = median(E_BAU_cap1_5),
            cap20 = median(E_BAU_cap2_0), Q = median(E_QuotaOnly), .groups = "drop") %>%
  pivot_longer(c(BAU, cap15, cap20, Q), names_to = "Arm", values_to = "GHG_Mt")
med$Arm <- factor(med$Arm, levels = c("BAU", "cap15", "cap20", "Q"),
                  labels = c("Uncapped", "Cap 1.5x", "Cap 2.0x", "Harvest-rate quota"))
p9c <- ggplot(med, aes(Year, GHG_Mt, colour = Arm, linetype = Arm)) +
  geom_line(linewidth = 0.5) +
  facet_wrap(~ TechCreep_lab, ncol = 3) +
  scale_colour_manual(values = c("Uncapped" = "#B81D0A", "Cap 1.5x" = "#E69F00",
                                 "Cap 2.0x" = "#56B4E9", "Harvest-rate quota" = "#1A7A8A")) +
  labs(tag = "(c)", x = NULL, y = "Median emissions (Mt CO2e yr-1)") +
  theme_pub + theme(legend.position = "bottom", legend.direction = "horizontal")

save_png_pdf((p9a | p9b) / p9c + plot_layout(heights = c(1, 1.1)),
             "Extended_Fig9_BreakEven_Cutoff", w = 183, h = 130)

# Full plotted source data; no subset is silently discarded.
write.csv(y50, file.path(HERE, "Extended_Fig9_PanelA_Render_Data.csv"), row.names = FALSE)
write.csv(cum, file.path(HERE, "Extended_Fig9_PanelB_Render_Data.csv"), row.names = FALSE)
write.csv(med, file.path(HERE, "Extended_Fig9_PanelC_Render_Data.csv"), row.names = FALSE)
