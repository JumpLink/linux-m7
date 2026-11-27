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

### 2026-11-26: DMA, PIO and transfer-size variants

Probes 75 to 79 tested the remaining host-controller and transfer-size
hypotheses. None completed the download:

- Data-first plus 32-byte FIFO bursts: immediate CRC failure `-84`.
- PIO with 64-byte FIFO and 32-byte blocks: 27 bytes, then the FIFO stayed
  full and `MMCIMASK1` was zero.
- 16-word QCOM DMA bursts: the DMA setup fell back to PIO and transferred 0
  bytes.
- Capping `brcmf_sdiod_ramrw()` transfers at 256 bytes: 18 bytes, then the
  same full-FIFO/zero-mask state.
- `MCI_DPSM_QCOM_DATA_PEND` for SDIO writes: the kernel did not reach the USB
  console at all; no ACM and no fastboot. This variant is reverted.

The best observed run is still the normal QCOM DMA path with 32-byte blocks:
259 bytes moved, then the TX FIFO stayed full, `MMCIMASK1` was zero and
`MMCIDATACNT` still held the remaining byte count. The 259-byte boundary is
`256 + 3`, but the 256-byte cap made the result worse, so it is not a simple
CMD53-size limit.

All temporary controller and brcmfmac changes are reverted. The tree is clean
at `f7a70bc4b` plus this documentation update.

### 2026-11-26: the download completes; the reset is after the reset vector

A temporary `brcmf_err()` trace in `brcmf_sdiod_ramrw()` showed that the
firmware transfer was never stuck at 259 bytes. The earlier monitor sampled at
3.6 s and the USB gadget re-enumerated at 25.8 s, which made a slow transfer
look like a stall. With a sample at 20 s the trace showed:

- 17 transfers of 32768 bytes from `0x00180000` through `0x001f8000`
- a final 12235-byte transfer at `0x00200000`
- the 1832-byte NVRAM transfer at `0x0023f8d8`
- the 4-byte reset vector write at address 0
- about 1.07 s per 32 KiB chunk at 400 kHz

The download therefore completes in about 19.7 s. The failure moved to the
post-reset path: `brcmf_chip_cm3_set_active()` releases the CM3 core, then the
USB ACM connection disappears at about 25.8 s and `wlan0` never appears. The
20 s register dump still shows `brcmf_wdog` in `brcmf_sdio_watchdog_thread`,
`MMCIDATACNT` at zero and no new pstore panic in the live dump.

The trace patch is kept outside the tree at
`/tmp/opencode/m7-ramrw-trace.patch`; the committed tree stays clean. The next
step is a post-reset pstore capture and a check of the CM3 reset/clock path,
not another controller-size experiment.

### 2026-11-27: stock firmware reaches the same post-reset timeout

Probe 82 replaced the generic LibreELEC image with HTC's stock
`fw_bcm4335_b0.bin` and kept the NVRAM and SDIO path unchanged. The stock image
is firmware 6.37.35.0; the generic image is 6.30.171.24. The code areas differ,
so this was a real firmware test rather than a header-only swap.

The stock image completed 17 transfers of 32768 bytes, a final 31221-byte
transfer, the 1832-byte NVRAM transfer and the 4-byte reset-vector write. At
23.04 s the first control receive timed out:

- `brcmf_sdio_bus_rxctl: resumed on timeout`
- `brcmf_bus_started: failed: -110`
- `brcmf_attach: dongle is not responding: err=-110`

The ACM connection disappeared at 25.82 s and `wlan0` never appeared. There
was no new pstore panic. The firmware choice is therefore not the immediate
cause.

The reset-vector write also settles the core type. Mainline takes the CR4 path,
which writes the vector to address zero and releases reset with CPUHALT clear.
Public BCM4335 enumeration logs report ARM CR4 core ID `0x83e`, matching this
path. The older HTC brcmfmac source's CM3 reset calls do not describe this
hardware. The next probe reads the downloaded firmware and NVRAM back from
Dongle RAM and compares every byte before reset; the normal non-debug build
currently skips that verification.

### 2026-11-27: the silent reboot is a hidden apps watchdog

Probes 83 to 85 exposed a separate failure. USB stayed available for about
26 s, then the phone reset and booted the same image again. Pstore contained
no panic. Disabling `PANIC_ON_OOPS` and the panic timeout did not change the
cycle, so this was not a kernel panic.

The APQ8064 watchdog enable registers read as zero for both WDT0 and WDT1.
Enabling the mainline QCOM watchdog driver did not stop the reset either.
HTC's downstream watchdog defaults explain the timing: a 22 s bark and a
bite three seconds later. A direct userspace experiment wrote `1` to WDT0's
reset register at `0x0208a038` once per second. The same boot then passed
60 s uptime, confirming that HBOOT leaves a watchdog running whose enable
bit is not visible to Linux.

The first-boot initramfs now has an opt-in `M7_WATCHDOG_PET=1` mode. It starts
the WDT0 reset-register pet loop immediately after devtmpfs is mounted. The
build manifest records the mode as `watchdog_pet`.

### 2026-11-27: complete RAM verification and local M7 NVRAM

Probe 86 combined the watchdog petter with a full read-back of the stock
firmware and NVRAM. USB stayed available for the complete 75 s capture. The
firmware comparison covered all 588277 bytes and the NVRAM comparison all
1832 bytes; both returned success. The dongle still timed out after the reset
vector at 39.91 s with `err=-110`. SDIO write corruption is therefore ruled
out.

The same probe enabled `CONFIG_ATAGS_PROC` to look for HTC's
`ATAG_MSM_WIFI`. Mainline reported `No ATAGs?` because this HBOOT path boots a
DTB. The diagnostic KEXEC/ATAGS config was removed again.

A read-only TWRP scan found text NVRAM in partitions 6 and 14. Partition 6
contains 45 keys; partition 14 contains 150 keys and has different boardrev
and MAC data. Both candidates stay under
`/tmp/opencode/m7-wlan-firmware-m7/` and are not committed or sent to public
subagents.

Probe 87 used that 2212-byte M7 NVRAM with the stock firmware. The watchdog
petter kept the device stable for 75 s, but `wlan0` still did not appear and
the log stopped after the firmware request. Probe 88 adds targeted callback,
clock and first-transfer markers to locate that earlier stall.

Probe 88 showed that the request and clock path are healthy. The callback
received the 588277-byte stock firmware and a 2220-byte prepared NVRAM block.
All 17 32 KiB firmware writes, the final 31221-byte write, the 2220-byte NVRAM
write and the 4-byte reset-vector write completed. Unlike the generic NVRAM
runs, no `dongle is not responding` error appeared during the following
60 s. `wlan0` still did not appear, so the remaining problem is after the
reset vector but before the cfg80211 device is registered.

The p14 extractor included adjacent radio-partition strings, partial keys and
duplicate `ccode` entries, so p14 is no longer the active input. The confirmed
p6 range is 815 bytes with 45 CRLF key/value lines and a trailing NUL. Probe 89
uses that raw p6 block.

The serial monitor now prefers a complete live host probe over the earlier
initramfs snapshot. It interrupts a stale foreground `/proc/kmsg` reader,
requests one delimited `dmesg` block after the live probe and bounds the final
CDC ACM close. Flushing pending TTY output removed a 32-second
`tty_wait_until_sent` delay; a real two-second capture now closes in 2.004 s.
The initramfs no longer writes its own extra `dmesg` block. Marker-order
regression tests reject an incomplete or reversed `dmesg` block.

Probe 89 adds temporary `M7_WLAN_TRACE` markers at the CR4 reset release, the
first post-reset F1 read, F2 and interrupt setup, control transmit/receive waits,
attach and bus start. The markers report stages, lengths and error codes only;
they do not log firmware, NVRAM, control packets, MAC addresses or device
identifiers. They will be removed after the failing stage is identified.

Probe 89 is built from `04de87aae` as kernel `7.1.0-g04de87aae3b2`. Its
`boot.img` SHA-256 is
`803cb873f536ca6b57adbeec960caf6cae9f7fb8aac7ca001eaf8f79ee86ea94`, and the
artifacts are staged under `/tmp/opencode/m7-wlan-probe-89/`. The embedded stock
firmware and p6 NVRAM hashes match the selected inputs.

### 2026-11-27: probe 89 reaches the first control-response timeout

A physical FASTBOOT transition allowed the lease-guarded `boot` flash. Fastboot
reported `OKAY` for both the write and reboot. The phone booted
`7.1.0-g04de87aae3b2`, and the watchdog petter kept ACM available for the live
read-only diagnostics.

The trace shows a successful firmware callback, all code and NVRAM writes, CR4
reset release, post-reset F1 access, F2 enable, OOB IRQ registration and the
first 36-byte control transmit. The first receive then waits 2.568 s without a
control response:

- `ctrl_wait_enter condition=0` at 20.712151 s
- `ctrl_wait_done condition=0 timeout=0 pending=0` at 23.279985 s
- `rxctl_done rxlen=0`
- `bus_preinit ret=-110`

No `oob_irq_seen` marker appeared. Live GPIO 38 reads high, but `/proc/interrupts`
has no IRQ 57 entry. After the failed attach, a read-only dump of SDCC3
`0x12180000..0x12180048` returned zero, while debugfs still reports `mmc0`
powered on at 400 kHz in 1-bit legacy mode.

The first capture falsely accepted the echoed shell command as a live probe and
dmesg block. The parser now requires standalone marker lines. Three regression
tests cover the echoed probe, echoed dmesg command and snapshot fallback.
Replaying the actual Probe 89 `serial.log` returns `ready=false`, an empty probe,
`source=None` and `dmesg_captured=false`; the old run manifest is not a valid
success record.

### 2026-11-27: probe 90 captures the timeout state

Probe 90 keeps the Probe 89 firmware, p6 NVRAM, diagnostic DTB, 400 kHz 1-bit
SDCC3 setup and watchdog pet. It adds a temporary `M7_WLAN_TRACE` snapshot only
when the control wait ends without a condition, signal or remaining timeout.
The snapshot runs before brcmfmac starts recovery.

It records the driver's receive and interrupt counters, CCCR interrupt enables,
F1 interrupt masks and status, the host/device mailbox pair, frame length and
clock state, the OOB GPIO line level, and raw SDCC3 power, clock, command, data,
status, mask and FIFO registers. The MMCI callback is registered for all hosts
but returns immediately unless the QCOM DML variant is active. It changes no
controller register.

The snapshot separates four predictions:

1. If the CR4 is stopped or stuck, the device mailbox and frame state stay empty
   after the reset-vector write.
2. If only OOB delivery is broken, the device reports a pending response while
   the brcmfmac interrupt counter stays at zero.
3. If the SDCC3 receive path is stuck, the device or controller reports data
   while the driver still has `rxlen=0`.
4. If firmware, NVRAM or the first control frame is wrong, every receive
   indicator stays empty while the write and clock readbacks remain clean.

The staged build is kernel `7.1.0-g17664778f3fa-dirty`. Its manifest records
source commit `17664778f` with `dirty=true` because the Probe 90 changes were
still uncommitted at build time. The `boot.img` SHA-256 is
`567b1076300b4b6dde6372851b5c502fe4403928e36113f8c3bd02e4a4fc09f0`, and the
`zImage-dtb` SHA-256 is
`19e55ceb92918c5127fee0912389b11be2faa58620256900096fd4534acfcacf`.
Artifacts are staged under `/tmp/opencode/m7-wlan-probe-90/`. The firmware and
NVRAM hashes read back from the packaged initramfs match the selected inputs.
A physical FASTBOOT transition then allowed a lease-guarded `boot` flash. Fastboot
reported `OKAY` for the write and reboot.

The phone reached the initramfs shell and the watchdog kept it alive. The first
capture is invalid. The old tool sent its 1.4 KiB probe before `M7_READY_END`, so
the input interleaved with the initramfs output. BusyBox ash also truncated the
long command line. The original run manifest therefore remains a failure record,
not a successful live probe.

A later capture saved a complete 25,158-byte dmesg block in `live-dmesg.log`. It
ends with `M7_DMESG_END` and a fresh `/ #` prompt. The kernel trace confirms the
firmware and p6 NVRAM writes, CR4 reset release, F1/F2 setup, OOB registration and
the first 36-byte control transmit. The receive wait runs from 20.690121 s to
23.199949 s with `condition=0`, `pending=0` and `rxlen=0`.

The timeout snapshot separates device activity from host delivery:

- `intrcount=0`, `pollcnt=0`, `f1=0` and `f2rxh=0`: brcmfmac saw no receive event.
- `oob_irq=57`, `oob_line=0`, `oob_err=0`: the OOB request succeeded, but the
  nested IRQ was not observed.
- `intstatus=208000c0`, `hostintmask=200000f0`, `intmask=c701ff0f` and
  `funcintmask=1`: interrupt state is present on the device side.
- `tosbmailbox=0`, `tohostmailbox=4`, `tohostdata=00040008`: the response-side
  mailbox is populated. This weakens a stopped-CR4 explanation but does not by
  itself prove that a complete control response was written.
- `rframebc=0`, `framectrl=0`, `clkcsr=c2`: no host frame count is visible and the
  clock request is active.
- SDCC3 remains at 400 kHz in 1-bit mode. The controller has no active command or
  data transfer, an empty FIFO and `datacnt=0`.

The OOB line value comes from `irq_get_irqchip_state()` with
`IRQCHIP_STATE_LINE_LEVEL`. It is not a direct PM8921 GPIO register read, so it
must not be treated as proof that the physical pin is low.

The capture tool now sends 21 standalone probe commands, at most 113 bytes each.
It waits for `M7_READY_END` or a fresh `/ #` prompt before sending them. The first
interrupt is Ctrl-C followed by a newline, because Ctrl-C alone does not redraw an
idle BusyBox prompt. The parser strips repeated `/ # ` prefixes before matching
markers and keys. It still rejects echoed commands. The dmesg command now ends
with a real newline and waits for a fresh prompt after the host probe.

Tests cover incomplete ready output, a complete marker block, a fresh prompt,
prompt-prefixed probe and dmesg blocks, the per-command size limit and the real
dmesg newline. The original Probe 90 dmesg is valid evidence; the original run
manifest is not evidence of a complete live host probe.

Run `20261127T133051Z` completed the corrected live capture on the same image. Its
25,887-byte serial log reports `ready=true`, `probe_source=host`,
`M7_WLAN_PRESENT=no`, `dmesg_captured=true` and a final shell prompt. The extracted
dmesg block is 24,777 bytes. This satisfies the live-probe capture requirement but
not the WLAN success criterion.

### 2026-11-27: live PMIC diagnostics and active-high OOB candidate

Run `20261127T134056Z` added read-only GPIO, pinctrl and IRQ diagnostics without
flashing or rebooting. It reports `ready=true`, `probe_source=host`,
`dmesg_captured=true`, `tty_closed=true` and `M7_WLAN_PRESENT=no` after 2160.58 s
of uptime. The 6,834-byte diagnostic block separates two different GPIO 38 pins:

- APQ TLMM GPIO 38 is unrelated to WLAN and reads high with a pull-up.
- The WLAN host-wake pin is PM8921 GPIO 38. It is an input in normal mode with
  VIN2, a 10 uA pull-down and push-pull buffer settings.
- The pinctrl driver's `VIN2` label is the numeric encoding for PM8921 S4, so the
  voltage source already matches Downstream. The pull does not: Downstream uses
  `PM_GPIO_PULL_NO` while WLAN is on and a pull-down only while it is off.

IRQ 57 does not appear in the post-failure `/proc/interrupts` dump because the
failed brcmfmac probe frees its handler. That absence is not an interrupt count
and does not prove that no IRQ arrived during the 2.568 s control wait.

The source trace gives the next single-variable test. Downstream defines
`HW_OOB=1` and requests `IORESOURCE_IRQ_HIGHLEVEL`. brcmfmac also describes its
OOB path as level-triggered. The M7 DTS used `IRQ_TYPE_EDGE_FALLING`, which makes
`pm8xxx_irq_set_type()` enable only the falling edge. brcmfmac consequently
writes `SEPINT=0x03`, with active-low polarity. Probe 90 confirms that read-back.

Commit `74bb395f0` changes only the M7 host-wake type to `IRQ_TYPE_LEVEL_HIGH`.
This selects the PMIC rising-level source and makes brcmfmac write `SEPINT=0x07`.
It leaves the GPIO pull, SDIO clock, bus width, firmware and NVRAM unchanged. The
PMIC's `handle_level_irq` path is compatible with this source because its
mask/ack operation latches and clears the event before dispatch.

Probe 91 packages that DTB with the unchanged Probe 90 kernel payload. Its
`boot.img` SHA-256 is
`30cca25340f9e1a2d4da4d6cf2c9d5a74b641d12a64055cfe5a3cb8d248bdf74`, its
`zImage-dtb` SHA-256 is
`029770f5074988c04badcdaeda46f146a1fe9620ce5589488d2c305cde9fe8ee`, and its
DTB SHA-256 is
`904b2822ea863d52c80fe4084d64d6779c143ca36c4866d0533f2b68c71fc7f8`. The
packaged firmware and p6 NVRAM match the confirmed Probe 90 hashes. The kernel
release remains `7.1.0-g17664778f3fa-dirty` because only the DTB changed.

Run `20261127T155624Z` flashed only `boot` through the lease and product guard,
then rebooted successfully. The initial probe was too early; a later read-only
probe at 186.38 s captured the complete trace. `SEPINT=0x07` proves that the
active-high selection reached the chip. The control wait still ended with
`condition=0`, `pending=0`, `rxlen=0`, `oob_line=0`, `intrcount=0` and
`bus_preinit ret=-110`. A complete live probe reports `M7_WLAN_PRESENT=no`.

### 2026-11-27: Probe 92 removes the host-wake pull

Commit `c92801c4f` adds only `bias-disable` to PM8921 GPIO 38. Probe 92 reuses the
Probe 91 kernel payload and the confirmed firmware and p6 NVRAM. Its `boot.img`
SHA-256 is
`21383c2bba5f20a56c1bb6b5b0bc690a2a37dddc66dcb41e58e96c851f381096`.

Run `20261127T160424Z` again used the guarded `boot`-only flash path. The complete
late probe at 102.38 s confirms `gpio38: in normal VIN2 no pull`. The chip still
reports `SEPINT=0x07`, but `oob_line=0`, `intrcount=0`, `rxlen=0` and
`bus_preinit ret=-110`. The complete live probe reports `M7_WLAN_PRESENT=no`.
The pull-down is therefore not the cause of the missing OOB interrupt.

Both Probes 91 and 92 leave `intstatus=0x208000c0`, `hostintmask=0x200000f0`,
`tohostmailbox=4` and `tohostdata=0x00040008` at the timeout. Response-side data
is pending, but no host interrupt consumes it. Probe 93 will remove only the OOB
interrupt entry so the MMC core polls `SDIO_CCCR_INTx`. If that consumes the
pending status, the fault is in OOB delivery rather than the SDIO control frame.

Probe 93 reuses the same kernel, firmware, p6 NVRAM, 400 kHz clock, 1-bit bus and
GPIO configuration. Its `boot.img` SHA-256 is
`70ce4cce4b547282c1ded1406e41aa4a5b155f05b2071b4038069cdb49dc929f`.
An attempted automatic `reboot-bootloader` transition from Probe 92 enumerated
as Qualcomm `QHSUSB_DLOAD` instead of Fastboot. No EDL write was attempted. A
physical power cycle and manual Fastboot selection restored the guarded path.

Run `20261127T162002Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. The first capture returned before brcmfmac finished, so it
did not count as validation. A later read-only capture at 114.86 s completed the
live probe and the full dmesg block. It reports `M7_WLAN_PRESENT=yes` and
`M7_WLAN_STATE=down`.

The trace now shows `irq_register_enter oob=0`. The first control response arrives
in about 4 ms, `bus_preinit ret=0`, and `attach_done err=0`. This proves that the
firmware control path works. The QCOM MMCI variant does not advertise in-band
SDIO IRQ support, so the MMC core polls `SDIO_CCCR_INTx` and dispatches the SDIO
function handler. OOB delivery remains broken on this board, but polling is a
working fallback.

### 2026-11-27: Probe 94 fails at 1 MHz

Probe 94 changes only `max-frequency` from 400 kHz to 1 MHz. The kernel payload,
firmware, p6 NVRAM and extracted initramfs contents are identical to Probe 93.
Its `boot.img` SHA-256 is
`edaf2ffd3da2815a20e513e7cd91f76e65ca6325405c8eff2106b2a138cd909f`.

Run `20261127T165849Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted successfully. The complete late probe at 80.97 s reports
`M7_WLAN_PRESENT=no`. The full dmesg block shows that SDCC3 still enumerates the
card, but all brcmfmac SDIO functions fail with `-84` before firmware download.
No firmware or control-frame trace runs. This isolates an early SDIO transfer
failure at 1 MHz. The DTS returns to the proven 400 kHz setting; Probe 95 will
test 500 kHz as the next single-variable clock step.

### 2026-11-27: Probe 95 fails at 500 kHz

Probe 95 changes only `max-frequency` from 400 kHz to 500 kHz. The kernel payload,
firmware, p6 NVRAM and extracted initramfs contents are identical to Probe 93.
Its `boot.img` SHA-256 is
`6dd145cd9316e230bafee664edfd992e75187245ece7d1b703f2ed7b4d9ad58e`.

Run `20261127T172904Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. The complete late probe at 78.05 s reports
`M7_WLAN_PRESENT=no`. SDCC3 still creates the SDIO card, but Functions 1, 2 and 3
all fail with `-84` at 0.748 s. No firmware or control-frame trace runs. This is
the same early failure as Probe 94, now at 500 kHz.

The DTS returns to the proven 400 kHz setting. Probe 96 will test 450 kHz to
narrow the clock boundary without changing bus width, transfer mode or pins.

### 2026-11-27: Probe 96 fails at 450 kHz

Probe 96 changes only `max-frequency` from 400 kHz to 450 kHz. The kernel payload,
firmware, p6 NVRAM and extracted initramfs contents are identical to Probe 93.
Its `boot.img` SHA-256 is
`1039079242ff8687603cf12622aad54ee466ab135576b0e0d26856ec1ca4759e`.

Run `20261127T173748Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. The complete late probe at 83.39 s reports
`M7_WLAN_PRESENT=no`. SDCC3 again creates the card, but Functions 1, 2 and 3 all
fail with `-84` at 0.835 s. No firmware or control-frame trace runs.

Three clock points now fail with the same early error: 450 kHz, 500 kHz and
1 MHz. Another clock-only run would not identify the failing transfer. The DTS
returns to 400 kHz. Probe 97 will keep 450 kHz and add temporary MMCI command and
data error logs to distinguish command CRC, data CRC and timeout paths. The
instrumentation will be removed after the trace is captured.

### 2026-11-27: Probe 97 identifies 16 MHz clock rounding

Probe 97 keeps 450 kHz in the DTS and adds temporary MMCI command, data and IOS
error logs. Firmware, p6 NVRAM and extracted initramfs contents remain identical
to Probe 93. Its `boot.img` SHA-256 is
`168a5b3aa2480f82c368f5f1a2e0e479c78bac9bb174d95e89ec7a72843fd7ea`.

Run `20261127T180408Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. The complete late probe at 75.00 s reports
`M7_WLAN_PRESENT=no`. SDCC3 first enumerates at 400 kHz. When the MMC core raises
the clock to the requested 450 kHz, the trace reports
`M7DBG ios clock=450000 actual=16000000 mclk=16000000`. The next CMD52 to F1
fails with `status=0x00000001`, the command CRC bit, and Functions 1, 2 and 3
return `-84`.

The MSM8960 SDC table has 400 kHz and 16 MHz but no entry between them.
`qcom_find_freq()` selects the first entry at or above the request, so Probes 94,
95 and 96 all ran at 16 MHz. They did not measure 1 MHz, 500 kHz or 450 kHz.

### 2026-11-27: Probe 98 reaches WLAN at 450 kHz

Commit `4eb6d13b9` adds exact 450 kHz, 500 kHz and 1 MHz entries to the shared
MSM8960 SDC clock table. A new source-table regression test checks selection,
rate arithmetic, ordering and counter widths. Probe 98 changes only the DTS to
450 kHz and keeps the temporary MMCI instrumentation. Its `boot.img` SHA-256 is
`e7517e7db83097886729aba1b00834174fa58d40c347157b1a3a9fabbc2cef04`.

Run `20261127T181819Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. The early probe at 2.37 s is not validation because firmware
download is still running. The trace confirms
`clock=450000 actual=450000 mclk=450000`, then completes firmware at 18.508 s,
p6 NVRAM at 18.532 s, CR4 activation and all control exchanges. A complete late
live probe at 52.74 s reports `M7_WLAN_PRESENT=yes` and `M7_WLAN_STATE=down`.
The complete dmesg block has no command CRC or data error. One CMD52 timeout
appears at 19.812 s after `attach_done`, during SDIO interrupt polling, without
preventing initialization.

The early `-84` failures were a clock-table rounding bug, not a BCM4335 limit at
450 kHz. The command and data debug logs are removed. The IOS clock log remains
temporarily for the 500 kHz and 1 MHz steps.

### 2026-11-27: Probe 99 reaches WLAN at the requested 500 kHz setting

Probe 99 changes only the DTS from 450 kHz to 500 kHz. Firmware, p6 NVRAM and
extracted initramfs contents remain identical to Probe 93. Its `boot.img` SHA-256
is `f9556b4374f11e5beed7203b53cc5a5b91c95a0c4d8f4c688b42d4dd31857bdc`.

Run `20261127T183711Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. Firmware completes at 16.906 s, p6 NVRAM at 16.928 s and
brcmfmac attachment at 18.243 s without `-84`. The complete late probe at
153.25 s reports `M7_WLAN_PRESENT=yes` and `M7_WLAN_STATE=down`.

The temporary IOS log still checked MMC index 0. SDCC3 is `mmc1` in this run, so
the trace contains no SDCC3 clock line. This run proves initialization but does
not prove the actual 500 kHz rate. Probe 100 corrects the temporary filter and
repeats the same rate.

### 2026-11-27: Probe 100 validates an actual 500 kHz clock

Probe 100 changes only the temporary IOS log filter from MMC index 0 to physical
address `0x12180000`. The DTS stays at 500 kHz, and firmware, p6 NVRAM and
extracted initramfs contents remain unchanged. Its `boot.img` SHA-256 is
`f1d942e88c1149ea19a97aa4f58e3d281d4bb3bc703be897e67db47fc7899494`.

Run `20261127T184621Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. SDCC3 first enumerates at 400 kHz, then reports
`clock=500000 actual=500000 mclk=500000 width=0 timing=0`. Firmware completes at
16.870 s, p6 NVRAM at 16.892 s, CR4 starts and `attach_done` follows at 18.053 s.
The complete late probe at 49.23 s reports `M7_WLAN_PRESENT=yes` and
`M7_WLAN_STATE=down`. The single complete dmesg block has 735 lines and contains
no SDCC3 command, data or timeout error.

### 2026-11-27: Probe 101 validates an actual 1 MHz clock

Probe 101 changes only the DTS from 500 kHz to 1 MHz. The temporary physical-
address IOS log, firmware, p6 NVRAM and extracted initramfs contents remain
unchanged. Its `boot.img` SHA-256 is
`a87375df1ea68d25d4c5530c5d4fa29d5566dbfb9ae6e7b8ab85e8463b23d487`.

Run `20261127T185319Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. After 400 kHz enumeration, SDCC3 reports
`clock=1000000 actual=1000000 mclk=1000000 width=0 timing=0`. Firmware completes
at 9.385 s, p6 NVRAM at 9.396 s, CR4 starts and `attach_done` follows at 10.536 s.
The complete late probe at 78.38 s reports `M7_WLAN_PRESENT=yes` and
`M7_WLAN_STATE=down`. The single complete dmesg block has 726 lines and contains
no SDCC3 command, data or timeout error.

### 2026-11-27: Probe 102 confirms the clean 1 MHz image

Probe 102 removes the temporary `M7DBG` IOS log from MMCI and keeps the 1 MHz
DTS. Firmware, p6 NVRAM and extracted initramfs contents remain unchanged. The
built kernel contains no `M7DBG` string. Its `boot.img` SHA-256 is
`a9cc01651ed26d144f1d1d1695ca79b52f0254ec26c083371efcee68538a5324`.

Run `20261127T190159Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. Firmware completes at 9.376 s, p6 NVRAM at 9.388 s and
`attach_done` at 10.532 s. The complete late probe at 52.40 s reports
`M7_WLAN_PRESENT=yes` and `M7_WLAN_STATE=down`. The single complete dmesg block
has 715 lines, zero `M7DBG` lines and no SDCC3 command, data or timeout error.

### 2026-11-27: Probe 103 keeps the 1-bit SDIO bus

Probe 103 changes only the DTS bus width from 1 bit to 4 bits. The clock stays at
1 MHz, and firmware, p6 NVRAM and extracted initramfs contents remain unchanged.
Its `boot.img` SHA-256 is
`2c288675f9366172e2778d5e63588d53e1c656aefc5c799ed702551ce1f73b11`.

Run `20261127T191135Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. The complete late probe at 53.28 s reports
`M7_WLAN_PRESENT=yes` and `M7_WLAN_STATE=down`. A read of `MMCICLOCK` at physical
address `0x12180000` returns `0x00000001`; bits 10:9 are zero, so the controller
still uses 1 bit. The complete dmesg block has 715 lines and no SDCC3 command,
data or timeout error.

The two early `mmc1: switch to bus width ... failed` messages belong to eMMC at
`0x12400000`. In this run SDCC3 is `mmc0` at `0x12180000`; host numbering is not
stable. `sdio_enable_wide()` skips the width change without an error when the
host lacks 4-bit capability or when CCCR advertises low speed without 4-bit
block mode. The DTS enables host 4-bit capability, and SDIO initialization
completes without an error while the controller remains at 1 bit. The remaining
path is the BCM4335 CCCR capability check. This matches the earlier 2026-11-26
4-bit failure. The DTS returns to the proven 1-bit setting.

### 2026-11-27: Probe 104 validates SD high-speed timing

Probe 104 changes only the DTS from deleting `cap-sd-highspeed` to enabling it.
The clock stays at 1 MHz, the bus stays at 1 bit, and firmware, p6 NVRAM and
extracted initramfs contents remain unchanged. Its `boot.img` SHA-256 is
`e6d7d15710ef68a03fea28ceb88e6f16231e83bec25d9ca23c95dc0e2f9ae327`.

Run `20261127T192434Z` verified `product: m7_ul`, flashed only `boot` through the
lease, and rebooted. SDCC3 is `mmc0` at `0x12180000` and reports
`new high speed SDIO card at address 0001`. Firmware completes at 9.342 s, p6
NVRAM at 9.354 s, CR4 starts and `attach_done` follows at 10.491 s. The complete
late probe at 54.09 s reports `M7_WLAN_PRESENT=yes` and `M7_WLAN_STATE=down`.
A read of `MMCICLOCK` returns `0x00000001`, so the controller still uses 1 bit.
The complete dmesg block has 737 lines and no SDCC3 command, data or timeout
error. The early `mmc1` hardware-reset error belongs to eMMC at `0x12400000`.

### 2026-11-27: Optional WLAN tools build reproducibly

The diagnostic image can now carry static ARMv7 `wpa_supplicant` 2.11,
`wpa_cli` and `iw` 5.19. `tools/m7/build-wifi-tools.sh` builds them in a pinned
Debian bookworm container from SHA-256-pinned source archives. Two consecutive
builds produced identical binaries:

- `iw`: `4a1cc0c4a91ecf162a0f142e06cf4094daffc7a7d188530cdd3f1174dfbd61cf`
- `wpa_cli`: `9e02de817364eefe821d6d48597956f2573b3cb3018f5b207da72266e26adff9`
- `wpa_supplicant`: `69628963f4e1039bc4699b52487784c0057b08b21921dab86407a350131abb5d`

`tools/m7/wifi_tools.py` rejects missing, non-ARM, non-executable and
dynamically linked binaries before packaging. It installs a supplied WPA
configuration as mode-0600 `/etc/wpa_supplicant.conf`; the build manifest records
only its presence, never its path, hash or contents. Credential-bearing builds
are accepted only outside the checkout or under `build/`.

The initramfs also exposes the BusyBox `ip`, `ifconfig`, `route`, `udhcpc`,
`ping`, `wget` and `nc` applets, and it ships
`/usr/share/udhcpc/default.script` so a `udhcpc` lease applies the address,
the default route and `resolv.conf`. No association was attempted at that point.

### 2026-11-27: Probe 105 scans from the clean tools build

Probe 105 builds from clean commit `1a9dcb0ed` with the validated 1 MHz, 1-bit,
high-speed DTS, the diagnostic reboot and the watchdog pet. The image is
15,122,432 bytes with SHA-256
`1066f4c2bdd24014de60d6e968153c1aed8266a8616211d112a1c5e62f5137f0`.

- The guarded flash of `boot` and the following reboot returned `OKAY`.
- A complete late `M7_HOST_PROBE` at 97.86 s reports `M7_WLAN_PRESENT=yes`,
  `M7_SDCC3_PRESENT=yes` and `M7_WLAN_STATE=down`.
- brcmfmac attach completes at 10.43 s with `attach_done err=0`.
- `ip link set wlan0 up` returns 0, and `iw dev wlan0 info` reports a managed
  interface on channel 1. Netlink works over the polling SDIO path.
- `iw dev wlan0 scan` returns three BSS on 2.4 GHz and 5 GHz (channel 116).
- After the scan the data path logs two `brcmf_sdio_hdparse: HW header checksum
  error` lines; the driver terminates those frames and keeps running.
- Association and DHCP remain untested because the image carries no credentials.

The scan output stays outside the repository because it contains neighbouring
SSIDs and device addresses.

### 2026-11-27: Probe 106 associates and reaches the network

Probe 106 uses the same kernel and DTB as Probe 105; only the initramfs adds a
credential-bearing `/etc/wpa_supplicant.conf` built from the host's existing
NetworkManager profile outside the repository. The image is 15,122,432 bytes
with SHA-256
`b4499394bc5f004055dac7720895ddfdf7f09226069ea13acc20934c21d4fc6f`, and the
manifest records only `wpa_supplicant_config: true`.

- The guarded flash of `boot` and the following reboot returned `OKAY`.
- A complete late `M7_HOST_PROBE` at 101.43 s reports `M7_WLAN_PRESENT=yes`.
- `wpa_supplicant` 2.11 associates and reports `wpa_state=COMPLETED`,
  `key_mgmt=WPA2-PSK` and `pairwise_cipher=CCMP` on channel 1.
- `udhcpc` obtains a lease, sets the address and the default route, and writes
  `resolv.conf` from the lease.
- `ping` reaches the gateway and the internet with 0 % loss, and `wget`
  fetches a page over HTTP.
- The SDIO receive path logs 8 `HW header checksum error` lines over the run;
  the driver terminates or aborts those frames and keeps running.
- After a long transfer burst the first ARP resolution failed. A
  `wpa_cli reassociate` restored the link and 4/4 pings and `wget` succeeded
  again, so the failure is recoverable rather than fatal.
- `iw dev wlan0 link` reports 1.0 Mbit/s rates at -71 dBm.

## Current result

The port boots Mainline Linux to a USB CDC ACM shell, detects eMMC, preserves
Pstore across failed boots, returns automatically to TWRP and runs the
Synaptics touchscreen. BCM4335 Function 1, firmware download, confirmed p6 NVRAM
and CR4 startup work. Probe 93 completes brcmfmac initialization over MMC SDIO
interrupt polling and a complete live `M7_HOST_PROBE` reports
`M7_WLAN_PRESENT=yes`. The interface remains down. Optional static
`wpa_supplicant`, `wpa_cli` and `iw` are packaged reproducibly, and Probe 105
scans three BSS on 2.4 GHz and 5 GHz from the live shell. Probe 106 associates
over WPA2-PSK, gets a DHCP lease and reaches the internet with ping and wget;
the SDIO receive path logs recoverable HW header checksum errors. Active-high
OOB and no-pull
tests both failed before polling succeeded, so the remaining OOB fault is in
signal delivery rather than the control frame. The bus now runs at 1 MHz
and 1 bit with SD high-speed timing. Probe 101 proves the actual clock, clean
Probe 102 confirms full WLAN initialization after all temporary `M7DBG` MMCI
logging is removed, Probe 103 shows that offering 4 bits does not change the
controller width, and Probe 104 validates high-speed timing. The DTS keeps the
proven 1-bit bus.

## Validation

- All 43 M7 Python unit tests pass, including the SDC clock-table and WLAN tool
  installer regressions.
- Two independent WLAN tool builds produced identical ARM binaries.
- Shell, Python syntax and `git diff --check` pass.
- The Probe 90 kernel and DTB build passed without warnings.
- The Probe 91, 92 and 93 DTBs compile, and `checkpatch --strict` reports no
  errors, warnings or checks for their source diffs.
- All three probes reuse the byte-identical kernel payload and the confirmed
  firmware and p6 NVRAM contents.
- Hardware validation uses the guarded `boot`-only flash path on HBOOT 1.61.
- Probes 91 and 92 reached the ACM shell, returned `OKAY` from flash and reboot,
  and produced complete dmesg blocks. Both report `M7_WLAN_PRESENT=no`.
- Probe 93 returned `OKAY` from flash and reboot. A later complete live probe and
  dmesg capture report `M7_WLAN_PRESENT=yes`. The early capture before brcmfmac
  completion is not used as validation.
- Probe 94 returned `OKAY` from flash and reboot. Its complete late probe and
  dmesg capture report `M7_WLAN_PRESENT=no` and an early `-84` brcmfmac failure.
- Probe 95 returned `OKAY` from flash and reboot. Its complete late probe and
  dmesg capture report `M7_WLAN_PRESENT=no` and the same early `-84` failure.
- Probe 96 returned `OKAY` from flash and reboot. Its complete late probe and
  dmesg capture report `M7_WLAN_PRESENT=no` and the same early `-84` failure.
- Probe 97 returned `OKAY` from flash and reboot. Its complete late probe and
  dmesg capture show that the requested 450 kHz became 16 MHz and CMD52 failed
  with command CRC.
- Probe 98 returned `OKAY` from flash and reboot. Its complete late probe and
  dmesg capture confirm an actual 450 kHz clock and `M7_WLAN_PRESENT=yes`.
- Probe 99 returned `OKAY` from flash and reboot. Its complete late probe and
  dmesg capture report `M7_WLAN_PRESENT=yes`, but the temporary IOS filter misses
  SDCC3 as `mmc1`, so the run does not prove the actual clock.
- Probe 100 returned `OKAY` from flash and reboot. Its complete late probe and
  dmesg capture confirm an actual 500 kHz clock, no SDCC3 error and
  `M7_WLAN_PRESENT=yes`.
- Probe 101 returned `OKAY` from flash and reboot. Its complete late probe and
  dmesg capture confirm an actual 1 MHz clock, no SDCC3 error and
  `M7_WLAN_PRESENT=yes`.
- Probe 102 returned `OKAY` from flash and reboot with all temporary MMCI
  `M7DBG` logging removed. Its complete late probe and dmesg capture contain no
  `M7DBG` line or SDCC3 error and report `M7_WLAN_PRESENT=yes`.
- Probe 103 returned `OKAY` from flash and reboot with the host offering 4 bits.
  Its complete late probe and dmesg capture report `M7_WLAN_PRESENT=yes` and no
  SDCC3 error. `MMCICLOCK` remains at 1 bit, so 4-bit mode is not accepted.
- Probe 104 returned `OKAY` from flash and reboot with SD high-speed enabled.
  Its complete late probe and dmesg capture report `new high speed SDIO card`,
  `M7_WLAN_PRESENT=yes` and no SDCC3 error. `MMCICLOCK` remains at 1 bit.
- Probe 105 returned `OKAY` from flash and reboot from clean commit
  `1a9dcb0ed`. Its complete late probe reports `M7_WLAN_PRESENT=yes`, and
  `iw dev wlan0 scan` returns three BSS on 2.4 GHz and 5 GHz. The scan adds two
  recovered HW header checksum errors to the data path.
- Probe 106 returned `OKAY` from flash and reboot from clean commit
  `e0a0278de`. A late probe reports `M7_WLAN_PRESENT=yes`, `wpa_supplicant`
  reaches `wpa_state=COMPLETED` over WPA2-PSK, `udhcpc` obtains a lease and
  `ping` and `wget` reach the internet. A post-burst ARP failure recovers after
  `wpa_cli reassociate`.

## Next steps

1. Fix the SDIO receive-path HW header checksum errors before expecting stable
   throughput at 1 MHz.
2. Investigate the recoverable post-burst link stall that needs a reassociate.
3. Investigate higher clock rates separately after the receive path is stable.
4. Investigate OOB routing and MMCI SDIO IRQ support after the stable polling
   path is recorded.
5. Continue with display, audio, Bluetooth and modem as separate milestones.

See also:

- `docs/m7-upstream-candidates.md`
- `docs/m7-agent-log.md`
