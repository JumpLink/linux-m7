# HTC One M7 mainline worklog

This file records the port from its initial import to the current hardware
checkpoint. It contains no serial numbers, credentials or user data.

## Starting point

The port began with the public APQ8064 mainline tree at upstream commit
`15fbd13fe2475cf77fca0006b618bb5c929025bd`. The test device is an HTC One M7
(`m7ul`) with 2 GiB RAM, no A/B slots and HBOOT 1.61. The official HTCdev unlock
and TWRP `3.7.0_9-0-m7univ` were verified before Mainline work started.

The initial tree had the imported SoC basis, but no working M7 boot path. The
known constraints were:

- Mainline must use an appended DTB and an Android `boot.img`.
- The kernel loads at `0x80608000`; the ramdisk must not overlap it.
- HBOOT does not reliably execute `fastboot boot`, even for a known-good image.
- Diagnostics must not write to eMMC.
- S-OFF and third-party unlock services are out of scope.

## Milestones

### 2026-11-25 to 2026-11-26: board import and first boot path

- `40942a8a5` imported the APQ8064 Mainline basis.
- `ce3e2dc4c` added the first M7 board description, defconfig, build script and
  USB maintenance initramfs.
- `cb8305da2` documented the source map and HBOOT transport limits.
- `c3e57998b` recorded the locked-bootloader result before the official unlock.
- `a09e523b2` corrected M7 memory and the USB console setup.
- `4cb3fdc92` added guarded boot flashing and benchmark manifests.

The first working layout used `CONFIG_PHYS_OFFSET=0x80600000`,
`CONFIG_AUTO_ZRELADDR=n`, a ramdisk at `0x84600000` and 2048-byte pages. The
Downstream ramdisk offset `0x01800000` overlaps the decompressed Mainline
kernel and corrupts the initramfs.

### IOMMU, pinctrl and USB bring-up

`4e61789a0` collected the fixes that turned an early crash into a USB shell:

- `drivers/iommu/msm_iommu.c`: resolve each IOMMU master by device node and
  IOMMU instead of using a global client list. The old code could dereference
  NULL for a second client.
- `drivers/pinctrl/qcom/pinctrl-msm.c`: enable pinctrl before registering the
  GPIO chip so inherited `gpio-ranges` can resolve the provider.
- `drivers/pinctrl/qcom/pinctrl-apq8064.c` and `pinctrl-msm.h`: mark the APQ8064
  `gpio` mux function with `PINCTRL_GPIO_PINFUNCTION`.
- `drivers/usb/chipidea/ci_hdrc_msm.c`: keep the controller in peripheral mode,
  disable OTG session detection and force VBUS active.
- The M7 USB node uses separate RPM fabric, `USB_HS1_H_CLK` and
  `USB_HS1_XCVR_CLK` clocks.
- The defconfig builds only `g_serial`; `g_ether` previously claimed the sole
  UDC before the console gadget.

The host then enumerated `0525:a4a7` as `/dev/ttyACM0`, and the benchmark
reported `ready=true` with UDC state `configured`.

### Pstore and automatic recovery

The port reserves 1 MiB at `0x86000000` for Pstore/Ramoops. HTC's reboot reason
lives at `IMEM + 0xF00`, or `0x2A03FF00`, not at the initially guessed offset.
The diagnostic DTB maps panic and emergency restart to TWRP. An early zImage
patch writes the recovery magic before decompression so failures before driver
probe still return to Recovery.

`dump-pstore.sh` reads the region through a freestanding ARM reader, verifies
that `/tmp` is tmpfs and never mounts or writes eMMC. `parse_pstore.py` handles
the five dmesg slots, console, pmsg and ftrace zones, including a displaced
console header. Old crash slots remain distinguishable from the current boot
by kernel banner and build timestamp.

### 2026-11-26: touchscreen

`7ecf21ed8` enabled the Synaptics S3202 touchscreen:

- GSBI3 I2C, address `0x20`
- interrupt GPIO 34, falling edge
- reset GPIO 85, driven high through pinctrl
- PM8921 LDO 15 as `vdd`

The first attempt left the controller in reset and produced a level-low
interrupt storm with `Failed to read irqs, code=-6`. Driving the reset pin high
and using a falling-edge interrupt fixed it. The kernel reports
`manufacturer: Synaptics, product: s3202` and creates the touch input device
without IRQ errors.

`546a83366` documented the result. A clean build from that commit produced:

- kernel `7.1.0-g546a83366530`
- `ready=true`
- `M7_TOUCH_DRIVER=rmi4_i2c`
- `M7_INPUT_NAMES` containing `Synaptics s3202`
- zero touch IRQ errors in the serial log

### 2026-11-26: BCM4335 WLAN checkpoint

Public HTC and LineageOS sources identify the WLAN chip as Broadcom BCM4335 on
SDCC3. `WL_REG_ON` is PM8921 GPIO 16, host wake is GPIO 38 and the card power
range is 2.8 to 2.9 V. The 32 kHz define exists in the Downstream board header
but has no software consumer in the published M7 sources.

The current work adds:

- SDCC3 with a 2.9 V fixed rail and `mmc-pwrseq-simple`
- a 120 ms post-power delay and 1 ms power-off delay
- SDC3 clock, command and data groups with 12 mA drive strength
- BCM4335 SDIO function 1 and host-wake IRQ
- optional `M7_FIRMWARE_DIR` packaging for `brcmfmac4335-sdio.bin` and NVRAM
- WLAN, SDCC3, MMC-host and deferred-probe benchmark markers

The MMC trace proved that the chip responds to CMD5, CMD3, CMD7 and common CIS
reads. Standard FBR access fails. A late `brcm,bcm4335-fmac` fixup marks the
card `MMC_QUIRK_NONSTD_SDIO`; the MMC core skips per-function FBR/CIS probing
and FBR block-size writes. The first checkpoint also skipped CCCR function
enable, which let brcmfmac reach the Function 1 ChipClkCSR access. That access
timed out, so `wlan0` did not exist. A PM8921 GPIO 43 `func2` experiment did not
change the failure and was reverted.

### 2026-11-26: Function 1 enable diagnosis

The published bcmdhd path enables F1 through the host claim and a direct
`SDIO_CCCR_IOEx` write. It does not mark F1 as already enabled. The local
`sdio_enable_func()` bypass was therefore incorrect and has been removed in the
current work tree.

A quoted `dyndbg=` parameter in the boot-image command line made HBOOT 1.61
report `Active cmdline overflow! (1047 Bytes)`. That run never started Mainline
and is not a WLAN result. Repackaging with the previous 136-byte command line
booted normally.

The valid follow-up runs measured:

- standard `sdio_enable_func()`: `CCCR_IOEx` read returns `-110`
- tagged MMC instrumentation: the controller reports command timeout on that
  read, not CRC or response-decoding failure
- direct `CCCR_IOEx` write, matching bcmdhd: the write also returns `-110`

F1 remains inactive. The current direct-write branch and tagged logs are
experiments, not a completed fix. USB, eMMC and touchscreen remain functional.

## Current result

The port boots Mainline Linux to a USB CDC ACM shell, detects eMMC, preserves
Pstore across failed boots, returns automatically to TWRP and runs the
Synaptics touchscreen. WLAN has a recognized SDIO bus, but Function 1 is not
active and `wlan0` is not operational.

## Validation

- 11 Python unit tests pass.
- Shell and Python syntax checks pass.
- DTB builds pass without new warnings.
- `checkpatch.pl` reports 0 errors and 0 warnings for the current diff.
- Hardware validation uses the guarded `boot`-only flash path on HBOOT 1.61.

## Next steps

1. Resolve the BCM4335 Function 1 enable timeout at `CCCR_IOEx`.
2. Provide a usable NVRAM. No freely licensed M7-specific file is public; any
   device-local calibration must stay outside git.
3. Re-enable 4-bit and high-speed SDIO only after 1-bit operation is stable.
4. Add network userspace tools, then verify an actual association.
5. Continue with display, audio, Bluetooth and modem as separate milestones.

See also:

- `docs/m7-upstream-candidates.md`
- `docs/m7-agent-log.md`
