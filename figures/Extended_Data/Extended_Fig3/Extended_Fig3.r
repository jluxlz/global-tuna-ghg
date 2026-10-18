# =============================================================================
# Extended Data Fig. 3 - Scale versus structure across RFMA regions
#   (a) fleet-based org composition (fractional)         (b) RFMA x species GHG
#   (c) RFMA x species intensity heatmap                 (d) RFMA annual emissions
# Inputs: ExtFig3_PanelA..D_*.csv (preprocess_extended_fig2.py, area-based)
# Run from this folder: Rscript Extended_Fig3.r
# =============================================================================
library(ggplot2); library(dplyr); library(tidyr); library(scales)
library(patchwork); library(ggrepel)

args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
if (length(file_arg) > 0) {
  SCRIPT_DIR <- normalizePath(dirname(sub("^--file=", "", file_arg)))
} else {
  SCRIPT_DIR <- normalizePath(getwd())
}
setwd(SCRIPT_DIR)

org_cols <- c(WCPFC = "#E69F00", IATTC = "#56B4E9", ICCAT = "#009E73",
              IOTC = "#CC79A7", CCSBT = "#555555")
sp_cols  <- c(SKJ = "#984EA3", YFT = "#FF7F00", BET = "#377EB8",
              ALB = "#E41A1C", SBT = "#4DAF4A")
sec_cols <- c(LL = "#B81D0A", PS = "#1A7A8A")

nature_theme <- theme_classic(base_size = 7, base_family = "Arial") + theme(
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

# ---------------------------------------------------------------------------
cat("Reading panel data...\n")
pa <- read.csv("ExtFig3_PanelA_Org_Fleet_GHG.csv")
pb <- read.csv("ExtFig3_PanelB_Org_Species_GHG.csv", check.names = FALSE)
pc <- read.csv("ExtFig3_PanelC_Org_Species_CEI.csv")
pdta <- read.csv("ExtFig3_PanelD_Org_Year_GHG.csv")

org_order <- c("WCPFC", "IATTC", "IOTC", "ICCAT", "CCSBT")
org_order_a <- pa %>% group_by(Organization) %>% summarise(T = sum(Total_Mt), .groups = "drop") %>% arrange(desc(T)) %>% pull(Organization)
pa$Organization <- factor(pa$Organization, levels = rev(org_order_a))
pb$Organization <- factor(pb$Organization, levels = rev(org_order))
pdta$Organization <- factor(pdta$Organization, levels = org_order)
pc$Organization <- factor(pc$Organization, levels = org_order)
pc$Species <- factor(pc$Species, levels = names(sp_cols))

# ---- (a) fleet-based organisation composition (fractional equal-split) ----
sec_cols2 <- c("LL_DW" = "#B81D0A", "LL_CO" = "#F28B7C", "PS_DW" = "#1A7A8A",
               "PS_CO" = "#7FCDE0", "TP" = "#00A087", "SA" = "#984EA3")
pa$Gear_Sector <- factor(pa$Gear_Sector, levels = names(sec_cols2))
tot_a <- pa %>% group_by(Organization) %>%
  summarise(T = sum(Total_Mt), .groups = "drop") %>%
  left_join(read.csv("ExtFig3_PanelA_Total_MC.csv"), by = "Organization")

p_a <- ggplot(pa, aes(Total_Mt, Organization, fill = Gear_Sector)) +
  geom_col(width = 0.72, colour = NA) +
  geom_errorbarh(data = tot_a, aes(xmin = lo, xmax = hi, y = Organization),
                 inherit.aes = FALSE, height = 0.3, linewidth = 0.5,
                 colour = "grey30") +
  geom_text(data = tot_a, aes(x = hi, y = Organization, label = sprintf("%.0f", T)),
            inherit.aes = FALSE, hjust = -0.15, size = 2.5, fontface = "bold") +
  scale_fill_manual(values = sec_cols2, name = NULL,
                    breaks = c("LL_DW", "LL_CO", "PS_DW", "TP", "SA"),
                    labels = c("LL (distant-water)", "LL (coastal)",
                               "PS (distant-water)", "Transhipment", "Support")) +
  scale_x_continuous(labels = comma_format(),
                     expand = expansion(mult = c(0, 0.12))) +
  labs(tag = "(a)", x = expression("Cumulative emissions"~(Mt~CO[2]*e)), y = NULL) +
  nature_theme +
  theme(legend.position = "bottom", panel.grid.major.y = element_blank())

# ---- (b) RFMA x species GHG (stacked bars) --------------------------------
pl_b <- pb %>%
  pivot_longer(-Organization, names_to = "Species", values_to = "GHG_Mt") %>%
  mutate(Species = factor(Species, levels = rev(names(sp_cols))),
         Organization = factor(Organization, levels = rev(org_order))) %>%
  filter(!is.na(GHG_Mt))
tot_b <- pl_b %>% group_by(Organization) %>% summarise(T = sum(GHG_Mt), .groups = "drop")

p_b <- ggplot(pl_b, aes(GHG_Mt, Organization, fill = Species)) +
  geom_col(width = 0.7, colour = NA) +
  geom_text(data = tot_b, aes(x = T, y = Organization, label = sprintf("%.0f", T)),
            inherit.aes = FALSE, hjust = -0.15, size = 2.5, fontface = "bold") +
  scale_fill_manual(values = sp_cols, name = NULL, breaks = names(sp_cols)) +
  scale_x_continuous(expand = expansion(mult = c(0, 0.12))) +
  labs(tag = "(b)", x = expression(Emissions~(Mt~CO[2]*e)), y = NULL) +
  nature_theme + theme(legend.position = "bottom")

# ---- (c) RFMA x species CEI heatmap ---------------------------------------
pc <- pc %>% complete(Organization = factor(org_order, levels = org_order),
                      Species = factor(names(sp_cols), levels = names(sp_cols)))
pc$CEI_lab <- ifelse(is.na(pc$CEI), "\u2013", sprintf("%.1f", pc$CEI))
pc$masked <- is.na(pc$CEI)
# Muted sequential colours: positive intensity has no meaningful midpoint.
# Keep the original log scale, limits, values and missing-data mask.
cei_palette <- c('#EEF3EF','#C4DCD3','#88B8AF','#477F85','#203F59')
cei_position <- scales::rescale(log10(pmin(40,pmax(.7,pc$CEI))),from=log10(c(.7,40)))
pc$Rendered_fill_hex <- scales::gradient_n_pal(cei_palette)(cei_position)
pc$Rendered_fill_hex[pc$masked] <- '#F0F1F2'
rgb <- t(grDevices::col2rgb(pc$Rendered_fill_hex))/255
rgb_lin <- ifelse(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)^2.4)
luminance <- drop(rgb_lin %*% c(.2126,.7152,.0722))
dark_rgb <- grDevices::col2rgb('#000000')/255
dark_lin <- ifelse(dark_rgb<=.04045,dark_rgb/12.92,((dark_rgb+.055)/1.055)^2.4)
dark_lum <- sum(dark_lin*c(.2126,.7152,.0722))
pc$txt_col <- ifelse(pc$masked,'#52626A',
  ifelse((luminance+.05)/(dark_lum+.05)>=1.05/(luminance+.05),'#000000','white'))
p_c <- ggplot(pc, aes(Species, Organization)) +
  geom_tile(aes(fill = CEI), colour = "white", linewidth = 0.4) +
  geom_text(aes(label = CEI_lab, colour = txt_col), size = 2.4, fontface = "bold") +
  scale_colour_identity() +
  scale_fill_gradientn(colours=cei_palette,trans = "log10", na.value = "#F0F1F2",
                       name = expression(CEI~(t~CO[2]*e~t^-1)),
                       breaks = c(1, 3, 10, 30), limits = c(0.7, 40), oob = scales::squish,
                       guide=guide_colourbar(barwidth=unit(32,'mm'),barheight=unit(2.5,'mm'),
                                             title.position='left')) +
  scale_x_discrete(position = "top") +
  labs(tag = "(c)", x = NULL, y = NULL) +
  nature_theme + theme(panel.grid.major = element_blank(),
                       axis.line = element_blank(), axis.ticks = element_blank())

# ---- (d) RFMA annual emissions, 1950-2025 (area-based series) -------------
p_d <- ggplot(pdta, aes(Year, GHG_Mt, colour = Organization, fill = Organization)) +
  geom_ribbon(aes(ymin = GHG_lo, ymax = GHG_hi), colour = NA, alpha = 0.12) +
  geom_line(linewidth = 0.55) +
  scale_colour_manual(values = org_cols, name = NULL) +
  scale_fill_manual(values = org_cols, guide = "none") +
  scale_x_continuous(breaks = c(1950, 1975, 2000, 2025)) +
  scale_y_continuous(labels = comma_format()) +
  labs(tag = "(d)", x = NULL,
       y = expression(Emissions~(Mt~CO[2]*e~yr^-1))) +
  nature_theme + theme(legend.position = "bottom")

# ---- assemble + export ----------------------------------------------------
cat("Assembling figure...\n")
fig <- ((p_a + guides(fill = guide_legend(nrow = 2))) | p_b) / (p_c | p_d) +
  plot_layout(heights = c(1, 0.92), guides = "keep") &
  theme(plot.margin = margin(t = 2, r = 4, b = 2, l = 2, unit = "pt"))

W_MM <- 183; H_MM <- 165
cat(sprintf("Exporting at %.0f x %.0f mm...\n", W_MM, H_MM))
ggsave("Extended_Fig3.pdf", plot = fig, width = W_MM, height = H_MM,
       units = "mm", device = cairo_pdf, bg = "white")
ggsave("Extended_Fig3.png", plot = fig, width = W_MM, height = H_MM,
       units = "mm", dpi = 300, bg = "white")
cat("Extended Fig 3 saved to", normalizePath("."), "\n")

ggsave("Extended_Fig3.tiff", fig, width = W_MM, height = H_MM, units = "mm", dpi = 900, compression = "lzw", bg = "white")

# Full plotted source data; no subset is silently discarded.
if (exists("pa")) write.csv(pa, file.path(SCRIPT_DIR, "Extended_Fig3_PanelA_Render_Data.csv"), row.names = FALSE)
if (exists("pl_b")) write.csv(pl_b, file.path(SCRIPT_DIR, "Extended_Fig3_PanelB_Render_Data.csv"), row.names = FALSE)
if (exists("pc")) write.csv(pc, file.path(SCRIPT_DIR, "Extended_Fig3_PanelC_Render_Data.csv"), row.names = FALSE)
if (exists("pdta")) write.csv(pdta, file.path(SCRIPT_DIR, "Extended_Fig3_PanelD_Render_Data.csv"), row.names = FALSE)
