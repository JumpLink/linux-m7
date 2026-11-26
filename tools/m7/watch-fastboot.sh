#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)

# Wait for the M7 and move any adb state into fastboot.
# Usage: FASTBOOT_SERIAL=... ./tools/m7/watch-fastboot.sh [timeout-seconds]

serial=${FASTBOOT_SERIAL:?Set FASTBOOT_SERIAL to the M7 Fastboot serial}
timeout_seconds=${1:-300}
if ! [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
	echo "timeout must be a positive integer" >&2
	exit 1
fi

for tool in adb fastboot timeout awk sleep; do
	command -v "$tool" >/dev/null || {
		echo "missing tool: $tool" >&2
		exit 1
	}
done

deadline=$((SECONDS + timeout_seconds))
while (( SECONDS < deadline )); do
	if timeout 2 fastboot devices -l 2>/dev/null \
		| awk -v serial="$serial" '$1 == serial && $2 == "fastboot" { found = 1 } END { exit !found }'; then
		if "$root/tools/m7/require-m7-fastboot.sh" "$serial" >/dev/null 2>&1; then
			echo "M7 is ready in fastboot"
			exit 0
		fi
	fi

	adb_state=$(timeout 2 adb devices -l 2>/dev/null \
		| awk -v serial="$serial" '$1 == serial { print $2; exit }')
	if [ -n "$adb_state" ]; then
		echo "M7 adb state is $adb_state; rebooting to bootloader"
		timeout 10 adb -s "$serial" reboot bootloader >/dev/null 2>&1 || true
	fi

	sleep 0.5
done

echo "timed out waiting for M7 fastboot" >&2
exit 1
