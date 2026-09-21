# 08 · V0 垂直切片实施计划（文件级 / 接口级）

- 计划：`REQ-20260921-002-deephealing-architecture-freeze`　作者：artisan　日期：2026-09-21
- 上游：`01_architecture_design.md`（已冻结）、`02_source/`（契约与骨架，`verify_specs.sh` exit 0）、`03_spike_log.md`（真跑证据）、`06`/`07`（选型与 ADR）
- 纪律：**RED 先行**（每条判据先有一个会失败的用例）→ 最小 GREEN → V0 复跑。本计划的「代码」= `02_source/v0_skeleton/` 下的接口骨架，V0 阶段把它们实现到可跑。
- 估算口径：1 人日 = 8 小时；估算是**实现工作量**，不含 Sentinel/Raven 复核时间。

---

## 1. V0 定义与验收边界

**V0 = 可跑的单街区垂直切片**：1 个 district pack（`xingfu-xiaoqu`，1 栋楼 + 5 住户）+ 确定性内核（10 Hz）+ 能力注册表（四类 provider，**远端为可降级的能力补充 provider，默认路径允许降级**）+ 双模式会话（observe / participate）+ three.js 渲染 + 观测回放。**不是**可玩成品：无美术量产、无多人在线部署、无自进化启用。

**V0 边界（round 3 写死，不得自行扩权）**：
- **世界模型**：V0 **不包含**世界模型运行时集成，只含**适配器接口 + 占位实现**（占位实现 = 静态呈现 / 确定性结构化回退，可被 provider 切换）。见 W0c。
- **AIGC 素材**：V0 只需 **1 张程序化占位资产 + 1 份 manifest 示例**（示例必须过 `asset.manifest.schema.json` 且 `jq .` 通过）；schema / art bible / pipeline spec 是**必交物**，但**不量产素材**。见 W0d。
- 若执行方认为必须提前集成 / 提前量产 → **上抛 `block_issues`**，不得自行扩权（architect 本轮裁决：**不提前集成、不提前量产**）。

**V0 完成的硬判据**（全部可命令行复现）：

| # | 判据 | 命令 | 期望 |
|---|---|---|---|
| 1 | 契约全部合法 | `cd 02_source && bash verify_specs.sh` | exit 0（当前 63 项检查通过） |
| 2 | 确定性回放 | `cd 02_source/v0_skeleton/kernel && python -m pytest tests/test_determinism_replay.py -q` | 全绿（含 2 个负例）；⚠️ **口径提示（F14 / Sentinel LOW-4）**：**当前骨架**下 `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q` 实测 **18 skipped / 0 passed**，这是**收集性检查**（测试可被发现、导入无副作用），**不得**读成「内核单测通过」；V0 实现完成后本行才是全绿判据 |
| 3 | 能力注册与补充 | `... pytest tests/test_capability_registry.py -q` | 全绿（含「新增能力零源码改动」） |
| 4 | 内容包校验与第二街区 | `... pytest tests/test_pack_validate.py -q` | 全绿 |
| 5 | 双模式权限 | `... pytest tests/test_observe_mode_readonly.py -q` + `cd ../session && npm test` | 全绿 |
| 6 | 端到端跑通 | `python -m deephealing_kernel run --pack districts/xingfu-xiaoqu --seed 20260921 --events /tmp/e.jsonl --snapshot-every 50 --ws-port 8787` + 浏览器打开渲染层 | 世界持续 tick；浏览器可见 5 住户；事件日志增长 |
| 7 | 回放一致 | `python -m deephealing_kernel verify --events /tmp/e.jsonl --pack districts/xingfu-xiaoqu` | exit 0，逐检查点哈希一致 |

---

## 2. 工作包（文件级）

### W0b · V0 内核源码指纹（**同口径**，新增任务项；本轮只登记不实现）

- **背景**：本轮 spike 的「新增能力不改内核代码」判据只覆盖 **`engine.py` 单文件**（`spikes/s2-capability-cassette/kernel-digest`），对 V0 内核（`deephealing_kernel/**` 共 20+ 文件）证明力不足——单文件之外的源码被改动不会被发现。
- **文件**：`02_source/v0_skeleton/kernel/tools/kernel_digest.py`（新增）、`02_source/v0_skeleton/kernel/tests/test_kernel_digest.py`（新增）
- **接口冻结（同口径，与 `spikes/s2-capability-cassette/engine.py:kernel_digest()` 一致）**：
  - `kernel_digest(root) -> {"files": {relpath: sha256}, "digest": sha256(canonical_json(files))}`，遍历 `deephealing_kernel/**/*.py`（排除 `.venv`/`__pycache__`/`tests`）
  - 新增能力判据 = **before/after 差集**：`changed` 必须为空（既有文件字节不变），`added` 必须全部落在 `deephealing_kernel/providers/adapters/*.py`（adapter 目录）
- **RED 用例**：`test_new_capability_requires_no_kernel_source_change`——丢入新能力数据 + adapter → `changed == []` 且 `added ⊆ adapters/`；负例：改动 `tick.py` 一个字节 → `changed` 非空 → 判据必须失败
- **命令**：`cd 02_source/v0_skeleton/kernel && python -m deephealing_kernel.tools.kernel_digest --root . > /tmp/kd_before.json`（after 同理）→ `python -m pytest tests/test_kernel_digest.py -q`
- **判据落点**：AC-13 的 V0 验收证据（与 `08` §3 AC-13 行一致）
- **估算**：0.5 人日
- **依赖**：W0、W3（adapter 目录约定）

### W0c · 世界模型适配器接口 + 占位实现（**V0 不做运行时集成**）

- **背景**：AC-14 要求 V0 只交付适配器接口与占位实现，运行时**不**接世界模型（`01 §16.1.7`）。
- **文件**：`02_source/v0_skeleton/kernel/deephealing_kernel/providers/worldmodel_placeholder.py`（新增，占位 provider）、
  `02_source/v0_skeleton/capabilities/imagine.predict@1.0.0.capability.json`（新增，`imagine.*` 槽位）
- **接口冻结**：呈现适配器 `render(request: RenderRequest) -> RenderFrame`（只读投影进、画面句柄出，**无写回字段**）；
  能力槽位走 `capability.schema.json`，provider **必须**是 `remote_api`（`world_model_backend=true` 时 default-deny 校验）。
- **RED 用例**：`test_worldmodel_not_authoritative` —— ① 占位 provider 返回静态占位场景时 `state_hash` 不变；
  ② 把世界模型后端声明成 `local_model` → `verify_capability_binding.py` 必须非 0；③ `imagine.*` 输出 schema 非法 → 落 fallback 且**不**产生事件。
- **命令**：`cd 02_source && python3 v0_skeleton/tools/verify_capability_binding.py --cap-dir v0_skeleton/capabilities --schema capability.schema.json`（期望 exit 0）
- **判据落点**：AC-14 的 V0 面（接口 + 占位实现存在；运行时无世界模型调用）

### W0d · 离线内容管线：1 张程序化占位资产 + 1 份 manifest 示例

- **背景**：AC-15 要求 V0 不量产素材，但 schema / art bible / pipeline spec 必交（`01 §16.2.9`）。
- **文件**：`02_source/v0_skeleton/assets-sample/placeholder-001.png`（**已生成**，64×64 程序化 PNG，无生成器元数据）、
  `assets-sample/asset.manifest.sample.json`（**已交付**）、`assets-sample/workflows/procedural-placeholder.json`（受管工作流登记）、
  `v0_skeleton/tools/make_placeholder_asset.py`（生成命令）、`v0_skeleton/tools/verify_asset_pack.py`（校验执行体）
- **命令**：
  `python3 v0_skeleton/tools/make_placeholder_asset.py assets-sample/placeholder-001.png`（workdir `<ws>/02_source/v0_skeleton`，exit 0）
  `python3 v0_skeleton/tools/verify_asset_pack.py --pack v0_skeleton/assets-sample --manifest v0_skeleton/assets-sample/asset.manifest.sample.json --license-table asset.license.table.data.json --runtime-tree v0_skeleton`（workdir `<ws>/02_source`，exit 0）
- **RED 用例**：把合法 PNG 改名 `.txt` 放进 pack → 校验器必须非 0（`spikes/s6-asset-pipeline/logs/n5_renamed_txt.log`）
- **判据落点**：AC-15 的 V0 面（示例过 schema + 校验器真跑）

### W0e · 实测延迟分布 → 声明值 → 降级率 标定（**V0 必做**，D-0.9）

- **背景**：D-0.9 要求 V0 交付标定；**不得把未标定的数带进 V0**。
- **文件**：`spikes/s5-latency-calibration/`（本轮已建：冻结规则 / 冻结区间 / 分布 / 降级率 / 敏感性对照）+ V0 侧脚本 `kernel/tools/calibrate_latency.py`
- **命令**：`python3 calibrate.py dist --samples 24 --timeout-ms 60000 --out logs/latency.distribution.json`（workdir `spikes/s5-latency-calibration`）→ `calibrate.py derive` → `calibrate.py degrade --formula adopted --runs 10` → `calibrate.py check`
- **判据**：① 规则文件 mtime 早于分布日志；② `timeout_ms ≥ p95` 且 `≠ max`；③ 三行对照（严 / 采用 / 松）都在**事先声明**的可接受区间内；④ 清单值与报告值脚本断言一致（`calibrate.py check` exit 0）
- **判据落点**：AC-13 / D-0.9 的 V0 面

### W0 · 骨架与契约校验（已在本轮完成，V0 只需保持）

- **文件**：`02_source/*.schema.json`、`manifest.txt`、`verify_specs.sh`、`v0_skeleton/tools/*`
- **接口**：无（数据契约）
- **RED**：篡改 pack 任一文件 → `verify_specs.sh` 必须非 0（已实测：`python3 tools/verify_pack.py` 篡改后 exit 1）
- **命令**：`cd 02_source && bash verify_specs.sh --quiet`
- **估算**：0.5 人日（维护成本，本轮已付）
- **依赖**：无

### W1 · 内核 tick / ECS / RNG（AC-1 / AC-2 基础）

- **文件**：
  - `kernel/deephealing_kernel/tick.py`（`WorldKernel.step/run/snapshot/state_hash`，`PHASES` 固定顺序）
  - `kernel/deephealing_kernel/ecs.py`（`World.spawn/despawn/query/set_component/to_state/apply_delta`）
  - `kernel/deephealing_kernel/rng.py`（`WorldRng.stream(name)` / `StreamRng.next_u64/uniform/pick` / `state_digest`）
  - `kernel/deephealing_kernel/bus.py`（只读订阅，订阅者异常隔离）
- **接口冻结**：`step()` 内阶段顺序 `input→perceive→decide→execute→account→snapshot` 不可交换；`query()` 返回按 entity id 升序；`set_component()` 只在 execute 阶段调用
- **RED 用例**：`tests/test_determinism_replay.py::test_new_subsystem_does_not_perturb_existing_streams`（新增 stream 不得改变既有序列）
- **命令**：`python -m pytest tests/test_determinism_replay.py -q -k stream`
- **估算**：3 人日
- **依赖**：W0

### W2 · 事件日志 / 快照 / 回放 / verify（AC-2）

- **文件**：
  - `kernel/deephealing_kernel/events.py`（`EventLog.append/read_all`、`redact()`、哈希链）
  - `kernel/deephealing_kernel/snapshot.py`（`canonical_json/state_hash/take_snapshot/write_checkpoint/compare_checkpoints/dump_divergence`）
  - `kernel/deephealing_kernel/cli.py`（`run` / `replay` / `verify` / `validate` / `pack sign` 子命令）
- **接口冻结**：`hash = sha256(prev_hash || canonical_json({seq,tick,type,actor,payload}))`；`state_hash = sha256(canonical_json(state))`；规范化共用 `tools/canonical_json.py`（**禁止各写一份**）
- **RED 用例**：`test_replay_twice_yields_identical_checkpoints`、`test_replay_detects_wall_clock_leak`、`test_replay_detects_unordered_iteration`
- **命令**：`python -m deephealing_kernel verify --events <log> --pack <dir>`（期望 exit 0；分歧时非 0 并打印首个分歧 tick）
- **参照实现**：`spikes/s1-determinism/kernel.py`（已真跑通过，可直接搬逻辑）
- **估算**：2 人日
- **依赖**：W1

### W3 · 能力注册表 / provider / cassette（AC-3 / AC-7 / AC-13）

- **文件**：
  - `kernel/deephealing_kernel/registry.py`（`discover/validate/register_adapter/invoke/resolve_impl/slots`）
  - `kernel/deephealing_kernel/providers/remote_api.py`（凭据只从环境变量；`redact_headers`）
  - `kernel/deephealing_kernel/providers/cassette.py`（`CassetteStore.cassette_key/record/lookup/verify_chain`）
  - `kernel/deephealing_kernel/providers/deterministic_rule.py`（四个纯函数）
  - `kernel/deephealing_kernel/providers/local_model.py`（ollama/transformers 适配器，V0 可 `available()=False`）
  - `capabilities/*.capability.json` + `capabilities/pins.json`（数据，已在骨架内）
- **接口冻结**：`invoke(slot, payload, force_provider=None, replay_mode=False)`；回放模式强制 `cassette_replay` + fail-closed；每次调用必须过 `output_schema`
- **RED 用例**：`test_registry_discovers_capability_files`、`test_new_capability_requires_no_kernel_source_change`、`test_provider_switch_remote_to_cassette_to_rule`、`test_invalid_capability_file_is_rejected`、`test_cassette_miss_is_fail_closed`、`test_invalid_model_output_falls_back`
- **命令**：`python -m pytest tests/test_capability_registry.py -q`
- **参照实现**：`spikes/s2-capability-cassette/engine.py`（已真跑；沿用 spike 的 `resolve_impl` 口径——`builtin:` 白名单枚举、`module:` 仅显式登记项，新增能力落 `providers/` adapter 目录；cassette 完整性 `hash` + `prev_hash` 链在命中/回放前置/validate 前置三处校验）
- **估算**：3 人日
- **依赖**：W1、W2（事件落盘）

### W4 · 规则层与预算（AC-7 / AC-10）

- **文件**：`kernel/deephealing_kernel/rules/utility.py`、`rules/behaviour_tree.py`、`kernel/deephealing_kernel/budget.py`
- **接口冻结**：行为树叶子 `call_capability(slot, budget)` 是**唯一**模型调用接缝；`BudgetLedger.allow_call/record/spend_impact/daily_report` 三级硬顶
- **RED 用例**：新增 `tests/test_budget_ledger.py`：超 tick 上限 → `fallback.on_budget_exhausted`；超日 token → 降级到 `deterministic_rule`；`spend_impact` 耗尽 → `E_BUDGET_EXHAUSTED`
- **命令**：`python -m pytest tests/test_budget_ledger.py -q`
- **估算**：2 人日
- **依赖**：W3

### W5 · 记忆层（AC-7 / R10）

- **文件**：`kernel/deephealing_kernel/memory/store.py`、`memory/retrieve.py`
- **接口冻结**：三张表（`working` / `episodes` / `facts`）字段名固定；`prune()` 只软删（`superseded_by`）
- **RED 用例**：新增 `tests/test_memory_layers.py`：写入→检索 top_k 排序稳定（相似度→tick→ref 显式 tie-break）；`prune` 后容量不超上限；反思写入的旧事实保留 `superseded_by`
- **命令**：`python -m pytest tests/test_memory_layers.py -q`
- **估算**：2 人日
- **依赖**：W3（`embed.text` 能力）、W2

### W6 · 内容包加载（AC-6）

- **文件**：`kernel/deephealing_kernel/pack.py`（`load_pack/verify_signature/check_engine_range/build_portal_edges`）+ `districts/xingfu-xiaoqu/**`（数据已在骨架内）
- **接口冻结**：校验顺序 `pack.json → engine_range → glob 命中 → 各文件 schema → pack.sig`；失败即 `E_PACK_INVALID` 且非 0 退出
- **RED 用例**：`tests/test_pack_validate.py`（含 `test_second_district_requires_no_kernel_change`、`test_tampered_pack_fails_closed`、`test_executable_file_in_pack_is_rejected`）
- **命令**：`python -m deephealing_kernel validate --pack districts/xingfu-xiaoqu`（exit 0）+ `pytest tests/test_pack_validate.py -q`
- **估算**：1 人日
- **依赖**：W0、W1

### W7 · 会话层：双模式权限 + 增量同步 + 意图（AC-4 / AC-12）

- **文件**：`session/src/server.js`、`session/src/mode.js`（已可执行）、`session/src/upstream.js`、`session/src/policy.js`、`session/test/session.test.js`
- **接口冻结**：`POST /sessions`、`WS /ws/{session_id}` 的消息类型与错误码见 `session.protocol.schema.json`；observe 上行一律 `E_MODE_READONLY`；意图只在 tick 边界应用
- **RED 用例**：`test_observe_session_intent_rejected_with_readonly_code`、`test_participate_intent_applied_only_at_tick_boundary`、`test_rate_limit_and_cooldown_enforced`、`test_impact_budget_exhausted_downgrades_to_observe`
- **命令**：`cd 02_source/v0_skeleton/session && npm test`
- **估算**：2 人日
- **依赖**：W1、W2、W3

### W8 · 渲染层与双模式 UI（AC-5 / AC-11）

- **文件**：`web/src/main.ts`、`web/src/net/client.ts`、`web/src/scene/world.ts`、`web/src/scene/lighting.ts`、`web/src/ui/observe/panel.ts`、`web/src/ui/participate/intervention.ts`
- **接口冻结**：`RenderClient.connect/apply/submitIntent`；`apply` 幂等（按 tick 丢弃过期、按 seq 去重）；观察模式 UI **无写入口**
- **RED 用例**：新增 `web/test/render-client.test.ts`：乱序 delta 被丢弃；`observe` 会话调用 `submitIntent` 本地即拒；`apply` 两次同一消息结果幂等
- **命令**：`cd 02_source/v0_skeleton/web && npm run build && npm test`
- **参照实现**：`spikes/s3-render/`（three.js 场景 + 治愈系数值断言，已真跑）
- **估算**：3 人日
- **依赖**：W7

### W9 · 观测层（AC-8）

- **文件**：`kernel/deephealing_kernel/cli.py` 的 `replay --out`（checkpoints）+ `tools/duckdb_queries.sql` + 观察模式指标面板
- **接口冻结**：`checkpoints/<tick>.json` 与 `snapshot.schema.json` 一致；分析只读事件日志，不写内核状态
- **RED 用例**：新增 `tests/test_observability.py`：`replay --out` 产出检查点数 = `ticks/snapshot_every`；哈希链自检 SQL 返回 0 断链
- **命令**：`python -m deephealing_kernel replay --events <log> --pack <dir> --out /tmp/ckpt --checkpoint-every 50` + `duckdb -c ".read tools/duckdb_queries.sql"`
- **估算**：1 人日
- **依赖**：W2

### W10 · 集成、端到端与 AC 全量验收

- **文件**：`v0_skeleton/kernel/tests/*`、`session/test/*`、`web/test/*` + 一份 `V0_SELF_TEST.md`（逐 AC 证据）
- **命令**：`cd 02_source && bash verify_specs.sh && cd v0_skeleton/kernel && python -m pytest -q && cd ../session && npm test`
- **估算**：2 人日
- **依赖**：W0~W9

### 汇总

| 工作包 | 人日 | 关键产物 |
|---|---|---|
| W0 契约与校验 | 0.5 | `verify_specs.sh` exit 0 |
| W0b V0 内核源码指纹（同口径） | 0.5 | `kernel_digest.py` + before/after 差集判据 |
| W1 内核 tick/ECS/RNG | 3 | `tick.py` / `ecs.py` / `rng.py` |
| W2 事件/快照/回放 | 2 | `events.py` / `snapshot.py` / `cli.py` |
| W3 能力注册表/provider | 3 | `registry.py` / `providers/*` / `capabilities/*` |
| W4 规则层与预算 | 2 | `rules/*` / `budget.py` |
| W5 记忆层 | 2 | `memory/store.py` / `memory/retrieve.py` |
| W6 内容包加载 | 1 | `pack.py` |
| W7 会话层 | 2 | `session/src/*` |
| W8 渲染层与 UI | 3 | `web/src/*` |
| W9 观测层 | 1 | `cli.py replay` / `duckdb_queries.sql` |
| W10 集成验收 | 2 | `V0_SELF_TEST.md` |
| **合计** | **22.0 人日（≈176 小时）** | — |

**关键路径**：W0 → W1 → W2 → W3 → {W4, W5} → W7 → W8 → W10（W0b/W6/W9 可并行）。
**风险缓冲**：+15%（≈3.2 人日）用于 `timeout_ms` 校准（见 Q1）、cassette 规范化跨语言一致性、日志体积（Q3）。

---

## 3. 逐 AC 判据（V0 阶段如何被证明）

| AC | V0 判据 | 证明命令 | 证据落点 |
|---|---|---|---|
| AC-1 分层架构与职责冻结 | 7 层职责/依赖方向/接口在 01 冻结；V0 实现不出现反向依赖（L1/L2 无模型调用、L4 不写世界状态） | `rg -n "requests\|httpx\|openai\|urllib" 02_source/v0_skeleton/kernel/deephealing_kernel/{tick,ecs,rules,memory}*.py`（期望零命中） | Sentinel 静态检查报告 |
| AC-2 确定性 tick 与回放 | 同一事件日志重放两次 → 全部检查点 `state_hash` 一致；两个非确定性负例被检出 | `pytest tests/test_determinism_replay.py -q` | 本文件 + `spikes/s1-determinism/logs/*` |
| AC-3 能力 provider 切换与 cassette | remote→cassette→rule 三类真跑；断网回放逐字段等价 | `pytest tests/test_capability_registry.py -q` | `spikes/s2-capability-cassette/logs/*` |
| AC-4 双模式权限与同步 | observe 上行 `E_MODE_READONLY`；participate 意图只在 tick 边界应用；限流/冷却/预算生效 | `pytest tests/test_observe_mode_readonly.py -q` + `npm test` | `session/test/*` |
| AC-5 渲染候选真跑 | `npm run build` exit 0 + 浏览器可见场景 | `cd web && npm run build` | `spikes/s3-render/logs/*`、`out/*.png` |
| AC-6 内容扩展机制 | 复制 pack → 改 id → 重签 → validate → run，`kernel/` 零改动 | `pytest tests/test_pack_validate.py -q` | `district.pack.spec.md` + 该用例 |
| AC-7 认知与自进化契约 | 四类高层能力经注册表；护栏契约存在且 V0 不启用改写 | `pytest tests/test_capability_registry.py -q` + 检查 `08`/`09` 的护栏条目 | `07_adr.md` ADR-012 |
| AC-8 观测回放 | `replay --out` 产出检查点；duckdb 查询可跑；时间轴 UI 读 `checkpoints/` | `python -m deephealing_kernel replay ... --out /tmp/ckpt` | `tools/duckdb_queries.sql` |
| AC-9 ADR | ≥8 条含 6 个必答主题 | `grep -c "^## ADR-" 07_adr.md`（期望 ≥8） | `07_adr.md` |
| AC-10 成本与性能预算 | 每 NPC 每日 token 三档 + 帧率/tick/延迟/内存预算；`BudgetLedger` 硬顶生效 | `pytest tests/test_budget_ledger.py -q` | `09_risks_open_questions.md` §3 |
| AC-11 美学与双模式信息架构 | 治愈系数值断言全通过；观察模式无写入口 | `node scripts/scene_assert.mjs` + `web` 的 `observe` 用例 | `spikes/s3-render/logs/scene_assert.log` |
| AC-12 参与影响任务演进 | `adaptation_rules` 数据驱动触发 `task.state_changed`，含 `max_shifts` 上限与审计 | `pytest tests/test_task_adaptation.py -q`（W7 新增） | `tasks/task-001.json` |
| AC-13 原子能力注册与补充 | 丢入新能力文件 + adapter → 注册表发现并调用成功；**既有内核源码字节不变，只新增数据 + adapter**（同口径指纹，见 W0b） | `pytest tests/test_capability_registry.py::test_new_capability_requires_no_kernel_source_change -q` + `pytest tests/test_kernel_digest.py -q` | `spikes/s2-capability-cassette/logs/s2_kernel_delta.json`（spike 侧同口径证据） |

---

## 4. 实施顺序与里程碑

| 里程碑 | 内容 | 出口条件 |
|---|---|---|
| M1（W0~W2，5.5 人日） | 内核能跑、能重放、哈希一致 | AC-2 用例全绿 + `verify --events` exit 0 |
| M2（W3~W6，8 人日） | 能力注册表 + 规则层 + 记忆 + 内容包 | AC-3 / AC-6 / AC-13 用例全绿；三类 provider 有真跑输出 |
| M3（W7~W8，5 人日） | 会话 + 渲染端到端 | 浏览器可见 5 住户持续 tick；observe/participate 权限用例全绿 |
| M4（W9~W10，3 人日） | 观测 + 集成验收 | 全部 AC 有 `PASS/GAP` 证据；`verify_specs.sh` exit 0 |

---

## 5. V0 明确不做（非目标）

- 不做美术量产（资产位留占位/程序化）；不做多人在线部署；不做生产部署/CI/CD 之外的基础设施
- **不做世界模型运行时集成**（只交付适配器接口 + 占位实现；见 W0c 与 `01 §16.1.7`）
- **不做 AIGC 素材量产**（只需 1 张程序化占位资产 + 1 份 manifest 示例；见 W0d 与 `01 §16.2.9`）
- 不启用自进化改写（V1/V2）；不引入服务型向量库；不引入 colyseus（V1 再议）
- 不做客户端预测与回滚（authority wins）；不做直播流/分享链接（V1）
- 不实现 `avatar` / `ghost_hand` 介入通道（V0 只 `delegate_instruction`）
- 不实现完整任务系统与剧情（只冻结契约 + 2 个样例任务）
- **不把未标定的 `timeout_ms` 带进 V0**（必须由 W0e 的实测标定给出声明值）

## 6. 已知会在 V0 撞上的坑（来自本轮真跑，提前记）

1. **`timeout_ms` 曾是纸面值**：round 1/2 契约钉死 2500/3000 ms，而实测远端推理 5.57–6.60 s（round 2 历史样本）→ 默认配置下必然超时降级。**round 3 已按 D-0.9 改为实测标定的声明值**（见 W0e 与 `spikes/s5-latency-calibration/`），V0 不得再用未标定的数
2. **`playwright@1.63` 与缓存 chromium 版本不匹配**：需 `npx playwright install chromium` 或回退系统 Chrome（S3 实测）
3. **colyseus 的版本耦合**（若 V1 采用）：`schema ^5.0.8` + 客户端必须是 `@colyseus/sdk`（S4 实测 ERESOLVE 与协议不兼容）
4. **cassette 规范化必须跨语言同一实现**：否则假 miss（ADR-006）
5. **内容包内禁止可执行文件**：已实装拦截，但 V0 加内容时要记得 `pack sign` 重签
6. **Rust 未装**：任何 Rust 候选都要先付工具链成本（ADR-001）
