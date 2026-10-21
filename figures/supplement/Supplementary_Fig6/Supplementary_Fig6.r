arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
source(file.path(HERE,'Supplementary_Fig6_JABBA_Diagnostics.r'),encoding='UTF-8')
