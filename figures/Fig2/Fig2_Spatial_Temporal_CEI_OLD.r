# ==============================================================================
# Fig 2: Spatial-Temporal Deconstruction of Global Tuna Fleet CEI
# ==============================================================================
# 2x2 layout with unified gear/species colour system:
#   Panel A (TL) -- 3-era CEI spatial patterns (1950-1979, 1980-2000, 2001-2025)
#   Panel B (TR) -- Grid-level CEI + GHG trend slope maps
#   Panel C (BL) -- Phase-space quadrant: Catch slope x CEI slope by species
#   Panel D (BR) -- Phase trajectory: Tech-ecology decoupling by RFMO x Decade
#
# Preprocessing: preprocess_fig2.py (scipy.stats.linregress + kendalltau)
#   -> Fig2_PanelA_Era_CEI.csv, Fig2_PanelBC_Grid_Slopes.csv
# ==============================================================================

library(ggplot2)
library(dplyr)
library(tidyr)
library(sf)
library(rnaturalearth)
library(rnaturalearthdata)
library(scales)
library(RColorBrewer)
library(mgcv)
library(patchwork)

# ---------------------------------------------------------------------------
# 0. Paths & settings
# ---------------------------------------------------------------------------
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

DATA_DIR <- "../../GHG_Calculation"
OUT_DIR  <- "."
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)

# ===========================================================================
# 1. UNIFIED COLOUR SYSTEM
# ===========================================================================

gear_cols <- c("LL" = "#E64B35", "PS" = "#4DBBD5")

species_cols <- c(
  "SKJ" = "#984EA3", "YFT" = "#FF7F00", "BET" = "#377EB8",
  "ALB" = "#E41A1C", "SBT" = "#4DAF4A", "None" = "#B0B0B0"
)

# Colorblind-friendly palette for Panel D (Okabe-Ito)
org_cb_cols <- c(
  "WCPFC" = "#E69F00", "IATTC" = "#56B4E9", "ICCAT" = "#009E73",
  "IOTC"  = "#CC79A7", "CCSBT" = "#0072B2"
)

# ===========================================================================
# 2. ACADEMIC THEMES (bumped font sizes for A4 18cm column readability)
# ===========================================================================
# Nature Food publication theme
theme_pub <- theme_classic(base_size = 7, base_family = "sans") +
  theme(
    plot.tag          = element_text(face = "bold", size = 8, family = "sans"),
    plot.tag.position = "topleft",
    axis.title        = element_text(size = 7, face = "bold", family = "sans"),
    axis.text         = element_text(size = 6, colour = "black", family = "sans"),
    axis.line         = element_line(colour = "black", linewidth = 0.5),
    axis.ticks        = element_line(colour = "black", linewidth = 0.5),
    legend.title      = element_text(face = "bold", size = 7, family = "sans"),
    legend.text       = element_text(size = 6, family = "sans"),
    legend.position   = "bottom",
    legend.box        = "horizontal",
    legend.key.size   = unit(0.35, "cm"),
    legend.margin     = margin(t = 0, b = 0),
    panel.grid.major  = element_line(colour = "grey90", linetype = "dashed", linewidth = 0.25),
    panel.grid.minor  = element_blank(),
    strip.background  = element_blank(),
    strip.text        = element_text(face = "bold", size = 7, family = "sans")
  )

theme_map <- theme_minimal(base_size = 7, base_family = "sans") +
  theme(
    panel.background  = element_rect(fill = "#d6eaf8", colour = NA),
    panel.grid        = element_blank(),
    panel.border      = element_rect(colour = "black", fill = NA, linewidth = 0.5),
    strip.background  = element_blank(),
    strip.text        = element_text(face = "bold", size = 7, family = "sans"),
    axis.text         = element_text(size = 6, colour = "grey30", family = "sans"),
    axis.title        = element_blank(),
    legend.position   = "bottom",
    legend.title      = element_text(face = "bold", size = 7, family = "sans"),
    legend.text       = element_text(size = 6, family = "sans"),
    legend.direction  = "horizontal",
    legend.key.width  = unit(0.8, "cm"),
    legend.margin     = margin(t = 0, b = 0),
    plot.tag          = element_text(face = "bold", size = 8, family = "sans"),
    plot.tag.position = "topleft",
    plot.margin       = margin(0, 1, 0, 1, unit = "pt")
  )

# ===========================================================================
# 3. BASEMAP (equirectangular projection, matching spatial_analysis convention)
# ===========================================================================
cat("Loading basemap...\n")
world <- ne_countries(scale = "medium", returnclass = "sf")

# RFMO boundary shapefiles for map overlay
SHAPE_DIR <- file.path(SCRIPT_DIR, "..", "..", "..", "shape_file")
rfmo_files <- list(
  CCSBT = file.path(SHAPE_DIR, "CCSBT", "RFB_CCSBT.shp"),
  IATTC = file.path(SHAPE_DIR, "IATTC", "RFB_IATTC.shp"),
  ICCAT = file.path(SHAPE_DIR, "ICCAT", "RFB_ICCAT.shp"),
  IOTC  = file.path(SHAPE_DIR, "IOTC",  "RFB_IOTC.shp"),
  WCPFC = file.path(SHAPE_DIR, "WCPFC", "RFB_WCPFC.shp")
)
flip_matrix <- matrix(c(0, 1, 1, 0), nrow = 2)

rfmo_sf <- lapply(rfmo_files, function(f) {
  s <- st_read(f, quiet = TRUE)
  s <- st_transform(s, crs = 4326)
  st_geometry(s) <- st_geometry(s) * flip_matrix
  st_crs(s) <- 4326
  s
})
# Combine into single sf with RFMO column
for (nm in names(rfmo_sf)) rfmo_sf[[nm]]$RFMO <- nm
rfmo_all <- do.call(rbind, unname(rfmo_sf))
rfmo_all <- st_wrap_dateline(rfmo_all)

# RFMO outline colours (matching org_cols from Fig1)
rfmo_cols <- c(
  CCSBT = "#2A363B", IATTC = "#019875", ICCAT = "#99B898",
  IOTC  = "#FECEA8", WCPFC = "#E84A5F"
)

# ===========================================================================
# 4. READ PRECOMPUTED DATA
# ===========================================================================
cat("Reading precomputed data...\n")
df_a <- read.csv("Fig2_PanelA_Era_CEI.csv") %>%
  filter(is.finite(Mean_CEI), Mean_CEI > 0) %>%
  mutate(
    Era  = gsub("–", "-", Era),  # normalise en-dash to hyphen
    Era  = factor(Era, levels = c("1950-1979", "1980-2000", "2001-2025")),
    Gear = factor(Gear, levels = c("LL", "PS")),
    Grid_Size = 5.1
  )

df_slopes <- read.csv("Fig2_PanelBC_Grid_Slopes.csv") %>%
  filter(!is.na(CEI_slope_pct), is.finite(CEI_slope_pct),
         !is.na(GHG_slope_pct), is.finite(GHG_slope_pct)) %>%
  mutate(Grid_Size = 5.1)

# ===========================================================================
# 5. PANEL A -- 3-Era CEI Spatial Patterns (5° grid, equirectangular)
# ===========================================================================
cat("Building Panel A: 3-era CEI maps...\n")

cei_breaks <- signif(quantile(df_a$Mean_CEI,
    probs = c(0.05, 0.15, 0.35, 0.55, 0.75, 0.88, 0.95, 0.98), na.rm = TRUE), 2)
cei_max_a <- cei_breaks[length(cei_breaks)]

p_a <- ggplot(df_a, aes(x = lon, y = lat)) +
  geom_tile(aes(fill = Mean_CEI, width = Grid_Size, height = Grid_Size),
            colour = NA) +
  geom_sf(data = world, inherit.aes = FALSE,
          fill = "gray85", colour = "gray50", linewidth = 0.10) +
  geom_sf(data = rfmo_all, inherit.aes = FALSE,
          fill = NA, colour = "grey40", linewidth = 0.25, linetype = "dashed") +
  coord_sf(crs = 4326, expand = FALSE, xlim = c(-160, 160), ylim = c(-60, 60)) +
  facet_grid(Gear ~ Era) +
  scale_fill_stepsn(
    colours  = c("#a6bddb", "#abd9e9", "#e0f3f8", "#ffffbf",
                 "#fdae61", "#f46d43", "#d73027", "#a50026"),
    trans    = "log10",
    breaks   = cei_breaks,
    limits   = c(0.05, cei_max_a),
    oob      = squish,
    na.value = "#a6bddb",
    name     = expression(CEI~(kg~CO[2]*e~kg^{-1})),
    guide    = guide_colorsteps(even.steps = FALSE, show.limits = TRUE,
                               title.position = "top", title.hjust = 0.5,
                               barwidth = unit(8, "cm"), barheight = unit(0.35, "cm"))
  ) +
  labs(tag = "a") +
  theme_map +
  theme(legend.position = "bottom",
        legend.margin = margin(t = -15, b = 0, unit = "pt"),
        axis.text.x = element_text(angle = 45, hjust = 1))

cat("  Panel A complete.\n")
write.csv(df_a, "Fig2_PanelA_Era_CEI.csv", row.names = FALSE)

# ===========================================================================
# 6. PANEL B -- CEI + GHG Trend Slope Maps (5° grid, equirectangular)
# ===========================================================================
cat("Building Panel B: CEI + GHG slope maps...\n")

df_b <- bind_rows(
  df_slopes %>% transmute(lon, lat, Grid_Size,
                          slope_pct = CEI_slope_pct, Metric = "CEI trend"),
  df_slopes %>% transmute(lon, lat, Grid_Size,
                          slope_pct = GHG_slope_pct, Metric = "GHG trend")
) %>%
  mutate(Metric = factor(Metric, levels = c("CEI trend", "GHG trend")))

slope_lim <- quantile(abs(df_b$slope_pct), probs = 0.95, na.rm = TRUE)
slope_breaks <- c(-slope_lim, -slope_lim/2, 0, slope_lim/2, slope_lim)
cat(sprintf("  Slope breaks: %s\n", paste(round(slope_breaks, 2), collapse = ", ")))

p_b <- ggplot(df_b, aes(x = lon, y = lat)) +
  geom_tile(aes(fill = slope_pct, width = Grid_Size, height = Grid_Size),
            colour = NA) +
  geom_sf(data = world, inherit.aes = FALSE,
          fill = "gray85", colour = "gray50", linewidth = 0.10) +
  geom_sf(data = rfmo_all, inherit.aes = FALSE,
          fill = NA, colour = "grey40", linewidth = 0.25, linetype = "dashed") +
  coord_sf(crs = 4326, expand = FALSE, xlim = c(-160, 160), ylim = c(-60, 60)) +
  facet_wrap(~ Metric, ncol = 1, scales = "fixed") +
  scale_fill_stepsn(
    colours  = rev(brewer.pal(11, "RdBu")),
    breaks   = slope_breaks,
    limits   = c(-slope_lim, slope_lim),
    oob      = squish,
    na.value = "transparent",
    name     = "Trend (%/yr)",
    guide    = guide_colorsteps(even.steps = FALSE, show.limits = TRUE,
                               title.position = "top", title.hjust = 0.5,
                               barwidth = unit(3.5, "cm"), barheight = unit(0.35, "cm"))
  ) +
  labs(tag = "b") +
  theme_map +
  theme(legend.position = "bottom",
        legend.margin = margin(t = -15, b = 0, unit = "pt"),
        axis.text.x = element_text(angle = 45, hjust = 1))

cat("  Panel B complete.\n")
write.csv(df_b, "Fig2_PanelB_Slope_Map.csv", row.names = FALSE)

# ===========================================================================
# 7. PANEL C -- Phase-Space Quadrant (split by species + All, 3×2 facets)
# ===========================================================================
cat("Building Panel C: Phase-space quadrant plot...\n")

# Compute dominant era per grid from Base_3 (snap to 5° like preprocess_fig2.py)
df_era_raw <- read.csv(file.path(DATA_DIR, "Base_3_Spatial_Grid_Enriched.csv")) %>%
  filter(GHG_emissions_median > 0) %>%
  mutate(
    lon = floor(lon / 5) * 5 + 2.5,
    lat = floor(lat / 5) * 5 + 2.5,
    Era = case_when(
      Year <= 1979 ~ "1950-1979",
      Year <= 2000 ~ "1980-2000",
      TRUE         ~ "2001-2025"
  )) %>%
  group_by(lon, lat, Era) %>%
  summarise(GHG_era = sum(GHG_emissions_median, na.rm = TRUE), .groups = "drop") %>%
  group_by(lon, lat) %>%
  slice_max(GHG_era, n = 1, with_ties = FALSE) %>%
  ungroup() %>% select(lon, lat, Era)

df_c <- df_slopes %>%
  left_join(df_era_raw, by = c("lon", "lat")) %>%
  mutate(Era = ifelse(is.na(Era), "2001-2025", Era)) %>%
  filter(Dominant_Species %in% names(species_cols),
         Mean_GHG > 0,
         !is.na(Catch_slope_pct), is.finite(Catch_slope_pct)) %>%
  mutate(Dominant_Species = factor(Dominant_Species, levels = names(species_cols)))

df_c_all <- df_c %>% mutate(Dominant_Species = factor("All", levels = c("All", names(species_cols))))
df_c <- df_c %>% mutate(Dominant_Species = factor(Dominant_Species, levels = c("All", names(species_cols))))
df_c <- bind_rows(df_c_all, df_c)

x_lim_c <- quantile(abs(df_c$Catch_slope_pct), 0.95, na.rm = TRUE)
y_lim_c <- quantile(abs(df_c$CEI_slope_pct),   0.95, na.rm = TRUE)

# Weighted centroids per species × era (background scatter + trajectory overlay)
df_centroids <- df_c %>%
  group_by(Dominant_Species, Era) %>%
  summarise(
    X_centroid = weighted.mean(Catch_slope_pct, Mean_GHG, na.rm = TRUE),
    Y_centroid = weighted.mean(CEI_slope_pct,   Mean_GHG, na.rm = TRUE),
    Total_GHG  = sum(Mean_GHG, na.rm = TRUE),
    .groups    = "drop"
  ) %>%
  arrange(Dominant_Species, Era)

# Species-era colours
make_era_cols <- function(hex) {
  rgb0 <- col2rgb(hex) / 255
  light <- rgb0 * 0.7 + 0.3
  mid   <- rgb0
  dark  <- rgb0 * 0.45
  c(rgb(light[1], light[2], light[3]),
    rgb(mid[1],   mid[2],   mid[3]),
    rgb(dark[1],  dark[2],  dark[3]))
}
sp_era_keys <- c()
for (sp in names(species_cols)) {
  for (era in c("1950-1979", "1980-2000", "2001-2025")) {
    sp_era_keys <- c(sp_era_keys, paste(sp, era, sep = "_"))
  }
}
sp_era_cols <- unlist(lapply(species_cols, make_era_cols))
names(sp_era_cols) <- sp_era_keys

p_c <- ggplot(df_c, aes(x = Catch_slope_pct, y = CEI_slope_pct)) +
  geom_vline(xintercept = 0, linetype = "dashed", colour = "grey50", linewidth = 0.4) +
  geom_hline(yintercept = 0, linetype = "dashed", colour = "grey50", linewidth = 0.4) +
  # Background: semi-transparent scatter cloud
  geom_point(aes(size = Mean_GHG, fill = interaction(Dominant_Species, Era, sep = "_")),
             shape = 21, colour = "transparent", stroke = 0, alpha = 0.22) +
  # Middle: centroid trajectory with arrows
  geom_path(data = df_centroids, aes(x = X_centroid, y = Y_centroid,
            group = Dominant_Species), colour = "grey20", linewidth = 0.6,
            arrow = arrow(length = unit(0.12, "cm"), type = "closed")) +
  # Top: centroid bubbles
  geom_point(data = df_centroids, aes(x = X_centroid, y = Y_centroid,
             size = Total_GHG, fill = interaction(Dominant_Species, Era, sep = "_")),
             shape = 21, colour = "grey10", stroke = 0.6, alpha = 1) +
  facet_wrap(~ Dominant_Species, ncol = 3) +
  scale_fill_manual(values = sp_era_cols, name = "Species / Era",
                    guide = guide_legend(override.aes = list(alpha = 1, size = 3), ncol = 3)) +
  scale_size_continuous(
    range  = c(1.5, 8), trans  = "log10",
    breaks = c(10, 100, 1000, 10000, 100000), labels = comma_format(),
    name   = expression(Era~Total~GHG~(t~CO[2]*e)),
    guide  = guide_legend(override.aes = list(fill = "grey50"))
  ) +
  scale_x_continuous(limits = c(-x_lim_c, x_lim_c), labels = comma_format(),
                     expand = expansion(mult = c(0.04, 0.04))) +
  scale_y_continuous(limits = c(-y_lim_c, y_lim_c), labels = comma_format(),
                     expand = expansion(mult = c(0.04, 0.04))) +
  labs(tag = "(c)",
       x = expression(Catch~trend~("%"~yr^{-1})),
       y = expression(CEI~trend~("%"~yr^{-1}))) +
  theme_pub +
  theme(
    strip.background = element_blank(),
    strip.text = element_text(face = "bold", size = 7, family = "sans"),
    panel.spacing = unit(1, "lines"),
    legend.position      = "bottom",
    legend.direction     = "horizontal",
    legend.box           = "horizontal",
    legend.box.spacing   = unit(6, "pt"),
    legend.justification = "centre"
  )

cat("  Panel C complete.\n")
write.csv(df_slopes, "Fig2_PanelC_Grid_Slopes.csv", row.names = FALSE)

cat("  Panel C complete.\n")

# ===========================================================================
# 8. PANEL D -- Phase Trajectory (LL & PS as separate facets with unit labels)
# ===========================================================================
cat("Building Panel D: Phase trajectory plot...\n")

df_d <- read.csv(file.path(DATA_DIR, "Base_3_Spatial_Grid_Enriched.csv")) %>%
  filter(Gear %in% c("LL", "PS"),
         Standard_Effort > 0, Total_Catch > 0,
         !is.na(GHG_emissions_median), GHG_emissions_median > 0,
         Organization %in% names(org_cb_cols)) %>%
  mutate(
    Decade         = paste0(floor(Year / 10) * 10, "s"),
    Scarcity_Index = ifelse(Gear == "LL", Standard_Effort / Total_Catch * 100,
                            Standard_Effort / Total_Catch),
    Tech_Intensity = ifelse(Gear == "LL", GHG_emissions_median / Standard_Effort * 100,
                            GHG_emissions_median / Standard_Effort)
  ) %>%
  filter(is.finite(Scarcity_Index), Scarcity_Index > 0,
         is.finite(Tech_Intensity), Tech_Intensity > 0) %>%
  group_by(Gear, Organization, Decade) %>%
  summarise(
    X_median  = median(Scarcity_Index, na.rm = TRUE),
    Y_median  = median(Tech_Intensity, na.rm = TRUE),
    Total_GHG = sum(GHG_emissions_median, na.rm = TRUE) / 1e6,
    .groups   = "drop"
  ) %>%
  mutate(
    Gear         = factor(Gear, levels = c("LL", "PS")),
    Organization = factor(Organization, levels = names(org_cb_cols)),
    Decade_Num   = as.numeric(sub("s", "", Decade)),
    Era          = case_when(
      Decade_Num < 1980 ~ "1950-1979",
      Decade_Num < 2001 ~ "1980-2000",
      TRUE               ~ "2001-2025"
    )
  ) %>%
  arrange(Gear, Organization, Decade_Num)

# Split by gear for independent axis labels
df_d_ll <- df_d %>% filter(Gear == "LL")
df_d_ps <- df_d %>% filter(Gear == "PS")

# Panel D: org-era colours — Era varies first (matching unlist order)
org_era_keys <- c()
for (org in names(org_cb_cols)) {
  for (era in c("1950-1979", "1980-2000", "2001-2025")) {
    org_era_keys <- c(org_era_keys, paste(org, era, sep = "_"))
  }
}
org_era_cols <- unlist(lapply(org_cb_cols, make_era_cols))
names(org_era_cols) <- org_era_keys

# --- LL sub-panel: org-era coloured bubbles, no arrows, hooks per 100 ---
p_d_ll <- ggplot(df_d_ll, aes(x = X_median, y = Y_median)) +
  geom_path(aes(group = Organization), colour = "grey60", linewidth = 0.4) +
  geom_point(aes(size = Total_GHG, fill = interaction(Organization, Era, sep = "_")),
             shape = 21, colour = "grey40", alpha = 0.75) +
  geom_text(aes(label = Decade), size = 2.5, fontface = "italic", family = "sans",
            hjust = -0.15, vjust = 0.5, colour = "grey50", show.legend = FALSE) +
  scale_x_log10(labels = comma_format()) +
  scale_y_log10(labels = comma_format()) +
  scale_fill_manual(values = org_era_cols, guide = "none") +
  scale_size_continuous(range = c(1.2, 5), guide = "none") +
  labs(
    x = expression(log[10]~(Hooks~per~100~t^{-1})~~"(resource scarcity)"),
    y = expression(log[10]~(kg~CO[2]*e~per~100~hooks)~~"(tech. intensity)")
  ) +
  ggtitle("LL (Longline)") +
  theme_pub +
  theme(legend.position = "none",
        plot.title = element_text(hjust = 0.5, face = "bold", size = 7,
                                  family = "sans"),
        plot.margin = margin(4, 2, 1, 2, unit = "pt"))

# --- PS sub-panel: org-era coloured bubbles, no arrows ---
p_d_ps <- ggplot(df_d_ps, aes(x = X_median, y = Y_median)) +
  geom_path(aes(group = Organization), colour = "grey60", linewidth = 0.4) +
  geom_point(aes(size = Total_GHG, fill = interaction(Organization, Era, sep = "_")),
             shape = 21, colour = "grey40", alpha = 0.75) +
  geom_text(aes(label = Decade), size = 2.5, fontface = "italic", family = "sans",
            hjust = -0.15, vjust = 0.5, colour = "grey50", show.legend = FALSE) +
  scale_x_log10(labels = comma_format()) +
  scale_y_log10(labels = comma_format()) +
  scale_fill_manual(values = org_era_cols, name = "RFMO / Era",
                    guide = guide_legend(override.aes = list(size = 3), ncol = 3)) +
  scale_size_continuous(
    range  = c(1.2, 5),
    name   = expression(Total~GHG~(Mt~CO[2]*e)),
    guide  = guide_legend(override.aes = list(fill = "grey50"))
  ) +
  labs(
    x = expression(log[10]~(Sets~t^{-1})~~"(resource scarcity)"),
    y = expression(log[10]~(kg~CO[2]*e~Set^{-1})~~"(tech. intensity)")
  ) +
  ggtitle("PS (Purse Seine)") +
  theme_pub +
  theme(legend.position = "bottom",
        legend.direction = "horizontal",
        legend.box = "horizontal",
        legend.justification = "centre",
        plot.title = element_text(hjust = 0.5, face = "bold", size = 7,
                                  family = "sans"),
        plot.margin = margin(4, 2, 1, 2, unit = "pt"))

# Add tag "d" to left sub-panel
p_d_ll <- p_d_ll + labs(tag = "d")

# Legend styling (position/box handled at patchwork level via guides="collect")
p_d_ps <- p_d_ps + theme(
  legend.key.size  = unit(0.45, "cm"),
  legend.text      = element_text(size = 8),
  legend.title     = element_text(size = 7),
  legend.margin    = margin(t = 0, r = 0, b = 0, l = 0),
  plot.margin      = margin(t = 4, r = 2, b = 8, l = 2, unit = "pt")
)

# Combine LL + PS — collect era + size legends, centered below both panels
p_d <- (p_d_ll | p_d_ps) +
  plot_layout(widths = c(1, 1), guides = "collect") &
  theme(legend.position  = "bottom",
        legend.box       = "vertical",
        legend.box.spacing = unit(4, "pt"),
        legend.direction = "horizontal",
        legend.justification = "centre")

cat(sprintf("  Trajectories: %d orgs x %d decades x 2 gears\n",
            n_distinct(df_d$Organization), n_distinct(df_d$Decade)))
cat("  Panel D complete.\n")
write.csv(df_d, "Fig2_PanelD_Trajectory.csv", row.names = FALSE)

# ===========================================================================
# 9. ASSEMBLE & EXPORT (tightened spacing, colorbars positioned under panels)
# ===========================================================================
cat("Assembling 2x2 composite figure...\n")

# Tight legend placement under each panel
tight_legend <- theme(
  legend.position  = "bottom",
  legend.direction = "horizontal",
  legend.box       = "horizontal",
  legend.margin    = margin(t = -2, r = 0, b = 0, l = 0),
  legend.box.margin = margin(t = 0, r = 0, b = 0, l = 0),
  legend.spacing   = unit(0, "cm"),
  legend.justification = "centre"
)

p_a <- p_a + tight_legend
p_b <- p_b + tight_legend
# Panel C has its own custom legend layout (vertical box, horizontal items)

# Top row: maps (A + B side by side) — give B slightly more width for its 2-row facet
top_row <- (p_a | p_b) + plot_layout(widths = c(2.6, 1), guides = "keep")

# 3-row layout: Panel C gets more height for its 3x2 bubble facets
fig2 <- top_row / p_c / p_d +
  plot_layout(heights = c(0.5, 1.4, 1.25), guides = "keep") &
  theme(plot.margin = margin(t = 2, r = 4, b = 6, l = 2, unit = "pt"))

# Export — Nature Food: 183 mm wide, 240 mm tall (within 247 mm max)
W_MM <- 183; H_MM <- 240
cat(sprintf("Exporting figures at %.0f x %.0f mm (Nature Food double-column)...\n", W_MM, H_MM))
ggsave(file.path(OUT_DIR, "Fig2_Spatial_Temporal_CEI.pdf"),
       plot = fig2, width = W_MM, height = H_MM, units = "mm",
       device = cairo_pdf, bg = "white")
cat("  -> PDF (vector) with embedded fonts\n")
ggsave(file.path(OUT_DIR, "Fig2_Spatial_Temporal_CEI.png"),
       plot = fig2, width = W_MM, height = H_MM, units = "mm", dpi = 300, bg = "white")
cat("  -> PNG preview (300 dpi)\n")

cat("\nFig 2 saved to", normalizePath(OUT_DIR), "\n")
