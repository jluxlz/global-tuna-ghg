# ==============================================================================
# Fig 2: Spatial-Temporal Deconstruction of Global Tuna Fleet CEI (v4.0)
# ==============================================================================
# Panel A — 3-era CEI maps with RFMO boundaries + species overlay (LL/PS rows)
# Panel B — 2x3 trend matrix: CPUE / CEI / GHG slopes by Gear (RdBu diverging)
# ==============================================================================

library(ggplot2)
library(dplyr)
library(tidyr)
library(sf)
library(rnaturalearth)
library(rnaturalearthdata)
library(scales)
library(RColorBrewer)
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

# Species shapes for overlay on Panel A maps
species_shapes <- c(
  "SKJ" = 21, "YFT" = 24, "BET" = 22, "ALB" = 23, "SBT" = 25, "None" = 1
)

org_cb_cols <- c(
  "WCPFC" = "#E69F00", "IATTC" = "#56B4E9", "ICCAT" = "#009E73",
  "IOTC"  = "#CC79A7", "CCSBT" = "#555555"
)

# ===========================================================================
# 2. ACADEMIC THEMES
# ===========================================================================

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
    panel.background  = element_rect(fill = "#edf5fa", colour = NA),
    panel.grid        = element_blank(),
    panel.border      = element_rect(colour = "black", fill = NA, linewidth = 0.5),
    strip.background  = element_blank(),
    strip.text        = element_text(face = "bold", size = 7, family = "sans"),
    axis.text         = element_text(size = 5, colour = "grey30", family = "sans"),
    axis.title        = element_blank(),
    legend.position   = "bottom",
    legend.title      = element_text(face = "bold", size = 7, family = "sans"),
    legend.text       = element_text(size = 6, family = "sans"),
    legend.direction  = "horizontal",
    legend.key.width  = unit(0.5, "cm"),
    legend.key.height = unit(0.25, "cm"),
    legend.margin     = margin(t = 0, b = 0),
    plot.tag          = element_text(face = "bold", size = 8, family = "sans"),
    plot.tag.position = "topleft",
    plot.margin       = margin(0, 1, 0, 1, unit = "pt")
  )

# ===========================================================================
# 3. BASEMAP & RFMO BOUNDARIES
# ===========================================================================
cat("Loading basemap...\n")
world <- ne_countries(scale = "medium", returnclass = "sf")

SHAPE_DIR <- file.path(SCRIPT_DIR, "..", "..", "shape_file")
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
for (nm in names(rfmo_sf)) rfmo_sf[[nm]]$RFMO <- nm
rfmo_all <- do.call(rbind, unname(rfmo_sf))
rfmo_all <- st_wrap_dateline(rfmo_all)

# RFMO outline colours — colourblind-friendly, matching org_cb_cols
rfmo_outline_cols <- c(
  "WCPFC" = "#E69F00", "IATTC" = "#56B4E9", "ICCAT" = "#009E73",
  "IOTC"  = "#CC79A7", "CCSBT" = "#555555"
)

# ===========================================================================
# 4. READ PRECOMPUTED DATA
# ===========================================================================
cat("Reading precomputed data...\n")
df_a <- read.csv("Fig2_PanelA_Era_CEI.csv") %>%
  filter(is.finite(Mean_CEI), Mean_CEI > 0) %>%
  mutate(
    Era  = factor(Era, levels = c("1970-1990", "1991-2005", "2006-2025"), labels = c("1970-1990", "1991-2005", "2006-2024")),
    Gear = factor(Gear, levels = c("LL", "PS")),
    Grid_Size = 5.1,
    Dominant_Species = ifelse(Dominant_Species %in% names(species_shapes),
                              Dominant_Species, "None")
  )

df_slopes <- read.csv("Fig2_PanelBC_Grid_Slopes.csv") %>%
  filter(!is.na(CEI_slope_pct), is.finite(CEI_slope_pct),
         !is.na(GHG_slope_pct), is.finite(GHG_slope_pct)) %>%
  mutate(
    Gear = factor(Gear, levels = c("LL", "PS")),
    Grid_Size = 5.1
  )

# ---- Land mask: remove grids whose centre falls on land (5deg snap artifact) ----
# Use sf::st_join — points on land get a non-NA admin field from world
filter_land <- function(df) {
  pts <- st_as_sf(df, coords = c("lon", "lat"), crs = 4326)
  # Join with world: ocean points get NA, land points get a country name
  joined <- st_join(pts, world[, "admin"], join = st_intersects)
  is_land <- !is.na(joined$admin)
  cat(sprintf("  Land mask: %d rows on land removed\n", sum(is_land)))
  df[!is_land, ]
}
# Preserve coastal tiles even when their centre lies on land. The land layer
# masks their terrestrial portions; removing the centre would discard ocean data.

# ===========================================================================
# 5. PANEL A — 3-Era CEI Maps with RFMO boundaries + species overlay
# ===========================================================================
cat("Building Panel A: 3-era CEI maps...\n")

# Log-based absolute CEI breaks (t CO2e / t catch)
cei_breaks <- c(0.1, 0.5, 1, 2, 5, 10, 20, 50)
cei_max_a  <- max(cei_breaks)

# Filter to break range
df_a_plot <- df_a

p_a <- ggplot(df_a_plot, aes(x = lon, y = lat)) +
  # CEI heatmap tiles
  geom_tile(aes(fill = Mean_CEI, width = Grid_Size, height = Grid_Size),
            colour = NA) +
  # Land
  geom_sf(data = world, inherit.aes = FALSE,
          fill = "gray85", colour = "gray50", linewidth = 0.10) +
  # RFMO boundaries — coloured by organisation, no fill
  geom_sf(data = rfmo_all, inherit.aes = FALSE,
          aes(colour = RFMO),
          fill = NA, linewidth = 0.15, linetype = "solid", key_glyph = draw_key_path) +
  scale_colour_manual(values = rfmo_outline_cols, name = "RFMO boundary",
                      guide = guide_legend(nrow = 1, override.aes = list(linewidth = 0.6))) +
  # Species overlay symbols (very subtle — don't obscure CEI heatmap)
  geom_point(data = df_a_plot %>% filter(Dominant_Species != "None", Dominant_Share >= 0.5),
             aes(shape = Dominant_Species),
             size = 0.4, colour = "grey20", alpha = 0.4, stroke = 0.2) +
  scale_shape_manual(values = species_shapes, name = "Dominant species (>=50% of catch)",
                     guide = guide_legend(override.aes = list(size = 2, alpha = 1),
                                          nrow = 1)) +
  # Full globe xlim
  coord_sf(crs = 4326, expand = FALSE,
           xlim = c(-180, 180), ylim = c(-60, 60)) +
  # LL/PS rows x 3 era columns, labels on left
  facet_grid(Gear ~ Era, switch = "y") +
  # Log-spaced CEI fill
  scale_fill_stepsn(
    colours  = c("#a6bddb", "#abd9e9", "#e0f3f8", "#ffffbf",
                 "#fdae61", "#f46d43", "#d73027", "#a50026"),
    trans    = "log10",
    breaks   = cei_breaks,
    limits   = c(min(cei_breaks), cei_max_a),
    oob      = squish,
    labels   = scales::number_format(accuracy = 0.1),
    na.value = "#a6bddb",
    name     = expression(CEI~(t~CO[2]*e~t^{-1})),
    guide    = guide_colorsteps(even.steps = FALSE, show.limits = TRUE,
                               title.position = "top", title.hjust = 0.5,
                               barwidth = unit(6, "cm"), barheight = unit(0.35, "cm"))
  ) +
  labs(tag = "(a)") +
  theme_map +
  theme(legend.position = "bottom",
        legend.margin = margin(t = 0, b = 0, unit = "pt"),
        axis.text.x = element_text(angle = 45, hjust = 1),
        legend.box = "vertical",
        legend.spacing = unit(2, "pt"),
        legend.justification = "centre")

cat("  Panel A complete.\n")
write.csv(df_a, "Fig2_PanelA_Render_Data.csv", row.names = FALSE)
write.csv(df_a %>% group_by(Era, Gear) %>% summarise(
  Input_Cells=n(), In_View=sum(abs(lat)<=60), Below_Colour_Range=sum(Mean_CEI<0.1),
  Above_Colour_Range=sum(Mean_CEI>50), Species_Symbols=sum(Dominant_Share>=0.5),
  .groups="drop"), "Fig2_Display_Coverage.csv", row.names=FALSE)

# ===========================================================================
# 6. PANEL B — 2×3 Trend Matrix (LL/PS × CPUE / CEI / GHG)
#    Separate colour scale per metric — CPUE/CEI/GHG have different ranges
#    Colour: red = bad (CEI/GHG up, CPUE down), blue = good (RdBu reversed)
# ===========================================================================
cat("Building Panel B: 2x3 trend matrix (per-metric colour scales)...\n")

# Helper: build one column of Panel B for a given metric
build_metric_plot <- function(data, metric_name, fill_label, negate = FALSE) {
  # Filter to this metric, optionally negate slope for CPUE semantics
  d <- data %>%
    filter(Metric == metric_name) %>%
    mutate(slope_val = if (negate) -slope_pct else slope_pct)

  # Per-metric symmetric breaks: 95th percentile of absolute values
  lim <- quantile(abs(d$slope_val), probs = 0.95, na.rm = TRUE)
  lim <- ceiling(lim / 2) * 2
  if (lim < 2) lim <- 2
  brk <- seq(-lim, lim, length.out = 5)
  cat(sprintf("  %s: lim=%.1f, breaks=%s\n", metric_name, lim,
              paste(round(brk, 1), collapse = ",")))

  ggplot(d, aes(x = lon, y = lat)) +
    geom_tile(aes(fill = slope_val, width = Grid_Size, height = Grid_Size),
              colour = NA) +
    geom_sf(data = world, inherit.aes = FALSE,
      fill = "gray85", colour = "gray50", linewidth = 0.10) +
    geom_sf(data = rfmo_all, inherit.aes = FALSE,
            aes(colour = RFMO),
            fill = NA, linewidth = 0.15, linetype = "solid") +
    scale_colour_manual(values = rfmo_outline_cols, guide = "none") +
    coord_sf(crs = 4326, expand = FALSE,
             xlim = c(-180, 180), ylim = c(-60, 60)) +
    facet_wrap(~ Gear, ncol = 1, strip.position = "left") +
    scale_fill_stepsn(
      colours  = rev(brewer.pal(11, "RdBu")),
      breaks   = brk,
      limits   = c(-lim, lim),
      oob      = squish,
      labels   = scales::number_format(accuracy = 0.1),
      na.value = "transparent",
      name     = fill_label,
      guide    = guide_colorsteps(even.steps = FALSE, show.limits = TRUE,
                                 title.position = "top", title.hjust = 0.5,
                                 barwidth = unit(2.5, "cm"),
                                 barheight = unit(0.3, "cm"))
    ) +
    labs(title = metric_name) +
    theme_map +
    theme(legend.position = "bottom",
          legend.margin = margin(t = 1, b = 0, unit = "pt"),
          axis.text.x = element_text(angle = 45, hjust = 1),
          plot.title = element_text(hjust = 0.5, size = 7, face = "bold",
                                    family = "sans"))
}

# Build per-metric data frames (from df_slopes, not unified df_b)
df_cpue <- df_slopes %>%
  filter(!is.na(CPUE_slope_pct), is.finite(CPUE_slope_pct)) %>%
  transmute(Gear, lon, lat, Grid_Size,
            slope_pct = CPUE_slope_pct, Metric = "CPUE")

df_cei <- df_slopes %>%
  filter(!is.na(CEI_slope_pct), is.finite(CEI_slope_pct)) %>%
  transmute(Gear, lon, lat, Grid_Size,
            slope_pct = CEI_slope_pct, Metric = "CEI")

df_ghg <- df_slopes %>%
  filter(!is.na(GHG_slope_pct), is.finite(GHG_slope_pct)) %>%
  transmute(Gear, lon, lat, Grid_Size,
            slope_pct = GHG_slope_pct, Metric = "GHG")

# All colour bars report the sign of the metric, not a good/bad classification.
p_cpue <- build_metric_plot(df_cpue, "CPUE",
                            "CPUE trend\n(%/yr)", negate = FALSE)
# CEI: red = CEI increasing (bad)
p_cei  <- build_metric_plot(df_cei,  "CEI",
                            "CEI trend\n(%/yr)",  negate = FALSE)
# GHG: red = GHG increasing (bad)
p_ghg  <- build_metric_plot(df_ghg,  "GHG",
                            "GHG trend\n(%/yr)",  negate = FALSE)

# Remove individual titles (replaced by strip labels)
p_cpue <- p_cpue + theme(plot.title = element_blank())
p_cei  <- p_cei  + theme(plot.title = element_blank())
p_ghg  <- p_ghg  + theme(plot.title = element_blank())

# Combine 3 metric panels via patchwork — VERTICALLY stacked (2026-09-12
# user directive: figure becomes left-right, panel b takes the RIGHT 1/3,
# so its three metrics are stacked instead of side-by-side).
# Tag "b" goes on the first sub-plot (CPUE panel)
p_cpue <- p_cpue + labs(tag = "(b)")
p_b <- (p_cpue | p_cei | p_ghg) + plot_layout(guides = "keep")

cat("  Panel B complete.\n")

# Export combined slope data (for reference)
df_b_export <- bind_rows(
  df_cpue %>% mutate(Metric = "CPUE trend"),
  df_cei  %>% mutate(Metric = "CEI trend"),
  df_ghg  %>% mutate(Metric = "GHG trend")
)
write.csv(df_b_export, "Fig2_PanelB_Slope_Map.csv", row.names = FALSE)

# ===========================================================================
# 7. ASSEMBLE & EXPORT
# ===========================================================================
cat("Assembling figure...\n")

# Vertical matrices share the same physical map columns, including axis space.
# Keep legends outside these columns so they cannot shrink either map matrix.
source(file.path(SCRIPT_DIR,"Legend_Layout.r"))
source(file.path(SCRIPT_DIR,"Fig2_Compact_Map_Layout.r"))
compact <- compact_map_matrices(p_a,p_cpue,p_cei,p_ghg,SCRIPT_DIR)
fig2 <- compact$plot; W_MM <- compact$width_mm; H_MM <- compact$height_mm
cat(sprintf("Exporting at %.0f x %.0f mm...\n", W_MM, H_MM))
ggsave(file.path(SCRIPT_DIR,"Fig2_Spatial_Temporal_CEI.pdf"), plot = fig2,
       width = W_MM, height = H_MM, units = "mm",
       device = cairo_pdf, bg = "white")
ggsave(file.path(SCRIPT_DIR,"Fig2_Spatial_Temporal_CEI.png"), plot = fig2,
       width = W_MM, height = H_MM, units = "mm", dpi = 300, bg = "white")
ggsave(file.path(SCRIPT_DIR,"Fig2_Spatial_Temporal_CEI.tiff"), plot = fig2,
       width = W_MM, height = H_MM, units = "mm", dpi = 900,
       compression = "lzw", bg = "white")
# NOTE (2026-09-13): Fig2.png / Fig2.pdf are USER-authored Adobe outputs —
# this script must ONLY write Fig2_Spatial_Temporal_CEI.* and never overwrite them.

cat("Fig 2 saved to", normalizePath(OUT_DIR), "\n")
