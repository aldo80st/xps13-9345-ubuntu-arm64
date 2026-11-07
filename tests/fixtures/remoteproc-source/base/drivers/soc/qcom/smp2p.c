/* Synthetic lexical fixture, NOT Linux source or working kernel code. */
static int qcom_smp2p_probe(struct platform_device *pdev) { return 0; }
static int qcom_smp2p_alloc_outbound_item(struct qcom_smp2p *smp2p) { return 0; }
static void qcom_smp2p_start_in(struct qcom_smp2p *smp2p) {}
static void qcom_smp2p_check_ssr(struct qcom_smp2p *smp2p) {}
static struct platform_driver qcom_smp2p_driver = {
 .probe = qcom_smp2p_probe,
 .driver = { .name = "qcom_smp2p" },
};
