#!/usr/bin/env bash
# N5-C r2 / FIX-5：从**最终桥本体**重生成存档 diff（脚本化，杜绝手抄过期）。
#
# raven R-M1 的事实：r1 的 `bridge_mem.diff` 生成于 16:29，而被证明的桥最后写入于 16:42
# ⇒ 存档缺 25 行（恰是 `--stub-remote-api` 的 argparse / 桩 provider / 读数），
#   而桩恰恰是 r1 的 C-4 结论的前提。⇒ 每轮收口都必须**重跑本脚本**。
#
# 用法：bash v0/spikes/n5c-evidence/tools/make-bridge-mem-diff.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WT="$(cd "$HERE/../../../.." && pwd)"       # <worktree root>
FROZEN_BRIDGE="$WT/v0/02_source/v0_skeleton/session/bridge/kernel_bridge.py"
EVIDENCE_BRIDGE="$WT/v0/spikes/n5c-evidence/bridge_mem/kernel_bridge_mem.py"
OUT="$WT/v0/spikes/n5c-evidence/bridge_mem/bridge_mem.diff"

test -f "$FROZEN_BRIDGE" || { echo "missing $FROZEN_BRIDGE" >&2; exit 1; }
test -f "$EVIDENCE_BRIDGE" || { echo "missing $EVIDENCE_BRIDGE" >&2; exit 1; }

{
  printf '# N5-C r2 · bridge_mem.diff — 由 tools/make-bridge-mem-diff.sh 生成\n'
  printf '# generated_at_epoch: %s\n' "$(date +%s)"
  printf '# left  (frozen)  : %s\n' "$FROZEN_BRIDGE"
  printf '# right (evidence): %s\n' "$EVIDENCE_BRIDGE"
  printf '# left_sha256 : %s\n' "$(shasum -a 256 "$FROZEN_BRIDGE" | awk '{print $1}')"
  printf '# right_sha256: %s\n' "$(shasum -a 256 "$EVIDENCE_BRIDGE" | awk '{print $1}')"
  printf '# 生成命令: diff -u "%s" "%s"\n' "$FROZEN_BRIDGE" "$EVIDENCE_BRIDGE"
  diff -u "$FROZEN_BRIDGE" "$EVIDENCE_BRIDGE" || true
} > "$OUT"

LINES=$(wc -l < "$OUT")
ADDED=$(grep -c '^+[^+]' "$OUT" || true)
REMOVED=$(grep -c '^-[^-]' "$OUT" || true)
echo "bridge_mem.diff: lines=$LINES added=$ADDED removed=$REMOVED out=$OUT"
