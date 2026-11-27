#!/usr/bin/env python3
"""Tests for optional WLAN tool validation and initramfs installation."""

import json
import pathlib
import tempfile
import unittest

from tools.m7.wifi_tools import (
    TOOL_NAMES,
    WifiToolError,
    install_tools,
    validate_tools,
)


def make_elf(path, machine=40, dynamic=False, mode=0o755):
    data = bytearray(52)
    data[:4] = b"\x7fELF"
    data[4] = 1
    data[5] = 1
    data[16:18] = (2).to_bytes(2, "little")
    data[18:20] = machine.to_bytes(2, "little")
    if dynamic:
        data.extend(bytes(32))
        data[28:32] = (52).to_bytes(4, "little")
        data[42:44] = (32).to_bytes(2, "little")
        data[44:46] = (1).to_bytes(2, "little")
        data[52:56] = (3).to_bytes(4, "little")
    path.write_bytes(data)
    path.chmod(mode)


class WifiToolsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.source = self.root / "tools"
        self.source.mkdir()
        for name in TOOL_NAMES:
            make_elf(self.source / name)

    def test_static_arm_tools_are_accepted(self):
        report = validate_tools(self.source)

        self.assertEqual(set(report["tools"]), set(TOOL_NAMES))
        for metadata in report["tools"].values():
            self.assertEqual(metadata["size"], 52)
            self.assertEqual(len(metadata["sha256"]), 64)

    def test_non_arm_tool_is_rejected(self):
        make_elf(self.source / "iw", machine=62)

        with self.assertRaisesRegex(WifiToolError, "not an ARM binary"):
            validate_tools(self.source)

    def test_dynamic_tool_is_rejected(self):
        make_elf(self.source / "iw", dynamic=True)

        with self.assertRaisesRegex(WifiToolError, "statically linked"):
            validate_tools(self.source)

    def test_non_executable_tool_is_rejected(self):
        (self.source / "iw").chmod(0o644)

        with self.assertRaisesRegex(WifiToolError, "not executable"):
            validate_tools(self.source)

    def test_missing_tool_is_rejected(self):
        (self.source / "iw").unlink()

        with self.assertRaisesRegex(WifiToolError, "missing WLAN tool"):
            validate_tools(self.source)

    def test_install_copies_tools_and_protects_credentials(self):
        initramfs = self.root / "initramfs"
        config = self.root / "outside-repository.conf"
        secret = "do-not-log-this-passphrase"
        config.write_text(f'network={{\n\tssid="test"\n\tpsk="{secret}"\n}}\n')

        report = install_tools(self.source, initramfs, config)
        installed_config = initramfs / "etc/wpa_supplicant.conf"

        self.assertTrue(report["wpa_supplicant_config"])
        self.assertNotIn(secret, json.dumps(report))
        self.assertNotIn(str(config), json.dumps(report))
        self.assertEqual(installed_config.stat().st_mode & 0o777, 0o600)
        for name in TOOL_NAMES:
            installed = initramfs / "sbin" / name
            self.assertEqual(installed.read_bytes(), (self.source / name).read_bytes())
            self.assertEqual(installed.stat().st_mode & 0o777, 0o755)

    def test_install_without_credentials_adds_no_config(self):
        initramfs = self.root / "initramfs"

        report = install_tools(self.source, initramfs)

        self.assertFalse(report["wpa_supplicant_config"])
        self.assertFalse((initramfs / "etc/wpa_supplicant.conf").exists())


if __name__ == "__main__":
    unittest.main()
