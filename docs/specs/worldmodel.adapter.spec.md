# 世界模型适配器契约（`worldmodel.adapter.spec.md`）

对应：REQ **D-0.7 / AC-14**、`01_architecture_design.md` §16.1、ADR-010。
**复用 D-0.6 能力槽位机制**：世界模型只作为 provider 出现；**不得**新增第二条调用路径（§7.5 分层静态检查）。

## 0. 权威归属（冻结，不可被后续轮次默认推翻）

1. **权威始终是确定性内核**。世界模型**不得直接**写世界状态；不得进入 `state_hash` /
   `rng_state_digest` / `event_chain_hash` 的**计算**；不得成为回放的必要条件。
2. **「直接 / 间接」限定语（必写）**：禁止的是**直接**写入；**间接**仅允许经
   「规则层决策 + `output_schema` 校验 + 事件日志」这一条路径产生事件内容，且该能力**必须可回放**（cassette 强制）。
3. **provider 类别绑定（default-deny）**：以世界模型为后端的 `imagine.*` 能力，其 provider 的
   `class` **必须**声明为 `remote_api`；`local_model` / `deterministic_rule` / `cassette_replay` 三类若
   `source_model` 命中世界模型白名单（`capability.schema.json` 的 `x-provider-class-binding.world_model_whitelist`）
   → **校验期拒收**。负例见 `spikes/s7-capability-binding/`。
4. **确定性闸门（禁止面）**：**非 `deterministic` 类 provider 的输出不得被规则层采纳为事件输入**；
   校验期**必跑**一致性检查（同输入重复 ≥3 次 → 输出摘要一致），未通过即拒收（不得留到 V1 事后测量）。
5. **tick 与耗时解耦**：tick 的**编号**与**事件内容**不得由实测耗时派生。
6. **已声明边界（不得写成「零影响」）**：呈现层 `non_deterministic` 的生成画面会影响**玩家意图的分布**，
   而意图事件本身在链哈希内；按 RA-2 先例登记为**已声明边界**，不宣称零影响。

## 1. 三处接入点（全部复用 D-0.6 槽位机制）

| # | 接入点 | 层 | 输入 | 输出 | 影响世界状态 |
|---|---|---|---|---|---|
| ① | `WorldModelRenderAdapter` | L1 渲染层 | 内核权威状态的**只读投影**（camera / scene + tick 号） | 画面（帧 / 纹理 / 高斯场景） | **否**（只影响画面） |
| ② | 离线内容生产管线 | 内容层（**离线**） | 生成请求（街区 / 室内 / 道具草稿） | 候选资产 + `asset.manifest` | 否（人工收编后才成为 pack 数据） |
| ③ | `capability:imagine.*` | L5 认知层（**能力槽位**） | 结构化情境（观察 + 记忆摘要，不含 secrets） | 结构化预测（`output_schema` 强校验） | **间接**（经规则层 → 事件日志） |

②与 AC-15 的离线内容管线是**同一条管线**（见 `content-pipeline.spec.md`），不得另建。

## 2. 七项必答（`01 §16.1.3` 逐条）

### 2.1 输入 / 输出契约

- **呈现适配器（①）**
  - 输入 `RenderRequest`：`{ tick:int, camera:{pos_mm,look_at_mm,fov_deg}, scene_projection:{entities:[{id,kind,transform}], lighting:{color_temp_k, intensity}}, style:{palette_id, mood_label} }`
    —— `scene_projection` 是**只读投影**（内核状态的拷贝，非引用）；**不得**携带 secrets / 玩家原文。
  - 输出 `RenderFrame`：`{ tick:int, kind:enum[static_placeholder|generated_frame|gaussian_splat], ref:string, produced_at_ms:int|null }`
    —— 只有 `ref`（画面句柄）交给渲染层；**不得**含任何世界状态写回字段。
- **`imagine.*` 能力（③）**：走 `capability.schema.json`。
  - `imagine.predict`：输入 `{ situation_digest, observation_refs[], memory_summary, horizon_ticks }`；
    输出 `{ predictions:[{entity_id, action_guess, confidence}], rationale_code, horizon_ticks }`。
  - `imagine.rollout`：输入 `{ situation_digest, candidate_actions[], horizon_ticks }`；
    输出 `{ rollouts:[{action, expected_valence_delta, expected_need_delta{...}}], rationale_code }`。
  - 两者输出**必须**过 `output_schema`（`additionalProperties:false`）；文本字段一律为**枚举码**，不得回传自由文本。

### 2.2 与 tick 的对齐

- 适配器是**异步只读消费者**：允许「晚一帧」，但**不得**反向阻塞内核 tick。
- 能力结果**在 tick 边界丢弃、绝不回填**（与 D-0.9 第 3 条、AC-2 一致）：迟到结果只记 metric。
- 调度抖动（G2 的 tick 抖动指标）只影响**调度**，不影响 tick 编号与事件内容。

### 2.3 确定性策略（两类显式标注）

| 类 | 允许出现的位置 | 约束 |
|---|---|---|
| `deterministic` | 任何层（含规则层输入） | 同 seed + 同输入 → 同输出摘要；可 cassette 回放；校验期一致性检查 ≥3 次 |
| `non_deterministic` | **只允许呈现层** | 必须在契约里写明「其结果**不得**进入任何哈希、不得用于回放判定」；`allowed_in_rule_layer` 必须为 `false` |

### 2.4 失败回退（可审计 + 可回放）

- 超时 / 失败 / schema 非法 → 回退到确定性占位：
  - 呈现层：静态占位场景或上一帧；
  - 能力层：`deterministic_rule`。
- 每次转移**必须**落 `capability.fallback{capability, from_provider, to_provider, reason}`（含中间转移），
  且该次回退**可回放**（cassette 命中即逐字节等价）。

### 2.5 预算

- 每能力**自己**的 `timeout_ms` / `latency_ms_budget`，按 `capability.time-budget.spec.md` 由**实测标定**；
  REQ 不钉毫秒数，也不得用全局常量代替。
- 预算记账沿用三级账本（tick / NPC 日 / 会话影响）；世界模型调用计入 `imagine.*` 的能力预算。

### 2.6 安全

- 能力上下文**不得**携带 secrets（`safety.secrets_in_context=false` 为硬约束）。
- 输出**必须**过 `output_schema`；provider 返回的文本**不得**直接进入内核逻辑（必须结构化）。
- 提示词注入面：玩家可控文本只以 `*_digest` / 枚举码形式进入上下文（`prompt_injection_guard`）。

### 2.7 注册方式（新增能力不改内核代码）

- 新增一个 `imagine.*` 能力**只需**注册数据 + 契约校验；内核既有源码**字节不变**（沿用 AC-13 / ADR-006 判据）。
- 世界模型后端的能力必须声明为 `remote_api`（§0 第 3 条），因此**注册即受 default-deny 校验**。

## 3. 崩溃恢复语义（与快照锚点相关）

- 世界模型能力的调用结果**不进入**检查点语义：检查点锚点只由事件日志决定（`INVARIANT-ECH-1/2`，见
  `snapshot.schema.json`）。因此世界模型不可用时，恢复路径**不需要**任何世界模型 provider。
- 呈现层适配器无持久状态；重启后从「上一帧 / 静态占位」重新开始，不写任何世界状态。

## 4. 无 NVIDIA GPU（M5 Pro / 24GB）可行性

- 生成式世界模型（Cosmos / HunyuanWorld 级）：**本机跑不动** → 只能离线云或 API；
  **不得声称在本机跑过**（未跑 → **GAP**）。
- 神经渲染（`nerfstudio-project/gsplat`、`graphdeco-inria/gaussian-splatting`）：训练 / 优化可在 CPU/MPS 上离线跑（慢），
  运行时只做**加载 + 渲染** → 列为 V1 候选，**需实测**（未实测 → **GAP**）。

## 5. V1 实验门禁判据（阈值 = 建议初值，**待 PM / 用户确认**）

| # | 判据 | 度量方法（脚本形态） | 建议初值（待确认） |
|---|---|---|---|
| G1 | 保真度 | `scripts/g1_fidelity.py`：非物理场景与内核权威投影参考帧比 SSIM（`--ref-frames` 目录 + `--gen-frames` 目录）；`imagine.*` 结构化输出 schema 合法率 | SSIM ≥ 0.85；合法率 ≥ 99% |
| G2 | 端到端延迟 | `scripts/g2_latency.py`：呈现适配器 p95 单帧耗时、`imagine.*` p95、内核 tick 抖动增量（同 seed 双跑对比） | 呈现 p95 ≤ 500 ms（异步）；imagine p95 ≤ 声明 `timeout_ms`；tick 抖动 ≤ +5% |
| G3 | 确定性 / 可回放 | `scripts/g3_determinism.py`：同 seed 同输入 N=20 次输出摘要一致率 + cassette 回放逐字段 diff | 一致率 100%（`deterministic` 类）；回放 diff 为空 |
| G4 | 单位成本 | `scripts/g4_cost.py`：每 1000 次 imagine 调用成本 / 每生成分钟视频成本（离线云计价 + 实测耗时） | **阈值待 PM / 用户给定**（本轮只给公式 + 实测方法） |
| G5 | 可控性 | `scripts/g5_control.py`：对抗提示（越界 / 越权 / 违规）N 次 → 违规率；一键关闭且不改内核 | 违规率 ≤ 1%；关闭 = 配置级 |

- 上述脚本形态**本轮不实现**（AC-14 只要求「给出度量方法与判据」）；实现属 V1。
- 未达标 → 保持「仅呈现层」；达标才允许扩大接入面。

## 6. V0 边界（写死）

- V0 **不包含**世界模型运行时集成，只包含**适配器接口 + 占位实现**（静态呈现 / 确定性结构化回退，可被 provider 切换）。
- 见 `08_v0_plan.md` 的「V0 明确不做」节与 W0c 工作项。

## 7. 与 AC 的对应

- **AC-14**：本文件 = 适配器契约；`07_adr.md` ADR-010 = 裁决；`06_open_source_matrix.md` L13 = 选型；
  `08_v0_plan.md` = V0 边界。
- **AC-13 / D-0.6**：能力槽位机制复用；`capability.schema.json` 的 `imagine.*` 槽位与 provider 类别绑定。
