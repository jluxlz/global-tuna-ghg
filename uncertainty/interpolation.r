# ==========================================
# 1. 加载所有必需的工具包 (已精简)
# ==========================================
# 如果有未安装的包，请先运行 install.packages(c("tidyverse", "mice", "readxl"))
library(tidyverse)  # 数据清洗核心
library(mice)       # PMM 多重插补核心
library(readxl)     # 读取 Excel

# ==========================================
# 2. 批量读取并清洗数据 (彻底解决 0 值问题 + 自动生成组织字段)
# ==========================================
# 请将下方路径替换为你存放 xlsx 文件的真实文件夹路径
folder_path <- "C:\\Users\\11401\\Desktop\\情景分析\\渔船数据" 
file_list <- list.files(path = folder_path, pattern = "\\.xlsx$", full.names = TRUE)

cat("找到", length(file_list), "个 Excel 文件，正在读取并拼接...\n")

# 强制全部按纯文本读取，并利用文件名生成 organization 字段
raw_data <- file_list %>%
  set_names(basename(.)) %>% 
  map_dfr(~ read_excel(.x, col_types = "text"), .id = "source_file") %>%
  mutate(
    # 从文件名中提取组织名称
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
    # 强制转回数值型
    Length_m = as.numeric(Length_m),
    Tonnage_t = as.numeric(Tonnage_t),
    Enginepower_kw = as.numeric(Enginepower_kw)
  ) %>%
  mutate(
    # 核心修复：把所有异常的 0 值，强制变回真正的缺失值 NA
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
# 4. 执行 PMM 插补 (生成 5 个平行数据集)
# ==========================================
cat("\n开始严格遵循 Length -> Power/Tonnage 的逻辑进行插补 (生成5个平行数据集)...\n")
# 注意：由于禁止了互相插补，计算速度会非常快
imp_model <- mice(impute_subset, m = 5, method = meth, predictorMatrix = pred, maxit = 5, seed = 123)

# ==========================================
# 5. 循环拼装并导出 5 个 CSV 文件
# ==========================================
cat("\n正在拼装 5 个平行数据集并导出...\n")

for (i in 1:5) {
  # 提取第 i 个插补完成的数据集
  completed_subset <- complete(imp_model, action = i)
  
  # 将插补结果安全替换回主数据表中，并保留 organization 等所有其他字段不变
  final_data <- clean_data %>%
    mutate(
      Length_m = completed_subset$Length_m,
      Tonnage_t = completed_subset$Tonnage_t,
      Enginepower_kw = completed_subset$Enginepower_kw
    ) %>%
    rename( # 还原带括号的原始列名，对齐 Python 脚本的读取习惯
      `Length(m)` = Length_m,
      `Tonnage(t)` = Tonnage_t,
      `Enginepower(kw)` = Enginepower_kw
    )
  
  # 导出为 CSV 文件
  output_filename <- paste0("Imputed_Vessels_PMM_", i, ".csv")
  write.csv(final_data, output_filename, row.names = FALSE, fileEncoding = "UTF-8")
  
  cat("已成功导出:", output_filename, "\n")
}

cat(">>> 恭喜！全流程运行完毕。请将这 5 个 CSV 文件放在 Python 脚本同级目录下，启动 GSA 引擎。\n")
