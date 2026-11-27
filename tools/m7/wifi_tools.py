#!/usr/bin/env python3
"""Validate and install the optional static ARM WLAN userspace tools."""

import argparse
import hashlib
import json
import pathlib
import shutil
import sys


TOOL_NAMES = ("iw", "wpa_cli", "wpa_supplicant")
PT_INTERP = 3
EM_ARM = 40
ET_EXEC = 2


class WifiToolError(ValueError):
    """A WLAN tool does not meet the diagnostic image requirements."""


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_elf(path):
    if not path.is_file():
        raise WifiToolError(f"missing WLAN tool: {path}")
    if path.stat().st_mode & 0o111 == 0:
        raise WifiToolError(f"WLAN tool is not executable: {path}")

    data = path.read_bytes()
    if len(data) < 52 or data[:4] != b"\x7fELF":
        raise WifiToolError(f"not an ELF binary: {path}")
    if data[4] != 1 or data[5] != 1:
        raise WifiToolError(f"expected a little-endian ELF32 binary: {path}")
    if int.from_bytes(data[16:18], "little") != ET_EXEC:
        raise WifiToolError(f"expected an executable ELF binary: {path}")
    if int.from_bytes(data[18:20], "little") != EM_ARM:
        raise WifiToolError(f"WLAN tool is not an ARM binary: {path}")

    program_offset = int.from_bytes(data[28:32], "little")
    entry_size = int.from_bytes(data[42:44], "little")
    entry_count = int.from_bytes(data[44:46], "little")
    table_end = program_offset + entry_size * entry_count
    if table_end > len(data):
        raise WifiToolError(f"truncated ELF program table: {path}")
    for index in range(entry_count):
        offset = program_offset + index * entry_size
        if int.from_bytes(data[offset : offset + 4], "little") == PT_INTERP:
            raise WifiToolError(f"WLAN tool must be statically linked: {path}")

    return {"size": len(data), "sha256": _sha256(path)}


def validate_tools(source):
    source = pathlib.Path(source)
    return {
        "tools": {name: _validate_elf(source / name) for name in TOOL_NAMES},
    }


def install_tools(source, initramfs, wpa_config=None):
    source = pathlib.Path(source)
    initramfs = pathlib.Path(initramfs)
    report = validate_tools(source)
    destination = initramfs / "sbin"
    destination.mkdir(parents=True, exist_ok=True)

    for name in TOOL_NAMES:
        target = destination / name
        shutil.copy2(source / name, target)
        target.chmod(0o755)

    report["wpa_supplicant_config"] = False
    if wpa_config is not None:
        config = pathlib.Path(wpa_config)
        if not config.is_file() or config.stat().st_size == 0:
            raise WifiToolError(f"missing or empty WPA configuration: {config}")
        etc = initramfs / "etc"
        etc.mkdir(parents=True, exist_ok=True)
        target = etc / "wpa_supplicant.conf"
        shutil.copy2(config, target)
        target.chmod(0o600)
        report["wpa_supplicant_config"] = True

    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a tool directory")
    validate.add_argument("source", type=pathlib.Path)
    install = commands.add_parser("install", help="install tools into an initramfs")
    install.add_argument("source", type=pathlib.Path)
    install.add_argument("initramfs", type=pathlib.Path)
    install.add_argument("wpa_config", nargs="?", type=pathlib.Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            report = validate_tools(args.source)
        else:
            report = install_tools(args.source, args.initramfs, args.wpa_config)
    except (OSError, WifiToolError) as error:
        parser.exit(1, f"wifi-tools: {error}\n")

    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
