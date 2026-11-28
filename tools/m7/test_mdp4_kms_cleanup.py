#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Source guards for MDP4 KMS initialization."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MDP4_KMS = ROOT / "drivers/gpu/drm/msm/disp/mdp4/mdp4_kms.c"
MSM_DRV = ROOT / "drivers/gpu/drm/msm/msm_drv.c"
MSM_IOMMU = ROOT / "drivers/gpu/drm/msm/msm_iommu.c"
MSM_IOMMU_CORE = ROOT / "drivers/iommu/msm_iommu.c"


def function_body(source, declaration):
    match = re.search(rf"{declaration}\(.*?\n\}}", source, re.DOTALL)
    if not match:
        raise AssertionError(f"{declaration}() not found")
    return match.group(0)


class Mdp4KmsCleanupTest(unittest.TestCase):
    def test_failed_backend_init_leaves_destruction_to_drm_core(self):
        init = function_body(MDP4_KMS.read_text(), r"static int mdp4_kms_init")
        uninit = function_body(MSM_DRV.read_text(), r"static int msm_drm_uninit")

        self.assertNotIn("mdp4_destroy(kms)", init)
        self.assertRegex(
            uninit,
            r"if \(priv->kms\)\s+msm_drm_kms_uninit\(dev\);",
        )

    def test_vm_initialization_failure_reports_its_errno(self):
        init = function_body(MDP4_KMS.read_text(), r"static int mdp4_kms_init")
        failure = re.search(
            r"vm = msm_kms_init_vm\(.*?if \(IS_ERR\(vm\)\) \{(.*?)\n\t\}",
            init,
            re.DOTALL,
        )

        self.assertIsNotNone(failure)
        self.assertIn("ret = PTR_ERR(vm);", failure.group(1))
        self.assertIn('DRM_DEV_ERROR(dev->dev, "failed to initialize VM: %d\\n", ret);', failure.group(1))

    def test_clock_enable_failure_unwinds_enabled_clocks(self):
        enable = function_body(MDP4_KMS.read_text(), r"int mdp4_enable")

        self.assertIn("struct clk *clks[]", enable)
        self.assertIn("ret = clk_prepare_enable(clks[i]);", enable)
        self.assertIn('"failed to enable %s clock: %d\\n"', enable)
        self.assertIn("while (i--)", enable)
        self.assertIn("clk_disable_unprepare(clks[i]);", enable)
        self.assertIn('pr_emerg("M7_MDP4_CLOCKS_BEGIN\\n");', enable)
        self.assertIn('pr_emerg("M7_MDP4_CLOCKS_FAIL %s %d\\n", clk_names[i], ret);', enable)
        self.assertIn('pr_emerg("M7_MDP4_CLOCKS_DONE\\n");', enable)

    def test_revision_read_checks_clocks_and_logs_mmio_milestone(self):
        source = MDP4_KMS.read_text()
        revision = function_body(source, r"static int read_mdp_hw_revision")
        init = function_body(source, r"static int mdp4_kms_init")

        self.assertIn("ret = mdp4_enable(mdp4_kms);", revision)
        self.assertRegex(revision, r"if \(ret\)\s+return ret;")
        self.assertIn('pr_emerg("M7_MDP4_REVISION_MMIO_BEGIN\\n");', revision)
        self.assertLess(
            revision.index("M7_MDP4_REVISION_MMIO_BEGIN"),
            revision.index("mdp4_read(mdp4_kms, REG_MDP4_VERSION)"),
        )
        self.assertIn("ret = read_mdp_hw_revision(mdp4_kms, &major, &minor);", init)
        self.assertRegex(init, r"if \(ret\)\s+goto fail;")

    def test_pre_vm_mmio_checks_clocks_and_logs_boundaries(self):
        init = function_body(MDP4_KMS.read_text(), r"static int mdp4_kms_init")

        self.assertIn('pr_emerg("M7_MDP4_PRE_VM_CLOCKS_BEGIN\\n");', init)
        self.assertIn("ret = mdp4_enable(mdp4_kms);", init)
        self.assertRegex(
            init,
            r"ret = mdp4_enable\(mdp4_kms\);\s+if \(ret\)\s+goto fail;",
        )
        self.assertIn('pr_emerg("M7_MDP4_PRE_VM_MMIO_BEGIN\\n");', init)
        self.assertIn('pr_emerg("M7_MDP4_PRE_VM_MMIO_DONE\\n");', init)
        self.assertLess(
            init.index("M7_MDP4_PRE_VM_MMIO_BEGIN"),
            init.index("mdp4_write(mdp4_kms, REG_MDP4_DTV_ENABLE, 0);"),
        )
        self.assertLess(
            init.index("mdp4_write(mdp4_kms, REG_MDP4_DSI_ENABLE, 0);"),
            init.index("M7_MDP4_PRE_VM_MMIO_DONE"),
        )

    def test_vm_initialization_has_persistent_boundaries(self):
        init = function_body(MDP4_KMS.read_text(), r"static int mdp4_kms_init")

        self.assertIn('pr_emerg("M7_MDP4_VM_INIT_BEGIN\\n");', init)
        self.assertIn('pr_emerg("M7_MDP4_VM_INIT_DONE\\n");', init)
        self.assertLess(
            init.index("M7_MDP4_VM_INIT_BEGIN"),
            init.index("vm = msm_kms_init_vm"),
        )
        self.assertLess(
            init.index("kms->vm = vm;"),
            init.index("M7_MDP4_VM_INIT_DONE"),
        )


class M7DsiStartupTraceTest(unittest.TestCase):
    def setUp(self):
        self.manager = (ROOT / "drivers/gpu/drm/msm/dsi/dsi_manager.c").read_text()
        self.host = (ROOT / "drivers/gpu/drm/msm/dsi/dsi_host.c").read_text()
        self.phy = (ROOT / "drivers/gpu/drm/msm/dsi/phy/dsi_phy.c").read_text()
        self.panel = (ROOT / "drivers/gpu/drm/panel/panel-htc-m7ul.c").read_text()

    def test_manager_marks_phy_power_host_irq_and_bridge_enable(self):
        power_on = function_body(self.manager, r"static int dsi_mgr_bridge_power_on")
        pre_enable = function_body(self.manager, r"static void dsi_mgr_bridge_pre_enable")

        self.assertIn('pr_emerg("M7_DSI_PHY_ENABLE_BEGIN %d\\n", id);', power_on)
        self.assertIn('pr_emerg("M7_DSI_PHY_ENABLE_DONE %d\\n", id);', power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_POWER_ON_BEGIN %d\\n", id);', power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_POWER_ON_DONE %d\\n", id);', power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_IRQ_ENABLE_BEGIN %d\\n", id);', power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_IRQ_ENABLE_DONE %d\\n", id);', power_on)

        self.assertIn('pr_emerg("M7_DSI_PRE_ENABLE_BEGIN %d\\n", id);', pre_enable)
        self.assertIn('pr_emerg("M7_DSI_BRIDGE_POWER_ON_BEGIN %d\\n", id);', pre_enable)
        self.assertIn('pr_emerg("M7_DSI_BRIDGE_POWER_ON_DONE %d\\n", id);', pre_enable)
        self.assertIn('pr_emerg("M7_DSI_HOST_ENABLE_BEGIN %d\\n", id);', pre_enable)
        self.assertIn('pr_emerg("M7_DSI_HOST_ENABLE_DONE %d\\n", id);', pre_enable)
        self.assertIn('pr_emerg("M7_DSI_PRE_ENABLE_DONE %d\\n", id);', pre_enable)
        self.assertLess(
            pre_enable.index("M7_DSI_BRIDGE_POWER_ON_BEGIN"),
            pre_enable.index("M7_DSI_HOST_ENABLE_BEGIN"),
        )
        self.assertLess(
            pre_enable.index("M7_DSI_HOST_ENABLE_DONE"),
            pre_enable.index("M7_DSI_PRE_ENABLE_DONE"),
        )
        self.assertIn("dsi_mgr_bridge_power_on(bridge);", pre_enable)

    def test_host_power_on_checks_pm_runtime_resume(self):
        power_on = function_body(self.host, r"int msm_dsi_host_power_on")

        self.assertIn("ret = pm_runtime_get_sync(&msm_host->pdev->dev);", power_on)
        self.assertIn("pm_runtime_put_noidle(&msm_host->pdev->dev);", power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_PM_BEGIN\\n");', power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_PM_DONE\\n");', power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_LINK_CLK_BEGIN\\n");', power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_PINCTRL_BEGIN\\n");', power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_MMIO_BEGIN\\n");', power_on)
        self.assertIn('pr_emerg("M7_DSI_HOST_MMIO_DONE\\n");', power_on)

    def test_phy_enable_marks_each_phase(self):
        enable = function_body(self.phy, r"int msm_dsi_phy_enable")

        for marker in (
            "M7_DSI_PHY_PM_BEGIN",
            "M7_DSI_PHY_PM_DONE",
            "M7_DSI_PHY_REGULATOR_BEGIN",
            "M7_DSI_PHY_REGULATOR_DONE",
            "M7_DSI_PHY_PROGRAM_BEGIN",
            "M7_DSI_PHY_PROGRAM_DONE",
            "M7_DSI_PHY_PLL_RESTORE_BEGIN",
            "M7_DSI_PHY_PLL_RESTORE_DONE",
        ):
            self.assertIn(f'pr_emerg("{marker}\\n");', enable)

    def test_panel_marks_power_and_command_progress(self):
        prepare = function_body(self.panel, r"static int m7ul_panel_prepare")
        enable = function_body(self.panel, r"static int m7ul_panel_enable")

        self.assertIn('pr_emerg("M7_PANEL_PREPARE_BEGIN\\n");', prepare)
        self.assertIn('pr_emerg("M7_PANEL_VDDIO_DONE\\n");', prepare)
        self.assertIn('pr_emerg("M7_PANEL_VDD_DONE\\n");', prepare)
        self.assertIn('pr_emerg("M7_PANEL_RESET_RELEASE\\n");', prepare)
        self.assertIn('pr_emerg("M7_PANEL_PREPARE_DONE\\n");', prepare)
        self.assertIn('pr_emerg("M7_PANEL_ENABLE_BEGIN\\n");', enable)
        self.assertIn('pr_emerg("M7_PANEL_ENABLE_DONE\\n");', enable)
        self.assertLess(
            prepare.index("M7_PANEL_RESET_RELEASE"),
            prepare.index("M7_PANEL_XO_BEGIN"),
        )


class MsmIommuOwnershipTest(unittest.TestCase):
    def test_legacy_arm_dma_mapping_is_released_before_msm_attach(self):
        source = MSM_IOMMU.read_text()
        attach = function_body(source, r"struct msm_mmu \*msm_iommu_new")

        self.assertIn("#if IS_ENABLED(CONFIG_ARM_DMA_USE_IOMMU)", source)
        self.assertIn("#include <asm/dma-iommu.h>", source)
        self.assertIn("if (to_dma_iommu_mapping(dev))", attach)
        self.assertIn("arm_iommu_detach_device(dev);", attach)
        self.assertIn("arm_iommu_release_mapping(mapping);", attach)
        self.assertLess(
            attach.index("arm_iommu_detach_device(dev);"),
            attach.index("arm_iommu_release_mapping(mapping);"),
        )
        self.assertLess(
            attach.index("arm_iommu_release_mapping(mapping);"),
            attach.index("iommu_attach_device(iommu->domain, dev);"),
        )

    def test_legacy_dma_ops_are_disabled_before_domain_detach(self):
        source = MSM_IOMMU.read_text()
        attach = function_body(source, r"struct msm_mmu \*msm_iommu_new")

        self.assertIn("#include <linux/dma-map-ops.h>", source)
        self.assertIn("set_dma_ops(dev, NULL);", attach)
        self.assertLess(
            attach.index("set_dma_ops(dev, NULL);"),
            attach.index("arm_iommu_detach_device(dev);"),
        )

    def test_attach_failure_reports_its_errno(self):
        attach = function_body(MSM_IOMMU.read_text(), r"struct msm_mmu \*msm_iommu_new")

        self.assertIn("failed to attach IOMMU domain: %d", attach)
        self.assertIn('dev_err(dev, "failed to attach IOMMU domain: %d\\n", ret);', attach)

    def test_page_table_configuration_failure_stops_attach(self):
        attach = function_body(MSM_IOMMU_CORE.read_text(), r"static int msm_iommu_attach_dev")

        self.assertIn("ret = msm_iommu_domain_config(priv);", attach)
        self.assertRegex(
            attach,
            r"if \(ret\) \{\s+dev_err\(dev, \"failed to configure IOMMU domain: %d\\n\", ret\);\s+return ret;\s+\}",
        )

    def test_page_table_configuration_is_reused_on_reattach(self):
        attach = function_body(MSM_IOMMU_CORE.read_text(), r"static int msm_iommu_attach_dev")

        self.assertIn("if (old == domain)", attach)
        self.assertRegex(attach, r"if \(old == domain\)\s+return 0;")
        self.assertLess(
            attach.index("if (!priv->iop)"),
            attach.index("ret = msm_iommu_domain_config(priv);"),
        )
        self.assertLess(
            attach.index("ret = msm_iommu_domain_config(priv);"),
            attach.index("spin_lock_irqsave(&msm_iommu_lock, flags);"),
        )

    def test_domain_owns_page_table_ops_until_it_is_freed(self):
        source = MSM_IOMMU_CORE.read_text()
        identity = function_body(source, r"static int msm_iommu_identity_attach")
        free = function_body(source, r"static void msm_iommu_domain_free")

        self.assertNotIn("free_io_pgtable_ops", identity)
        self.assertIn("free_io_pgtable_ops(priv->iop);", free)
        self.assertLess(
            free.index("free_io_pgtable_ops(priv->iop);"),
            free.index("kfree(priv);"),
        )

    def test_tlb_flushes_skip_unattached_contexts(self):
        source = MSM_IOMMU_CORE.read_text()
        flush_all = function_body(source, r"static void __flush_iotlb")
        flush_range = function_body(source, r"static void __flush_iotlb_range")

        for flush in (flush_all, flush_range):
            self.assertRegex(
                flush,
                r"list_for_each_entry\(master, &iommu->ctx_list, list\) \{\s+if \(master->num < 0\)\s+continue;",
            )

    def test_iova_to_phys_skips_unattached_contexts(self):
        lookup = function_body(
            MSM_IOMMU_CORE.read_text(),
            r"static phys_addr_t msm_iommu_iova_to_phys",
        )

        self.assertIn("if (list_empty(&priv->list_attached))", lookup)
        self.assertIn("list_for_each_entry(master, &iommu->ctx_list, list)", lookup)
        self.assertIn("if (master->num >= 0)", lookup)
        self.assertIn("if (&master->list == &iommu->ctx_list)", lookup)
        self.assertNotIn("find_master_for_dev(iommu, priv->dev)", lookup)

    def test_mmu_destroy_detaches_only_its_own_domain(self):
        destroy = function_body(MSM_IOMMU.read_text(), r"static void msm_iommu_destroy")

        self.assertIn(
            "if (iommu_get_domain_for_dev(mmu->dev) == iommu->domain)",
            destroy,
        )
        self.assertLess(
            destroy.index("iommu_detach_device(iommu->domain, mmu->dev);"),
            destroy.index("iommu_domain_free(iommu->domain);"),
        )

    def test_context_zero_is_a_valid_attached_context(self):
        source = MSM_IOMMU_CORE.read_text()
        insert = function_body(source, r"static int insert_iommu_master")
        attach = function_body(source, r"static int msm_iommu_attach_dev")

        self.assertIn("master->num = -1;", insert)
        self.assertIn("if (master->num >= 0)", attach)
        self.assertNotIn("if (master->num)", attach)

    def test_identity_detach_releases_only_the_clients_context(self):
        identity = function_body(
            MSM_IOMMU_CORE.read_text(),
            r"static int msm_iommu_identity_attach",
        )

        self.assertIn("master = find_master_for_dev(iommu, dev);", identity)
        self.assertNotIn("list_for_each_entry(master, &iommu->ctx_list", identity)
        self.assertIn("master->num = -1;", identity)
        self.assertLess(
            identity.index("__reset_context(iommu->base, master->num);"),
            identity.index("master->num = -1;"),
        )

    def test_identity_detach_removes_the_iommu_from_the_old_domain(self):
        identity = function_body(
            MSM_IOMMU_CORE.read_text(),
            r"static int msm_iommu_identity_attach",
        )

        self.assertIn("list_del(&iommu->dom_node);", identity)
        self.assertLess(
            identity.index("master->num = -1;"),
            identity.index("list_del(&iommu->dom_node);"),
        )

    def test_attach_checks_context_before_enabling_clocks(self):
        attach = function_body(MSM_IOMMU_CORE.read_text(), r"static int msm_iommu_attach_dev")

        self.assertLess(
            attach.index("if (master->num >= 0)"),
            attach.index("ret = __enable_clocks(iommu);"),
        )
        self.assertLess(
            attach.index("master->num = msm_iommu_alloc_ctx"),
            attach.index("ret = __enable_clocks(iommu);"),
        )

    def test_attach_failure_unwinds_contexts_and_clocks(self):
        attach = function_body(MSM_IOMMU_CORE.read_text(), r"static int msm_iommu_attach_dev")
        failure = attach[attach.rindex("\nfail:"):]

        self.assertIn("goto out;", attach)
        self.assertIn("list_for_each_entry_safe", failure)
        self.assertIn("master = find_master_for_dev(iommu, dev);", failure)
        self.assertIn("cleanup_ret = __enable_clocks(iommu);", failure)
        self.assertIn("msm_iommu_free_ctx(iommu->context_map, master->num);", failure)
        self.assertIn("__reset_context(iommu->base, master->num);", failure)
        self.assertIn("master->num = -1;", failure)
        self.assertIn("__disable_clocks(iommu);", failure)
        self.assertIn("list_del(&iommu->dom_node);", failure)
        self.assertIn('"failed to enable IOMMU clocks during cleanup: %d\\n"', failure)
        self.assertIn("cleanup_ret);", failure)
        self.assertIn(
            "} else {\n\t\t\t__reset_context(iommu->base, master->num);\n\t\t}",
            failure,
        )
        self.assertLess(
            failure.index("if (cleanup_ret)"),
            failure.index("msm_iommu_free_ctx(iommu->context_map, master->num);"),
        )


if __name__ == "__main__":
    unittest.main()
