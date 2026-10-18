# ==============================================================================
# Fig 1: Multi-dimensional Deconstruction of Global Tuna Fleet LCA GHG Emissions
# ==============================================================================
# 2×2 layout with unified colour system:
#   Panel A (TL) — Process perspective: 100% stacked area + total absolute line
#   Panel B (TR) — Gear perspective: small multiples with CEI heat background
#   Panel C (BL) — Species perspective: bubble scatter (Catch × GHG × CEI)
#   Panel D (BR) — Organisation perspective: stacked bar by RFMO × Gear
#
# Input:  Base_1_LCA_Global_Process.csv, Base_2_Fleet_GHG.csv,
#         Base_3_Spatial_Grid_Enriched.csv, GSA_Process_Parameter_Ranking.csv
# Output: Fig1_Multi_Dimensional_Deconstruction.png / .pdf / .svg
# ==============================================================================

library(ggplot2)
library(dplyr)
library(tidyr)
library(patchwork)
library(scales)
library(mgcv)

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
OUT_DIR  <- SCRIPT_DIR
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)

source(file.path(SCRIPT_DIR, 'Fig1_Icon_Assets.r'))

# ===========================================================================
# 1. UNIFIED COLOUR SYSTEM (consistent across all panels)
# ===========================================================================

# --- Gear colours (used in Panels B, D, and as secondary encoding elsewhere) ---
# v3.0: LL/PS split by Sector (I=distant-water, APW=coastal)
# Panel D (2026-09-21): book-based attribution carries LL/PS only
gear_sector_cols <- c(
  "LL" = "#B81D0A",   # longline (deep red)
  "PS" = "#1A7A8A"    # purse seine (deep cyan)
)
gear_sector_labels <- c(
  "LL" = "Longline",
  "PS" = "Purse seine"
)

# Legacy gear colours (for Panel B which does NOT split by Sector)
gear_cols <- c(
  "LL" = "#B81D0A",   # same gear hue as Panel D
  "PS" = "#1A7A8A",
  "TP" = "#00A087",   # transport/transhipment — green
  "SA" = "#984EA3"    # support/auxiliary — purple
)

# --- Process colours (Panel A) — warm-to-cool LCA cascade ---
process_cols <- c(
  "Fuel"        = "#9B2226",   # deep red — dominant (CO2 + CH4 + N2O)
  "Build"       = "#EE9B00",   # amber — hull construction
  "Maint"       = "#E9C46A",   # pale gold — maintenance
  "Gear"        = "#94D2BD",   # seafoam — fishing gear
  "Refrig"      = "#0A9396",   # teal — refrigerant
  "Bait"        = "#6A3D99"    # mauve — bait (LL only)
)

process_labels <- c(
  "Fuel"        = "Fuel",
  "Build"       = "Hull build",
  "Maint"       = "Hull maint.",
  "Gear"        = "Fishing gear",
  "Refrig"      = "Refrigerant",
  "Bait"        = "Bait"
)

# --- Species colours (Panel C) ---
species_cols <- c(
  "SKJ" = "#984EA3",   # skipjack — purple
  "YFT" = "#FF7F00",   # yellowfin — orange
  "BET" = "#377EB8",   # bigeye — blue
  "ALB" = "#E41A1C",   # albacore — red
  "SBT" = "#4DAF4A"    # southern bluefin — green
)

# --- Organisation colours (Panel D) ---
org_cols <- c(
  # Unified Okabe-Ito colourblind-friendly palette (consistent with Fig2/Fig3)
  "WCPFC" = "#E69F00",  # orange
  "IATTC" = "#56B4E9",  # sky blue
  "ICCAT" = "#009E73",  # bluish green
  "IOTC"  = "#CC79A7",  # reddish purple
  "CCSBT" = "#555555"   # dark grey (distinct from blues)
)

# ===========================================================================
# 2. NATURE FOOD PUBLICATION THEME (Nature Portfolio standards)
# ===========================================================================
# Canvas: 183 mm (7.2 in) wide, max 247 mm (9.7 in) tall
# Typography: Arial/Helvetica sans-serif, 5-7 pt, 8 pt bold lowercase tags
# Lines: 0.5 pt axes, 0.25 pt gridlines (dashed light grey)
# ===========================================================================

nature_theme <- theme_classic(base_size = 7, base_family = "sans") +
  theme(
    plot.tag          = element_text(face = "bold", size = 8, family = "sans"),
    plot.tag.position = "topleft",
    plot.title        = element_text(hjust = 0.5, face = "bold", size = 7, family = "sans"),
    axis.title        = element_text(size = 7, face = "bold", family = "sans"),
    axis.text         = element_text(size = 6, colour = "black", family = "sans"),
    axis.line         = element_line(colour = "black", linewidth = 0.5),
    axis.ticks        = element_line(colour = "black", linewidth = 0.5),
    legend.title      = element_text(face = "bold", size = 7, family = "sans"),
    legend.text       = element_text(size = 6, family = "sans"),
    legend.position   = "bottom",
    legend.key.size   = unit(0.35, "cm"),
    legend.margin     = margin(t = 0, b = 0),
    panel.grid.major  = element_line(colour = "grey90", linetype = "dashed", linewidth = 0.25),
    panel.grid.minor  = element_blank(),
    panel.background  = element_rect(fill = "white", colour = NA),
    plot.background   = element_rect(fill = "white", colour = NA),
    strip.background  = element_blank(),
    strip.text        = element_text(face = "bold", size = 7, family = "sans")
  )

tight_legend <- theme(
  legend.position      = "bottom",
  legend.box           = "vertical",
  legend.margin        = margin(t = 2, r = 0, b = 0, l = 0),
  legend.box.margin    = margin(t = 0, r = 0, b = 0, l = 0),
  legend.spacing       = unit(2, "pt"),
  legend.justification = "centre",
  legend.key.size      = unit(0.3, "cm")
)

theme_pub <- nature_theme

# ===========================================================================
# 3. READ & PREPARE DATA
# ===========================================================================
cat("Reading data...\n")

# --- Global process timeseries ---
df_proc <- read.csv(file.path(DATA_DIR, "Base_1_LCA_Global_Process.csv"), fileEncoding = "UTF-8-BOM") %>%
  filter(Year >= 1950, Year <= 2025)

# --- Fleet-level GHG ---
df_fleet <- read.csv(file.path(DATA_DIR, "Base_2_Fleet_GHG.csv"), fileEncoding = "UTF-8-BOM") %>%
  filter(Year >= 1950, Year <= 2025)

# --- Spatial grid (for species × gear aggregation) ---
df_grid_all <- read.csv(file.path(DATA_DIR, "Base_3_Spatial_Grid_Enriched.csv"), fileEncoding = "UTF-8-BOM") %>%
  filter(Year >= 1950, Year <= 2025,
         !is.na(GHG_emissions_median), GHG_emissions_median > 0)
df_grid <- df_grid_all %>% filter(Total_Catch > 0)

# ===========================================================================
# 4. PANEL A — Process Perspective: 100% Stacked Area + Total Line
# ===========================================================================
cat("Building Panel A: Process perspective...\n")

# 4a. Compute process totals in Mt (Fuel = CO2 + CH4 + N2O combined)
df_a_proc <- df_proc %>%
  transmute(
    Year  = Year,
    Fuel  = (Fuel_CO2_median + Fuel_CH4_median + Fuel_N2O_median + Fuel_WTT_median) / 1e6,
    Build = Build_median / 1e6,
    Maint = Maint_median / 1e6,
    Gear  = (Gear_Build_median + Gear_Maint_median) / 1e6,
    Refrig = Refrig_median / 1e6,
    Bait  = Bait_median / 1e6
  )

# 4b. Total GHG (Mt) + CI
df_a_total <- df_proc %>%
  transmute(
    Year     = Year,
    Total    = Total_median / 1e6,
    Total_lo = Total_p5 / 1e6,
    Total_hi = Total_p95 / 1e6
  )

# 4c. Compute percentages and scale total for dual-axis
max_total <- max(df_a_total$Total_hi, na.rm = TRUE)

df_a_pct <- df_a_proc %>%
  mutate(
    Total = Fuel + Build + Maint + Gear + Refrig + Bait,
    across(c(Fuel, Build, Maint, Gear, Refrig, Bait),
           ~ . / Total * 100)
  ) %>%
  pivot_longer(c(Fuel, Build, Maint, Gear, Refrig, Bait),
               names_to = "Process", values_to = "Percent") %>%
  mutate(Process = factor(Process, levels = rev(names(process_cols))))

# Scale total line to percentage range for dual-axis plotting
df_a_total <- df_a_total %>%
  mutate(
    Total_pct    = Total    / max_total * 100,
    Total_lo_pct = Total_lo / max_total * 100,
    Total_hi_pct = Total_hi / max_total * 100
  )

# 4d. Build the dual-axis plot
p_a <- ggplot() +
  # 100% stacked area
  geom_area(data = df_a_pct,
            aes(x = Year, y = Percent, fill = Process),
            alpha = 0.90, colour = NA) +
  # Total line + CI ribbon (scaled to percentage range)
  geom_ribbon(data = df_a_total,
              aes(x = Year, ymin = Total_lo_pct, ymax = Total_hi_pct),
              fill = "grey30", alpha = 0.20) +
  geom_line(data = df_a_total,
            aes(x = Year, y = Total_pct, linetype = "Total GHG"),
            colour = "black", linewidth = 0.8) +
  # Scales
  scale_fill_manual(
    values = process_cols,
    labels = process_labels,
    name   = "Emission process",
    guide  = guide_legend(nrow = 2, byrow = TRUE)
  ) +
  scale_linetype_manual(
    values = c("Total GHG" = "solid"),
    name   = NULL
  ) +
  scale_x_continuous(breaks = seq(1950, 2025, by = 15), expand = c(0, 0)) +
  scale_y_continuous(
    expand = c(0, 0),
    labels = comma_format(),
    # Secondary axis: map percentage back to Mt
    sec.axis = sec_axis(
      ~ . * max_total / 100,
      name = expression(Total~GHG~(Mt~CO[2]*e~yr^{-1})),
      labels = comma_format()
    )
  ) +
  labs(
    tag    = "(a)",
    x      = "Year",
    y      = "Process contribution (%)"
  ) +
  theme_pub +
  theme(legend.key.size = unit(0.35, "cm"))

cat("  Panel A complete.\n")

# Export Panel A input data
write.csv(df_a_pct, "Fig1_PanelA_Process_Pct.csv", row.names = FALSE)
write.csv(df_a_total, "Fig1_PanelA_Total_GHG.csv", row.names = FALSE)

# ===========================================================================
# ===========================================================================
# 5. PANEL B - Gear Perspective: Small Multiples (GHG area + CEI line)
# ===========================================================================
# Each panel = one gear type. Area = annual GHG with p5-p95 ribbon.
# The CEI dotted line is drawn only in coverage-comparable windows:
# longline from 1976, purse seine from 1990 (flag-level fleet records, and
# hence the catch denominator, are incomplete before those years).
# Transshipment carriers and support vessels carry no CEI because they do
# not land catch (no catch-based denominator for the index).
# Each panel carries its own CEI right-hand axis.
cat("Building Panel B: Gear perspective...\n")

# 5a. Aggregate GHG by Gear x Year (all 4 gear types)
df_b_ghg <- read.csv("Fig1_Gear_Annual_MC.csv") %>%
  mutate(Gear = factor(Gear, levels = names(gear_cols)))

# 5b. CEI by Gear x Year - only cells that received GHG allocation
df_b_cei <- df_grid %>%
  filter(Gear %in% c("LL", "PS", "TP", "SA"),
         GHG_emissions_median > 0) %>%
  group_by(Gear, Year) %>%
  summarise(
    Total_GHG   = sum(GHG_emissions_median, na.rm = TRUE),
    Total_Catch = sum(Total_Catch, na.rm = TRUE),
    .groups     = "drop"
  ) %>%
  mutate(
    CEI = ifelse(Total_Catch > 0, Total_GHG / Total_Catch, NA),
    Gear = factor(Gear, levels = names(gear_cols))
  ) %>%
  filter(!is.na(CEI), is.finite(CEI))

# 5b2. Restrict to coverage-comparable windows (LL: 1976+; PS: 1990+);
#      TP / SA drop out automatically (no catch-based CEI exists)
CEI_START <- c(LL = 1955, PS = 1961)   # trim only first-year small-sample spikes (2026-09-18, ghosts)
# Coverage-limited windows (2026-09-21): years in which the recorded catch base
# was still expanding steeply (LL: the catch denominator grows ~4x while the
# allocated GHG stays flat; PS: before the 1967 entry of additional fleets), so
# the ratio reflects reporting build-up rather than fleet intensity. The line
# is drawn in light grey for these years.
COV_LIM <- c(LL = 1968, PS = 1966)

# 5b3. CEI right-axis ranges in real CEI units (t CO2e per t catch);
#      floors/hi are nice round values bracketing the data range so
#      the dotted line reads as true CEI values on the right axis
AXIS_LO  <- c(LL = 0,  PS = 0)
AXIS_HI <- sapply(c("LL", "PS"), function(g) {
  values <- df_b_cei$CEI[df_b_cei$Gear == g & df_b_cei$Year >= CEI_START[[g]]]
  max(pretty(c(0, values), n = 4))
})
AXIS_BRK <- lapply(AXIS_HI, function(hi) pretty(c(0, hi), n = 4))
df_b_cei <- df_b_cei %>%
  filter(Gear %in% names(CEI_START)) %>%
  filter(Year >= CEI_START[as.character(Gear)])

# 5c. Normalise CEI to [0, 1] per gear (within the shown window) and keep
#     the per-gear CEI range for the right-hand axis
df_b_cei <- df_b_cei %>%
  group_by(Gear) %>%
  mutate(
    CEI_scaled = (CEI - min(CEI, na.rm = TRUE)) /
                 (max(CEI, na.rm = TRUE) - min(CEI, na.rm = TRUE)),
    CEI_lo = min(CEI, na.rm = TRUE),
    CEI_hi = max(CEI, na.rm = TRUE)
  ) %>%
  ungroup()

# 5c2. Fraction of the right-axis range (real CEI units), for plotting/CSV
df_b_cei <- df_b_cei %>%
  mutate(
    CEI_line_frac = (CEI - AXIS_LO[as.character(Gear)]) /
                    (AXIS_HI[as.character(Gear)] - AXIS_LO[as.character(Gear)])
  )

# 5d. One panel per gear, each with its own CEI right-hand axis
make_b_panel <- function(g, show_xlab = FALSE, show_ylab = FALSE) {
  gdat <- df_b_ghg %>% filter(Gear == g)
  cdat <- df_b_cei %>% filter(Gear == g)
    maxg <- max(gdat$GHG_Mt_hi, na.rm = TRUE)
  p <- ggplot(gdat, aes(x = Year)) +
    geom_ribbon(aes(ymin = GHG_Mt_lo, ymax = GHG_Mt_hi),
                fill = gear_cols[[g]], alpha = 0.18, colour = NA) +
    geom_area(aes(y = GHG_Mt), fill = gear_cols[[g]],
              alpha = 0.82, colour = NA)
  if (nrow(cdat) > 0) {
    lo <- AXIS_LO[[g]]
    hi <- AXIS_HI[[g]]
    p <- p +
      geom_line(data = cdat %>% filter(Year <= COV_LIM[[g]]) %>%
                  mutate(CEI_line = (CEI - lo) / (hi - lo) * maxg * 0.80),
                aes(y = CEI_line, colour = "Coverage-limited",
                    linetype = "Coverage-limited"), linewidth = 0.35) +
      geom_line(data = cdat %>% filter(Year >= COV_LIM[[g]]) %>%
                  mutate(CEI_line = (CEI - lo) / (hi - lo) * maxg * 0.80),
                aes(y = CEI_line, colour = "CEI trend",
                    linetype = "CEI trend"), linewidth = 0.35) +
      scale_linetype_manual(values = c("CEI trend" = "dotted",
                                       "Coverage-limited" = "dotted"), name = NULL) +
      scale_colour_manual(values = c("CEI trend" = "grey20",
                                     "Coverage-limited" = "grey60"), name = NULL) +
      scale_y_continuous(
        labels = comma_format(), expand = expansion(mult = c(0, 0.08)),
        sec.axis = sec_axis(
          ~ . / (maxg * 0.80) * (hi - lo) + lo,
          name   = if (g == "LL") expression(CEI~(t~CO[2]*e~t^{-1})) else NULL,
          breaks = AXIS_BRK[[g]]
        )
      )
  } else {
    p <- p + scale_y_continuous(labels = comma_format(),
                                expand = expansion(mult = c(0, 0.08)))
  }
  p <- p +
    scale_x_continuous(breaks = seq(1950, 2025, by = 20)) +
    labs(y = expression(GHG~(Mt~CO[2]*e~yr^{-1}))) +
  ggtitle(c(LL = "Longline", PS = "Purse seine", TP = "Carriers", SA = "Support")[[g]]) +
    theme_pub +
    theme(
      plot.title    = element_text(face = "bold", size = 7,
                                   family = "sans", hjust = 0.5),
      panel.spacing = unit(0.9, "lines")
    )
  if (!show_xlab) p <- p + theme(axis.title.x = element_blank())
  if (!show_ylab) p <- p + theme(axis.title.y = element_blank())
  if (g == "LL")  p <- p + labs(tag = "(b)")
  p
}

# 5e. Assemble 2 x 2
p_b <- (make_b_panel("LL", show_ylab = TRUE) |
        make_b_panel("PS")) /
       (make_b_panel("TP", show_xlab = TRUE, show_ylab = TRUE) |
        make_b_panel("SA", show_xlab = TRUE)) +
  plot_layout(guides = "collect") &
  theme(legend.position = "bottom")

cat("  Panel B complete.\n")

write.csv(df_b_ghg, "Fig1_PanelB_GHG_Area.csv", row.names = FALSE)
write.csv(df_b_cei, "Fig1_PanelB_CEI_Line.csv", row.names = FALSE)

# ===========================================================================
# 6. PANEL C — Species Perspective: Bubble Scatter
# ===========================================================================
cat("Building Panel C: Species perspective...\n")

# 6a. Aggregate species-level catch and attributed GHG (cumulative 1950-2025)
df_c <- df_grid %>%
  filter(Gear %in% c("LL", "PS")) %>%
  pivot_longer(
    cols = c(SBT_Tonnes, SKJ_Tonnes, BET_Tonnes, YFT_Tonnes, ALB_Tonnes),
    names_to  = "Species",
    values_to = "Catch"
  ) %>%
  mutate(
    Species     = gsub("_Tonnes", "", Species),
    Species_GHG = GHG_emissions_median * (Catch / Total_Catch)
  ) %>%
  filter(Catch > 0) %>%
  group_by(Species) %>%
  summarise(
    Total_Catch_Mt = sum(Catch, na.rm = TRUE) / 1e6,
    Total_GHG_Mt   = sum(Species_GHG, na.rm = TRUE) / 1e6,
    .groups        = "drop"
  ) %>%
  mutate(
    CEI = Total_GHG_Mt / Total_Catch_Mt,
    Species = factor(Species, levels = names(species_cols))
  ) %>%
  filter(!is.na(CEI), is.finite(CEI))

# 6b. Bubble scatter plot
p_c <- ggplot(df_c, aes(x = Total_Catch_Mt, y = Total_GHG_Mt)) +
  # Reference line: global mean CEI
  geom_abline(
    aes(slope = sum(df_c$Total_GHG_Mt) / sum(df_c$Total_Catch_Mt),
        intercept = 0, linetype = "Mean CEI"),
    colour = "grey50", linewidth = 0.5
  ) +
  # Bubbles
  geom_point(aes(size = CEI, fill = Species),
             shape = 21, colour = "black", stroke = 0.3, alpha = 0.85) +
  scale_fill_manual(values = species_cols, name = "Target species") +
  scale_linetype_manual(values = c("Mean CEI" = "dashed"), name = NULL) +
  scale_size_area(
    max_size = 12,
    breaks  = c(5, 10, 20, 30),
    name    = expression(CEI~(t~CO[2]*e~t^{-1})),
    guide   = guide_legend(override.aes = list(fill = "grey50"))
  ) +
  scale_x_continuous(labels = comma_format(), expand = expansion(mult = c(0.12, 0.15))) +
  scale_y_continuous(labels = comma_format(), expand = expansion(mult = c(0.12, 0.32))) +
  coord_cartesian(clip = "off") +
  labs(
    tag = "(c)",
    x   = expression(Matched~catch~(Mt)),
    y   = expression(Attributed~GHG~emissions~(Mt~CO[2]*e))
  ) +
  theme_pub +
  theme(
    legend.key.size = unit(0.35, "cm"),
    panel.grid.major = element_line(colour = "grey92", linetype = "dashed")
  )

# Fish are illustrative labels, never an additional data encoding.
fish_files <- c(ALB='Albacore', BET='Bigeye', SBT='Bluefin', SKJ='Skipjack', YFT='Yellowfin')
placements <- df_c
placements$Bubble_diameter_mm <- 12*sqrt(placements$CEI/max(placements$CEI))
placements$Icon_x <- placements$Total_Catch_Mt
# SBT and ALB are too close for stacked artwork; keep the data point fixed and
# use a short labelled callout in the empty lower-middle part of the panel.
placements$Icon_x[placements$Species == 'SBT'] <- 20
p_c <- p_c + annotate('segment', x=4.5,y=38,xend=20,yend=52,
  colour='grey55',linewidth=.25)
for (i in seq_len(nrow(placements))) {
  item <- placements[i,]
  name <- as.character(item$Species)
  path <- file.path(SCRIPT_DIR,'..','..','Icon',
    paste0('640x427-Tuna-',fish_files[name],'-NOAAFisheries.png'))
  a <- read_icon(path)
  fish_h <- 12*dim(a)[1]/dim(a)[2]
  fish <- grid::rasterGrob(a,y=grid::unit(.5,'npc')+
    grid::unit(item$Bubble_diameter_mm/2+5.6,'mm'),
    width=grid::unit(12,'mm'),height=grid::unit(fish_h,'mm'),interpolate=TRUE)
  label <- grid::textGrob(name,y=grid::unit(.5,'npc')+
    grid::unit(item$Bubble_diameter_mm/2+1.3,'mm'),
    gp=grid::gpar(fontsize=7,fontface='bold',fontfamily='Arial'))
  p_c <- p_c + annotation_custom(grid::grobTree(fish,label),
    xmin=item$Icon_x,xmax=item$Icon_x,
    ymin=item$Total_GHG_Mt,ymax=item$Total_GHG_Mt)
}
write.csv(placements,'Fig1_PanelC_Icon_Placements.csv',row.names=FALSE)

cat("  Panel C complete.\n")

write.csv(df_c, "Fig1_PanelC_Bubble.csv", row.names = FALSE)

# ===========================================================================
# 7. PANEL D — Organisation Perspective: Stacked Bar by RFMA × Gear
# ===========================================================================
# 2026-09-21: organisation attribution switched from the flag-majority rule
# (Base_2) to the catch-book basis (Base_3): each flag's fleet emissions are
# allocated to its grid records in proportion to standardised effort, and
# records are grouped by the RFMA of the catch book. LL+PS only; support
# vessels and records without grid coverage are excluded (coverage:
# Extended Data Fig. 4).
cat("Building Panel D: Organisation perspective (book-based)...\n")

# 7a-7b. Aggregate Organisation x Gear cumulative GHG (1950-2025)
df_d <- df_grid_all %>%
  filter(Gear %in% c("LL", "PS"),
         Organization %in% names(org_cols)) %>%
  group_by(Organization, Gear_Sector = Gear) %>%
  summarise(
    Total_GHG_Mt = sum(GHG_emissions_median, na.rm = TRUE) / 1e6,
    .groups      = "drop"
  ) %>%
  mutate(
    Organization  = factor(Organization, levels = names(org_cols)),
    Gear_Sector   = factor(Gear_Sector, levels = rev(names(gear_sector_cols)))
  )

# 7c. Sort organisations by cumulative GHG
org_order <- df_d %>%
  group_by(Organization) %>%
  summarise(Total = sum(Total_GHG_Mt), .groups = "drop") %>%
  arrange(desc(Total)) %>%
  pull(Organization) %>% rev()

df_d$Organization <- factor(df_d$Organization, levels = org_order)

# 7d. Pre-compute totals per Organisation for error bars
df_d_tot <- df_d %>%
  group_by(Organization) %>%
  summarise(Total = sum(Total_GHG_Mt), .groups = "drop") %>%
  left_join(read.csv("Fig1_Org_Cumulative_MC.csv"), by = "Organization") %>%
  mutate(Organization = factor(Organization, levels = org_order))

# 7e. Stacked bar with supplied RFMO artwork inserted beside its labels
p_d <- ggplot(df_d, aes(x = Total_GHG_Mt, y = Organization, fill = Gear_Sector)) +
  geom_col(colour = NA, width = 0.75) +
  geom_errorbar(
    data = df_d_tot,
    aes(xmin = Total_lo, xmax = Total_hi, y = Organization),
    inherit.aes = FALSE, orientation = "y", linewidth = 0.5, width = 0.25, colour = "grey30"
  ) +
  geom_text(
    data = df_d_tot,
    aes(x = Total_hi, y = Organization, label = sprintf("%.0f", Total)),
    inherit.aes = FALSE, hjust = -0.15, size = 2.8, fontface = "bold", family = "sans"
  ) +
  scale_fill_manual(
    values = gear_sector_cols,
    labels = gear_sector_labels,
    name   = "Gear type",
    guide  = guide_legend(nrow = 1, byrow = TRUE)
  ) +
  scale_x_continuous(
    labels = comma_format(),
    expand = expansion(mult = c(0, 0.12))
  ) +
  labs(
    tag = "(d)",
    x   = expression("Grid-attributed GHG"~(Mt~CO[2]*e)),
    y   = NULL
  ) +
  theme_pub +
  theme(
    panel.grid.major.y = element_blank(),
    axis.ticks.y       = element_blank(),
    axis.text.y        = element_text(face = "bold", size = 7, colour = "black"),
    legend.key.size    = unit(0.35, "cm")
  )

cat("  Panel D complete.\n")

write.csv(df_d, "Fig1_PanelD_Org_Gear.csv", row.names = FALSE)
write.csv(df_d_tot, "Fig1_PanelD_Org_Total.csv", row.names = FALSE)

# ===========================================================================
# 8. Supplied RFMO artwork is read-only; loaded by Fig1_Icon_Assets.r.
# ===========================================================================

# ===========================================================================
# 9. ASSEMBLE & EXPORT (Nature Food: 183 mm wide, sans-serif, PDF vector)
# ===========================================================================
source(file.path(SCRIPT_DIR,"Legend_Layout.r"))
cat("Assembling 2x2 composite figure...\n")

p_a <- p_a + tight_legend
p_b <- p_b & tight_legend   # patchwork object: use & to apply to all subplots
p_c <- p_c + tight_legend
p_d <- p_d + tight_legend

# Assemble: each panel keeps its own legend (guides = "keep")
p_a_layout <- horizontal_legend_plot(p_a,81,"Fig1a")
p_c_layout <- horizontal_legend_plot(p_c,81,"Fig1c")
p_d_layout <- add_rfmo_icon_column(p_d,SCRIPT_DIR)
fig1 <- (p_a_layout + p_b) / (p_c_layout + p_d_layout) +
  plot_layout(guides = "keep", heights = c(1.15, 1)) &
  theme(plot.margin = margin(t = 2, r = 2, b = 2, l = 2, unit = "pt"))

# Export — Nature Food: 183 mm x max 247 mm (use 183 x 220 mm)
W_MM <- 183; H_MM <- 196
cat(sprintf("  Exporting at %.0f x %.0f mm (Nature Food double-column)...\n", W_MM, H_MM))

ggsave(file.path(OUT_DIR, "Fig1_Multi_Dimensional_Deconstruction.pdf"),
       plot = fig1, width = W_MM, height = H_MM, units = "mm",
       device = cairo_pdf, bg = "white")
cat("  -> PDF (vector) with embedded fonts\n")

# Also render a PNG preview at 300 dpi
ggsave(file.path(OUT_DIR, "Fig1_Multi_Dimensional_Deconstruction.png"),
       plot = fig1, width = W_MM, height = H_MM, units = "mm", dpi = 300, bg = "white")
cat("  -> PNG preview (300 dpi)\n")
ggsave(file.path(OUT_DIR, "Fig1_Multi_Dimensional_Deconstruction.tiff"),
       plot = fig1, width = W_MM, height = H_MM, units = "mm", dpi = 900,
       compression = "lzw", bg = "white")

cat("\nFig 1 saved to", normalizePath(OUT_DIR), "\n")
