# Exact reparameterisation: kappa=q*K, kappa|K ~ Uniform(K*a,K*b).
# q=kappa/K retains the original q prior after the transformation Jacobian.
# Applies only to the current uniform-q, no-auxiliary model. Does not change priors.
make_qK_fit<-function(K_guess_Mt) {
  stopifnot(is.finite(K_guess_Mt),K_guess_Mt>0)
  transform_qK_model<-function(path) {
    original<-readLines(path,warn=FALSE)
    model<-paste(original,collapse='\n')
    pattern<-'q\\[([^]]+)\\]\\s*~\\s*dunif\\(([^,]+),([^\\)]+)\\)'
    matches<-gregexpr(pattern,model,perl=TRUE)[[1]]
    if(matches[1]<0) stop('Expected uniform q prior absent; cannot apply qK sampler')
    changed<-gsub(pattern,'qK[\\1] ~ dunif((\\2)*K,(\\3)*K)\n    q[\\1] <- qK[\\1]/K',model,perl=TRUE)
    changed<-gsub('log(q[sets.q[i]]*P[t]*K)','log(qK[sets.q[i]]*P[t])',changed,fixed=TRUE)
    if(grepl('q\\[[^]]+\\]\\s*~',changed,perl=TRUE)) stop('Unsupported remaining stochastic q prior')
    writeLines(original,paste0(path,'.original'))
    writeLines(changed,path)
  }
  f<-JABBA::fit_jabba
  expressions<-as.list(body(f))[-1]
  at<-which(vapply(expressions,function(x) grepl('R2jags::jags',paste(deparse(x),collapse=' '),fixed=TRUE),logical(1)))
  stopifnot(length(at)==1)
  insert<-quote({
    transform_qK_model(file.path(tmpath,'JABBA.jags'))
    old_inits<-inits
    inits<-function() {
      z<-old_inits()
      # Overdispersed physically plausible starts; this affects burn-in only.
      z$K<-rlnorm(1,log(K_guess_Mt/mucatch),.6)
      z$qK<-z$q*z$K;z$q<-NULL
      z
    }
  })
  body(f)<-as.call(c(list(as.name('{')),expressions[seq_len(at-1)],list(insert),expressions[at:length(expressions)]))
  env<-new.env(parent=environment(JABBA::fit_jabba))
  env$transform_qK_model<-transform_qK_model;env$K_guess_Mt<-K_guess_Mt
  environment(f)<-env
  f
}
