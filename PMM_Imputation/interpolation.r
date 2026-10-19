# ==========================================
# 1. Load all necessary toolkits
# ==========================================
# If there is an uninstalled package, Please run first install.packages(c("tidyverse", "mice", "readxl", "writexl", "ggplot2", "patchwork"))
library(tidyverse)  # Data clean core
library(mice)       # PMM Multiple Plug Cores
library(readxl)     # Read Excel
library(writexl)    # Export Excel
library(ggplot2)    # Advanced Drawing
library(patchwork)  # Jigsaw

# ==========================================
# 2. Batch Read and Clean Data (Its done 0 Value issues + Auto Generate a tissue field)
# ==========================================
# Please replace the lower path with your storage xlsx Path to the real folder of the file
script_file <- sub("^--file=", "", grep("^--file=", commandArgs(), value=TRUE)[1])
folder_path <- file.path(dirname(dirname(normalizePath(script_file))), "extracted_vessel_data")
file_list <- list.files(path = folder_path, pattern = "\\.xlsx$", full.names = TRUE)

cat("Found it", length(file_list), "One Excel Documentation, Reading & & Spelling...\n")

# Make all read in plain text, And use the filename to generate it organization Fields
raw_data <- file_list %>%
  # set_names From the list of paths"Name"Set as File Name, Here map_dfr Automatically generates a column with filenames
  set_names(basename(.)) %>% 
  map_dfr(~ read_excel(.x, col_types = "text"), .id = "source_file") %>%
  mutate(
    # [Add]: Extract tissue name from file name
    # Methodology A (default) : Remove all the English letters in the filename (For example "2023_CCSBT Data.xlsx" -> "CCSBT") 
    organization = str_extract(source_file, "[A-Za-z]+") 
    
    # Methodology B (Alternatives) : If your file name is pure "CCSBT.xlsx", You can just remove the suffix as a tissue name, Just cancel the next line of comment: 
    # organization = str_remove(source_file, "\\.xlsx$")
  ) %>%
  relocate(organization) %>% # Put it on organization Move Fields to the Front of Tables (Its... its... its... its... its 1 Column) 
  select(-source_file)       # Delete as a transit source_file Original file name

clean_data <- raw_data %>%
  rename(
    Length_m = `Length(m)`,
    Tonnage_t = `Tonnage(t)`,
    Enginepower_kw = `Enginepower(kw)`
  ) %>%
  mutate(
    # Force to revert to the numeric type
    Length_m = as.numeric(Length_m),
    Tonnage_t = as.numeric(Tonnage_t),
    Enginepower_kw = as.numeric(Enginepower_kw)
  ) %>%
  mutate(
    # [Core repairs]: Take all the anomalies 0 Value, Force to return to the real missing value NA
    Length_m = na_if(Length_m, 0),
    Tonnage_t = na_if(Tonnage_t, 0),
    Enginepower_kw = na_if(Enginepower_kw, 0)
  )

# ==========================================
# 3. configure the one-way imputation rules
# ==========================================
impute_subset <- clean_data %>%
  select(Length_m, Tonnage_t, Enginepower_kw) 

# Initialization mice Configure (Dont run the model first, Extract only the settings matrix) 
init <- mice(impute_subset, maxit = 0)
meth <- init$method
pred <- init$predictorMatrix

# Rules A: Never intrude Length_m. Its empty, Just leave it empty. 
meth["Length_m"] <- ""  

# Rules B: Clears all default mutual predictions
pred[,] <- 0 

# Rules C: Only allowed Length_m Go ahead and predict it Enginepower_kw and Tonnage_t
pred["Enginepower_kw", "Length_m"] <- 1
pred["Tonnage_t", "Length_m"] <- 1

# ==========================================
# 4. Implementation PMM imputation
# ==========================================
cat("\n Start strict compliance Length -> Power/Tonnage The logic of interpolating (Generate 5 Parallel data sets)...\n")
# attention: Because of the ban on each other, Its gonna be a lot faster than before
imp_model <- mice(impute_subset, m = 5, method = meth, predictorMatrix = pred, maxit = 5, seed = 123)

# ==========================================
# 5. Draw and export the ultimate diagnostic puzzle: Density Chart + Scatter Diagram
# ==========================================
cat("\n Generating final diagnostic puzzles backstage (Density Chart + Scatter Diagram), Please wait...\n")

# reshape all imputation draws into long format
long_data <- complete(imp_model, action = "long", include = TRUE)
long_data$.imp <- as.factor(long_data$.imp)

# Customize the aesthetic: Let raw data(0)Use black thick lines, Insert Data(1-5)Use colour lines
line_colors <- c("0" = "black", "1" = "#E69F00", "2" = "#56B4E9", 
                 "3" = "#009E73", "4" = "#F0E442", "5" = "#CC79A7")
line_sizes <- c("0" = 1.2, "1" = 0.5, "2" = 0.5, "3" = 0.5, "4" = 0.5, "5" = 0.5)

# ------------------------------------------
# First Platoon: Density Chart (Density Plots)
# ------------------------------------------
d_length <- ggplot(long_data, aes(x = Length_m, color = .imp, size = .imp)) +
  geom_density(alpha = 0) + # alpha=0 Show only the lines, Do Not Fill Bottom Colour
  scale_color_manual(values = line_colors) +
  scale_size_manual(values = line_sizes) +
  theme_minimal() +
  labs(title = "Density: Length (m)", x = "Length (m)", y = "Density") +
  theme(legend.position = "none")

d_tonnage <- ggplot(long_data, aes(x = Tonnage_t, color = .imp, size = .imp)) +
  geom_density(alpha = 0) +
  scale_color_manual(values = line_colors) +
  scale_size_manual(values = line_sizes) +
  theme_minimal() +
  labs(title = "Density: Tonnage (t)", x = "Tonnage (t)", y = "") +
  theme(legend.position = "none")

d_power <- ggplot(long_data, aes(x = Enginepower_kw, color = .imp, size = .imp)) +
  geom_density(alpha = 0) +
  scale_color_manual(values = line_colors) +
  scale_size_manual(values = line_sizes) +
  theme_minimal() +
  labs(title = "Density: Engine Power (kw)", x = "Engine Power (kw)", y = "") +
  theme(legend.position = "none")

# ------------------------------------------
# Second row: Scatter Bands Chart (Strip Plots)
# ------------------------------------------
p_length <- ggplot(long_data, aes(x = .imp, y = Length_m, color = .imp)) +
  geom_jitter(width = 0.2, size = 0.1, alpha = 0.3) + 
  scale_color_manual(values = line_colors) +
  theme_minimal() +
  labs(title = "Strip: Length (m)", x = "Imputation Run (0=Observed)", y = "Length (m)") +
  theme(legend.position = "none")

p_tonnage <- ggplot(long_data, aes(x = .imp, y = Tonnage_t, color = .imp)) +
  geom_jitter(width = 0.2, size = 0.1, alpha = 0.3) +
  scale_color_manual(values = line_colors) +
  theme_minimal() +
  labs(title = "Strip: Tonnage (t)", x = "Imputation Run (0=Observed)", y = "Tonnage (t)") +
  theme(legend.position = "none")

p_power <- ggplot(long_data, aes(x = .imp, y = Enginepower_kw, color = .imp)) +
  geom_jitter(width = 0.2, size = 0.1, alpha = 0.3) +
  scale_color_manual(values = line_colors) +
  theme_minimal() +
  labs(title = "Strip: Engine Power (kw)", x = "Imputation Run (0=Observed)", y = "Engine Power (kw)") +
  theme(legend.position = "none")

# ------------------------------------------
# Core magic: Use patchwork Do top-down, right-and-left puzzles
# ------------------------------------------
combined_plot <- (d_length | d_tonnage | d_power) / (p_length | p_tonnage | p_power) +
  plot_annotation(
    title = "Comprehensive PMM Diagnostics: Density & Strip Plots",
    subtitle = "Top: Density distribution (Black=Observed, Colored=Imputed) | Bottom: Data points spread | Strict 1-way Imputation",
    theme = theme(plot.title = element_text(size = 18, face = "bold", hjust = 0.5),
                  plot.subtitle = element_text(size = 12, color = "gray30", hjust = 0.5))
  )

# ------------------------------------------
# Export to Super-Hinged-up
# ------------------------------------------
ggsave(filename = "Strict_Imputation_Ultimate_Diagnostics.png", 
       plot = combined_plot, width = 14, height = 10, dpi = 900)
cat(">>> The final diagnostic map has been generated: Strict_Imputation_Ultimate_Diagnostics.png\n")


library(svglite)
ggsave(filename = "Strict_Imputation_Ultimate_Diagnostics.svg", 
       plot = combined_plot, 
       width = 14, height = 10, 
       device = "svg")

# ==========================================
# 6. Generate Final File and Export As Excel
# ==========================================
cat("\n Embracing final data sheets and exporting them...\n")

# Extract first 1 completed imputed datasets
completed_subset <- complete(imp_model, action = 1)

# replace the corresponding source-table entries with imputed values, ♪ And keep ♪ organization When all other fields remain unchanged
final_data <- clean_data %>%
  mutate(
    Length_m = completed_subset$Length_m,
    Tonnage_t = completed_subset$Tonnage_t,
    Enginepower_kw = completed_subset$Enginepower_kw
  )

# Revert original listing with brackets
final_export <- final_data %>%
  rename(
    `Length(m)` = Length_m,
    `Tonnage(t)` = Tonnage_t,
    `Enginepower(kw)` = Enginepower_kw
  )

# Export as Final .xlsx Documentation
output_filename <- "Final_Strict_Imputed_Vessels.xlsx"
write_xlsx(final_export, output_filename)

cat(">>> Congratulations！Full process run. Final Data Saved As:", output_filename, "\n")
