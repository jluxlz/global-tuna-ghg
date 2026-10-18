# Load Core Package
library(tidyverse)
library(ggplot2)
library(scales)
library(svglite)  # For high quality output SVG

# ==========================================
# 0. Data reading and academic theme setting
# ==========================================
# Read Data
df <- read_csv("Table2_Species_CEI_Timeseries.csv")

# Customize classic academic themes
theme_academic <- function() {
  theme_classic(base_size = 13, base_family = "sans") +
    theme(
      panel.border = element_rect(color = "black", fill = NA, linewidth = 1),
      axis.text = element_text(color = "black"),
      axis.title = element_text(color = "black", face = "bold"),
      axis.ticks = element_line(color = "black"),
      strip.background = element_rect(fill = "grey95", color = "black", linewidth = 1),
      strip.text = element_text(face = "bold", size = 13),
      legend.position = "bottom",
      legend.title = element_text(face = "bold"),
      panel.grid.major.y = element_line(color = "grey90", linetype = "dashed", linewidth = 0.5)
    )
}

gear_colors <- c("LL" = "#E64B35", "PS" = "#4DBBD5", "ALL" = "#00A087")


# ==========================================
# 1. Figure A: Long-term carbon emission intensity evolution of species
# ==========================================
df_trend <- df %>%
  filter(Year >= 1970, Gear %in% c("LL", "PS"))

p1 <- ggplot(df_trend, aes(x = Year)) +
  geom_ribbon(aes(ymin = CEI_min, ymax = CEI_max, fill = Gear), alpha = 0.25) +
  geom_line(aes(y = CEI_median, color = Gear), linewidth = 0.5) +
  facet_wrap(~ Species, scales = "free_y", ncol = 3) +
  
  # ======= Restoring a stable writing =======
  scale_y_log10(
    breaks = trans_breaks("log10", function(x) 10^x),
    labels = trans_format("log10", math_format(10^.x)),
    
    # Just relax a little bit 1e-2, Lets get the early values straight
    # If you still think its more square,, You can keep it small, Like 1e-3
    limits = c(1e-2, NA), 
    
    # Restore squish: Below 1e-2 ♪ The extreme low-value beat at the bottom ♪, The line of guarantees is not up and running Y Axes
    oob = squish 
  ) +
  # ============================
  
  scale_color_manual(values = gear_colors) +
  scale_fill_manual(values = gear_colors) +
  scale_x_continuous(breaks = seq(1970, 2020, by = 10)) +
  labs(
    x = "Year",
    y = expression(bold(Carbon~Emission~Intensity~(kg~CO[2]*e/kg))), 
    color = "Gear Type",
    fill = "Gear Type"
  ) +
  theme_academic() +
  theme(panel.spacing = unit(1.5, "lines"))

# --- Save simultaneously Figure A of PDF and SVG ---
ggsave("Fig_A_CEI_Timeseries.pdf", plot = p1, width = 12, height = 7, dpi = 900)
ggsave("Fig_A_CEI_Timeseries.svg", plot = p1, device = "svg", width = 12, height = 7)


# ==========================================
# 2. Figure B: Global profile for the last 10 years
# ==========================================
df_recent <- df %>%
  filter(Year >= 2015) %>%
  group_by(Species, Gear) %>%
  summarise(
    mean_med = mean(CEI_median, na.rm = TRUE),
    mean_min = mean(CEI_min, na.rm = TRUE),
    mean_max = mean(CEI_max, na.rm = TRUE),
    .groups = "drop"
  )

p2 <- ggplot(df_recent, aes(x = Species, y = mean_med, fill = Gear)) +
  geom_bar(stat = "identity", position = position_dodge(width = 0.8), 
           width = 0.7, color = "black", linewidth = 0.4) +
  geom_errorbar(aes(ymin = mean_min, ymax = mean_max),
                position = position_dodge(width = 0.8), width = 0.25, linewidth = 0.8) +
                
  geom_text(aes(y = mean_max, label = sprintf("%.1f", mean_med)), 
            position = position_dodge(width = 0.8), 
            vjust = -0.5,  
            size = 3.5, 
            fontface = "bold",
            color = "black") +

  scale_fill_manual(values = gear_colors) +
  
  scale_y_continuous(trans = "log10", 
                     breaks = trans_breaks("log10", function(x) 10^x),
                     labels = trans_format("log10", math_format(10^.x)),
                     expand = expansion(mult = c(0, 0.3))) +
  labs(
    x = "Target Species",
    y = expression(bold(Recent~CEI~(kg~CO[2]*e/kg)~"["*Log[10]~Scale*"]")),
    fill = "Gear Type"
  ) +
  theme_academic()

# --- Save simultaneously Figure B of PDF and SVG ---
ggsave("Fig_B_Recent_Decade_Barplot.pdf", plot = p2, width = 9, height = 6, dpi = 900)
ggsave("Fig_B_Recent_Decade_Barplot.svg", plot = p2, device = "svg", width = 9, height = 6)
