#!/usr/bin/env python3
"""Source guard for MDP4 DSI interface selection."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENCODER = ROOT / "drivers/gpu/drm/msm/disp/mdp4/mdp4_dsi_encoder.c"


def function_body(source, name):
    match = re.search(rf"static void {name}\(.*?\n\}}", source, re.DOTALL)
    if not match:
        raise AssertionError(f"{name}() not found")
    return match.group(0)


class Mdp4CommandModeTests(unittest.TestCase):
    def setUp(self):
        self.source = ENCODER.read_text()

    def test_video_remains_the_default_interface(self):
        enable = function_body(self.source, "mdp4_dsi_encoder_enable")
        self.assertIn("enum mdp4_intf intf = INTF_DSI_VIDEO;", enable)
        self.assertIn("mdp4_crtc_set_intf(encoder->crtc, intf, 0);", enable)

    def test_dsi0_command_mode_selects_the_command_interface(self):
        enable = function_body(self.source, "mdp4_dsi_encoder_enable")
        self.assertRegex(
            enable,
            r"if \(msm_dsi_is_cmd_mode\(priv->kms->dsi\[0\]\)\)\s+"
            r"intf = INTF_DSI_CMD;",
        )


if __name__ == "__main__":
    unittest.main()
