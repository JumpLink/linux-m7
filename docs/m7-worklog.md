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

- SDCC3 with PM8921 L6 card power, L7 IO power and `mmc-pwrseq-simple`
- a 120 ms post-power delay and 1 ms power-off delay
- SDC3 clock, command and data groups with 12 mA drive strength
- the Downstream `WL_REG_ON` electrical configuration on PM8921 GPIO 16
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

The published bcmdhd path enables F1 through the host claim and the standard
`sdio_enable_func()` path. Its low-level SDMMC code special-cases F2 enable and
disable, but it does not mark F1 as already enabled. The local
`sdio_enable_func()` bypass was therefore incorrect and has been removed.

A quoted `dyndbg=` parameter in the boot-image command line made HBOOT 1.61
report `Active cmdline overflow! (1047 Bytes)`. That run never started Mainline
and is not a WLAN result. Repackaging with the previous 136-byte command line
booted normally.

The valid follow-up runs measured:

- standard `sdio_enable_func()`: `CCCR_IOEx` read returns `-110`
- tagged MMC instrumentation: the controller reports command timeout on that
  read, not CRC or response-decoding failure
- direct `CCCR_IOEx` write: the write also returns `-110`

At this point F1 was still inactive. USB, eMMC and touchscreen remained
functional.

The SSBI PMIC GPIO binding uses one-based GPIO cells. The Mainline driver
subtracts `PM8XXX_GPIO_PHYSICAL_OFFSET` from GPIO and IRQ offsets, so the M7
values 16 for `WL_REG_ON` and 38 for host wake are correct. A temporary test
with GPIO cell 15 prevented SDIO initialization and was reverted.

### 2026-11-26: Function 1 online

The Downstream board code supplied the missing electrical details:

- SDCC3 uses PM8921 L6 at 2.95 V for card power and L7 at 1.8 V for IO.
- `WL_REG_ON` is a CMOS output on S4 with no pull-up.
- SDC3 uses 12 mA drive strength and pull-ups on command and data.
- The old MSM controller enables `FLOWENA` but not `SELECT_IN_FBCLK`.

Several plausible changes were measured and rejected. Four-bit mode failed
before brcmfmac started. A 1 ms reset-assert delay, three 1 ms write retries,
SD high-speed, 10 MHz with feedback-clock selection, GPIO 43 `func2` and an
explicit push-pull setting did not fix F1. The push-pull property also
overlapped the drive-strength encoding and was reverted.

Removing `SELECT_IN_FBCLK` changed the 25 MHz failure from command timeout to
an invalid `0xffffffff` R5 response. At 10 MHz the response was still invalid.
At 400 kHz the same controller path returned a valid response. The standard
MMC enable sequence then wrote `IOEx`, read `IORx = 0x02` and brcmfmac selected
`brcm/brcmfmac4335-sdio` for BCM4335/1.

Commit `604513c5e` contains the clean result: 1 bit, 400 kHz, no QCOM
feedback-clock selection, L6/L7 regulators, the Downstream `WL_REG_ON` pin
configuration and the standard `sdio_enable_func()` path. The temporary
direct-write, CRC and logging experiments are removed. A clean rerun reached
firmware selection again.

The earlier `HT Avail timeout` was a cleanup path: without an NVRAM file the
firmware request failed before the code download started.

### 2026-11-26: firmware download checkpoint

A generic LibreELEC BCM4335 NVRAM was downloaded only to
`/tmp/opencode/m7-wlan-firmware/` for testing. It is not M7 calibration and is
not committed. With that file present, brcmfmac started downloading
`brcmfmac4335-sdio.bin`.

At 400 kHz the first 32 KiB CMD53 block exceeded the one-second SDIO data
timeout. Restoring the standard FBR block-size writes fixed the immediate
failure. Smaller 4 KiB transfers then succeeded, but a block ending exactly at
the 32 KiB backplane-window boundary stalled. A 63-block split passed that
boundary. PIO was worse, and 4-bit mode did not complete the download either.

Commit `901cb4ac7` keeps the standard FBR writes and uses byte mode for SDIO
extended transfers whenever the host clock is at most 1 MHz. This avoids both
the oversized block timeout and the window-boundary block. The firmware
download then progresses through many successful 512-byte commands. The device
still resets silently before completion. Ramoops contains no new panic, only an
older IOMMU crash.

A QCOM-specific dummy CMD52 after each CMD53 write was also tested. It matched
the old MSM driver and returned success, but did not prevent the reset, so it
was removed.

### 2026-11-26: low-speed download is not a FIFO or clock-bit problem

Probes 63 to 74 tested the remaining small controller hypotheses. None completed
the download:

- `datactrl_first` for QCOM: immediate CRC failure `-84`.
- 63-block byte-mode limit at 400 kHz: first 4 KiB transfer stopped after 259
  bytes.
- `MMC_QUIRK_BLKSZ_FOR_BYTE_MODE` (64-byte CMD53): brcmfmac reached firmware
  selection but the first transfer did not start.
- 32-byte FIFO bursts with 64-byte and 32-byte blocks: no completed transfer.
- Leaving `MMCIMASK1` enabled for QCOM until `DATAEND`: no completed transfer.
- `MCI_QCOM_CLK_SELECT_IN_FBCLK` alone and together with bit 24: no completed
  transfer; the 32-byte run stopped after 5 bytes.
- 500 ms `WL_REG_ON` post-power-on delay: no completed transfer.
- HTC `fw_bcm4335_b0.bin` from the public LineageOS M7 vendor repository:
  same first-transfer stall, so the generic firmware blob is not the cause.

The best observed run remains 32-byte blocks with the normal 64-byte FIFO
bursts: 259 bytes moved, then the TX FIFO was full, `MMCIMASK1` was zero and
`MMCIDATACNT` still held the remaining byte count. The later 64-byte and
clock-bit variants were worse. All temporary controller changes were reverted;
the tree is clean at `4b63372ef` plus the documentation update.

Two infrastructure changes landed and were pushed:

- `c3ac95599` refuses every fastboot target whose `product` is not `m7_ul`.
- `4b63372ef` adds `/bin/reboot-bootloader`, a small static ARM helper that
  calls the Linux reboot syscall with `bootloader`, and uses it for the
  diagnostic no-console reboot.

The helper reaches the HBOOT menu, but the M7 USB port does not always
re-enumerate fastboot without a power keypress. The product guard and lease
remain mandatory for every write.

## Current result

The port boots Mainline Linux to a USB CDC ACM shell, detects eMMC, preserves
Pstore across failed boots, returns automatically to TWRP and runs the
Synaptics touchscreen. WLAN enumerates the BCM4335, enables Function 1 and
starts the firmware download when an NVRAM file is supplied. Low-speed byte
mode sustains the transfer, but the device resets before completion and
`wlan0` is not operational yet.

## Validation

- 11 Python unit tests pass.
- Shell and Python syntax checks pass.
- DTB builds pass without new warnings.
- `checkpatch.pl` reports 0 errors and 0 warnings for the current diff.
- Hardware validation uses the guarded `boot`-only flash path on HBOOT 1.61.

## Next steps

1. Identify the silent reset during the firmware download and complete one
   transfer without a watchdog or power reset.
2. Provide a usable M7 NVRAM. No freely licensed M7-specific file is public;
   any device-local calibration must stay outside git.
3. Raise the SDIO clock in steps after the 400 kHz firmware path is stable.
4. Re-enable 4-bit and high-speed SDIO only after 1-bit operation is stable.
5. Add network userspace tools, then verify an actual association.
6. Continue with display, audio, Bluetooth and modem as separate milestones.

See also:

- `docs/m7-upstream-candidates.md`
- `docs/m7-agent-log.md`
