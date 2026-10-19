# Fig 3: Phase-Space Decoupling of Global Tuna Fleet
library(ggplot2); library(dplyr); library(tidyr); library(scales); library(patchwork); library(ggrepel)

args <- commandArgs(trailingOnly=FALSE)
file_arg <- grep("^--file=",args,value=TRUE)
if (length(file_arg)>0) {
  SCRIPT_DIR <- normalizePath(dirname(sub("^--file=","",file_arg)))
} else if (sys.nframe()>0) {
  SCRIPT_DIR <- normalizePath(dirname(sys.frame(1)$ofile))
} else {
  SCRIPT_DIR <- normalizePath(getwd())
}
setwd(SCRIPT_DIR)
source("Legend_Layout.r")
DATA_DIR<-"../../GHG_Calculation"; OUT_DIR<-"."

species_cols<-c("SKJ"="#984EA3","YFT"="#FF7F00","BET"="#377EB8","ALB"="#E41A1C","SBT"="#4DAF4A","All"="#808080","None"="#B0B0B0")
org_cb_cols<-c("WCPFC"="#E69F00","IATTC"="#56B4E9","ICCAT"="#009E73","IOTC"="#CC79A7","CCSBT"="#555555")

theme_pub<-theme_classic(base_size=7,base_family="sans")+theme(
  plot.tag=element_text(face="bold",size=8,family="sans"),plot.tag.position="topleft",
  axis.title=element_text(size=7,face="bold",family="sans"),axis.text=element_text(size=6,colour="black",family="sans"),
  axis.line=element_line(colour="black",linewidth=0.5),axis.ticks=element_line(colour="black",linewidth=0.5),
  legend.title=element_text(face="bold",size=7,family="sans"),legend.text=element_text(size=6,family="sans"),
  legend.position="bottom",legend.box="horizontal",legend.key.size=unit(0.35,"cm"),legend.margin=margin(t=0,b=0),
  panel.grid.major=element_line(colour="grey90",linetype="dashed",linewidth=0.25),panel.grid.minor=element_blank(),
  strip.background=element_blank(),strip.text=element_text(face="bold",size=7,family="sans"))

if (any(c("bc","bc-era") %in% commandArgs(trailingOnly=TRUE))) {
  source("Fig3_PanelBC_Era_Background.r")
  quit(save="no",status=0)
}
source("Fig3_PanelA_Decomposition.r")
if ("a" %in% commandArgs(trailingOnly=TRUE)) quit(save="no",status=0)

source("Fig3_PanelBC_Era_Background.r")

# ASSEMBLE
cat("Assembling figure...\n")
source("Fig3_Aligned_Layout.r")
if(!is.null(bc_caption))
  fig3<-fig3+plot_annotation(caption=bc_caption,theme=theme(plot.caption=element_text(size=6,hjust=0)))
W_MM<-180;H_MM<-225
output_prefix<-"Fig3_Era_Background_Preview"
cat(sprintf("Exporting at %.0f x %.0f mm...\n",W_MM,H_MM))
ggsave(paste0(output_prefix,".pdf"),plot=fig3,width=W_MM,height=H_MM,units="mm",device=cairo_pdf,bg="white")
ggsave(paste0(output_prefix,".png"),plot=fig3,width=W_MM,height=H_MM,units="mm",dpi=300,bg="white",device=grDevices::png,type="cairo")
ggsave(paste0(output_prefix,".tiff"),plot=fig3,width=W_MM,height=H_MM,units="mm",dpi=900,compression="lzw",bg="white",device=grDevices::tiff,type="cairo")
cat("Fig 3 saved to",normalizePath(OUT_DIR),"\n")
if (sys.nframe()==0) quit(save="no",status=0)
