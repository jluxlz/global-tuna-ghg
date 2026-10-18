# FIGURES.md — Publication Figure Standards (Nature Food)

This file documents all plotting conventions for figures in this project.
Apply these standards to ALL new figures. Read before writing any ggplot2/R code.

## File Organization (MANDATORY)

**Each figure lives in its own subfolder.** Every figure folder is self-contained:
- R script(s) + Python preprocessing
- Generated images (PDF + PNG)
- Panel input data (CSV per panel)

```
figures/
├── FIGURES.md                    # This file
├── Fig1/                         # Group figure 1
│   ├── Fig1_xxx.r                # R script
│   ├── Fig1_xxx.pdf / .png       # Output images
│   ├── Fig1_PanelA_xxx.csv ...   # Per-panel input data
│   └── RFMO_Icons/               # (if applicable)
├── Fig2/
│   ├── Fig2_xxx.r
│   ├── preprocess_fig2.py        # (if applicable)
│   ├── Fig2_xxx.pdf / .png
│   └── Fig2_PanelA_xxx.csv ...
└── FigN/ ...
```

**When creating a new figure:**
1. Create `figures/FigN/` folder
2. ALL code, data, and outputs go inside that folder
3. R scripts read from `DATA_DIR <- "../.."` (points to `GHG_Calculation/`)
4. Shapefiles read from `file.path(SCRIPT_DIR, "..", "..", "..", "shape_file")`
5. CSV exports write to `"."` (the figure folder itself)

## Data Export Rule (MANDATORY)

**Every panel of every figure MUST export its input data as CSV.**

After each panel completes, add:
```r
cat("  Panel X complete.\n")
write.csv(df_panel, "FigN_PanelX_Description.csv", row.names = FALSE)
```

Naming convention: `Fig{N}_{Panel}{Letter}_{Description}.csv`
Examples: `Fig1_PanelA_Process_Pct.csv`, `Fig2_PanelD_Trajectory.csv`

## Canvas & Export

| Parameter | Value |
|-----------|-------|
| Width | **183 mm** (Nature Food double-column) |
| Max height | **247 mm** |
| Format | **PDF vector** (cairo_pdf) + **PNG preview** (300 dpi) + **TIFF** (900 dpi, LZW compression, for submission) |
| Background | White |

```r
W_MM <- 183; H_MM <- 220  # adjust H_MM per figure, max 247
ggsave("figure.pdf", plot = fig, width = W_MM, height = H_MM, units = "mm",
       device = cairo_pdf, bg = "white")
ggsave("figure.png", plot = fig, width = W_MM, height = H_MM, units = "mm",
       dpi = 300, bg = "white")
ggsave("figure.tiff", plot = fig, width = W_MM, height = H_MM, units = "mm",
       dpi = 900, compression = "lzw")
```

## Typography

| Element | Font | Size | Style |
|---------|------|------|-------|
| Panel tags (a), (b), (c), (d) | Sans-serif | **8 pt** | Bold, lowercase, **with parentheses** |
| Axis titles | Sans-serif | **7 pt** | Bold |
| Axis tick labels | Sans-serif | **6 pt** | Regular |
| Legend title | Sans-serif | **7 pt** | Bold |
| Legend text | Sans-serif | **6 pt** | Regular |
| Strip/facet labels | Sans-serif | **7 pt** | Bold |
| All text | **Arial / Helvetica** | — | NO serif fonts |

```r
nature_theme <- theme_classic(base_size = 7, base_family = "sans") +
  theme(
    plot.tag          = element_text(face = "bold", size = 8, family = "sans"),
    axis.title        = element_text(size = 7, face = "bold", family = "sans"),
    axis.text         = element_text(size = 6, colour = "black", family = "sans"),
    legend.title      = element_text(face = "bold", size = 7, family = "sans"),
    legend.text       = element_text(size = 6, family = "sans"),
    strip.text        = element_text(face = "bold", size = 7, family = "sans")
  )
```

## Lines & Spacing

| Element | Weight | Style |
|---------|--------|-------|
| Axis lines | **0.5 pt** | Solid black |
| Axis ticks | **0.5 pt** | Solid black |
| Gridlines | **0.25 pt** | Dashed, grey90 |
| Data lines | 0.5–0.8 pt | — |
| Minimum line weight | **0.25 pt** | NO hairlines |

## Legend Rules

- Position legends below their associated panel and centre them.
- Use horizontal items and place separate guides side by side when their measured
  widths fit the actual exported panel width. Wrap to additional rows only when
  needed; do not force every guide onto a separate row.
- Size legends against their panel width, not the full composite width. Keep
  separate colour, shape and size meanings and retain all labels and keys.
- Local `Legend_Layout.r` helpers measure the existing guide grobs, preserve
  overrides, wrap long item lists, then pack the guide groups into centred rows.
- A shared x title must span every subplot it describes, including independently
  scaled facets. Use `axis_titles = "collect_x"` for identical adjacent titles.
- Keep independent x titles centred within their own panel; never centre them
  across unrelated panels.
- Colour bars remain horizontal; preserve their scale, breaks and units.

## Color Schemes

- Use **colorblind-friendly** palettes (Okabe-Ito preferred)
- Sequential: viridis or custom log10 CEI ramp
- Diverging: RColorBrewer RdBu (for slope/trend maps)
- Background: **white**, no grey fill

### Gear Colors (consistent across all panels)
```r
gear_sector_cols <- c(
  "LL_DW" = "#B81D0A", "LL_CO" = "#F28B7C",
  "PS_DW" = "#1A7A8A", "PS_CO" = "#7FCDE0",
  "TP"    = "#00A087", "SA"    = "#984EA3"
)
```

## Layout (patchwork)

### Multi-panel Assembly

```
Use: top_row / middle / bottom  (vertical stack for rows)
     panel_a | panel_b           (horizontal for columns)

Key rules:
- Spatial maps (coord_sf): compress row height (0.5-0.75) — maps are flat
- Faceted scatterplots: give more height (1.4-1.5) — bubbles need room
- Legend-heavy panels: extra bottom margin (20-40 pt)
- Use & theme() to penetrate patchwork sub-plots
- Use guides = "keep" for per-panel legends, "collect" to center shared legends
```

### Common Layout Patterns

**2×2 (Fig1):**
```r
fig <- (p_a + p_b) / (p_c + p_d) + plot_layout(guides = "keep")
```

**3-row with maps on top (Fig2):**
```r
top_row <- (p_a | p_b) + plot_layout(widths = c(2.6, 1), guides = "keep")
fig <- top_row / p_c / p_d + plot_layout(heights = c(0.5, 1.4, 1.25), guides = "keep")
```

## Spatial Maps

- Projection: equirectangular (`coord_sf(crs = 4326)`)
- Bounds: xlim = c(-160, 160), ylim = c(-60, 60)
- Ocean fill: "#d6eaf8"
- Land fill: "gray85", border "gray50", linewidth 0.10
- Grid: 5° × 5° tiles, snapped to `floor(lon/5)*5+2.5`
- Facet labels: NO strip background, bold sans-serif 7pt

## Stacked Bar Charts

- No white borders between segments (`colour = NA`)
- Width: 0.75
- Error bars: `geom_errorbarh(linewidth = 0.6, height = 0.3, colour = "grey30")`
- Value labels: right end of bar, hjust = -0.15, size = 2.8, bold

## Figure-Specific Notes

### Fig1 (Multi-Dimensional Deconstruction)
- Panel A: 100% stacked area + cumulative line + CI ribbon. `guide_legend(nrow = 2)` for 7 processes
- Panel B: Gear small multiples (2×2). CEI from Base_3 (GHG>0 cells only)
- Panel C: Species bubble scatter (3×2 facets). Two legends stacked vertically
- Panel D: Cumulative 1950-2025 stacked bar by RFMO×Gear. `guide_legend(nrow = 2)` for 6 gear types

### Fig2 (Spatial-Temporal CEI)
- Panel A: 3-era CEI maps, colorbar 8cm × 0.35cm, legend.margin t=-15
- Panel B: CEI+GHG slope maps, colorbar 3.5cm × 0.35cm, 5 slope breaks
- Panel C: Phase-space quadrant (3×2 facets), horizontal legend box
- Panel D: Phase trajectory (LL+PS), shared legend via guides="collect"

## RFMO Shapefile Handling

Shapefiles in `../../shape_file/ORG/RFB_ORG.shp`. Must apply XY-flip fix on load (FAO data has transposed Lat/Lon):

```r
flip_matrix <- matrix(c(0, 1, 1, 0), nrow = 2)
s <- st_read(path, quiet = TRUE)
s <- st_transform(s, crs = 4326)
st_geometry(s) <- st_geometry(s) * flip_matrix
st_crs(s) <- 4326
```

**Dateline treatment (per-org, NOT blanket):**

| Org | `st_shift_longitude` | Why |
|-----|---------------------|-----|
| WCPFC | ✅ Yes | Crosses 180° dateline |
| CCSBT | ❌ No | Crosses 0° (Greenwich), shift tears it |
| ICCAT | ❌ No | Same as CCSBT |
| IOTC | ❌ No | Indian Ocean only |
| IATTC | ❌ No | All western hemisphere |

**Global maps (Fig2)**: use `st_wrap_dateline(rfmo_all)` on combined dataset.
**Standalone icons (Fig1 export)**: per-org decision, `coord_sf(datum = NA)`, dynamic aspect ratio with `cos(center_lat)`.
