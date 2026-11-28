#!/usr/bin/env python3
"""Source guard for the MSM empty component-match crash."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MSM_DRV = ROOT / "drivers/gpu/drm/msm/msm_drv.c"


def probe_function(source):
    match = re.search(
        r"int msm_drv_probe\(struct device \*master_dev,(.*?)\n\}",
        source,
        re.DOTALL,
    )
    if not match:
        raise AssertionError("msm_drv_probe() not found")
    return match.group(0)


class MsmComponentMatchTests(unittest.TestCase):
    def test_error_match_is_returned_before_core_call(self):
        probe = probe_function(MSM_DRV.read_text())
        self.assertRegex(
            probe,
            r"if \(IS_ERR\(match\)\)\s+return PTR_ERR\(match\);",
        )

    def test_empty_component_match_is_rejected_before_core_call(self):
        probe = probe_function(MSM_DRV.read_text())
        guard = re.search(r"if \(!match\)(.*?)component_master_add_with_match", probe, re.DOTALL)
        self.assertIsNotNone(guard, "msm_drv_probe() must reject an empty match list")
        self.assertIn("-ENODEV", guard.group(1))
        self.assertIn("no display or GPU components", guard.group(1))


if __name__ == "__main__":
    unittest.main()
