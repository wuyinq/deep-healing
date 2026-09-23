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
#  13) R2 新增：标定 registry 零绝对路径（P-9 / 3A-C3）—— 相对路径 + 运行时解析
#  14) R3 新增：三份冻结物的内容锚（工具内锚 == 盘上实算 == registry 登记）—— G6 / Raven R2-M2
#  15) R3 新增：几何判据必须经**应用装配路径**取数（createScene/geometryFor/setReading/assemblyReport）—— G2④
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
PACK_DIR_2="v0_skeleton/districts/xingfu-xiaoqu-north"
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
    if ! awk -v p="$rel" 'index($0, p " | ")==1 {found=1} END{exit !found}' manifest.txt; then
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

# ---------- 7b) 第二街区**必须**进门禁（M3 / 3A-M2 / AC-M3-1d） ----------
# 理由（Raven 预审 M2）：`xingfu-xiaoqu-north` 原先不被任何门禁或测试加载 ⇒
# pack#2 缺 `worldview.json`、或 `pack.sig` 未重签、或 `pack.json` 未登记 `worldview`，门禁**照样全绿**。
if python3 v0_skeleton/tools/verify_pack.py "$PACK_DIR_2"; then
  ok "pack.sig verified for $PACK_DIR_2 (second district is gated)"
else
  bad "pack.sig verification failed for $PACK_DIR_2"
fi
if PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=v0_skeleton/kernel python3 -m deephealing_kernel validate --pack "$PACK_DIR_2" >/dev/null 2>&1; then
  ok "kernel validate --pack $PACK_DIR_2"
else
  bad "kernel validate failed for $PACK_DIR_2"
fi
if PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=v0_skeleton/kernel python3 -m deephealing_kernel validate --pack "$PACK_DIR" >/dev/null 2>&1; then
  ok "kernel validate --pack $PACK_DIR"
else
  bad "kernel validate failed for $PACK_DIR"
fi

# ---------- 7c) 世界观契约（M3 / ADR-016 / AC-M3-8①） ----------
# 两个 pack **各自**必须有 `worldview.json`，且真过 `worldview.schema.json`（引擎 jsonschema）。
WORLDVIEW_MISSING=0
for pack in "$PACK_DIR" "$PACK_DIR_2"; do
  if [ ! -s "$pack/worldview.json" ]; then
    bad "worldview.json missing for $pack (ADR-016 要求每个 pack 都携带)"
    WORLDVIEW_MISSING=$((WORLDVIEW_MISSING + 1))
    continue
  fi
  if python3 v0_skeleton/tools/schema_validate.py worldview.schema.json "$pack/worldview.json" >/dev/null 2>&1; then
    ok "worldview.schema.json validated: $pack/worldview.json"
  else
    bad "worldview.json fails worldview.schema.json: $pack/worldview.json"
  fi
  registered=$(jq -r '.entrypoints.worldview // ""' "$pack/pack.json")
  if [ "$registered" = "worldview.json" ]; then
    ok "pack.entrypoints.worldview registered: $pack"
  else
    bad "pack.entrypoints.worldview not registered (got '$registered'): $pack"
  fi
  # 数值纪律：深层态**不升饱和**；禁止形容词字段由 schema 的 additionalProperties:false 守
  if jq -e '(.tone.underneath.saturation_pct <= .tone.surface.saturation_pct)
            and (.tone.surface.saturation_pct <= 45)
            and (.tone.underneath.light_k < .tone.surface.light_k)' "$pack/worldview.json" >/dev/null 2>&1; then
    ok "worldview two-reading numerics hold: $pack"
  else
    bad "worldview two-reading numerics violated (underneath must be same palette, lower luminance): $pack"
  fi
done
if [ "$WORLDVIEW_MISSING" -eq 0 ]; then ok "every pack carries worldview.json"; fi

# ---------- 7d) narrative_hooks 拆两面（M3 / ADR-016 / AC-M3-8②） ----------
# **加字段不删字段**：旧 `narrative_hooks` 必须在；新增两面必须非空。
NPC_FACE_BAD=0
NPC_FACE_TOTAL=0
while IFS= read -r npc; do
  NPC_FACE_TOTAL=$((NPC_FACE_TOTAL + 1))
  if ! jq -e '(.narrative_hooks | type == "array" and length >= 1)
              and (.healing_face | type == "array" and length >= 1)
              and (.hidden_face | type == "array" and length >= 1)' "$npc" >/dev/null 2>&1; then
    bad "npc missing narrative_hooks / healing_face / hidden_face: $npc"
    NPC_FACE_BAD=$((NPC_FACE_BAD + 1))
  fi
done < <(/usr/bin/find v0_skeleton/districts -path '*/npcs/*.json' -type f | sort)
if [ "$NPC_FACE_BAD" -eq 0 ] && [ "$NPC_FACE_TOTAL" -ge 10 ]; then
  ok "every NPC carries narrative_hooks + healing_face + hidden_face ($NPC_FACE_TOTAL npcs)"
fi

# ---------- 7e) 构建/依赖产物零残渣（M3 / 3A-M3 / AC-M3-1e） ----------
# 理由：`GENERATED_PATTERNS` 把 `*/dist/*`、`*/node_modules/*` 排除在覆盖比对之外 ⇒ 残渣天然不可见。
RESIDUE=$(/usr/bin/find . \( -name node_modules -o -name dist -o -name .build \) | wc -l | tr -d ' ')
if [ "$RESIDUE" -eq 0 ]; then
  ok "no node_modules / dist / .build residue under 02_source"
else
  bad "build/dependency residue found under 02_source (count=$RESIDUE)"
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

# ---------- 12) 标定 registry 零绝对路径（R2 / P-9 / 3A-C3） ----------
# 理由：registry 登记的是**本工作区内**的三份冻结物。写绝对路径会把「某台机器的检出位置」
# 烙进交付产物 —— 换机 / 克隆后 `path` 立即失效，且泄漏本地目录结构。
# 判据：① 所有 `path` 字段都不是绝对路径；② 每条都能**相对 registry 目录**解析到真实文件。
REGISTRY_FILE="$HERE/../spikes/s5-latency-calibration/calibration.registry.json"
if [ ! -f "$REGISTRY_FILE" ]; then
  bad "calibration registry missing: $REGISTRY_FILE"
else
  REG_TOTAL=$(jq -r '[.. | objects | select(has("path")) | .path] | length' "$REGISTRY_FILE" 2>/dev/null || printf '0')
  REG_ABS=$(jq -r '[.. | objects | select(has("path")) | .path | select(startswith("/"))] | length' "$REGISTRY_FILE" 2>/dev/null || printf '1')
  REG_UNRESOLVED=0
  while IFS= read -r reg_path; do
    [ -z "$reg_path" ] && continue
    case "$reg_path" in
      /*) REG_UNRESOLVED=$((REG_UNRESOLVED + 1)) ;;
      *) if [ ! -f "$(dirname "$REGISTRY_FILE")/$reg_path" ]; then REG_UNRESOLVED=$((REG_UNRESOLVED + 1)); fi ;;
    esac
  done < <(jq -r '.. | objects | select(has("path")) | .path' "$REGISTRY_FILE" 2>/dev/null)
  if [ "${REG_ABS:-1}" = "0" ] && [ "${REG_TOTAL:-0}" -ge 3 ] && [ "$REG_UNRESOLVED" -eq 0 ]; then
    ok "calibration registry: 0 absolute paths, $REG_TOTAL relative paths all resolvable"
  else
    bad "calibration registry path format (absolute=$REG_ABS total=$REG_TOTAL unresolved=$REG_UNRESOLVED)"
  fi
fi

# ---------- 12b) 三份冻结物的内容锚：工具内锚 == 盘上实算 == registry 登记（R3 / G6） ----------
# 理由（Raven r2 R2-M2）：`registry` 登记三份冻结物的 sha256，但 `ENVIRONMENT-CLASS.frozen.md`
# 此前**没有**硬编码锚 ⇒ 篡改它后跑**普通** `registry` 会静默把新摘要写进 registry（exit 0）。
# 判据：① 工具内三条锚 == 盘上文件实算；② registry 里登记的三条 sha256 == 盘上实算。
sha256_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else printf ''
  fi
}
ANCHOR_TOOL="v0_skeleton/kernel/tools/calibrate_latency.py"
if [ ! -f "$ANCHOR_TOOL" ]; then
  bad "calibration anchor tool missing: $ANCHOR_TOOL"
else
  S5_DIR="$(cd "$(dirname "$REGISTRY_FILE")" && pwd)"
  ANCHOR_MISMATCH=0
  REG_MISMATCH=0
  for pair in "FROZEN_RULE_SHA256:DERIVATION-RULE.frozen.md:frozen_rule" \
              "FROZEN_RANGE_SHA256:ACCEPTED-DEGRADATION-RANGE.frozen.md:accepted_degradation_range" \
              "FROZEN_ENVCLASS_SHA256:ENVIRONMENT-CLASS.frozen.md:environment_class_rule"; do
    ANCHOR_NAME="${pair%%:*}"
    REST="${pair#*:}"
    FILE_NAME="${REST%%:*}"
    REG_KEY="${REST#*:}"
    TOOL_SHA=$(awk -F'"' -v n="$ANCHOR_NAME" '$0 ~ ("^" n " = ") {print $2; exit}' "$ANCHOR_TOOL")
    DISK_SHA=$(sha256_of "$S5_DIR/$FILE_NAME")
    REG_SHA=$(jq -r --arg k "$REG_KEY" '.[$k].sha256' "$REGISTRY_FILE" 2>/dev/null || printf '')
    if [ -z "$TOOL_SHA" ] || [ "$TOOL_SHA" != "$DISK_SHA" ]; then ANCHOR_MISMATCH=$((ANCHOR_MISMATCH + 1)); fi
    if [ -z "$REG_SHA" ] || [ "$REG_SHA" != "$DISK_SHA" ]; then REG_MISMATCH=$((REG_MISMATCH + 1)); fi
  done
  if [ "$ANCHOR_MISMATCH" -eq 0 ] && [ "$REG_MISMATCH" -eq 0 ]; then
    ok "calibration frozen anchors: 3/3 (tool anchor == on-disk sha256 == registry entry)"
  else
    bad "calibration frozen anchors (tool!=disk:$ANCHOR_MISMATCH registry!=disk:$REG_MISMATCH)"
  fi
fi

# ---------- 12c) 几何判据必须经**应用装配路径**取数（R3 / G2④） ----------
# 理由（Raven r2 R2-C1）：判据此前只打自由函数 `buildEntityBoxes/geometryReport`，从不经过
# `createScene()` 的 `setReading/geometryFor/assemblyReport` ⇒ 装配路径上的 D-7 违规无判据。
SCENE_ASSERT="v0_skeleton/web/scripts/scene_assert.mjs"
if [ ! -f "$SCENE_ASSERT" ]; then
  bad "scene_assert missing: $SCENE_ASSERT"
else
  SA_CREATE=$(grep -c 'createScene' "$SCENE_ASSERT" || true)
  SA_GEOMFOR=$(grep -c 'geometryFor' "$SCENE_ASSERT" || true)
  SA_SETREAD=$(grep -c 'setReading' "$SCENE_ASSERT" || true)
  SA_ASM=$(grep -c 'assemblyReport' "$SCENE_ASSERT" || true)
  if [ "${SA_CREATE:-0}" -ge 1 ] && [ "${SA_GEOMFOR:-0}" -ge 1 ] && [ "${SA_SETREAD:-0}" -ge 1 ] && [ "${SA_ASM:-0}" -ge 1 ]; then
    ok "scene_assert drives the application assembly path (createScene=$SA_CREATE geometryFor=$SA_GEOMFOR setReading=$SA_SETREAD assemblyReport=$SA_ASM)"
  else
    bad "scene_assert does not reference the assembly path (createScene=$SA_CREATE geometryFor=$SA_GEOMFOR setReading=$SA_SETREAD assemblyReport=$SA_ASM)"
  fi
fi

# ---------- 13) IP 边界扫描（R2 / F12） ----------
# 理由（Raven M3 观察）：R1 的 IP 探针只活在 `/tmp`，交付树里**没有判据载体** ——
# 唯一命中是 schema `$comment` 的**自命中**（那条 $comment 自己逐字列了 IP 禁令词）。
# 现在：扫描器 + 白名单（逐条给理由）进交付树，并用 `--probe` 自证**命中能力**。
if python3 v0_skeleton/tools/scan_ip_boundary.py --root . >/dev/null; then
  ok "IP boundary scan clean (0 unwhitelisted hits)"
else
  bad "IP boundary scan found unwhitelisted hits"
fi
if python3 v0_skeleton/tools/scan_ip_boundary.py --root . --probe >/dev/null; then
  ok "IP boundary scanner self-proof holds (probe detected + removal restores baseline)"
else
  bad "IP boundary scanner self-proof failed (scanner may be a zero-hit green command)"
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
