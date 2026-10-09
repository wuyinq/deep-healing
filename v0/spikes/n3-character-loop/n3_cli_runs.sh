#!/usr/bin/env bash
# N3 · AC-1/2/3/7 主证据：**交付面 CLI 自然运行**（不带 --replay、不用 harness、不 promote）。
# 用法: bash n3_cli_runs.sh <ws>
set -u
WS="$1"
SK="$WS/v0/02_source/v0_skeleton"
SPIKE="$WS/v0/spikes/n3-character-loop"
PACK="$SK/districts/xingfu-xiaoqu-xuqin"

run_arm() {
  local name="$1"
  mkdir -p "$SPIKE/runs/cli-$name"
  echo "### CLI 自然运行 arm=$name"
  cd "$SK/kernel" || exit 1
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m deephealing_kernel run \
    --pack "$PACK" --seed 20260921 \
    --events "$SPIKE/runs/cli-$name/events.jsonl" \
    --ticks 2880 --snapshot-every 0 \
    --memory-chain --capability-chain \
    > "$SPIKE/runs/cli-$name/cli.log" 2>&1
  echo "arm=$name exit=$?"
  tail -1 "$SPIKE/runs/cli-$name/cli.log"
}

run_arm cli-1
run_arm cli-2

echo "### 对照臂（唯一变量 = `npcs/npc-006.json` 的 `pressure_window` 声明是否在；包副本在 spike 目录，交付树未动）"
UNDECL="$SPIKE/runs/pack-undeclared/xingfu-xiaoqu-xuqin"
run_arm_off() {
  local name="$1" ticks="$2"
  mkdir -p "$SPIKE/runs/cli-$name"
  cd "$SK/kernel" || exit 1
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m deephealing_kernel run \
    --pack "$UNDECL" --seed 20260921 \
    --events "$SPIKE/runs/cli-$name/events.jsonl" \
    --ticks "$ticks" --snapshot-every 0 \
    --memory-chain --capability-chain \
    > "$SPIKE/runs/cli-$name/cli.log" 2>&1
  echo "arm=$name ticks=$ticks exit=$?"
  tail -1 "$SPIKE/runs/cli-$name/cli.log"
}
run_arm_off undeclared-2880 2880
run_arm_off undeclared-480 480

echo "=== AC-7：两次运行事件流逐字节比对 ==="
if cmp -s "$SPIKE/runs/cli-cli-1/events.jsonl" "$SPIKE/runs/cli-cli-2/events.jsonl"; then
  echo "BYTE_IDENTICAL events.jsonl（同 seed 两次自然运行）"
else
  echo "DIFFERS events.jsonl"
fi
echo "=== AC-4：首个分叉 tick（对照臂 vs 缺失臂，逐行 diff 第一处） ==="
first_on=$(grep -n "" "$SPIKE/runs/cli-cli-1/events.jsonl" | head -1 | cut -d: -f1)
diff <(cat "$SPIKE/runs/cli-cli-1/events.jsonl") <(cat "$SPIKE/runs/cli-undeclared-2880/events.jsonl") > /tmp/n3-ac4.diff 2>&1
echo "diff 行数: $(wc -l < /tmp/n3-ac4.diff)"; head -6 /tmp/n3-ac4.diff
echo "=== 事件类型计数（arm cli-1） ==="
grep -o '"type": "[a-z.]*"' "$SPIKE/runs/cli-cli-1/events.jsonl" | sort | uniq -c
