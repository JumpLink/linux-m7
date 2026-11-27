# linux-m7

Mainline Linux bring-up for the **HTC One M7 (m7ul)**, based on the APQ8064
mainline tree maintained at
[`LogicalErzor/linux`](https://codeberg.org/LogicalErzor/linux), branch
`apq8064`.

## Status

**2026-11-26: HTCdev unlock, TWRP recovery and adb are verified. Mainline now
boots to the USB CDC ACM shell with a working Synaptics S3202 touchscreen. The
bench records `ready=true`, UDC state `configured`, the M7 device-tree model,
eMMC presence and the bound RMI4 driver. The port fixes the MSM IOMMU lookup,
pinctrl registration order, APQ8064 GPIO function flag and the Qcom USB
clock/role setup.**

The imported basis is Linux 7.1.0 at upstream commit
`15fbd13fe2475cf77fca0006b618bb5c929025bd`. The first device tree enables:

- APQ8064 / Krait 300 and the three M7 RAM banks from HTC's downstream kernel
- PM8921 + PM8821 and the M7 regulator voltages
- eMMC on SDCC1
- USB peripheral on HSUSB1, with a built-in `g_serial` console for early logs
- Synaptics S3202 touchscreen on GSBI3 I2C, IRQ GPIO 34, reset GPIO 85 and
  PM8921 LDO 15
- volume keys, reboot-mode handling and a 1 MiB Pstore/Ramoops region

WLAN reaches `wlan0` on SDCC3 at 1 MHz and 1 bit. Firmware and the confirmed
partition-6 NVRAM pass the read-back check, CR4 starts, and the MMC core delivers
control responses through SDIO interrupt polling. A complete live `M7_HOST_PROBE`
from the clean Probe 104 reports `M7_WLAN_PRESENT=yes`; the interface is down
until userspace brings it up. The diagnostic image can carry static ARM
`wpa_supplicant`, `wpa_cli` and `iw`; Probe 105 scans BSS on 2.4 GHz and 5 GHz
and Probe 106 associates over WPA2-PSK, gets a DHCP lease and reaches the
internet. Probes 107 and 108 trace the recoverable HW header checksum errors to
a PIO FIFO drain problem at 1 MHz byte mode: reads return stale bytes left from
the previous frame. DMA is ruled out, because it is disabled by design for
transfers below the FIFO size and every SDIO transfer here is 4 to 32 bytes.

Probes 91 and 92 isolated the old failure to OOB delivery. Active-high selection
reached the chip as `SEPINT=0x07`, and removing the GPIO 38 pull did not help.
Both runs left response data in the device mailbox without an OOB interrupt.
Probe 93 removed only the OOB interrupt entry. The QCOM MMCI variant does not
advertise `MMC_CAP_SDIO_IRQ`, so the MMC core polls `SDIO_CCCR_INTx` and calls
the registered SDIO function handler. That path consumes the responses and
finishes brcmfmac initialization.

Probes 94 to 96 did not reach their requested clocks. The MSM8960 SDC RCG rounded
450 kHz, 500 kHz and 1 MHz up to 16 MHz, where CMD52 failed with a command CRC
error and brcmfmac returned `-84` before firmware download. Probe 97 recorded the
actual rate and status. Commit `4eb6d13b9` adds exact low-rate entries to the SDC
clock table. Probes 98, 100 and 101 report actual 450 kHz, 500 kHz and 1 MHz
clocks and complete firmware, NVRAM, CR4 and control initialization. Probe 102
removes all temporary MMCI `M7DBG` logging and confirms the clean 1 MHz image.
Its complete dmesg has no SDCC3 command, data or timeout error. Probe 103 offers
4-bit mode, but `MMCICLOCK` stays at 1 bit and WLAN still attaches without an
SDIO error, consistent with a CCCR that advertises low speed without 4-bit
block mode. Probe 104 enables SD high-speed timing, reports
`new high speed SDIO card`, and completes firmware, NVRAM, CR4 and the live
`wlan0` probe without an SDCC3 error. `MMCICLOCK` remains at 1 bit. The DTS keeps
the proven 1-bit bus at 1 MHz. Association is not tested yet. Display, audio,
Bluetooth, modem and cameras remain separate milestones. The camera has no
mainline APQ8064 driver and is a separate long-term project.

The full history, current result and upstream candidates are recorded in
`docs/m7-worklog.md`, `docs/m7-upstream-candidates.md` and
`docs/m7-agent-log.md`.

## Build

Requirements: an ARM cross-compiler, `make`, `cpio`, `gzip`, `readelf`, AOSP
`mkbootimg`, and a **statically linked ARMv7 BusyBox**. On Fedora the kernel
cross-compiler package is `gcc-arm-linux-gnu` (prefix `arm-linux-gnu-`).

```sh
BUSYBOX=/path/to/busybox-armhf ./tools/m7/build.sh
python3 -m unittest discover -v -s tools/m7 -p 'test_*.py'
```

Artifacts are written to `build/m7/`:

| File | Purpose |
|---|---|
| `boot.img` | Android boot image for `fastboot flash boot` |
| `zImage-dtb` | Mainline zImage with the M7 DTB appended |
| `initramfs.cpio.gz` | Minimal rootfs with a USB ACM shell |
| `readmem` | Freestanding ARM reader for the fixed Pstore region |
| `SHA256SUMS` | Checksums for the generated images |
| `wifi-tools.json` | Optional WLAN tool hashes and credential-presence flag |

For a split build, `SKIP_KERNEL_BUILD=1` packages existing kernel artifacts and
`SKIP_READER_BUILD=1` reuses an already built `readmem`. This allows the kernel
to build in a container while AOSP `mkbootimg` runs on the host.

## WLAN userspace

`tools/m7/build-wifi-tools.sh` builds `wpa_supplicant` 2.11, `wpa_cli` and `iw`
5.19 as static ARMv7 binaries in a pinned Debian bookworm container. The source
archives are checked against fixed SHA-256 values, and two consecutive builds
produce identical binaries. The first build needs Podman and network access:

```sh
./tools/m7/build-wifi-tools.sh
M7_WIFI_TOOLS_DIR="$PWD/build/m7/wifi-tools" \
  BUSYBOX=/path/to/busybox-armhf ./tools/m7/build.sh
```

`wifi_tools.py` rejects missing, non-ARM, non-executable and dynamically linked
tools before packaging. The initramfs also adds `ip`, `ifconfig`, `route`,
`udhcpc`, `ping`, `wget` and `nc` BusyBox applets and the `udhcpc`
`default.script` that applies a lease.

A private test network can be embedded without putting credentials in the
repository. The configuration must contain
`ctrl_interface=/run/wpa_supplicant` and must live outside the checkout:

```sh
M7_WIFI_TOOLS_DIR="$PWD/build/m7/wifi-tools" \
M7_WPA_SUPPLICANT_CONF=/tmp/m7-wpa.conf \
  BUSYBOX=/path/to/busybox-armhf ./tools/m7/build.sh
```

The installer stores it as mode-0600 `/etc/wpa_supplicant.conf`. Its contents,
path and hash are excluded from `build-manifest.json`; the manifest records only
whether a configuration is present. A credential-bearing build is accepted only
under `build/` or outside the repository. Do not publish that `boot.img` or its
run directory.

From the live shell:

```sh
mkdir -p /run/wpa_supplicant
ip link set wlan0 up
iw dev wlan0 scan
wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf
wpa_cli -p /run/wpa_supplicant -i wlan0 status
udhcpc -i wlan0 -n -q
ip addr show wlan0
ip route
ping -c 3 1.1.1.1
```

`udhcpc` applies the lease with the packaged
`/usr/share/udhcpc/default.script`, which sets the address, the default route
and `resolv.conf`. A probe with a configuration therefore reaches the network
after a single `udhcpc` call.

Without a configuration, `iw dev wlan0 scan` still verifies scanning and
regulatory behaviour without exposing a passphrase.

The M7 kernel loads at `0x80608000`. Mainline uses a ramdisk address of
`0x84600000`, above the 28 MiB decompressed kernel. The downstream value
`0x81e00000` overlaps this kernel and corrupts the initramfs. Pages are 2048
bytes.

`ARCH_MULTIPLATFORM` and `AUTO_ZRELADDR` must stay disabled. M7 RAM starts at
`0x80600000`, which is not 128 MiB aligned; automatic relocation selects the
reserved address `0x80008000`. The builder checks `PHYS_OFFSET`, the fixed
decompress target and the ramdisk gap before packaging.

## Hardware test

The test unit is **S-ON and UNLOCKED** after the official HTCdev procedure.
S-ON remains set by design and protects the radio and SIM lock. No S-OFF
exploit or third-party unlock service is part of this project.

`fastboot boot` is a dead end on this HBOOT. TWRP's official M7 instructions
use `fastboot flash recovery`, and M7 reports document the same `fastboot boot`
failure from HBOOT 1.55 onward. A verified TWRP image returned `Booting OKAY`
and then immediately reappeared in fastboot, without adb.

LineageOS also warns about buggy M7 bootloader USB. Replacing the cable fixed
the transfer errors. TWRP now flashes to `recovery`, boots and exposes adb.
The mainline image flashes to `boot`, HBOOT reports `TAG:Ramdisk OK` and the
kernel reaches the USB ACM shell. A known-good image also fails through
`fastboot boot`, so `bench.sh` defaults to that path only for compatible
bootloaders. Use `M7_BOOT_METHOD=flash` on this HBOOT.

The touch controller needs GPIO 85 driven high before RMI4 probes. A pull-up
alone left it in reset and caused a level-low interrupt storm with
`Failed to read irqs, code=-6`. The reset pin now uses `output-high`, and GPIO 34
uses a falling-edge interrupt. The kernel then reports
`found RMI device, manufacturer: Synaptics, product: s3202` and creates the
touch input device without IRQ errors.

Pstore/Ramoops at `0x86000000` remains the diagnostic path for failed builds.
Boot TWRP after a failed attempt and read that RAM region before a power-off.
The console ring can retain the current boot even when the last crash slot is
stale.

HBOOT 1.61 exposes no RAM read command. `fastboot reboot recovery` was accepted
but did not start TWRP. A host watcher therefore cannot detect a silent HTC
logo bootloop or press the hardware keys.

For a recorded one-shot run:

```sh
FASTBOOT_SERIAL=... DURATION=30 ./tools/m7/bench.sh build/m7/boot.img
```

The bench waits up to 30 seconds for `/dev/ttyACM*`; override this with
`M7_TTY_TIMEOUT` on slower HBOOT runs. It accepts the initramfs ready marker and
also sends an `M7_HOST_PROBE` after init or a fresh shell prompt to verify a
responsive shell when the original marker was written before capture started.
Set `M7_REQUIRE_WLAN=1` to fail unless that live probe reports `wlan0`.

The serial monitor interrupts a stale foreground kernel-log reader, waits for the
initramfs ready marker or a fresh shell prompt, then sends 21 separate probe
commands. Each command is at most 113 bytes, so BusyBox does not truncate the
combined line. It captures `dmesg` once after the live probe and bounds the final
CDC ACM close. This keeps a blocked USB drain from adding about 32 seconds to every
run.

Keep the boot-image command line short. HBOOT 1.61 reported
`Active cmdline overflow! (1047 Bytes)` for a 186-byte line containing a quoted
`dyndbg=` option, while the previous 136-byte line booted. Put quoted debug
options in `CONFIG_CMDLINE` instead; the kernel still receives them when HBOOT
supplies its shorter command line.

If `fastboot boot` does not execute the image, the same tool can write and
reboot the `boot` partition. It refuses every partition except `boot`:

```sh
FASTBOOT_SERIAL=... M7_BOOT_METHOD=flash ./tools/m7/bench.sh build/m7/boot.img
```

The run directory contains `run-manifest.json`, raw serial/fastboot/USB logs
and the ready probe. The build directory also contains `build-manifest.json`.
Both schemas are shared with the
[phone workbench](https://github.com/JumpLink/werkstatt/blob/main/docs/projects/phone-workbench.md)
so kernel results can move into the smartphone benchmark without scraping a
terminal. Serial numbers, IMEIs and unlock tokens are excluded.

Keep TWRP as the recovery fallback. The mainline bench can flash only `boot`,
and its initramfs never writes to eMMC.

To move any adb state into fastboot automatically:

```sh
FASTBOOT_SERIAL=... ./tools/m7/watch-fastboot.sh 600
```

The watcher exits when Fastboot answers `getvar product`. It cannot act on a
silent HTC logo with no USB device; that state still needs a hardware reset.

## Pstore diagnostic

`m7_defconfig` enables Pstore console and Ramoops. The DTS reserves 1 MiB at
`0x86000000`, away from HBOOT's own RAM log near `0x85100000`. A diagnostic
command line can force panics on oops, soft lockups and hung tasks:

```sh
M7_CMDLINE='console=ttyGS0 root=/dev/ram0 rw init=/init loglevel=7 ignore_loglevel panic=5 oops=panic softlockup_panic=1 hung_task_panic=1' \
  BUSYBOX=/path/to/busybox-armhf ./tools/m7/build.sh
```

After a failed boot, enter TWRP before powering off and preserve the RAM dump.
The opt-in `M7_DIAGNOSTIC_REBOOT=1` initramfs probe reboots only when
`/init` runs without a USB console.

To read and decode the region over adb:

```sh
ADB_SERIAL=... ./tools/m7/dump-pstore.sh /tmp/m7-pstore
```

The build produces a freestanding ARM `readmem` binary. It opens `/dev/mem`,
seeks once with `_llseek` and reads exactly 1 MiB. ARM `_llseek` takes five
arguments; the reader passes `SEEK_SET` in `r4` and declares `r12` and the
condition flags as clobbered. Omitting `r4` made optimized builds pass the file
descriptor as the seek origin and fail with `EINVAL`. BusyBox `dd` is not safe
on this recovery kernel: it continued past the requested page into the unmapped
end of the first RAM bank and triggered a kernel panic at `0x88c00000`.

`dump-pstore.sh` verifies that `/tmp` is tmpfs, pushes the reader there, writes
the dump only to that RAM filesystem and pulls it to the host. It never mounts
or writes eMMC. Set `M7_READMEM` when the reader lives outside `build/m7/`.
`parse_pstore.py` decodes the five 128 KiB dmesg slots, the 128 KiB console,
64 KiB pmsg and 128 KiB ftrace slots. It also scans for a displaced console
header, which happens with this Ramoops layout, and reports every kernel banner
so a stale crash slot cannot hide the current console log. Ramoops `start` is
the next write position; valid bytes begin at `(start - size) % capacity`. The
parser keeps a `strings.txt` index for a damaged or overwritten region.

The verified TWRP kernel has `CONFIG_DEVMEM` disabled, so it cannot read the
region even though the automatic recovery route now works. A diagnostic HTC
3.4 kernel enables devmem and reserves `0x86000000` before TWRP starts. TWRP
also does not inherit the mainline reserved-memory node, so an empty dump from
an unmodified recovery kernel is inconclusive. A valid old record does not prove
that the latest boot reached Pstore: compare its kernel build timestamp and
symbol addresses with the image under test.

The current console record reaches `/init` at 2.838 seconds. Pinctrl first kept
deferring because `gpiochip_add_data()` resolves `gpio-ranges` before
`pinctrl_enable()` had published the provider. The driver now enables pinctrl
first. APQ8064 also lacked the GPIO flag on its `gpio` mux function, which made
the strict pinmux path reject `gpio-keys`. Both declarations are corrected.
USB had two built-in gadgets: `g_ether` claimed the only UDC before `g_serial`.
The defconfig now builds only `g_serial` and disables the Chipidea host role so
the controller starts directly as a peripheral. The M7 USB node uses the current
MSM8960 clock mapping: RPM fabric as `iface`, `USB_HS1_H_CLK` as `core` and
`USB_HS1_XCVR_CLK` as `fs`. For `dr-mode="peripheral"`, the Qcom glue also
disables OTG session detection and forces VBUS active. The host now enumerates
`0525:a4a7` as `/dev/ttyACM0`.

### Automatic recovery after a panic

`m7_defconfig` enables `SYSCON_REBOOT_MODE`. The diagnostic DTB maps the normal
reboot command to HTC's recovery magic `0x77665502`. Panic and emergency restart
pass a NULL command, so they enter TWRP when the reboot-mode and pinctrl drivers
have probed. The first valid Pstore log captures an oops in
`qcom_iommu_of_xlate()` at about 0.224 seconds and the following panic reboot.

HTC's downstream restart handler places the reboot reason at `IMEM + 0xF00`,
which is `0x2A03FF00` on APQ8064. The first port used offset `0x65C`; that was
wrong and explains why neither recovery test produced a USB state. After the
correction, the phone entered TWRP automatically and the watcher returned it to
fastboot.

`M7_EARLY_REBOOT_MODE=1` patches the first zImage instructions to write the
recovery magic to `0x2A03FF00` before decompression. The patch preserves the
boot arguments, uses only scratch registers and verifies the expected eight-NOP
prologue. Any later reset should then enter TWRP even if the kernel never
reaches a driver.

Build and flash the diagnostic variant once:

```sh
M7_DTB=qcom-apq8064-htc-m7ul-diag \
M7_CMDLINE='console=ttyGS0 root=/dev/ram0 rw init=/init loglevel=7 ignore_loglevel panic=5 oops=panic softlockup_panic=1 hung_task_panic=1 maxcpus=1' \
M7_DIAGNOSTIC_REBOOT=1 M7_EARLY_REBOOT_MODE=1 \
  BUSYBOX=/path/to/busybox-armhf ./tools/m7/build.sh
FASTBOOT_SERIAL=... M7_BOOT_METHOD=flash ./tools/m7/bench.sh build/m7/boot.img
FASTBOOT_SERIAL=... ./tools/m7/watch-recovery.sh 180 /tmp/m7-pstore
```

Start the watcher as soon as `bench.sh` returns. It waits for TWRP, preserves
Pstore, reboots to fastboot and reports whether a valid Pstore zone was found.
The recovery partition's verified kernel has `devmem` disabled. To preserve a
Mainline dump, boot the diagnostic HTC 3.4 image after the failed attempt, run
`dump-pstore.sh`, then restore the Mainline image to `boot`.
`maxcpus=1` isolates secondary-CPU startup. The earlier one-CPU test used the
overlapping ramdisk address, so it did not isolate SMP correctly.

## Source map

- `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dts`: board description
- `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul-diag.dts`: panic-to-recovery variant
- `arch/arm/configs/m7_defconfig`: first-boot kernel configuration
- `tools/m7/build.sh`: reproducible kernel, initramfs and boot image build
- `tools/m7/build-wifi-tools.sh`: pinned static ARM WLAN userspace build
- `tools/m7/wifi_tools.py`: WLAN tool validation and initramfs installation
- `tools/m7/initramfs/init`: read-only maintenance init
- `tools/m7/watch-fastboot.sh`: adb/recovery to fastboot watcher
- `tools/m7/watch-recovery.sh`: panic to TWRP, Pstore dump and fastboot watcher
- `tools/m7/dump-pstore.sh`: read-only Ramoops transfer over adb
- `tools/m7/readmem.c`: exact `_llseek` reader used by the recovery dump
- `tools/m7/parse_pstore.py`: Ramoops decoder with synthetic tests
- `tools/m7/patch_zimage_early_reboot.py`: pre-decompression recovery marker
- `Documentation/devicetree/bindings/arm/qcom.yaml`: board compatible

Hardware facts were cross-checked against the public HTC kernel sources in
[`LineageOS/android_kernel_htc_msm8960`](https://github.com/LineageOS/android_kernel_htc_msm8960),
branch `cm-14.1`, especially `arch/arm/mach-msm/htc/m7/` and
`arch/arm/mach-msm/htc/htc_restart_handler.c`.

## Bootloader references

- [TWRP's official M7 fastboot install method](https://twrp.me/htc/htconem7gsm.html)
- [LineageOS M7 install instructions and bootloader USB warning](https://wiki.lineageos.org/devices/m7/install/)
- [M7 report that `fastboot boot` works only on HBOOT 1.44](https://xdaforums.com/t/solved-please-help-android-bricked-and-no-recovery-boot-either.2791811/)

## License and contributions

Linux kernel code is GPL-2.0-only. Follow
`Documentation/process/coding-assistants.rst`: AI assistance must be disclosed,
and only the human submitter may add a `Signed-off-by` trailer.
