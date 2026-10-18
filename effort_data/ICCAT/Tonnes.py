import pandas as pd
import sys, os
import time

# 记录开始时间以测试性能
start_time = time.time()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flag_utils import normalize_flag_to_iso3, is_allowed_iso3

# --- 1. 基础配置 ---
# 指向你的 Data.csv 文件
t1nc_file_path = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\ICCAT\source_data\t1nc-20260129_ALL.xlsx'

target_species = ['SKJ', 'BET', 'ALB', 'YFT']
target_gears = ['LL', 'PS']

# --- 2. 极致性能读取与过滤 ---
print("🚀 开始读取并优化处理 T1NC 数据...")

# 优化 1：只读取需要的 5 个列，其余 20 列直接丢弃，极大降低内存占用
needed_columns = ['YearC', 'FlagName', 'GearCode', 'Species', 'Qty_t']
df = pd.read_excel(t1nc_file_path, sheet_name='Data', usecols=needed_columns)

# 优化 2：在进行复杂的国家名替换前，先用简单的物种和渔具条件进行"粗筛"
# 这会让数据量瞬间缩水，加快后续字符串处理速度
df = df[df['Species'].isin(target_species) & df['GearCode'].isin(target_gears)].copy()

# --- 3. 清洗与白名单验证 ---
# 国家名称映射到 ISO3 并过滤白名单
df['Flag'] = df['FlagName'].astype(str).str.strip().apply(normalize_flag_to_iso3)
df = df[df['Flag'].apply(is_allowed_iso3)]

# --- 4. 聚合与行列转换 ---
print("🔄 正在进行多维聚合与透视...")

# 按 年/国/渔具/物种 汇总吨数
grouped_series = df.groupby(['YearC', 'Flag', 'GearCode', 'Species'])['Qty_t'].sum()

# 优化 3：使用 unstack 将物种索引展开为列，比 pivot_table 更高效
df_pivot = grouped_series.unstack(fill_value=0).reset_index()

# 安全机制：如果在筛选后的数据中，某一种鱼完全没有被这几十个国家捕捞过（概率极低），
# 强制创建该列并填 0，防止报错
for sp in target_species:
    if sp not in df_pivot.columns:
        df_pivot[sp] = 0

# 提取并严格排序最终列
final_df = df_pivot[['YearC', 'Flag', 'GearCode', 'ALB', 'YFT', 'BET', 'SKJ']]

# 按年份降序、国家拼音排序，让数据更好看
final_df = final_df.sort_values(by=['YearC', 'Flag'], ascending=[False, True]).reset_index(drop=True)

# --- 5. 结果检查与导出 ---
end_time = time.time()
print(f"✅ 处理完毕！耗时: {end_time - start_time:.2f} 秒，总行数: {len(final_df)} 行")
print("\n🔍 最终数据前 5 行预览：")
print(final_df.head())

# 保存最终的干净数据
output_path = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\ICCAT\ICCAT_Annual_Catch.csv'
final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
print(f"\n📁 官方年度捕捞吨数已完美提取并保存至: {output_path}")