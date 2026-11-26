#!/usr/bin/env bash
set -euo pipefail

# Wait for a diagnostic kernel to reboot into TWRP, preserve Pstore, then
# return the M7 to fastboot. Usage: FASTBOOT_SERIAL=... ./tools/m7/watch-recovery.sh [timeout] [output-dir]

root=$(cd "$(dirname "$0")/../.." && pwd)
serial=${FASTBOOT_SERIAL:-${ADB_SERIAL:?Set FASTBOOT_SERIAL or ADB_SERIAL to the M7 serial}}
timeout_seconds=${1:-180}
output=${2:-"$root/build/m7/pstore/$(date -u +%Y%m%dT%H%M%SZ)"}

if ! [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
	echo "timeout must be a positive integer" >&2
	exit 1
fi
for tool in adb fastboot timeout awk; do
	command -v "$tool" >/dev/null || {
		echo "missing tool: $tool" >&2
		exit 1
	}
done

adb_state() {
	timeout 3 adb -s "$serial" get-state 2>/dev/null || true
}

fastboot_ready() {
	timeout 3 fastboot devices -l 2>/dev/null \
		| awk -v serial="$serial" '$1 == serial && $2 == "fastboot" { found = 1 } END { exit !found }' \
		&& timeout 5 fastboot -s "$serial" getvar product >/dev/null 2>&1
}

deadline=$((SECONDS + timeout_seconds))
ignore_fastboot_until=$((SECONDS + 10))
while (( SECONDS < deadline )); do
	state=$(adb_state)
	if [ "$state" = device ] || [ "$state" = recovery ]; then
		echo "M7 is in TWRP; reading Pstore"
		set +e
		ADB_SERIAL="$serial" "$root/tools/m7/dump-pstore.sh" "$output"
		dump_rc=$?
		set -e
		echo "Rebooting M7 to fastboot"
		timeout 15 adb -s "$serial" reboot bootloader >/dev/null 2>&1 || true

		fastboot_deadline=$((SECONDS + 60))
		while (( SECONDS < fastboot_deadline )); do
			if fastboot_ready; then
				echo "M7 is ready in fastboot"
				exit "$dump_rc"
			fi
			sleep 0.5
		done
		echo "timed out waiting for fastboot after Pstore dump" >&2
		exit 1
	fi

	if (( SECONDS >= ignore_fastboot_until )) && fastboot_ready; then
		echo "M7 reached fastboot before TWRP; no Pstore dump was taken" >&2
		exit 2
	fi
	sleep 0.5
done

echo "timed out waiting for M7 TWRP; a silent bootloop has no USB signal" >&2
exit 1
