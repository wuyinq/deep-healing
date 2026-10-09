#!/usr/bin/env bash
# N3 · C6 环境无关性：同 seed、`pace` 两档各跑一次 `live`（真 CLI），关键读数必须一致。
# 用法: bash n3_c6_pace.sh <ws>
set -u
WS="$1"
SK="$WS/v0/02_source/v0_skeleton"
SPIKE="$WS/v0/spikes/n3-character-loop"
PACK="$SK/districts/xingfu-xiaoqu-xuqin"
mkdir -p "$SPIKE/runs/live-pace-a" "$SPIKE/runs/live-pace-b"

run_arm() {
  local name="$1" pace="$2" port="$3"
  echo "### arm=$name pace=$pace port=$port"
  cd "$SK/kernel" || exit 1
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m deephealing_kernel live \
    --pack "$PACK" --seed 20260921 --events "$SPIKE/runs/live-$name/events.jsonl" \
    --out "$SPIKE/runs/live-$name" --no-warmup --ticks 2880 --pace "$pace" --port "$port" \
    --memory-chain --capability-chain > "$SPIKE/runs/live-$name/cli.log" 2>&1
  echo "arm=$name exit=$?"
  tail -3 "$SPIKE/runs/live-$name/cli.log"
}

run_arm pace-a 0.0005 8821
run_arm pace-b 0.0030 8822

echo "=== 事件流逐字节比对（pace 只影响墙钟，不得进入世界） ==="
if cmp -s "$SPIKE/runs/live-pace-a/events.jsonl" "$SPIKE/runs/live-pace-b/events.jsonl"; then
  echo "BYTE_IDENTICAL events.jsonl"
else
  echo "DIFFERS events.jsonl"
  diff <(head -c 2000 "$SPIKE/runs/live-pace-a/events.jsonl") \
       <(head -c 2000 "$SPIKE/runs/live-pace-b/events.jsonl") | head -10
fi
echo "=== live_state.json 关键读数 ==="
for name in pace-a pace-b; do
  printf "%s: " "$name"
  python3 -m json.tool "$SPIKE/runs/live-$name/live_state.json" 2>/dev/null | grep -E '"(tick|state_hash|event_chain_hash|pace_s_per_tick)"' | tr '\n' ' '
  echo
done
