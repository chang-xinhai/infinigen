#!/usr/bin/env bash
set -euo pipefail

auto_root="/home/xinhai/projects/cuakr-docker/output/paper/inference_video_fixed_local"

usage() {
  echo "usage: $0 <rgb_dir>" >&2
  echo "       $0 --auto" >&2
}

make_mp4() {
  local rgb_dir="$1"
  local parent_dir dir_name out_path pattern

  if [[ ! -d "$rgb_dir" ]]; then
    echo "error: directory not found: $rgb_dir" >&2
    return 1
  fi

  parent_dir="$(dirname "$rgb_dir")"
  dir_name="$(basename "$rgb_dir")"
  out_path="${parent_dir}/${dir_name}.mp4"

  if [[ -f "$out_path" ]]; then
    echo "skip: output already exists: $out_path"
    return 0
  fi

  if compgen -G "${rgb_dir}/*.png" > /dev/null; then
    pattern="${rgb_dir}/*.png"
  elif compgen -G "${rgb_dir}/*.jpg" > /dev/null; then
    pattern="${rgb_dir}/*.jpg"
  elif compgen -G "${rgb_dir}/*.jpeg" > /dev/null; then
    pattern="${rgb_dir}/*.jpeg"
  else
    echo "error: no .png/.jpg/.jpeg images found in $rgb_dir" >&2
    return 1
  fi

  ffmpeg -y \
    -framerate 30 \
    -pattern_type glob \
    -i "$pattern" \
    -c:v libx264 \
    -pix_fmt yuv420p \
    "$out_path"

  echo "wrote $out_path"
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

if [[ "$1" == "--auto" ]]; then
  if [[ ! -d "$auto_root" ]]; then
    echo "error: auto root not found: $auto_root" >&2
    exit 1
  fi

  found=0
  while IFS= read -r -d '' camera_dir; do
    rgb_dir="${camera_dir}/rgb"
    if [[ ! -d "$rgb_dir" ]]; then
      continue
    fi

    if ! compgen -G "${rgb_dir}/*.png" > /dev/null \
      && ! compgen -G "${rgb_dir}/*.jpg" > /dev/null \
      && ! compgen -G "${rgb_dir}/*.jpeg" > /dev/null; then
      continue
    fi

    found=1
    make_mp4 "$rgb_dir"
  done < <(find "$auto_root" -type d \( -name fix_local -o -name fix_global \) -print0)

  if [[ "$found" -eq 0 ]]; then
    echo "error: no fix_local/fix_global rgb directories with images found under $auto_root" >&2
    exit 1
  fi

  exit 0
fi

make_mp4 "${1%/}"
