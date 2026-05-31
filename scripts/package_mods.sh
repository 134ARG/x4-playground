#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

cd "$repo_dir"

build_dir="build"
stage_dir="$build_dir/.package_stage"

stage_super_phoenix_teladi() {
  source_mod_dir=$1
  source_mod_name=$2
  staged_mod_dir="$stage_dir/$source_mod_name"

  mkdir -p "$stage_dir"
  cp -R "$source_mod_dir" "$stage_dir/"
  mkdir -p "$staged_mod_dir/assets/units/size_l"
  rm -f "$staged_mod_dir/assets/units/size_l/super_phoenix_teladi.xml"
  rm -rf "$staged_mod_dir/assets/units/size_l/super_phoenix_teladi_data" \
    "$staged_mod_dir/assets/units/size_l/super_phoenix_teladi_data.ani"

  sed \
    -e 's/<component name="super_phoenix"/<component name="super_phoenix_teladi"/' \
    -e 's#extensions\\super_phoenix\\assets\\units\\size_l\\super_phoenix_data#extensions\\super_phoenix_teladi\\assets\\units\\size_l\\super_phoenix_teladi_data#' \
    "super_phoenix/assets/units/size_l/super_phoenix.xml" \
    > "$staged_mod_dir/assets/units/size_l/super_phoenix_teladi.xml"

  cp -R "super_phoenix/assets/units/size_l/super_phoenix_data" \
    "$staged_mod_dir/assets/units/size_l/super_phoenix_teladi_data"
  cp "super_phoenix/assets/units/size_l/super_phoenix_data.ani" \
    "$staged_mod_dir/assets/units/size_l/super_phoenix_teladi_data.ani"
}

mkdir -p "$build_dir"
rm -rf "$stage_dir"
trap 'rm -rf "$stage_dir"' EXIT HUP INT TERM

count=0

for content_xml in ./*/content.xml; do
  [ -f "$content_xml" ] || continue

  mod_dir=${content_xml%/content.xml}
  mod_name=${mod_dir#./}
  zip_path="$repo_dir/$build_dir/$mod_name.zip"
  package_dir="$mod_dir"

  if [ "$mod_name" = "super_phoenix_teladi" ]; then
    stage_super_phoenix_teladi "$mod_dir" "$mod_name"
    package_dir="$stage_dir/$mod_name"
  fi

  printf 'Packaging %s -> %s\n' "$mod_name" "$zip_path"
  rm -f "$zip_path"
  (
    cd "$(dirname "$package_dir")"
    zip -qr -X "$zip_path" "$mod_name"
  )

  count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
  printf 'No root-level mod folders with content.xml were found.\n' >&2
  exit 1
fi

printf 'Packaged %s mod(s) into %s/\n' "$count" "$build_dir"
