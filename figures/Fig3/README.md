# Fig3 当前文件与归档索引

整理日期：2026-10-12。

顶层保留当前版本：a 为网格两因素的对数趋势；b/c 为灰色网格–时期气泡、三个时期的 RFMO 汇总点和时间箭头。b/c 保留 RFMO 颜色、时期形状、气泡排放量图例，已删除用户指定的图内说明文字。

## 当前入口

从项目根目录运行：

```powershell
& C:/CONDA/python figures/Fig3/preprocess_fig3.py
$env:R_HOME='C:/Users/11401/Desktop/r_env/R_4.5.2/lib/R'
$env:PATH='C:/Users/11401/Desktop/r_env/R_4.5.2/lib/R/bin/x64;C:/Users/11401/Desktop/r_env/R_4.5.2/Library/bin;' + $env:PATH
& C:/Users/11401/Desktop/r_env/R_4.5.2/lib/R/bin/x64/Rscript.exe --vanilla figures/Fig3/Fig3_Phase_Decoupling.r
```

默认输出为 `Fig3_Era_Background_Preview.png/.pdf/.tiff`。文件名沿用预览阶段名称，内容是当前版本。R 入口加 `a` 仅出 a；加 `bc` 或 `bc-era` 仅出 b/c。Python 加 `bc` 或 `bc-era` 仅更新当前 b/c 数据。原来的 `era-background` 参数仍可用于完整出图。

当前代码仅有：

- `preprocess_fig3.py`：当前 a、b、c 数据构建及上游渔获记录核查。
- `Fig3_Phase_Decoupling.r`：完整图入口。
- `Fig3_PanelA_Decomposition.r`：a 的渲染模块。
- `Fig3_PanelBC_Era_Background.r`：b/c 的渲染模块。

顶层的当前 panel CSV、审计 JSON、单面板 PNG/PDF 和 `Fig3_Revision_Notes.md` 一并保留。当前构建与渲染均不读取 `_archive_*`，删除归档不会影响当前入口。

## 归档分组

| 文件夹 | 保存内容 | 对比重点 |
|---|---|---|
| `_archive_pre_decomposition_20261011` | 原 CPUE–CEI 图、代码和面板数据 | 改变 a 坐标前的原分析 |
| `_archive_newspace_prototypes_20261011` | a 的 NewSpace 数据和 preview 1–6 的代码、PNG、PDF，共 19 个文件 | 早期设计试验；不作为当前统计结果 |
| `_archive_pre_bc_aggregation_20261011` | 改写 b/c 汇总方法前保存的图、代码和数据 | b/c 分别取中位数的旧方法 |
| `_archive_decade_aggregation_20261011` | b/c 改为总量比值后的年代轨迹、敏感性数据、审计、旧完整图；另附整理前代码和共享 a 输入快照 | 多年代轨迹与当前三时期背景气泡设计的对比 |
| `_archive_legacy_exports_20260928` | `Fig3_new.pdf/.png/.tif` 和 `Rplots.pdf` | 早期导出图；未确认其对应的生成代码 |
| `_archive_runtime_cache_20261012` | 旧 Python 编译缓存 | 缓存留档，不作为源代码使用 |

归档代码保留移动/复制前的内容，供版本对比。部分历史脚本按原 Fig3 顶层路径编写，移入子目录后不能假定直接运行即可复现。各版本的已有图和数据可以直接查看。

`Fig3_Archive_Manifest_20261012.json` 保存本次移动、复制清单、大小和 SHA-256 校验值。两个原有归档文件夹保持原内容。没有删除文件。

## Adobe 原稿

`Fig3.ai`、`Fig3.pdf`、`Fig3.png`、`Fig3.tif` 为用户原稿，按仓库约定保留原位，内容未改动。分析比较以当前输出和归档中的分析输出为准。

运行环境提示：本机 R 曾在完成导出后返回状态 1，未出现计算错误。已直接检查输出文件和数据断言；详细记录见 `Fig3_Revision_Notes.md`。
