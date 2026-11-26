#!/usr/bin/env bash
set -euo pipefail

# Refuse every fastboot target that does not identify itself as the M7.
# A serial alone is not an identity: several phones can share one host and
# their fastboot serials do not reliably match their adb serials.

serial=${1:?Usage: require-m7-fastboot.sh SERIAL}
product=$(timeout 5 fastboot -s "$serial" getvar product 2>&1 \
	| sed -n 's/^product: //p' | tail -n 1)

if [ "$product" != m7_ul ]; then
	echo "refusing fastboot target: product '${product:-unknown}', expected m7_ul" >&2
	exit 1
fi
