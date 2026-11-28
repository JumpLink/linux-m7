# M7 vendor-source analysis protocol

## Purpose

This document records how the public HTC/LineageOS vendor kernel is used to
bring up the HTC One M7 (`m7ul`) on Mainline. It is both a reproducible engineering
log and source material for a later blog article.

The vendor tree is evidence, not code to copy wholesale. Each finding is mapped
to a Mainline abstraction and classified as **adopted**, **verified**, or
**open**. Raw extracts remain local and read-only. This repository contains only
sanitized facts and references to public source.

## Source snapshot

- Repository: `LineageOS/android_kernel_htc_msm8960`
- Branch: `cm-14.1`
- Commit: `cb121ea9e86cd51e814cb50048fd64544e672bcc`
- Primary directory: `arch/arm/mach-msm/htc/m7/`
- Local read-only mirror: `/tmp/opencode/lineage_m7/`

The local path is not part of the evidence chain. The public commit, file and
line references below are.

## Method

1. Start with board symbols, not driver names. Resolve GPIO numbers, PMIC GPIO
   domains, regulators and bus attachments.
2. Follow one complete state transition. For the panel that means first boot,
   resume, display-on, display-off and backlight separately.
3. Record timing and order exactly. A correct pin with the wrong rail order is
   not a correct sequence.
4. Separate panel identity from backlight-controller identity. The JDI/Samsung
   panel variant and the PWM IC revision are independent inputs.
5. Compare the vendor sequence with the Mainline DTS and driver. Adopt only the
   part supported by evidence and the target subsystem's programming model.
6. Turn every unresolved difference into a measurement or a bounded experiment.
7. Require hardware acceptance: a complete late `M7_HOST_PROBE` with
   `M7_WLAN_PRESENT=yes`, and visible output on the physical panel for display.

## Evidence ledger

### Panel mode and timing

**Vendor evidence:** `display/mipi_m7_1080p_pt.c:42-103` defines a 1080x1920,
24-bit command-mode panel on the primary DSI link, four data lanes, RGB888 and
60 Hz. Horizontal porches are 27/10/38 and vertical porches are 4/2/4. The panel
structure requests an 830 MHz MDP clock.

**Mainline mapping:** `drivers/gpu/drm/panel/panel-htc-m7ul.c:136-149` reproduces
the geometry and porches. The DTS connects MDP4's DSI1 output to Mainline DSI0;
the vendor's primary link and Mainline's DSI0 are the same board path.

**Status:** adopted for geometry, format, lane count and refresh. The vendor's
830 MHz clock request remains a comparison point, not a value to copy blindly.
Mainline MDP4 currently selects 266.667 MHz for APQ8064
(`disp/mdp4/mdp4_kms.c:402-403`). Whether the lower rate sustains the command
path must be established from measured clocks and display behavior.

### Pins, rails and electrical mapping

**Vendor evidence:**

- `board-m7.h:46,77,133,175-176`: `LCD_TE` is TLMM GPIO 0, `LCD_RST` is GPIO 31,
  `BL_HW_EN` is GPIO 86, and the negative/positive boost enables are PM8921 GPIO
  36/37.
- `display/board-m7-panel.c:315-350`: `dsi1_vddio` is LVS5 and
  `dsi1_pll_vdda` is L2 at 1.2 V.
- `board-m7-regulator.c:35-36,198,207`: the vendor rail names resolve through
  the PM8921 regulator table.
- `display/board-m7-panel.c:602`: the XO voter uses `MSM_XO_TCXO_D0`.

**Mainline mapping:** `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dts:441-489`
uses L2 for DSI VDDA and panel VDD, LVS5 for DSI/panel VDDIO, and LVS7 for PHY
VDDIO. DSI AVDD stays unconnected because the M7 panel path does not use the
Nexus 7 rail arrangement. GPIO 31 is active-low reset, GPIO 86 is active-high
backlight enable, and PM8921 GPIO 37/36 are active-high positive/negative boost.

**Status:** verified and adopted. The DSI `avdd` supply is deliberately absent.

### First initialization versus resume

**Vendor evidence:** `display/board-m7-panel.c:355-404` has two distinct paths.

First initialization:

1. Enable LVS5.
2. Set L2 optimum mode and enable L2.
3. Pulse XO_D0 on for 10 ms, then off.

Resume:

1. Set L2 optimum mode and enable L2.
2. Enable LVS5.
3. Wait 1 ms; assert positive boost GPIO 37.
4. Wait 2 ms; assert negative boost GPIO 36.
5. Wait 7 ms; release reset.
6. Pulse XO_D0 on for 10 ms, then off.

Power-off in `display/board-m7-panel.c:410-424` disables backlight, asserts
reset, waits 3 ms, disables negative boost, waits 2 ms, then disables positive
boost.

**Mainline mapping:** `drivers/gpu/drm/panel/panel-htc-m7ul.c:33-85` uses the
resume-like boost/reset timing on every prepare, but enables LVS5 before L2 and
then pulses XO after releasing reset.

**Status:** pin mapping and delays are verified. The L2/LVS5 ordering difference
and the lack of a separate first-initialization path remain open. The current
sequence must not be described as proven until the physical panel produces
visible output.

### Panel command sequence

**Vendor evidence:** `display/mipi_m7.c:182-206` contains the complete original
JDI/Samsung command-mode table. It includes exit-sleep with a 120 ms delay,
manufacturer password sequences, MIE/CABC controls, gamma tables, column/page
addresses, TE enable and a NOP. `m7_lcd_on()` sends this table at
`display/mipi_m7.c:899-911`; `m7_display_on()` sends DCS display-on later at
`display/mipi_m7.c:932-951`. Other Samsung revisions select different tables at
`display/mipi_m7.c:1180-1233`.

**Mainline mapping:** `drivers/gpu/drm/panel/panel-htc-m7ul.c:103-119` currently
uses only:

1. `EXIT_SLEEP_MODE`
2. 120 ms delay
3. DCS `0x53 0x2c`
4. DCS `0x51 0xff`
5. `SET_DISPLAY_ON`

Gamma and manufacturer tables are intentionally omitted in the first minimal
probe.

**Status:** the minimal commands are evidence-backed as a subset, but successful
command transport and visible panel output are not yet proven. The installed
panel revision must be identified before selecting a full revision-specific
table.

### PWM revision and backlight

**Vendor evidence:**

- `board-m7.c:4266-4269,4579-4584`: the device named `pwm_i2c` is on GSBI2 at
  7-bit address `0x36` (`0x6c >> 1`).
- `display/mipi_m7.c:1460-1471`: HTC reads register `0x1f` to obtain `pwmic_ver`.
- `display/mipi_m7.c:1058-1067`: for revision 2 or newer, enable GPIO 86, wait
  4 ms, write `{0x50=0x02, 0x01=0x09, 0x02=0x78, 0x05=0x14, 0x00=0x04}`,
  wait 12 ms, then write `0x03=0xff`.
- `display/mipi_m7.c:1068-1099`: older revisions use a different initialization
  and brightness path.

The vendor probe assumes the I2C client exists and does not check the revision
read result. Mainline must not copy that assumption.

**Mainline mapping:** GPIO 86 stays low. GSBI2 and its I2C child are enabled at
400 kHz, matching the vendor `clk_freq`. The panel driver resolves the bus by
`pwm-i2c-bus` phandle, creates a dummy client at 7-bit `0x36`, and reads
register `0x1f` read-only at the end of `m7ul_panel_prepare()`. No
revision-specific writes, no `backlight-gpios` consumer, no DRM backlight
device is registered.

**Status:** read-only revision detection is implemented. The read is
non-fatal: a missing bus or a failed read leaves the backlight off and does
not abort panel prepare. The revision value appears in the Pstore console as
`M7_PANEL_PWM_REVISION <n>` (or `M7_PANEL_PWM_REVISION_FAIL <errno>`). No
revision-specific writes until that value is verified on hardware.

## Translation rules

- Preserve the vendor's electrical facts, not its legacy framework objects.
- Express rails as regulator consumers, pins as GPIO descriptors and XO as a
  clock consumer.
- Keep first-boot and resume semantics explicit in the panel driver.
- Treat command tables as revision data. Do not merge several Samsung variants
  into an untested superset.
- Read hardware identity before programming revision-specific backlight state.
- Add return-code checks where the vendor code logs and continues.
- Keep diagnostic breadcrumbs in the existing Pstore console path so a silent
  warm reset can be attributed to the last completed milestone.

## Open questions and next measurements

1. Does the identity-domain detach complete safely now that direct DMA ops are
   selected before legacy page-table cleanup?
2. Does `msm_iommu_domain_config()` succeed, and is `priv->iop` non-NULL before
   context programming?
3. Which MDP4/DSI register access follows the IOMMU attach, and do all required
   clocks report success before that access?
4. Is the installed panel one of the original JDI/Samsung revisions, and what
   does PWM register `0x1f` return?
5. Does first initialization require LVS5 before L2 while resume requires L2
   before LVS5, or is the vendor split incidental to its state machine?
6. Is Mainline's 266.667 MHz MDP clock sufficient for the 1080p command path?

## Running protocol

| Date | Step | Result | Confidence |
|---|---|---|---|
| 2026-11-28 | Pin and rail inventory | GPIO 31/36/37/86 and L2/LVS5/LVS7 mapped to Mainline DTS | High |
| 2026-11-28 | First-init/resume trace | Two vendor orderings identified; Mainline currently follows a third ordering | High for source, open for hardware |
| 2026-11-28 | Panel-command trace | Minimal Mainline subset identified; full vendor tables remain revision-specific | High |
| 2026-11-28 | PWM trace | GSBI2, address `0x36`, revision register `0x1f`, two programming families | High |
| 2026-11-28 | Mainline comparison | Unchecked IOMMU configuration and clock/MMIO diagnostics added to the next-probe checklist | High for source, hardware pending |
| 2026-11-28 | Read-only PWM detection | GSBI2 at 400 kHz, dummy client `0x36`, register `0x1f` read after panel prepare | High for source, hardware pending |
| 2026-11-28 | DSI startup tracing | PHY/host/panel milestones added; `pm_runtime_get_sync()` return checked | High for source, hardware pending |

## Blog narrative

The useful unit of a vendor port is not a source file. It is a sequence:
**pins -> supplies -> clocks -> reset -> commands -> backlight**. The vendor
kernel exposes that sequence across board setup, panel power management, DSI
command tables and an independent PWM driver. Mainline has to reconstruct the
same hardware contract with different ownership and error rules.

The discipline is therefore to preserve facts, reject accidental assumptions,
and turn every unresolved difference into a measurable experiment. A booting
kernel is not yet a display port; the physical panel and the complete late host
probe are the acceptance tests.
