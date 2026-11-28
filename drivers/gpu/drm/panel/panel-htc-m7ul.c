// SPDX-License-Identifier: GPL-2.0-only

#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/regulator/consumer.h>

#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>
#include <drm/drm_probe_helper.h>

#include <video/mipi_display.h>

struct m7ul_panel {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi;
	struct regulator_bulk_data supplies[2];
	struct gpio_desc *reset_gpio;
	struct gpio_desc *vdd5v_en_gpio;
	struct gpio_desc *vddn5v_en_gpio;
	struct gpio_desc *backlight_gpio;
	struct clk *xo_clk;
};

static inline struct m7ul_panel *to_m7ul_panel(struct drm_panel *panel)
{
	return container_of(panel, struct m7ul_panel, panel);
}

static void m7ul_panel_power_off(struct m7ul_panel *ctx)
{
	gpiod_set_value_cansleep(ctx->backlight_gpio, 0);
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	usleep_range(3000, 4000);
	gpiod_set_value_cansleep(ctx->vddn5v_en_gpio, 0);
	usleep_range(2000, 3000);
	gpiod_set_value_cansleep(ctx->vdd5v_en_gpio, 0);
	usleep_range(8000, 10000);
}

static int m7ul_panel_prepare(struct drm_panel *panel)
{
	struct m7ul_panel *ctx = to_m7ul_panel(panel);
	struct device *dev = &ctx->dsi->dev;
	int ret;

	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	gpiod_set_value_cansleep(ctx->backlight_gpio, 0);

	/* HTC enables the I/O rail before the analog supply. */
	ret = regulator_enable(ctx->supplies[0].consumer);
	if (ret)
		return dev_err_probe(dev, ret, "failed to enable panel VDDIO\n");

	ret = regulator_enable(ctx->supplies[1].consumer);
	if (ret) {
		regulator_disable(ctx->supplies[0].consumer);
		return dev_err_probe(dev, ret, "failed to enable panel VDD\n");
	}

	usleep_range(1000, 2000);
	gpiod_set_value_cansleep(ctx->vdd5v_en_gpio, 1);
	usleep_range(2000, 3000);
	gpiod_set_value_cansleep(ctx->vddn5v_en_gpio, 1);
	usleep_range(7000, 8000);
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);

	/* HTC's panel sequence pulses XO_D0 after releasing reset. */
	ret = clk_prepare_enable(ctx->xo_clk);
	if (ret)
		goto power_off;

	usleep_range(10000, 11000);
	clk_disable_unprepare(ctx->xo_clk);

	return 0;

power_off:
	m7ul_panel_power_off(ctx);
	regulator_bulk_disable(ARRAY_SIZE(ctx->supplies), ctx->supplies);
	return dev_err_probe(dev, ret, "failed to pulse panel XO clock\n");
}

static int m7ul_panel_unprepare(struct drm_panel *panel)
{
	struct m7ul_panel *ctx = to_m7ul_panel(panel);
	int ret;

	m7ul_panel_power_off(ctx);

	ret = regulator_bulk_disable(ARRAY_SIZE(ctx->supplies), ctx->supplies);
	if (ret)
		return dev_err_probe(&ctx->dsi->dev, ret,
				     "failed to disable panel supplies\n");

	return 0;
}

static int m7ul_panel_enable(struct drm_panel *panel)
{
	struct m7ul_panel *ctx = to_m7ul_panel(panel);
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = ctx->dsi };

	mipi_dsi_dcs_exit_sleep_mode_multi(&dsi_ctx);
	mipi_dsi_msleep(&dsi_ctx, 120);

	/* HTC's minimal panel path still enables the DCS brightness block. */
	mipi_dsi_dcs_write_seq_multi(&dsi_ctx, MIPI_DCS_WRITE_CONTROL_DISPLAY, 0x2c);
	mipi_dsi_dcs_set_display_brightness_multi(&dsi_ctx, 0xff);
	mipi_dsi_dcs_set_display_on_multi(&dsi_ctx);
	if (dsi_ctx.accum_err)
		return dsi_ctx.accum_err;

	/* Keep BL_HW_EN low until the revision-specific PWM sequence is ported. */
	return 0;
}

static int m7ul_panel_disable(struct drm_panel *panel)
{
	struct m7ul_panel *ctx = to_m7ul_panel(panel);
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = ctx->dsi };

	gpiod_set_value_cansleep(ctx->backlight_gpio, 0);
	mipi_dsi_dcs_set_display_off_multi(&dsi_ctx);
	mipi_dsi_msleep(&dsi_ctx, 20);
	mipi_dsi_dcs_enter_sleep_mode_multi(&dsi_ctx);
	mipi_dsi_msleep(&dsi_ctx, 120);

	return dsi_ctx.accum_err;
}

static const struct drm_display_mode m7ul_panel_mode = {
	.clock = (1080 + 27 + 10 + 38) * (1920 + 4 + 2 + 4) * 60 / 1000,
	.hdisplay = 1080,
	.hsync_start = 1080 + 27,
	.hsync_end = 1080 + 27 + 10,
	.htotal = 1080 + 27 + 10 + 38,
	.vdisplay = 1920,
	.vsync_start = 1920 + 4,
	.vsync_end = 1920 + 4 + 2,
	.vtotal = 1920 + 4 + 2 + 4,
	.width_mm = 58,
	.height_mm = 103,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int m7ul_panel_get_modes(struct drm_panel *panel,
				struct drm_connector *connector)
{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, &m7ul_panel_mode);
	if (!mode)
		return -ENOMEM;

	drm_mode_set_name(mode);
	connector->display_info.width_mm = mode->width_mm;
	connector->display_info.height_mm = mode->height_mm;
	drm_mode_probed_add(connector, mode);

	return 1;
}

static const struct drm_panel_funcs m7ul_panel_funcs = {
	.prepare = m7ul_panel_prepare,
	.unprepare = m7ul_panel_unprepare,
	.enable = m7ul_panel_enable,
	.disable = m7ul_panel_disable,
	.get_modes = m7ul_panel_get_modes,
};

static int m7ul_panel_probe(struct mipi_dsi_device *dsi)
{
	struct device *dev = &dsi->dev;
	struct m7ul_panel *ctx;
	int ret;

	ctx = devm_drm_panel_alloc(dev, struct m7ul_panel, panel,
				   &m7ul_panel_funcs, DRM_MODE_CONNECTOR_DSI);
	if (IS_ERR(ctx))
		return PTR_ERR(ctx);

	ctx->supplies[0].supply = "vddio";
	ctx->supplies[1].supply = "vdd";
	ret = devm_regulator_bulk_get(dev, ARRAY_SIZE(ctx->supplies),
				      ctx->supplies);
	if (ret)
		return dev_err_probe(dev, ret, "failed to get panel supplies\n");

	ctx->reset_gpio = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(ctx->reset_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->reset_gpio),
				     "failed to get reset GPIO\n");

	ctx->vdd5v_en_gpio = devm_gpiod_get(dev, "vdd5v-en", GPIOD_OUT_LOW);
	if (IS_ERR(ctx->vdd5v_en_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->vdd5v_en_gpio),
				     "failed to get positive boost GPIO\n");

	ctx->vddn5v_en_gpio = devm_gpiod_get(dev, "vddn5v-en", GPIOD_OUT_LOW);
	if (IS_ERR(ctx->vddn5v_en_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->vddn5v_en_gpio),
				     "failed to get negative boost GPIO\n");

	ctx->backlight_gpio = devm_gpiod_get(dev, "backlight", GPIOD_OUT_LOW);
	if (IS_ERR(ctx->backlight_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->backlight_gpio),
				     "failed to get backlight GPIO\n");

	ctx->xo_clk = devm_clk_get(dev, "xo");
	if (IS_ERR(ctx->xo_clk))
		return dev_err_probe(dev, PTR_ERR(ctx->xo_clk),
				     "failed to get XO clock\n");

	ctx->dsi = dsi;
	mipi_dsi_set_drvdata(dsi, ctx);

	dsi->lanes = 4;
	dsi->format = MIPI_DSI_FMT_RGB888;
	dsi->mode_flags = MIPI_DSI_MODE_LPM | MIPI_DSI_CLOCK_NON_CONTINUOUS;
	ctx->panel.prepare_prev_first = true;

	drm_panel_add(&ctx->panel);

	ret = devm_mipi_dsi_attach(dev, dsi);
	if (ret) {
		drm_panel_remove(&ctx->panel);
		return dev_err_probe(dev, ret, "failed to attach to DSI host\n");
	}

	return 0;
}

static void m7ul_panel_remove(struct mipi_dsi_device *dsi)
{
	struct m7ul_panel *ctx = mipi_dsi_get_drvdata(dsi);

	drm_panel_remove(&ctx->panel);
}

static const struct of_device_id m7ul_panel_of_match[] = {
	{ .compatible = "htc,m7ul-panel" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, m7ul_panel_of_match);

static struct mipi_dsi_driver m7ul_panel_driver = {
	.probe = m7ul_panel_probe,
	.remove = m7ul_panel_remove,
	.driver = {
		.name = "panel-htc-m7ul",
		.of_match_table = m7ul_panel_of_match,
	},
};
module_mipi_dsi_driver(m7ul_panel_driver);

MODULE_DESCRIPTION("HTC One M7 UL JDI/Samsung DSI panel driver");
MODULE_LICENSE("GPL");
