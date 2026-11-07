/* Synthetic proposal-shaped fixture; no firmware implementation. */
static int qcom_smp2p_probe(struct platform_device *pdev) { return 0; }
static int qcom_smp2p_alloc_outbound_item(struct qcom_smp2p *smp2p) { return 0; }
static void qcom_smp2p_start_in(struct qcom_smp2p *smp2p) {}
static void qcom_smp2p_check_ssr(struct qcom_smp2p *smp2p) {}
static void qcom_smp2p_claim_outbound_entry(struct qcom_smp2p *smp2p,
                                         struct smp2p_entry *entry) {}
static int qcom_smp2p_restore_noirq(struct device *dev)
{
 struct qcom_smp2p *smp2p = dev_get_drvdata(dev);
 struct smp2p_entry *entry;
 int ret;
 smp2p->in = NULL;
 smp2p->valid_entries = 0;
 smp2p->negotiation_done = false;
 smp2p->ssr_ack_enabled = false;
 smp2p->ssr_ack = false;
 list_for_each_entry(entry, &smp2p->inbound, node) {
  entry->value = NULL;
  entry->last_value = 0;
 }
 ret = qcom_smp2p_alloc_outbound_item(smp2p);
 if (ret < 0)
  return ret;
 list_for_each_entry_reverse(entry, &smp2p->outbound, node)
  qcom_smp2p_claim_outbound_entry(smp2p, entry);
 qcom_smp2p_start_in(smp2p);
 qcom_smp2p_kick(smp2p);
 return 0;
}
static const struct dev_pm_ops qcom_smp2p_pm_ops = {
 .restore_noirq = pm_sleep_ptr(qcom_smp2p_restore_noirq),
};
static struct platform_driver qcom_smp2p_driver = {
 .probe = qcom_smp2p_probe,
 .driver = { .name = "qcom_smp2p", .pm = &qcom_smp2p_pm_ops },
};
