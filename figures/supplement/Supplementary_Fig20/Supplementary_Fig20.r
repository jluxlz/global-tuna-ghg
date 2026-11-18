suppressPackageStartupMessages({library(ggplot2);library(dplyr);library(patchwork)})
a <- grep("^--file=", commandArgs(FALSE), value = TRUE)
here <- dirname(normalizePath(sub("^--file=", "", a[1]), winslash="/"))
panel <- function(name) {
  stem <- file.path(here, paste0("Supplementary_Fig20_Panel", name))
  d <- read.csv(paste0(stem, ".csv"))
  stopifnot(all(d$Stock == "BET"))
  write.csv(d, paste0(stem, "_Render_Data.csv"), row.names=FALSE)
  d
}
style <- theme_classic(base_family="Arial", base_size=8) +
  theme(axis.title=element_text(face="bold"), axis.text=element_text(colour="black"),
        plot.tag=element_text(face="bold"), plot.margin=margin(6,9,6,7))
col <- "#0072B2"
fit <- panel("A_Regional_Fits")
p1 <- ggplot(fit, aes(Year, B_Mt)) +
  geom_ribbon(aes(ymin=B_Lower, ymax=B_Upper), fill=col, alpha=.17) +
  geom_line(colour=col, linewidth=.55) +
  labs(tag="(a)", x="Year", y="Fitted total biomass (Mt)") + style
qc <- panel("B_Regional_QC")
q <- summarize(qc, Rhat=max(Rhat), Bulk=min(ESS_Bulk), Tail=min(ESS_Tail))
p2 <- ggplot(q, aes(Rhat, 0)) +
  geom_vline(xintercept=1.01, colour="grey45", linetype="dotted", linewidth=.3) +
  geom_point(colour=col, size=2.3) +
  geom_text(aes(label=sprintf("Bulk ESS %.0f   |   Tail ESS %.0f", Bulk, Tail)), nudge_y=.13, size=2.8) +
  scale_x_continuous(limits=c(1,1.011), breaks=c(1,1.0025,1.005,1.0075,1.01)) +
  scale_y_continuous(limits=c(-.35,.35), breaks=NULL) +
  labs(tag="(b)", x=expression("Maximum rank-normalized "*hat(R)), y=NULL) + style +
  theme(axis.line.y=element_blank(), axis.ticks.y=element_blank())
out <- p1 / p2 + plot_layout(heights=c(1.8,1))
stem <- file.path(here,"Supplementary_Fig20_BET_Stock_Diagnostics")
ggsave(paste0(stem,".pdf"),out,width=183,height=115,units="mm",device=cairo_pdf,bg="white")
ggsave(paste0(stem,".png"),out,width=183,height=115,units="mm",dpi=300,bg="white")
ggsave(paste0(stem,".tiff"),out,width=183,height=115,units="mm",dpi=900,compression="lzw",bg="white")
