# =============================================================================
# Extended Data Fig. 8 | Subsidy buffer: price-signal robustness (ED8 data)
# Data: scenario/output/fig5/ED10_Mecon_Series.csv, ED10_Subsidy_Buffer.csv
#       (builder in this folder)
# Output: Extended_Fig8_Subsidy_Buffer.{pdf,png}
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
  plot.tag.position = "topleft", plot.title = element_text(size = 7, face = "bold"),
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

cb <- c("base" = "#555555", "sb0.5" = "#E69F00", "sb1.0" = "#56B4E9",
        "BAU" = "#B81D0A", "Quota" = "#1A7A8A")

# ---- subsidy buffer panels ----
ms <- read.csv(file.path(OUT, "ED10_Mecon_Series.csv"))
msl <- ms %>% select(WEO, Year, base, sb0_5, sb1_0) %>%
  pivot_longer(c(base, sb0_5, sb1_0), names_to = "Subsidy", values_to = "M_econ")
msl$Subsidy <- factor(msl$Subsidy, levels = c("base", "sb0_5", "sb1_0"),
                      labels = c("No subsidy", "50% carbon-price subsidy", "Price-insulated (M_econ = 1)"))
msl$WEO <- factor(msl$WEO, levels = c("STEPS", "APS", "NZE"))

p8a <- ggplot(msl, aes(Year, M_econ, colour = Subsidy, linetype = Subsidy)) +
  geom_line(linewidth = 0.5) +
  facet_wrap(~ WEO, ncol = 3) +
  geom_hline(yintercept = 1, colour = "grey65", linewidth = 0.18, linetype = "dotted") +
  scale_colour_manual(values = c("No subsidy" = "#555555", "50% carbon-price subsidy" = "#E69F00", "Price-insulated (M_econ = 1)" = "#56B4E9"), name = NULL) +
  scale_linetype_manual(values = c("solid", "dashed", "dotted"), name = NULL) +
  labs(tag = "(a)", x = NULL, y = expression(M[econ])) +
  theme_pub + theme(legend.position = "bottom", legend.direction = "horizontal")

sub <- read.csv(file.path(OUT, "ED10_Subsidy_Buffer.csv"))
s50 <- sub %>% select(BAU_ID, WEO, Year, E_BAU_sb0_5, E_Quota_sb0_5) %>% rename(BAU = E_BAU_sb0_5, Quota = E_Quota_sb0_5) %>%
  mutate(Subsidy = "50% carbon-price subsidy")
s10 <- sub %>% select(BAU_ID, WEO, Year, E_BAU_sb1_0, E_Quota_sb1_0) %>% rename(BAU = E_BAU_sb1_0, Quota = E_Quota_sb1_0) %>%
  mutate(Subsidy = "Price-insulated (M_econ = 1)")
s00 <- sub %>% select(BAU_ID, WEO, Year, E_BAU, E_Quota) %>%
  rename(BAU = E_BAU, Quota = E_Quota) %>% mutate(Subsidy = "No subsidy")
y50 <- bind_rows(s00, s50, s10) %>%
  pivot_longer(c(BAU, Quota), names_to = "Arm", values_to = "GHG_Mt") %>%
  filter(Year == 2050)
y50$Subsidy <- factor(y50$Subsidy, levels = c("No subsidy", "50% carbon-price subsidy", "Price-insulated (M_econ = 1)"))

p8b <- ggplot(y50, aes(Subsidy, GHG_Mt, fill = Arm)) +
  geom_boxplot(outlier.size = 0.3, linewidth = 0.2, width = 0.65) +
  scale_fill_manual(values = cb[c("BAU", "Quota")], labels = c(BAU = "Fixed-2024-catch baseline", Quota = "Harvest-rate quota"), name = NULL) +
  labs(tag = "(b)", x = NULL, y = "2050 emissions (Mt CO2e)") +
  theme_pub + theme(axis.text.x = element_text(size = 5.5)) +
  scale_x_discrete(labels = c("No subsidy" = "No subsidy", "50% carbon-price subsidy" = "50% carbon\nsubsidy", "Price-insulated (M_econ = 1)" = "Price\ninsulated"))

cum <- sub %>% group_by(BAU_ID, WEO) %>%
  summarise(C = sum(E_BAU), Q = sum(E_Quota),
            C5 = sum(E_BAU_sb0_5), Q5 = sum(E_Quota_sb0_5),
            C1 = sum(E_BAU_sb1_0), Q1 = sum(E_Quota_sb1_0), .groups = "drop") %>%
  summarise(no = median(C / Q), sb05 = median(C5 / Q5), sb10 = median(C1 / Q1)) %>%
  pivot_longer(everything(), names_to = "Subsidy", values_to = "C_over_F")
cum$Subsidy <- factor(cum$Subsidy, levels = c("no", "sb05", "sb10"),
                      labels = c("No subsidy", "50% carbon-price subsidy", "Price-insulated"))
p8c <- ggplot(cum, aes(Subsidy, C_over_F)) +
  geom_col(fill = "#1A7A8A", width = 0.6) +
  geom_text(aes(label = sprintf("%.2f", C_over_F)), vjust = -0.4, size = 2.2) +
  coord_cartesian(ylim = c(0, max(cum$C_over_F) * 1.2)) +
  labs(tag = "(c)", x = NULL, y = "Cumulative GHG ratio (baseline / quota)") +
  theme_pub + theme(axis.text.x = element_text(size = 5.5)) +
  scale_x_discrete(labels = c("No subsidy"="No subsidy", "50% carbon-price subsidy"="50% carbon\nsubsidy", "Price-insulated"="Price\ninsulated"))

save_png_pdf((p8a / (p8b | p8c)) + plot_layout(heights = c(1, 1.1)),
             "Extended_Fig8_Subsidy_Buffer", w = 183, h = 130)

# Full plotted source data; no subset is silently discarded.
write.csv(msl, file.path(HERE, "Extended_Fig8_PanelA_Render_Data.csv"), row.names = FALSE)
write.csv(y50, file.path(HERE, "Extended_Fig8_PanelB_Render_Data.csv"), row.names = FALSE)
write.csv(cum, file.path(HERE, "Extended_Fig8_PanelC_Render_Data.csv"), row.names = FALSE)
stopifnot(!anyNA(y50$GHG_Mt), nrow(y50) == 81 * 3 * 2)
