#!/usr/bin/env bash
set -euo pipefail

# Read the M7 Ramoops region from TWRP without writing to eMMC.
# Usage: ADB_SERIAL=... ./tools/m7/dump-pstore.sh [output-dir]

root=$(cd "$(dirname "$0")/../.." && pwd)
serial=${ADB_SERIAL:?Set ADB_SERIAL to the M7 adb serial}
output=${1:-"$root/build/m7/pstore/$(date -u +%Y%m%dT%H%M%SZ)"}
reader=${M7_READMEM:-"$root/build/m7/readmem"}
size_decimal=$((0x100000))

for tool in adb python3 timeout tr; do
	command -v "$tool" >/dev/null || {
		echo "missing tool: $tool" >&2
		exit 1
	}
done

state=$(timeout 10 adb -s "$serial" get-state 2>/dev/null || true)
if [ "$state" != device ] && [ "$state" != recovery ]; then
	echo "M7 adb state is $state" >&2
	exit 1
fi
if [ -z "$(timeout 10 adb -s "$serial" shell getprop ro.twrp.version)" ]; then
	echo "connected adb device is not TWRP" >&2
	exit 1
fi
uid=$(timeout 10 adb -s "$serial" shell id -u | tr -d '\r')
if [ "$uid" != 0 ]; then
	echo "TWRP adb shell is not root" >&2
	exit 1
fi

if [ ! -x "$reader" ]; then
	echo "missing ARM reader: $reader (run tools/m7/build.sh or set M7_READMEM)" >&2
	exit 1
fi

mkdir -p "$output"
output=$(cd "$output" && pwd)
dump=$output/pstore.bin
remote_reader=/tmp/m7-readmem
remote_dump=/tmp/m7-pstore.bin

# TWRP may omit the devmem node even when its kernel supports the driver.
if ! timeout 10 adb -s "$serial" shell 'test -e /dev/mem' >/dev/null 2>&1; then
	timeout 10 adb -s "$serial" shell 'mknod -m 600 /dev/mem c 1 1' >/dev/null
fi
if ! timeout 10 adb -s "$serial" shell 'grep -q "^tmpfs /tmp tmpfs " /proc/mounts'; then
	echo "M7 /tmp is not tmpfs; refusing to write a RAM dump" >&2
	exit 1
fi

# The 3.4 devmem read path panics at the end of the first RAM bank when
# BusyBox dd keeps reading. The freestanding reader seeks once and reads
# exactly the reserved 1 MiB. Keep the intermediate file in tmpfs.
timeout 20 adb -s "$serial" push "$reader" "$remote_reader" >/dev/null
timeout 10 adb -s "$serial" shell chmod 755 "$remote_reader"
set +e
timeout 30 adb -s "$serial" shell \
	"$remote_reader > $remote_dump; echo \$? > /tmp/m7-readmem.rc" >/dev/null
reader_rc=$?
set -e
if [ "$reader_rc" -ne 0 ]; then
	echo "M7 RAM reader transport failed with status $reader_rc" >&2
	exit 1
fi
remote_status=$(timeout 10 adb -s "$serial" shell 'cat /tmp/m7-readmem.rc' | tr -d '\r')
if [ "$remote_status" != 0 ]; then
	echo "M7 RAM reader exited with status $remote_status" >&2
	exit 1
fi
remote_size=$(timeout 10 adb -s "$serial" shell "wc -c < $remote_dump" | tr -d '\r')
if [ "$remote_size" != "$size_decimal" ]; then
	echo "short Ramoops dump: $remote_size of $size_decimal bytes" >&2
	exit 1
fi
timeout 30 adb -s "$serial" pull "$remote_dump" "$dump" >/dev/null
timeout 10 adb -s "$serial" shell "rm -f $remote_reader $remote_dump /tmp/m7-readmem.rc" >/dev/null
if [ "$(stat -c %s "$dump")" -ne "$size_decimal" ]; then
	echo "short host Ramoops dump: $(stat -c %s "$dump") of $size_decimal bytes" >&2
	exit 1
fi

set +e
python3 "$root/tools/m7/parse_pstore.py" "$dump" "$output"
rc=$?
set -e
printf 'Pstore artifacts: %s\n' "$output"
exit "$rc"
