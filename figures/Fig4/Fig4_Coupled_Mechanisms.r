# Fig4 analytical mechanisms. Run from any directory; [a|b|c|d|e|f|all].
suppressPackageStartupMessages({library(ggplot2); library(patchwork)})
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
stopifnot(length(script_arg) == 1)
HERE <- dirname(normalizePath(sub("^--file=", "", script_arg)))
setwd(HERE)
args <- commandArgs(TRUE)
TARGET <- if (length(args)) tolower(args[1]) else "all"
stopifnot(TARGET %in% c(letters[1:6], "all"))

theme_fig4 <- function() {
  theme_classic(base_size = 7, base_family = "sans") +
    theme(axis.line = element_line(linewidth = .4),
          axis.ticks = element_line(linewidth = .35),
          axis.title = element_text(size = 7), axis.text = element_text(size = 6, colour = "black"),
          axis.text.x = element_text(angle = 45, hjust = 1),
          legend.position = "bottom", legend.box = "vertical",
          legend.title = element_text(size = 6.5), legend.text = element_text(size = 6),
          legend.key.height = unit(2.8, "mm"), legend.key.width = unit(6, "mm"),
          legend.margin = margin(0,0,0,0), legend.spacing = unit(1, "mm"),
          legend.box.spacing = unit(1, "mm"),
          strip.background = element_blank(), strip.text = element_text(size = 7, face = "bold"),
          panel.grid.major.y = element_line(colour = "grey92", linewidth = .2),
          panel.grid.minor = element_blank(), panel.spacing = unit(2, "mm"),
          plot.subtitle = element_text(size=6.5), plot.tag = element_text(size = 8, face = "bold"), plot.margin = margin(2,2,2,2,"mm"))
}
weo_cols <- c(STEPS="#D55E00", APS="#0072B2", NZE="#009E73")
regime_cols <- c(MSY_100="#238B8D", MSY_90="#67A9CF", MSY_80="#8073AC", MSY_70="#C65C8B", C2024="#555555")
tc_cols <- c(slow="#1B9E77", steady="#D95F02", rapid="#7570B3")
fuel_order <- c("MGO","HFO","FAME","HVO","LNG_Fossil","H2_Fossil","NH3_Green","H2_Green")
fuel_cols <- c(MGO="#444444", HFO="#B8860B", FAME="#66A61E", HVO="#1B9E77",
               LNG_Fossil="#377EB8", H2_Fossil="#984EA3", NH3_Green="#00A0A8", H2_Green="#80CDC1")
fuel_lts <- c(MGO="solid",HFO="solid",FAME="dashed",HVO="dashed",LNG_Fossil="solid",
              H2_Fossil="longdash",NH3_Green="dotted",H2_Green="dotted")
fuel_lab <- c(MGO="MGO",HFO="HFO",FAME="FAME",HVO="HVO",LNG_Fossil="LNG fossil",
              H2_Fossil="H2 fossil",NH3_Green="NH3 green",H2_Green="H2 green")
design_lab <- c(C="C: constant catch", F="F: harvest rate", T="T: biomass threshold")
hcr_cols <- c(C="#666F77",F="#0072B2",T="#009E73")
yrs <- c(2025,2030,2040,2050)

read_panel <- function(letter, suffix, keys) {
  d <- read.csv(sprintf("Fig4_Panel%s_%s.csv", letter, suffix), check.names = FALSE)
  stopifnot(nrow(d)>0, !anyDuplicated(d[keys]))
  # Preserve exactly the table read by R on every render, including partial previews.
  write.csv(d, sprintf("Fig4_Panel%s_Render_Data.csv", letter), row.names=FALSE, na="")
  d
}
checked_factor <- function(x, levels) {
  stopifnot(!anyNA(x), all(x %in% levels))
  factor(x, levels=levels)
}
zones <- function() {
  list(annotate("rect",xmin=-Inf,xmax=Inf,ymin=1,ymax=Inf,fill="#FBEFEF"),
       annotate("rect",xmin=-Inf,xmax=Inf,ymin=-Inf,ymax=1,fill="#EFF6FB"),
       geom_hline(yintercept=1,linetype="dashed",colour="grey40",linewidth=.3))
}

da <- read_panel("A","HCR_Summary",c("Year","Stock","Rule"))
da$Stock <- checked_factor(da$Stock,c("SKJ","YFT","BET","ALB","SBT"))
da$Rule <- checked_factor(da$Rule,names(hcr_cols))
p_a <- ggplot(da,aes(Year,Median,colour=Rule,fill=Rule)) +
  geom_hline(yintercept=1,linetype="dashed",colour="grey55",linewidth=.3) +
  geom_hline(yintercept=c(.2,.8),linetype="dotted",colour="grey75",linewidth=.22) +
  geom_ribbon(aes(ymin=P5,ymax=P95),alpha=.12,colour=NA) +
  geom_line(linewidth=.5) + facet_wrap(~Stock,nrow=1) +
  scale_colour_manual(values=hcr_cols,labels=design_lab,name=NULL) +
  scale_fill_manual(values=hcr_cols,labels=design_lab,name=NULL) +
  scale_x_continuous(breaks=yrs) +
  labs(x="Year",y=expression(B[t]/B[MSY]),tag="(a)",subtitle="Stock trajectories under three harvest control rules") + theme_fig4() +
  guides(colour=guide_legend(nrow=1),fill=guide_legend(nrow=1))

db <- read_panel("B","Yearly_M",c("WEO","Region","Year"))
region_cols <- c("European Union"="#08519C","Canada"="#2171B5","Korea"="#6BAED6",
  "Advanced economies with net-zero pledges*"="#9ECAE1","China"="#005A32",
  "Chile & Colombia"="#238B45","Selected EMDE with net-zero pledges**"="#74C476",
  "Selected EMDE without net-zero pledges"="#E69F00",
  "Other emerging market & developing economies"="#882255")
region_labels <- c("EU","Canada","Korea","Advanced, pledges","China","Chile & Colombia",
                   "Selected EMDE, pledges","Selected EMDE, no pledge","Other EMDE")
db$WEO <- checked_factor(db$WEO,names(weo_cols))
db$Region <- checked_factor(db$Region,names(region_cols))
p_b <- ggplot(db,aes(Year,M_econ,colour=Region)) + zones() + geom_line(linewidth=.5) +
  facet_wrap(~WEO,nrow=1) +
  scale_colour_manual(values=region_cols,labels=region_labels,name=NULL,
                       guide=guide_legend(ncol=2,byrow=TRUE)) +
  scale_x_continuous(breaks=c(2023,2030,2040,2050)) +
  labs(x="Year",y=expression(M[econ]~"(relative to 2023)"),tag="(b)") + theme_fig4()

dc <- read_panel("C","HCR_Summary",c("Year","Gear","Rule","Metric"))
dc <- dc[dc$Metric %in% c("Realised_kW_days","Effort_per_t"),]
dc$Gear <- checked_factor(dc$Gear,c("LL","PS"))
dc$Rule <- checked_factor(dc$Rule,names(hcr_cols))
dc$Metric <- factor(dc$Metric,levels=c("Realised_kW_days","Effort_per_t"),
                    labels=c("Effort (billion kW-days)","Effort/catch (kW-days/t)"))
ix <- dc$Metric=="Effort (billion kW-days)"
dc[ix,c("Median","P5","P95")] <- dc[ix,c("Median","P5","P95")]/1e9
p_c <- ggplot(dc,aes(Year,Median,colour=Rule,fill=Rule)) +
  geom_ribbon(aes(ymin=P5,ymax=P95),alpha=.12,colour=NA) +
  geom_line(linewidth=.5) + facet_wrap(vars(Metric,Gear),ncol=2,scales="free_y") +
  scale_colour_manual(values=hcr_cols,labels=design_lab,name=NULL) +
  scale_fill_manual(values=hcr_cols,labels=design_lab,name=NULL) +
  scale_x_continuous(breaks=yrs) + scale_y_log10(breaks=scales::breaks_log(n=3),expand=expansion(mult=c(.04,.06))) +
  labs(x="Year",y=NULL,tag="(c)",subtitle="Actual effort and catch acquisition (log scales)") + theme_fig4() +
  theme(strip.text=element_text(size=5.8)) +
  guides(colour=guide_legend(nrow=1),fill=guide_legend(nrow=1))

dd <- read_panel("D","Fuel_Cost",c("WEO","Year","Fuel"))
dd$WEO <- checked_factor(dd$WEO,names(weo_cols))
dd$Fuel <- checked_factor(dd$Fuel,fuel_order)
dd$Year <- factor(dd$Year)
# Floating bars start at the reference 1, encoding expansion/contraction directly.
p_d <- ggplot(dd,aes(Fuel,M_econ,colour=WEO)) +
  geom_linerange(aes(ymin=pmin(1,M_econ),ymax=pmax(1,M_econ)),
                 position=position_dodge(.65),linewidth=1.8) +
  geom_point(position=position_dodge(.65),size=1.2) +
  geom_hline(yintercept=1,linetype="dashed",colour="grey50",linewidth=.3) +
  facet_wrap(~Year,nrow=1) + scale_x_discrete(labels=fuel_lab) +
  scale_colour_manual(values=weo_cols,name="WEO") +
  labs(x=NULL,y=expression(M[econ]~"(same-year MGO = 1)"),tag="(d)",subtitle="EU; same-year MGO cost reference") + theme_fig4()

de <- read_panel("E","Intensity",c("WEO","Year","Fuel"))
de$WEO <- checked_factor(de$WEO,names(weo_cols))
de$Fuel <- checked_factor(de$Fuel,fuel_order)
de_view <- de[de$Year>=2025,]
stopifnot(all(is.finite(de_view$Intensity_gCO2e_kWh)))
p_e <- ggplot(de_view,aes(Year,Intensity_gCO2e_kWh,colour=Fuel,linetype=Fuel)) +
  geom_hline(yintercept=0,colour="grey55",linewidth=.3) + geom_line(linewidth=.5) +
  facet_wrap(~WEO,nrow=1) +
  scale_colour_manual(values=fuel_cols,breaks=fuel_order,labels=fuel_lab,name="Fuel",guide="none") +
  scale_linetype_manual(values=fuel_lts,breaks=fuel_order,labels=fuel_lab,name="Fuel",
    guide=guide_legend(ncol=2,byrow=TRUE,keywidth=unit(9,"mm"),
                      override.aes=list(colour=unname(fuel_cols[fuel_order]),linewidth=.7))) +
  scale_x_continuous(breaks=yrs) +
  scale_y_continuous(expand=expansion(mult=c(.04,.05))) +
  labs(x="Year",y="Adjusted GHG intensity\n(g CO2e per engine-kWh)",tag="(e)",subtitle="EU; prescribed lifecycle factors and raw cost response") + theme_fig4()

df <- read_panel("F","Crossover_By_Leak",c("WEO","Leak_kg_yr"))
df$WEO <- checked_factor(df$WEO,names(weo_cols))
df$Display_Year <- ifelse(is.na(df$Cross_Year),2054,df$Cross_Year)
p_f <- ggplot(df,aes(Leak_kg_yr,Display_Year,colour=WEO)) +
  geom_step(data=df[!is.na(df$Cross_Year),],linewidth=.55,direction="hv") +
  geom_point(data=df[is.na(df$Cross_Year),],shape=4,size=1.4,stroke=.45,show.legend=FALSE) +
  geom_hline(yintercept=2050,linetype="dotted",colour="grey70",linewidth=.3) +
  geom_vline(xintercept=c(10,150,200,500),linetype="dashed",colour="grey70",linewidth=.25) +
  scale_x_log10(breaks=c(10,50,100,250,500,1000)) +
  scale_y_continuous(breaks=c(2023,2030,2040,2050,2054),labels=c("2023","2030","2040","2050",">2050")) +
  scale_colour_manual(values=weo_cols,name="WEO") +
  labs(x=expression(Leak~rate~(kg~ship^{-1}~yr^{-1})),y="First year LN2 < R22",tag="(f)") + theme_fig4()

source("Legend_Layout.r")
panels <- list(a=p_a,b=p_b,c=p_c,d=p_d,e=p_e,f=p_f)
save_panel <- function(nm,p) {
  ggsave(sprintf("Fig4_Panel%s_Audited.png",toupper(nm)),p,width=150,height=120,units="mm",dpi=300,
         device=grDevices::png,type="cairo",bg="white")
}
if(TARGET!="all") {
  save_panel(TARGET,panels[[TARGET]])
} else {
  for(nm in names(panels)) save_panel(nm,panels[[nm]])
  pa_layout <- horizontal_legend_plot(p_a,174,"Fig4a")
  pb_layout <- horizontal_legend_plot(p_b,83,"Fig4b")
  pc_layout <- horizontal_legend_plot(p_c,83,"Fig4c")
  pe_layout <- horizontal_legend_plot(p_e,83,"Fig4e")
  fig4 <- pa_layout / (pb_layout | pc_layout) / p_d / (pe_layout | p_f) + plot_layout(heights=c(.9,1.35,.9,1.35))
  ggsave("Figure4_Coupled_Mechanisms_Audited.pdf",fig4,width=183,height=247,units="mm",device=cairo_pdf,bg="white")
  ggsave("Figure4_Coupled_Mechanisms_Audited.png",fig4,width=183,height=247,units="mm",dpi=300,
         device=grDevices::png,type="cairo",bg="white")
  ggsave("Figure4_Coupled_Mechanisms_Audited.tiff",fig4,width=183,height=247,units="mm",dpi=900,
         device=grDevices::tiff,type="cairo",compression="lzw",bg="white")
}
cat("Fig4 render complete; R input tables exported.\n")
