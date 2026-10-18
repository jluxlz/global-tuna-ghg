# ==============================================================================
# JABBA — Bayesian SPM for 5 tuna stocks (screened four-chain MCMC)
# ==============================================================================
# 2026-08-15 — NATIVE multi-CPUE for multi-gear species (BET, YFT):
#   each gear (LL, PS) is passed as its own CPUE column; JABBA estimates a
#   per-series catchability q and observation error via the joint likelihood
#   (precision-weighted geometric mean of the q-scaled series — the statistically
#   principled replacement for any manual blend). The old catch-weighted
#   aggregation had a dplyr variable-shadowing bug that silently turned the
#   weighted blend into an UNWEIGHTED SUM of the two gear indices:
#   `summarise(Catch = sum(Catch)/1e6, Index_raw = sum(Index*Catch)/sum(Catch))`
#   — the 2nd expression's `Catch` is the newly-created scalar, so the blend
#   collapsed to `sum(Index)`. Do NOT reintroduce any blend inside a
#   summarise() that reassigns a name already present as a column.
#   Single-gear species (SBT/SKJ/ALB) are unaffected — one series, same math.

library(JABBA)
library(dplyr)

DATA_DIR <- Sys.getenv("JABBA_DATA_DIR", "../GHG_Calculation")
OUT_DIR  <- Sys.getenv("JABBA_OUTPUT_DIR", "output")
DIAG_DIR <- Sys.getenv("JABBA_DIAGNOSTICS_DIR", file.path(OUT_DIR, "jabba_diagnostics"))
dir.create(OUT_DIR, showWarnings = FALSE)
dir.create(DIAG_DIR, recursive = TRUE, showWarnings = FALSE)
ROOT_DIR <- normalizePath(file.path(DATA_DIR, '..'), winslash = '/')
DIAGNOSTIC_LIB <- Sys.getenv('JABBA_DIAGNOSTIC_LIB', file.path(ROOT_DIR, 'scenario', 'r_lib'))
source(file.path(ROOT_DIR, 'scenario', 'jabba_mcmc_qc.r'))
SAMPLER_CONFIG <- read.csv(Sys.getenv('JABBA_SAMPLER_CONFIG',
  file.path(ROOT_DIR,'scenario','jabba_sampler_config.csv')),stringsAsFactors=FALSE)
stopifnot(!anyDuplicated(SAMPLER_CONFIG$Stock))
REFIT_DIR <- Sys.getenv('JABBA_REFIT_DIR', '')
source(file.path(ROOT_DIR,'scenario','jabba_qK_sampler.r'))
source(file.path(ROOT_DIR,'scenario','jabba_b0_sampler.r'))

df <- read.csv(file.path(DATA_DIR, "Base_3_Spatial_Grid_Enriched.csv"),
               fileEncoding = "UTF-8-BOM")
stopifnot(all(c("Year", "Organization", "Gear", "Total_Catch", "Standard_Effort") %in% names(df)))
df <- df[df$Year >= 1970 & df$Year <= 2024 & df$Total_Catch > 0 & df$Standard_Effort > 0, ]

# ---- Tech creep correction (Palomares & Pauly 2019) ----
Y_span <- 2024 - 1970  # 54 years
C_pct   <- 13.8 * Y_span^(-0.511)  # Eq.1
pd      <- C_pct / 100            # legacy fleet-average rate (LL default)
PD_PS   <- 0.0426                  # industrial purse-seine tech-creep rate
PD_LL   <- 0.0186                  # longline: fleet-average (Palomares & Pauly 2019)
cat(sprintf("Tech creep: Y=%d yr, C%%=%.2f%%, pd=%.5f\n", Y_span, C_pct, pd))

build_cpue <- function(data, catch_col = "Total_Catch", gears = c("LL", "PS"),
                       effort_orgs = NULL, min_share = 0.05, min_years = 20) {
  # effort_orgs: restrict to specific RFMOs (composition fix - SBT)
  if (!is.null(effort_orgs)) data <- data[data$Organization %in% effort_orgs, ]
  data <- data[data$Gear %in% gears, ]
  data_all <- data  # full directed-gear data (for the total catch input)
  # ---- organisation-share filter (2026-09-17) -------------------------------
  # Each (Gear x Organisation) unit becomes its own CPUE series with its own
  # catchability q in JABBA (native multi-series; the statistically principled
  # replacement for any manual blend). Units contributing < min_share of the
  # species' directed-gear catch, or spanning < min_years, are dropped as
  # noise series. This isolates fleet-composition effects: the old SKJ global
  # pool (high-CPUE WCPFC/IOTC fleets rising from 12 flags in 1970 to 40 in
  # 2024) inflated the pooled index 3.4x and JABBA read that as stock growth.
  org_tot <- data %>% group_by(Organization) %>%
    summarise(C = sum(.data[[catch_col]], na.rm = TRUE), .groups = "drop")
  keep_orgs <- org_tot$Organization[org_tot$C >= min_share * sum(org_tot$C)]
  data <- data[data$Organization %in% keep_orgs, ]
  go_yr <- data %>%
    group_by(Year, Gear, Organization) %>%
    summarise(Catch = sum(.data[[catch_col]], na.rm = TRUE),
              Effort = sum(Standard_Effort, na.rm = TRUE), .groups = "drop") %>%
    mutate(CPUE = ifelse(Effort > 0, Catch / Effort, NA_real_))
  series <- list()
  keys <- paste(go_yr$Gear, go_yr$Organization, sep = "_")
  for (k in unique(keys[order(keys)])) {
    gg <- go_yr[keys == k, ]
    if (nrow(gg) < min_years) next
    ref <- mean(gg$CPUE[gg$Year >= 2000], na.rm = TRUE)
    s <- gg %>% arrange(Year) %>%
      mutate(t = Year - 1970,  # correction base: series start of the whole dataset
             pd_g = if (grepl("^PS", k)) PD_PS else PD_LL,
             Index = (CPUE / ref) * (1 - pd_g)^t) %>%
      select(Year, Catch, Index)
    # zero-catch years -> NA, NOT 0 (JAGS logs the index; log(0) crashes)
    s$Index[s$Catch == 0] <- NA
    series[[k]] <- s[, c("Year", "Index")]
  }
  # Annual total catch (Mt) across ALL directed-gear organisations
  catch <- data_all %>% group_by(Year) %>%
    summarise(Catch = sum(.data[[catch_col]], na.rm = TRUE) / 1e6, .groups = "drop") %>%
    arrange(Year)
  list(series = series, catch = as.data.frame(catch))
}

# Species-specific CPUE: use ONLY gears that actually catch that species
# (one row = one effort for all species → must filter by gear dominance)
species_gears <- list(
  # ⚠️ BYCATCH SERIES EXCLUDED (user decision 2026-08-15): minority-gear series
  # are bycatch only (SKJ LL 0.05%, ALB PS 0.47%, SBT PS 1.5% in just 7 years)
  # and must NOT enter the fit. Bycatch CPUE violates the q = const assumption
  # behind CPUE = q·B: catchability is set by the TARGET species' behavior,
  # fleet tactics (FADs, targeting switches) and ground composition, so a
  # bycatch series tracks those confounders, not the stock (ALB PS showed a
  # 3.2× pseudo-decline driven by post-2000 PS effort expansion — run10 test
  # pulled ALB P2024 0.847→0.765 on 0.47% of catch). Fit 2026-08-15 with SKJ
  # LL + ALB PS included reproduced as run10; outputs of that run are
  # superseded. Only gears where the species is a DIRECT target are kept:
  SBT = c("LL"),        # LL only (98.5%; PS not viable: only 7 non-zero years,
                        #   dual-series test fit unchanged: P2024 0.131 vs 0.132)
  SKJ = c("PS"),        # PS only (99.95%)
  BET = c("LL","PS"),   # native multi-CPUE: 75.5% LL + 24.5% PS, both directed
  YFT = c("LL","PS"),   # native multi-CPUE: 76.5% PS + 23.5% LL, both directed
  ALB = c("LL")         # LL only (99.5%)
)
# Composition fix (2026-08-15): SBT catch is 100% CCSBT (98.9% LL), but the
# pooled CPUE divided SBT catch by GLOBAL LL effort (all 5 RFMOs). Non-SBT
# longline expansion (IOTC/WCPFC/ICCAT) inflated the denominator → false 15×
# index decline → B_2024/K = 0.052. Restricting effort to CCSBT (the fleet
# that actually catches SBT) gives a 3.1× decline → B_2024/K = 0.17,
# consistent with CCSBT's assessment (~0.2 of unfished). Other species are
# multi-org catches (SKJ/BET/YFT/ALB: max org share 35-66%, verified pooled vs
# org-restricted trends agree within 1.3×) → pooled effort retained.
effort_orgs <- list(
  SBT = "CCSBT",
  SKJ = NULL, BET = NULL, YFT = NULL, ALB = NULL
)

# ---- Fit JABBA with FishBase resilience priors ----
# Actual compiled r.prior convention: c(lognormal median, CV on original scale).
# CV=0.3→literature-anchored (prevents noisy CPUE from pulling r off-physics)
r_priors <- list(
  SBT = c(0.10, 0.3),   # SBT: slow-growing, r < 0.2 (CCSBT literature)
  SKJ = c(0.80, 0.2),   # SKJ: skipjack, r > 0.8 (fast-growing, literature ~1.0)
  BET = c(0.35, 0.3),
  YFT = c(0.40, 0.3),
  ALB = c(0.25, 0.3)
)

# psi = B_first/K priors c(mu, CV) — JABBA's psi is the depletion at the START
# of the fitted time series (1970), NOT the current (2024) depletion. Old
# c(0.3, 1.0) (CV=100%) was so diffuse that noisy indices parked posteriors at
# psi≈1 (near-virgin 1970 state). Informative priors keep the 1970 depletion
# physically sensible; they do NOT constrain the 2024 state (that is the job
# of the fitted terminal depletion P2024, see below).
psi_priors <- list(
  SBT = c(0.25, 0.35),
  SKJ = c(0.45, 0.3),
  BET = c(0.45, 0.3),
  YFT = c(0.50, 0.3),
  ALB = c(0.55, 0.3)
)

se_val <- 0.20
fits <- list()
cat("Stock   r      K(Mt)   B2024(Mt) B1970(Mt) MSY\n")
for (nm in names(species_gears)) {
  config <- SAMPLER_CONFIG[SAMPLER_CONFIG$Stock==nm,]
  stopifnot(nrow(config)==1)
  MCMC_NI <- as.integer(Sys.getenv('JABBA_NI',as.character(config$Iterations)))
  MCMC_NB <- as.integer(Sys.getenv('JABBA_NB',as.character(config$Burnin)))
  MCMC_NT <- as.integer(Sys.getenv('JABBA_NT',as.character(config$Thin)))
  MCMC_SEED <- as.integer(Sys.getenv('JABBA_SEED',as.character(config$Seed)))
  sampler <- Sys.getenv('JABBA_SAMPLER',config$Sampler)
  stopifnot(MCMC_NI > MCMC_NB, MCMC_NB>=5000, MCMC_NT>=1,
            sampler%in%c('centred','qK','B0'))
  sp_col <- paste0(nm, "_Tonnes")
  gears <- species_gears[[nm]]
  sp_df <- df[df$Gear %in% gears, ]
  cp <- build_cpue(sp_df, sp_col, gears, effort_orgs[[nm]])
  series <- cp$series
  catch_dat <- cp$catch  # base data.frame (Year, Catch) — NOT a tibble:
  # build_jabba indexes catch[, 1]; a tibble's [, 1] returns a tibble and the
  # sequential-year check fails on it (another silent trap, caught 2026-08-15).

  # --- JABBA cpue/se inputs: single series, or wide per-gear columns ---
  if (length(series) == 1) {
    s <- series[[1]]
    cpue_in <- data.frame(Year = s$Year, Index = s$Index)
  } else {
    cpue_in <- series[[1]]
    names(cpue_in)[2] <- names(series)[1]
    for (g in names(series)[-1]) {
      s <- series[[g]]
      names(s)[2] <- g
      cpue_in <- merge(cpue_in, s, by = "Year", all = TRUE)  # NA = series gap
    }
  }
  se_in <- cpue_in
  se_in[, -1] <- se_val  # same SE prior for all series; sigma.est re-estimates

  rp <- r_priors[[nm]]
  pp <- psi_priors[[nm]]
  # All five stocks fitted with the Schaefer (logistic) surplus production model:
  # P(B) = r*B*(1-B/K), B_MSY/K = 0.5, MSY = r*K/4
  mtype <- "Schaefer"
  Kp <- if (nm == "SBT") c(1, 5) else c(2, 80)
  jb <- tryCatch({
    build_jabba(
      catch = catch_dat,
      cpue  = cpue_in,
      se    = se_in,
      assessment = nm, model.type = mtype,
      r.prior = rp, r.dist = 'lnorm', K.prior = Kp, K.dist = 'lnorm',
      psi.prior = pp, psi.dist = 'lnorm')
  }, error = function(e) { cat(sprintf("  %s build err: %s\n", nm, e$message)); NULL })
  if (is.null(jb)) next
  # K is kept at the actual legacy log-median/CV convention. This is NOT a range.
  # Checking compiled priors guards the package's ambiguous mean terminology.
  stopifnot(isTRUE(all.equal(jb$jagsdata$K.pr,c(Kp[1],sqrt(log(Kp[2]^2+1))),tolerance=1e-12)))
  if(!nzchar(REFIT_DIR)) {
    fit_jabba <- switch(sampler,centred=JABBA::fit_jabba,
      qK=make_qK_fit(config$Initial_K_Mt),B0=make_b0_fit(config$Initial_K_Mt))
    trace('fit_jabba',where=.GlobalEnv,print=FALSE,exit=quote({
      b<-mod$BUGSoutput
      saveRDS(list(sims.array=b$sims.array,summary=b$summary),
        file.path(DIAG_DIR,paste0(assessment,'_BUGSoutput.rds')))
    }))
  }

  fit <- tryCatch({
    if (nzchar(REFIT_DIR)) {
      refit <- readRDS(file.path(REFIT_DIR, paste0(nm, '_fit.rds')))
      stopifnot(as.character(refit$source_md5) == as.character(tools::md5sum(
        file.path(DATA_DIR, 'Base_3_Spatial_Grid_Enriched.csv'))),
        isTRUE(all.equal(refit$input$jagsdata, jb$jagsdata, tolerance=0)),
        isTRUE(all.equal(refit$cpue, cpue_in, tolerance=0)),
        isTRUE(all.equal(refit$catch, catch_dat, tolerance=0)),
        refit$PD_LL == PD_LL, refit$PD_PS == PD_PS)
      file.copy(file.path(REFIT_DIR, paste0(nm, '_BUGSoutput.rds')),
                file.path(DIAG_DIR, paste0(nm, '_BUGSoutput.rds')), overwrite=TRUE)
      refit$fit
    } else {
      fit_jabba(jb, save.csvs = FALSE, output.dir = OUT_DIR,
        quickmcmc = FALSE, nb=MCMC_NB, ni=MCMC_NI, nt=MCMC_NT, nc=4, seed=MCMC_SEED)
    }
  }, error = function(e) { cat(sprintf("  %s fit err: %s\n", nm, e$message)); NULL })
  if(!nzchar(REFIT_DIR)) untrace('fit_jabba',where=.GlobalEnv)
  if (is.null(fit)) next
  actual_sampler <- if(nzchar(REFIT_DIR) && !is.null(refit$sampler)) refit$sampler else sampler
  # Retain failed as well as passing fits; no output projection is written until all pass.
  saveRDS(list(fit=fit,input=jb,cpue=cpue_in,se=se_in,catch=catch_dat,
    source_md5=tools::md5sum(file.path(DATA_DIR,'Base_3_Spatial_Grid_Enriched.csv')),
    PD_LL=PD_LL,PD_PS=PD_PS,package_version=as.character(packageVersion('JABBA')),
    sampler=actual_sampler,sampling_seed=if(nzchar(REFIT_DIR)) refit$sampling_seed else MCMC_SEED,prior_change=FALSE),
    file.path(DIAG_DIR,paste0(nm,'_fit.rds')))
  raw_chains <- readRDS(file.path(DIAG_DIR, paste0(nm, '_BUGSoutput.rds')))
  mcmc_qc <- rank_mcmc_qc(raw_chains, DIAGNOSTIC_LIB, trajectory=TRUE)
  write.csv(mcmc_qc, file.path(DIAG_DIR, paste0(nm, '_Rank_Diagnostics.csv')), row.names=FALSE)
  if (any(mcmc_qc$Screen_Fail)) {
    stop(sprintf('%s MCMC did not pass rank Rhat <=1.01 and bulk/tail ESS >=400. No projections written.', nm))
  }

  # Preserve the actual fitted object and inputs before any projection.
  # Preserve actual array dimensions and settings; quick MCMC is not production.
  write.csv(cpue_in, file.path(DIAG_DIR, paste0(nm, "_CPUE_Input.csv")), row.names = FALSE)
  write.csv(catch_dat, file.path(DIAG_DIR, paste0(nm, "_Catch_Input.csv")), row.names = FALSE)
  write.csv(fit$diags, file.path(DIAG_DIR, paste0(nm, "_Fit_Diagnostics.csv")), row.names = FALSE)
  write.csv(fit$estimates, file.path(DIAG_DIR, paste0(nm, "_Estimates.csv")))
  write.csv(as.data.frame(fit$settings$mcmc),
            file.path(DIAG_DIR, paste0(nm, "_MCMC_Settings.csv")), row.names = FALSE)

  r   <- fit$estimates["r", "mu"]
  K   <- fit$estimates["K", "mu"]
  psi <- fit$estimates["psi", "mu"]
  # Consistent deterministic point parameters, rather than rounded package refpoints.
  MSY <- r*K/4
  Hmsy <- r/2
  # ⚠️ JABBA parameterization: psi = B[1]/K — depletion at the START of the
  # fitted time series (1970). It is NOT the current depletion. The projection
  # must start from the fitted TERMINAL biomass (2024): the last row of the
  # fitted trajectory fit$timeseries[,"mu","B"] (equivalently P2024 = B_2024/K
  # in the estimates table). Old bug: B <- psi*K started the 2024-2050
  # projection from B_1970, shifting the whole trajectory 55 years late.
  B_1970 <- psi * K
  B_2024 <- as.numeric(tail(fit$timeseries[, "mu", "B"], 1))
  B <- B_2024
  catch_2024 <- as.numeric(tail(catch_dat$Catch, 1))
  fits[[nm]] <- list(r = r, K = K, B = B, MSY = MSY, Hmsy = Hmsy,
                     catch24 = catch_2024)
  cat(sprintf("%-5s %.3f %7.1f %8.2f %8.2f %7.2f\n",
              nm, r, K, B_2024, B_1970, MSY))
}

# ---- Hard completeness check (a JAGS failure must NOT silently drop a stock) ----
missing <- setdiff(names(species_gears), names(fits))
if (length(missing)) {
  stop(sprintf("FIT FAILED for: %s — output CSVs would be incomplete. Fix before projecting.",
               paste(missing, collapse = ", ")))
}
write.csv(do.call(rbind,lapply(names(fits),function(s) {
 f<-fits[[s]];data.frame(Stock=s,r=f$r,K_Mt=f$K,B2024_Mt=f$B,
   B2024_K_Point=f$B/f$K,MSY_Point_Mt=f$MSY,FMSY_Point=f$Hmsy,
   Catch2024_Mt=f$catch24,Method='Posterior medians of r,K,terminal B; MSY=r*K/4; FMSY=r/2')
})),file.path(OUT_DIR,'schaefer_projection_parameters.csv'),row.names=FALSE)

# ---- Projections: 4 MSY-based scenarios × 2 quota designs ----
# C-type (fixed catch):  C_t = frac * MSY          (absolute catch quota)
# F-type (harvest rate): C_t = frac * F_MSY * B_t  (proportional quota, HCR-style)
#   F_MSY = Hmsy = r/2 for Schaefer. F-type self-limits with biomass → each
#   frac converges to B*/K = 1 - frac/2 (MSY_100→0.50, MSY_90→0.55, MSY_80→0.60,
#   MSY_70→0.65); C-type from below B_MSY collapses (one-way-trip) unless
#   catch < current surplus production. Both written as separate CSVs.
scens <- list(
  MSY_100 = 1.00,  # catch = 100% MSY (sustainable limit)
  MSY_90  = 0.90,  # catch = 90% MSY
  MSY_80  = 0.80,  # catch = 80% MSY
  MSY_70  = 0.70   # catch = 70% MSY (precautionary rebuild)
)

proj  <- data.frame()  # C-type: output/schaefer_biomass_annual.csv   (downstream default)
projF <- data.frame()  # F-type: output/schaefer_biomass_annual_F.csv (comparison variant)
for (nm in names(fits)) {
  f <- fits[[nm]]
  catch_2024 <- f$catch24
  msy_val <- f$MSY
  fmsy <- f$Hmsy  # = r/2 (Schaefer)
  # Schaefer (logistic) surplus production: P(B) = r*B*(1-B/K) — the same form
  # used in the JABBA fit (model.type = "Schaefer" for all stocks), so the
  # projection is model-consistent: B_{t+1} = B_t + r*B_t*(1-B_t/K) - C_t

  # --- C2024 (BAU): catch FIXED at the 2024 ACTUAL level (user-specified,
  #     NOT predicted), biomass evolves per the Schaefer model. quota_ratio = 1
  #     by construction (C_t / catch_2024 ≡ 1). User directive 2026-08-28. ---
  future_catch <- catch_2024
  quota_r <- 1.0
  B <- f$B; K <- f$K; rs <- f$r
  for (y in 2024:2050) {
    proj <- rbind(proj, data.frame(Year = y, Stock = nm, Scenario = "C2024",
      biomass_ratio = B / f$B, quota_ratio = quota_r,
      Catch_Mt = future_catch, Biomass_Mt = B,
      K_Mt = K))
    if (y < 2050) {
      B <- max(B + rs * B * (1 - B / K) - future_catch, K * 0.03)  # floor backstop only
    }
  }

  for (sc in names(scens)) {
    frac <- scens[[sc]]
    # --- C-type: fixed absolute catch ---
    future_catch <- msy_val * frac
    quota_r <- future_catch / catch_2024
    B <- f$B; K <- f$K; rs <- f$r  # fixed biological parameters
    for (y in 2024:2050) {
      proj <- rbind(proj, data.frame(Year = y, Stock = nm, Scenario = sc,
        biomass_ratio = B / f$B, quota_ratio = quota_r,
        Catch_Mt = future_catch, Biomass_Mt = B,
        K_Mt = K))
      if (y < 2050) {
        B <- max(B + rs * B * (1 - B / K) - future_catch, K * 0.03)  # floor backstop only
      }
    }
    # --- F-type: harvest rate on current biomass (quota_ratio time-varying) ---
    B <- f$B; K <- f$K; rs <- f$r
    for (y in 2024:2050) {
      catch_t <- frac * fmsy * B
      projF <- rbind(projF, data.frame(Year = y, Stock = nm, Scenario = sc,
        biomass_ratio = B / f$B,
        quota_ratio = catch_t / catch_2024,
        Catch_Mt = catch_t, Biomass_Mt = B,
        K_Mt = K))
      if (y < 2050) {
        B <- max(B + rs * B * (1 - B / K) - catch_t, K * 0.03)  # backstop (never hit)
      }
    }
    cat(sprintf("%-4s %s: C_ratio2050=%.3f  F_ratio2050=%.3f\n", nm, sc,
      tail(proj[proj$Stock == nm & proj$Scenario == sc, "biomass_ratio"], 1),
      tail(projF[projF$Stock == nm & projF$Scenario == sc, "biomass_ratio"], 1)))
  }
}

write.csv(proj,  file.path(OUT_DIR, "schaefer_biomass_annual.csv"),   row.names = FALSE)
write.csv(projF, file.path(OUT_DIR, "schaefer_biomass_annual_F.csv"), row.names = FALSE)
cat(sprintf("Done: C-type %d rows, F-type %d rows\n", nrow(proj), nrow(projF)))
