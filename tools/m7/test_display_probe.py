#!/usr/bin/env python3
"""Source guards for the M7 MDP4/DSI0 display probe."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DTS = ROOT / "arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dts"


def node_override(source, label):
    match = re.search(rf"&{re.escape(label)} \{{(.*?)\n\}};", source, re.DOTALL)
    if not match:
        raise AssertionError(f"&{label} override not found")
    return match.group(1)


def labelled_node(source, label):
    match = re.search(rf"\b{re.escape(label)}: [^{{]+ \{{(.*?)\n\s*\}};", source, re.DOTALL)
    if not match:
        raise AssertionError(f"{label} node not found")
    return match.group(1)


class DisplayProbeTests(unittest.TestCase):
    def setUp(self):
        self.dts = DTS.read_text()

    def test_mdp4_dsi1_output_is_connected_to_dsi0(self):
        self.assertIn(
            "remote-endpoint = <&dsi0_in>;",
            node_override(self.dts, "mdp_dsi1_out"),
        )
        self.assertIn(
            "remote-endpoint = <&mdp_dsi1_out>;",
            node_override(self.dts, "dsi0_in"),
        )

    def test_dsi0_uses_the_m7_host_supplies(self):
        dsi0 = node_override(self.dts, "dsi0")
        self.assertIn('status = "okay";', dsi0)
        self.assertIn("vdda-supply = <&pm8921_l2>;", dsi0)
        self.assertIn("vddio-supply = <&pm8921_lvs5>;", dsi0)
        self.assertNotIn("avdd-supply", dsi0)
        self.assertNotIn("pm8921_l11", dsi0)

    def test_dsi0_phy_uses_the_m7_pll_supply(self):
        phy = node_override(self.dts, "dsi0_phy")
        self.assertIn('status = "okay";', phy)
        self.assertIn("vddio-supply = <&pm8921_lvs7>;", phy)

    def test_host_and_phy_supply_voltages_match_downstream(self):
        l2 = labelled_node(self.dts, "pm8921_l2")
        self.assertIn("regulator-min-microvolt = <1200000>;", l2)
        self.assertIn("regulator-max-microvolt = <1200000>;", l2)
        labelled_node(self.dts, "pm8921_lvs5")
        labelled_node(self.dts, "pm8921_lvs7")
        self.assertIn("vin_lvs4_5_7-supply = <&pm8921_s4>;", self.dts)
        s4 = labelled_node(self.dts, "pm8921_s4")
        self.assertIn("regulator-min-microvolt = <1800000>;", s4)
        self.assertIn("regulator-max-microvolt = <1800000>;", s4)

    def test_gpu_stays_disabled_during_display_bringup(self):
        self.assertIn('status = "disabled";', node_override(self.dts, "gpu"))


if __name__ == "__main__":
    unittest.main()
