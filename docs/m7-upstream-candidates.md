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
2. Skip FBR block-size writes for cards explicitly marked
   `MMC_QUIRK_NONSTD_SDIO`.

Evidence: the M7 BCM4335 responds to common CIS reads but not standard FBR
access. Skipping FBR/CIS probing and block-size writes lets brcmfmac reach its
Function 1 setup. A separate experiment showed that bypassing F1 enable only
moves the failure to ChipClkCSR. Published bcmdhd code does enable F1, so the
bypass is not an upstream candidate.

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
- Determine whether 400 kHz is an M7 module requirement or a symptom of the
  incomplete clock/power setup.

## 3. APQ8064 pinctrl registration order

Files:

- `drivers/pinctrl/qcom/pinctrl-msm.c`

Candidate: use `devm_pinctrl_register_and_init()` and call `pinctrl_enable()`
before `gpiochip_add_data()`.

Evidence: inherited `gpio-ranges` resolves the pinctrl provider during GPIO
registration. The old order caused repeated `EPROBE_DEFER` and blocked
`gpio-keys`.

Open risk: review other MSM pinctrl users for assumptions about GPIO-base
allocation and hog handling.

## 4. APQ8064 GPIO function flag

Files:

- `drivers/pinctrl/qcom/pinctrl-apq8064.c`
- `drivers/pinctrl/qcom/pinctrl-msm.h`

Candidate: export the APQ8064 `gpio` mux function with
`PINCTRL_GPIO_PINFUNCTION`.

Evidence: strict pinmux rejected `gpio-keys` because the GPIO function lacked
the GPIO flag.

Open risk: check whether any Downstream-only APQ8064 pin table relies on the
old declaration.

## 5. MSM IOMMU master lookup

File:

- `drivers/iommu/msm_iommu.c`

Candidate: resolve each master by device node and IOMMU specifier instead of
using a global client list.

Evidence: the old lookup could return NULL for a second client and caused an
early `qcom_iommu_of_xlate()` oops.

Open risk: test a platform with multiple IOMMU clients and multiple IOMMUs,
not only the M7.

## 6. Chipidea MSM USB peripheral setup

Files:

- `drivers/usb/chipidea/ci_hdrc_msm.c`
- M7 USB node in `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dts`

Candidate: keep the Qcom glue in peripheral mode, disable OTG session
detection, force VBUS active and document the separate `fs` clock.

Evidence: the old setup started as EHCI host and competed for the only UDC.
The corrected path enumerates the CDC ACM console reliably.

Open risk: test OTG and host use cases before generalizing the glue behavior.

## 7. HTC One M7 board support

Files:

- `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dts`
- `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul-diag.dts`
- `arch/arm/configs/m7_defconfig`

Candidate: submit the board in stages as subsystems become stable.

Current evidence: eMMC, USB ACM, Pstore, automatic Recovery and Synaptics
S3202 touchscreen work. BCM4335 SDIO enumerates, enables Function 1 and reaches
firmware selection, but `wlan0` is not operational.

Open risks:

- WLAN HT clock and NVRAM remain unresolved.
- Display, audio, Bluetooth, modem and cameras are not enabled.
- The defconfig is intentionally headless and not a daily-driver
  configuration.

## Submission checklist

- Split generic driver fixes from M7 board data.
- Keep one logical fix per patch.
- Run `checkpatch.pl`, DTB checks and the relevant test suite.
- Record exact commit, image hash and last kernel message.
- Test standard hardware paths for regressions.
- Get Pascal's approval before sending mail or opening an upstream PR.
