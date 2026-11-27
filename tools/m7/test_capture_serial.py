#!/usr/bin/env python3
"""Tests for the M7 serial probe parser."""

import time
import unittest
from unittest import mock

from tools.m7.capture_serial import (
    DMESG_COMMAND,
    HOST_PROBE_COMMANDS,
    close_tty,
    has_complete_dmesg,
    parse_probe,
    shell_ready,
)


class HostProbeCommandTest(unittest.TestCase):
    def test_each_probe_line_fits_the_busybox_console_buffer(self):
        for command in HOST_PROBE_COMMANDS:
            with self.subTest(command=command):
                self.assertLessEqual(len(command), 200)
                self.assertNotIn(b"\n", command)


class DmesgCommandTest(unittest.TestCase):
    def test_command_ends_with_a_real_newline(self):
        self.assertTrue(DMESG_COMMAND.endswith(b"\n"))
        self.assertNotIn(b"\\n", DMESG_COMMAND)


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


class ShellReadyTest(unittest.TestCase):
    def test_incomplete_initramfs_output_is_not_ready(self):
        data = b"HTC One M7, mainline Linux\nM7_READY_BEGIN\nM7_KERNEL=7.1.0-m7\n"

        self.assertFalse(shell_ready(data))

    def test_complete_initramfs_output_is_ready(self):
        data = b"M7_READY_BEGIN\nM7_KERNEL=7.1.0-m7\nM7_READY_END\n"

        self.assertTrue(shell_ready(data))

    def test_fresh_shell_prompt_is_ready(self):
        self.assertTrue(shell_ready(b"sh: can't access tty; job control turned off\n/ # "))


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

    def test_prompt_prefixed_dmesg_block_is_accepted(self):
        data = (
            b"/ # M7_DMESG_BEGIN\n"
            b"[    1.000000] kernel log\n"
            b"/ # M7_DMESG_END\n"
            b"/ # "
        )

        self.assertTrue(has_complete_dmesg(data))


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

    def test_prompt_prefixed_live_probe_is_accepted(self):
        data = (
            b"/ # M7_HOST_PROBE_BEGIN\n"
            b"/ # M7_KERNEL=7.1.0-m7\n"
            b"/ # M7_WLAN_PRESENT=no\n"
            b"/ # / # M7_DEFERRED=\n"
            b"/ # M7_HOST_PROBE_END\n"
            b"/ # "
        )

        ready, probe, source = parse_probe(data)

        self.assertTrue(ready)
        self.assertEqual(source, "host")
        self.assertEqual(probe["M7_KERNEL"], "7.1.0-m7")
        self.assertEqual(probe["M7_WLAN_PRESENT"], "no")
        self.assertEqual(probe["M7_DEFERRED"], "")

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
