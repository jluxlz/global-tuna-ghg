# Current C/F/T figure; former renderer preserved in the dated revision archive.
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
source(file.path(HERE,'Extended_Fig6_HCR.r'),encoding='UTF-8')
