#!/usr/bin/env python3
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "drivers/clk/qcom/gcc-msm8960.c"
PXO_RATE = 27_000_000
PLL8_RATE = 384_000_000


def parse_sdc_table():
    source = SOURCE.read_text()
    match = re.search(
        r"static const struct freq_tbl clk_tbl_sdc\[\] = \{(.*?)\n\};",
        source,
        re.DOTALL,
    )
    if not match:
        raise AssertionError("clk_tbl_sdc not found")

    entries = []
    for line in match.group(1).splitlines():
        line = line.strip().rstrip(",")
        freq_match = re.fullmatch(r"F\((\d+), P_(PXO|PLL8), (\d+), (\d+), (\d+)\)", line)
        if freq_match:
            freq, parent, half_div, m, n = freq_match.groups()
            entries.append(
                {
                    "freq": int(freq),
                    "parent": parent,
                    "pre_div": 2 * int(half_div),
                    "m": int(m),
                    "n": int(n),
                }
            )
            continue

        literal_match = re.fullmatch(
            r"\{\s*(\d+), P_(PXO|PLL8),\s*(\d+),\s*(\d+),\s*(\d+)\s*\}",
            line,
        )
        if literal_match:
            freq, parent, pre_div, m, n = literal_match.groups()
            entries.append(
                {
                    "freq": int(freq),
                    "parent": parent,
                    "pre_div": int(pre_div),
                    "m": int(m),
                    "n": int(n),
                }
            )

    if not entries:
        raise AssertionError("clk_tbl_sdc has no readable entries")
    return entries


def select_rate(entries, requested):
    selected = entries[-1]
    for entry in entries:
        if requested <= entry["freq"]:
            selected = entry
            break
    return selected


def calculate_rate(entry):
    parent_rate = PXO_RATE if entry["parent"] == "PXO" else PLL8_RATE
    rate = parent_rate // entry["pre_div"]
    if entry["n"]:
        rate = rate * entry["m"] // entry["n"]
    return rate


class SdcClockTableTests(unittest.TestCase):
    def setUp(self):
        self.entries = parse_sdc_table()

    def test_low_sdio_rates_select_exact_entries(self):
        for requested in (400_000, 450_000, 500_000, 1_000_000):
            with self.subTest(requested=requested):
                selected = select_rate(self.entries, requested)
                self.assertEqual(selected["freq"], requested)
                self.assertEqual(calculate_rate(selected), requested)

    def test_entries_are_sorted_and_fit_counter_width(self):
        frequencies = [entry["freq"] for entry in self.entries]
        self.assertEqual(frequencies, sorted(frequencies))
        for entry in self.entries:
            with self.subTest(freq=entry["freq"]):
                self.assertLessEqual(entry["m"], 255)
                self.assertLessEqual(entry["n"], 255)
                self.assertLessEqual(entry["pre_div"], 4)


if __name__ == "__main__":
    unittest.main()
