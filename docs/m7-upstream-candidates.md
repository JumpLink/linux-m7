# M7 upstream candidates

These are candidates for future upstream submission, not approved patches. No
issue or pull request is filed automatically. The workflow matches the OnePlus
6T work: isolate one fix, prove it on hardware, keep board data separate and
ask before contacting upstream maintainers.

## 1. MMC core: complete non-standard SDIO handling

Files:

- `drivers/mmc/core/quirks.h`
- `drivers/mmc/core/sdio_io.c`

Candidate series:

1. Add a compatible-based BCM4335 `MMC_QUIRK_NONSTD_SDIO` fixup after the
   common CIS has been read.
2. Skip per-function FBR/CIS probing for that quirk, but keep standard FBR
   block-size writes and `sdio_enable_func()`.

Evidence: the M7 BCM4335 responds to common CIS reads but not standard FBR
reads at 25 MHz. At 400 kHz the FBR block-size writes succeed and are required
for the firmware data path. Bypassing F1 enable only moves the failure to
ChipClkCSR. Published bcmdhd code does enable F1, so neither bypass is an
upstream candidate.

Open risks:

- The BCM4335 fixup currently applies to every board using
  `brcm,bcm4335-fmac`; confirm that all affected modules share this behavior.
- Prove that standard SDIO and eMMC behavior is unchanged.
- Add a focused test or at least a documented multi-board regression matrix.
- Keep the standard `sdio_enable_func()` path. The M7 now enables F1 at
  400 kHz; bypassing enable or replacing it with a direct write is not needed.

## 2. QCOM MMCI feedback-clock selection

File:

- `drivers/mmc/host/mmci.c`

Candidate: make `MCI_QCOM_CLK_SELECT_IN_FBCLK` optional per controller or
board instead of enabling it for every QCOM variant.

Evidence: the old MSM SDCC driver enables only `MCI_QCOM_CLK_FLOWENA`. On the
M7, feedback-clock selection produces CMD52 timeouts at 10 and 25 MHz and an
invalid R5 response without it. At 400 kHz without feedback-clock selection,
the standard F1 enable sequence succeeds and brcmfmac reaches firmware
selection. eMMC still works in the same image.

Open risks:

- The current checkpoint changes the global QCOM variant. Scope the final
  change to SDCC3 or add a DT property before upstream submission.
- Test other QCOM SDCC/MMC boards and eMMC at all supported speeds.
- Probes 98 and 100 reach full WLAN initialization at actual 450 kHz and
  500 kHz. Test 1 MHz after correcting the SDC clock table before calling
  400 kHz a module limit.

## 3. SDIO low-speed byte mode

File:

- `drivers/mmc/core/sdio_io.c`

Candidate: use byte mode for SDIO extended transfers when the host clock is at
most 1 MHz.

Evidence: at 400 kHz a 32 KiB block exceeded the one-second SDIO timeout. Byte
mode sustains a sequence of 512-byte firmware writes and avoids the 32 KiB
backplane-window boundary. The device still resets before the download
completes.

Open risks:

- Confirm that the reset is unrelated to byte mode.
- Measure the throughput cost and test other low-speed SDIO devices.
- Decide whether the threshold belongs in the MMC core or in brcmfmac.

Rejected variants from probes 63 to 79: `datactrl_first`, a 63-block limit,
64-byte CMD53 with `MMC_QUIRK_BLKSZ_FOR_BYTE_MODE`, 32-byte FIFO bursts,
keeping `MMCIMASK1` enabled until `DATAEND`, the QCOM feedback-clock bits, a
500 ms WL reset delay, the public HTC `fw_bcm4335_b0.bin`, 16-word DMA bursts,
a 256-byte `brcmf_sdiod_ramrw()` cap and `MCI_DPSM_QCOM_DATA_PEND`. None
completed the first transfer. The 32-byte block with normal 64-byte FIFO bursts
remains the furthest run (259 bytes).

## 4. APQ8064 pinctrl registration order

Files:

- `drivers/pinctrl/qcom/pinctrl-msm.c`

Candidate: use `devm_pinctrl_register_and_init()` and call `pinctrl_enable()`
before `gpiochip_add_data()`.

Evidence: inherited `gpio-ranges` resolves the pinctrl provider during GPIO
registration. The old order caused repeated `EPROBE_DEFER` and blocked
`gpio-keys`.

Open risk: review other MSM pinctrl users for assumptions about GPIO-base
allocation and hog handling.

## 5. APQ8064 GPIO function flag

Files:

- `drivers/pinctrl/qcom/pinctrl-apq8064.c`
- `drivers/pinctrl/qcom/pinctrl-msm.h`

Candidate: export the APQ8064 `gpio` mux function with
`PINCTRL_GPIO_PINFUNCTION`.

Evidence: strict pinmux rejected `gpio-keys` because the GPIO function lacked
the GPIO flag.

Open risk: check whether any Downstream-only APQ8064 pin table relies on the
old declaration.

## 6. MSM IOMMU master lookup

File:

- `drivers/iommu/msm_iommu.c`

Candidate: resolve each master by device node and IOMMU specifier instead of
using a global client list.

Evidence: the old lookup could return NULL for a second client and caused an
early `qcom_iommu_of_xlate()` oops.

Open risk: test a platform with multiple IOMMU clients and multiple IOMMUs,
not only the M7.

## 7. Chipidea MSM USB peripheral setup

Files:

- `drivers/usb/chipidea/ci_hdrc_msm.c`
- M7 USB node in `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dts`

Candidate: keep the Qcom glue in peripheral mode, disable OTG session
detection, force VBUS active and document the separate `fs` clock.

Evidence: the old setup started as EHCI host and competed for the only UDC.
The corrected path enumerates the CDC ACM console reliably.

Open risk: test OTG and host use cases before generalizing the glue behavior.

## 8. HTC One M7 board support

Files:

- `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dts`
- `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul-diag.dts`
- `arch/arm/configs/m7_defconfig`

Candidate: submit the board in stages as subsystems become stable.

Current evidence: eMMC, USB ACM, Pstore, automatic Recovery and Synaptics
S3202 touchscreen work. BCM4335 SDIO enumerates, enables Function 1, completes the
firmware and confirmed partition-6 NVRAM download, starts CR4 and creates
`wlan0`. Probe 100 uses MMC SDIO interrupt polling and reports
`M7_WLAN_PRESENT=yes` at an actual 500 kHz and 1 bit. Association is not tested.

Probes 91 and 92 show that the OOB path still fails with Downstream's active-high
selection and no PM8921 GPIO 38 pull. Probe 93 removes only the OOB entry and
succeeds. The QCOM MMCI variant does not advertise `MMC_CAP_SDIO_IRQ`, so the MMC
core polls `SDIO_CCCR_INTx`.

Open risks:

- Fix or explain the OOB route before relying on it. Polling works but adds CPU
  and SDIO-bus traffic.
- Confirm that the confirmed partition-6 NVRAM range is valid across M7 units
  before generalizing the board support.
- Probes 94 to 96 all ran at 16 MHz because the SDC table rounded their requested
  rates upward. Probe 97 captured the command CRC failure. Probes 98 and 100 prove
  full WLAN initialization at actual 450 kHz and 500 kHz after the table fix.
- Test 1 MHz, then 4-bit mode, high-speed mode and association.
- Display, audio, Bluetooth, modem and cameras are not enabled.
- The defconfig is intentionally headless and not a daily-driver
  configuration.

## 9. MSM8960 SDC low-clock table

Files:

- `drivers/clk/qcom/gcc-msm8960.c`
- `tools/m7/test_sdc_clock_table.py`

Candidate: add exact 450 kHz, 500 kHz and 1 MHz entries to `clk_tbl_sdc` using
PXO and the existing M/N counters.

Evidence: `qcom_find_freq()` selects the first table entry at or above the
requested rate. The old table jumped from 400 kHz to 16 MHz. Probe 97 recorded
`clock=450000 actual=16000000 mclk=16000000`, followed by a CMD52 command CRC
failure and `-84` from all BCM4335 SDIO functions. Probes 98 and 100 recorded
actual 450 kHz and 500 kHz clocks and completed firmware, NVRAM, CR4 and control
initialization. Probe 100's complete dmesg has no SDCC3 error.

Open risks:

- Test the added rates on other MSM8960/APQ8064 SDC controllers and boards.
- Keep eMMC clock selection and all existing higher rates unchanged.
- Add a driver-level KUnit test if this is submitted upstream; the current
  repository test guards the source table and its rate arithmetic.

## Submission checklist

- Split generic driver fixes from M7 board data.
- Keep one logical fix per patch.
- Run `checkpatch.pl`, DTB checks and the relevant test suite.
- Record exact commit, image hash and last kernel message.
- Test standard hardware paths for regressions.
- Get Pascal's approval before sending mail or opening an upstream PR.
