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


if __name__ == "__main__":
    unittest.main()
