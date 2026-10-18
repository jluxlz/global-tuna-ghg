# ==============================================================================
# 0. Preload and Load
# ==============================================================================
library(tidyverse)
library(sf)
library(rnaturalearth)
library(rnaturalearthdata)
library(scales)
library(RColorBrewer) 
library(patchwork)
library(biscale)
library(cowplot) # For precise extraction and grouping of legends

cat("Loading basecharts...\n")
world <- ne_countries(scale = "medium", returnclass = "sf")

# ==============================================================================
# 1. Raw data reading and preliminary cleansing (Add Filter Logical)
# ==============================================================================
df_raw <- read_csv("Table1_Catch_with_Grid_GHG_CEI.csv", show_col_types = FALSE) %>%
  # [Optimize]: Were gonna filter it out Unknown, Clear Unusual Values
  filter(Gear %in% c("PS", "LL"), Total_Catch > 0, squaretypecode != "Unknown") %>%
  pivot_longer(
    cols = c(SKJ_Tonnes, BET_Tonnes, YFT_Tonnes, ALB_Tonnes, SBT_Tonnes),
    names_to = "Species", values_to = "Catch"
  ) %>%
  mutate(Species = str_replace(Species, "_Tonnes", "")) %>%
  filter(Catch > 0, !is.na(GHG_emissions_median), GHG_emissions_median > 0) %>% 
  mutate(
    Species_GHG = GHG_emissions_median * (Catch / Total_Catch),
    Era_Binary = ifelse(Year <= 2000, "Pre-2000", "Post-2000"),
    Organization = ifelse(str_detect(Organization, "ATTC"), "IATTC", Organization)
  )

# ==============================================================================
# 2. [Final architecture optimization]: Build Space Resize Search Table (Lookup Table)
# ==============================================================================
cat("Constructing a full-dimensional grid space heavy dictionaries...\n")

# Define an auxiliary function: Generate any N*M bilinear interpolation weights for grid cells
generate_weights <- function(lon_span, lat_span, code_name) {
  # Calculate deviation range (Spreading out at the integer longitude)
  lon_offsets <- seq(-floor((lon_span-1)/2), floor(lon_span/2), by = 1)
  lat_offsets <- seq(-floor((lat_span-1)/2), floor(lat_span/2), by = 1)
  
  expand_grid(lon_off = lon_offsets, lat_off = lat_offsets) %>%
    mutate(
      # Dynamic calculation of double-linear decay denominators (Make sure the edge is smooth)
      weight_x = 1 - abs(lon_off) / ((lon_span + 1) / 2),
      weight_y = 1 - abs(lat_off) / ((lat_span + 1) / 2),
      weight_raw = weight_x * weight_y,
      weight = weight_raw / sum(weight_raw), # Normalize, Its a guaranteed quality maintenance
      square_type = code_name
    ) %>%
    select(square_type, lon_off, lat_off, weight)
}

# [Core changes]: Dictionary Key Directly use the original string in your data！
# attention: International fisheries 5x10 Usually 5 Latitude × 10 Longitude, And so lat_span=5, lon_span=10
dict_1x1   <- generate_weights(lon_span = 1, lat_span = 1, code_name = "1x1")
dict_5x5   <- generate_weights(lon_span = 5, lat_span = 5, code_name = "5x5")
dict_10x10 <- generate_weights(lon_span = 10, lat_span = 10, code_name = "10x10")
dict_5x10  <- generate_weights(lon_span = 10, lat_span = 5, code_name = "5x10") 
dict_10x20 <- generate_weights(lon_span = 20, lat_span = 10, code_name = "10x20")

# Merge into an invincible dictionary
weight_dictionary <- bind_rows(dict_1x1, dict_5x5, dict_10x10, dict_5x10, dict_10x20)

# ==============================================================================
# 3. Extreme downscale processing (Direct Join Match)
# ==============================================================================
cat("Its going straight Join Double-linear downscale...\n")

df_clean <- df_raw %>%
  # [Simplified completely]: No need for anything case_when, Just take yours squaretypecode Fields match in dictionary！
  inner_join(weight_dictionary, by = c("squaretypecode" = "square_type")) %>%
  mutate(
    Lon = Lon + lon_off,            
    Lat = Lat + lat_off,
    Catch = Catch * weight,             
    Species_GHG = Species_GHG * weight  
  ) %>%
  # ultimate grid alignment (Grid Snapping) - align to the common global half-degree grid centres
  mutate(
    Lon = floor(Lon) + 0.5,
    Lat = floor(Lat) + 0.5
  ) %>%
  # Same 1x1 The space grid is perfect for the fusion
  group_by(Year, Era_Binary, Organization, Gear, Species, Lon, Lat) %>%
  summarise(
    Catch = sum(Catch, na.rm = TRUE), 
    Species_GHG = sum(Species_GHG, na.rm = TRUE), 
    .groups = "drop"
  ) %>%
  # Harmonize all the retraced grids visual dimensions
  mutate(Grid_Size = 0.6)

cat("Data cleansing and multidimensional downscaling are perfect！\n")

# ==============================================================================
# 4. Drawing data preparation
# ==============================================================================
binary_years <- df_clean %>% group_by(Era_Binary) %>% summarise(N_Years = n_distinct(Year), .groups="drop")

df_binary <- df_clean %>%
  group_by(Era_Binary, Lon, Lat, Gear, Species, Grid_Size) %>%
  summarise(Sum_Catch = sum(Catch, na.rm=T), Sum_GHG = sum(Species_GHG, na.rm=T), .groups="drop") %>%
  left_join(binary_years, by="Era_Binary") %>%
  mutate(Mean_GHG = Sum_GHG / N_Years, Mean_CEI = Sum_GHG / Sum_Catch) %>%
  filter(is.finite(Mean_CEI))

df_delta <- df_binary %>%
  pivot_wider(names_from = Era_Binary, values_from = c(Mean_GHG, Mean_CEI), values_fill = 0) %>%
  mutate(Delta_GHG = `Mean_GHG_Post-2000` - `Mean_GHG_Pre-2000`, Delta_CEI = `Mean_CEI_Post-2000` - `Mean_CEI_Pre-2000`)

lim_ghg <- quantile(abs(df_delta$Delta_GHG), 0.85, na.rm = TRUE)
lim_cei <- quantile(abs(df_delta$Delta_CEI), 0.85, na.rm = TRUE)

df_bivar_base <- df_clean %>% filter(Era_Binary == "Post-2000") %>% 
  group_by(Lon, Lat, Gear, Species, Grid_Size) %>%
  summarise(Sum_Catch = sum(Catch, na.rm=T), Sum_GHG = sum(Species_GHG, na.rm=T), .groups="drop") %>%
  mutate(Mean_CEI = Sum_GHG / Sum_Catch) %>% filter(is.finite(Mean_CEI))
df_bivar <- bi_class(df_bivar_base, x = Sum_Catch, y = Mean_CEI, style = "quantile", dim = 3)

# ==============================================================================
# 5. Extremely tight theme (A,B,C With ocean blue; D Pure White)
# ==============================================================================
theme_common <- theme_minimal(base_size = 12) +
  theme(
    plot.background = element_rect(fill = "transparent", color = NA),
    panel.grid = element_blank(),
    panel.border = element_rect(color = "black", fill = NA, size = 0.5),
    strip.background = element_blank(),
    strip.text = element_text(face = "bold", size = 10),
    axis.text = element_text(size = 5),
    axis.title = element_blank(),
    plot.margin = margin(-2, 5, -2, 5, unit = "pt")
  )

theme_map <- theme_common + theme(panel.background = element_rect(fill = "#d6eaf8", color = NA))
theme_chart <- theme_common + theme(panel.background = element_blank())

# ==============================================================================
# 6. Rendering sub-map parts
# ==============================================================================

# --- A & B: Delta Maps ---
create_p <- function(data, metric, lim, tit) {
  ggplot(data) +
    geom_tile(aes(x = Lon, y = Lat, fill = .data[[metric]], width = Grid_Size, height = Grid_Size)) +
    geom_sf(data = world, inherit.aes = FALSE, fill = "gray85", color = "gray50", size = 0.1) +
    coord_sf(crs = 4326, expand = FALSE, xlim = c(-160, 160), ylim = c(-60, 60)) +
    facet_grid(Gear ~ Species) + 
    scale_fill_gradient2(low = "#053061", mid = "white", high = "#67001F", limits = c(-lim, lim), oob = scales::squish, name = tit) +
    theme_map
}

p_a <- create_p(df_delta, "Delta_GHG", lim_ghg, "Δ GHG") + theme(axis.text.x = element_blank())
p_b <- create_p(df_delta, "Delta_CEI", lim_cei, "Δ CEI") + theme(axis.text.x = element_blank(), strip.text.x = element_blank())

# --- C: Double-variable diagram ---
p_c <- ggplot(df_bivar) +
  geom_tile(aes(x = Lon, y = Lat, fill = bi_class, width = Grid_Size, height = Grid_Size), show.legend = FALSE) +
  geom_sf(data = world, inherit.aes = FALSE, fill = "gray85", color = "gray50", size = 0.1) +
  bi_scale_fill(pal = "DkViolet", dim = 3) +
  coord_sf(crs = 4326, expand = FALSE, xlim = c(-160, 160), ylim = c(-60, 60)) +
  facet_grid(Gear ~ Species) + 
  labs(x = "Longitude") + theme_map + 
  theme(strip.text.x = element_blank(), axis.title.x = element_text(size = 9, margin = margin(t=2)))

# --- D: RFMO Share ---
df_rfmo <- df_clean %>% filter(Organization %in% c("CCSBT", "IATTC", "ICCAT", "IOTC", "WCPFC")) %>%
  group_by(Era_Binary, Gear, Species, Organization) %>% summarise(Total_GHG = sum(Species_GHG, na.rm=TRUE), .groups="drop") %>%
  group_by(Era_Binary, Gear, Species) %>% mutate(GHG_Share = Total_GHG / sum(Total_GHG)) %>% ungroup()

p_d <- ggplot(df_rfmo, aes(x = Era_Binary, y = GHG_Share, fill = Organization)) +
  geom_bar(stat="identity", position="fill", width=0.8, color = "black", size = 0.1) +
  facet_grid(Gear ~ Species) +
  scale_y_continuous(labels = scales::percent_format(), expand = c(0, 0)) +
  scale_fill_brewer(palette = "Set2", name = "RFMO Share") +
  theme_chart + theme(strip.text.x = element_blank(), axis.text.x = element_text(angle = 45, hjust = 1))

# ==============================================================================
# 7. Legend extraction versus[Horizontal Row]Rehearsal
# ==============================================================================
cat("Rehearsal horizontal rows are being reordered for legends...\n")

leg_ghg <- get_legend(p_a + theme(legend.position = "bottom", legend.direction = "horizontal", legend.key.width = unit(1.2, "cm")))
leg_cei <- get_legend(p_b + theme(legend.position = "bottom", legend.direction = "horizontal", legend.key.width = unit(1.2, "cm")))
leg_rfmo <- get_legend(p_d + theme(legend.position = "bottom", legend.direction = "horizontal"))
leg_bi <- bi_legend(pal = "DkViolet", dim = 3, xlab = "Higher Catch", ylab = "Higher CEI", size = 10) +
          theme(plot.background = element_blank(), panel.background = element_blank())

p_legend_row <- plot_grid(
  leg_ghg, leg_cei, leg_rfmo, leg_bi,
  nrow = 1, rel_widths = c(1, 1, 1.2, 0.8), align = "h"
)

# ==============================================================================
# 8. Final assembly output
# ==============================================================================
p_main <- (p_a / p_b / p_c / p_d) + 
  plot_layout(heights = c(1, 1, 1, 0.6)) +
  plot_annotation(tag_levels = 'a', tag_prefix = '(', tag_suffix = ')') & 
  theme(legend.position = "none") 

p_final <- wrap_elements(p_main) / p_legend_row + 
  plot_layout(heights = c(25, 3))

ggsave("MainText_Fig2_Bilinear_Ultimate.png", plot = p_final, width = 14, height = 11, dpi = 900, bg = "transparent")
ggsave("MainText_Fig2_Bilinear_Ultimate.pdf", plot = p_final, width = 14, height = 11, bg = "transparent")

cat("Were done！bilinear grid resampling with the correspondence dictionary is complete. \n")