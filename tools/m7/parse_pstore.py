#!/usr/bin/env python3
"""Decode the fixed Ramoops layout used by the HTC One M7 device tree."""

import argparse
import hashlib
import json
import pathlib
import re
import sys
import zlib

PERSISTENT_RAM_SIG = 0x43474244
PSTORE_TYPE_PMSG = 7
VERSION_CODE = (7 << 16) | (1 << 8)
REGION_SIZE = 0x100000
RECORD_SIZE = 0x20000
CONSOLE_SIZE = 0x20000
PMSG_SIZE = 0x10000
FTRACE_SIZE = 0x20000
DUMP_COUNT = 5

# Ramoops places dump records first, then console, pmsg and ftrace zones.
ZONES = [
    *[(f"dmesg-{index}", index * RECORD_SIZE, RECORD_SIZE, PERSISTENT_RAM_SIG)
      for index in range(DUMP_COUNT)],
    ("console", DUMP_COUNT * RECORD_SIZE, CONSOLE_SIZE, PERSISTENT_RAM_SIG),
    ("pmsg", DUMP_COUNT * RECORD_SIZE + CONSOLE_SIZE, PMSG_SIZE,
     PERSISTENT_RAM_SIG ^ PSTORE_TYPE_PMSG),
    ("ftrace", DUMP_COUNT * RECORD_SIZE + CONSOLE_SIZE + PMSG_SIZE, FTRACE_SIZE,
     PERSISTENT_RAM_SIG ^ VERSION_CODE),
]


def circular_bytes(zone, start, size):
    capacity = len(zone) - 12
    begin = (start - size) % capacity
    first = min(size, capacity - begin)
    return bytes(zone[12 + begin:12 + begin + first]) + bytes(zone[12:12 + size - first])


def decode_dmesg(payload):
    if payload.startswith(b"===="):
        newline = payload.find(b"\n")
        if newline >= 0 and payload[5:newline].endswith(b"-C"):
            compressed = payload[newline + 1:]
            try:
                return zlib.decompress(compressed, wbits=-15), "zlib"
            except zlib.error:
                return payload, "invalid-zlib"
        if newline >= 0:
            return payload[newline + 1:], "plain"
    return payload, "missing-header"


def find_console_record(dump):
    """Find a console ring whose header moved with the Ramoops layout."""
    capacity = CONSOLE_SIZE - 12
    signature = PERSISTENT_RAM_SIG.to_bytes(4, "little")
    search_from = 0
    while True:
        offset = dump.find(signature, search_from)
        if offset < 0:
            return None
        search_from = offset + 4
        if offset + CONSOLE_SIZE > len(dump):
            continue
        start = int.from_bytes(dump[offset + 4:offset + 8], "little")
        size = int.from_bytes(dump[offset + 8:offset + 12], "little")
        if size == 0 or size > capacity or start >= capacity:
            continue
        payload = circular_bytes(dump[offset:offset + CONSOLE_SIZE], start, size)
        if payload.startswith((b"[", b"<")) and b"Linux version" in payload[:8192]:
            return offset, start, size, payload


def parse_dump(dump, output):
    output.mkdir(parents=True, exist_ok=True)
    zones = []
    decoded_zones = {}
    for name, offset, zone_size, expected_signature in ZONES:
        if offset + zone_size > len(dump):
            continue
        zone = dump[offset:offset + zone_size]
        signature, start, size = struct_unpack(zone[:12])
        if signature != expected_signature:
            continue
        capacity = zone_size - 12
        if size > capacity or start >= capacity:
            continue
        payload = circular_bytes(zone, start, size)
        (output / f"{name}.bin").write_bytes(payload)

        decoded = payload
        decoder = "raw"
        if name.startswith("dmesg-"):
            decoded, decoder = decode_dmesg(payload)
        (output / f"{name}.txt").write_bytes(decoded)
        decoded_zones[name] = decoded
        zones.append({
            "name": name,
            "offset": f"0x{offset:x}",
            "signature": f"0x{signature:08x}",
            "start": start,
            "size": size,
            "decoder": decoder,
        })

    if "console" not in decoded_zones:
        console = find_console_record(dump)
        if console:
            offset, start, size, decoded = console
            (output / "console.txt").write_bytes(decoded)
            decoded_zones["console"] = decoded
            zones.append({
                "name": "console",
                "offset": f"0x{offset:x}",
                "signature": f"0x{PERSISTENT_RAM_SIG:08x}",
                "start": start,
                "size": size,
                "decoder": "plain",
            })

    strings = []
    for match in re.finditer(rb"[\x20-\x7e]{4,}", dump):
        strings.append(f"0x{match.start():08x} {match.group().decode('ascii')}")
    (output / "strings.txt").write_text("\n".join(strings) + ("\n" if strings else ""))

    banners = []
    names = ["console", *sorted(decoded_zones)]
    for name in names:
        if name not in decoded_zones:
            continue
        for line in decoded_zones[name].splitlines():
            if b"Linux version " in line:
                banner = line.decode("utf-8", errors="replace")
                if banner not in banners:
                    banners.append(banner)
                break

    summary = {
        "dump_sha256": hashlib.sha256(dump).hexdigest(),
        "dump_size": len(dump),
        "nonzero_bytes": sum(byte != 0 for byte in dump),
        "valid_zones": len(zones),
        "zones": zones,
    }
    if banners:
        summary["kernel_banner"] = banners[0]
        summary["kernel_banners"] = banners
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def struct_unpack(data):
    return (
        int.from_bytes(data[0:4], "little"),
        int.from_bytes(data[4:8], "little"),
        int.from_bytes(data[8:12], "little"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    dump = args.dump.read_bytes()
    if len(dump) != REGION_SIZE:
        parser.error(f"expected a {REGION_SIZE}-byte Ramoops dump, got {len(dump)}")
    summary = parse_dump(dump, args.output)
    print(json.dumps(summary, indent=2))
    return 0 if summary["valid_zones"] else 1


if __name__ == "__main__":
    sys.exit(main())
