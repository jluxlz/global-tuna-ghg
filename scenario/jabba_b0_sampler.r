# Exact initial-biomass parameterisation of the same state-space model.
# B0=K*psi, kappa=q*B0, U[t]=P[t]/psi. Priors include their exact Jacobians.
make_b0_fit<-function(K_guess_Mt) {
  stopifnot(is.finite(K_guess_Mt),K_guess_Mt>0)
  transform_b0_model<-function(path) {
    original<-readLines(path,warn=FALSE);model<-paste(original,collapse='\n')
    Kold<-'K ~ dlnorm(log(K.pr[1]),pow(K.pr[2], -2))'
    if(!grepl(Kold,model,fixed=TRUE)) stop('Unexpected K prior; B0 sampler stopped')
    changed<-gsub(Kold,'B0 ~ dlnorm(log(K.pr[1])+log(psi),pow(K.pr[2],-2))\n    K <- B0/psi',model,fixed=TRUE)
    pattern<-'q\\[([^]]+)\\]\\s*~\\s*dunif\\(([^,]+),([^\\)]+)\\)'
    if(gregexpr(pattern,changed,perl=TRUE)[[1]][1]<0) stop('Uniform q prior required')
    changed<-gsub(pattern,'qB0[\\1] ~ dunif((\\2)*B0,(\\3)*B0)\n    q[\\1] <- qB0[\\1]/B0',changed,perl=TRUE)
    if(grepl('q\\[[^]]+\\]\\s*~',changed,perl=TRUE)) stop('Unsupported remaining q prior')
    first<-'P[1] ~ dlnorm(Pmean[1],iPV[1])'
    later<-'P[t] ~ dlnorm(Pmean[t],iPV[t]*iprocdyn[t-1])'
    stopifnot(grepl(first,changed,fixed=TRUE),grepl(later,changed,fixed=TRUE))
    changed<-gsub(first,'U[1] ~ dlnorm(Pmean[1]-log(psi),iPV[1])\n    P[1] <- psi*U[1]',changed,fixed=TRUE)
    changed<-gsub(later,'U[t] ~ dlnorm(Pmean[t]-log(psi),iPV[t]*iprocdyn[t-1])\n    P[t] <- psi*U[t]',changed,fixed=TRUE)
    changed<-gsub('log(q[sets.q[i]]*P[t]*K)','log(qB0[sets.q[i]]*U[t])',changed,fixed=TRUE)
    writeLines(original,paste0(path,'.original'));writeLines(changed,path)
  }
  f<-JABBA::fit_jabba;expressions<-as.list(body(f))[-1]
  at<-which(vapply(expressions,function(x)grepl('R2jags::jags',paste(deparse(x),collapse=' '),fixed=TRUE),logical(1)))
  stopifnot(length(at)==1)
  insert<-quote({
    transform_b0_model(file.path(tmpath,'JABBA.jags'))
    old_inits<-inits
    inits<-function() {
      z<-old_inits();K0<-rlnorm(1,log(K_guess_Mt/mucatch),.6)
      z$B0<-K0*z$psi;z$qB0<-z$q*z$B0
      z$K<-NULL;z$q<-NULL;z
    }
  })
  body(f)<-as.call(c(list(as.name('{')),expressions[seq_len(at-1)],list(insert),expressions[at:length(expressions)]))
  env<-new.env(parent=environment(JABBA::fit_jabba));env$transform_b0_model<-transform_b0_model;env$K_guess_Mt<-K_guess_Mt
  environment(f)<-env;f
}
