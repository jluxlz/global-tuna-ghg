import pandas as pd
import numpy as np

def extract_specific_flags_catch(file_path, output_path):
    # ==========================================
    # 1. 读取数据并跳过前7行的说明文字与复杂表头
    # ==========================================
    # 原始表格头部有多行合并单元格，第8行（索引7）才是真正的数据起点
    df = pd.read_excel(file_path, header=None, skiprows=7)
    
    # 根据我们对原 Excel 表头的解析，手动为数据列命名
    # 原表中依次是：年份, 澳洲(商业), 澳洲(业余), 日本, 新西兰(商业), 新西兰(业余), 韩国, 台湾, 菲律宾, 印尼, 南非, 欧盟, 杂项, 研究
    df.columns = [
        'Year', 
        'AU_Com', 'AU_Ama', 
        'JP', 
        'NZ_Com', 'NZ_Ama', 
        'KR', 'TW', 'PH', 'ID', 'ZA', 'EU', 'Misc', 'Res'
    ]
    
    # 将所有列转换为数值型，无法转换的（比如空字符串）会被转为 NaN
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    # 清洗：删除年份为空的行（例如文件末尾的汇总说明），并将年份转为整数
    df = df.dropna(subset=['Year']).copy()
    df['Year'] = df['Year'].astype(int)
    
    # ==========================================
    # 2. 仅提取图片中出现的 6 个国家/地区，并汇总特定列
    # ==========================================
    df_flags = pd.DataFrame()
    df_flags['Year'] = df['Year']
    
    # 将商业和业余捕捞量相加，列名使用 ISO3 代码
    df_flags['AUS'] = df['AU_Com'].fillna(0) + df['AU_Ama'].fillna(0)
    df_flags['NZL'] = df['NZ_Com'].fillna(0) + df['NZ_Ama'].fillna(0)

    # 提取其他单列国家数据，列名使用 ISO3 代码
    df_flags['JPN'] = df['JP'].fillna(0)
    df_flags['KOR'] = df['KR'].fillna(0)
    df_flags['TWN'] = df['TW'].fillna(0)
    df_flags['ZAF'] = df['ZA'].fillna(0)
    
    # ==========================================
    # 3. 导出结果
    # ==========================================
    df_flags.to_csv(output_path, index=False)
    print(f"提取完成！数据已保存至 {output_path}")
    
    return df_flags

# 运行代码提取数据
input_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\source_data\GlobalCatch_Flag_Gear.xlsx'
output_file = r'C:\Users\11401\Desktop\Global_Tuna_Fishery_GHG_Emission\effort_data\CCSBT\CCSBT_Annual_Catch.csv'

final_flags_df = extract_specific_flags_catch(input_file, output_file)

# 打印前几行预览结果
print("\n提取后的数据预览:")
print(final_flags_df.head())