#!/usr/bin/env bash
# AC-F-6（回放 run↔replay 逐点一致）· AC-F-7（审计/回放路径不得改写源）· AC-F-1 佐证。
# 用 C-1 真会话产出的内核事件日志做**链外锚 + 重放比对**；跑前/跑后对交付树做全量 sha256。
set -u
WS="/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/_worktrees/n5c-evidence-20260924"
SRC="$WS/v0/02_source/v0_skeleton"
PACK="$SRC/districts/xingfu-xiaoqu-xuqin"
OUTDIR="$WS/v0/spikes/n5c-evidence/readback"
RUNOUT="$WS/v0/spikes/n5c-evidence/runtime/c1c2/out"
EVENTS="$RUNOUT/kernel-events-c1c2.jsonl"
LOG="$OUTDIR/f-replay-n5c.log"
: > "$LOG"

hash_tree() {  # 全量 sha256（相对路径排序）
  ( cd "$1" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 )
}
{
  echo "=== F-7 跑前交付树哈希 ==="
  hash_tree "$WS/v0/02_source" | shasum -a 256
  echo "files=$(hash_tree "$WS/v0/02_source" | wc -l | tr -d ' ')"
} >> "$LOG" 2>&1
BEFORE=$(hash_tree "$WS/v0/02_source" | shasum -a 256 | awk '{print $1}')
echo "BEFORE=$BEFORE"

{
  echo
  echo "=== F-6 链尾锚（run 侧） ==="
  tail -1 "$EVENTS" | head -c 400
  echo
  echo "=== F-6 verify（重放 + 逐检查点比对 state_hash + 链外锚） ==="
} >> "$LOG"
CHAIN_TAIL=$(python3 - "$EVENTS" <<'PY'
import json,sys
last=None
for line in open(sys.argv[1],encoding='utf-8'):
    line=line.strip()
    if line: last=line
obj=json.loads(last)
payload=obj.get('payload') or {}
print(payload.get('chain_hash') or payload.get('event_chain_hash') or obj.get('chain_hash') or '')
PY
)
echo "CHAIN_TAIL=$CHAIN_TAIL" | tee -a "$LOG"
( cd "$SRC/kernel" && PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel verify \
    --events "$EVENTS" --pack "$PACK" ${CHAIN_TAIL:+--expected-hash "$CHAIN_TAIL"} ) >> "$LOG" 2>&1
echo "VERIFY_EXIT=$?" | tee -a "$LOG"

{
  echo
  echo "=== F-6 replay（从 genesis 重放，逐检查点） ==="
} >> "$LOG"
( cd "$SRC/kernel" && PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel replay \
    --events "$EVENTS" --pack "$PACK" --out /tmp/n5c-replay-out --checkpoint-every 1 ) >> "$LOG" 2>&1
echo "REPLAY_EXIT=$?" | tee -a "$LOG"

{
  echo
  echo "=== F-6 replay 产物 ==="
  ls -la /tmp/n5c-replay-out 2>/dev/null | head
} >> "$LOG" 2>&1
python3 - "$EVENTS" /tmp/n5c-replay-out "$OUTDIR/f6-compare-n5c.json" <<'PY' >> "$LOG" 2>&1
import json,sys,os
events,replay_out,out = sys.argv[1],sys.argv[2],sys.argv[3]
def load(path):
    rows=[]
    if not os.path.exists(path): return rows
    for line in open(path,encoding='utf-8'):
        line=line.strip()
        if line: rows.append(json.loads(line))
    return rows
run=[r for r in load(events) if r.get('kind')=='tick' or r.get('type')=='tick' or 'tick' in r]
rep=load(os.path.join(replay_out,'kernel-events.jsonl')) if os.path.exists(os.path.join(replay_out,'kernel-events.jsonl')) else []
def triple(rows):
    out={}
    for r in rows:
        t=r.get('tick')
        if t is None: continue
        p=r.get('payload') or {}
        out[t]=(r.get('event_chain_hash') or p.get('event_chain_hash'), p.get('state_hash') or r.get('state_hash'))
    return out
a,b=triple(run),triple(rep)
common=sorted(set(a)&set(b))
mismatch=[t for t in common if a[t]!=b[t]]
json.dump({'run_ticks':len(a),'replay_ticks':len(b),'common_ticks':len(common),
           'mismatch_ticks':mismatch[:20],'mismatch_count':len(mismatch),
           'tick_sets_equal':set(a)==set(b),'three_fields_pointwise_equal':len(mismatch)==0},
          open(out,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(open(out,encoding='utf-8').read())
PY

{
  echo
  echo "=== F-7 跑后交付树哈希 ==="
  hash_tree "$WS/v0/02_source" | shasum -a 256
} >> "$LOG" 2>&1
AFTER=$(hash_tree "$WS/v0/02_source" | shasum -a 256 | awk '{print $1}')
echo "AFTER=$AFTER"
if [ "$BEFORE" = "$AFTER" ]; then echo "F7_SOURCE_UNCHANGED=true" | tee -a "$LOG"; else echo "F7_SOURCE_UNCHANGED=false" | tee -a "$LOG"; fi
echo "BEFORE=$BEFORE" >> "$LOG"; echo "AFTER=$AFTER" >> "$LOG"
