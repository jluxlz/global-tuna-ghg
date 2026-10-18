# ==============================================================================
# 1. Load the necessary packages
# ==============================================================================
library(tidyverse)
library(sf)
library(rnaturalearth)
library(rnaturalearthdata)
library(sp)
library(gstat)
library(scales)
library(svglite) 
library(RColorBrewer) 

# ==============================================================================
# 2. Get a bottom chart, Data cleansing with[Times(Era)Division]
# ==============================================================================
cat("Loading base maps and cleaning data...\n")
world <- ne_countries(scale = "medium", returnclass = "sf")

df <- read_csv("Table1_Catch_with_Grid_GHG_CEI.csv", show_col_types = FALSE)

df_clean <- df %>%
  filter(Gear %in% c("PS", "LL"), Total_Catch > 0) %>%
  select(Year, Lat, Lon, Gear, SKJ_Tonnes, BET_Tonnes, YFT_Tonnes, ALB_Tonnes, SBT_Tonnes,
         Total_Catch, GHG_emissions_median, Grid_CEI_median) %>%
  pivot_longer(
    cols = c(SKJ_Tonnes, BET_Tonnes, YFT_Tonnes, ALB_Tonnes, SBT_Tonnes),
    names_to = "Species",
    values_to = "Catch"
  ) %>%
  mutate(Species = str_replace(Species, "_Tonnes", "")) %>%
  filter(Catch > 0) %>% 
  mutate(Species_GHG = GHG_emissions_median * (Catch / Total_Catch)) %>%
  mutate(Era = case_when(
    Year <= 2000 ~ "Pre-2000",
    Year >= 2001 & Year <= 2010 ~ "2001-2010",
    Year >= 2011 ~ "2011-2024"
  ))

# ==============================================================================
# 3. Builds a full-arranged frame and calculates the average
# ==============================================================================
cat("Calculating average spatial distribution over historical periods...\n")
# We dont need all the arrangements here, generated within the interpolation function
df_era_agg <- df_clean %>%
  group_by(Era, Lon, Lat, Gear, Species) %>%
  summarise(
    Mean_GHG = mean(Species_GHG, na.rm = TRUE),
    Mean_CEI = mean(Grid_CEI_median, na.rm = TRUE),
    .groups = "drop"
  )

max_ghg <- quantile(df_era_agg$Mean_GHG, probs = 0.98, na.rm = TRUE)
max_cei <- quantile(df_era_agg$Mean_CEI, probs = 0.98, na.rm = TRUE)

# ==============================================================================
# 4. spatial interpolation (IDW) and[Its a complete fix]
# ==============================================================================
grid_res <- 1 
base_grid_df <- expand.grid(Lon = seq(-180, 180, by = grid_res), Lat = seq(-80, 80, by = grid_res))
pred_grid <- base_grid_df
coordinates(pred_grid) <- ~Lon+Lat
gridded(pred_grid) <- TRUE

run_idw_smoothing <- function(data, metric_col) {
  # [Key Changes]: No longer only use available data combos, Its about forcing all possible combinations
  # Make sure even 0 Data Panel, Theyll be assigned a transparent layer
  all_eras <- c("Pre-2000", "2001-2010", "2011-2024")
  all_gears <- c("LL", "PS")
  all_species <- c("ALB", "BET", "SBT", "SKJ", "YFT")
  full_combos <- expand.grid(Era = all_eras, Gear = all_gears, Species = all_species, stringsAsFactors = FALSE)
  
  idw_list <- list()
  
  for(i in 1:nrow(full_combos)) {
    sub_df <- data %>% filter(Era == full_combos$Era[i], Gear == full_combos$Gear[i], Species == full_combos$Species[i])
    
    # Scene 1: Data Point >= 4 One, Execute normal IDW
    if(nrow(sub_df) >= 4) {
      sp_pts <- sub_df %>% rename(Val = all_of(metric_col))
      coordinates(sp_pts) <- ~Lon+Lat
      
      tryCatch({
        idw_res <- idw(Val ~ 1, locations = sp_pts, newdata = pred_grid, idp = 3.5, maxdist = 10, debug.level = 0)
        res_df <- as.data.frame(idw_res) %>% select(Lon, Lat, var1.pred)
        res_df$var1.pred[is.na(res_df$var1.pred)] <- 0
        res_df$var1.pred[res_df$var1.pred < 0] <- 0
        
        res_df$Era <- full_combos$Era[i]
        res_df$Gear <- full_combos$Gear[i]
        res_df$Species <- full_combos$Species[i]
        idw_list[[length(idw_list) + 1]] <- res_df
      }, error = function(e) {})
      
    # Scene 2: Extremely isolated (Like 1-3 A point) , Visual Magnifier
    } else if (nrow(sub_df) > 0) {
      res_df <- base_grid_df
      res_df$var1.pred <- 0 
      
      for (j in 1:nrow(sub_df)) {
         lon_base <- sub_df$Lon[j]
         lat_base <- sub_df$Lat[j]
         val <- sub_df[[metric_col]][j]
         res_df <- res_df %>% mutate(var1.pred = ifelse(abs(Lon - lon_base) <= 2 & abs(Lat - lat_base) <= 2, val, var1.pred))
      }
      res_df$Era <- full_combos$Era[i]
      res_df$Gear <- full_combos$Gear[i]
      res_df$Species <- full_combos$Species[i]
      idw_list[[length(idw_list) + 1]] <- res_df
      
    # Scene 3: [Its all new]Theres no data at all (Like 2001-2010 SBT PS) , Output Pure 0 Grid
    } else {
      res_df <- base_grid_df
      res_df$var1.pred <- 0 # Make All 0, Im going to put it in #d6eaf8 Ocean background colour
      res_df$Era <- full_combos$Era[i]
      res_df$Gear <- full_combos$Gear[i]
      res_df$Species <- full_combos$Species[i]
      idw_list[[length(idw_list) + 1]] <- res_df
    }
  }
  return(bind_rows(idw_list))
}

cat("performing spatial interpolation (Include global blanks)...\n")
df_ghg_smooth <- run_idw_smoothing(df_era_agg, "Mean_GHG")
df_cei_smooth <- run_idw_smoothing(df_era_agg, "Mean_CEI")

# ==============================================================================
# 5. Core Large Chart Generating Plant
# ==============================================================================
custom_palette <- rev(brewer.pal(11, "Spectral"))

create_master_plot <- function(data, max_limit, title, legend_title) {
  
  data$Era <- factor(data$Era, levels = c("Pre-2000", "2001-2010", "2011-2024"))
  
  p <- ggplot(data = data) +
    geom_raster(aes(x = Lon, y = Lat, fill = var1.pred), interpolate = TRUE) +
    geom_sf(data = world, inherit.aes = FALSE, fill = "gray85", color = "gray50", size = 0.2) +
    coord_sf(crs = 4326, expand = FALSE, xlim = c(-160, 160), ylim = c(-60, 60)) +
    
    scale_x_continuous(breaks = c(-120, -60, 0, 60, 120)) +
    scale_y_continuous(breaks = c(-40, 0, 40)) +
    
    facet_grid(Era + Gear ~ Species) + 
    
    scale_fill_gradientn(
      colors = custom_palette,
      trans = pseudo_log_trans(sigma = 1, base = 10),
      limits = c(0, max_limit),
      breaks = c(1, 10, 100, 1000, 10000, 100000), 
      labels = scales::comma,
      oob = scales::squish,
      na.value = "transparent",
      name = legend_title,
      guide = guide_colorbar(barwidth = unit(16, "cm"), barheight = unit(0.5, "cm"), title.position = "top", title.hjust = 0.5)
    ) +
    labs(title = title, x = "Longitude", y = "Latitude") +
    theme_minimal(base_size = 12) +
    theme(
      panel.background = element_rect(fill = "#d6eaf8", color = NA), 
      panel.grid.major = element_blank(), 
      panel.grid.minor = element_blank(),
      panel.border = element_rect(color = "black", fill = NA, size = 0.6),
      strip.text = element_text(size = 11, face = "bold", color = "black"),
      strip.background = element_rect(fill = "gray90", color = "black", size = 0.5),
      axis.text = element_text(size = 8),
      axis.text.x = element_text(angle = 45, hjust = 1),
      legend.position = "bottom",
      legend.text = element_text(size = 10),
      plot.title = element_text(size = 18, face = "bold", hjust = 0.5, margin = margin(b = 15))
    )
  return(p)
}

# ==============================================================================
# 6. Drawing and Output
# ==============================================================================
cat("Drawing charts and output files...\n")

p_ghg <- create_master_plot(df_ghg_smooth, max_ghg, "Global Decadal Evolution of GHG Emissions by Gear and Species", "GHG Emissions (Tonnes/Year)")
ggsave("Master_Map_GHG_Evolution.pdf", plot = p_ghg, width = 18, height = 12, dpi = 600)
ggsave("Master_Map_GHG_Evolution.svg", plot = p_ghg, device = "svg", width = 18, height = 12)
ggsave("Master_Map_GHG_Evolution.png", plot = p_ghg, width = 18, height = 12, dpi = 900)

p_cei <- create_master_plot(df_cei_smooth, max_cei, "Global Decadal Evolution of Grid CEI by Gear and Species", "Grid CEI (kg CO2e/kg)")
ggsave("Master_Map_CEI_Evolution.pdf", plot = p_cei, width = 18, height = 12, dpi = 600)
ggsave("Master_Map_CEI_Evolution.svg", plot = p_cei, device = "svg", width = 18, height = 12)
ggsave("Master_Map_CEI_Evolution.png", plot = p_cei, width = 18, height = 12, dpi = 900)

cat("\n The missions a perfect one！All blank faults have been filled by the blue ocean. \n")