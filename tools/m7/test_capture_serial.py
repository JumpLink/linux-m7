#!/usr/bin/env python3
"""Tests for the M7 serial probe parser."""

import time
import unittest
from unittest import mock

from tools.m7.capture_serial import close_tty, has_complete_dmesg, parse_probe


class CloseTtyTest(unittest.TestCase):
    def test_blocking_close_is_bounded(self):
        def blocking_close(fd):
            self.assertEqual(fd, 42)
            time.sleep(2)

        with mock.patch("tools.m7.capture_serial.os.close", side_effect=blocking_close):
            started = time.monotonic()
            closed = close_tty(42, 0.05)
            elapsed = time.monotonic() - started

        self.assertFalse(closed)
        self.assertLess(elapsed, 0.5)

    def test_immediate_close_succeeds(self):
        with mock.patch("tools.m7.capture_serial.os.close") as close:
            self.assertTrue(close_tty(42, 0.05))

        close.assert_called_once_with(42)


class DmesgCaptureTest(unittest.TestCase):
    def test_complete_block_is_accepted(self):
        data = b"M7_DMESG_BEGIN\nkernel log\nM7_DMESG_END\n"

        self.assertTrue(has_complete_dmesg(data))

    def test_missing_end_is_rejected(self):
        data = b"M7_DMESG_BEGIN\nkernel log\n"

        self.assertFalse(has_complete_dmesg(data))

    def test_end_before_begin_is_rejected(self):
        data = b"M7_DMESG_END\nkernel log\nM7_DMESG_BEGIN\n"

        self.assertFalse(has_complete_dmesg(data))

    def test_echoed_command_is_not_a_dmesg_block(self):
        data = b"echo M7_DMESG_BEGIN; dmesg; echo M7_DMESG_END\n"

        self.assertFalse(has_complete_dmesg(data))


class ParseProbeTest(unittest.TestCase):
    def test_missing_probe_is_not_ready(self):
        ready, probe, source = parse_probe(b"")

        self.assertFalse(ready)
        self.assertEqual(probe, {})
        self.assertIsNone(source)

    def test_initramfs_snapshot_without_wlan_is_red_capable(self):
        data = (
            b"M7_READY_BEGIN\n"
            b"M7_KERNEL=7.1.0-m7\n"
            b"M7_WLAN_PRESENT=no\n"
            b"M7_READY_END\n"
        )

        ready, probe, source = parse_probe(data)

        self.assertTrue(ready)
        self.assertEqual(source, "initramfs")
        self.assertEqual(probe["M7_WLAN_PRESENT"], "no")

    def test_live_probe_overrides_earlier_snapshot(self):
        data = (
            b"M7_READY_BEGIN\nM7_WLAN_PRESENT=no\nM7_READY_END\n"
            b"M7_HOST_PROBE_BEGIN\nM7_WLAN_PRESENT=yes\nM7_HOST_PROBE_END\n"
        )

        ready, probe, source = parse_probe(data)

        self.assertTrue(ready)
        self.assertEqual(source, "host")
        self.assertEqual(probe["M7_WLAN_PRESENT"], "yes")

    def test_incomplete_live_probe_falls_back_to_snapshot(self):
        data = (
            b"M7_HOST_PROBE_BEGIN\nM7_WLAN_PRESENT=yes\n"
            b"M7_READY_BEGIN\nM7_WLAN_PRESENT=no\nM7_READY_END\n"
        )

        ready, probe, source = parse_probe(data)

        self.assertTrue(ready)
        self.assertEqual(source, "initramfs")
        self.assertEqual(probe["M7_WLAN_PRESENT"], "no")

    def test_echoed_probe_command_is_not_a_live_probe(self):
        data = (
            b"echo M7_HOST_PROBE_BEGIN;echo M7_KERNEL=$(uname -r);"
            b"echo M7_WLAN_PRESENT=no;echo M7_HOST_PROBE_END\n"
        )

        ready, probe, source = parse_probe(data)

        self.assertFalse(ready)
        self.assertEqual(probe, {})
        self.assertIsNone(source)

    def test_echoed_command_does_not_hide_initramfs_snapshot(self):
        data = (
            b"echo M7_HOST_PROBE_BEGIN;echo M7_WLAN_PRESENT=no;"
            b"echo M7_HOST_PROBE_END\n"
            b"M7_READY_BEGIN\nM7_WLAN_PRESENT=no\nM7_READY_END\n"
        )

        ready, probe, source = parse_probe(data)

        self.assertTrue(ready)
        self.assertEqual(source, "initramfs")
        self.assertEqual(probe["M7_WLAN_PRESENT"], "no")


if __name__ == "__main__":
    unittest.main()
