#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

cd "$repo_dir"

exec python3 tools/generate_weapon_range_mod.py \
  --assets-root x4-assets \
  --output weapon_range_enhancement \
  --force \
  "$@"
