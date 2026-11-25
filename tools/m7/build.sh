#!/usr/bin/env bash
set -euo pipefail

# Build a first-boot mainline image for the HTC One M7 (m7ul).
# Usage: BUSYBOX=/path/to/static-arm-busybox ./tools/m7/build.sh [build-dir]

root=$(cd "$(dirname "$0")/../.." && pwd)
build=${1:-"$root/build/m7"}
busybox=${BUSYBOX:?Set BUSYBOX to a statically linked ARMv7 BusyBox binary}
cross=${CROSS_COMPILE:-arm-linux-gnu-}
jobs=${JOBS:-$(nproc)}

tools=(cpio gzip mkbootimg python3 readelf)
if [ "${SKIP_KERNEL_BUILD:-0}" != 1 ]; then
	tools+=(make "$cross"gcc)
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

mkdir -p "$build"
if [ "${SKIP_KERNEL_BUILD:-0}" != 1 ]; then
	make -C "$root" O="$build" ARCH=arm CROSS_COMPILE="$cross" m7_defconfig
	make -C "$root" O="$build" ARCH=arm CROSS_COMPILE="$cross" -j"$jobs" zImage
	make -C "$root" O="$build" ARCH=arm CROSS_COMPILE="$cross" -j"$jobs" dtbs
fi

kernel=$build/arch/arm/boot/zImage
dtb=$build/arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dtb
[ -s "$kernel" ] && [ -s "$dtb" ] && [ -s "$build/vmlinux" ] || {
	echo "missing kernel artifacts in $build" >&2
	exit 1
}
cat "$kernel" "$dtb" > "$build/zImage-dtb"

initramfs=$build/initramfs
rm -rf "$initramfs"
mkdir -p "$initramfs"/{bin,sbin,dev,proc,sys,config,run,tmp,root,usr/bin,etc}
cp "$busybox" "$initramfs/bin/busybox"
for applet in sh mount mkdir ls head sleep ln echo cat uname dmesg hostname poweroff reboot grep tr cut; do
	ln -s busybox "$initramfs/bin/$applet"
done
install -m 0755 "$root/tools/m7/initramfs/init" "$initramfs/init"
printf 'root:x:0:0:root:/root:/bin/sh\n' > "$initramfs/etc/passwd"
printf 'root:x:0:\n' > "$initramfs/etc/group"

(
	cd "$initramfs"
	find . -print0 | cpio --null -o -H newc 2>/dev/null | gzip -1
) > "$build/initramfs.cpio.gz"

mkbootimg \
	--kernel "$build/zImage-dtb" \
	--ramdisk "$build/initramfs.cpio.gz" \
	--base 0x80600000 \
	--kernel_offset 0x00008000 \
	--ramdisk_offset 0x01800000 \
	--second_offset 0x00f00000 \
	--tags_offset 0x00000100 \
	--pagesize 2048 \
	--header_version 0 \
	--board m7 \
	--cmdline 'console=ttyGS0 root=/dev/ram0 rw init=/init loglevel=7 ignore_loglevel' \
	--output "$build/boot.img"

sha256sum "$build/boot.img" "$build/zImage-dtb" "$dtb" "$build/initramfs.cpio.gz" "$build/.config" > "$build/SHA256SUMS"

python3 - "$build" "$root" <<'PY'
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

build = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2])

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
        "dtb_sha256": digest(build / "arch/arm/boot/dts/qcom/qcom-apq8064-htc-m7ul.dtb"),
        "initramfs_sha256": digest(build / "initramfs.cpio.gz"),
        "base": "0x80600000",
        "kernel_offset": "0x00008000",
        "ramdisk_offset": "0x01800000",
        "pagesize": 2048,
        "cmdline": "console=ttyGS0 root=/dev/ram0 rw init=/init loglevel=7 ignore_loglevel",
        "debug_channel": "usb-acm",
    },
}
(build / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY

ls -lh "$build/boot.img" "$build/zImage-dtb" "$dtb" "$build/initramfs.cpio.gz" "$build/build-manifest.json"
