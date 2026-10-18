# Current publication renderer; original author artwork remains read-only.
arg<-grep('^--file=',commandArgs(FALSE),value=TRUE)
HERE<-dirname(normalizePath(sub('^--file=','',arg[1]),winslash='/'))
source(file.path(HERE,'Extended_Fig2_Model_Framework.r'))
