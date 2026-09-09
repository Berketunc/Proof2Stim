#!/usr/bin/env bash
set -euo pipefail

proof2stim_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
proof2stim_release="2026-09-03"
proof2stim_archive_name="oss-cad-suite-linux-x64-20260903.tgz"
proof2stim_sha256="35544965a37a2dba015586a7bb6e52ec65c59f7b62aeb18effe43501c4d3f551"
proof2stim_destination="$proof2stim_root/.tools/oss-cad-suite"
proof2stim_archive="/tmp/$proof2stim_archive_name"
proof2stim_url="https://github.com/YosysHQ/oss-cad-suite-build/releases/download/$proof2stim_release/$proof2stim_archive_name"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "This pinned bootstrap currently supports Linux x86_64 only." >&2
  exit 2
fi

if [[ -x "$proof2stim_destination/bin/yosys" ]]; then
  echo "OSS CAD Suite is already installed at $proof2stim_destination"
  exit 0
fi

mkdir -p "$proof2stim_root/.tools"
if [[ ! -f "$proof2stim_archive" ]]; then
  curl -fL --retry 3 -o "$proof2stim_archive" "$proof2stim_url"
fi

echo "$proof2stim_sha256  $proof2stim_archive" | sha256sum --check --status
tar -xzf "$proof2stim_archive" -C "$proof2stim_root/.tools"
echo "Installed OSS CAD Suite $proof2stim_release at $proof2stim_destination"
