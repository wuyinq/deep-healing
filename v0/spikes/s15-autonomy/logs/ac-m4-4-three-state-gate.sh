#!/bin/bash
# AC-M4-4 三态判据门（可复核）：交付面 / providers.remote_api 注入 / urllib 注入
# 用法：bash m4r2_ac44_gate.sh   （只读交付面；注入一律在 /tmp 隔离镜像里）
set -u
WS=/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-006-deephealing-v0-m4
K="$WS/02_source/v0_skeleton/kernel"
BASE=/tmp/m4r2_ac44
TOKENS='requests|httpx|openai|urllib|socket\.'

echo "=== [0] 交付面整树摘要（注入前后必须逐位相同）==="
before=$(cd "$WS" && find 02_source -type f -exec shasum -a 256 {} + | sort | shasum -a 256)
echo "delivery_tree_digest_before=$before"

echo
echo "=== [1] 隔离镜像（镜像 02_source 根，路径算术依赖它）==="
rm -rf "$BASE"
mkdir -p "$BASE"
cp -R "$WS/02_source" "$BASE/clean"
cp -R "$BASE/clean" "$BASE/inj-remote"
cp -R "$BASE/clean" "$BASE/inj-urllib"
ls "$BASE"
echo "mirror_roots=$(ls "$BASE" | tr '\n' ' ')"

echo
echo "=== [2] 注入 A：providers.remote_api（项目自身模型出口）==="
python3 "$(dirname "$0")/ac-m4-4-inject-remote.py" "$BASE/inj-remote/v0_skeleton/kernel/deephealing_kernel/rules/decision.py" || exit 9
grep -n "providers" "$BASE/inj-remote/v0_skeleton/kernel/deephealing_kernel/rules/decision.py" | head -5

echo
echo "=== [3] 注入 B：urllib（对照，证明判据有命中能力）==="
printf '\nimport urllib.request\n' >> "$BASE/inj-urllib/v0_skeleton/kernel/deephealing_kernel/rules/decision.py"
grep -n "urllib" "$BASE/inj-urllib/v0_skeleton/kernel/deephealing_kernel/rules/decision.py" | head -5

run_state () {
  label="$1"; dir="$2"
  echo "--- state=$label workdir=$dir"
  ( cd "$dir" || exit 9
    echo "\$ rg -n \"$TOKENS\" deephealing_kernel/rules/*.py ; echo exit=\$?"
    rg -n "$TOKENS" deephealing_kernel/rules/*.py
    echo "rg_exit=$?"
    echo "\$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_rules_layer.py -q -p no:cacheprovider ; echo exit=\$?"
    PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_rules_layer.py -q -p no:cacheprovider 2>&1 | tail -12
  )
}

echo
echo "=== [4] state=DELIVERY（真实交付面，未注入）==="
run_state DELIVERY "$K"

echo
echo "=== [5] state=CLEAN-MIRROR（镜像副本，未注入：应与 DELIVERY 同读数）==="
run_state CLEAN-MIRROR "$BASE/clean/v0_skeleton/kernel"

echo
echo "=== [6] state=INJ-REMOTE-API（必须非绿）==="
run_state INJ-REMOTE-API "$BASE/inj-remote/v0_skeleton/kernel"

echo
echo "=== [7] state=INJ-URLLIB（必须非绿）==="
run_state INJ-URLLIB "$BASE/inj-urllib/v0_skeleton/kernel"

echo
echo "=== [8] 交付面摘要复核 ==="
after=$(cd "$WS" && find 02_source -type f -exec shasum -a 256 {} + | sort | shasum -a 256)
echo "delivery_tree_digest_after =$after"
if [ "$before" = "$after" ]; then echo "DELIVERY-FACE: byte-identical (OK)"; else echo "DELIVERY-FACE: CHANGED (FAIL)"; fi

echo
echo "=== [9] 交付面零注入复核 ==="
( cd "$K" && rg -n "MODEL_EGRESS_PROBE|urllib" deephealing_kernel/rules/*.py; echo "clean_exit=$?（1=零命中）" )
