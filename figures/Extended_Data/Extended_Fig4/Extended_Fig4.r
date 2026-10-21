arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
source(file.path(HERE,'Extended_Fig4_Decomposition.r'),encoding='UTF-8')
