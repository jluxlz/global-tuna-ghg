# ==============================================================================
# 1. Load the necessary packages
# ==============================================================================
# Run if the package is missing: install.packages(c("tidyverse", "viridis", "sf", "rnaturalearth", "rnaturalearthdata", "sp", "gstat", "scales"))
library(tidyverse)
library(viridis)
library(sf)
library(rnaturalearth)
library(rnaturalearthdata)
library(sp)
library(gstat)
library(scales) # Provision pseudo_log_trans Waiting for advanced scale and logarithmic variable

# ==============================================================================
# 2. Get a global true base map and data cleansing
# ==============================================================================
cat("Loading base maps and cleaning data...\n")
world <- ne_countries(scale = "medium", returnclass = "sf")

df <- read_csv("Table1_Catch_with_Grid_GHG_CEI.csv", show_col_types = FALSE)

df_clean <- df %>%
  filter(Gear %in% c("PS", "LL"), Total_Catch >= 1) %>%
  # Include All 5 A species
  select(Year, Lat, Lon, Gear, SKJ_Tonnes, BET_Tonnes, YFT_Tonnes, ALB_Tonnes, SBT_Tonnes,
         Total_Catch, GHG_emissions_median, Grid_CEI_median) %>%
  pivot_longer(
    cols = c(SKJ_Tonnes, BET_Tonnes, YFT_Tonnes, ALB_Tonnes, SBT_Tonnes),
    names_to = "Species",
    values_to = "Catch"
  ) %>%
  # Clear species names, Make it simpler on the chart
  mutate(Species = str_replace(Species, "_Tonnes", "")) %>%
  filter(Catch >= 0.1) %>%
  mutate(Species_GHG = GHG_emissions_median * (Catch / Total_Catch))

# ==============================================================================
# 3. Defines the maximum range of global legends to calculate functions
# ==============================================================================
calc_limit <- function(data, group_cols, metric) {
  if (metric == "GHG") {
    agg <- data %>% group_by(across(all_of(c("Year", "Lon", "Lat", group_cols)))) %>%
      summarise(Val = sum(Species_GHG, na.rm=TRUE), .groups="drop")
  } else {
    agg <- data %>% group_by(across(all_of(c("Year", "Lon", "Lat", group_cols)))) %>%
      summarise(Val = mean(Grid_CEI_median, na.rm=TRUE), .groups="drop")
  }
  # Use 98% Number of places as the upper limit of the colour bar, Fit back logarithms, Its a good one
  return(quantile(agg$Val, probs = 0.98, na.rm = TRUE))
}

cat("Calculating global polar values in dimensions...\n")
limits <- list(
  GHG_Combined = calc_limit(df_clean, c("Gear", "Species"), "GHG"),
  CEI_Combined = calc_limit(df_clean, c("Gear", "Species"), "CEI"),
  GHG_Species  = calc_limit(df_clean, "Species", "GHG"),
  CEI_Species  = calc_limit(df_clean, "Species", "CEI"),
  GHG_Gear     = calc_limit(df_clean, "Gear", "GHG"),
  CEI_Gear     = calc_limit(df_clean, "Gear", "CEI")
)

# ==============================================================================
# 4. set the interpolation grid and output directory
# ==============================================================================
grid_res <- 1 
pred_grid <- expand.grid(Lon = seq(-180, 180, by = grid_res), Lat = seq(-80, 80, by = grid_res))
coordinates(pred_grid) <- ~Lon+Lat
gridded(pred_grid) <- TRUE

output_dir <- "Yearly_GIS_IDW_Heatmaps"
dir.create(output_dir, showWarnings = FALSE)

# ==============================================================================
# 5. Core Drawing Plant Functions (aggregate downsampled data, IDW interpolation and stepped logarithmic plotting)
# ==============================================================================
generate_plot <- function(data, group_cols, metric, limit_max, title_prefix, file_prefix, y) {
  
  # 1. Drop Samples/Aggregation
  if (metric == "GHG") {
    agg_data <- data %>% group_by(across(all_of(c("Lon", "Lat", group_cols)))) %>%
      summarise(Val = sum(Species_GHG, na.rm=TRUE), .groups="drop")
  } else {
    agg_data <- data %>% group_by(across(all_of(c("Lon", "Lat", group_cols)))) %>%
      summarise(Val = mean(Grid_CEI_median, na.rm=TRUE), .groups="drop")
  }
  
  combos <- agg_data %>% distinct(across(all_of(group_cols)))
  idw_list <- list()
  
  # 2. Plug value through a combination
  for(i in 1:nrow(combos)) {
    sub_df <- agg_data
    for(col in group_cols) {
      sub_df <- sub_df %>% filter(.data[[col]] == combos[[col]][i])
    }
    
    if(nrow(sub_df) >= 4) {
      sp_pts <- sub_df
      coordinates(sp_pts) <- ~Lon+Lat
      tryCatch({
        # [Psychic optimisation]: Raise the penalty for distance reduction idp = 3.5
        idw_res <- idw(Val ~ 1, locations = sp_pts, newdata = pred_grid, idp = 3.5, maxdist = 10, debug.level = 0)
        res_df <- as.data.frame(idw_res) %>% select(Lon, Lat, var1.pred)
        
        # [Force zero]: No fishing area and very small negative error 0, ♪ In the blue of the ocean ♪
        res_df$var1.pred[is.na(res_df$var1.pred)] <- 0
        res_df$var1.pred[res_df$var1.pred < 0] <- 0
        
        for(col in group_cols) { res_df[[col]] <- combos[[col]][i] }
        idw_list[[length(idw_list) + 1]] <- res_df
      }, error = function(e) {})
    }
  }
  
  df_smooth <- bind_rows(idw_list)
  if (nrow(df_smooth) == 0) return(NULL)
  
  # 3. Build ggplot
  p <- ggplot(data = df_smooth) +
    geom_raster(aes(x = Lon, y = Lat, fill = var1.pred), interpolate = TRUE) +
    geom_sf(data = world, inherit.aes = FALSE, fill = "#e5e5e5", color = "gray40", size = 0.2) +
    coord_sf(crs = 4326, expand = FALSE, xlim = c(-180, 180), ylim = c(-80, 80))
  
  # Differential Logic
  if (length(group_cols) == 2) {
    p <- p + facet_grid(Gear ~ Species)
  } else if (group_cols[1] == "Species") {
    p <- p + facet_wrap(~ Species, ncol = 3)
  } else if (group_cols[1] == "Gear") {
    p <- p + facet_wrap(~ Gear, ncol = 2)
  }
  
  legend_title <- ifelse(metric == "GHG", "GHG Emissions\n(Tonnes)", "Grid CEI")
  
  # [The ultimate anti-panic design]: Staircase separated from color belts + Pseudo logarithmic Variation
  p <- p + scale_fill_stepsn(
    colors = c("#a6bddb", "#abd9e9", "#e0f3f8", "#ffffbf", "#fdae61", "#f46d43", "#d73027", "#a50026"),
    trans = pseudo_log_trans(sigma = 1, base = 10),
    breaks = c(1, 10, 100, 1000, 10000, 50000, 100000), # Scatter step scale
    limits = c(0, limit_max),
    oob = scales::squish,
    na.value = "#a6bddb",
    name = legend_title,
    guide = guide_colorsteps(even.steps = FALSE, show.limits = TRUE, title.position = "top", barwidth = unit(10, "cm"))
  ) +
    labs(title = paste(title_prefix, "-", y), x = "Longitude", y = "Latitude") +
    theme_minimal() +
    theme(
      panel.background = element_rect(fill = "#a6bddb", color = NA), # Ocean Bottom Blue
      panel.grid.major = element_line(color = "white", linetype = "dashed", size = 0.3),
      panel.border = element_rect(color = "black", fill = NA, size = 0.5),
      strip.text = element_text(size = 12, face = "bold"),
      strip.background = element_rect(fill = "gray90", color = "black", size = 0.5),
      legend.position = "bottom"
    )
  
  ggsave(file.path(output_dir, paste0(file_prefix, "_", y, ".png")), plot = p, width = 16, height = 9, dpi = 300)
}

# ==============================================================================
# 6. Recycled by year
# ==============================================================================
years <- sort(unique(df_clean$Year))

for (y in years) {
  df_year <- df_clean %>% filter(Year == y)
  if (nrow(df_year) == 0) next
  cat(sprintf("\n--- Processing and Generation Year: %d Charts and charts ---\n", y))
  
  # Category 1: Combine (Gear x Species)
  generate_plot(df_year, c("Gear", "Species"), "GHG", limits$GHG_Combined, "Combined GHG Emissions", "GHG_Combined", y)
  generate_plot(df_year, c("Gear", "Species"), "CEI", limits$CEI_Combined, "Combined Grid CEI", "CEI_Combined", y)
  
  # Category 2: Individually drawn species (Press only Species Aggregation)
  generate_plot(df_year, "Species", "GHG", limits$GHG_Species, "GHG Emissions by Species", "GHG_Species", y)
  generate_plot(df_year, "Species", "CEI", limits$CEI_Species, "Grid CEI by Species", "CEI_Species", y)
  
  # Category 3: Networks to draw separately (Press only Gear Aggregation)
  generate_plot(df_year, "Gear", "GHG", limits$GHG_Gear, "GHG Emissions by Gear", "GHG_Gear", y)
  generate_plot(df_year, "Gear", "CEI", limits$CEI_Gear, "Grid CEI by Gear", "CEI_Gear", y)
  
  cat("  -> Year", y, "of 6 All maps are generated. \n")
}

cat("\n Congratulations！Different dimensions of all years GIS The map has been successfully generated！\n")