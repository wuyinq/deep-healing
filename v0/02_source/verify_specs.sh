#!/usr/bin/env bash
# verify_specs.sh —— 02_source 交付物的真跑校验（架构冻结轮 / round 3）
#
# 做什么：
#   1) 必需文件存在且非空（交付屏障硬要求，含 round 3 新增契约）
#   2) jq 逐文件解析 02_source/**/*.json（含 v0_skeleton 内全部 JSON）
#   3) manifest.txt 非空，且覆盖 02_source 下每一个文件（除自身）
#      —— **排除规则精确**：只排除「生成残渣」，逐条列明（见 §3 的 GENERATED_PATTERNS）
#   4) 能力文件结构断言（必填字段 + id 与文件名一致 + safety.secrets_in_context=false + calibration + rule_layer_adoption）
#   5) 注册表样例断言（>=3 能力，每个能力声明四类 provider + calibration 块）
#   6) V0 骨架目录完整性（web/ kernel/ districts/xingfu-xiaoqu/ capabilities/ tools/）
#   7) pack.sig 逐文件 sha256 比对（tools/verify_pack.py）
#   8) 治愈系美学数值校验（tools/aesthetic_check.py）
#   9) round 3 新增：provider 类别绑定 + 确定性闸门 + 标定一致性（tools/verify_capability_binding.py）
#  10) round 3 新增：资产包校验（tools/verify_asset_pack.py，含运行时零生成扫描）
#  11) round 3 新增：许可枚举一致性（asset.license.table.json ↔ asset.manifest.schema.json）
#  12) round 3 · 修复迭代 2 新增：能力清单的**真** JSON-Schema 校验 + 自证反例
#      （tools/validate_capability_schema.py，引擎 = jsonschema 库；G3 / Raven N-3）
#
# 退出码：0 全通过；1 有失败项；2 用法/环境错误。
# 用法：bash verify_specs.sh [--quiet]
#
# 复跑纪律（R2-3）：跑 pytest 一律 `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider`，
#   避免在交付树里留下 `__pycache__` / `.pytest_cache`（否则本脚本的覆盖检查会红）。

set -u

# 复跑纪律（R2-3）：不在交付树里留字节码。
# round 3 · 修复迭代 2：校验器改为 import 同目录模块（schema_validate），故本脚本也显式禁止
# 写 `__pycache__`（`02_source/**` 是冻结面，虽已排除生成残渣，仍不给漂移留口子）。
export PYTHONDONTWRITEBYTECODE=1

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE" || exit 2

QUIET=0
if [ "${1:-}" = "--quiet" ]; then QUIET=1; fi

FAIL=0
PASS=0
SKIP=0

say() { if [ "$QUIET" -eq 0 ]; then printf '%s\n' "$*"; fi; }
ok()   { PASS=$((PASS + 1)); say "PASS  $*"; }
bad()  { FAIL=$((FAIL + 1)); printf 'FAIL  %s\n' "$*"; }
skip() { SKIP=$((SKIP + 1)); say "SKIP  $*"; }

for tool in jq python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'ENV   missing required tool: %s\n' "$tool" >&2
    exit 2
  fi
done

PACK_DIR="v0_skeleton/districts/xingfu-xiaoqu"
ASSET_SAMPLE="v0_skeleton/assets-sample"

# ---------- 1) 必需文件 ----------
REQUIRED_FILES="
manifest.txt
world.schema.json
events.schema.json
snapshot.schema.json
capability.schema.json
capability.registry.sample.json
capability.time-budget.spec.md
cassette.schema.json
cassette.format.md
session.protocol.schema.json
district.pack.schema.json
district.pack.spec.md
intervention.policy.schema.json
worldmodel.adapter.spec.md
asset.manifest.schema.json
asset.license.table.json
asset.license.table.data.json
art-bible.md
content-pipeline.spec.md
verify_specs.sh
$PACK_DIR/pack.json
$PACK_DIR/pack.sig
$PACK_DIR/world.seed.json
$PACK_DIR/assets/manifest.json
$ASSET_SAMPLE/placeholder-001.png
$ASSET_SAMPLE/asset.manifest.sample.json
$ASSET_SAMPLE/workflows/procedural-placeholder.json
v0_skeleton/capabilities/imagine.predict@1.0.0.capability.json
v0_skeleton/tools/verify_asset_pack.py
v0_skeleton/tools/verify_capability_binding.py
v0_skeleton/tools/make_placeholder_asset.py
v0_skeleton/tools/schema_validate.py
v0_skeleton/tools/validate_capability_schema.py
v0_skeleton/tools/determinism_probe_worker.py
v0_skeleton/kernel/deephealing_kernel/adapters/__init__.py
v0_skeleton/kernel/deephealing_kernel/adapters/determinism_probe.py
"

for f in $REQUIRED_FILES; do
  if [ -s "$f" ]; then
    ok "required file present and non-empty: $f"
  else
    bad "required file missing or empty: $f"
  fi
done

# ---------- 2) jq 逐文件解析 ----------
JSON_COUNT=0
while IFS= read -r f; do
  JSON_COUNT=$((JSON_COUNT + 1))
  if jq . "$f" >/dev/null 2>/tmp/verify_specs_jq_err.$$; then
    ok "jq parse: $f"
  else
    bad "jq parse failed: $f ($(tr -d '\n' < /tmp/verify_specs_jq_err.$$ | cut -c1-160))"
  fi
done < <(find . -name '*.json' -type f | sort)
rm -f /tmp/verify_specs_jq_err.$$
if [ "$JSON_COUNT" -eq 0 ]; then bad "no JSON files found under 02_source"; fi
say "INFO  jq checked $JSON_COUNT JSON files"

# ---------- 3) manifest 覆盖（排除规则精确，逐条列明） ----------
# 只排除「**生成残渣**」（构建/测试/缓存产物），**不排除任何真实交付文件**。
# 逐条模式与理由：
#   */__pycache__/*   Python 字节码目录（pytest/import 生成）
#   *.pyc             Python 字节码文件
#   */.pytest_cache/* pytest 缓存目录
#   */.DS_Store       macOS Finder 元数据
#   */node_modules/*  npm 依赖目录（若 spike 依赖被误拷入）
#   */.venv/*         Python 虚拟环境
#   */dist/*          前端构建产物
#   attic-*/*         归档残渣（历史产物，保留但不进交付清单）
GENERATED_PATTERNS=(
  '*/__pycache__/*'
  '*.pyc'
  '*/.pytest_cache/*'
  '*/.DS_Store'
  '*/node_modules/*'
  '*/.venv/*'
  '*/dist/*'
  'attic-*/*'
)
is_generated() {
  local rel="$1" pattern
  for pattern in "${GENERATED_PATTERNS[@]}"; do
    # shellcheck disable=SC2053
    if [[ "$rel" == $pattern ]]; then return 0; fi
  done
  return 1
}

if [ -s manifest.txt ]; then
  ok "manifest.txt non-empty ($(wc -l < manifest.txt | tr -d ' ') lines)"
  BAD_FIELDS=0
  while IFS= read -r line; do
    # 三字段格式断言：恰好 2 个 '|' 且两侧都是空格（字段值内不含 '|'）
    pipes=$(printf '%s' "$line" | tr -cd '|' | wc -c | tr -d ' ')
    if [ "$pipes" -ne 2 ] || ! printf '%s' "$line" | grep -q -F ' | '; then
      bad "manifest line does not have 3 ' | ' separated fields: $line"
      BAD_FIELDS=$((BAD_FIELDS + 1))
    fi
  done < manifest.txt
  if [ "$BAD_FIELDS" -eq 0 ]; then ok "manifest.txt: every line has 3 fields (path | 用途 | 生成方式)"; fi

  MISSING=0
  EXCLUDED=0
  while IFS= read -r f; do
    rel=${f#./}
    if [ "$rel" = "manifest.txt" ]; then continue; fi
    if is_generated "$rel"; then
      EXCLUDED=$((EXCLUDED + 1))
      continue
    fi
    if ! grep -q -F "$rel | " manifest.txt; then
      bad "manifest.txt does not cover file: $rel"
      MISSING=$((MISSING + 1))
    fi
  done < <(find . -type f | sort)
  if [ "$MISSING" -eq 0 ]; then
    ok "manifest.txt covers every non-generated file under 02_source (excluded generated files: $EXCLUDED)"
  fi
else
  bad "manifest.txt missing or empty"
fi

# ---------- 4) 能力文件结构断言 ----------
CAP_COUNT=0
for f in v0_skeleton/capabilities/*.capability.json; do
  if [ ! -f "$f" ]; then continue; fi
  CAP_COUNT=$((CAP_COUNT + 1))
  missing=$(jq -r '
    ["id","version","slot","input_schema","output_schema","providers","cost",
     "latency_ms_budget","timeout_ms","fallback","determinism","safety","calibration","rule_layer_adoption"]
    | map(select(. as $k | ($doc | has($k)) | not)) | join(",")
  ' --argjson doc "$(jq -c . "$f")" "$f" 2>/dev/null)
  if [ -n "$missing" ]; then
    bad "capability missing required fields ($missing): $f"
    continue
  fi
  cap_id=$(jq -r '.id' "$f")
  base=$(basename "$f")
  case "$base" in
    "$cap_id"@*.capability.json) : ;;
    *) bad "capability id does not match filename: id=$cap_id file=$base"; continue ;;
  esac
  secrets=$(jq -r '.safety.secrets_in_context' "$f")
  if [ "$secrets" != "false" ]; then
    bad "capability safety.secrets_in_context must be false: $f"
    continue
  fi
  # provider 类别面（round 3 · 修复迭代 1 / RR3-3 裁决）：`slot ∈ imagine.*` 的能力，其**所有**
  # provider 必须是 remote_api（不可自声明的锚，与 `01 §16.1.1②` 一致）；其余槽位必须四类齐全。
  slot=$(jq -r '.slot' "$f")
  prov_classes=$(jq -r '[.providers[].class] | sort | join(",")' "$f")
  case "$slot" in
    imagine.*)
      if [ "$prov_classes" != "remote_api" ]; then
        bad "imagine.* capability must declare remote_api providers only: $f (slot=$slot got $prov_classes)"
        continue
      fi
      ;;
    *)
      if [ "$prov_classes" != "cassette_replay,deterministic_rule,local_model,remote_api" ]; then
        bad "capability must declare all four provider classes: $f (got $prov_classes)"
        continue
      fi
      ;;
  esac
  key_missing=""
  for kf in capability_id capability_version canonical_input_hash provider; do
    if ! jq -e --arg kf "$kf" '.determinism.cassette_key_fields | index($kf) != null' "$f" >/dev/null 2>&1; then
      key_missing="$key_missing $kf"
    fi
  done
  if [ -n "$key_missing" ]; then
    bad "cassette_key_fields missing required field(s):$key_missing in $f"
    continue
  fi
  # round 3：声明值必须 ≥ p95 且 ≠ max（防自证），且附实测依据
  if ! jq -e '(.timeout_ms >= .calibration.p95_ms) and (.timeout_ms != .calibration.max_ms)
              and (.latency_ms_budget >= .calibration.p90_ms)
              and ((.calibration.derivation_rule_sha256 | length) == 64)
              and (.calibration.sample_count >= 20)' "$f" >/dev/null 2>&1; then
    bad "capability calibration assertions failed (timeout>=p95, timeout!=max, budget>=p90, rule sha256, sample>=20): $f"
    continue
  fi
  ok "capability OK: $cap_id@$(jq -r '.version' "$f") providers=$(jq -r '[.providers[]] | length' "$f") calibrated=yes"
done
if [ "$CAP_COUNT" -lt 3 ]; then bad "expected >=3 capability files, found $CAP_COUNT"; fi

# ---------- 5) 注册表样例断言 ----------
if jq -e '.capabilities | length >= 3' capability.registry.sample.json >/dev/null 2>&1; then
  ok "registry sample declares >=3 capabilities"
else
  bad "registry sample must declare >=3 capabilities"
fi
REG_BAD=0
while IFS= read -r cap; do
  classes=$(printf '%s' "$cap" | jq -r '[.providers[].class] | sort | join(",")')
  if [ "$classes" != "cassette_replay,deterministic_rule,local_model,remote_api" ]; then
    bad "registry capability lacks four provider classes: $(printf '%s' "$cap" | jq -r '.id')"
    REG_BAD=$((REG_BAD + 1))
  fi
  if ! printf '%s' "$cap" | jq -e '(.timeout_ms >= .calibration.p95_ms) and (.timeout_ms != .calibration.max_ms)' >/dev/null 2>&1; then
    bad "registry capability calibration assertions failed: $(printf '%s' "$cap" | jq -r '.id')"
    REG_BAD=$((REG_BAD + 1))
  fi
done < <(jq -c '.capabilities[]' capability.registry.sample.json)
if [ "$REG_BAD" -eq 0 ]; then ok "registry sample: every capability has four provider classes + calibrated declared values"; fi

# ---------- 6) V0 骨架目录 ----------
for d in v0_skeleton/web v0_skeleton/kernel v0_skeleton/districts/xingfu-xiaoqu v0_skeleton/capabilities v0_skeleton/tools; do
  if [ -d "$d" ]; then ok "skeleton dir exists: $d"; else bad "skeleton dir missing: $d"; fi
done

# ---------- 7) pack.sig 逐文件比对 ----------
if python3 v0_skeleton/tools/verify_pack.py "$PACK_DIR"; then
  ok "pack.sig verified for $PACK_DIR"
else
  bad "pack.sig verification failed for $PACK_DIR"
fi

# ---------- 8) 美学数值校验 ----------
if python3 v0_skeleton/tools/aesthetic_check.py "$PACK_DIR/assets/manifest.json"; then
  ok "aesthetic constraints satisfied"
else
  bad "aesthetic constraints violated"
fi

# ---------- 9) provider 类别绑定 + 确定性闸门 + 标定一致性（round 3） ----------
if python3 v0_skeleton/tools/verify_capability_binding.py --cap-dir v0_skeleton/capabilities --schema capability.schema.json; then
  ok "capability binding verified (world-model class binding + determinism gate + calibration)"
else
  bad "capability binding verification failed"
fi

# ---------- 9b) 能力清单的**真** JSON-Schema 校验 + 自证反例（round 3 · 修复迭代 2 / G3） ----------
# 此前 schema 只被当作「白名单来源」传给校验器，additionalProperties:false / required / enum
# 从未被真正执行（Raven N-3）。这一步把 schema 变成**可执行判据**。
if python3 v0_skeleton/tools/validate_capability_schema.py --schema capability.schema.json \
     --cap-dir v0_skeleton/capabilities; then
  ok "capability manifests pass the real JSON-Schema validation (engine = jsonschema)"
else
  bad "capability manifest JSON-Schema validation failed"
fi
if python3 v0_skeleton/tools/validate_capability_schema.py --schema capability.schema.json \
     --cap-dir v0_skeleton/capabilities --selftest; then
  ok "schema validator self-proof holds (valid baseline green + 4 invalid red + sampling-legal green)"
else
  bad "schema validator self-proof failed (validator may be a zero-hit green command)"
fi

# ---------- 10) 资产包校验 + 运行时零生成（round 3） ----------
if python3 v0_skeleton/tools/verify_asset_pack.py --pack "$ASSET_SAMPLE" --manifest "$ASSET_SAMPLE/asset.manifest.sample.json" \
     --license-table asset.license.table.data.json --runtime-tree v0_skeleton; then
  ok "asset pack verified (manifest coverage + license table + content hash + review status + derived_from + metadata)"
else
  bad "asset pack verification failed"
fi
if python3 v0_skeleton/tools/verify_asset_pack.py --zero-generation-scan v0_skeleton; then
  ok "runtime zero-generation scan clean"
else
  bad "runtime zero-generation scan found generation call paths"
fi

# ---------- 11) 许可枚举一致性（round 3，三处必须逐字一致） ----------
TABLE_DATA_ENUM=$(jq -c -S '.license_enum' asset.license.table.data.json)
TABLE_SCHEMA_ENUM=$(jq -c -S '.properties.license_enum.items.enum' asset.license.table.json)
SCHEMA_ENUM=$(jq -c -S '.["$defs"].asset.properties.license.enum' asset.manifest.schema.json)
if [ "$TABLE_DATA_ENUM" = "$SCHEMA_ENUM" ] && [ "$TABLE_SCHEMA_ENUM" = "$SCHEMA_ENUM" ]; then
  ok "license enum identical across asset.license.table.data.json / asset.license.table.json / asset.manifest.schema.json"
else
  bad "license enum mismatch: data=$TABLE_DATA_ENUM table_schema=$TABLE_SCHEMA_ENUM manifest_schema=$SCHEMA_ENUM"
fi

# ---------- 汇总 ----------
say ""
say "verify_specs: PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
if [ "$FAIL" -gt 0 ]; then
  printf 'verify_specs: FAILED (%d failures)\n' "$FAIL"
  exit 1
fi
printf 'verify_specs: OK (%d checks passed, %d skipped)\n' "$PASS" "$SKIP"
exit 0
