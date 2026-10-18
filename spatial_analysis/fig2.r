# ==============================================================================
# 0. 前置与加载
# ==============================================================================
library(tidyverse)
library(sf)
library(rnaturalearth)
library(rnaturalearthdata)
library(scales)
library(RColorBrewer) 
library(patchwork)
library(biscale)
library(cowplot) # 用于精确提取和组合图例

cat("正在加载底图...\n")
world <- ne_countries(scale = "medium", returnclass = "sf")

# ==============================================================================
# 1. 原始数据读取与初步清洗 (加入过滤逻辑)
# ==============================================================================
df_raw <- read_csv("Table1_Catch_with_Grid_GHG_CEI.csv", show_col_types = FALSE) %>%
  # 【优化】：果断过滤掉 Unknown，清理异常值
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
# 2. 【终极架构优化】：构建空间权重查找表 (Lookup Table)
# ==============================================================================
cat("正在构建全维度网格空间权重字典...\n")

# 定义一个辅助函数：生成任意 N*M 网格的双线性插值权重
generate_weights <- function(lon_span, lat_span, code_name) {
  # 计算偏移量范围 (以整数经纬度为中心向外扩散)
  lon_offsets <- seq(-floor((lon_span-1)/2), floor(lon_span/2), by = 1)
  lat_offsets <- seq(-floor((lat_span-1)/2), floor(lat_span/2), by = 1)
  
  expand_grid(lon_off = lon_offsets, lat_off = lat_offsets) %>%
    mutate(
      # 动态计算双线性衰减分母 (保证边缘平滑)
      weight_x = 1 - abs(lon_off) / ((lon_span + 1) / 2),
      weight_y = 1 - abs(lat_off) / ((lat_span + 1) / 2),
      weight_raw = weight_x * weight_y,
      weight = weight_raw / sum(weight_raw), # 归一化，绝对保证质量守恒
      square_type = code_name
    ) %>%
    select(square_type, lon_off, lat_off, weight)
}

# 【核心修改】：字典的 Key 直接使用你数据里的原文字符串！
# 注意：国际渔业中 5x10 通常是 5度纬度 × 10度经度，因此 lat_span=5, lon_span=10
dict_1x1   <- generate_weights(lon_span = 1, lat_span = 1, code_name = "1x1")
dict_5x5   <- generate_weights(lon_span = 5, lat_span = 5, code_name = "5x5")
dict_10x10 <- generate_weights(lon_span = 10, lat_span = 10, code_name = "10x10")
dict_5x10  <- generate_weights(lon_span = 10, lat_span = 5, code_name = "5x10") 
dict_10x20 <- generate_weights(lon_span = 20, lat_span = 10, code_name = "10x20")

# 合并为一个无敌字典表
weight_dictionary <- bind_rows(dict_1x1, dict_5x5, dict_10x10, dict_5x10, dict_10x20)

# ==============================================================================
# 3. 极速降尺度处理 (直接 Join 匹配)
# ==============================================================================
cat("正在进行直接 Join 双线性降尺度...\n")

df_clean <- df_raw %>%
  # 【彻底简化】：不需要任何 case_when，直接拿你的 squaretypecode 字段去字典里匹配！
  inner_join(weight_dictionary, by = c("squaretypecode" = "square_type")) %>%
  mutate(
    Lon = Lon + lon_off,            
    Lat = Lat + lat_off,
    Catch = Catch * weight,             
    Species_GHG = Species_GHG * weight  
  ) %>%
  # 终极网格对齐 (Grid Snapping) - 锁定在全球统一的半度网格中心上
  mutate(
    Lon = floor(Lon) + 0.5,
    Lat = floor(Lat) + 0.5
  ) %>%
  # 同一 1x1 空间网格完美聚合
  group_by(Year, Era_Binary, Organization, Gear, Species, Lon, Lat) %>%
  summarise(
    Catch = sum(Catch, na.rm = TRUE), 
    Species_GHG = sum(Species_GHG, na.rm = TRUE), 
    .groups = "drop"
  ) %>%
  # 统一所有渲染出的网格视觉尺寸
  mutate(Grid_Size = 0.6)

cat("数据清洗与多维度降尺度完美完成！\n")

# ==============================================================================
# 4. 绘图数据准备
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
# 5. 极致紧凑主题 (A,B,C 带海洋蓝；D 纯白)
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
# 6. 渲染子图零件
# ==============================================================================

# --- A & B: Delta 地图 ---
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

# --- C: 双变量图 ---
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
# 7. 图例提取与【水平一行化】重排
# ==============================================================================
cat("正在对图例进行水平一行化重排...\n")

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
# 8. 最终组装输出
# ==============================================================================
p_main <- (p_a / p_b / p_c / p_d) + 
  plot_layout(heights = c(1, 1, 1, 0.6)) +
  plot_annotation(tag_levels = 'a', tag_prefix = '(', tag_suffix = ')') & 
  theme(legend.position = "none") 

p_final <- wrap_elements(p_main) / p_legend_row + 
  plot_layout(heights = c(25, 3))

ggsave("MainText_Fig2_Bilinear_Ultimate.png", plot = p_final, width = 14, height = 11, dpi = 900, bg = "transparent")
ggsave("MainText_Fig2_Bilinear_Ultimate.pdf", plot = p_final, width = 14, height = 11, bg = "transparent")

cat("大功告成！基于严格对应字典的双线性插值网格重采样已完成。\n")