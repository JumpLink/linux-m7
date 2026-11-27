#!/usr/bin/env bash
set -euo pipefail

# Build a first-boot mainline image for the HTC One M7 (m7ul).
# Usage: BUSYBOX=/path/to/static-arm-busybox ./tools/m7/build.sh [build-dir]
# SKIP_KERNEL_BUILD=1 packages existing kernel artifacts; SKIP_READER_BUILD=1
# reuses prebuilt ARM helpers when the cross compiler is unavailable on the host.
# M7_FIRMWARE_DIR optionally supplies an unpacked brcmfmac4335-sdio.bin and NVRAM.

root=$(cd "$(dirname "$0")/../.." && pwd)
build=${1:-"$root/build/m7"}
busybox=${BUSYBOX:?Set BUSYBOX to a statically linked ARMv7 BusyBox binary}
cross=${CROSS_COMPILE:-arm-linux-gnu-}
jobs=${JOBS:-$(nproc)}
firmware=${M7_FIRMWARE_DIR:-}

tools=(cpio gzip mkbootimg python3 readelf)
if [ "${SKIP_READER_BUILD:-0}" != 1 ]; then
	tools+=("$cross"gcc)
fi
if [ "${SKIP_KERNEL_BUILD:-0}" != 1 ]; then
	tools+=(make)
fi
for tool in "${tools[@]}"; do
	command -v "$tool" >/dev/null || {
		echo "missing tool: $tool" >&2
		exit 1
	}
done

if ! readelf -h "$busybox" | grep -q 'Machine:.*ARM'; then
	echo "BUSYBOX is not an ARM binary: $busybox" >&2
	exit 1
fi
if readelf -l "$busybox" | grep -q 'INTERP'; then
	echo "BUSYBOX must be statically linked: $busybox" >&2
	exit 1
fi

cmdline=${M7_CMDLINE:-"console=ttyGS0 root=/dev/ram0 rw init=/init loglevel=7 ignore_loglevel"}
dtb_name=${M7_DTB:-qcom-apq8064-htc-m7ul}
base=0x80600000
kernel_offset=0x00008000
ramdisk_offset=${M7_RAMDISK_OFFSET:-0x04000000}

mkdir -p "$build"
if [ "${SKIP_READER_BUILD:-0}" != 1 ]; then
	"$cross"gcc -marm -nostdlib -static -O2 -Wall -Wextra \
		-fno-builtin -fno-stack-protector -Wl,-e,_start \
		-o "$build/readmem" "$root/tools/m7/readmem.c"
	"$cross"gcc -marm -nostdlib -static -O2 -Wall -Wextra \
		-fno-builtin -fno-stack-protector -Wl,-e,_start \
		-o "$build/reboot-bootloader" "$root/tools/m7/reboot_bootloader.c"
else
	[ -x "$build/readmem" ] || {
		echo "missing prebuilt ARM reader: $build/readmem" >&2
		exit 1
	}
	[ -x "$build/reboot-bootloader" ] || {
		echo "missing prebuilt ARM reboot helper: $build/reboot-bootloader" >&2
		exit 1
	}
fi
if [ "${SKIP_KERNEL_BUILD:-0}" != 1 ]; then
	make -C "$root" O="$build" ARCH=arm CROSS_COMPILE="$cross" m7_defconfig
	if [ -n "${M7_CMDLINE:-}" ]; then
		"$root/scripts/config" --file "$build/.config" --set-str CONFIG_CMDLINE "$cmdline"
		make -C "$root" O="$build" ARCH=arm CROSS_COMPILE="$cross" olddefconfig
	fi
	make -C "$root" O="$build" ARCH=arm CROSS_COMPILE="$cross" -j"$jobs" zImage
	make -C "$root" O="$build" ARCH=arm CROSS_COMPILE="$cross" -j"$jobs" dtbs
fi
kernel=$build/arch/arm/boot/zImage
dtb=$build/arch/arm/boot/dts/qcom/$dtb_name.dtb
[ -s "$kernel" ] && [ -s "$dtb" ] && [ -s "$build/vmlinux" ] || {
	echo "missing kernel artifacts in $build" >&2
	exit 1
}
if grep -q '^CONFIG_AUTO_ZRELADDR=y' "$build/.config"; then
	echo "M7 requires CONFIG_AUTO_ZRELADDR=n; RAM starts at 0x80600000" >&2
	exit 1
fi
if ! grep -q '^CONFIG_PHYS_OFFSET=0x80600000$' "$build/.config"; then
	echo "M7 requires CONFIG_PHYS_OFFSET=0x80600000" >&2
	exit 1
fi
image=$build/arch/arm/boot/Image
[ -s "$image" ] || {
	echo "missing decompressed kernel image in $build" >&2
	exit 1
}
kernel_end=$((base + kernel_offset + $(stat -c %s "$image")))
ramdisk_addr=$((base + ramdisk_offset))
if (( ramdisk_addr < kernel_end + 0x100000 )); then
	echo "ramdisk at $ramdisk_offset overlaps the kernel; raise M7_RAMDISK_OFFSET" >&2
	exit 1
fi
if [ "${M7_EARLY_REBOOT_MODE:-0}" = 1 ]; then
	python3 "$root/tools/m7/patch_zimage_early_reboot.py" "$kernel"
else
	python3 "$root/tools/m7/patch_zimage_early_reboot.py" --forbid-patched "$kernel"
fi
cat "$kernel" "$dtb" > "$build/zImage-dtb"

initramfs=$build/initramfs
rm -rf "$initramfs"
mkdir -p "$initramfs"/{bin,sbin,dev,proc,sys,config,run,tmp,root,usr/bin,etc}
cp "$busybox" "$initramfs/bin/busybox"
for applet in sh mount mkdir ls head sleep ln echo cat uname dmesg hostname poweroff reboot grep tr cut; do
	ln -s busybox "$initramfs/bin/$applet"
done
install -m 0755 "$root/tools/m7/initramfs/init" "$initramfs/init"
install -m 0755 "$build/reboot-bootloader" "$initramfs/bin/reboot-bootloader"
if [ "${M7_DIAGNOSTIC_REBOOT:-0}" = 1 ]; then
	: > "$initramfs/m7-diag-reboot"
fi
if [ "${M7_WATCHDOG_PET:-0}" = 1 ]; then
	: > "$initramfs/m7-wdt-pet"
fi
printf 'root:x:0:0:root:/root:/bin/sh\n' > "$initramfs/etc/passwd"
printf 'root:x:0:\n' > "$initramfs/etc/group"

if [ -n "$firmware" ]; then
	fw="$firmware/brcmfmac4335-sdio.bin"
	[ -f "$fw" ] || { echo "missing firmware: $fw" >&2; exit 1; }
	mkdir -p "$initramfs/lib/firmware/brcm"
	install -m 0644 "$fw" "$initramfs/lib/firmware/brcm/brcmfmac4335-sdio.bin"
	for name in brcmfmac4335-sdio.htc,m7ul.txt brcmfmac4335-sdio.txt; do
		if [ -f "$firmware/$name" ]; then
			install -m 0644 "$firmware/$name" "$initramfs/lib/firmware/brcm/$name"
		fi
	done
fi

(
	cd "$initramfs"
	find . -print0 | cpio --null -o -H newc 2>/dev/null | gzip -1
) > "$build/initramfs.cpio.gz"

mkbootimg \
	--kernel "$build/zImage-dtb" \
	--ramdisk "$build/initramfs.cpio.gz" \
	--base "$base" \
	--kernel_offset "$kernel_offset" \
	--ramdisk_offset "$ramdisk_offset" \
	--second_offset 0x00f00000 \
	--tags_offset 0x00000100 \
	--pagesize 2048 \
	--header_version 0 \
	--board m7 \
	--cmdline "$cmdline" \
	--output "$build/boot.img"

sha256sum "$build/boot.img" "$build/zImage-dtb" "$dtb" "$build/initramfs.cpio.gz" "$build/readmem" "$build/reboot-bootloader" "$build/.config" > "$build/SHA256SUMS"

python3 - "$build" "$root" "$cmdline" "$dtb_name" "$ramdisk_offset" \
	"${M7_EARLY_REBOOT_MODE:-0}" "${M7_DIAGNOSTIC_REBOOT:-0}" \
	"${M7_WATCHDOG_PET:-0}" <<'PY'
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

build = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2])
cmdline = sys.argv[3]
dtb_name = sys.argv[4]
ramdisk_offset = sys.argv[5]
early_reboot_mode = sys.argv[6] == "1"
diagnostic_reboot = sys.argv[7] == "1"
watchdog_pet = sys.argv[8] == "1"

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

commit = subprocess.run(
    ["git", "-C", str(root), "rev-parse", "HEAD"],
    check=True, text=True, capture_output=True,
).stdout.strip()
dirty = bool(subprocess.run(
    ["git", "-C", str(root), "status", "--porcelain"],
    check=True, text=True, capture_output=True,
).stdout.strip())
release = (build / "include/config/kernel.release").read_text().strip()
manifest = {
    "schema": "jumplink.phone-kernel-build/v1",
    "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "device": {
        "manufacturer": "HTC",
        "model": "One M7",
        "codename": "m7ul",
        "soc": "qcom,apq8064",
    },
    "source": {"repository": "JumpLink/linux-m7", "commit": commit, "dirty": dirty},
    "kernel": {
        "release": release,
        "config_sha256": digest(build / ".config"),
        "vmlinux_sha256": digest(build / "vmlinux"),
    },
    "image": {
        "boot_sha256": digest(build / "boot.img"),
        "zimage_dtb_sha256": digest(build / "zImage-dtb"),
        "dtb": dtb_name,
        "dtb_sha256": digest(build / "arch/arm/boot/dts/qcom" / (dtb_name + ".dtb")),
        "initramfs_sha256": digest(build / "initramfs.cpio.gz"),
        "readmem_sha256": digest(build / "readmem"),
        "reboot_bootloader_sha256": digest(build / "reboot-bootloader"),
        "base": "0x80600000",
        "kernel_offset": "0x00008000",
        "ramdisk_offset": ramdisk_offset,
        "pagesize": 2048,
        "cmdline": cmdline,
        "debug_channel": "usb-acm",
        "early_reboot_mode": early_reboot_mode,
        "diagnostic_reboot": diagnostic_reboot,
        "watchdog_pet": watchdog_pet,
    },
}
(build / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY

ls -lh "$build/boot.img" "$build/zImage-dtb" "$dtb" "$build/initramfs.cpio.gz" "$build/readmem" "$build/reboot-bootloader" "$build/build-manifest.json"
