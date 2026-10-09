#!/usr/bin/env bash
# AC-F-6 · **同口径** run ↔ replay 逐点一致 + 链外锚（`--expected-hash`）。
# ⚠️ 口径（实测踩过）：C-1 的日志是**取证桥**（memory-chain 打开）产出的 ⇒ 与**原厂 replay**
# 比会必然分歧（日志多 `memory.written`、`npc.decision.payload.memory_influence` 而 replay 侧为 None）。
# 因此 F-6 必须用**同一条原厂通路**（`deephealing_kernel run` ⇒ `verify`），不用桥产物。
set -u
WS="/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/_worktrees/n5c-evidence-20260924"
SRC="$WS/v0/02_source/v0_skeleton"
PACK="$SRC/districts/xingfu-xiaoqu"
KERNEL="$SRC/kernel"
OUT="/tmp/n5c-f6-run"
LOG="$WS/v0/spikes/n5c-evidence/readback/f6-replay-n5c.log"
: > "$LOG"

rm -rf "$OUT" 2>/dev/null; mkdir -p "$OUT"

echo "=== F-6 步骤 1：原厂 run（同 seed / 固定 tick 数） ===" >> "$LOG"
( cd "$KERNEL" && PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel run \
    --pack "$PACK" --seed 20260921 --ticks 200 --snapshot-every 1 \
    --events "$OUT/kernel-events.jsonl" ) >> "$LOG" 2>&1
echo "RUN_EXIT=$?" | tee -a "$LOG"
ls -la "$OUT" >> "$LOG" 2>&1

echo "=== F-6 步骤 2：verify（重放 + 逐检查点 state_hash 比对；不带锚） ===" >> "$LOG"
( cd "$KERNEL" && PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel verify \
    --events "$OUT/kernel-events.jsonl" --pack "$PACK" ) > "$OUT/verify-1.json" 2>&1
echo "VERIFY_1_EXIT=$?" | tee -a "$LOG"
python3 - "$OUT/verify-1.json" <<'PY' | tee -a "$LOG"
import json,sys
raw=open(sys.argv[1],encoding='utf-8').read()
obj=None
for line in raw.splitlines():
    line=line.strip()
    if line.startswith('{'):
        try: obj=json.loads(line)
        except Exception: pass
if obj is None:
    print('VERIFY_JSON=PARSE_FAIL'); raise SystemExit(0)
print('VERIFY_JSON=' + json.dumps({k:obj.get(k) for k in
      ['checkpoints_present','event_count','event_stream_compared','event_stream_divergences',
       'max_tick','plan_ticks','log_tail','expected_hash_provided','snapshots','seed','problems']}, ensure_ascii=False)[:1500])
print('LOG_TAIL=' + str(obj.get('log_tail')))
print('PROBLEMS_COUNT=' + str(len(obj.get('problems') or [])))
PY

TAIL=$(python3 - "$OUT/verify-1.json" <<'PY'
import json,sys
raw=open(sys.argv[1],encoding='utf-8').read(); obj=None
for line in raw.splitlines():
    line=line.strip()
    if line.startswith('{'):
        try: obj=json.loads(line)
        except Exception: pass
print((obj or {}).get('log_tail',''))
PY
)
echo "CHAIN_TAIL=$TAIL" | tee -a "$LOG"

echo "=== F-6 步骤 3：verify --expected-hash <链尾>（链外锚；未被篡改必须 exit 0） ===" >> "$LOG"
( cd "$KERNEL" && PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel verify \
    --events "$OUT/kernel-events.jsonl" --pack "$PACK" --expected-hash "$TAIL" ) > "$OUT/verify-2.json" 2>&1
echo "VERIFY_2_EXIT=$?" | tee -a "$LOG"

echo "=== F-6 步骤 4：负对照（链外锚改一位 ⇒ 必须 fail-closed） ===" >> "$LOG"
( cd "$KERNEL" && PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel verify \
    --events "$OUT/kernel-events.jsonl" --pack "$PACK" --expected-hash "${TAIL%?}0" ) > "$OUT/verify-3.json" 2>&1
echo "VERIFY_3_EXIT=$?" | tee -a "$LOG"
grep -o "anchor_mismatch[^\"]*" "$OUT/verify-3.json" | head -2 | tee -a "$LOG"
