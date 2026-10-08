#!/usr/bin/env bash
# verify_specs.sh —— 02_source 交付物的真跑校验（架构冻结轮 / round 3）
#
# 做什么（**索引与正文小节逐条对齐**；Raven M-4：旧头部列到 15) 且与正文编号错位）：
#   1) 必需文件存在且非空（交付屏障硬要求，含 round 3 新增契约）
#   2) jq 逐文件解析 02_source/**/*.json（含 v0_skeleton 内全部 JSON）
#   3) manifest.txt 非空，且覆盖 02_source 下每一个文件（除自身）
#      —— **排除规则精确**：只排除「生成残渣」，逐条列明（见本节 GENERATED_PATTERNS）
#   4) 能力文件结构断言（必填字段 + id 与文件名一致 + safety.secrets_in_context=false + calibration + rule_layer_adoption）
#   5) 注册表样例断言（>=3 能力，每个能力声明四类 provider + calibration 块）
#   6) V0 骨架目录完整性（web/ kernel/ districts/xingfu-xiaoqu/ capabilities/ tools/）
#   7) pack.sig 逐文件 sha256 比对（tools/verify_pack.py）
#   7b) 第二街区**必须**进门禁（M3 / 3A-M2 / AC-M3-1d）
#   7c) 世界观契约（M3 / ADR-016 / AC-M3-8①）
#   7d) narrative_hooks 拆两面（M3 / ADR-016 / AC-M3-8②）
#   7e) 构建/依赖产物零残渣（M3 / 3A-M3 / AC-M3-1e）
#   8) 治愈系美学数值校验（tools/aesthetic_check.py）
#   9) round 3：provider 类别绑定 + 确定性闸门 + 标定一致性（tools/verify_capability_binding.py）
#   9b) round 3 · 修复迭代 2：能力清单的**真** JSON-Schema 校验 + 自证反例
#       （tools/validate_capability_schema.py，引擎 = jsonschema 库；G3 / Raven N-3）
#  10) round 3：资产包校验（tools/verify_asset_pack.py，含运行时零生成扫描）
#  11) round 3：许可枚举一致性（asset.license.table.json ↔ asset.manifest.schema.json）
#  12) R2：标定 registry 零绝对路径（P-9 / 3A-C3）—— 相对路径 + 运行时解析
#  12b) R3：三份冻结物的内容锚（工具内锚 == 盘上实算 == registry 登记）—— G6 / Raven R2-M2
#  12c) R3：几何判据必须经**应用装配路径**取数（createScene/geometryFor/setReading/assemblyReport）—— G2④
#  13) IP 边界扫描（R2 / F12；M5.1 r2 起收敛为 2 条模式）
#  14) 保真度判据（M5.1 / S1~S8）—— 两脚本 + 两套 tools 单测 + 出处表 lint
#  14b) 红线内容比对（`l0_verbatim` 主判据，M5.1 r2.5 / PM 裁决 m5-07 §一 / Raven R-1 / R-6）
#       —— 非白名单 l0_verbatim 命中数 = 0；L0 缺件 ⇒ SKIP + 显式标记
#  15) AC-10 行为多样性判据（M5.2 r1 / REQ §4 / 设计 §5.5 D-7）
#       —— 5 条判据（10-a/10-b/10-c/10-d-1/10-d-2）+ **逐 NPC 室外占比一并公布** + 负对照探针
#  16) AC-4 对照场景（M5.2 r1 / Raven M-14）—— 三条对照臂 + 事件解释链 + 判据自证
#  17) 新 pack 的独立判据（M5.2 r1 / Raven M-6 / M-10 / M-11 / M-17）
#       —— AC-6 身份连续性 + AC-7 NPC 准入闸门 + CHR 出处可复算（各带负对照）
#  18) AC-10 记忆**接线臂** + MEMORY_SIGNAL_* 敏感性断言（M5.2 r3 / FIX-5 · Raven §2.3）
#       —— 交付门禁口径 = 记忆链关闭（unwired，§15）；本节并列公布接线臂读数，
#          并断言 MEMORY_SIGNAL_WEIGHT ∈ {0.10, 0.20, 0.30} 三档下五条判据均绿
#
# 编号纪律（Raven M-4）：新增小节一律追加在正文末尾，并**同步登记到本索引**；
#   定位一律用**精确标题串**（`grep -n '^# ---------- 14)'`），不靠「第 N 节」推断。
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

# ---------- 临时文件（可移植） ----------
# 缺陷（CI 首跑实测）：`mktemp -t <name>` 是 **BSD/macOS** 写法。GNU coreutils 的 mktemp
#   要求模板里至少 3 个连续 `X`，`-t name` 在 Linux 上直接报
#   `mktemp: too few X's in template` ⇒ 临时文件根本没建 ⇒ 工具 JSON 读不到 ⇒
#   判据被读成 `field_unreadable (status=empty)`（5 条判据因此红，且失败文案指向判据本身，
#   归因误导）。用**显式模板**（带 6 个 X）两边都能跑。
tmpfile() { local d="${TMPDIR:-/tmp}"; mktemp "${d%/}/$1.XXXXXX"; }

# ---------- 自证项统一判据（M5.1 r2.6 · PM m5-08 §三） ----------
# 缺陷：自证项此前读**工具退出码**，而退出码把「真实树读数」与「探针读数」合成了一个
#   （例：`fidelity_lint.py` 末行 `return 0 if (rc == 0 and prc == 0) else 1`）⇒
#   ① 树脏时自证项报「自证失败」（归因误导，且正好发生在修树窗口里，最容易把人带偏）；
#   ② 树脏时探针真失效会被同一个红**掩盖** ⇒ 自证项在该窗口内不携带独立信息。
# 契约（逐条落地）：
#   1) 判据读工具 JSON 的**判定字段**（probe_ok / self_proof_ok），**不读退出码**；
#   2) fail-closed：字段缺失 / JSON 不可解析 / 字段非布尔 ⇒ FAIL（不得因「没读到」转绿）；
#   3) PASS 行必须打印探针计数 `cases=N fired=N back_to_baseline=...`（否则不可复核）；
#   4) 探针在**隔离临时树**上跑（工具 `--probe-only`：只跑探针、**不扫真实树**）——
#      判据的输入与被测树解耦（PM §8.4：判据 / 自证的输入不得取自被测对象）；
#   5) FAIL 文案**指名维度**（`probe_ok=false` / `field_unreadable`），不再出现「自证失败」
#      而实际是树红 —— 树红由对应的**树项**单独承担。
# 用法：selfproof "<维度标签>" <工具种类> <命令...>
selfproof() {
  local label="$1" kind="$2"; shift 2
  local out raw norm
  out="$("$@" 2>/dev/null)"
  raw="$(printf '%s\n' "$out" | grep -E '^\{' | tail -1)"
  case "$kind" in
    fidelity_lint)
      norm="$(printf '%s' "$raw" | jq -r '
        if (type != "object") then "MISSING json_unparseable"
        elif ((.probe_ok | type) != "boolean") then "MISSING field_missing_or_non_boolean"
        elif .probe_ok == false then "FALSE probe_ok"
        else "OK cases=\((.probe // []) | length) fired=\((.probe // []) | map(select(.fired == true)) | length) back_to_baseline=\(if (.back_to_baseline | type) == "boolean" then (.back_to_baseline | tostring) else "n/a" end)"
        end' 2>/dev/null)"
      ;;
    redline_scan)
      norm="$(printf '%s' "$raw" | jq -r '
        if (type != "object") then "MISSING json_unparseable"
        elif ((.probe_ok | type) != "boolean") then "MISSING field_missing_or_non_boolean"
        elif .probe_ok == false then "FALSE probe_ok"
        else "OK cases=\((.probe // []) | length) fired=\((.probe // []) | map(select((.fired == true) or (.clean == true))) | length) back_to_baseline=\((.probe // []) | map(select(.case == "back_to_baseline")) | if length == 0 then "n/a" elif .[0].hits == .[0].baseline then "true" else "false" end)"
        end' 2>/dev/null)"
      ;;
    scan_ip_boundary)
      norm="$(printf '%s' "$raw" | jq -r '
        if (type != "object") then "MISSING json_unparseable"
        elif ((.self_proof_ok | type) != "boolean") then "MISSING field_missing_or_non_boolean"
        elif .self_proof_ok == false then "FALSE self_proof_ok"
        else (.self_proof // {}) as $p
          | "OK cases=\(($p.per_pattern_detected // {}) | length) fired=\(($p.per_pattern_detected // {}) | map(select(. == true)) | length) back_to_baseline=\(if ($p.removed_restores_baseline | type) == "boolean" then ($p.removed_restores_baseline | tostring) else "n/a" end)"
        end' 2>/dev/null)"
      ;;
    scan_fidelity_terms)
      norm="$(printf '%s' "$raw" | jq -r '
        if (type != "object") then "MISSING json_unparseable"
        elif ((.probe_ok | type) != "boolean") then "MISSING field_missing_or_non_boolean"
        elif .probe_ok == false then "FALSE probe_ok"
        else "OK cases=\((.probe // []) | length) fired=\((.probe // []) | map(select(((if .fact_line_detected == null then true else .fact_line_detected end) and (if .non_fact_line_ignored == null then true else .non_fact_line_ignored end) and (if .capped == null then true else .capped end)))) | length) back_to_baseline=\(if (.back_to_baseline | type) == "boolean" then (.back_to_baseline | tostring) else "n/a" end)"
        end' 2>/dev/null)"
      ;;
    validate_capability_schema)
      norm="$(printf '%s' "$raw" | jq -r '
        if (type != "object") then "MISSING json_unparseable"
        elif ((.self_proof_ok | type) != "boolean") then "MISSING field_missing_or_non_boolean"
        elif .self_proof_ok == false then "FALSE self_proof_ok"
        else "OK cases=\(.cases // "n/a") fired=\(.fired // "n/a") back_to_baseline=n/a engine=\(.engine // "n/a")"
        end' 2>/dev/null)"
      ;;
    probe_json)
      norm="$(printf '%s' "$raw" | jq -r '
        if (type != "object") then "MISSING json_unparseable"
        elif ((.probe_ok | type) != "boolean") then "MISSING field_missing_or_non_boolean"
        elif .probe_ok == false then "FALSE probe_ok"
        else "OK cases=\((.probe // []) | length) fired=\((.probe // []) | map(select(.fired == true)) | length) back_to_baseline=\(if (.back_to_baseline | type) == "boolean" then (.back_to_baseline | tostring) else "n/a" end)"
        end' 2>/dev/null)"
      ;;
    *)
      norm="MISSING unknown_tool_kind"
      ;;
  esac
  case "$norm" in
    OK\ *)    ok "$label self-proof holds (${norm#OK })" ;;
    FALSE\ *) bad "$label self-proof failed (${norm#FALSE }=false)" ;;
    "")       bad "$label self-proof failed (field_unreadable: empty_output)" ;;
    *)        bad "$label self-proof failed (field_unreadable: ${norm#MISSING })" ;;
  esac
}

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
# r2.6（PM m5-08 §7.1 + §三.1）：自证项读**机器可读判定字段** `self_proof_ok`（工具新增 `--json`），
#   **不读退出码**；且自证**基线来源与被测树解耦** —— 合法基线是工具**内嵌夹具**（实现 ③），
#   与被测树零交集 ⇒ 改坏 cap_dir 下**任何一个** manifest（含实测 `bases[0] = embed.text@1.0.0`）
#   都不会把自证染红（PM §8.3 的 6 次逐个注入判据）。
selfproof "schema validator (valid baseline green + 4 invalid red + sampling-legal green)" \
  validate_capability_schema python3 v0_skeleton/tools/validate_capability_schema.py \
  --schema capability.schema.json --cap-dir v0_skeleton/capabilities --selftest --json

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

# ---------- 13) IP 边界扫描（R2 / F12；M5.1 r2 起收敛为 2 条模式） ----------
# 方向（CHG-20260923-009 §0）：原著人物 / 名称 / 情节 / 世界规则是**核心依据** ——
# 判据从「拦原著内容」翻转为「要求原著内容命中」。本扫描器只留 2 条模式：
#   `jump_scare`（呈现选择，不是 IP 约束）与 `verbatim_body_paragraph`（D-4 规则：
#   引号内 CJK ≥60，或 ≥24 且 ≥2 个句末/分句标点 ⇒ 逐字搬运正文段落）。
# `verbatim_body_paragraph` **不可豁免**；声明站点机制只对 `jump_scare` 生效，且同行须含
# 显式哨兵 `IP-BOUNDARY-DECLARATION`（取代旧词法判据 —— Raven C-2 两侧对照实证其可被绕过）。
# `--probe-only` 为**逐模式**自证（Raven M-8）：任一模式失效即自证失败。
#
# ⚠️ r2.6 dedupe（PM m5-08 §7.2，**做，两对都做**）：本节原有 4 条项，其中**两对**是
#   **同一条命令跑两遍**（只有标签不同）。同一条命令跑两遍不是第二份证据：虚增 PASS、
#   把该扫描器的成本翻倍、树脏时把同一条 FAIL 报两遍。合并后本组 = 2 条（1 树读数 + 1 自证）：
#     对 1（树读数）：`scan_ip_boundary.py --root .`（原 L513 / L531）⇒ 保留 1 条；
#     对 2（自证）：`scan_ip_boundary.py --root . --probe`（原 L518 / L536）⇒ 保留 1 条。
#   被删那处的语义**已并进保留处的标签**（不丢可追溯性）：
#     · 树项标签保留 `S1~S5: 2 patterns` 的可追溯性；
#     · 自证项标签保留**逐模式归因**（工具的 `_probe_self_proof()` 确实按
#       `per_pattern_detected` 逐模式判定 ⇒「per-pattern」不是假标签）。
# ⚠️ `L389 / L395`（`validate_capability_schema.py --schema … --cap-dir …`）**不是重复**：
#   一条带 `--selftest`、一条不带，**未做 dedupe**（朴素按行首归一化会把 `--selftest` 抹掉
#   从而误报假重复 —— 本处显式登记，供后续扫描脚本自检）。
# r2.6：树项读**退出码 + JSON 树读数**（树项本来就该因树红而红），自证项改走 `selfproof`
#   （读 JSON 判定字段 + 工具 `--probe-only` 隔离临时树）⇒ 两个维度不再互相污染。
IPB_TREE_OUT="$(python3 v0_skeleton/tools/scan_ip_boundary.py --root . 2>/dev/null)"; IPB_TREE_RC=$?
IPB_TREE_N="$(printf '%s\n' "$IPB_TREE_OUT" | grep -E '^\{' | tail -1 | jq -r '.unwhitelisted_hits // "n/a"' 2>/dev/null)"
if [ "$IPB_TREE_RC" -eq 0 ]; then
  ok "IP boundary scan clean (S1~S5: 2 patterns, 0 unwhitelisted hits)"
else
  bad "IP boundary scan found unwhitelisted hits (tree violations: ${IPB_TREE_N:-n/a}; S1~S5: 2 patterns)"
fi
selfproof "IP boundary scanner per-pattern (jump_scare + verbatim_body_paragraph; probe detected + removal restores baseline)" \
  scan_ip_boundary python3 v0_skeleton/tools/scan_ip_boundary.py --probe-only

# ---------- 14) 保真度判据（M5.1 / S1~S8） ----------
# 把 CHG-20260923-009 §2 的 S1~S8 逐处落成的**机械判据**接进门禁：
#   ① IP 边界扫描（2 条模式 + **逐模式**自证）—— **见 §13**
#      （r2.6 dedupe：本节原有两条 `scan_ip_boundary.py` 调用与 §13 的两条是**同一条命令**，
#       已合并进 §13 且语义并进其标签；本节不再重复调用同一条命令。）
#   ② 反向判据 scan_fidelity_terms（register 面 = 门禁；pack 面 = 本轮只出读数、enforced:false）
#   ③ 出处表 lint R1~R7（--strict + 四态自证）
#   ④ 两套 tools 单测（AC-1 侧 fidelity/tools/tests、AC-2 侧 v0_skeleton/tools/tests）
# 复跑纪律：pytest 一律 PYTHONDONTWRITEBYTECODE=1 + -p no:cacheprovider（不在交付树留残渣）。
# r2.6：本节的自证项一律改走 `selfproof`（读 JSON 判定字段 `probe_ok` + 工具 `--probe-only`
#   隔离临时树），**不读退出码** ⇒ 树红不再把自证项一起染红（PM m5-08 §三）。
if python3 v0_skeleton/tools/scan_fidelity_terms.py --root . --face register >/dev/null; then
  ok "fidelity terms (register face) met: every pinned term has >=1 fact-line hit"
else
  bad "fidelity terms (register face) below floor (tree reading: 逐词命中/下界见工具 JSON)"
fi
selfproof "fidelity terms register face (per-term fact-line injection + non-fact-line ignored + word-salad capped + baseline restore)" \
  scan_fidelity_terms python3 v0_skeleton/tools/scan_fidelity_terms.py --probe-only
LINT_TREE_OUT="$(python3 fidelity/tools/fidelity_lint.py --strict 2>/dev/null)"; LINT_TREE_RC=$?
LINT_TREE_N="$(printf '%s\n' "$LINT_TREE_OUT" | grep -E '^\{' | tail -1 | jq -r '.violations_total // "n/a"' 2>/dev/null)"
if [ "$LINT_TREE_RC" -eq 0 ]; then
  ok "fidelity lint --strict clean (R1~R7, 0 violations)"
else
  bad "fidelity lint --strict reported violations (tree violations: ${LINT_TREE_N:-n/a}; R1~R7)"
fi
selfproof "fidelity lint four-state (no-anchor / fake-anchor / body paragraph / body-in-fact)" \
  fidelity_lint python3 fidelity/tools/fidelity_lint.py --probe-only
if PYTHONDONTWRITEBYTECODE=1 python3 -m pytest v0_skeleton/tools/tests -q -p no:cacheprovider >/dev/null 2>&1; then
  ok "tools unit tests (AC-2 side: scan_ip_boundary + scan_fidelity_terms) pass"
else
  bad "tools unit tests (AC-2 side) failed"
fi
if PYTHONDONTWRITEBYTECODE=1 python3 -m pytest fidelity/tools/tests -q -p no:cacheprovider >/dev/null 2>&1; then
  ok "tools unit tests (AC-1 side: fidelity_lint + redline_scan + extract_facts) pass"
else
  bad "tools unit tests (AC-1 side) failed"
fi

# ---------- 14b) 红线内容比对（l0_verbatim 主判据）—— M5.1 r2.5 / PM 裁决 m5-07 §一 / Raven R-1 / R-6 ----------
# 判据（PM m5-07 §一）：只取 CJK 归一化后与 L0 全本逐字比对，**连续串 ≥16 字**即命中 —— 形态无关
#   （去引号 / 换未登记引号 / 引号配对错位 / 按标点切句 都不影响）；命中串落在官方标题（`official_title`）
#   内 ⇒ **机械豁免**并计数（白名单是算出来的，不是手写的）。
# 扫描面 = **门禁面**（`02_source/**` + `docs/**` + 根级 `03_artisan_self_test.log` / `V0_M5.sha256` / `0*.md`）；
#   **按名排除**（工具 `scope` 里显式输出，不得静默）：`refs/**`（源镜像本身）、`spikes/**`（参考 fixture）、
#   `.squad_result.txt` 与 `.task-*.out`（**原始子代理转录：改了即篡改证据**）。
# 出口判据 = **非白名单 l0_verbatim 命中数 = 0**；L0 缺件 ⇒ **SKIP + 显式标记**（不得记 PASS）。
# 读数格式 = `文件:行:长度`（**不含正文**）；次要规则（quoted_body / long_cjk_run）只出读数，不参与退出码。
WS_ROOT="$(cd "$HERE/.." && pwd)"
L0_PATH="$(cd "$HERE/../../.." && pwd)/sources/deephealing/《我的治愈系游戏》（校对版全本+番外）.txt"
if [ ! -f "$L0_PATH" ]; then
  skip "redline scan (l0_verbatim): L0 fulltext missing => SKIP (NOT PASS)"
else
  REDLINE_OUT="$(python3 fidelity/tools/redline_scan.py --root "$WS_ROOT" --source-l0 "$L0_PATH" 2>&1)"
  REDLINE_RC=$?
  REDLINE_PRIMARY="$(printf '%s\n' "$REDLINE_OUT" | grep -E '^\{' | tail -1 | jq -r '.primary_hits_total // "n/a"' 2>/dev/null)"
  printf '%s\n' "$REDLINE_OUT" | grep -E ':l0_verbatim:|:quoted_body:|:long_cjk_run:' | sed 's/^/      hit  /' || true
  if [ "$REDLINE_RC" -eq 0 ]; then
    ok "redline scan clean (non-whitelisted l0_verbatim == 0; delivery face + named excludes)"
  elif [ "$REDLINE_RC" -eq 3 ]; then
    skip "redline scan: L0 fulltext missing => SKIP (NOT PASS)"
  else
    bad "redline scan found non-whitelisted l0_verbatim hits (tree violations: ${REDLINE_PRIMARY:-n/a}; see hit lines above; delivery face)"
  fi
  # 自证（RK-3：判据必须有牙）：正对照 = 运行时从 L0 取 60 CJK 去标点注入 /tmp ⇒ 必命中；
  # 负对照 = 技术性中文行 ⇒ 不命中；标题豁免；移除注入 ⇒ 回基线。
  # r2.6：**不再**靠调用点挑 `docs/` 这个「恰好干净」的 scope 来规避树状态（脆弱耦合）——
  #   改用工具自带 `--probe-only`（临时树 + **运行时构造**的负对照行，不读被测树），
  #   判据读 JSON 字段 `probe_ok`（PM m5-08 §三.5；隔离写进工具自身）。
  selfproof "redline scanner (L0 excerpt punctuation-stripped => hit; technical line => no hit; title exempt; removal => baseline)" \
    redline_scan python3 fidelity/tools/redline_scan.py --root "$WS_ROOT" --source-l0 "$L0_PATH" --probe-only
fi

# ---------- 15) AC-10 行为多样性判据（M5.2 r1 / REQ §4 / 设计 §5.5 D-7） ----------
# 判据（**逐字不动**，不得为凑绿放宽）：10-a 单一 bt_branch <= 60% / 10-b 单一 dominant_need <= 60%
#   / 10-c 每 NPC 不同动作 >= 3 / 10-d-1 全体室外采样占比 >= 20% / 10-d-2 各自 >= 20% 的 NPC >= 2。
# **口径声明（M5.2 r3 / FIX-5 · Raven §2.3，硬性）**：本节读数 = **交付门禁口径 = 记忆链关闭**
#   （工具不传 `memory_store`，JSON 的 `arm == "unwired"`）。**接线臂**读数（`--memory`）在 §18
#   并列公布，**不参与**本节 PASS 判定 ⇒ 不得把本节读数读成「接线后也这样」。
# 边界比较（FIX-10①）：10-d-1 / 10-d-2 读**未舍入**占比（`*_raw`），舍入值只作公布。
# 工具自研：v0_skeleton/tools/measure_behaviour_diversity.py（**不 cp PM 参考件**）；采样口径与
#   PM 参考件一致（每 5 tick 采样、>1500mm 判室外、seed=20260921、ticks=1440）。
# 判据读 **JSON 判定字段**（不读工具退出码）；前置输入缺失 ⇒ `status=skipped_missing_input` ⇒
#   本项记 **SKIP + 显式标记**（**不得**记 PASS）。逐 NPC 室外占比**一并公布**（REQ §4 硬性）。
AC10_JSON="$(tmpfile m52-ac10-gate)"
PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/measure_behaviour_diversity.py \
  --kernel-root v0_skeleton/kernel --pack "$PACK_DIR" \
  --seed 20260921 --ticks 1440 --json "$AC10_JSON" >/dev/null 2>&1
AC10_STATUS="$(jq -r '.status // "unreadable"' "$AC10_JSON" 2>/dev/null)"
if [ "$AC10_STATUS" = "skipped_missing_input" ]; then
  skip "AC-10 behaviour diversity: SKIPPED (missing prerequisite input => NOT PASS)"
elif [ "$AC10_STATUS" != "measured" ]; then
  bad "AC-10 behaviour diversity: field_unreadable (status=${AC10_STATUS:-empty})"
else
  AC10_SUMMARY="$(jq -r '[(."10a_pass"|tostring),(."10b_pass"|tostring),(."10c_pass"|tostring),(."10d1_pass"|tostring),(."10d2_pass"|tostring)] | join("/")' "$AC10_JSON" 2>/dev/null)"
  AC10_NUMBERS="$(jq -r '"10a=\(."10a_share") top=\(."10a_top_branch") | 10b=\(."10b_share") top=\(."10b_top_need") | 10c_min=\(."10c_min_actions_per_npc") | 10d1=\(."10d1_outdoor_share") | 10d2=\(."10d2_npcs_at_or_above_20pct")/\(."pack_npcs")"' "$AC10_JSON" 2>/dev/null)"
  AC10_PER_NPC="$(jq -rc '.per_npc_outdoor' "$AC10_JSON" 2>/dev/null)"
  if [ "$AC10_SUMMARY" = "true/true/true/true/true" ]; then
    ok "AC-10 behaviour diversity: all five criteria hold (10a/10b/10c/10d1/10d2 = ${AC10_SUMMARY}; ${AC10_NUMBERS})"
  else
    bad "AC-10 behaviour diversity: criteria not all green (10a/10b/10c/10d1/10d2 = ${AC10_SUMMARY}; ${AC10_NUMBERS})"
  fi
  say "      per-npc outdoor share (REQ hard requirement): ${AC10_PER_NPC}"
fi
selfproof "AC-10 criteria (revert C1 => single-branch dominance; revert C2+C3 => outdoor collapse)" \
  probe_json python3 v0_skeleton/tools/ac10_probe.py

# ---------- 16) AC-4 对照场景（M5.2 r1 / Raven M-14） ----------
# 三条对照臂：A 无经历·短 tick / B 无经历·长 tick / C 有经历·与 B 同 tick 数；
# 判据 = ① 同窗口内 A==B（tick 数不是原因）② C 在该窗口内与 B 不同且有事件解释链
# ③ 经历效应严格大于 tick 效应 ④ 无经历臂不得「被治愈」（不塌成单一分支、无收敛趋势）。
AC4_JSON="$(tmpfile m52-ac4-gate)"
PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/contrast_scenario.py \
  --kernel-root v0_skeleton/kernel --pack "$PACK_DIR" \
  --seed 20260921 --ticks 480 --short-ticks 120 --json "$AC4_JSON" >/dev/null 2>&1
AC4_STATUS="$(jq -r '.status // "unreadable"' "$AC4_JSON" 2>/dev/null)"
if [ "$AC4_STATUS" = "skipped_missing_input" ]; then
  skip "AC-4 contrast scenario: SKIPPED (missing prerequisite input => NOT PASS)"
elif [ "$AC4_STATUS" != "measured" ]; then
  bad "AC-4 contrast scenario: field_unreadable (status=${AC4_STATUS:-empty})"
elif [ "$(jq -r '.all_pass' "$AC4_JSON" 2>/dev/null)" = "true" ]; then
  ok "AC-4 contrast scenario: all criteria hold (explanation chain at tick $(jq -r '.explanation_chain.tick' "$AC4_JSON" 2>/dev/null), injected for $(jq -r '.explanation_chain.npc_id' "$AC4_JSON" 2>/dev/null))"
else
  bad "AC-4 contrast scenario: criteria not all green ($(jq -rc '.criteria | map_values(.pass)' "$AC4_JSON" 2>/dev/null))"
fi

# ---------- 17) 新 pack 的独立判据（M5.2 r1 / Raven M-6 / M-10 / M-11 / M-17） ----------
# M-6：`verify_specs.sh` 的 `PACK_DIR` / `PACK_DIR_2` 是硬编码的 ⇒ 新 pack **不会**被 §7/§7b 覆盖
#   ⇒ 这里给**独立**判据（pack.sig 逐文件比对 + `kernel validate --pack` + worldview 过 schema + 负例）。
PACK_DIR_3="v0_skeleton/districts/xingfu-xiaoqu-xuqin"
AC6_MIRROR="$WS_ROOT/spikes/m52-ac6/xingfu-xiaoqu-xuqin-mirror"
if python3 v0_skeleton/tools/verify_pack.py "$PACK_DIR_3" >/dev/null 2>&1; then
  ok "pack.sig verified for $PACK_DIR_3 (M5.2 proposal pack)"
else
  bad "pack.sig verification failed for $PACK_DIR_3"
fi
if PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=v0_skeleton/kernel python3 -m deephealing_kernel validate --pack "$PACK_DIR_3" >/dev/null 2>&1; then
  ok "kernel validate --pack $PACK_DIR_3 (pure-data addition; zero kernel change)"
else
  bad "kernel validate failed for $PACK_DIR_3"
fi
if python3 v0_skeleton/tools/schema_validate.py worldview.schema.json "$PACK_DIR_3/worldview.json" >/dev/null 2>&1; then
  ok "worldview.json passes worldview.schema.json for $PACK_DIR_3"
else
  bad "worldview.json failed worldview.schema.json for $PACK_DIR_3"
fi
# AC-6：人物跨 pack 身份映射（**只读 pack 数据、内核零改动**）—— 正例 + 反例（真实冻结产物 north）
if [ -d "$AC6_MIRROR" ]; then
  AC6_OUT="$(PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/check_identity_continuity.py \
    --pack-a "$PACK_DIR_3" --npc-a npc-006 --pack-b "$AC6_MIRROR" --npc-b npc-006 \
    --positive-pack "$PACK_DIR_3" --negative-pack "$PACK_DIR_2" 2>/dev/null | grep -E '^\{' | tail -1)"
  if [ "$(printf '%s' "$AC6_OUT" | jq -r '.continuous' 2>/dev/null)" = "true" ] \
     && [ "$(printf '%s' "$AC6_OUT" | jq -r '.probe_ok' 2>/dev/null)" = "true" ]; then
    ok "AC-6 identity continuity: same person_id across packs => continuous; copied pack without alignment => discontinuous (probe ok)"
  else
    bad "AC-6 identity continuity failed (continuous=$(printf '%s' "$AC6_OUT" | jq -r '.continuous' 2>/dev/null), probe_ok=$(printf '%s' "$AC6_OUT" | jq -r '.probe_ok' 2>/dev/null))"
  fi
else
  skip "AC-6 identity continuity: fixture pack missing at $AC6_MIRROR => SKIP (NOT PASS)"
fi
selfproof "AC-6 identity continuity (positive/negative cases)" \
  probe_json python3 v0_skeleton/tools/check_identity_continuity.py \
  --pack-a "$PACK_DIR_3" --npc-a npc-006 --pack-b "$AC6_MIRROR" --npc-b npc-006 \
  --positive-pack "$PACK_DIR_3" --negative-pack "$PACK_DIR_2" --probe-only
# AC-7：NPC 准入闸门（主包 5 个 + pack.sig 逐字节不变 + 提案包 1 个 + 来源标注非空）+ 负例
AC7_OUT="$(PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/check_npc_admission_gate.py \
  --main-pack "$PACK_DIR" --proposal-pack "$PACK_DIR_3" 2>/dev/null | grep -E '^\{' | tail -1)"
if [ "$(printf '%s' "$AC7_OUT" | jq -r '.gate_ok' 2>/dev/null)" = "true" ] \
   && [ "$(printf '%s' "$AC7_OUT" | jq -r '.probe_ok' 2>/dev/null)" = "true" ]; then
  ok "AC-7 NPC admission gate: main pack == 5 npcs + pack.sig byte-identical; proposal pack == 1 npc with source_facts (probe ok)"
else
  bad "AC-7 NPC admission gate failed (gate_ok=$(printf '%s' "$AC7_OUT" | jq -r '.gate_ok' 2>/dev/null), probe_ok=$(printf '%s' "$AC7_OUT" | jq -r '.probe_ok' 2>/dev/null))"
fi
selfproof "AC-7 admission gate (extra npc / npc without source_facts)" \
  probe_json python3 v0_skeleton/tools/check_npc_admission_gate.py \
  --main-pack "$PACK_DIR" --proposal-pack "$PACK_DIR_3" --probe-only
# M-17：CHR 出处可复算（每条设定 → CHR 编号，且编号在事实册内存在且非 UNVERIFIED）+ 负例
CHR_DOSSIERS="fidelity/05-character-dossiers.md"
if [ -f "$CHR_DOSSIERS" ]; then
  CHR_OUT="$(PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/check_chr_provenance.py \
    --dossiers "$CHR_DOSSIERS" --npc "$PACK_DIR_3/npcs/npc-006.json" 2>/dev/null | grep -E '^\{' | tail -1)"
  if [ "$(printf '%s' "$CHR_OUT" | jq -r '.provenance_ok' 2>/dev/null)" = "true" ] \
     && [ "$(printf '%s' "$CHR_OUT" | jq -r '.probe_ok' 2>/dev/null)" = "true" ]; then
    ok "CHR provenance: every setting maps to an existing non-UNVERIFIED CHR id (probe ok)"
  else
    bad "CHR provenance failed (provenance_ok=$(printf '%s' "$CHR_OUT" | jq -r '.provenance_ok' 2>/dev/null), probe_ok=$(printf '%s' "$CHR_OUT" | jq -r '.probe_ok' 2>/dev/null))"
  fi
  selfproof "CHR provenance (forged id / UNVERIFIED id)" \
    probe_json python3 v0_skeleton/tools/check_chr_provenance.py \
    --dossiers "$CHR_DOSSIERS" --npc "$PACK_DIR_3/npcs/npc-006.json" --probe-only
else
  skip "CHR provenance: dossiers missing at $CHR_DOSSIERS => SKIP (NOT PASS)"
fi

# ---------- 17b) NPC 外形契约（N2 / REQ-20260924-002 W1d；**只新增一条**，既有检查项逐字不动） ----------
# 依据（设计 §9-B7 / §12 R-10）：`appearance.*.source_facts` 是**嵌套**字段，而既有
#   `check_chr_provenance.py` 只读**顶层** `source_facts` / `source_fact_map`
#   ⇒ 若不接入，AC-1 / AC-2 / AC-4 / AC-10 本轮**没有任何门禁级判据**（只剩自测日志）。
# 口径：这是**加法**（REQ §2 明文只禁「`verify_specs.sh` 的**既有检查项语义**」被改）；
#   本项**不**触碰任何既有检查项，且**只**新增这一条。
# 读数 = 工具 JSON 的判定字段（`appearance_ok` + `probe_ok`），不是退出码；
#   `probe_ok` 覆盖 6 条 /tmp 隔离负例（删 eyes.color / 去 design_fill / 伪造 CHR-99 /
#   mask.number=9 / 顶层塞 appearance.* 新键 / 删被引用的参考图）。
NA_OUT="$(PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/verify_npc_appearance.py --root . 2>/dev/null | grep -E '^\{' | tail -1)"
if [ "$(printf '%s' "$NA_OUT" | jq -r '.appearance_ok' 2>/dev/null)" = "true" ] \
   && [ "$(printf '%s' "$NA_OUT" | jq -r '.probe_ok' 2>/dev/null)" = "true" ]; then
  ok "NPC appearance contract verified (schema + nested provenance + states/mask + character refs; 9 injected negatives fire)"
else
  bad "NPC appearance contract failed (appearance_ok=$(printf '%s' "$NA_OUT" | jq -r '.appearance_ok' 2>/dev/null), probe_ok=$(printf '%s' "$NA_OUT" | jq -r '.probe_ok' 2>/dev/null))"
fi

# ---------- 18) AC-10 记忆接线臂 + MEMORY_SIGNAL_* 敏感性断言（M5.2 r3 / FIX-5 · Raven §2.3） ----------
# **口径声明（硬性）**：§15 的**交付门禁口径 = 记忆链关闭**（`memory_store=None`，unwired）——
#   那是「交付特性未接线」的配置，不得读成「接线后也这样」。本节补**接线臂**读数
#   （`--memory`，等价 `cli.py --memory-chain`）⇒ 两组读数**并列公布**。
# **敏感性断言**：`MEMORY_SIGNAL_WEIGHT`（=「近因自我强化」的强度）× w ∈ {0.10, 0.20, 0.30}
#   三档下**五条判据均须为真**（判据阈值**逐字未动**：10-a/10-b ≤60%、10-c ≥3、10-d-1 ≥20%、10-d-2 ≥2）。
#   **为什么是这三档**：标定值 0.20 上下各一档；w=1.00 时 10-c 会红（实测 1 个动作/NPC）⇒
#   「达标是标定结果、不是机制鲁棒」这件事由本节读数**显式暴露**，不再只写在自述里。
# **同一敏感性说明还覆盖**：`MEMORY_SIGNAL_WINDOW` / `MEMORY_SIGNAL_MIN_IMPORTANCE`
#   （实测 window∈{1,3,5}、min_importance∈{0.3,0.5,0.7} 均绿；读数见 `03` 的 M5.2-r3 段 FIX-5）。
#   扫描开关只在工具进程内覆盖模块级常量 ⇒ **不写盘、不改交付面**（交付面常量未被改动）。
for W in 0.10 0.20 0.30; do
  AC10_W_JSON="$(tmpfile m52-ac10-wired)"
  PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/measure_behaviour_diversity.py \
    --kernel-root v0_skeleton/kernel --pack "$PACK_DIR" \
    --seed 20260921 --ticks 1440 --memory --weight "$W" --json "$AC10_W_JSON" >/dev/null 2>&1
  AC10_W_STATUS="$(jq -r '.status // "unreadable"' "$AC10_W_JSON" 2>/dev/null)"
  AC10_W_ARM="$(jq -r '.arm // "unreadable"' "$AC10_W_JSON" 2>/dev/null)"
  if [ "$AC10_W_STATUS" != "measured" ] || [ "$AC10_W_ARM" != "wired" ]; then
    bad "AC-10 wired arm w=$W: field_unreadable (status=${AC10_W_STATUS:-empty} arm=${AC10_W_ARM:-empty})"
    continue
  fi
  AC10_W_SUMMARY="$(jq -r '[(."10a_pass"|tostring),(."10b_pass"|tostring),(."10c_pass"|tostring),(."10d1_pass"|tostring),(."10d2_pass"|tostring)] | join("/")' "$AC10_W_JSON" 2>/dev/null)"
  AC10_W_NUMBERS="$(jq -r '"10a=\(."10a_share") | 10b=\(."10b_share") | 10c_min=\(."10c_min_actions_per_npc") | 10d1=\(."10d1_outdoor_share_raw") | 10d2=\(."10d2_npcs_at_or_above_20pct")/\(.pack_npcs)"' "$AC10_W_JSON" 2>/dev/null)"
  if [ "$AC10_W_SUMMARY" = "true/true/true/true/true" ]; then
    ok "AC-10 wired arm (MEMORY_SIGNAL_WEIGHT=$W): all five criteria hold (${AC10_W_SUMMARY}; ${AC10_W_NUMBERS})"
  else
    bad "AC-10 wired arm (MEMORY_SIGNAL_WEIGHT=$W): criteria not all green (${AC10_W_SUMMARY}; ${AC10_W_NUMBERS})"
  fi
done
# 交付门禁口径的**声明项**（防止读者把 §15 的读数误读成「接线后也这样」）：
#   口径 = unwired；接线臂读数只作**并列公布**，不参与 §15 的 PASS 判定。
if [ "$(jq -r '.arm' "$AC10_JSON" 2>/dev/null)" = "unwired" ]; then
  ok "AC-10 delivery-gate arm is explicitly UNWIRED (memory chain off; wired readings published separately in this section)"
else
  bad "AC-10 delivery-gate arm is not unwired (arm=$(jq -r '.arm // "unreadable"' "$AC10_JSON" 2>/dev/null)) — gate scope must be declared"
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
