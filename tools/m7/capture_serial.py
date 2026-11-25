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
    log_path = pathlib.Path(args.log)

    with log_path.open("wb", buffering=0) as log:
        while time.monotonic() - started < args.duration:
            readable, _, _ = select.select([fd], [], [], 0.2)
            if not readable:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data.extend(chunk)
            log.write(chunk)

            if not ready and b"M7_READY_BEGIN" in data and b"M7_READY_END" in data:
                block = data.split(b"M7_READY_BEGIN", 1)[1].split(b"M7_READY_END", 1)[0]
                for line in block.decode("utf-8", "replace").splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        probe[key.strip()] = value.strip()
                ready = True

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
