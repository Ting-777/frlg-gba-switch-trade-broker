#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 /path/to/GBLink-Firmware" >&2
    exit 2
fi

firmware_checkout=$(cd "$1" && pwd)
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_root=$(cd "$script_dir/.." && pwd)
expected_commit=2facc86bc7292b1adad436ba8ebd5a7ccd649c12
actual_commit=$(git -C "$firmware_checkout" rev-parse HEAD)
if [[ "$actual_commit" != "$expected_commit" ]]; then
    echo "expected GBLink-Firmware $expected_commit, got $actual_commit" >&2
    exit 1
fi
if [[ -n $(git -C "$firmware_checkout" status --porcelain) ]]; then
    echo "GBLink-Firmware checkout must be clean" >&2
    exit 1
fi

git -C "$firmware_checkout" apply --check --unidiff-zero "$project_root/firmware/patches/0001-trade-broker-integration.patch"
mkdir -p "$firmware_checkout/src/broker"
cp "$project_root"/firmware/gb-link/*.{cpp,hpp} "$firmware_checkout/src/broker/"
git -C "$firmware_checkout" apply --unidiff-zero "$project_root/firmware/patches/0001-trade-broker-integration.patch"
echo "GB-Link broker integration installed. Build with the upstream west/Zephyr workflow."
