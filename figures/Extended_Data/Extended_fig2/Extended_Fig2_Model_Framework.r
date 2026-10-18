# Scientific framework rebuilt from ghg_lca, fleet_model and fishery_coupling.
# Original author PNG/SVG/PPTX files remain untouched. All artwork is vector.
suppressPackageStartupMessages(library(ggplot2))
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
source(file.path(HERE,'Framework_Icons.r'))
ink<-'#263F4C';muted<-'#586E78';teal<-'#377E7C';blue<-'#517A96';rust<-'#AF704E'

nodes<-data.frame(
 id=c('registry','activity','parameters','harmonise','lca','stock_fit','historical','stock_reference',
      'ensemble','quota','fuel','refrigeration','consolidation','fixed','feasible','outcomes'),
 x=c(30,90,150,90,58,150,58,150,90,22.5,67.5,112.5,157.5,44,136,90),
 y=c(194,194,194,172,144,144,113,113,89,71,71,71,71,43.5,43.5,13.5),
 w=c(54,54,54,174,110,54,110,54,174,39,39,39,39,82,82,174),
 h=c(23,23,23,14,34,34,20,20,12,18,18,18,18,32,32,19),
 accent=c(rep(blue,4),teal,blue,teal,blue,blue,rust,teal,blue,teal,rust,teal,blue),
 fill=c(rep('#F6F8F9',4),'#EFF6F4','#F0F4F7','#F6F9F8','#F5F7FA','#F3F6F8',
        '#FBF7F2','#F2F8F5','#F1F5F9','#F2F8F5','#FBF6F1','#EFF7F5','#EDF3F6'),
 title=c('Registry and capacity','Catch and effort','Engineering inputs','Data harmonisation and fleet reconstruction',
         'Vessel-year life-cycle inventory','Exploratory stock fits','Historical GHG, CEI and fleet state','Stock reference',
         '81 futures','Quota rules','Fuel transition','Refrigeration','Fleet consolidation',
         'Fixed-catch stress test','Feasible-catch simulation','Paired GHG, catch and mitigation outcomes'),
 body=c('Five RFMO registries\nPower, tonnage, age','Catch and effort grids\nRegional CPUE indices',
        'Operation and life-cycle factors\nFuel, carbon and electricity costs',
        'Vessel identity and imputation  /  historical capacity gaps  /  catch-effort units',
        'Monte Carlo emission accounting','Catch + CPUE; JABBA / Schaefer; global fits and regional checks',
        'Fleet, RFMO, species and grid; CEI factorisation','Biomass, production and catch shares',
        '3 WEO x 3 growth x 3 turnover x 3 technology',
        'C-type / F-type','Blends + newbuilds','R22 to LN2','Power conserved',
        'Prescribed biomass and catch; Meco x Mecon; no realised-catch feedback; 0.03K floor',
        'Available biomass to target catch; effort bounded by demand, capacity and costs; realised catch updates stock',
        'Own-BAU reductions; period CEI; Shapley contributions; matched-catch checks'))
nodes$xmin<-nodes$x-nodes$w/2;nodes$xmax<-nodes$x+nodes$w/2
nodes$ymin<-nodes$y-nodes$h/2;nodes$ymax<-nodes$y+nodes$h/2
edges<-data.frame(x=numeric(),y=numeric(),xend=numeric(),yend=numeric(),colour=character(),arrow=logical())
edge<-function(x,y,xend,yend,colour='#9AAAB2',arrow=TRUE) {
  edges<<-rbind(edges,data.frame(x,y,xend,yend,colour,arrow))
}
for(x in c(30,90,150))edge(x,182,x,179.5)
for(x in c(58,150)){edge(x,164.5,x,161.5);edge(x,126.5,x,123.5)}
edge(58,102.5,58,101.8,arrow=FALSE);edge(150,102.5,150,101.8,arrow=FALSE)
edge(58,101.8,150,101.8,arrow=FALSE);edge(110,101.8,110,95.5)
for(x in c(22.5,67.5,112.5,157.5)){edge(x,82.5,x,79.4);edge(x,61.6,x,60.7,arrow=FALSE)}
edge(22.5,60.7,157.5,60.7,arrow=FALSE)
for(x in c(44,136)){edge(x,60.7,x,59.8);edge(x,27,x,23.5)}
# Realised removals feed the following year's stock in the feasible branch only.
edge(174.5,32,179.6,32,teal,FALSE);edge(179.6,32,179.6,47.5,teal,FALSE)
edge(179.6,47.5,177.3,47.5,teal,TRUE)

p<-ggplot()+geom_segment(data=edges[!edges$arrow,],aes(x,y,xend=xend,yend=yend,colour=colour),linewidth=.30)+
 geom_segment(data=edges[edges$arrow,],aes(x,y,xend=xend,yend=yend,colour=colour),linewidth=.30,
              arrow=grid::arrow(length=grid::unit(1.1,'mm'),type='closed'))+
 scale_colour_identity()+
 geom_rect(data=nodes,aes(xmin=xmin,xmax=xmax,ymin=ymin,ymax=ymax),
           fill=nodes$fill,colour='#D7E1E4',linewidth=.25)+
 geom_segment(data=nodes,aes(x=xmin,xend=xmax,y=ymax,yend=ymax),colour=nodes$accent,linewidth=.65)
label<-function(x,y,text,size=2.5,bold=FALSE,hjust=.5,colour=ink,lineheight=1.15) {
 p<<-p+annotate('text',x=x,y=y,label=text,size=size,hjust=hjust,colour=colour,
               family='Arial',fontface=if(bold)'bold' else 'plain',lineheight=lineheight)
}
label(3,211,'Historical inventory  |  1950\u20132025',3.4,TRUE,0)
for(i in 1:3) {
 n<-nodes[i,];left<-n$xmin
 framework_icon(c('boat','fish','sliders')[i],left+5.3,194,3.3,blue)
 label(left+12,201,n$title,2.8,TRUE,0)
 label(left+12,192.5,n$body,2.35,FALSE,0,muted,1.35)
}
label(90,175,'Data harmonisation and fleet reconstruction',2.9,TRUE)
label(90,169,'Vessel identity and imputation  /  historical capacity gaps  /  catch-effort units',2.4,FALSE,.5,muted)
label(58,156,'Vessel-year life-cycle inventory',2.9,TRUE)
label(58,150.5,'Monte Carlo emission accounting',2.45,FALSE,.5,muted)
for(i in 1:5)framework_icon(c('fuel','snow','boat','gear','bait')[i],c(15,36,58,80,101)[i],141,3.0,teal)
for(i in 1:5)label(c(15,36,58,80,101)[i],132.5,
 c('Fuel + supply\n(main + aux)','Refrigerant','Vessel\nbuild + upkeep','Gear\nbuild + upkeep','Bait')[i],2.4)
label(150,156,'Exploratory stock fits',2.8,TRUE)
framework_icon('fish',132,144,3.7,blue)
label(141,144,'Catch + CPUE\nJABBA / Schaefer',2.4,FALSE,0,ink,1.4)
label(150,132.5,'Global fits / regional checks',2.35,FALSE,.5,muted)
framework_icon('globe',11,113,3.5,teal)
label(20,118,'Historical GHG, CEI and fleet state',2.85,TRUE,0)
label(20,112,'Fleet-to-grid allocation / E*: standardised effort',2.4,FALSE,0,muted)
label(20,106.5,'CEI = (E* / catch) \u00d7 (GHG / E*)',2.4,FALSE,0)
label(150,118,'Stock reference',2.8,TRUE)
label(150,110,'Biomass and production\nInventory / removal shares',2.35,FALSE,.5,muted,1.3)
label(3,98,'Future stock-fleet comparisons',3.25,TRUE,0)
label(177,98,'2025 reference to 2050',2.5,FALSE,1,muted)
label(8,91,'81 futures',2.9,TRUE,0)
label(40,91,'3 WEO \u00d7 3 growth \u00d7 3 turnover \u00d7 3 technology',2.6,FALSE,0)
label(40,86.5,'Stock conditions / fleet capacity / fuel and carbon costs',2.35,FALSE,0,muted)
for(i in 1:4) {
 n<-nodes[9+i,];left<-n$xmin
 framework_icon(c('quota','fuel','snow','fleet')[i],left+4.6,71.2,2.5,n$accent)
 label(left+9.3,74.5,n$title,2.5,TRUE,0)
 label(left+9.3,68,if(i==3)'R22 \u2192 LN\u2082' else n$body,2.25,FALSE,0,muted)
}
label(9,55.5,'Fixed-catch stress test',2.9,TRUE,0,rust)
label(101,55.5,'Feasible-catch simulation',2.9,TRUE,0,teal)
for(i in 1:3){
 yy<-c(47.4,39.7,32)[i]
 framework_icon(c('chart','sliders','chart')[i],10,yy,2.2,rust)
 framework_icon(c('fish','boat','chart')[i],102,yy,2.2,teal)
}
label(18,47.4,'Prescribed biomass + catch targets',2.4,FALSE,0)
p<-p+annotate('text',x=18,y=39.7,label='M[eco] %*% M[econ]',parse=TRUE,
              hjust=0,size=2.6,colour=ink,family='Arial')
label(41,39.7,'\u2192 requested activity',2.4,FALSE,0)
label(18,32,'No catch feedback; floor 0.03K',2.4,FALSE,0)
label(110,47.4,'Available stock \u2192 catch target',2.4,FALSE,0)
label(110,39.7,'Effort limited by demand,\ncapacity and fuel-cost response',2.4,FALSE,0,ink,1.15)
label(110,32,'Realised catch \u2192 next-year stock',2.4,FALSE,0)
label(172,39.7,'Annual\nfeedback',2.05,FALSE,.5,teal)
framework_icon('chart',12,13.5,3.6,blue)
label(23,18,'Paired GHG, catch and mitigation outcomes',2.9,TRUE,0)
label(23,10.3,'Own-BAU reductions / period CEI / Shapley contributions / matched-catch checks',2.4,FALSE,0,muted)

paths<-do.call(rbind,icon_paths);dots<-do.call(rbind,icon_dots)
p<-p+geom_path(data=paths,aes(x,y,group=group,colour=colour),linewidth=.32,lineend='round',linejoin='round')+
 geom_point(data=dots,aes(x,y,colour=colour),size=.45)+
 coord_fixed(xlim=c(0,182),ylim=c(0,215),expand=FALSE,clip='off')+
 theme_void(base_family='Arial')+theme(plot.margin=margin(1.5,1.5,1.5,1.5,'mm'))
write.csv(nodes,file.path(HERE,'Extended_Fig2_Final_Interfaces.csv'),row.names=FALSE)
write.csv(edges,file.path(HERE,'Extended_Fig2_Final_Arrows.csv'),row.names=FALSE)
write.csv(paths,file.path(HERE,'Extended_Fig2_Icon_Paths.csv'),row.names=FALSE)
write.csv(nodes,file.path(HERE,'Extended_Fig2_PanelA_Render_Data.csv'),row.names=FALSE)
for(ext in c('pdf','png','tiff')){
 opts<-list(filename=file.path(HERE,paste0('Extended_Fig2_Stock_Fleet_Framework.',ext)),plot=p,width=183,height=215,units='mm',bg='white')
 if(ext=='pdf')opts$device<-cairo_pdf
 if(ext=='png')opts$dpi<-300
 if(ext=='tiff'){opts$dpi<-900;opts$compression<-'lzw'}
 do.call(ggsave,opts)
}
