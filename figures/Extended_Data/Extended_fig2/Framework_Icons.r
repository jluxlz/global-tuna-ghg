# Small vector line illustrations, expressed as paths rather than raster icons.
# All coordinates are schematic and carry no empirical data.
icon_paths <- list(); icon_dots <- list(); icon_id <- 0L
framework_icon <- function(kind,x,y,s=3,colour='#426B79') {
  path <- function(a,b) {
    icon_id <<- icon_id+1L
    icon_paths[[length(icon_paths)+1L]] <<- data.frame(x=x+s*a,y=y+s*b,
      group=icon_id,colour=colour,icon=kind)
  }
  dot <- function(a,b) icon_dots[[length(icon_dots)+1L]] <<-
    data.frame(x=x+s*a,y=y+s*b,colour=colour,icon=kind)
  ellipse <- function(a=0,b=0,rx=.8,ry=.8) {
    t<-seq(0,2*pi,length.out=50);path(a+rx*cos(t),b+ry*sin(t))
  }
  if(kind=='boat') {
    path(c(-1,1,.65,-.65,-1),c(-.2,-.2,-.65,-.65,-.2))
    path(c(-.55,-.55,.45,.45),c(-.2,.35,.35,-.2))
    path(c(.1,.1),c(.35,.85));path(c(-1.1,-.7,-.3,.1,.5,.9),c(-.9,-.8,-.9,-.8,-.9,-.8))
    path(c(-.3,-.05),c(.12,.12));path(c(.15,.35),c(.12,.12))
  } else if(kind=='fish') {
    t<-seq(.1,2*pi-.1,length.out=50);path(-.1+.8*cos(t),.38*sin(t))
    path(c(.69,1.15,1.15,.69),c(0,.43,-.43,0));dot(-.55,.1)
    path(c(-.15,.1,.3),c(.36,.63,.33))
  } else if(kind=='sliders') {
    for(i in 1:3){yy<-c(.55,0,-.55)[i];xx<-c(-.35,.35,-.1)[i]
      path(c(-.9,.9),c(yy,yy));ellipse(xx,yy,.13,.13)}
  } else if(kind=='fuel') {
    path(c(-.65,-.65,.45,.45,-.65),c(-.8,.7,.7,-.8,-.8))
    path(c(-.45,-.45,.25,.25,-.45),c(.45,.1,.1,.45,.45))
    path(c(.45,.8,.85,.75,.5),c(.55,.35,-.55,-.7,-.55))
    path(c(-.85,.7),c(-.85,-.85))
  } else if(kind=='snow') {
    for(a in seq(0,5)*pi/3) {
      path(c(0,cos(a)),c(0,sin(a)))
      for(b in c(-1,1)) path(c(.62*cos(a),.62*cos(a)+.28*cos(a+b*pi/3)),
                           c(.62*sin(a),.62*sin(a)+.28*sin(a+b*pi/3)))
    }
  } else if(kind=='gear') {
    for(v in seq(-.8,.8,length.out=5)) {
      path(c(v,v),c(-.8,.8));path(c(-.8,.8),c(v,v))
    }
  } else if(kind=='bait') {
    t<-seq(pi,2*pi,length.out=30);path(.48*cos(t),-.15+.48*sin(t))
    path(c(.48,.48,.25),c(-.15,.9,.65));ellipse(.48,1,.1,.1)
  } else if(kind=='globe') {
    ellipse();ellipse(0,0,.35,.8)
    path(c(-.8,.8),c(0,0));path(c(-.65,.65),c(.4,.4));path(c(-.65,.65),c(-.4,-.4))
  } else if(kind=='chart') {
    path(c(-.9,-.9,.9),c(.85,-.8,-.8))
    path(c(-.7,-.3,.1,.45,.8),c(-.5,-.1,-.3,.3,.65))
  } else if(kind=='quota') {
    path(c(-.65,-.65,.65,.65,-.65),c(-.85,.85,.85,-.85,-.85))
    for(yy in c(.45,0,-.45)){dot(-.35,yy);path(c(-.1,.4),c(yy,yy))}
  } else if(kind=='fleet') {
    path(c(-1.1,.4,.1,-.8,-1.1),c(-.35,-.35,-.8,-.8,-.35))
    path(c(-.75,-.75,.05,.05),c(-.35,.15,.15,-.35))
    path(c(-.5,1,.7,-.2),c(.05,.05,-.35,-.35))
    path(c(-.1,-.1,.6,.6),c(.05,.65,.65,.05))
  } else stop('Unknown framework icon: ',kind)
}
