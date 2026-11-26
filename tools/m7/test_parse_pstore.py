#!/usr/bin/env python3
import pathlib
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from parse_pstore import PERSISTENT_RAM_SIG, PSTORE_TYPE_PMSG, VERSION_CODE, parse_dump


class ParsePstoreTests(unittest.TestCase):
    def make_dump(self):
        return bytearray(0x100000)

    def write_zone(self, dump, offset, payload, signature=PERSISTENT_RAM_SIG, start=0):
        capacity = 0x20000 - 12
        self.assertLessEqual(len(payload), capacity)
        self.assertLessEqual(start, capacity)
        header_start = (start + len(payload)) % capacity
        dump[offset:offset + 12] = (
            signature.to_bytes(4, "little")
            + header_start.to_bytes(4, "little")
            + len(payload).to_bytes(4, "little")
        )
        first = min(len(payload), capacity - start)
        dump[offset + 12 + start:offset + 12 + start + first] = payload[:first]
        if first < len(payload):
            dump[offset + 12:offset + 12 + len(payload) - first] = payload[first:]

    def test_console_wraps_ring_buffer(self):
        dump = self.make_dump()
        self.write_zone(dump, 0xA0000, b"alpha123", start=5)

        with tempfile.TemporaryDirectory() as directory:
            summary = parse_dump(dump, pathlib.Path(directory))
            decoded = (pathlib.Path(directory) / "console.txt").read_bytes()

        zone = next(item for item in summary["zones"] if item["name"] == "console")
        self.assertEqual(zone["start"], 13)
        self.assertEqual(zone["size"], 8)
        self.assertEqual(decoded, b"alpha123")

    def test_console_wraps_at_end_of_zone(self):
        dump = self.make_dump()
        capacity = 0x20000 - 12
        payload = b"XY" + b"a" * (capacity - 2)
        start = capacity - 2
        self.write_zone(dump, 0xA0000, payload, start=start)

        with tempfile.TemporaryDirectory() as directory:
            parse_dump(dump, pathlib.Path(directory))
            decoded = (pathlib.Path(directory) / "console.txt").read_bytes()

        self.assertEqual(decoded, payload)

    def test_console_header_is_found_away_from_fixed_offset(self):
        dump = self.make_dump()
        payload = (
            b"[    0.000000] Booting Linux on physical CPU 0x0\n"
            b"[    0.000000] Linux version 7.1.0-test #3 SMP PREEMPT\n"
            b"[    2.838090] Run /init as init process\n"
        )
        self.write_zone(dump, 0xAFFFA, payload)

        with tempfile.TemporaryDirectory() as directory:
            summary = parse_dump(dump, pathlib.Path(directory))
            decoded = (pathlib.Path(directory) / "console.txt").read_bytes()

        self.assertEqual(decoded, payload)
        zone = next(item for item in summary["zones"] if item["name"] == "console")
        self.assertEqual(zone["offset"], "0xafffa")
        self.assertIn("Linux version 7.1.0-test", summary["kernel_banner"])

    def test_compressed_dmesg_is_decoded(self):
        dump = self.make_dump()
        text = b"Kernel panic - not syncing: test panic\n"
        header = b"====123.456-C\n"
        compressed = zlib.compressobj(wbits=-15)
        payload = header + compressed.compress(text) + compressed.flush()
        self.write_zone(dump, 0, payload)

        with tempfile.TemporaryDirectory() as directory:
            summary = parse_dump(dump, pathlib.Path(directory))
            decoded = (pathlib.Path(directory) / "dmesg-0.txt").read_bytes()

        self.assertEqual(decoded, text)
        zone = next(item for item in summary["zones"] if item["name"] == "dmesg-0")
        self.assertEqual(zone["start"], len(payload))
        self.assertEqual(zone["decoder"], "zlib")

    def test_pmsg_signature_is_checked(self):
        dump = self.make_dump()
        self.write_zone(
            dump,
            0xC0000,
            b"userspace message\n",
            signature=PERSISTENT_RAM_SIG ^ PSTORE_TYPE_PMSG,
        )

        with tempfile.TemporaryDirectory() as directory:
            summary = parse_dump(dump, pathlib.Path(directory))
            decoded = (pathlib.Path(directory) / "pmsg.txt").read_bytes()

        self.assertEqual([item["name"] for item in summary["zones"]], ["pmsg"])
        self.assertEqual(decoded, b"userspace message\n")

    def test_invalid_header_is_not_reported_as_a_zone(self):
        dump = self.make_dump()
        dump[0xA0000:0xA000C] = (
            PERSISTENT_RAM_SIG.to_bytes(4, "little")
            + (0xFFFFFFFF).to_bytes(4, "little")
            + (18).to_bytes(4, "little")
        )

        with tempfile.TemporaryDirectory() as directory:
            summary = parse_dump(dump, pathlib.Path(directory))

        self.assertEqual(summary["valid_zones"], 0)
        self.assertEqual(summary["zones"], [])

    def test_ftrace_uses_kernel_version_signature(self):
        dump = self.make_dump()
        self.write_zone(
            dump,
            0xD0000,
            b"trace data\n",
            signature=PERSISTENT_RAM_SIG ^ VERSION_CODE,
        )

        with tempfile.TemporaryDirectory() as directory:
            summary = parse_dump(dump, pathlib.Path(directory))

        self.assertEqual([item["name"] for item in summary["zones"]], ["ftrace"])


if __name__ == "__main__":
    unittest.main()
