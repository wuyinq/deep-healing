#!/bin/bash
# M4 观测层真跑 spike（AC-M4-2 / AC-8）：run → replay 检查点 → 只读分析 → 负例断链。
#
# 运行：bash spikes/s14-observability/run_observability.sh
# 产物：spikes/s14-observability/logs/*
# **本脚本不是交付面**（spikes/**）；它只调用交付实现。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
WS="$(cd "$HERE/../.." && pwd)"
KERNEL="$WS/02_source/v0_skeleton/kernel"
PACK="$WS/02_source/v0_skeleton/districts/xingfu-xiaoqu"
LOGS="$HERE/logs"
RUNTIME="$HERE/runtime"
mkdir -p "$LOGS" "$RUNTIME"

export PYTHONDONTWRITEBYTECODE=1
cd "$KERNEL" || exit 2

echo "=== 1) run（300 tick / snapshot_every 50 / --ws-port 0）===" | tee "$LOGS/spike.log"
python3 -m deephealing_kernel run --ws-port 0 --pack "$PACK" --seed 20260921 \
  --events "$RUNTIME/run/events.jsonl" --snapshot-every 50 --ticks 300 \
  > "$LOGS/run.json" 2> "$LOGS/run.err"
echo "run_exit=$?" | tee -a "$LOGS/spike.log"
cat "$LOGS/run.json" | tee -a "$LOGS/spike.log"

echo "=== 2) replay --checkpoint-every 50（检查点数必须 == ticks/snapshot_every）===" | tee -a "$LOGS/spike.log"
python3 -m deephealing_kernel replay --events "$RUNTIME/run/events.jsonl" --pack "$PACK" \
  --checkpoint-every 50 --out "$RUNTIME/replay" > "$LOGS/replay.json" 2> "$LOGS/replay.err"
echo "replay_exit=$?" | tee -a "$LOGS/spike.log"
cat "$LOGS/replay.json" | tee -a "$LOGS/spike.log"
ls "$RUNTIME/replay/checkpoints" | tee "$LOGS/replay-checkpoints.txt"
echo "checkpoint_count=$(ls "$RUNTIME/replay/checkpoints" | wc -l | tr -d ' ')" | tee -a "$LOGS/spike.log"

echo "=== 2b) 负例：--checkpoint-every 100 ⇒ 同一谓词必须变假 ===" | tee -a "$LOGS/spike.log"
python3 -m deephealing_kernel replay --events "$RUNTIME/run/events.jsonl" --pack "$PACK" \
  --checkpoint-every 100 --out "$RUNTIME/replay-other" > "$LOGS/replay-other.json" 2>&1
echo "checkpoint_count_other=$(ls "$RUNTIME/replay-other/checkpoints" | wc -l | tr -d ' ')" | tee -a "$LOGS/spike.log"

echo "=== 3) 只读分析（分析前后逐字节 sha256 比对）===" | tee -a "$LOGS/spike.log"
shasum -a 256 "$RUNTIME/run/events.jsonl" | tee "$LOGS/events-sha-before.txt"
python3 "$KERNEL/tools/observability_report.py" --events "$RUNTIME/run/events.jsonl" \
  --checkpoints "$RUNTIME/replay/checkpoints" --out "$LOGS/observability-report.json"
echo "report_exit=$?" | tee -a "$LOGS/spike.log"
shasum -a 256 "$RUNTIME/run/events.jsonl" | tee "$LOGS/events-sha-after.txt"

echo "=== 3b) duckdb 可用性（如实登记，不假装跑过）===" | tee -a "$LOGS/spike.log"
which duckdb > "$LOGS/duckdb-cli.txt" 2>&1 || echo "duckdb CLI: not found" >> "$LOGS/duckdb-cli.txt"
python3 -m pip install --no-index duckdb > "$LOGS/duckdb-pip-install.txt" 2>&1
echo "pip_install_exit=$?" >> "$LOGS/duckdb-pip-install.txt"
cat "$LOGS/duckdb-cli.txt" | tee -a "$LOGS/spike.log"
tail -3 "$LOGS/duckdb-pip-install.txt" | tee -a "$LOGS/spike.log"

echo "=== 4) 负例：复制日志造一处断链 ⇒ 自检必须非零 ===" | tee -a "$LOGS/spike.log"
python3 - "$RUNTIME/run/events.jsonl" "$RUNTIME/tampered.jsonl" "$LOGS/broken-chain.json" <<'PYEOF'
import json, sys
sys.path.insert(0, sys.argv[0].rsplit('/spikes/', 1)[0] + '/02_source/v0_skeleton/kernel')
from pathlib import Path
source, target, report_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
lines = source.read_text(encoding="utf-8").splitlines()
doc = json.loads(lines[10])
doc["prev_hash"] = "f" * 64
lines[10] = json.dumps(doc, ensure_ascii=False, sort_keys=True)
target.write_text("\n".join(lines) + "\n", encoding="utf-8")
from tools.observability_report import analyze
clean = analyze(source)["hash_chain"]["broken_links"]
broken = analyze(target)["hash_chain"]["broken_links"]
report_path.write_text(json.dumps({"clean_broken_links": clean, "tampered_broken_links": broken,
                                   "criterion": "断链 ⇒ 自检必须非零", "passed": broken > 0},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"clean={clean} tampered={broken}")
PYEOF
echo "SPIKE_S14_DONE" | tee -a "$LOGS/spike.log"
