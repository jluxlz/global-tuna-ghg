# Corrected analysis derivative; the author's PNG/PPTX/SVG remain unchanged.
suppressPackageStartupMessages(library(ggplot2))
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
ROOT<-normalizePath(file.path(HERE,'..','..','..'),winslash='/')
b<-read.csv(file.path(ROOT,'scenario','output','fig5','BAU_81_Annual.csv'))
rates<-function(x)paste0(paste(sprintf('%.2f%%',100*sort(unique(x))),collapse=' / '),'\nper year')
blocks<-list()
add<-function(y,titles,bodies) {
 n<-length(titles);left<-seq(1,99,length.out=n+1)
 for(i in seq_len(n))blocks[[length(blocks)+1]]<<-data.frame(xmin=left[i],xmax=left[i+1]-1,ymin=y,ymax=y+11,Title=titles[i],Body=bodies[i])
}
add(83,c('Sources','Vessel registry','Harmonisation','Activity and catch'),c('Five tuna RFMOs\nRegistry and authorisations\nCatch / effort records','Gear, flag and RFMO\nLength, tonnage, power\nBuild and exit years','Identifier deduplication\nUnit checks and PMM\nHistorical gap reconstruction','Gear-specific effort units\nCatch by species and year\nSpatial record keys'))
add(68,c('Fuel','Refrigerant','Gear','Bait','Hull'),c('Power, load and hours\nSFC and fuel factors\nCombustion + upstream','R22 charge and leakage\nAnnual release\nCharacterisation factor','Gear mass and lifetime\nMaterial emission factors','LL hooks and bait mass\nBait production factor','Hull mass and materials\nConstruction emission factor\nMaintenance and lifetime'))
add(53,c('Historical inventory','Spatial and species allocation'),c('Vessel-year life-cycle emissions\nMonte Carlo parameter / donor uncertainty\nPaired-draw cumulative ranges','Fleet-to-grid effort shares; catch conservation\nSpecies catch composition; tuna-only share\nGrid, species and RFMO intensity outputs'))
add(38,c('Stock and ecological response','Combined effort response','Economic response'),c('JABBA: directed catch + CPUE\nFour-chain sampling gate\nMeco: quota / biomass / technology','Meco x Mecon\nApplied once to operating effort\nCapacity and adoption remain separate','Fuel and carbon energy costs\nSame-pathway MGO reference\nMecon: effort elasticity -0.3'))
add(23,c('WEO','Capacity growth','Technology creep','Fleet turnover'),c('STEPS / APS / NZE',rates(b$Growth),rates(b$TechCreep),'Natural / renewal / forced\nAge and capacity rules'))
add(8,c('Quota rules','Fuel transition','Refrigeration','Consolidation'),c('Fixed catch vs harvest rate\nPrescribed species fractions\nTerminal biomass guard','WEO-bound fuel screening\nBlend and newbuild adoption\nPrices and life-cycle factors','R22 to liquid nitrogen\nElectricity-linked upstream emissions','Power-conserving replacements\nLarger group templates\nOperating-time factor 1 - 0.243 S'))
d<-do.call(rbind,blocks)
stages<-data.frame(y=c(96,81,66,51,36,21),Label=c('Data collection and preprocessing','Vessel-level historical life-cycle inventory','Historical totals and allocation','Biological and economic effort mechanisms','81 future configurations: 3 x 3 x 3 x 3','Mitigation packages compared with matched baselines'))
write.csv(d,file.path(HERE,'Extended_Fig2_PanelA_Framework.csv'),row.names=FALSE)
write.csv(stages,file.path(HERE,'Extended_Fig2_PanelA_Stages.csv'),row.names=FALSE)
write.csv(unique(b[c('WEO','Growth','Retirement','TechCreep')]),file.path(HERE,'Extended_Fig2_Scenario_Inputs.csv'),row.names=FALSE)
fig<-ggplot()+
 geom_rect(data=stages,aes(xmin=1,xmax=99,ymin=y-1,ymax=y+1),fill='#24789B')+
 geom_text(data=stages,aes(x=50,y=y,label=Label),colour='white',fontface='bold',size=2.4)+
 geom_rect(data=d,aes(xmin=xmin,xmax=xmax,ymin=ymin,ymax=ymax),fill='#E7F2F6',colour='white',linewidth=.3)+
 geom_rect(data=d,aes(xmin=xmin,xmax=xmax,ymin=ymax-2,ymax=ymax),fill='#469EB9')+
 geom_text(data=d,aes(x=(xmin+xmax)/2,y=ymax-1,label=Title),colour='white',fontface='bold',size=2.3)+
 geom_text(data=d,aes(x=(xmin+xmax)/2,y=ymin+4.5,label=Body),size=2.15,lineheight=1.15)+
 annotate('text',x=50,y=4,label='Preserved outputs: stock fits, annual scenarios, panel data and full-subset Shapley attribution',size=2.1,colour='#333333')+
 scale_x_continuous(limits=c(0,100),expand=c(0,0))+scale_y_continuous(limits=c(0,100),expand=c(0,0))+
 theme_void(base_family='Arial')+theme(plot.margin=margin(2,2,2,2,'mm'))
for(ext in c('pdf','png','tiff')) {
 options<-list(filename=file.path(HERE,paste0('Extended_Fig2_Framework_Audited.',ext)),plot=fig,width=183,height=190,units='mm',bg='white')
 if(ext=='pdf')options$device<-cairo_pdf
 if(ext=='png')options$dpi<-300
 if(ext=='tiff'){options$dpi<-900;options$compression<-'lzw'}
 do.call(ggsave,options)
}
write.csv(d,file.path(HERE,'Extended_Fig2_PanelA_Render_Data.csv'),row.names=FALSE)
