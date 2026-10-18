# Diagnostic data derive only from the preserved screened production fits.
library(dplyr); library(coda)
file_arg <- grep('^--file=', commandArgs(FALSE), value = TRUE)
HERE <- dirname(normalizePath(sub('^--file=', '', file_arg[1]), winslash = '/'))
DIR <- file.path(HERE, 'jabba_diagnostics')
ROOT <- normalizePath(file.path(HERE,'..','..','..'),winslash='/')
source(file.path(ROOT,'scenario','jabba_mcmc_qc.r'))
biomass <- indices <- conv <- all_parameters <- traces <- summaries <- ppcs <- list()
stocks <- c('SKJ', 'YFT', 'BET', 'ALB', 'SBT')
for (stock in stocks) {
  x <- readRDS(file.path(DIR, paste0(stock, '_fit.rds')))
  f <- x$fit; b <- readRDS(file.path(DIR, paste0(stock, '_BUGSoutput.rds')))
  stopifnot(as.character(x$source_md5) == as.character(tools::md5sum(file.path(HERE,
      '..','..','..','GHG_Calculation','Base_3_Spatial_Grid_Enriched.csv'))),
      abs(median(b$sims.array[, , 'r']) - f$estimates['r','mu']) < 1e-12)
  stopifnot(dim(b$sims.array)[2] == 4L,
            dim(b$sims.array)[1] == (f$settings$mcmc$ni-f$settings$mcmc$nb)/f$settings$mcmc$nt,
            x$PD_LL == 0.0186, x$PD_PS == 0.0426)
  t <- f$timeseries
  biomass[[stock]] <- data.frame(Stock = stock, Year = as.integer(dimnames(t)[[1]]),
    Median = t[, 'mu', 'BB0'], Lower = t[, 'lci', 'BB0'], Upper = t[, 'uci', 'BB0'])
  d <- f$diags; d$Stock <- stock
  ppd <- f$cpue.ppd
  for (i in seq_len(nrow(d))) {
    j <- match(d$name[i], dimnames(ppd)[[3]])
    if (is.na(j) && dim(ppd)[3] == 1) j <- 1
    k <- match(as.character(d$year[i]), dimnames(ppd)[[1]])
    d$Predictive_Lower[i] <- ppd[k, 'lci', j]
    d$Predictive_Upper[i] <- ppd[k, 'uci', j]
  }
  indices[[stock]] <- d
  sm <- rank_mcmc_qc(b,file.path(ROOT,'scenario','r_lib'));sm$Stock<-stock
  stopifnot(!any(sm$Screen_Fail))
  sm$Rhat<-sm$Rank_Rhat;sm$n.eff<-sm$ESS_Bulk
  conv[[stock]] <- sm
  full <- as.data.frame(b$summary)
  full$Parameter <- rownames(full); full$Stock <- stock
  # Classical package diagnostics for every monitored parameter; modern diagnostics
  # and the acceptance gate cover core parameters plus projection-relevant states.
  all_parameters[[stock]] <- full
  names_all <- dimnames(b$sims.array)[[3]]
  core <- sm$Parameter
  if (!length(core)) stop('Core MCMC parameters unavailable')
  for (parameter in core) {
    for (chain in seq_len(dim(b$sims.array)[2])) {
      vals <- if(parameter=='Terminal_B') b$sims.array[,chain,'K']*b$sims.array[,chain,'P[55]'] else b$sims.array[, chain, parameter]
      traces[[length(traces) + 1]] <- data.frame(Stock = stock, Parameter = parameter,
        Chain = chain, Draw = seq_along(vals), Value = vals)
    }
  }
  term <- tail(biomass[[stock]], 1)
  summaries[[stock]] <- data.frame(Stock=stock, r=f$estimates['r','mu'],
    K_Mt=f$estimates['K','mu'], B2024_Mt=tail(t[,'mu','B'],1),
    B2024_K=term$Median, B2024_K_lo=term$Lower, B2024_K_hi=term$Upper,
    MSY_Mt=f$estimates['MSY','mu'], ni=f$settings$mcmc$ni, nb=f$settings$mcmc$nb,
    nt=f$settings$mcmc$nt, nc=f$settings$mcmc$nc,
    Actual_Retained_Draws=prod(dim(b$sims.array)[1:2]),
    Package_Reported_nsaved=f$settings$mcmc$nsaved, CPUE_Series=length(unique(d$name)),
    Observations=nrow(d), RMSE_log=sqrt(mean(d$residual^2)),
    Coverage_95_Predictive=mean(d$obs >= d$Predictive_Lower & d$obs <= d$Predictive_Upper))
  if (is.data.frame(f$PPC)) {pp <- f$PPC; pp$Stock <- stock; ppcs[[stock]] <- pp}
}
write.csv(bind_rows(biomass), file.path(HERE,'Extended_Fig5_PanelA_Biomass.csv'),row.names=FALSE)
write.csv(bind_rows(indices), file.path(HERE,'Extended_Fig5_PanelB_CPUE_Fits.csv'),row.names=FALSE)
c <- bind_rows(conv)
c$Screen_Fail <- !is.finite(c$Rhat) | c$Rhat > 1.01 | c$ESS_Bulk < 400 | c$ESS_Tail < 400
write.csv(bind_rows(all_parameters),file.path(HERE,'Extended_Fig5_MCMC_All_Parameters.csv'),row.names=FALSE)
core <- c
write.csv(core,file.path(HERE,'Extended_Fig5_PanelCD_Core_MCMC.csv'),row.names=FALSE)
write.csv(bind_rows(traces),file.path(HERE,'Extended_Fig5_MCMC_Traces.csv'),row.names=FALSE)
s <- bind_rows(summaries) %>% left_join(core %>% group_by(Stock) %>%
  summarise(Max_Rhat=max(Rhat,na.rm=TRUE),Min_ESS=min(n.eff,na.rm=TRUE),Min_ESS_Tail=min(ESS_Tail,na.rm=TRUE),
    Core_Screen_Fail=any(Screen_Fail),.groups='drop'),by='Stock')
write.csv(s,file.path(HERE,'Extended_Fig5_Diagnostic_Summary.csv'),row.names=FALSE)
if(length(ppcs)) write.csv(bind_rows(ppcs),file.path(HERE,'Extended_Fig5_Posterior_Predictive_Checks.csv'),row.names=FALSE)
print(s)
