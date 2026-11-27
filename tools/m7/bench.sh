#!/usr/bin/env bash
set -euo pipefail

# One-shot mainline boot test with a benchmark-friendly run manifest.
# Usage: FASTBOOT_SERIAL=... ./tools/m7/bench.sh [boot.img] [run-dir]
# Set M7_BOOT_METHOD=flash to write the boot partition and reboot. The flash
# path accepts only the boot partition, never recovery or userdata.

root=$(cd "$(dirname "$0")/../.." && pwd)
image=${1:-"$root/build/m7/boot.img"}
run=${2:-"$root/build/m7/runs/$(date -u +%Y%m%dT%H%M%SZ)"}
duration=${DURATION:-30}
tty_timeout=${M7_TTY_TIMEOUT:-30}
serial=${FASTBOOT_SERIAL:-}
method=${M7_BOOT_METHOD:-boot}
partition=
require_wlan=${M7_REQUIRE_WLAN:-0}
wlan_diagnostics=${M7_WLAN_DIAGNOSTICS:-0}

if ! [[ "$tty_timeout" =~ ^[1-9][0-9]*$ ]]; then
	echo "M7_TTY_TIMEOUT must be a positive integer" >&2
	exit 1
fi

if [[ "$require_wlan" != 0 && "$require_wlan" != 1 ]]; then
	echo "M7_REQUIRE_WLAN must be 0 or 1" >&2
	exit 1
fi

if [[ "$wlan_diagnostics" != 0 && "$wlan_diagnostics" != 1 ]]; then
	echo "M7_WLAN_DIAGNOSTICS must be 0 or 1" >&2
	exit 1
fi

case "$method" in
	boot)
		;;
	flash)
		partition=${M7_PARTITION:-boot}
		if [ "$partition" != boot ]; then
			echo "M7_PARTITION must be boot" >&2
			exit 1
		fi
		;;
	*)
		echo "M7_BOOT_METHOD must be boot or flash" >&2
		exit 1
		;;
esac

for tool in fastboot python3 sha256sum lsusb timeout; do
	command -v "$tool" >/dev/null || {
		echo "missing tool: $tool" >&2
		exit 1
	}
done
[ -f "$image" ] || { echo "missing boot image: $image" >&2; exit 1; }

if [ -z "$serial" ]; then
	mapfile -t serials < <(fastboot devices -l | awk '$2 == "fastboot" {print $1}')
	if [ "${#serials[@]}" -ne 1 ]; then
		echo "set FASTBOOT_SERIAL; found ${#serials[@]} fastboot devices" >&2
		exit 1
	fi
	serial=${serials[0]}
fi

"$root/tools/m7/require-m7-fastboot.sh" "$serial"
mkdir -p "$run"
run=$(cd "$run" && pwd)

started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
start_epoch=$(date +%s)
dump_fastboot() {
	local var value
	for var in product platform version-bootloader version-baseband version-misc security battery-status battery-voltage; do
		value=$(timeout 3 fastboot -s "$serial" getvar "$var" 2>&1 | sed -n "s/^$var: //p" | tail -n 1)
		printf '%s=%s\n' "$var" "$value"
	done
}

dump_fastboot > "$run/fastboot-before.txt" || true
lsusb > "$run/lsusb-before.txt"
sha256sum "$image" > "$run/image.sha256"

set +e
reboot_rc=
if [ "$method" = boot ]; then
	fastboot_log=fastboot-boot.txt
	timeout 60 fastboot -s "$serial" boot "$image" > "$run/$fastboot_log" 2>&1
	fastboot_rc=$?
else
	fastboot_log=fastboot-flash.txt
	timeout 60 fastboot -s "$serial" flash "$partition" "$image" > "$run/$fastboot_log" 2>&1
	fastboot_rc=$?
	if [ "$fastboot_rc" -eq 0 ]; then
		timeout 30 fastboot -s "$serial" reboot > "$run/fastboot-reboot.txt" 2>&1
		reboot_rc=$?
	fi
fi
set -e

tty=
for _ in $(seq 1 $((tty_timeout * 10))); do
	if compgen -G '/dev/ttyACM*' >/dev/null; then
		tty=$(ls -t /dev/ttyACM* | head -n 1)
		break
	fi
	sleep 0.1
done

ready=false
wlan_ready=false
capture_rc=1
if [ -n "$tty" ]; then
	capture_args=(--duration "$duration")
	if [ "$require_wlan" = 1 ]; then
		capture_args+=(--require-wlan)
	fi
	if [ "$wlan_diagnostics" = 1 ]; then
		capture_args+=(--wlan-diagnostics)
	fi
	set +e
	timeout "$(( ${duration%.*} + 10 ))s" \
		python3 "$root/tools/m7/capture_serial.py" "$tty" "$run/serial.log" \
		"${capture_args[@]}" > "$run/serial-summary.json"
	capture_rc=$?
	set -e
	if [ -f "$run/serial.log.json" ] && \
		python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["ready"])' \
		"$run/serial.log.json"; then
		ready=true
	fi
	if [ -f "$run/serial.log.json" ] && \
		python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["wlan_ready"])' \
		"$run/serial.log.json"; then
		wlan_ready=true
	fi
else
	echo '{"ready":false,"wlan_ready":false,"probe":{},"bytes":0,"elapsed_seconds":0}' \
		> "$run/serial-summary.json"
fi

ended=$(date -u +%Y-%m-%dT%H:%M:%SZ)
elapsed=$(( $(date +%s) - start_epoch ))
lsusb > "$run/lsusb-after.txt"
dump_fastboot > "$run/fastboot-after.txt" || true

python3 - "$run" "$root" "$image" "$started" "$ended" "$elapsed" \
	"$fastboot_rc" "$tty" "$ready" "$method" "$partition" "$fastboot_log" "$reboot_rc" \
	"$capture_rc" "$wlan_ready" "$require_wlan" "$wlan_diagnostics" <<'PY'
import json
import pathlib
import subprocess
import sys

(
    run, root, image, started, ended, elapsed, fastboot_rc, tty, ready,
    method, partition, fastboot_log, reboot_rc, capture_rc, wlan_ready,
    require_wlan, wlan_diagnostics,
) = sys.argv[1:]
run = pathlib.Path(run)
root = pathlib.Path(root)
summary_path = run / "serial.log.json"
summary = (
    json.loads(summary_path.read_text())
    if summary_path.exists()
    else {"probe": {}}
)
diagnostics = summary["probe"].pop("M7_WLAN_DIAGNOSTICS", None)
diagnostics_log = None
if diagnostics is not None:
    diagnostics_log = "wlan-diagnostics.txt"
    (run / diagnostics_log).write_text(diagnostics + "\n")
commit = subprocess.run(
    ["git", "-C", str(root), "rev-parse", "HEAD"],
    text=True, capture_output=True, check=True,
).stdout.strip()
dirty = bool(subprocess.run(
    ["git", "-C", str(root), "status", "--porcelain"],
    text=True, capture_output=True, check=True,
).stdout.strip())
build_manifest = run / "build-manifest.json"
if not build_manifest.exists():
    candidate = pathlib.Path(image).parent / "build-manifest.json"
    if candidate.exists():
        build_manifest.write_bytes(candidate.read_bytes())

manifest = {
    "schema": "jumplink.phone-kernel-run/v1",
    "device": {"manufacturer": "HTC", "model": "One M7", "codename": "m7ul"},
    "started_utc": started,
    "ended_utc": ended,
    "elapsed_seconds": int(elapsed),
    "source": {"repository": "JumpLink/linux-m7", "commit": commit, "dirty": dirty},
    "boot": {
        "method": "fastboot flash" if method == "flash" else "fastboot boot",
        "partition": partition or None,
        "image": pathlib.Path(image).name,
        "fastboot_returncode": int(fastboot_rc),
        "reboot_returncode": int(reboot_rc) if reboot_rc else None,
        "serial_console": tty or None,
        "ready": ready == "true",
        "capture_returncode": int(capture_rc),
        "wlan_ready": wlan_ready == "true",
        "require_wlan": require_wlan == "1",
        "wlan_diagnostics": wlan_diagnostics == "1",
        "probe": summary["probe"],
    },
    "artifacts": {
        "serial_log": "serial.log" if tty else None,
        "fastboot_log": fastboot_log,
        "fastboot_reboot_log": "fastboot-reboot.txt" if method == "flash" else None,
        "usb_before": "lsusb-before.txt",
        "usb_after": "lsusb-after.txt",
        "wlan_diagnostics": diagnostics_log,
    },
}
(run / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY

cat "$run/run-manifest.json"
[ "$ready" = true ] && { [ "$require_wlan" != 1 ] || [ "$wlan_ready" = true ]; }
