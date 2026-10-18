cran <- c("R2jags","RColorBrewer","biscale","coda","cowplot","dplyr","ggplot2","ggrepel","ggtext","gstat","gtable","mgcv","mice","patchwork","png","posterior","readxl","remotes","rnaturalearth","rnaturalearthdata","scales","sf","sp","svglite","tidyr","tidyverse","viridis","writexl")
install.packages(cran, repos="https://cloud.r-project.org")
# Install JAGS separately, then JABBA from its upstream repository.
if (!requireNamespace("remotes", quietly=TRUE)) install.packages("remotes")
remotes::install_github("jabbamodel/JABBA")
