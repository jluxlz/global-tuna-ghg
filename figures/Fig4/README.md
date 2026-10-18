# Fig4 当前版本

- 绘图：`Figure4_Coupled_Mechanisms_Audited.pdf/png/tiff`；逐面板预览 `Fig4_PanelA_Audited.png` 至 F。
- 当前绘图代码：`Fig4_Coupled_Mechanisms.r`；数据代码：`preprocess_fig4.py`。
- 审计与计算边界：`Fig4_Audit_Report.md`；对应图注：`Figure4_Caption_Audited.md`。
- 可重跑核查：`audit_fig4.py`；结果 `Fig4_QC.json`、`Fig4_Upstream_QC.json` 与各 QC CSV。
- 2026-10-12 修改前代码/数据/分析图：`_archive_pre_audit_20261012/`（manifest.csv）。删除此备份不会阻止当前数据生产与 QC；历史数值比较将自动跳过。

无 Audited 后缀的旧分析图片以及 Figure4_Caption.md 保留用于对比，不能代表当前 CSV。`fig4.*` 和 `fig4_new.*` 是用户的 Adobe 产品，未修改。

特别注意：c 是原构思的动态 gear ratio-of-blends 示意，不能直接当作生产模型 flag×org 的 Meco。b 相对 2023，d/e 相对同年 MGO，生产模型相对 2025。详情及可复算分量见审计说明。
