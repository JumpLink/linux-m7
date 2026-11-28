#!/usr/bin/env python3
"""Source guard for single-owner MDP4 KMS cleanup."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MDP4_KMS = ROOT / "drivers/gpu/drm/msm/disp/mdp4/mdp4_kms.c"
MSM_DRV = ROOT / "drivers/gpu/drm/msm/msm_drv.c"


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


if __name__ == "__main__":
    unittest.main()
