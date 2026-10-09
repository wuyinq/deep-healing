#!/usr/bin/env bash
# `AC-C-2c` 负对照（持久层按 npc_id 敏感）· `AC-A-2e` 运行期绑定读回。
# 目标 run 目录：C-1 的产物（`<run_out>/kernel_memory.sqlite` + 事件链）。
set -u
WS="/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/_worktrees/n5c-evidence-20260924"
RUNOUT="$WS/v0/spikes/n5c-evidence/runtime/c1c2/out"
DB="$RUNOUT/kernel_memory.sqlite"
EVENTS="$RUNOUT/kernel-events-c1c2.jsonl"
OUT="$WS/v0/spikes/n5c-evidence/readback/c2c-negative-control.json"
TARGET="npc-006"
OTHER="npc-001"   # 交付面 intervene 控件里**写死**的委托对象（实测 `intervention.ts` 的 `submitDelegateInstruction('npc-001', …)`）
LOG="$WS/v0/spikes/n5c-evidence/readback/c2c-negative-control.log"
: > "$LOG"

{
  echo "=== C-2a 正读数（按目标 npc_id 过滤） ==="
  sqlite3 "$DB" "select npc_id, count(*) from episodes group by npc_id;"
  echo "=== C-2a 负对照（换另一个 npc_id ⇒ 必须 0 条） ==="
  sqlite3 "$DB" "select count(*) from episodes where npc_id = '$OTHER';"
  echo "=== C-2b 事件链 actor / payload.npc_id 集合 ==="
} >> "$LOG" 2>&1

TARGET_COUNT=$(sqlite3 "$DB" "select count(*) from episodes where npc_id = '$TARGET';")
OTHER_COUNT=$(sqlite3 "$DB" "select count(*) from episodes where npc_id = '$OTHER';")
EVENT_SET=$(python3 - "$EVENTS" <<'PY'
import json,sys
actors=set(); npcids=set(); kinds=set()
EXPERIENCE={'memory.written','npc.decision','npc.action','intent.applied','intent.rejected'}
for line in open(sys.argv[1],encoding='utf-8'):
    line=line.strip()
    if not line: continue
    obj=json.loads(line)
    t=obj.get('type') or obj.get('kind')
    actor=obj.get('actor')
    if t in EXPERIENCE:
        kinds.add(t)
        if actor and actor!='kernel': actors.add(actor)
        p=obj.get('payload') or {}
        nid=p.get('npc_id')
        if isinstance(nid,str): npcids.add(nid)
print(json.dumps({'actors':sorted(actors),'payload_npc_ids':sorted(npcids),
                  'experience_event_types':sorted(kinds)},ensure_ascii=False))
PY
)
echo "EVENT_SET=$EVENT_SET" >> "$LOG"

python3 - "$OUT" "$TARGET" "$TARGET_COUNT" "$OTHER_COUNT" "$EVENT_SET" "$DB" "$EVENTS" <<'PY'
import json,sys
out,target,tc,oc,evset,db,events=sys.argv[1:8]
ev=json.loads(evset)
actors=set(ev['actors']); npcids=set(ev['payload_npc_ids'])
reading={
 'task':'c2c-negative-control',
 'db':db,'events':events,
 'C-2a':{'target_npc_id':target,'target_rows':int(tc),
         'other_npc_id':'npc-001','other_rows':int(oc),
         'pass':int(tc)>0 and int(oc)==0,
         'note':'换一个 npc_id 过滤 ⇒ 0 条（判据对 id 敏感，不是恒真）'},
 'C-2b':{'scope':'仅「经历相关」事件类型',
         'experience_event_types':ev['experience_event_types'],
         'npc_scoped_actors':sorted(actors),'payload_npc_ids':sorted(npcids),
         'expected_set':[target],
         'pass':npcids=={target} and actors<= {target},
         'note':'非 npc 作用域的 actor（world / session:*）不属「该经历相关事件」；npc 作用域集合必须恰为一个'},
 'C-2b-classified':{
   'npc_scoped':sorted(a for a in actors if not a.startswith('session:') and a!='world'),
   'non_npc_scoped':sorted(a for a in actors if a.startswith('session:') or a=='world'),
   'requirement':'npc 作用域集合 == {目标 npc id}（恰一个）；非 npc 作用域（session:*/world）不计入',
   'pass':sorted(a for a in actors if not a.startswith('session:') and a!='world')==[target] and npcids=={target}},
}
json.dump(reading,open(out,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps({'C-2a':reading['C-2a']['pass'],'C-2b':reading['C-2b']['pass'],
                  'target_rows':int(tc),'other_rows':int(oc),
                  'npc_scoped_actors':sorted(actors),'npcids':sorted(npcids)},ensure_ascii=False))
PY
