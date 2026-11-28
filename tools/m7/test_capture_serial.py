#!/usr/bin/env python3
"""Tests for the M7 serial probe parser."""

import errno
import pathlib
import tempfile
import termios
import time
import unittest
from unittest import mock

from tools.m7.capture_serial import (
    DMESG_COMMAND,
    HOST_PROBE_COMMANDS,
    WLAN_DIAGNOSTIC_COMMANDS,
    capture_console,
    close_tty,
    configure_tty,
    has_complete_dmesg,
    host_probe_commands,
    host_probe_satisfied,
    parse_probe,
    shell_ready,
)


class HostProbeCommandTest(unittest.TestCase):
    def test_each_probe_line_fits_the_busybox_console_buffer(self):
        for diagnostics in (False, True):
            for command in host_probe_commands(diagnostics):
                with self.subTest(command=command, diagnostics=diagnostics):
                    self.assertLessEqual(len(command), 113)
                    self.assertNotIn(b"\n", command)

    def test_standard_probe_omits_diagnostics(self):
        self.assertEqual(host_probe_commands(), HOST_PROBE_COMMANDS)
        self.assertFalse(any(b"M7_WLAN_DIAG" in command for command in HOST_PROBE_COMMANDS))

    def test_diagnostics_precede_probe_terminator(self):
        commands = host_probe_commands(wlan_diagnostics=True)

        self.assertEqual(commands[: len(HOST_PROBE_COMMANDS) - 1], HOST_PROBE_COMMANDS[:-1])
        self.assertEqual(commands[len(HOST_PROBE_COMMANDS) - 1 : -1], WLAN_DIAGNOSTIC_COMMANDS)
        self.assertEqual(commands[-1], b"echo M7_HOST_PROBE_END")


class DmesgCommandTest(unittest.TestCase):
    def test_command_ends_with_a_real_newline(self):
        self.assertTrue(DMESG_COMMAND.endswith(b"\n"))
        self.assertNotIn(b"\\n", DMESG_COMMAND)


class CaptureConsoleTest(unittest.TestCase):
    def test_stale_tty_and_read_eio_recover_to_a_fresh_live_probe(self):
        class Clock:
            now = 0.0

            def monotonic(self):
                return self.now

            def sleep(self, seconds):
                self.now += seconds

            def select(self, fds, *_args):
                self.now += 0.2
                return fds, [], []

        clock = Clock()
        attrs = [
            0,
            0,
            0,
            0,
            termios.B115200,
            termios.B115200,
            [0] * termios.NCCS,
        ]
        ready = b"M7_READY_BEGIN\nM7_KERNEL=old\nM7_READY_END\n/ # "
        live_probe = (
            b"M7_HOST_PROBE_BEGIN\n"
            b"M7_KERNEL=7.1.0-m7\n"
            b"M7_WLAN_PRESENT=yes\n"
            b"M7_HOST_PROBE_END\n/ # "
        )
        reads = {
            10: [ready, OSError(errno.EIO, "disconnected")],
            11: [live_probe],
        }

        def read(fd, _size):
            values = reads[fd]
            if not values:
                raise BlockingIOError
            value = values.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value

        with tempfile.TemporaryDirectory() as directory:
            log = pathlib.Path(directory) / "serial.log"
            with (
                mock.patch("tools.m7.capture_serial.time.monotonic", side_effect=clock.monotonic),
                mock.patch("tools.m7.capture_serial.time.sleep", side_effect=clock.sleep),
                mock.patch("tools.m7.capture_serial.select.select", side_effect=clock.select),
                mock.patch(
                    "tools.m7.capture_serial.os.open",
                    side_effect=[
                        OSError(errno.ENOENT, "stale tty"),
                        10,
                        OSError(errno.EIO, "reconnecting"),
                        11,
                    ],
                ) as open_tty,
                mock.patch("tools.m7.capture_serial.os.read", side_effect=read),
                mock.patch("tools.m7.capture_serial.os.write", return_value=1),
                mock.patch("tools.m7.capture_serial.os.close"),
                mock.patch("tools.m7.capture_serial.termios.tcgetattr", return_value=attrs),
                mock.patch("tools.m7.capture_serial.termios.tcsetattr"),
                mock.patch(
                    "tools.m7.capture_serial.termios.tcflush",
                    side_effect=OSError(errno.EIO, "disconnected"),
                ),
            ):
                result = capture_console(
                    "/dev/ttyACM0", log, duration=1.0, require_wlan=True,
                )

            self.assertEqual(open_tty.call_count, 4)
            self.assertTrue(result["ready"])
            self.assertEqual(result["probe_source"], "host")
            self.assertEqual(result["probe"]["M7_WLAN_PRESENT"], "yes")
            self.assertEqual(result["bytes"], len(ready) + len(live_probe))
            self.assertIn(ready, log.read_bytes())
            self.assertIn(live_probe, log.read_bytes())


class ConfigureTtyTest(unittest.TestCase):
    def setUp(self):
        self.attrs = [
            0,
            0,
            0,
            0,
            termios.B115200,
            termios.B115200,
            [0] * termios.NCCS,
        ]

    def test_getattr_eio_marks_the_connection_stale(self):
        with mock.patch(
            "tools.m7.capture_serial.termios.tcgetattr",
            side_effect=termios.error(errno.EIO, "disconnected"),
        ):
            self.assertFalse(configure_tty(42))

    def test_setattr_eio_marks_the_connection_stale(self):
        with (
            mock.patch("tools.m7.capture_serial.termios.tcgetattr", return_value=self.attrs),
            mock.patch(
                "tools.m7.capture_serial.termios.tcsetattr",
                side_effect=OSError(errno.EIO, "disconnected"),
            ),
        ):
            self.assertFalse(configure_tty(42))

    def test_non_transient_termios_error_propagates(self):
        with mock.patch(
            "tools.m7.capture_serial.termios.tcgetattr",
            side_effect=termios.error(errno.EINVAL, "invalid argument"),
        ):
            with self.assertRaises(termios.error):
                configure_tty(42)


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
    def test_complete_live_probe_satisfies_standard_run(self):
        self.assertTrue(host_probe_satisfied(True, "host", {}, False))

    def test_wlan_requirement_waits_for_later_live_probe(self):
        self.assertFalse(
            host_probe_satisfied(
                True, "host", {"M7_WLAN_PRESENT": "no"}, True,
            )
        )
        self.assertTrue(
            host_probe_satisfied(
                True, "host", {"M7_WLAN_PRESENT": "yes"}, True,
            )
        )

    def test_initramfs_snapshot_never_satisfies_live_probe(self):
        self.assertFalse(
            host_probe_satisfied(
                True, "initramfs", {"M7_WLAN_PRESENT": "yes"}, True,
            )
        )

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


    def test_complete_wlan_diagnostics_are_reported(self):
        data = (
            b"M7_HOST_PROBE_BEGIN\nM7_WLAN_PRESENT=no\n"
            b"M7_WLAN_DIAG_BEGIN\ngpio38: high\nM7_WLAN_DIAG_END\n"
            b"M7_HOST_PROBE_END\n"
        )

        ready, probe, source = parse_probe(data)

        self.assertTrue(ready)
        self.assertEqual(source, "host")
        self.assertEqual(probe["M7_WLAN_DIAGNOSTICS"], "gpio38: high")

    def test_incomplete_wlan_diagnostics_are_not_reported(self):
        data = (
            b"M7_HOST_PROBE_BEGIN\nM7_WLAN_PRESENT=no\n"
            b"M7_WLAN_DIAG_BEGIN\ngpio38: high\nM7_HOST_PROBE_END\n"
        )

        ready, probe, source = parse_probe(data)

        self.assertTrue(ready)
        self.assertEqual(source, "host")
        self.assertNotIn("M7_WLAN_DIAGNOSTICS", probe)


if __name__ == "__main__":
    unittest.main()
