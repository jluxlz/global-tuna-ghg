# Compatibility entry: unsupported assessment concordance was retired.
arg <- grep("^--file=",commandArgs(FALSE),value=TRUE)
HERE <- dirname(normalizePath(sub("^--file=","",arg[1]),winslash="/"))
source(file.path(HERE,"Extended_Fig5_JABBA_Diagnostics.r"))
