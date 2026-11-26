#!/usr/bin/env python3
"""Capture the M7 USB ACM console and parse its benchmark ready marker."""

import argparse
import json
import os
import pathlib
import select
import termios
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tty")
    parser.add_argument("log")
    parser.add_argument("--duration", type=float, default=30)
    args = parser.parse_args()

    fd = os.open(args.tty, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)

    data = bytearray()
    probe = {}
    ready = False
    started = time.monotonic()
    next_probe = started
    log_path = pathlib.Path(args.log)
    probe_command = (
        b"echo M7_HOST_PROBE_BEGIN;"
        b"echo M7_KERNEL=$(uname -r);"
        b"echo M7_CMDLINE=$(cat /proc/cmdline);"
        b"echo M7_DT_MODEL=$(cat /proc/device-tree/model);"
        b"echo M7_DT_COMPATIBLE=$(tr '\\0' ' ' < /proc/device-tree/compatible);"
        b"echo M7_UPTIME=$(cut -d' ' -f1 /proc/uptime);"
        b"echo M7_UDC=$(ls /sys/class/udc | head -n1);"
        b"echo M7_UDC_STATE=$(cat /sys/class/udc/*/state 2>/dev/null);"
        b"grep -q mmcblk0 /proc/partitions && echo M7_EMMC_PRESENT=yes || echo M7_EMMC_PRESENT=no;"
        b"echo M7_HOST_PROBE_END\\n"
    )

    with log_path.open("wb", buffering=0) as log:
        while time.monotonic() - started < args.duration:
            now = time.monotonic()
            if not ready and now >= next_probe:
                try:
                    os.write(fd, probe_command)
                except BlockingIOError:
                    pass
                next_probe = now + 2

            readable, _, _ = select.select([fd], [], [], 0.2)
            if not readable:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data.extend(chunk)
            log.write(chunk)

            for begin, end in (
                (b"M7_READY_BEGIN", b"M7_READY_END"),
                (b"M7_HOST_PROBE_BEGIN", b"M7_HOST_PROBE_END"),
            ):
                if begin in data and end in data:
                    block = data.split(begin, 1)[1].split(end, 1)[0]
                    for line in block.decode("utf-8", "replace").splitlines():
                        if "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip()
                            if key.startswith("M7_"):
                                probe[key] = value.strip()
                    ready = True
                    break

    os.close(fd)
    result = {
        "ready": ready,
        "probe": probe,
        "bytes": len(data),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    pathlib.Path(args.log + ".json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
