/* Synthetic lexical fixture, NOT Linux source or working kernel code. */
static int qcom_pas_probe(struct platform_device *pdev) { return 0; }
static int qcom_pas_stop(struct rproc *rproc) { return 0; }
static struct platform_driver qcom_pas_driver = {
 .probe = qcom_pas_probe,
 .driver = { .name = "qcom_q6v5_pas" },
};
