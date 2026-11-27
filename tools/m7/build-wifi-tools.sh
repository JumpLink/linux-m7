#!/usr/bin/env bash
set -euo pipefail

# Build the optional static ARMv7 WLAN userspace tools in a pinned container.
# Usage: ./tools/m7/build-wifi-tools.sh [output-dir]

root=$(cd "$(dirname "$0")/../.." && pwd)
output=${1:-"$root/build/m7/wifi-tools"}
cache=${M7_WIFI_TOOLS_CACHE:-"${XDG_CACHE_HOME:-$HOME/.cache}/linux-m7/wifi-tools"}
jobs=${M7_WIFI_JOBS:-2}
image=docker.io/library/debian@sha256:e67eeead736ff7bbe258ef088bff683635c561b1fcfefad0806c1df4ab49ce0e
wpa_version=2.11
iw_version=5.19
source_epoch=1721500051

for tool in curl sha256sum python3 podman mktemp; do
	command -v "$tool" >/dev/null || {
		echo "missing tool: $tool" >&2
		exit 1
	}
done
if ! [[ "$jobs" =~ ^[1-9][0-9]*$ ]]; then
	echo "M7_WIFI_JOBS must be a positive integer" >&2
	exit 1
fi

mkdir -p "$output" "$cache"
output=$(cd "$output" && pwd)
cache=$(cd "$cache" && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/linux-m7-wifi-tools.XXXXXX")
cleanup() {
	podman unshare chown -R 0:0 "$work" "$output" >/dev/null 2>&1 || true
	rm -rf "$work" || true
}
trap cleanup EXIT

fetch() {
	local url=$1 name=$2 expected=$3 path="$cache/$2"
	if [ ! -f "$path" ]; then
		curl --fail --location --silent --show-error "$url" --output "$path.tmp"
		mv "$path.tmp" "$path"
	fi
	printf '%s  %s\n' "$expected" "$path" | sha256sum --check --status
}

fetch "https://w1.fi/releases/wpa_supplicant-$wpa_version.tar.gz" \
	wpa_supplicant.tar.gz \
	912ea06f74e30a8e36fbb68064d6cdff218d8d591db0fc5d75dee6c81ac7fc0a
fetch "https://deb.debian.org/debian/pool/main/i/iw/iw_${iw_version}.orig.tar.xz" \
	iw.tar.xz \
	f167bbe947dd53bb9ebc0c1dcef5db6ad73ac1d6084f2c6f9376c5c360cc4d4e

rm -f "$output/iw" "$output/wpa_cli" "$output/wpa_supplicant" "$output/SHA256SUMS"
podman run --rm --interactive --platform linux/arm/v7 \
	-v "$cache/wpa_supplicant.tar.gz:/src/wpa_supplicant.tar.gz:ro,Z" \
	-v "$cache/iw.tar.xz:/src/iw.tar.xz:ro,Z" \
	-v "$work:/build:Z" \
	-v "$output:/out:Z" \
	-e SOURCE_DATE_EPOCH="$source_epoch" \
	-e M7_WIFI_JOBS="$jobs" \
	-e LC_ALL=C \
	-e TZ=UTC \
	-e DEBIAN_FRONTEND=noninteractive \
	"$image" bash -s <<'CONTAINER'
set -euo pipefail
umask 022
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
	gcc-12=12.2.0-14+deb12u1 \
	make=4.3-4.1 \
	libc6-dev=2.36-9+deb12u14 \
	libnl-3-dev=3.7.0-0.2+b1 \
	libnl-genl-3-dev=3.7.0-0.2+b1 \
	libssl-dev=3.0.22-1~deb12u2 \
	xz-utils=5.4.1-1+deb12u2 \
	pkgconf=1.8.1-1 \
	binutils=2.40-2 >/dev/null

tar -xzf /src/wpa_supplicant.tar.gz -C /build
tar -xJf /src/iw.tar.xz -C /build

cd /build/wpa_supplicant-2.11/wpa_supplicant
cat > .config <<'WPA_CONFIG'
CONFIG_DRIVER_NL80211=y
CONFIG_LIBNL32=y
CONFIG_CTRL_IFACE=y
CONFIG_CTRL_IFACE_UNIX=y
CONFIG_IEEE8021X_EAPOL=y
CONFIG_TLS=openssl
CONFIG_NO_WPA_PASSPHRASE=y
CONFIG_NO_CONFIG_WRITE=y
CONFIG_NO_CONFIG_BLOBS=y
CONFIG_NO_RADIUS=y
WPA_CONFIG
make -j"${M7_WIFI_JOBS:-2}" CC=gcc-12 PKG_CONFIG=pkgconf LDFLAGS=-static \
	wpa_supplicant wpa_cli

cd /build/iw-5.19
make -j"${M7_WIFI_JOBS:-2}" CC=gcc-12 PKG_CONFIG=pkgconf LDFLAGS=-static iw

strip --strip-unneeded \
	/build/wpa_supplicant-2.11/wpa_supplicant/wpa_supplicant \
	/build/wpa_supplicant-2.11/wpa_supplicant/wpa_cli \
	/build/iw-5.19/iw
install -m 0755 \
	/build/wpa_supplicant-2.11/wpa_supplicant/wpa_supplicant \
	/build/wpa_supplicant-2.11/wpa_supplicant/wpa_cli \
	/build/iw-5.19/iw /out/
touch -d "@${SOURCE_DATE_EPOCH}" /out/iw /out/wpa_cli /out/wpa_supplicant
CONTAINER

podman unshare chown -R 0:0 "$work" "$output"
python3 "$root/tools/m7/wifi_tools.py" validate "$output" >/dev/null
(
	cd "$output"
	sha256sum iw wpa_cli wpa_supplicant > SHA256SUMS
)
if command -v qemu-arm-static >/dev/null; then
	qemu-arm-static "$output/wpa_supplicant" -v >/dev/null
	qemu-arm-static "$output/wpa_cli" -v >/dev/null
	if ! iw_output=$(LC_ALL=C qemu-arm-static "$output/iw" -V 2>&1); then
		[ "$iw_output" = "Failed to connect to generic netlink." ] || {
			echo "iw failed under qemu-arm: $iw_output" >&2
			exit 1
		}
	fi
fi

printf 'Built static ARM WLAN tools in %s\n' "$output"
