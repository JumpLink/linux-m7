#!/usr/bin/env python3
"""Capture the M7 USB ACM console and parse its benchmark ready marker."""

import argparse
import json
import os
import pathlib
import select
import signal
import sys
import termios
import time


class _CloseTimeout(Exception):
    pass


# BusyBox ash truncates a serial input line at roughly 1 KiB on the M7. Keep
# every probe command independently executable instead of building one long
# shell line that the console silently cuts in half.
HOST_PROBE_COMMANDS = (
    b"echo M7_HOST_PROBE_BEGIN",
    b"echo M7_KERNEL=$(uname -r)",
    b"echo M7_CMDLINE=$(cat /proc/cmdline)",
    b"echo M7_DT_MODEL=$(cat /proc/device-tree/model)",
    b"echo M7_DT_COMPATIBLE=$(tr '\\0' ' ' < /proc/device-tree/compatible)",
    b"echo M7_UPTIME=$(cut -d' ' -f1 /proc/uptime)",
    b"echo M7_UDC=$(ls /sys/class/udc | head -n1)",
    b"echo M7_UDC_STATE=$(cat /sys/class/udc/*/state 2>/dev/null)",
    b"grep -q mmcblk /proc/partitions && echo M7_EMMC_PRESENT=yes || echo M7_EMMC_PRESENT=no",
    b"ls /sys/bus/i2c/devices/*-0020 >/dev/null 2>&1 && echo M7_TOUCH_PRESENT=yes || echo M7_TOUCH_PRESENT=no",
    b"echo M7_TOUCH_DRIVER=$(cat /sys/bus/i2c/devices/*-0020/uevent 2>/dev/null | grep '^DRIVER=' | cut -d= -f2)",
    b"echo M7_INPUT_DEVICES=$(ls /sys/class/input 2>/dev/null | tr '\\n' ' ')",
    b"echo M7_INPUT_NAMES=$(grep '^N: Name=' /proc/bus/input/devices 2>/dev/null | tr '\\n' ' ')",
    b"test -d /sys/class/net/wlan0 && echo M7_WLAN_PRESENT=yes || echo M7_WLAN_PRESENT=no",
    b"echo M7_WLAN_STATE=$(cat /sys/class/net/wlan0/operstate 2>/dev/null)",
    b"test -d /sys/bus/amba/devices/12180000.mmc && echo M7_SDCC3_PRESENT=yes || echo M7_SDCC3_PRESENT=no",
    b"echo M7_SDCC3_DRIVER=$(cat /sys/bus/amba/devices/12180000.mmc/uevent 2>/dev/null | grep '^DRIVER=' | cut -d= -f2)",
    b"echo M7_MMC_HOSTS=$(ls /sys/class/mmc_host 2>/dev/null | tr '\\n' ' ')",
    b"mount -t debugfs none /sys/kernel/debug 2>/dev/null",
    b"echo M7_DEFERRED=$(grep -E '12180000|wlan|mmc' /sys/kernel/debug/devices_deferred 2>/dev/null | tr '\\n' ' ')",
    b"echo M7_HOST_PROBE_END",
)
DMESG_COMMAND = b"echo M7_DMESG_BEGIN; dmesg; echo M7_DMESG_END\n"


def close_tty(fd, timeout):
    """Close a CDC ACM descriptor without waiting indefinitely for USB drain."""
    if timeout <= 0:
        raise ValueError("close timeout must be positive")

    def interrupt_close(signum, frame):
        raise _CloseTimeout

    previous_handler = signal.signal(signal.SIGALRM, interrupt_close)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        os.close(fd)
    except _CloseTimeout:
        return False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            remaining = max(0, previous_timer[0] - (time.monotonic() - started))
            signal.setitimer(signal.ITIMER_REAL, remaining, previous_timer[1])
    return True


def output_line(line):
    """Strip BusyBox prompts that share a line with command output."""
    line = line.strip()
    while line.startswith(b"/ #"):
        line = line[3:].lstrip()
    return line


def complete_block(data, begin, end):
    """Return the last block delimited by output lines, ignoring shell prompts."""
    lines = [output_line(line) for line in data.splitlines()]
    block = None
    for index, line in enumerate(lines):
        if line != begin:
            continue
        for end_index in range(index + 1, len(lines)):
            if lines[end_index] == end:
                block = b"\n".join(lines[index + 1 : end_index])
                break
    return block


def has_complete_dmesg(data):
    """Return whether one complete delimited kernel-log block was captured."""
    return complete_block(data, b"M7_DMESG_BEGIN", b"M7_DMESG_END") is not None


def shell_ready(data):
    """Return whether init finished or the interactive shell published a prompt."""
    if complete_block(data, b"M7_READY_BEGIN", b"M7_READY_END") is not None:
        return True
    return b"/ #" in data[-512:]


def parse_probe(data):
    """Prefer the live host probe over the earlier initramfs snapshot."""
    probe = {}
    ready = False
    source = None
    for name, begin, end in (
        ("host", b"M7_HOST_PROBE_BEGIN", b"M7_HOST_PROBE_END"),
        ("initramfs", b"M7_READY_BEGIN", b"M7_READY_END"),
    ):
        block = complete_block(data, begin, end)
        if block is None:
            continue
        for line in block.decode("utf-8", "replace").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key.startswith("M7_"):
                probe[key] = value.strip()
        ready = True
        source = name
        break
    return ready, probe, source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tty")
    parser.add_argument("log")
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument(
        "--require-wlan",
        action="store_true",
        help="fail unless the live probe reports wlan0",
    )
    parser.add_argument(
        "--close-timeout",
        type=float,
        default=1.0,
        help="maximum seconds to wait for the final ACM close",
    )
    args = parser.parse_args()

    fd = os.open(args.tty, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    desired = attrs.copy()
    desired[6] = attrs[6].copy()
    desired[0] = 0
    desired[1] = 0
    desired[2] = (
        attrs[2] & ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
    ) | termios.CS8 | termios.CREAD | termios.CLOCAL
    desired[3] = attrs[3] & ~(termios.ECHO | termios.ICANON | termios.IEXTEN)
    desired[4] = termios.B115200
    desired[5] = termios.B115200
    desired[6][termios.VMIN] = 0
    desired[6][termios.VTIME] = 0
    if attrs != desired:
        termios.tcsetattr(fd, termios.TCSANOW, desired)

    data = bytearray()
    probe = {}
    ready = False
    probe_source = None
    started = time.monotonic()
    next_probe = None
    dmesg_requested = False
    log_path = pathlib.Path(args.log)
    probe_command = b"\n".join(HOST_PROBE_COMMANDS) + b"\n"

    with log_path.open("wb", buffering=0) as log:
        # A previous monitor may have left cat /proc/kmsg in the foreground.
        # ISIG stays enabled so Ctrl-C interrupts that reader. The newline makes
        # an idle shell redraw its prompt, which gates the host probe.
        try:
            os.write(fd, b"\x03\n")
        except OSError:
            pass

        while time.monotonic() - started < args.duration:
            now = time.monotonic()
            if next_probe is None and shell_ready(data):
                next_probe = now + 0.1
            if (
                next_probe is not None
                and not (ready and probe_source == "host")
                and now >= next_probe
            ):
                try:
                    os.write(fd, probe_command)
                except OSError:
                    pass
                next_probe = now + 2

            readable, _, _ = select.select([fd], [], [], 0.2)
            if not readable:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            data.extend(chunk)
            log.write(chunk)

            ready, probe, probe_source = parse_probe(data)
            if (
                probe_source == "host"
                and not dmesg_requested
                and b"/ #" in data[-64:]
            ):
                try:
                    os.write(fd, DMESG_COMMAND)
                except OSError:
                    pass
                dmesg_requested = True

    try:
        termios.tcflush(fd, termios.TCOFLUSH)
    except OSError:
        pass
    closed = close_tty(fd, args.close_timeout)
    if not closed:
        print(
            "warning: ACM close timed out; releasing the descriptor on exit",
            file=sys.stderr,
        )
    wlan_ready = probe.get("M7_WLAN_PRESENT") == "yes"
    dmesg_captured = has_complete_dmesg(data)
    result = {
        "ready": ready,
        "probe_source": probe_source,
        "wlan_ready": wlan_ready,
        "probe": probe,
        "bytes": len(data),
        "dmesg_captured": dmesg_captured,
        "tty_closed": closed,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    pathlib.Path(args.log + ".json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if args.require_wlan and not (
        ready and probe_source == "host" and wlan_ready
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
