# ==============================================================================
# 0. 加载必要的包与底图
# ==============================================================================
library(tidyverse)
library(sf)
library(rnaturalearth)
library(rnaturalearthdata)
library(scales)
library(RColorBrewer) 
library(patchwork)
library(ggtext)

cat("正在加载底图...\n")
world <- ne_countries(scale = "medium", returnclass = "sf")

# ==============================================================================
# 1. 原始数据读取与初步清洗
# ==============================================================================
cat("正在读取与清洗原生数据...\n")
df_raw <- read_csv("Table1_Catch_with_Grid_GHG_CEI.csv", show_col_types = FALSE) %>%
  # 果断过滤掉 Unknown，清理异常值
  filter(Gear %in% c("PS", "LL"), Total_Catch > 0, squaretypecode != "Unknown") %>%
  pivot_longer(
    cols = c(SKJ_Tonnes, BET_Tonnes, YFT_Tonnes, ALB_Tonnes, SBT_Tonnes),
    names_to = "Species", values_to = "Catch"
  ) %>%
  mutate(Species = str_replace(Species, "_Tonnes", "")) %>%
  filter(Catch > 0, !is.na(GHG_emissions_median), GHG_emissions_median > 0) %>% 
  # 【核心修改】：限定年份在 1950-2024 之间，防止越界数据干扰
  filter(Year >= 1950 & Year <= 2024) %>% 
  mutate(
    Species_GHG = GHG_emissions_median * (Catch / Total_Catch),
    # 【核心修改】：时代(3阶段) - 采用极其公平的 25 年等距切分！
    Era = case_when(
      Year >= 1950 & Year <= 1974 ~ "1950-1974",
      Year >= 1975 & Year <= 1999 ~ "1975-1999",
      Year >= 2000 & Year <= 2024 ~ "2000-2024"
    )
  )

# ==============================================================================
# 2. 构建全维度网格空间权重字典 (双线性插值)
# ==============================================================================
cat("正在构建双线性网格降尺度字典...\n")
generate_weights <- function(lon_span, lat_span, code_name) {
  lon_offsets <- seq(-floor((lon_span-1)/2), floor(lon_span/2), by = 1)
  lat_offsets <- seq(-floor((lat_span-1)/2), floor(lat_span/2), by = 1)
  
  expand_grid(lon_off = lon_offsets, lat_off = lat_offsets) %>%
    mutate(
      weight_x = 1 - abs(lon_off) / ((lon_span + 1) / 2),
      weight_y = 1 - abs(lat_off) / ((lat_span + 1) / 2),
      weight_raw = weight_x * weight_y,
      weight = weight_raw / sum(weight_raw), # 归一化，绝对质量守恒
      square_type = code_name
    ) %>%
    select(square_type, lon_off, lat_off, weight)
}

# 字典的 Key 严格匹配你表中的字符串
dict_1x1   <- generate_weights(1, 1, "1x1")
dict_5x5   <- generate_weights(5, 5, "5x5")
dict_10x10 <- generate_weights(10, 10, "10x10")
dict_5x10  <- generate_weights(10, 5, "5x10") 
dict_10x20 <- generate_weights(20, 10, "10x20")

weight_dictionary <- bind_rows(dict_1x1, dict_5x5, dict_10x10, dict_5x10, dict_10x20)

# ==============================================================================
# 3. 极速降尺度处理 (直接 Join 匹配 + 网格对齐)
# ==============================================================================
cat("正在应用降尺度映射并强制对齐半度网格...\n")

df_clean <- df_raw %>%
  # 拿 squaretypecode 字段去字典里直接精准匹配
  inner_join(weight_dictionary, by = c("squaretypecode" = "square_type")) %>%
  mutate(
    Lon = Lon + lon_off,            
    Lat = Lat + lat_off,
    Catch = Catch * weight,             
    Species_GHG = Species_GHG * weight  
  ) %>%
  # 吸附到全球唯一的半度中心点上，消灭一切重叠与错位！
  mutate(
    Lon = floor(Lon) + 0.5,
    Lat = floor(Lat) + 0.5
  ) %>%
  # 按照新的 3 个时代重新聚合
  group_by(Year, Era, Gear, Species, Lon, Lat) %>%
  summarise(
    Catch = sum(Catch, na.rm = TRUE), 
    Species_GHG = sum(Species_GHG, na.rm = TRUE), 
    .groups = "drop"
  )

# ==============================================================================
# 4. 统计补充图指标 (Mean Catch, Mean GHG, Mean CEI)
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
    Grid_Size = 1.05 # 设置为 1.05 的微小溢出，让瓷砖拼接感更强，无缝隙
  ) %>% 
  filter(is.finite(Mean_CEI))

# 【核心修改】：更新因子化排序的 Levels，确保出图顺序按年代先后
df_supp$Era <- factor(df_supp$Era, levels = c("1950-1974", "1975-1999", "2000-2024"))
df_supp$Gear <- factor(df_supp$Gear, levels = c("LL", "PS"))

# ==============================================================================
# 5. 补充图极致主题与通用绘图函数 (修复版)
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
    
    # 【黑科技 1】：在 labeller 中注入 HTML 样式，强制让年份变为 7pt 大小
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
      # 顶部物种保持 11 号
      strip.text.x = element_text(face = "bold", size = 11),
      
      # 【黑科技 2】：将 element_text 替换为 element_markdown，让 ggplot2 能够解析我们刚刚写的 HTML
      strip.text.y = element_markdown(face = "bold", size = 11, margin = margin(l = 3, r = 3)),
      
      # 减小图例空隙
      legend.box.margin = margin(l = -5)
    )
}

# ==============================================================================
# 6. 生成三个子面板并组合 (修复版)
# ==============================================================================
cat("正在渲染地图图层...\n")

max_c <- quantile(df_supp$Mean_Catch, 0.98, na.rm = TRUE)
max_g <- quantile(df_supp$Mean_GHG, 0.98, na.rm = TRUE)
max_i <- quantile(df_supp$Mean_CEI, 0.98, na.rm = TRUE)

p_a <- create_supp_plot(df_supp, "Mean_Catch", 1, max_c, c(1,10,100,1000,10000,100000), "Catch\n(Tonnes/Yr)") + 
       theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())

p_b <- create_supp_plot(df_supp, "Mean_GHG", 1, max_g, c(1,10,100,1000,10000,100000), "GHG\n(T CO2e/Yr)") + 
       theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())

p_c <- create_supp_plot(df_supp, "Mean_CEI", 0.1, max_i, c(0.1, 1, 3, 5, 10, 20), "CEI\n(kg CO2e/kg)") + 
       labs(x = "Longitude")

cat("正在使用 patchwork 进行终极纵向拼装...\n")

p_combined <- (p_a / p_b / p_c) +
  plot_annotation(tag_levels = 'a', tag_prefix = '(', tag_suffix = ')') & 
  theme(plot.tag = element_text(size = 20, face = "bold", margin = margin(b = -5)))

# 【核心修复 2】：调整画布比例！
# 把原本的 width = 13 缩减到 9.5，逼迫多余的白色空间消失，LL/PS自然就会吸附上去
ggsave("Supp_Fig1_Downscaled_Combined_25Yrs.png", plot = p_combined, width = 13, height = 18, dpi = 900, bg = "white")
ggsave("Supp_Fig1_Downscaled_Combined_25Yrs.pdf", plot = p_combined, width = 13, height = 18, bg = "white")
library(svglite)
ggsave(filename = "Supp_Fig1_Downscaled_Combined_25Yrs.svg", 
       plot = p_combined, 
       width = 13, height = 18, 
       bg = "white",
       device = "svg")
cat("大功告成！年份隐藏成功，且右侧标签与图例已完美贴合组图。\n")