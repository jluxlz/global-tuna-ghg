# ==========================================
# 1. 加载所有必需的工具包
# ==========================================
# 如果有未安装的包，请先运行 install.packages(c("tidyverse", "mice", "readxl", "writexl", "ggplot2", "patchwork"))
library(tidyverse)  # 数据清洗核心
library(mice)       # PMM 多重插补核心
library(readxl)     # 读取 Excel
library(writexl)    # 导出 Excel
library(ggplot2)    # 高级绘图
library(patchwork)  # 拼图神器

# ==========================================
# 2. 批量读取并清洗数据 (彻底解决 0 值问题 + 自动生成组织字段)
# ==========================================
# 请将下方路径替换为你存放 xlsx 文件的真实文件夹路径
folder_path <- "C:\\Users\\11401\\Desktop\\情景分析\\渔船数据" 
file_list <- list.files(path = folder_path, pattern = "\\.xlsx$", full.names = TRUE)

cat("找到", length(file_list), "个 Excel 文件，正在读取并拼接...\n")

# 强制全部按纯文本读取，并利用文件名生成 organization 字段
raw_data <- file_list %>%
  # set_names 把路径列表的"名字"设为文件名，这样 map_dfr 会自动生成一个包含文件名的列
  set_names(basename(.)) %>% 
  map_dfr(~ read_excel(.x, col_types = "text"), .id = "source_file") %>%
  mutate(
    # 【新增】：从文件名中提取组织名称
    # 方法A（默认）：提取文件名中的所有英文字母（例如 "2023_CCSBT数据.xlsx" -> "CCSBT"）
    organization = str_extract(source_file, "[A-Za-z]+") 
    
    # 方法B（备选）：如果你文件名纯粹就是 "CCSBT.xlsx"，可以直接去掉后缀作为组织名，取消下一行的注释即可：
    # organization = str_remove(source_file, "\\.xlsx$")
  ) %>%
  relocate(organization) %>% # 把 organization 字段挪到表格的最前面（第1列）
  select(-source_file)       # 删掉作为中转的 source_file 原始文件名列

clean_data <- raw_data %>%
  rename(
    Length_m = `Length(m)`,
    Tonnage_t = `Tonnage(t)`,
    Enginepower_kw = `Enginepower(kw)`
  ) %>%
  mutate(
    # 强制转回数值型
    Length_m = as.numeric(Length_m),
    Tonnage_t = as.numeric(Tonnage_t),
    Enginepower_kw = as.numeric(Enginepower_kw)
  ) %>%
  mutate(
    # 【核心修复】：把所有异常的 0 值，强制变回真正的缺失值 NA
    Length_m = na_if(Length_m, 0),
    Tonnage_t = na_if(Tonnage_t, 0),
    Enginepower_kw = na_if(Enginepower_kw, 0)
  )

# ==========================================
# 3. 配置严格的单向插补规则
# ==========================================
impute_subset <- clean_data %>%
  select(Length_m, Tonnage_t, Enginepower_kw) 

# 初始化 mice 配置（先不跑模型，只提取设置矩阵）
init <- mice(impute_subset, maxit = 0)
meth <- init$method
pred <- init$predictorMatrix

# 规则 A：绝对不插补 Length_m。它原来是空的，就让它空着。
meth["Length_m"] <- ""  

# 规则 B：清空所有默认的互相预测关系
pred[,] <- 0 

# 规则 C：只允许用 Length_m 去预测 Enginepower_kw 和 Tonnage_t
pred["Enginepower_kw", "Length_m"] <- 1
pred["Tonnage_t", "Length_m"] <- 1

# ==========================================
# 4. 执行 PMM 插补
# ==========================================
cat("\n开始严格遵循 Length -> Power/Tonnage 的逻辑进行插补 (生成5个平行数据集)...\n")
# 注意：由于禁止了互相插补，计算速度会比之前快很多
imp_model <- mice(impute_subset, m = 5, method = meth, predictorMatrix = pred, maxit = 5, seed = 123)

# ==========================================
# 5. 绘制并输出终极版诊断拼图：密度图 + 散点图
# ==========================================
cat("\n正在后台生成终极版诊断拼图 (密度图 + 散点图)，请稍候...\n")

# 提取所有插补轮次的数据为长表格
long_data <- complete(imp_model, action = "long", include = TRUE)
long_data$.imp <- as.factor(long_data$.imp)

# 自定义审美：让原始数据(0)用黑色粗线，插补数据(1-5)用彩色细线
line_colors <- c("0" = "black", "1" = "#E69F00", "2" = "#56B4E9", 
                 "3" = "#009E73", "4" = "#F0E442", "5" = "#CC79A7")
line_sizes <- c("0" = 1.2, "1" = 0.5, "2" = 0.5, "3" = 0.5, "4" = 0.5, "5" = 0.5)

# ------------------------------------------
# 第一排：密度图 (Density Plots)
# ------------------------------------------
d_length <- ggplot(long_data, aes(x = Length_m, color = .imp, size = .imp)) +
  geom_density(alpha = 0) + # alpha=0表示只画线，不填充底色
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
# 第二排：散点带状图 (Strip Plots)
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
# 核心魔法：使用 patchwork 进行上下左右无缝拼图
# ------------------------------------------
combined_plot <- (d_length | d_tonnage | d_power) / (p_length | p_tonnage | p_power) +
  plot_annotation(
    title = "Comprehensive PMM Diagnostics: Density & Strip Plots",
    subtitle = "Top: Density distribution (Black=Observed, Colored=Imputed) | Bottom: Data points spread | Strict 1-way Imputation",
    theme = theme(plot.title = element_text(size = 18, face = "bold", hjust = 0.5),
                  plot.subtitle = element_text(size = 12, color = "gray30", hjust = 0.5))
  )

# ------------------------------------------
# 导出为超高清大图
# ------------------------------------------
ggsave(filename = "Strict_Imputation_Ultimate_Diagnostics.png", 
       plot = combined_plot, width = 14, height = 10, dpi = 900)
cat(">>> 终极诊断图已生成: Strict_Imputation_Ultimate_Diagnostics.png\n")


library(svglite)
ggsave(filename = "Strict_Imputation_Ultimate_Diagnostics.svg", 
       plot = combined_plot, 
       width = 14, height = 10, 
       device = "svg")

# ==========================================
# 6. 生成最终文件并导出为 Excel
# ==========================================
cat("\n正在拼装最终数据表并导出...\n")

# 提取第 1 个插补完成的数据集
completed_subset <- complete(imp_model, action = 1)

# 将插补结果安全替换回主数据表中，并保留 organization 等所有其他字段不变
final_data <- clean_data %>%
  mutate(
    Length_m = completed_subset$Length_m,
    Tonnage_t = completed_subset$Tonnage_t,
    Enginepower_kw = completed_subset$Enginepower_kw
  )

# 还原带括号的原始列名
final_export <- final_data %>%
  rename(
    `Length(m)` = Length_m,
    `Tonnage(t)` = Tonnage_t,
    `Enginepower(kw)` = Enginepower_kw
  )

# 导出为最终的 .xlsx 文件
output_filename <- "Final_Strict_Imputed_Vessels.xlsx"
write_xlsx(final_export, output_filename)

cat(">>> 恭喜！全流程运行完毕。最终数据已保存为:", output_filename, "\n")
