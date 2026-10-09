#!/usr/bin/env bash
# AC-A-2c/A-2d · 生成 `v0/spikes/n5-asset/shots/MANIFEST.sha256`（当前冻结集）+ 标注 superseded 旧标签。
# 用法：bash gen-shots-manifest.sh <tag> <captured_by> <superseded_tags_space_separated>
set -euo pipefail
TAG="${1:?tag required}"
CAPTURED_BY="${2:-artisan}"
SUPERSEDED="${3:-}"
WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
SHOTS="$WORKSPACE/spikes/n5-asset/shots"
cd "$SHOTS"

FROZEN_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
{
  printf 'frozen_at=%s\n' "$FROZEN_AT"
  printf 'captured_by=%s\n' "$CAPTURED_BY"
  printf 'tag=%s\n' "$TAG"
  for file in $(ls | grep -- "-${TAG}" | grep -- "\.png$" | sort); do
    shasum -a 256 "$file"
  done
} > MANIFEST.sha256

if [ -n "$SUPERSEDED" ]; then
  {
    printf 'superseded_at=%s\n' "$FROZEN_AT"
    printf 'note=重拍保留：这些标签的图仍留在盘上，但判定只用 MANIFEST.sha256\n'
    for old in $SUPERSEDED; do
      printf 'superseded_tag=%s files=%s\n' "$old" "$(ls | grep -c -- "-${old}\.png$")"
    done
  } > MANIFEST.superseded.txt
fi

LINE_COUNT=$(grep -c '^[0-9a-f]\{64\}  ' MANIFEST.sha256)
printf 'MANIFEST shots=%s tag=%s frozen_at=%s\n' "$LINE_COUNT" "$TAG" "$FROZEN_AT"
