# 07 · 架构决策记录（ADR）

- 计划：`REQ-20260921-002-deephealing-architecture-freeze`　作者：artisan　日期：2026-09-21
- 格式：**背景 / 选项 / 决定 / 后果**；每条附**证据**（真跑日志绝对路径）与**成本项**
- 必答主题覆盖：ADR-001 内核语言、ADR-002 渲染引擎、ADR-003 同步方案、ADR-004 记忆存储、ADR-005 模型通道、ADR-006 provider 抽象与结构化输出、**ADR-010 世界模型接入（AC-14）**、**ADR-011 AIGC 素材生产与许可合规（AC-15）**；ADR-007~009、ADR-012 为自选/重编号条目。
- **条数口径（round 3 注明）**：AC-9 的 REQ 字面要求是「≥8 条（含 ADR-10/11 则 ≥10）」；`07_adr.md` 实际 12 条。
  本轮任务书另要求「条数 ≥ 12」——**这是 architect 自设的更高门槛，不是 REQ AC-9 的判据**，审计时不得拿它当 AC-9 判定。
- **编号规则**：`ADR-010` = 世界模型接入、`ADR-011` = AIGC 素材生产、`ADR-012` = 记忆/自进化受控边界（原 ADR-010）。
  旧→新映射与全库引用清扫表见文末「ADR 编号规则与重编号记录」。

---

## ADR-001 · 内核语言：Python（自研薄内核）而非 Rust / TS

**背景**：世界内核要承担固定 dt tick、确定性 RNG 分流、事件哈希链、快照、能力注册表调度、记忆读写。AC-2 的判据是「同一事件日志重放两次 → 全部检查点 `state_hash` 一致」，即**确定性优先于吞吐**。

**选项**
1. **Python 3.13（本机 3.13.13 + uv 0.12.1 已装）**：与 L4 认知/L6 记忆同语言；stdlib 足够（hashlib/json/sqlite3）。
2. Rust（hecs/bevy_ecs + rapier）：性能上限高、确定性可做，但 **本机 Rust 未装**（无 cargo/rustup）→ 需先补工具链 + 跨语言边界（PyO3/FFI 或把认知层也搬过去）。
3. TypeScript（bitECS）：会把权威推到 Node/浏览器侧，与「内核唯一权威」冲突。

**决定**：**V0 用 Python 3.13 自研薄确定性内核**（`02_source/v0_skeleton/kernel/`，接口已冻结）。Rust 性能路线在 V1 之前做一次独立性能 spike 再决策。

**后果**
- ✅ S1 spike 证明：纯 stdlib 就能实现 tick/RNG 分流/哈希链/快照/重放，**双跑哈希逐位一致**（`388a1a51833f04b0ad674c01a2a879511a58a1ae1eee10f414cfee3e98aa659e`），两个非确定性负例都被检出（证据：`spikes/s1-determinism/logs/run_s1.summary.log`，exit 0）
- ✅ 省掉跨语言边界与第二套类型系统；认知/记忆/内容校验都在同一进程
- ⚠️ **成本项**：Rust 未装 = 任何 Rust 候选（hecs/rapier/bevy）都附带「先装工具链 + 构建管线」的前置成本；无 NVIDIA GPU 使「本地大模型 + Rust 推理服务」路线不可行
- ⚠️ V1 若需要更高 tick 吞吐，迁移成本高（事件/快照/能力契约是语言无关的，但实现要重写）；缓解：契约先冻结（本轮已做），迁移时用同一套 JSONL/哈希判据验收

---

## ADR-002 · 渲染引擎：three.js（非 R3F / Babylon / Godot）

**背景**：L1 渲染层只需消费 `snapshot/delta/event`，渲染 3D 场景 + 双模式 UI，**零业务逻辑、零模型调用**。V0 规模：1 栋楼 + 5 住户 + 60 fps 目标 / 30 fps 下限（5 NPC 单栋楼）。

**选项**
1. **three.js（MIT，npm 实查 0.186.0）**：事实标准，生态最大，WebGL2/WebGPU 路径在推进。
2. @react-three/fiber（MIT，9.7.0）：声明式组件化，适合 HUD/UI，但引入 React 运行时。
3. @babylonjs/core（Apache-2.0，9.27.1）：功能更全（自带物理/导航），bundle 更重。
4. Godot（导出 Web）：引擎即权威，架构不匹配；且上游 license 抓取失败（社区共识 MIT，**未取得权威响应**）。

**决定**：**adopt three.js**；R3F 保留为 V1 组件化选项；Babylon / Godot / playcanvas reject（V0）。

**后果**
- ✅ S3 真跑：`tsc` exit 0、`vite build` exit 0（`dist/assets/index.js` 478.10 kB / gzip 120.94 kB）、WebGL2 真渲染截图 2 张（`spikes/s3-render/out/*.png`）、11 项治愈系数值断言全通过（证据：`spikes/s3-render/logs/run_s3.summary.log`，exit 0）
- ✅ 渲染层保持「薄」：场景断言里 NPC=5/楼=1/可交互物=2/灯=3，全部来自数据
- ⚠️ **成本项**：`playwright@1.63` 期望 `chromium_headless_shell-1243`，本机缓存是 `chromium-1234` → 截图脚本回退系统 Chrome（已实测可用）；纯 headless-shell 需 `npx playwright install chromium`
- ⚠️ three.js 无内建物理/导航：V0 用自建路点图，V1 视需要接 recast-navigation（MIT）或 yuka（MIT）
- ⚠️ R3F 若 V1 引入，需重新评估「渲染层零业务逻辑」的边界（组件树容易藏逻辑）

---

## ADR-003 · 同步方案：自研最小权威 WS 传输（非 Colyseus），含双权威风险

**背景**：L2 会话传输层要处理会话建立、双模式鉴权（observe/participate）、增量同步、意图上行。架构硬规则：**内核是唯一权威**，L2 只搬运。R7 风险即「传输层持状态并回写 → 状态分叉」。

**选项**
1. **自研最小 WS 传输（Node + `ws`，MIT 8.21.3）**：无状态搬运，权威留在 Python 内核。
2. **colyseus（MIT，0.18.6）**：成熟房间/状态同步/重连，但**假定权威在 Node 侧**（`Room` + `setSimulationInterval` 就是权威循环）。
3. nakama（Apache-2.0）：生产级社交后端，引入部署面。
4. networked-aframe（MIT）：A-Frame 生态绑定。

**决定**：**V0 自研最小 WS 传输**（`02_source/v0_skeleton/session/`，接口已冻结）；V1 若需要房间/重连/匹配能力再评估 colyseus，**但必须先解决权威归属**。

**后果**
- ✅ 双权威风险 R7 从结构上消失：L2 无世界状态真值、无规则计算、无模型调用（契约级禁令，Sentinel 静态检查项）
- ⚠️ 自研要自己实现重连、心跳、seq 去重、背压 —— 这部分工作量真实存在（已列入 `08_v0_plan.md` 的会话层任务与工时）
- ⚠️ **colyseus 的实测成本**（S4 真跑）：143 个顶层依赖目录 / **196 MB** / 首次安装约 3 分钟；`@type` 装饰器裸 Node 解析不了（需 TS/babel 构建步骤）；`defineTypes` 已 deprecated；客户端必须 `@colyseus/sdk@0.18.2`（旧 `colyseus.js@0.16` 协议不兼容，报 `Cannot read properties of undefined (reading 'name')`）；`Room` 需从 `@colyseus/core` 导入；`@colyseus/schema` 版本强耦合 `^5.0.8`（首次安装直接 ERESOLVE 失败）。证据：`spikes/s4-colyseus/logs/run_s4.summary.log`（exit 0）、`logs/npm_install.log`（ERESOLVE 全文）
- ⚠️ 若 V1 采用 colyseus，必须选一条：① 把权威搬到 Node（推翻 ADR-001）② 引入内核↔Node 权威桥（新增一致性面，R7 入口）→ **本轮倾向保持 ①「不采用」**

---

## ADR-004 · 记忆存储：V0 sqlite + numpy 余弦 → V1 sqlite-vec（非 LanceDB / 外部服务）

**背景**：L6 记忆三层（working 环形缓冲 / episodic 事件索引 / semantic 事实），检索用嵌入余弦。边界：记忆**不得**绕过 schema 写世界状态，只影响认知输入与规则层打分。R10：无裁剪会无界增长。

**选项**
1. **sqlite（stdlib）+ numpy 余弦**：零外部服务、零网络；表结构可冻结。
2. sqlite-vec（MIT/Apache-2.0 双许可，PyPI 0.1.9）：sqlite 扩展，向量检索下推到 C。
3. LanceDB（Apache-2.0，PyPI 0.39.0）：列式 + 向量，规模化更强。
4. mem0 / letta / graphiti（均 Apache-2.0）：自带 agent 运行时与记忆 ownership，与内核抢权威。
5. pgvector（待核）/ qdrant（待核）：需部署数据库服务。

**决定**：**V0 = sqlite + numpy 暴力余弦**；**V1 首选 sqlite-vec**（同栈、迁移成本最低）；LanceDB 作 V1 备选；服务型向量库本轮不引入。

**后果**
- ✅ 无服务依赖 → 记忆层不会成为第二权威；离线可跑（与 AC-3 的离线降级一致）
- ✅ 裁剪策略明确：重要性阈值 + 时间衰减（`decay_half_life_ticks`）+ 每 NPC 容量上限；反思结果保留 `superseded_by` 可回滚
- ⚠️ 暴力余弦在 NPC 数与历史长度上去后会成为瓶颈：5 NPC × 数百条 episode 无压力，**多街区/长历史（V1）必须换 sqlite-vec**（已列 V1）
- ⚠️ 嵌入质量决定检索质量：`embed.text` 的 `deterministic_rule` 兜底（n-gram 哈希）**语义质量不保证**，只保证「同输入同输出」，属认知降质而非正确性判据
- ⚠️ 许可：mem0/letta/graphiti 均 Apache-2.0 可商用，但架构冲突（reject）；pgvector/qdrant 许可**待核**，不得引入

---

## ADR-005 · 模型通道：远端为可降级的能力补充 provider（默认路径允许降级）

**背景**：AC-7 要求 LLM 只做「意图规划 / 情绪评估 / 记忆反思 / 叙事生成」四类高层能力，全部经注册表，规则层给预算与超时；AC-10 给出成本预算；R2 是成本失控。

**选项**
1. **远端 OpenAI 兼容 API**（实测 `https://api.tokenfab.cn/v1`，`deepseek-v4.1-flash`）：零部署、可结构化输出。
2. **本地推理**：ollama（本机已装可执行文件，**未启动/未真跑**）、vllm/SGLang（**无 NVIDIA GPU** → 不可行）、transformers CPU 小模型（可行但慢）。
3. **浏览器内推理**（web-llm / transformers.js，均 Apache-2.0）：违反「渲染层零模型调用」。
4. **混合**：远端为**可降级的能力补充 provider**（默认路径允许降级）+ `deterministic_rule` 兜底 + cassette 回放保证可复现。

**决定**：**V0 = 远端为可降级的能力补充 provider，默认路径允许降级；`deterministic_rule` 为终态兜底；`local_model` 保留 provider 位但 V0 不启用**。三层预算硬顶 + 五级降级阶梯。
**声明值（round 3 修订，D-0.9）**：`timeout_ms` / `latency_ms_budget` 改为**该能力自己的、由实测标定的声明值**（推导规则先冻结 + 敏感性对照，见 `spikes/s5-latency-calibration/` 与 `02_source/capability.time-budget.spec.md`）；REQ 不钉毫秒数，取证不得用 `--timeout-ms-override`（合成负例例外除外）。

**后果**
- ✅ S2 真跑：`emotion.appraise` / `intent.plan` 经 `remote_api` 成功产出结构化结果；单次实测 2.33s（含 reasoning tokens）
- ✅ 离线可用性由 `cassette_replay` + `deterministic_rule` 保证：断网回放（socket 全封）3 叶全部成功且**逐字段等价**
- ⚠️ **实测偏差（必须记）**：能力声明的 `timeout_ms=2500/3000` 对推理模型**偏紧**，首轮直接超时降级。spike 用 `--timeout-ms-override 20000` 完成真跑 → 建议 V0 把规划/评估类能力 `timeout_ms` 提到 **8~15s**，或强制这两类走 cassette/规则层（已登记 `09_risks_open_questions.md` Q1）
- ⚠️ **成本与账单**：远端 API 按 token 计费，`capability.cost` 里的单价是**声明值**（USD/1k），需在 V0 用真实账单校准；`BudgetLedger` 三级硬顶是唯一护栏
- ⚠️ **许可**：远端服务属采购/账号条款（非开源许可）；vllm/ollama 的 license 在上游抓取为 `NONE` → **待核**，启用本地通道前必须确认
- ⚠️ 本地通道未验证：`local_model` 在本轮**无真跑输出**（GAP），V0 若要用必须先补 spike

---

## ADR-006 · 原子能力 provider 抽象与结构化输出：capability 契约 + instructor/jsonschema 强校验 + cassette fail-closed

**背景**：D-0.6 / AC-13 要求「原子能力注册与补充机制」：能力槽位与 provider 分离（四类）、新增能力不改内核代码、四类 provider 输出 schema 合法性与决策可推进性必须等价。R11：模型输出不合规进入世界 = CRITICAL。

**选项**
1. **能力描述文件（`*.capability.json`）+ 数据 glob 发现 + 显式 provider 适配器**：能力=契约，provider=实现，规则层按 slot 调用。
2. 把能力写进代码（注册表硬编码/装饰器自动注册）：改能力要改源码 → 违反 AC-13。
3. 只用 LLM 框架的 agent 抽象（pydantic-ai/langgraph）：框架自带运行时假设，且「能力」与「agent」概念错位。
4. **结构化输出方案**：`instructor`（MIT，1.17.0，重试+校验）vs `outlines`（Apache-2.0，1.3.3，约束解码）vs 裸 `jsonschema` 校验。

**决定**：
- 能力用 **`capability.schema.json` 契约 + `capabilities/**/*.capability.json` 数据发现**（无 import 列表、无 if 分支）
- provider 四类：`remote_api` / `local_model` / `deterministic_rule` / `cassette_replay`；**模型调用只允许出现在 provider 适配器内**（契约级禁令）
- `providers[].impl` **必须可解析**（round 2 落地）：`builtin:<name>` 走白名单枚举，`module:<mod>:<fn>` 只允许**显式登记项**（`providers/` 适配器目录内实际存在的模块文件）；不可解析即 `E_IMPL_NOT_REGISTERED`，注册表拒绝加载。新增能力 = 新增能力数据 + 新增 adapter 文件
- 结构化输出：**instructor 为主（V0）、outlines 为对照（V1 本地推理配套）、`jsonschema` 作为每次调用的强制校验闸门**
- `determinism.mode=replayable` 的能力在回放模式强制 `cassette_replay`，**miss 默认 fail-closed**（`E_CASSETTE_MISS`）；回放录制源由**历史 `capability.invoked` 事件**确定（`cassette.format.md` §4.2），目录内多录制源共存即 `E_CASSETTE_AMBIGUOUS_SOURCE`
- cassette 完整性（`hash` + `prev_hash` 链）在「命中即校验 / 回放前置 / validate 前置」三个时机强制校验，不符即 `E_CASSETTE_TAMPERED`（`cassette.format.md` §4.3）——`output_schema` 合法不免除完整性校验

**后果**
- ✅ S2 真跑证明 AC-13 可达成（**判据口径 round 2 已改写，见下**）：丢入 `relation.infer@1.0.0.capability.json` + `providers/rules_relation_infer.py` + 规则层数据加一个 leaf → 注册表 3→4、调用成功。
- ✅ **判据口径（冻结，替代 round 1 的「整体指纹前后一致」）**：**既有内核源码文件字节不变，只新增数据 + adapter**。验证方式：`before`/`after` 两份 `kernel-digest` 求差集——`changed` 必须为空（每个 before 中存在的文件在 after 中 sha256 相同），`added` 必须全部落在 adapter 目录 `providers/*.py`。证据：`spikes/s2-capability-cassette/logs/s2_kernel_delta.json` = `{"changed":[],"added":["providers/rules_relation_infer.py"]}`；`engine.py` 前后 sha256 均为 `96df7b716ca9bc2d9902ff814bba8e150283e04e8791ba3ee77c5af67994b8c9`。
  - 为什么改口径：round 1 的 `before` 指纹取自**已包含新能力实现**的源码（`engine.py` 里硬编码 `"relation.infer": rule_relation_infer`），等于用结果证明结果（RB-1）。现在实现整体搬进 adapter 文件，`engine.py` 不含任何 `relation.infer` 分支，`before` 基线不再可能包含它。
- ✅ 三类 provider 都真跑出结果（remote / cassette / rule），且 remote→cassette 输出**逐字段等价**（录制源由历史事件日志确定，不再靠目录枚举）。
- ✅ **schema 闸门有实战价值**：真实模型把 `new_facts` 返回成字符串数组（应为对象数组）→ `jsonschema` 判 `on_invalid_schema` → 自动降级到 `deterministic_rule`。这不是构造的失败路径。
- ✅ **每一次 provider 降级转移都落 `capability.fallback` 事件**（round 2 实装；含中间转移与终态失败）。中间降级可由事件流重建：`spikes/s2-capability-cassette/logs/s2_midchain.chains.json` 显示每条链都从入口 provider 起、逐跳连续。
- ✅ **cassette 完整性有闸**：`valence 0.08 → -0.9` / `mood_label tired → irritated` 这类**仍满足 schema** 的篡改会被 `E_CASSETTE_TAMPERED` 拦住（round 2 负例真跑）。
- ⚠️ instructor 的 `uv pip install` 会拉入 openai/httpx 等（实测 exit 0）；`outlines` 拉入 outlines-core + pillow。两者都只在**能力层**出现，不得被业务模块直接 import（Sentinel 静态检查）
- ⚠️ `local_model` provider 本轮无真跑（GAP）；四类等价性里这一类只有声明
- ⚠️ cassette 的「逐字节等价」依赖 `canonical_input_hash` 与规范化实现**跨语言一致**；V0 实现必须共用一份 `canonical_json`（已在 `tools/canonical_json.py` 落位），否则跨语言回放会假 miss
- ⚠️ 玩家可控文本进入能力上下文 = prompt injection 面：`safety.prompt_injection_guard` 已进契约（`delimit_and_ignore_instructions` / `allowlist_fields`），V0 必须实装而非仅声明

---

## ADR-007 · 事件日志哈希链 + 事件溯源式回放（而非「重跑同一随机序列」）

**背景**：AC-2 判据要求「同一事件日志重放两次 → 全部检查点 state_hash 一致」，并要能**检测**非确定性（R1）。

**选项**
1. **事件溯源**：状态 = 事件日志的纯函数；回放路径不引入 RNG（S1 采用）。
2. 重放时重跑同一随机序列：需要 RNG 状态完全可序列化且与决策顺序强耦合，任何子系统改动都可能扰动。
3. 只存快照（不存事件）：无法定位分歧，也失去审计能力。

**决定**：**事件溯源 + `hash = sha256(prev_hash || canonical_json({seq,tick,type,actor,payload}))` + 每 50 tick 快照**；事件 payload 携带写入后的组件快照（`state_after`）与 RNG 流摘要（`rng_digests`），使状态成为日志的纯函数。

**后果**
- ✅ S1 真跑：8 个检查点双跑一致（`388a1a51…`），两个负例（wall-clock / 迭代顺序泄漏）各造成 **8/8 检查点分歧** → 判据非空转
- ✅ 分歧可定位：`--dump-divergence` 输出分歧 tick 的组件级 diff（接口已在 `snapshot.py` 冻结）
- ⚠️ 日志体积：S1 规模 200 tick × 5 NPC = 1009 行；按 20 MB/小时上限（AC-10）需滚动策略，且 `state_after` 会放大体积 → V0 需实测（已登记 Q3）
- ⚠️ 「重放 = 新内核实例 + 同一日志」意味着**回放不能改历史**：任何「补录」都会破坏链，必须重开日志

---

## ADR-008 · 内容层：district pack 数据驱动（含 portals 数据建边），不改内核代码

**背景**：AC-6 要求「新增第二街区不改内核代码」，且有迁移路径与校验方式。

**选项**
1. **自研 pack 规范**：`pack.json`（id/version/engine_range/bounds/license/entrypoints/portals）+ 数据文件 + `pack.sig` 完整性清单。
2. 直接复用现成城市数据格式（osmnx/GeoJSON/UrbanWorld2.0）：只解决几何，不解决 NPC/任务/日程/签名/迁移路径。
3. 把街区写进内核代码分支：直接违反 AC-6。

**决定**：**自研 pack 规范**（`district.pack.schema.json` + `district.pack.spec.md`），跨区连接**只在 `portals[]` 声明**，内核按数据建边；目标 pack 未加载时边标 `inactive`（不报错、不崩）。

**后果**
- ✅ 样例 pack 13 个文件已签名，`verify_pack.py` exit 0；**篡改任一文件后 exit 1**（负例证据：`spikes/logs/verify_specs.log` 前的篡改实验、`02_source/v0_skeleton/tools/verify_pack.py`）
- ✅ 迁移路径可照抄：复制目录 → 改 `pack.json` → `pack sign` → `validate` → `run`，改动仅落在 `districts/**`
- ⚠️ `engine_range` 与内核契约版本必须同步维护：新数据配旧内核会静默出错 → 已做成**硬校验**（不满足即 `E_PACK_INVALID`）
- ⚠️ 一个内核实例同时只加载一个主 pack（跨区经 portals）是 V0 简化；多 pack 并存会引入状态合并的确定性复杂度 → V1 再议
- ⚠️ 内容层禁止可执行文件（`.py/.js/.sh` 一律拒绝）—— 已实装，`pack_sign.py` / `verify_pack.py` 都会拦

---

## ADR-009 · 双模式权限与介入护栏：observe 硬拒 + 参与走策略（含预算/冷却/审计）

**背景**：AC-4 要求双模式权限模型与同步协议，且「参与影响任务迭代演进」必须有防滥用边界。R12 是刷分/滥用。

**选项**
1. **权限在传输层判定 + 策略在数据里声明**（`intervention.policy.schema.json`）：observe 上行一律 `E_MODE_READONLY`；participate 走 forbidden→rate_limit→cooldown→impact_budget→入队。
2. 把权限写进内核（内核判会话模式）：内核不该知道会话细节。
3. 不做限流，靠前端禁用按钮：可被绕过。

**决定**：**传输层做权限判定（`session/src/mode.js` 已可执行），策略数据化（`intervention.policy.schema.json`），内核只在 tick 边界应用意图**；被拒必须落 `intent.rejected` 事件（可审计、可回放）。

**后果**
- ✅ `session/test/session.test.js` 的权限判定部分**已可执行**（`node --test`）：observe 上行返回 `E_MODE_READONLY`、未知模式抛 `E_SCHEMA_INVALID`
- ✅ 任务演进护栏数据化：`adaptation_rules[].max_shifts` + `impact_cost` + `forbidden_actions[]` + 全量审计
- ⚠️ 影响预算的**计量口径**必须与事件一致（`impact_cost` 只认 `intent.applied`）；重复意图合并窗口要防「同目标高频小步」绕过
- ⚠️ 玩家文本进入能力上下文是注入面 → 审计默认只存 digest（`audit.player_text_storage=digest_only`）
- ⚠️ 会话层的限流/冷却/预算**尚未实现**（骨架只有接口）→ 属 V0 实施范围，不是本轮结论

---

## ADR-012 · 记忆/自进化的受控边界：只允许改数据化策略参数（**原 ADR-010，round 3 重编号**）

> 编号变更：本条在 round 1/2 编号为 `ADR-010`；round 3 按 REQ AC-9 字面把 `ADR-010` 让给「世界模型接入」、
> `ADR-011` 让给「AIGC 素材生产」，本条顺延为 **`ADR-012`**。历史文件中的旧编号属**历史锚定**，见文末重编号记录。

**背景**：AC-7 的自进化（QD / 自改写）有 R5「自进化失控 / 目标函数被劫持」（CRITICAL）。

**选项**
1. **只允许改数据化策略参数**（效用权重、日程模板、行为树数据），内核源码不可改；五步护栏（提案→沙箱回放评估→审批→灰度→回滚）。
2. 允许自改代码（dgm 原始形态）：护栏无法保证可回滚/可复现。
3. 不做自进化。

**决定**：**V0 只冻结契约与护栏（不启用改写）；V1 启用档案库 + QD（pyribs，MIT）；V2 才启用受控自我改写**。硬性：改写必须能用事件日志回放复现，且目标函数含治愈向硬约束。

**后果**
- ✅ 与 ADR-007（事件溯源）天然配合：任何改写都能用「同一日志 + 新数据」复现与比对
- ✅ 与 ADR-008（数据驱动）配合：策略参数在内容包里，改写 = 改数据 = 可 diff 可回滚
- ⚠️ 「只改数据」意味着表达力受限：需要新行为模式时仍要人工改代码 → 这是**有意**的限制（换取可审计）
- ⚠️ 目标函数（治愈向）目前只有文字约束 + 少量数值（`healing_delta`），V1 启用前必须先把它做成可计算指标，否则护栏是空的
- ⚠️ pyribs 的 PyPI 版本是 `0.0.2`（GitHub 仓库 MIT、2026-07 活跃）→ V1 引入前需核对 PyPI 包与仓库的关系（已登记 `09_risks_open_questions.md` Q5）

---

## ADR-010 · 世界模型接入裁决：接入但不做权威（AC-14 / D-0.7）

**背景**：用户提问「是否接入世界模型引擎」。文献（arXiv 2609.10540 / 2607.14076 / 2608.06257）指出生成式世界模型**缺乏持久世界状态与可编程规则**，多人权威共享状态仍是开放问题；而本项目的硬需求恰是**确定性回放（AC-2）+ 可编程规则（D-0.2）+ 双模式权威写入（AC-4）+ 可审计（AC-12）**。

**选项**
1. **不接入**：放弃「梦境 / 回忆 / 创伤空间」等非物理场景与 NPC 想象推演的表达力。
2. **接入并作为仿真权威**：把世界状态交给生成模型。→ 与 AC-2/AC-4/AC-12 直接冲突（无法可编程、无法逐字节回放、无法审计）。
3. **接入但不做权威**（三处接入点 + 能力槽位 + V1 实验门禁）。**← 采用**

**决定**
- **权威归属（冻结）**：权威始终是**确定性内核**。世界模型**不得直接**写世界状态、不得进入 `state_hash` / `rng_state_digest` / `event_chain_hash` 的**计算**、不得成为回放的必要条件。
  - **「直接 / 间接」限定语**：禁止的是**直接**写入；**间接**仅允许经「规则层决策 + `output_schema` 校验 + 事件日志」这一条路径产生事件内容，且该能力**必须可回放**（cassette 强制）。
  - **已声明边界**（不得写成「世界模型对世界状态零影响」）：呈现层 `non_deterministic` 的生成画面会影响**玩家意图的分布**，而意图事件本身在链哈希内；按 RA-2 先例登记为**已声明边界**。
- **三处接入点**（全部复用 D-0.6 能力槽位机制，**禁止第二调用路径**）：
  ① `WorldModelRenderAdapter`（L1，只影响画面）；② 离线内容生产管线（与 AC-15 **同一条管线**）；③ `capability:imagine.*`（L5 能力槽位，输出结构化、**间接**影响事件）。
- **provider 类别绑定（default-deny）**：以世界模型为后端的能力其 provider **必须**是 `remote_api`；其余三类若 `source_model` 命中世界模型白名单 → **校验期拒收**（`x-provider-class-binding` + `verify_capability_binding.py`）。
- **闭源 API vs 开源自托管**：闭源 API（Genie 3 / Oasis·Mirage / Odyssey / Marble）**接入成本低但不可控**（黑盒、版本漂移、无离线）→ 只允许用于**离线内容生产 / V1 实验**；开源自托管（Cosmos / HunyuanWorld-1.0 / 3DGS·gsplat）**可控可复算** → **V1 主候选（离线侧）**。
  - ⚠️ **许可二次核对结果（round 3 真查，与 `01 §16.1.4` 的旧表述不同，必须以此为准）**：`NVIDIA/Cosmos` = **OpenMDW-1.1（自定义）**、`Tencent/HunyuanWorld-1.0` = **腾讯社区许可（含地域限制）**、`graphdeco-inria/gaussian-splatting` = **Inria/MPII 自定义许可**（`LICENSE.md`，非商用倾向）、`nerfstudio-project/gsplat` = **Apache-2.0 ✅**、`danijar/dreamerv3` = MIT。⇒ 开源侧**只有 gsplat / dreamerv3 可直接判可商用**，其余**待核**（证据 `spikes/facts-license/r3.summary.txt`，命令 `bash spikes/facts-license/probe_facts_r3.sh`）。**不得**再写「Cosmos Apache-2.0」。
- **无 NVIDIA GPU（M5 Pro / 24GB）可行性**：生成式世界模型**本机跑不动** → 只能离线云或 API，**不得声称在本机跑过**（未跑 → **GAP**）；神经渲染（gsplat / gaussian-splatting）训练可在 CPU/MPS 离线跑（慢），运行时只加载 + 渲染 → V1 候选，**需实测**（未实测 → **GAP**）。

**V1 实验门禁判据**（阈值 = **建议初值，待 PM / 用户确认**；脚本形态见 `02_source/worldmodel.adapter.spec.md` §5，本轮**不实现**）

| # | 判据 | 度量方法 | 建议初值（待确认） |
|---|---|---|---|
| G1 | 保真度 | `scripts/g1_fidelity.py`：与内核权威投影参考帧比 SSIM；`imagine.*` 输出 schema 合法率 | SSIM ≥ 0.85；合法率 ≥ 99% |
| G2 | 端到端延迟 | `scripts/g2_latency.py`：呈现适配器 p95 单帧；`imagine.*` p95；内核 tick 抖动增量 | 呈现 p95 ≤ 500 ms；imagine p95 ≤ 声明 `timeout_ms`；抖动 ≤ +5% |
| G3 | 确定性 / 可回放 | `scripts/g3_determinism.py`：同 seed 同输入 N=20 次输出摘要一致率 + cassette 回放逐字段 diff | 一致率 100%；回放 diff 为空 |
| G4 | 单位成本 | `scripts/g4_cost.py`：每 1000 次 imagine / 每生成分钟视频成本 | **阈值待 PM / 用户给定**（本轮只给公式 + 实测方法） |
| G5 | 可控性 | `scripts/g5_control.py`：对抗提示 N 次违规率；一键关闭不改内核 | 违规率 ≤ 1%；关闭 = 配置级 |

**反伪造要求（`01 §16.1.6` 表，round 3 审计 RR3-22 收口，逐条必写）**

五条判据各自必须写清「**怎样才算真的测过**」，否则可被伪造通过；下表逐条对应 `01 §16.1.6` 的
「可伪造形态 / 必须补的核验要求」两列（**本轮不实现**，但 V1 判据必须照此写）：

| # | 可伪造形态 | 必须补的核验要求（逐条） |
|---|---|---|
| G1 | 只比配置 / 只报单次 | 必须报**样本数 N**、逐帧 / 逐次结果落盘、**比较器自证**（负例能被检出） |
| G2 | 只报单次延迟或均值 | 必须报**分布**（p50/p95/max）+ **样本数** + **同条件声明**；tick 抖动需与基线**同机同负载**对照 |
| G3 | 只跑 1 次 / 只比一个字段 | **N ≥ 20**、逐次输出摘要落盘、**多字段**比对、附**负例**（改一个字段必须被检出） |
| G4 | 用估算冒充实测 | 必须给**计价来源 + 实测耗时 / 调用次数**；估算部分标 **GAP**，不得写成实测 |
| G5 | 无对抗样本 | 必须给**对抗样本集（N ≥ 20）** + 违规判定规则 + **关闭动作的配置级证据** |

> 配套纪律：门禁结果必须绑定被冻结的**度量脚本 sha256**（否则阈值与度量方法可事后调）；
> 「未达标 → 保持仅呈现层」是**默认值**，且「**未跑 = 不是达标**」（`01 §16.1.6` / RR3-22 建议 2、3）。

**后果**
- ✅ 表达力与确定性解耦：非物理场景与想象推演可用生成模型，但**不进入**权威链路（`02_source/worldmodel.adapter.spec.md`）。
- ✅ 可离线：世界模型不可用时，回放路径**不需要**任何世界模型 provider（`spikes/s1-determinism` 的确定性证据不受影响）。
- ⚠️ **未实测项**：本机生成式世界模型可行性、神经渲染运行时性能 → **GAP**（不得写成已达成）。
- ⚠️ **成本/延迟不可控**：闭源 API 的版本漂移与计价变化 → 只能用于离线；G4 阈值待 PM/用户给定。
- ⚠️ 新增 `imagine.*` 槽位属契约变更（已在本轮 `capability.schema.json` 落地并注明由本条引入）。

---

## ADR-011 · AIGC 素材生产裁决：离线生产 + 许可白名单（AC-15 / D-0.8）

**背景**：项目无美术团队，美学是核心卖点 → 素材以 **AIGC 生成为主路径**；但本机 M5 Pro / 24GB / **无 CUDA**，且生成式权重的许可差异极大。

**选项**
1. 全部离线云 / API 生成（可控性差、成本高、许可与来源不可核验）。
2. **本机能跑的本机跑 + 跑不动的走离线云/API，统一走同一条离线管线 + 许可白名单**。**← 采用**
3. 不做 AIGC（放弃美学卖点）。

**决定**
- **本机可跑 / 不可跑划分**：图像 ✅（MLX + `mflux` MIT，或 `diffusers`）；音频 ✅（自托管 `ACE-Step` Apache-2.0）；**3D ❌ / 视频 ❌**（CUDA 依赖 → 离线云或 API，**绝不进运行时**）。
- **离线云 / API 边界**：生成**只发生在离线**；运行时**零生成**（强制约束 + 静态扫描判据，见 `content-pipeline.spec.md` §2）；云产出必须回到同一条管线，不得绕过 manifest 直接进 pack。
- **许可白名单与陷阱**（数据表 `asset.license.table.data.json`，**未知模型 default-deny**）：

  | 项 | 事实 | 处置 |
  |---|---|---|
  | FLUX.1-**dev** | **非商用**权重 | **禁止**进交付链（仅可本地研究，不得入库） |
  | FLUX.1-**schnell** | Apache-2.0 | 白名单 ✅ |
  | MusicGen 权重 | **CC-BY-NC**（代码 MIT ≠ 权重许可） | **禁止**进交付链 |
  | ComfyUI | **GPL-3.0** | 独立进程调用可；**不得链接进产品**（V0 只允许「独立进程 + 产物文件」） |
  | `mflux` / `Z-Image` / `Qwen-Image` / `ACE-Step` | MIT / Apache-2.0 | 白名单 ✅（逐条给 URL + 判定） |
  | Hunyuan3D-2 / TripoSG | 自有条款 / 权重未核 + CUDA 依赖 | 本轮**拒收**（保守；待离线云核验） |

- **版权灰区处理**：逐资产登记来源（模型 id / 版本 / 提示词摘要 / 种子 / 时间 / 许可）；不可商用权重**禁止出现在任何交付产物中**（含 manifest / 示例 / 截图）；不把生成物当「自有版权」宣称；对外使用前必须人工过审（`review_status=adopted` + reviewer + 时间）；IP 边界沿用 `01 §13`（只借鉴设定结构，不复制原文 / 台词 / 姓名）。
- **来源可核验性**：云 / API 产出标 `provenance.self_reported=true` 且 `verification_status=self_reported`，**不得**标「已核验」——按 RA-2 先例登记为**已声明边界**。

**成本估算（公式 + 实测基础）**
- 本机：`单位成本 = 单次生成耗时(实测) × 本机单位时间成本`；云：`= API 单价 × 调用次数 + 离线云时长成本`。
- **实测基础**：本轮**未做素材生成 spike** → 生成耗时与单价**无实测** ⇒ 成本数字一律记 **GAP**（不得用「预计」冒充）。
  已有可复用的旁证：远端模型调用延迟实测见 `spikes/s5-latency-calibration/logs/latency.distribution.json`（同 API 通道、非图像模型，**不可**直接当图像生成耗时）。
- 输出要求：每资产 / 每街区 / 每子类的成本区间 + 不确定度说明；**V0 不量产**（只需 1 张程序化占位资产 + 1 份 manifest 示例）。

**后果**
- ✅ 交付链内**没有**不可商用权重（白名单查表 + default-deny + 传递闭包 + 负例，见 `spikes/s6-asset-pipeline/`）。
- ✅ 换 EXIF / 重编码不产生新哈希的口径**已写明**；V0 示例取 `file_bytes` → 该口径 **GAP**（未实现像素解码器）。
- ⚠️ 3D / 视频本机不可跑 → 相关资产只能离线云，成本与许可均**未实测**（GAP）。
- ⚠️ ComfyUI 工作流内的 checkpoint 引用是**间接**来源面 → 已用「工作流受管登记 + 引用模型过白名单表」收口（A8）。

---

## ADR 编号规则与重编号记录（round 3）

### 规则

1. 编号只增不改：已发布的编号**不回收**；需要腾位时用**顺延重编号**（本条）。
2. 必答主题（AC-9 的 8 项）优先占用低编号；扩展主题顺延。
3. 契约 / 报告中的引用必须指向**当前**编号；历史冻结件中的旧编号按「历史锚定」保留（见豁免清单）。

### 旧 → 新映射

| 旧编号 | 新编号 | 主题 | 原因 |
|---|---|---|---|
| `ADR-010` | **`ADR-012`** | 记忆/自进化受控边界 | REQ AC-9 字面要求 `ADR-10 = 世界模型`、`ADR-11 = AIGC`；原 ADR-010 让位 |
| （新增） | **`ADR-010`** | 世界模型接入裁决（AC-14） | 满足 AC-9 字面 |
| （新增） | **`ADR-011`** | AIGC 素材生产裁决（AC-15） | 满足 AC-9 字面 |

### 全库引用清扫表

**清扫命令（原文，可复跑；`<ws>` = 本 workspace）**：

```
cd <ws> && grep -rn -I -E "ADR-01[0-9]|ADR-10[^0-9]" . \
  --exclude-dir=raven-review --exclude-dir=sentinel-review --exclude-dir=architect-verify \
  --exclude-dir=attic-round2-generated-cache --exclude-dir=attic-round3-generated-cache \
  --exclude-dir=attic-fix1-manifests-before \
  --exclude='.squad_*' --exclude='.task-*' --exclude='.run-*'
```

（`--exclude-dir` 是 spike 内的**第三方复核副本**与生成缓存归档目录；`--exclude` 是**编排过程日志**，均非交付文档。）

**逐条命中与判定（round 3 · **修复迭代 2** 于 2026-09-21T22:07+0800 重算；`grep -c` 逐文件复算）**：

| # | 文件 | 命中数（`grep -c` 复算） | 命中内容 | 判定 | 理由 |
|---|---|---|---|---|---|
| 1 | `07_adr.md` | 34 | 本文件**自指**（编号规则 / 旧→新映射 / 本清扫表 / 8 主题映射 / ADR-010 / ADR-011 / ADR-012 标题与正文） | **自指（口径）** | 表格与映射表本身必然命中；逐条判读后无一处把记忆条写成 `ADR-010`。数值在**本表定稿后**复算（口径见下） |
| 2 | `08_v0_plan.md` | 1 | AC-7 判据行引用（指记忆条） | **改** | 已是 `ADR-012` |
| 3 | `03_artisan_self_test.log` | 9 | L102 AC-7 行（`ADR-006/ADR-012`）+ D1/D5/D11/B3/AC-9/F8 行的 `ADR-010`(世界模型) / `ADR-011`(AIGC) / `ADR-012`(记忆条) | **改（修复迭代 1 落地；计数于修复迭代 2 重算）** | **L102 已由 `ADR-006/ADR-010` 改为 `ADR-006/ADR-012`**（修复迭代 1）；L102 / L375 / L380 逐行核过，无一处把记忆条写成 `ADR-010`。**细分计数属自指**（写进本表会改变被统计文本）⇒ 表内不声明细分值，只给命令（见下方「计数口径」） |
| 4 | `01_architecture_design.md` | **12**（原表记 8；architect 侧 round 3 后续增补后重算） | 全部为 `ADR-010 = 世界模型` / `ADR-011 = AIGC` / §16.4.3 重编号裁决文字 | **豁免（且语义已正确）** | Architect 所有、Artisan 只读；逐条核对后**无一处**把记忆条写成 `ADR-010` |
| 5 | `02_source/worldmodel.adapter.spec.md` | 2 | `ADR-010`（世界模型） | 正确 | 指向当前编号 |
| 6 | `02_source/content-pipeline.spec.md` | 2 | `ADR-011`（AIGC） | 正确 | 同上 |
| 7 | `02_source/capability.schema.json` | 1 | `ADR-010（世界模型接入）` | 正确 | 同上 |
| 8 | `02_source/manifest.txt` | 2 | 登记用途串（`capability.schema.json` / `imagine.predict` 行） | 正确 | 同上 |
| 9 | `06_open_source_matrix.md` | 2 | `ADR-010`（世界模型） | 正确 | 同上 |
| 10 | `09_risks_open_questions.md` | 1 | `ADR-010`（世界模型） | 正确 | 同上 |
| 11 | `04_sentinel_test_report.md` | **12**（原表记 2 → 修复迭代 1 记 7；reviewer 的 round 3 §10/§11 追加后重算） | `ADR-006/ADR-010` 等（旧义） | **豁免** | 只读件（reviewer 所有）；旧编号属历史锚定 |
| 12 | `05_raven_risk_report.md` | 3 | 旧编号引用 | **豁免** | 只读件（reviewer 所有） |
| 13 | `.pm_acceptance.md` | 3 | `ADR-006/ADR-010`、`ADR-001~ADR-010`、重编号提示 | **豁免** | PM 只读件；PM 明确保留历史记载 |
| 14 | `.pm_notes.md` | 4 | 同上（含 PM 自我更正） | **豁免** | 同上 |
| 15 | `.raven_prereview_r3.md` | 7 | 预审正文引用 `ADR-010`（旧义） | **豁免** | 只读预审回执；历史锚定 |
| 16 | `_round2-bookkeeping/04_sentinel_test_report.round2.md` | 2 | 旧 `ADR-006/ADR-010` | **豁免** | round 2 簿记快照；改写历史快照 = 销毁证据 |
| 17 | `_round2-bookkeeping/03_artisan_self_test.round2.log` | 1 | 旧 `ADR-006/ADR-010` | **豁免** | 同上 |
| 18 | `_round2-bookkeeping/.squad_result.txt` / `.task-artisan-r2.out` | 2 / 1 | 编排输出中的旧编号 | **豁免** | 同上（由 `--exclude='.squad_*'`/`--exclude='.task-*'` 排除，故不在上面的 `grep -rn` 输出里，单列登记） |

**计数口径（重要；F8 / Sentinel LOW-2 / **Sentinel MEDIUM-4 + LOW-6** 收口）**：

- 上表命中数 = 对**该文件**跑同一条 `grep -c -E 'ADR-01[0-9]|ADR-10[^0-9]'` 得到的**行数**（不是「出现次数」）。
- **复算时刻**：`round 3 · 修复迭代 2`，2026-09-21T22:07+0800（复算输出见 `03_artisan_self_test.log` 的「修复迭代 2」小节）。文件在 reviewer 追加内容后会变（第 4 行 8→12、第 11 行 2→7→12 即由此而来），故重算必须给出**时刻 + 命令原文**。
- **自指规则（本表的核心口径；Sentinel MEDIUM-4 / LOW-6 的根因）**：本表**自身**写在 `07_adr.md` 里，所以第 1 行的计数**包含本表的文字**。为避免「写表 → 计数 → 表内容又变」的漂移，规定两条：
  1. 第 1 行的数值一律在**本表文字定稿之后**复算；
  2. **任何细分计数都不在表内声明**，只给**命令**，由 reviewer 在盘上复算。修复迭代 1 曾在表内写「`grep -c 'ADR-006/ADR-010' 03…` = 0、`ADR-006/ADR-012` = 1」，那是**自指偏差**：这两句话本身写进了 `07`，而盘上 `03` 的实值为 **1 / 2**（`03` 的 F8 行自身也带一个 token）。修复迭代 2 已把 `03` 的 F8 行改为**不声明细分计数**，并在此处只保留命令。
- **复算命令（照抄即可；workdir = `<ws>`）**：

  ```
  grep -c -E 'ADR-01[0-9]|ADR-10[^0-9]' 07_adr.md 08_v0_plan.md 03_artisan_self_test.log \
      01_architecture_design.md 02_source/worldmodel.adapter.spec.md \
      02_source/content-pipeline.spec.md 02_source/capability.schema.json 02_source/manifest.txt \
      06_open_source_matrix.md 09_risks_open_questions.md 04_sentinel_test_report.md \
      05_raven_risk_report.md .pm_acceptance.md .pm_notes.md .raven_prereview_r3.md
  grep -c 'ADR-006/ADR-010' 03_artisan_self_test.log      # 细分：只给命令，不在表内声明数值
  grep -c 'ADR-006/ADR-012' 03_artisan_self_test.log
  ```

**判据口径（重要）**：本轮判据是「**所有残留都在豁免清单内且逐条列出**」，**不是**「零残留」——
`04` / `05` / `.pm_*` / `_round2-bookkeeping/**` / `.raven_prereview_r3.md` 按纪律**不得改写**（预审 Q3 收口）。

### 8 个必答主题 → ADR 编号映射（AC-9）

| # | AC-9 必答主题 | ADR | 状态 |
|---|---|---|---|
| 1 | 内核语言（Python vs Rust vs TS） | `ADR-001` | ✅ |
| 2 | 渲染引擎（three.js/R3F vs Babylon vs Godot） | `ADR-002` | ✅ |
| 3 | 同步方案（Colyseus vs 自建） | `ADR-003` | ✅ |
| 4 | 记忆存储（sqlite-vec vs LanceDB vs 外部服务） | `ADR-004` | ✅ |
| 5 | 模型通道（远程 API vs 本地推理 vs 混合） | `ADR-005` | ✅（round 3 已按 D-0.9 改写表述） |
| 6 | 原子能力 provider 抽象与结构化输出 | `ADR-006` | ✅ |
| 7 | **世界模型接入（ADR-10）** | `ADR-010` | ✅（round 3 新增） |
| 8 | **AIGC 素材生产与许可合规（ADR-11）** | `ADR-011` | ✅（round 3 新增） |

其余条目（`ADR-007` 事件日志哈希链、`ADR-008` 内容层数据驱动、`ADR-009` 双模式权限、`ADR-012` 记忆/自进化边界）为自选主题。
