#!/usr/bin/env python3
"""Source guards for the minimal M7 command-mode panel driver."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DRIVER = ROOT / "drivers/gpu/drm/panel/panel-htc-m7ul.c"
DTS = ROOT / "arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dts"
BINDING = ROOT / "Documentation/devicetree/bindings/display/panel/htc,m7ul-panel.yaml"
DEFCONFIG = ROOT / "arch/arm/configs/m7_defconfig"
MAINTAINERS = ROOT / "MAINTAINERS"


def function_body(source, name):
    match = re.search(rf"static (?:int|void) {name}\(.*?\n\}}", source, re.DOTALL)
    if not match:
        raise AssertionError(f"{name}() not found")
    return match.group(0)


def node_override(source, label):
    match = re.search(rf"&{re.escape(label)} \{{(.*?)\n\}};", source, re.DOTALL)
    if not match:
        raise AssertionError(f"&{label} override not found")
    return match.group(1)


def pin_state(source, label):
    match = re.search(rf"{re.escape(label)}: [^{{]+ \{{(.*?)\n\t\}};", source, re.DOTALL)
    if not match:
        raise AssertionError(f"{label} not found")
    return match.group(1)


class M7PanelTests(unittest.TestCase):
    def setUp(self):
        self.driver = DRIVER.read_text()
        self.dts = DTS.read_text()

    def test_panel_uses_four_lane_rgb888_command_mode(self):
        self.assertIn("dsi->lanes = 4;", self.driver)
        self.assertIn("dsi->format = MIPI_DSI_FMT_RGB888;", self.driver)
        self.assertIn(
            "dsi->mode_flags = MIPI_DSI_MODE_LPM | MIPI_DSI_CLOCK_NON_CONTINUOUS;",
            self.driver,
        )
        self.assertNotIn("MIPI_DSI_MODE_VIDEO", self.driver)

    def test_panel_mode_matches_htc_timings(self):
        for setting in (
            ".clock = (1080 + 27 + 10 + 38) * (1920 + 4 + 2 + 4) * 60 / 1000,",
            ".hdisplay = 1080,",
            ".hsync_start = 1080 + 27,",
            ".hsync_end = 1080 + 27 + 10,",
            ".htotal = 1080 + 27 + 10 + 38,",
            ".vdisplay = 1920,",
            ".vsync_start = 1920 + 4,",
            ".vsync_end = 1920 + 4 + 2,",
            ".vtotal = 1920 + 4 + 2 + 4,",
            ".width_mm = 58,",
            ".height_mm = 103,",
        ):
            self.assertIn(setting, self.driver)

    def test_minimal_init_enables_backlight_without_gamma_tables(self):
        enable = function_body(self.driver, "m7ul_panel_enable")
        self.assertEqual(
            re.findall(r"mipi_dsi_dcs_\w+_multi", enable),
            [
                "mipi_dsi_dcs_exit_sleep_mode_multi",
                "mipi_dsi_dcs_write_seq_multi",
                "mipi_dsi_dcs_set_display_brightness_multi",
                "mipi_dsi_dcs_set_display_on_multi",
            ],
        )
        self.assertIn("mipi_dsi_msleep(&dsi_ctx, 120);", enable)
        self.assertIn(
            "mipi_dsi_dcs_write_seq_multi(&dsi_ctx, MIPI_DCS_WRITE_CONTROL_DISPLAY, 0x2c);",
            enable,
        )
        self.assertIn("mipi_dsi_dcs_set_display_brightness_multi(&dsi_ctx, 0xff);", enable)
        self.assertNotRegex(enable, r"0xfa|0xfb")

    def test_power_sequence_orders_supplies_boosts_reset_and_xo_pulse(self):
        prepare = function_body(self.driver, "m7ul_panel_prepare")
        ordered = (
            "regulator_enable(ctx->supplies[0].consumer);",
            "regulator_enable(ctx->supplies[1].consumer);",
            "usleep_range(1000, 2000);",
            "gpiod_set_value_cansleep(ctx->vdd5v_en_gpio, 1);",
            "usleep_range(2000, 3000);",
            "gpiod_set_value_cansleep(ctx->vddn5v_en_gpio, 1);",
            "usleep_range(7000, 8000);",
            "gpiod_set_value_cansleep(ctx->reset_gpio, 0);",
            "clk_prepare_enable(ctx->xo_clk);",
            "usleep_range(10000, 11000);",
            "clk_disable_unprepare(ctx->xo_clk);",
        )
        positions = [prepare.index(item) for item in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('ctx->supplies[0].supply = "vddio";', self.driver)
        self.assertIn('ctx->supplies[1].supply = "vdd";', self.driver)

    def test_backlight_enable_is_deferred(self):
        prepare = function_body(self.driver, "m7ul_panel_prepare")
        disable = function_body(self.driver, "m7ul_panel_disable")
        power_off = function_body(self.driver, "m7ul_panel_power_off")
        self.assertNotIn("gpiod_set_value_cansleep(ctx->backlight_gpio, 1)", self.driver)
        for body in (prepare, disable, power_off):
            self.assertIn("gpiod_set_value_cansleep(ctx->backlight_gpio, 0)", body)
        self.assertLess(
            disable.index("gpiod_set_value_cansleep(ctx->backlight_gpio, 0)"),
            disable.index("mipi_dsi_dcs_set_display_off_multi"),
        )
        self.assertLess(
            power_off.index("gpiod_set_value_cansleep(ctx->backlight_gpio, 0)"),
            power_off.index("gpiod_set_value_cansleep(ctx->reset_gpio, 1)"),
        )

    def test_panel_has_a_reciprocal_dsi0_endpoint(self):
        panel = node_override(self.dts, "dsi0")
        self.assertIn('compatible = "htc,m7ul-panel";', panel)
        self.assertIn("remote-endpoint = <&dsi0_out>;", panel)
        self.assertIn(
            "remote-endpoint = <&panel_in>;",
            node_override(self.dts, "dsi0_out"),
        )

    def test_board_wires_supplies_reset_boosts_and_xo(self):
        panel = node_override(self.dts, "dsi0")
        for setting in (
            "vdd-supply = <&pm8921_l2>;",
            "vddio-supply = <&pm8921_lvs5>;",
            "clocks = <&rpmcc RPM_XO_D0>;",
            'clock-names = "xo";',
            "reset-gpios = <&tlmm_pinmux 31 GPIO_ACTIVE_LOW>;",
            "vdd5v-en-gpios = <&pm8921_gpio 37 GPIO_ACTIVE_HIGH>;",
            "vddn5v-en-gpios = <&pm8921_gpio 36 GPIO_ACTIVE_HIGH>;",
            "backlight-gpios = <&tlmm_pinmux 86 GPIO_ACTIVE_HIGH>;",
            "pinctrl-0 = <&panel_backlight_pin>, <&panel_reset_pin>;",
        ):
            self.assertIn(setting, panel)

    def test_reset_starts_asserted(self):
        state = pin_state(self.dts, "panel_reset_pin")
        self.assertIn('function = "gpio";', state)
        self.assertIn("output-low;", state)

    def test_active_low_reset_is_released_after_boost(self):
        panel = node_override(self.dts, "dsi0")
        prepare = function_body(self.driver, "m7ul_panel_prepare")
        power_off = function_body(self.driver, "m7ul_panel_power_off")

        self.assertIn(
            "reset-gpios = <&tlmm_pinmux 31 GPIO_ACTIVE_LOW>;",
            panel,
        )
        self.assertIn('devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH)', self.driver)
        self.assertLess(
            prepare.index("gpiod_set_value_cansleep(ctx->reset_gpio, 1)"),
            prepare.index("regulator_enable(ctx->supplies[0].consumer);"),
        )
        self.assertLess(
            prepare.index("gpiod_set_value_cansleep(ctx->vddn5v_en_gpio, 1)"),
            prepare.index("gpiod_set_value_cansleep(ctx->reset_gpio, 0)"),
        )
        self.assertIn("gpiod_set_value_cansleep(ctx->reset_gpio, 1)", power_off)

    def test_backlight_starts_disabled(self):
        state = pin_state(self.dts, "panel_backlight_pin")
        self.assertIn('function = "gpio";', state)
        self.assertIn("output-low;", state)

    def test_revision_specific_backlight_is_not_probed_yet(self):
        self.assertNotIn("led-controller@36", self.dts)
        self.assertNotIn('compatible = "ti,lm3630a";', self.dts)
        self.assertNotIn("drm_panel_of_backlight(&ctx->panel);", self.driver)
        kconfig = (ROOT / "drivers/gpu/drm/panel/Kconfig").read_text()
        block = re.search(
            r"config DRM_PANEL_HTC_M7UL\n(.*?)(?=\nconfig |\Z)",
            kconfig,
            re.DOTALL,
        )
        self.assertIsNotNone(block)
        self.assertNotIn("depends on BACKLIGHT_CLASS_DEVICE", block.group(1))

    def test_pwm_revision_read_is_read_only(self):
        driver = self.driver
        self.assertIn("M7UL_PWM_I2C_ADDRESS\t0x36", driver)
        self.assertIn("M7UL_PWM_REVISION_REG\t0x1f", driver)
        self.assertIn("i2c_smbus_read_byte_data(ctx->pwm_client,", driver)
        self.assertIn("M7_PANEL_PWM_REVISION_BEGIN", driver)
        self.assertIn("M7_PANEL_PWM_REVISION_FAIL %d", driver)
        self.assertIn("M7_PANEL_PWM_REVISION %d", driver)
        self.assertNotIn("i2c_smbus_write_byte_data", driver)
        self.assertNotIn("gpiod_set_value_cansleep(ctx->backlight_gpio, 1)", driver)

    def test_panel_resolves_the_pwm_bus_by_phandle(self):
        panel = node_override(self.dts, "dsi0")
        self.assertIn("pwm-i2c-bus = <&gsbi2_i2c>;", panel)
        gsbi2 = node_override(self.dts, "gsbi2")
        self.assertIn("status = \"okay\";", gsbi2)
        gsbi2_i2c = node_override(self.dts, "gsbi2_i2c")
        self.assertIn("clock-frequency = <400000>;", gsbi2_i2c)
        self.assertIn("status = \"okay\";", gsbi2_i2c)

    def test_panel_resolves_pwm_bus_phandle_not_panel_node(self):
        probe = function_body(self.driver, "m7ul_panel_probe")
        self.assertIn('of_parse_phandle(dev->of_node, "pwm-i2c-bus", 0)', probe)
        self.assertIn("of_get_i2c_adapter_by_node(bus_np)", probe)
        self.assertIn("of_node_put(bus_np)", probe)
        self.assertNotIn("of_get_i2c_adapter_by_node(dev->of_node)", probe)
        self.assertIn("if (!ctx->pwm_adapter)", probe)

    def test_panel_releases_the_pwm_adapter(self):
        self.assertIn("static void m7ul_put_pwm_adapter(void *data)", self.driver)
        self.assertIn("i2c_put_adapter(data);", self.driver)
        self.assertIn("devm_add_action_or_reset(dev, m7ul_put_pwm_adapter,", self.driver)
        self.assertIn("devm_i2c_new_dummy_device(dev,", self.driver)

    def test_pmic_boost_pins_start_disabled(self):
        for label in ("panel_p5v_en_pin", "panel_n5v_en_pin"):
            state = pin_state(self.dts, label)
            self.assertIn('function = "normal";', state)
            self.assertIn("drive-push-pull;", state)
            self.assertIn("output-low;", state)

    def test_driver_is_built_and_bound(self):
        self.assertIn("CONFIG_DRM_PANEL_HTC_M7UL=y", DEFCONFIG.read_text())
        self.assertIn(
            "obj-$(CONFIG_DRM_PANEL_HTC_M7UL) += panel-htc-m7ul.o",
            (ROOT / "drivers/gpu/drm/panel/Makefile").read_text(),
        )
        self.assertIn("config DRM_PANEL_HTC_M7UL", (ROOT / "drivers/gpu/drm/panel/Kconfig").read_text())
        self.assertIn("compatible:\n    const: htc,m7ul-panel", BINDING.read_text())
        self.assertNotIn("  backlight: true", BINDING.read_text())
        maintainers = MAINTAINERS.read_text()
        self.assertIn(
            "F:\tDocumentation/devicetree/bindings/display/panel/htc,m7ul-panel.yaml",
            maintainers,
        )
        self.assertIn("F:\tdrivers/gpu/drm/panel/panel-htc-m7ul.c", maintainers)


if __name__ == "__main__":
    unittest.main()
