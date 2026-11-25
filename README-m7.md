# linux-m7

Mainline Linux bring-up for the **HTC One M7 (m7ul)**, based on the APQ8064
mainline tree maintained at
[`LogicalErzor/linux`](https://codeberg.org/LogicalErzor/linux), branch
`apq8064`.

## Status

**2026-11-25: kernel and device tree build. The first `fastboot boot` uploaded
the image, then the locked bootloader rejected it with `not allowed`.**

The imported basis is Linux 7.1.0 at upstream commit
`15fbd13fe2475cf77fca0006b618bb5c929025bd`. The first device tree enables:

- APQ8064 / Krait 300 and 2 GiB of RAM
- PM8921 + PM8821 and the M7 regulator voltages
- eMMC on SDCC1
- USB peripheral on HSUSB1, for a CDC ACM maintenance console
- volume keys and reboot-mode handling

Display, touchscreen, audio, wireless, modem and cameras are not enabled yet.
The camera has no mainline APQ8064 driver and is a separate long-term project.

## Build

Requirements: an ARM cross-compiler, `make`, `cpio`, `gzip`, `readelf`, AOSP
`mkbootimg`, and a **statically linked ARMv7 BusyBox**. On Fedora the kernel
cross-compiler package is `gcc-arm-linux-gnu` (prefix `arm-linux-gnu-`).

```sh
BUSYBOX=/path/to/busybox-armhf ./tools/m7/build.sh
```

Artifacts are written to `build/m7/`:

| File | Purpose |
|---|---|
| `boot.img` | Android boot image for `fastboot boot` |
| `zImage-dtb` | Mainline zImage with the M7 DTB appended |
| `initramfs.cpio.gz` | Minimal rootfs with a USB ACM shell |
| `SHA256SUMS` | Checksums for the generated images |

The M7 bootloader parameters come from the published LineageOS device tree:
kernel base `0x80600000`, ramdisk offset `0x01800000`, 2048-byte pages.
The kernel command line is forced in `m7_defconfig` so HTC's `console=none`
cannot hide the maintenance console.

## Hardware test

The test unit is currently **S-ON with a locked bootloader**. HTCdev still
lists the M7, but unlocking erases all user data. Back up first and accept the
unlock explicitly. No S-OFF exploit or third-party unlock service is part of
this project.

After an official HTCdev unlock, test without writing any partition:

```sh
fastboot boot build/m7/boot.img
```

The host should expose `/dev/ttyACM0`. Open it at 115200 baud with `screen`,
`picocom`, or another serial terminal. The initramfs emits a machine-readable
ready block, replays `dmesg` and opens a root shell. It does not mount or modify
eMMC.

For a recorded one-shot run:

```sh
FASTBOOT_SERIAL=... DURATION=30 ./tools/m7/bench.sh build/m7/boot.img
```

The run directory contains `run-manifest.json`, raw serial/fastboot/USB logs
and the ready probe. The build directory also contains `build-manifest.json`.
Both schemas are shared with the
[phone workbench](https://github.com/JumpLink/werkstatt/blob/main/docs/projects/phone-workbench.md)
so kernel results can move into the smartphone benchmark without scraping a
terminal. Serial numbers, IMEIs and unlock tokens are excluded.

Only after repeated successful `fastboot boot` tests should flashing `boot` be
considered. Keep a known-good stock recovery path available.

## Source map

- `arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dts`: board description
- `arch/arm/configs/m7_defconfig`: first-boot kernel configuration
- `tools/m7/build.sh`: reproducible kernel, initramfs and boot image build
- `tools/m7/initramfs/init`: read-only maintenance init
- `Documentation/devicetree/bindings/arm/qcom.yaml`: board compatible

Hardware facts were cross-checked against the public HTC kernel sources in
[`LineageOS/android_kernel_htc_msm8960`](https://github.com/LineageOS/android_kernel_htc_msm8960),
branch `cm-14.1`, especially `arch/arm/mach-msm/htc/m7/`.

## License and contributions

Linux kernel code is GPL-2.0-only. Follow
`Documentation/process/coding-assistants.rst`: AI assistance must be disclosed,
and only the human submitter may add a `Signed-off-by` trailer.
