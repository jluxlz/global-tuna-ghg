# ==============================================================================
# 0. Load necessary packages and base maps
# ==============================================================================
library(tidyverse)
library(sf)
library(rnaturalearth)
library(rnaturalearthdata)
library(scales)
library(RColorBrewer) 
library(patchwork)
library(ggtext)

cat("Loading basecharts...\n")
world <- ne_countries(scale = "medium", returnclass = "sf")

# ==============================================================================
# 1. Raw data reading and preliminary cleansing
# ==============================================================================
cat("Reading and cleaning raw data...\n")
df_raw <- read_csv("Table1_Catch_with_Grid_GHG_CEI.csv", show_col_types = FALSE) %>%
  # Were gonna filter it out Unknown, Clear Unusual Values
  filter(Gear %in% c("PS", "LL"), Total_Catch > 0, squaretypecode != "Unknown") %>%
  pivot_longer(
    cols = c(SKJ_Tonnes, BET_Tonnes, YFT_Tonnes, ALB_Tonnes, SBT_Tonnes),
    names_to = "Species", values_to = "Catch"
  ) %>%
  mutate(Species = str_replace(Species, "_Tonnes", "")) %>%
  filter(Catch > 0, !is.na(GHG_emissions_median), GHG_emissions_median > 0) %>% 
  # [Core changes]: _Other Organiser 1950-2024 Between, Prevention of transborder data interference
  filter(Year >= 1950 & Year <= 2024) %>% 
  mutate(
    Species_GHG = GHG_emissions_median * (Catch / Total_Catch),
    # [Core changes]: Times(3 Phase) - Use of extreme fairness 25 Year equivalency cut！
    Era = case_when(
      Year >= 1950 & Year <= 1974 ~ "1950-1974",
      Year >= 1975 & Year <= 1999 ~ "1975-1999",
      Year >= 2000 & Year <= 2024 ~ "2000-2024"
    )
  )

# ==============================================================================
# 2. Construct a full-dimensional grid space heavy dictionary (bilinear interpolation)
# ==============================================================================
cat("Constructing bilinear grid downscale dictionary...\n")
generate_weights <- function(lon_span, lat_span, code_name) {
  lon_offsets <- seq(-floor((lon_span-1)/2), floor(lon_span/2), by = 1)
  lat_offsets <- seq(-floor((lat_span-1)/2), floor(lat_span/2), by = 1)
  
  expand_grid(lon_off = lon_offsets, lat_off = lat_offsets) %>%
    mutate(
      weight_x = 1 - abs(lon_off) / ((lon_span + 1) / 2),
      weight_y = 1 - abs(lat_off) / ((lat_span + 1) / 2),
      weight_raw = weight_x * weight_y,
      weight = weight_raw / sum(weight_raw), # Normalize, Absolute mass constant
      square_type = code_name
    ) %>%
    select(square_type, lon_off, lat_off, weight)
}

# Dictionary Key Strictly matches the string in your table
dict_1x1   <- generate_weights(1, 1, "1x1")
dict_5x5   <- generate_weights(5, 5, "5x5")
dict_10x10 <- generate_weights(10, 10, "10x10")
dict_5x10  <- generate_weights(10, 5, "5x10") 
dict_10x20 <- generate_weights(20, 10, "10x20")

weight_dictionary <- bind_rows(dict_1x1, dict_5x5, dict_10x10, dict_5x10, dict_10x20)

# ==============================================================================
# 3. Extreme downscale processing (Direct Join Match + Grid Alignment)
# ==============================================================================
cat("Applying downscale mapping and forcing alignment of the half-degree grid...\n")

df_clean <- df_raw %>%
  # Take it squaretypecode The field goes to the dictionary for direct exact matches
  inner_join(weight_dictionary, by = c("squaretypecode" = "square_type")) %>%
  mutate(
    Lon = Lon + lon_off,            
    Lat = Lat + lat_off,
    Catch = Catch * weight,             
    Species_GHG = Species_GHG * weight  
  ) %>%
  # snap to the unique global half-degree cell centre, Destroy all overlaps and errors！
  mutate(
    Lon = floor(Lon) + 0.5,
    Lat = floor(Lat) + 0.5
  ) %>%
  # By New 3 Time reassembles
  group_by(Year, Era, Gear, Species, Lon, Lat) %>%
  summarise(
    Catch = sum(Catch, na.rm = TRUE), 
    Species_GHG = sum(Species_GHG, na.rm = TRUE), 
    .groups = "drop"
  )

# ==============================================================================
# 4. Indicators for statistical supplements (Mean Catch, Mean GHG, Mean CEI)
# ==============================================================================
era_years <- df_clean %>% group_by(Era) %>% summarise(N_Years = n_distinct(Year), .groups = "drop")

df_supp <- df_clean %>%
  group_by(Era, Lon, Lat, Gear, Species) %>%
  summarise(
    Sum_Catch = sum(Catch, na.rm = TRUE),
    Sum_GHG = sum(Species_GHG, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  left_join(era_years, by = "Era") %>%
  mutate(
    Mean_Catch = Sum_Catch / N_Years,
    Mean_GHG = Sum_GHG / N_Years,
    Mean_CEI = Sum_GHG / Sum_Catch,
    Grid_Size = 1.05 # Set As 1.05 ♪ A tiny spill ♪, Make tiles feel stronger, Secrecy gap
  ) %>% 
  filter(is.finite(Mean_CEI))

# [Core changes]: Update factor sorting Levels, Make sure the charts are dated
df_supp$Era <- factor(df_supp$Era, levels = c("1950-1974", "1975-1999", "2000-2024"))
df_supp$Gear <- factor(df_supp$Gear, levels = c("LL", "PS"))

# ==============================================================================
# 5. Supplementing the apogee theme and the universal drawing function (Restoring version)
# ==============================================================================
theme_map <- theme_minimal(base_size = 12) +
  theme(
    panel.background = element_rect(fill = "#d6eaf8", color = NA),
    panel.grid = element_blank(),
    panel.border = element_rect(color = "black", fill = NA, size = 0.5),
    strip.background = element_blank(), 
    strip.text = element_text(face = "bold", size = 11),
    axis.text = element_text(size = 6),
    legend.title = element_text(size = 10, face = "bold"),
    plot.margin = margin(2, 2, 2, 2, unit = "pt")
  )

create_supp_plot <- function(data, metric, min_lim, max_lim, custom_breaks, legend_title) {
  ggplot(data) +
    geom_tile(aes(x = Lon, y = Lat, fill = .data[[metric]], width = Grid_Size, height = Grid_Size)) +
    geom_sf(data = world, inherit.aes = FALSE, fill = "#fdf5e6", color = "gray70", size = 0.1) +
    coord_sf(crs = 4326, expand = FALSE, xlim = c(-160, 160), ylim = c(-60, 60)) +
    
    # [Black technology 1]: Yes labeller Injection HTML Styles, Force year to become 7pt Size
    facet_grid(Gear + Era ~ Species, 
               labeller = labeller(Era = as_labeller(c(
                 "1950-1974" = "<span style='font-size:7pt;'>1950-1974</span>", 
                 "1975-1999" = "<span style='font-size:7pt;'>1975-1999</span>", 
                 "2000-2024" = "<span style='font-size:7pt;'>2000-2024</span>"
               )))) + 
    
    scale_fill_gradientn(
      colors = rev(brewer.pal(11, "Spectral")),
      trans = "log10", 
      limits = c(min_lim, max_lim),
      breaks = custom_breaks, 
      labels = scales::comma, oob = scales::squish, na.value = "transparent", name = legend_title,
      guide = guide_colorbar(barwidth = unit(0.8, "cm"), barheight = unit(12, "cm"), title.position = "top")
    ) +
    labs(x = NULL, y = "Latitude") + 
    theme_map +
    theme(
      # Top species maintained 11 No. No
      strip.text.x = element_text(face = "bold", size = 11),
      
      # [Black technology 2]: Will element_text Replace with element_markdown, Jean ggplot2 Itll explain what we just wrote HTML
      strip.text.y = element_markdown(face = "bold", size = 11, margin = margin(l = 3, r = 3)),
      
      # Decreases the gap of legends
      legend.box.margin = margin(l = -5)
    )
}

# ==============================================================================
# 6. Generate three sub-pane and group (Restoring version)
# ==============================================================================
cat("Rendering map layer...\n")

max_c <- quantile(df_supp$Mean_Catch, 0.98, na.rm = TRUE)
max_g <- quantile(df_supp$Mean_GHG, 0.98, na.rm = TRUE)
max_i <- quantile(df_supp$Mean_CEI, 0.98, na.rm = TRUE)

p_a <- create_supp_plot(df_supp, "Mean_Catch", 1, max_c, c(1,10,100,1000,10000,100000), "Catch\n(Tonnes/Yr)") + 
       theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())

p_b <- create_supp_plot(df_supp, "Mean_GHG", 1, max_g, c(1,10,100,1000,10000,100000), "GHG\n(T CO2e/Yr)") + 
       theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())

p_c <- create_supp_plot(df_supp, "Mean_CEI", 0.1, max_i, c(0.1, 1, 3, 5, 10, 20), "CEI\n(kg CO2e/kg)") + 
       labs(x = "Longitude")

cat("In use patchwork Do the ultimate vertical spewing...\n")

p_combined <- (p_a / p_b / p_c) +
  plot_annotation(tag_levels = 'a', tag_prefix = '(', tag_suffix = ')') & 
  theme(plot.tag = element_text(size = 20, face = "bold", margin = margin(b = -5)))

# [Core repairs 2]: Adjust canvas scale！
# Take the originals width = 13 Zoom To 9.5, And force the extra white space to disappear, LL/PS Ill just suck it up
ggsave("Supp_Fig1_Downscaled_Combined_25Yrs.png", plot = p_combined, width = 13, height = 18, dpi = 900, bg = "white")
ggsave("Supp_Fig1_Downscaled_Combined_25Yrs.pdf", plot = p_combined, width = 13, height = 18, bg = "white")
library(svglite)
ggsave(filename = "Supp_Fig1_Downscaled_Combined_25Yrs.svg", 
       plot = p_combined, 
       width = 13, height = 18, 
       bg = "white",
       device = "svg")
cat("Were done！Year hide success, And the right tab and the legend are perfectly aligned to the group. \n")