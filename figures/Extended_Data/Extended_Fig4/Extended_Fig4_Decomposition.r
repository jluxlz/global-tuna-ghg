# ============================================================================
# Extended Data Fig. 4 | Decomposition of the grid-attributed emission
# increase into intensity, catch and fishing-area effects.
# Data: ED4_PanelA..D CSVs (built by Extended_Fig4_build_data.py from Base_3).
# ============================================================================
suppressMessages({library(ggplot2); library(dplyr); library(tidyr); library(patchwork)})
args <- commandArgs(trailingOnly = TRUE)
script <- grep("^--file=", commandArgs(FALSE), value=TRUE)
HERE <- if(length(args)) args[1] else dirname(normalizePath(sub("^--file=", "", script[1]), winslash="/"))

OUT <- file.path(HERE, "ED4_PanelA_EraTotals.csv")
a  <- read.csv(file.path(HERE, "ED4_PanelA_EraTotals.csv"))
b  <- read.csv(file.path(HERE, "ED4_PanelB_Decomposition.csv"))
c  <- read.csv(file.path(HERE, "ED4_PanelC_Drivers.csv"))
d  <- read.csv(file.path(HERE, "ED4_PanelD_CEI_Views.csv"))
era_lab <- c(E1 = "1970-1990", E2 = "1991-2005", E3 = "2006-2024")
a$EraL <- era_lab[a$Era]; d$EraL <- era_lab[d$Era]

nature_theme <- theme_classic(base_size = 7, base_family = "Arial") + theme(
  plot.tag = element_text(face = "bold", size = 8),
  plot.tag.position = c(0, 1), plot.title = element_text(size = 7, face = "bold"),
  axis.title = element_text(size = 7, face = "bold"),
  axis.text = element_text(size = 6, colour = "black"),
  axis.line = element_line(linewidth = 0.18, colour = "black"),
  axis.ticks = element_line(linewidth = 0.18), axis.ticks.length = unit(1.3, "mm"),
  strip.background = element_blank(), strip.text = element_text(size = 7, face = "bold"),
  legend.title = element_text(size = 7, face = "bold"), legend.text = element_text(size = 6),
  legend.position = "bottom", legend.box = "vertical", legend.key.size = unit(3, "mm"),
  legend.spacing = unit(2, "pt"), legend.margin = margin(2, 0, 0, 0),
  panel.grid.major = element_blank(), panel.grid.minor = element_blank(),
  panel.spacing = unit(3, "mm"), plot.margin = margin(4, 5, 3, 4, "pt"))

# ---- panel a : era totals ----
al <- a %>% select(EraL, Cells, Years, GHG_Mt_yr, Catch_Mt_yr) %>%
  pivot_longer(c(GHG_Mt_yr, Catch_Mt_yr), names_to = "Var", values_to = "Value") %>%
  mutate(Var = factor(Var, levels = c("Catch_Mt_yr", "GHG_Mt_yr"),
                      labels = c("Catch (Mt yr-1)", "GHG emissions (Mt yr-1)")))
pa <- ggplot(al, aes(EraL, Value, fill = Var)) +
  geom_col(position = position_dodge(width = 0.7), width = 0.65, colour = "grey25", linewidth = 0.2) +
  geom_text(data = a, aes(EraL, GHG_Mt_yr + 1.4,
            label = format(Cells, big.mark = ",")),
            inherit.aes = FALSE, size = 2.2, colour = "grey20") +
  scale_y_continuous(expand = expansion(mult = c(0, 0.1))) +
  scale_fill_manual(values = c("Catch (Mt yr-1)" = "#88CCEE", "GHG emissions (Mt yr-1)" = "#CC6677"), name = NULL) +
  labs(x = NULL, y = "Era mean (Mt yr-1)", tag = "(a)") + nature_theme

# ---- panel b : decomposition of the emission change ----
bl <- b %>% select(Transition, Common_Mt_yr, Entered_Mt_yr, Left_Mt_yr) %>%
  pivot_longer(c(Common_Mt_yr, Entered_Mt_yr, Left_Mt_yr),
               names_to = "Part", values_to = "Mt_yr")
bl$Part <- factor(bl$Part,
                  levels = c("Common_Mt_yr", "Entered_Mt_yr", "Left_Mt_yr"),
                  labels = c("Common cells", "Entered cells", "Left cells"))
bl$Trans <- factor(bl$Transition, levels = c("E1-E2", "E2-E3"),
                   labels = c("1970-1990 to 1991-2005", "1991-2005 to 2006-2024"))
bl$lab <- sprintf("%+.1f", bl$Mt_yr)
lbl <- data.frame(Trans = bl$Trans, Part = bl$Part,
                  lab = bl$lab, laby = bl$Mt_yr + ifelse(bl$Mt_yr >= 0, 0.25, -0.6))

pb <- ggplot(bl, aes(Trans, Mt_yr, fill = Part)) +
  geom_col(position = position_dodge(width = 0.7), width = 0.62,
           colour = "grey25", linewidth = 0.2) +
  geom_hline(yintercept = 0, linewidth = 0.2, colour = "grey50") +
  geom_text(data = lbl, aes(y = laby, label = lab), size = 2.0,
            position = position_dodge(width = 0.7)) +
  scale_fill_manual(values = c("Common cells" = "#4477AA",
                               "Entered cells" = "#DDCC77",
                               "Left cells" = "grey80"), name = "Cell type") +
  scale_x_discrete(labels = c("1970-1990 to 1991-2005" = "1970-1990 to\n1991-2005",
                              "1991-2005 to 2006-2024" = "1991-2005 to\n2006-2024")) +
  labs(x = NULL, y = "Change in annual GHG (Mt yr-1)",
       tag = "(b)") + nature_theme

# ---- panel c : common-cell drivers, full grid ----
cf <- c %>% select(Transition, View, Catch_effect_Mt, Intensity_effect_Mt) %>%
  pivot_longer(c(Catch_effect_Mt, Intensity_effect_Mt), names_to = "Effect", values_to = "Mt") %>%
  mutate(Effect = factor(Effect, levels = c("Catch_effect_Mt", "Intensity_effect_Mt"),
                         labels = c("Catch effect", "Intensity effect")))
pc <- ggplot(cf, aes(Transition, Mt, fill = Effect)) +
  geom_col(position = position_dodge(width = 0.7), width = 0.65, colour = "grey25", linewidth = 0.2) +
  facet_wrap(~View, ncol = 1) +
  geom_hline(yintercept = 0, linewidth = 0.2, colour = "grey50") +
  scale_fill_manual(values = c("Catch effect" = "#88CCEE", "Intensity effect" = "#CC6677",
                               "Interaction" = "grey75"), name = NULL) +
  scale_x_discrete(labels = c("E1-E2" = "1970-1990 to\n1991-2005", "E2-E3" = "1991-2005 to\n2006-2024")) +
  labs(x = NULL, y = "Common-cell GHG change (Mt yr-1)", tag = "(c)") + nature_theme

# ---- panel d : pooled and gear-specific ratios of totals ----
d$View <- factor(d$View, levels = c("Full grid", "LL grid", "PS grid"))
end_labels <- d %>% filter(Era == 'E3') %>%
  mutate(Label=sprintf('%.1f',CEI), Label_y=CEI+ifelse(View=='PS grid',-.65,.65))
pd <- ggplot(d, aes(EraL, CEI, group = View, colour = View, shape = View)) +
  geom_line(linewidth = 0.6) + geom_point(size = 1.6) +
  geom_text(data=end_labels,aes(y=Label_y,label=Label),size=2.2,
            show.legend=FALSE) +
  scale_colour_manual(values = c("Full grid" = "grey40", "LL grid" = "#B81D0A",
                                 "PS grid" = "#1A7A8A"), name = NULL) +
  scale_shape_manual(values = c("Full grid"=18,"LL grid"=16,"PS grid"=17),name=NULL) +
  scale_y_continuous(limits=c(0,NA),breaks=seq(0,25,5),expand=expansion(mult=c(0,.09))) +
  guides(colour=guide_legend(nrow=1,byrow=TRUE),shape=guide_legend(nrow=1,byrow=TRUE)) +
  labs(x = NULL, y = expression("Catch-weighted CEI"~(t~CO[2]*e~t^{-1})), tag = "(d)") + nature_theme

p <- (pa | pb) / (pc | pd) + plot_layout(heights = c(1, 1))
ggsave(file.path(HERE, "Extended_Fig4_Decomposition.pdf"), p, width = 183, height = 145, units = "mm", device = cairo_pdf)
ggsave(file.path(HERE, "Extended_Fig4_Decomposition.png"), p, width = 183, height = 145, units = "mm", dpi = 300)
cat("Extended Data Fig. 4 saved to", HERE, "\n")

ggsave(file.path(HERE, "Extended_Fig4_Decomposition.tiff"), p, width = 183, height = 145, units = "mm", dpi = 900, compression = "lzw", bg = "white")

# Full plotted source data; no subset is silently discarded.
if (exists("al")) write.csv(al, file.path(HERE, "Extended_Fig4_PanelA_Render_Data.csv"), row.names = FALSE)
if (exists("bl")) write.csv(bl, file.path(HERE, "Extended_Fig4_PanelB_Render_Data.csv"), row.names = FALSE)
if (exists("cf")) write.csv(cf, file.path(HERE, "Extended_Fig4_PanelC_Render_Data.csv"), row.names = FALSE)
if (exists("d")) write.csv(d, file.path(HERE, "Extended_Fig4_PanelD_Render_Data.csv"), row.names = FALSE)
