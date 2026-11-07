/* Synthetic lexical fixture, NOT Linux source or working kernel code. */
static int rproc_start(struct rproc *rproc, const struct firmware *fw) { return 0; }
int rproc_boot(struct rproc *rproc) { return 0; }
static int __rproc_shutdown(struct rproc *rproc) { return 0; }
static int rproc_stop(struct rproc *rproc, bool crashed) { return 0; }
