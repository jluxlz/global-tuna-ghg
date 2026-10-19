# ==========================================
# 1. Load all necessary toolkits (Streamlined)
# ==========================================
# If there is an uninstalled package, Please run first install.packages(c("tidyverse", "mice", "readxl"))
library(tidyverse)  # Data clean core
library(mice)       # PMM Multiple Plug Cores
library(readxl)     # Read Excel

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
  set_names(basename(.)) %>% 
  map_dfr(~ read_excel(.x, col_types = "text"), .id = "source_file") %>%
  mutate(
    # Extract tissue name from file name
    organization = str_extract(source_file, "[A-Za-z]+") 
  ) %>%
  relocate(organization) %>% 
  select(-source_file)       

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
    # Core repairs: Take all the anomalies 0 Value, Force to return to the real missing value NA
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
# 4. Implementation PMM imputation (Generate 5 Parallel data sets)
# ==========================================
cat("\n Start strict compliance Length -> Power/Tonnage The logic of interpolating (Generate 5 Parallel data sets)...\n")
# attention: Because of the ban on each other, Its gonna be fast
imp_model <- mice(impute_subset, m = 5, method = meth, predictorMatrix = pred, maxit = 5, seed = 123)

# ==========================================
# 5. Recycle and Export 5 One CSV Documentation
# ==========================================
cat("\n Im putting it together 5 A parallel data set and export...\n")

for (i in 1:5) {
  # Extract first i completed imputed datasets
  completed_subset <- complete(imp_model, action = i)
  
  # replace the corresponding source-table entries with imputed values, ♪ And keep ♪ organization When all other fields remain unchanged
  final_data <- clean_data %>%
    mutate(
      Length_m = completed_subset$Length_m,
      Tonnage_t = completed_subset$Tonnage_t,
      Enginepower_kw = completed_subset$Enginepower_kw
    ) %>%
    rename( # Revert original listing with brackets, Alignment Python The habit of reading scripts
      `Length(m)` = Length_m,
      `Tonnage(t)` = Tonnage_t,
      `Enginepower(kw)` = Enginepower_kw
    )
  
  # Export As CSV Documentation
  output_filename <- paste0("Imputed_Vessels_PMM_", i, ".csv")
  write.csv(final_data, output_filename, row.names = FALSE, fileEncoding = "UTF-8")
  
  cat("Exported successfully:", output_filename, "\n")
}

cat(">>> Congratulations！Full process run. Please take this 5 One CSV File In Python Under Script Peer Directory, Start GSA Engine. \n")
