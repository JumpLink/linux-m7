#!/usr/bin/env python3
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from patch_zimage_early_reboot import LEGACY_PATCHED, ORIGINAL, PATCHED, patch_zimage


class PatchZimageTests(unittest.TestCase):
    def make_image(self, directory):
        path = pathlib.Path(directory) / "zImage"
        path.write_bytes(ORIGINAL + b"kernel payload" + b"\0" * 64)
        return path

    def test_patch_replaces_only_entry_prologue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_image(directory)
            self.assertTrue(patch_zimage(path))
            self.assertEqual(path.read_bytes(), PATCHED + b"kernel payload" + b"\0" * 64)

    def test_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_image(directory)
            patch_zimage(path)
            self.assertFalse(patch_zimage(path))
            self.assertEqual(path.read_bytes(), PATCHED + b"kernel payload" + b"\0" * 64)

    def test_legacy_patch_is_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "zImage"
            path.write_bytes(LEGACY_PATCHED + b"kernel payload" + b"\0" * 64)
            self.assertTrue(patch_zimage(path))
            self.assertEqual(path.read_bytes(), PATCHED + b"kernel payload" + b"\0" * 64)

    def test_patch_rejects_unknown_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "zImage"
            path.write_bytes(b"not a kernel" + b"\0" * 64)
            with self.assertRaises(ValueError):
                patch_zimage(path)


if __name__ == "__main__":
    unittest.main()
