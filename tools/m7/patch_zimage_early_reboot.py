#!/usr/bin/env python3
"""Set HTC's recovery magic before the ARM zImage decompressor starts."""

import argparse
import pathlib
import struct
import sys

NOP = 0xE1A00000
ORIGINAL = struct.pack("<8I", *([NOP] * 8))
PATCHED = struct.pack(
    "<8I",
    0xE30F0F00,  # movw r0, #0xff00
    0xE3420A03,  # movt r0, #0x2a03 -> 0x2a03ff00
    0xE3053502,  # movw r3, #0x5502
    0xE3473766,  # movt r3, #0x7766 -> 0x77665502
    0xE5803000,  # str r3, [r0]
    0xF57FF04F,  # dsb sy
    NOP,
    NOP,
)
LEGACY_PATCHED = struct.pack(
    "<8I",
    0xE30F065C,  # wrong IMEM offset used by the first diagnostic build
    0xE3420A03,
    0xE3053502,
    0xE3473766,
    0xE5803000,
    0xF57FF04F,
    NOP,
    NOP,
)


def patch_zimage(path):
    path = pathlib.Path(path)
    data = path.read_bytes()
    if len(data) < 64:
        raise ValueError("zImage is too short")
    if data[:32] == PATCHED:
        return False
    if data[:32] not in (ORIGINAL, LEGACY_PATCHED):
        raise ValueError("unexpected zImage entry prologue")
    path.write_bytes(PATCHED + data[32:])
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zimage", type=pathlib.Path)
    parser.add_argument("--forbid-patched", action="store_true")
    args = parser.parse_args()
    try:
        if args.forbid_patched:
            if pathlib.Path(args.zimage).read_bytes()[:32] in (PATCHED, LEGACY_PATCHED):
                parser.error("build directory contains an early-recovery zImage; rebuild it")
            return 0
        changed = patch_zimage(args.zimage)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print("early recovery patch applied" if changed else "early recovery patch already present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
