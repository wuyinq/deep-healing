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

---

## ADR-13 · `world.schema.json` 补 `weather`：消除「同一份文件两把尺子」的契约矛盾（P-2）

- 轮次：`REQ-20260921-004-deephealing-v0-m2`（V0 里程碑 M2 = W3~W6）　决定人：architect（设计 §5，采纳 **A′**）　落地人：artisan
- 关联：`02_source/world.schema.json`、`02_source/district.pack.schema.json`、`02_source/district.pack.spec.md`、
  `v0_skeleton/kernel/deephealing_kernel/pack.py`、`v0_skeleton/kernel/tests/test_pack_validate.py`、
  `v0_skeleton/kernel/tests/test_bus_and_ecs_invariants.py`、`v0_skeleton/kernel/tests/test_kernel_digest.py`

### 背景

- `district.pack.spec.md` **§1** 目录结构写明 `world.seed.json` 的初始世界**含 `weather`**，且「须过 `world.schema.json`」；
  同一份 spec 的 **§2 第 4 步**再次要求「每个数据文件过对应 schema（`world.seed.json` → `world.schema.json`）」。
- `district.pack.schema.json` 的 `$defs/worldSeed` **显式声明** `weather`（`condition` 枚举 / `temperature_c` / `time_of_day` 正则）。
- 而 `world.schema.json` 顶层是 `additionalProperties:false`，`required` 与 `properties` **均无** `weather`
  ⇒ `world.seed.json` 原样**必然**过不了 `world.schema.json`。
- `pack.py` 原先用「**去掉 `weather` 的投影**」补偿（`pack.py:300`），于是**同一份文件两把尺子**：
  `$defs/worldSeed` 收 `weather`、`world.schema.json` 拒 `weather`。
- **机器可读后果**（Raven 预审 X-1，architect 独立复现）：`tests/test_bus_and_ecs_invariants.py:59~63` 的
  「state 不含 weather」**反向对照**，其牙齿**正是** `world.schema.json` 拒收 `weather` —— 给 schema 补 `weather` 会拆掉该对照。

### 选项

| 选项 | 内容 | 代价 |
|---|---|---|
| **A′（采纳）** | 保留 A 的 schema 改动（顶层补 `weather`，结构镜像 `$defs/worldSeed.weather`，**保留 `additionalProperties:false`**），并把「state 不含 weather」的牙齿从「靠 schema 拒收」改为**领域断言 + 哈希差异**（ADR-13 后果第 3 条） | 1 份契约文件字节变更 + **1 处 M1 断言改写（T-3）** + `V0_M1.sha256` divergence；换来**契约单口径** |
| B（否） | 只改 `world.seed.json`：删掉 `weather` | 与**三份**文档冲突（spec §1 + spec §2 第 4 步 + `$defs/worldSeed`）⇒ 不是「只改一处」；且删掉已设计内容、需重签 `pack.sig` |
| C（否） | 只改 `district.pack.spec.md` 文字 | 矛盾根源在 schema 缺字段；且 spec 有**两处** + `$defs/worldSeed` ⇒ **三方冲突**，改文字属掩盖 |
| D（否） | 新增一份「去 weather 的 world 子 schema」给 `snapshot.schema.json` 用 | 需新增契约文件 ⇒ 契约面变大；其收益（不动 M1 判据）已被 A′ 的显式登记方案覆盖 |

### 决定

**采纳 A′**：`world.schema.json` 顶层补 `weather`（typed object，与 `$defs/worldSeed.weather` 同构），**保留 `additionalProperties:false`**。
改动**只有一处**：`02_source/world.schema.json`。**不动** `district.pack.spec.md`、**不动** `district.pack.schema.json`、
**不动** `world.seed.json` 的 `weather`、**不动** `verify_specs.sh` / `snapshot.schema.json`。

### 后果

1. `world.seed.json` **原样**即过 `world.schema.json` ⇒ 双口径消失（单口径）。
2. `pack.py` 的补偿路径**保留调用、退化为恒等**（`projection = dict(world_seed)`）：
   `_validate_schema(` 的出现次数**仍是 4**（1 定义 + 3 调用）⇒ `test_pack_docstring_matches_implementation` **零改动**。
   代码注释已写清「投影已退化为恒等；保留是为了不扰动既有判据计数」。
3. **内核状态边界不变**：`snapshot.state` **仍不得**含 `weather`；**牙齿换位**（M1 判据口径改写，见下表 T-3）。
4. **判据口径改写逐条登记**（改前断言 / 改后断言 / 为什么不是放松判据 / 自证反例）：

| # | 文件与断言 | 改前断言 | 改后断言 | 为什么不是放松判据 | 自证反例（退回旧形态 ⇒ 必红） |
|---|---|---|---|---|---|
| **T-1** | `tests/test_pack_validate.py::test_seed_projection_passes_world_schema` | 「去 `weather` 的投影」过 `world.schema.json`，且**原样（含 weather）必红**（契约矛盾的机器可读证据） | **原样**过 `world.schema.json`（单口径）+ 负例「未声明字段 `humidity` ⇒ 必红」+ 负例「`weather` 内未声明子字段 ⇒ 必红」 | 判据未变空：从「schema 拒收 weather」换成「schema **接受** weather（与 `$defs/worldSeed` 同构）但**仍拒收未声明字段**」；原样的两条结构负例（缺 `transform` / `kind` 非法）**逐字保留** | 用例内即时构造 `degraded`（删掉 `properties.weather` 的 schema）⇒ 「原样过 schema」那条断言必红（已落进用例） |
| **T-2** | `tests/test_pack_validate.py::test_executable_file_in_pack_is_rejected`（② 段） | `_sign(by_magic).returncode == 0`（编码 docstring 自称的「L3 已知缺陷：写侧只按后缀名」） | `_sign(by_magic).returncode **!= 0**` + 结构化 `E_PACK_INVALID`；并加「判据归因」断言（拒收来自**内容魔数**而非后缀名） | **不是把负例改正例**：改名 shebang 内容仍然**必须被拒**，只是拒的位置从「只读侧」变成「读写两侧」；判据由 1 处变 2 处 | 独立反例脚本 `.squad_tools/artisan-p5-revert-negative-control.py` 用仓库 HEAD 的修复前工具实测 `exit 0`；同批 `pack_sign.py` 退回只按后缀名 ⇒ 该断言必红 |
| **T-3** | `tests/test_bus_and_ecs_invariants.py::test_state_passes_world_schema`（反向对照段） | `jsonschema.validate(state + weather)` **必须抛**（牙齿 = schema 拒收 weather） | 三段：① `state` 过 schema **且** `"weather" not in state`；② **哈希差异**（注入 weather ⇒ `canonical_json` / `state_hash` 必须与真实值不同）；③ **schema 牙齿保留**（注入未声明字段 `humidity` ⇒ 必抛） | 「state 不得含 weather」这条**领域约束一字未改**；牙齿从「借 schema 的拒收」换成「哈希差异 + 领域断言」——前者只证 schema 形状，后者证**真实哈希受影响** | 用例内即时构造 `relaxed`（去掉顶层 `additionalProperties:false` 的 schema）⇒ ③ 必红；② 已把「正向断言非空转」量化成哈希差异 |
| **T-4** | `tests/test_kernel_digest.py::test_no_providers_adapters_dir_in_delivery_tree`（**本轮授权清单外，需 architect 追认**） | `not (…/deephealing_kernel/providers/adapters).exists()` —— 原 docstring 明写「属 **W3 面**，预审 M4 第 5 条」= **M1 期的里程碑范围约束** | 该目录**存在**且**只作 adapter 实现面**（`relation_infer.py` / `__init__.py` 在位），并复验 `kernel_digest` 并集判据对它成立、对包根新增仍不成立 | 约束从「禁止新建该目录（W3 前的范围冻结）」换成「该目录存在，且**只有**它与 `adapters/` 是新增豁免面，包根新增仍必须红」；M1 真正要保的性质（新增能力不改既有内核文件）**一字未改** | 用例内把 `ADAPTER_DIRS` 收窄回 `("adapters/",)`（= 退回「不承认该目录」的形态）⇒ 并集正例必红 |

5. `V0_M1.sha256` 对应条目会 divergence ⇒ 逐条列出（见 `06` 的「显式声明」节）+ 原因；`V0_M2.sha256` 为本轮新冻结面。
6. **T-4 的授权状态（必须上抛）**：设计 §1.3 的 M-7 追加授权只枚举了 **T-1/T-2/T-3** 三处；
   T-4 是落地 W3 授权面（设计 §3.1 明列 `providers/adapters/relation_infer.py`）时**必然**撞上的 M1 里程碑约束。
   处置：**最小改写 + 逐条登记（本节 + `06`）+ 在本轮摘要里显式标注需 architect/PM 追认**；未追认前按「已登记的越界候选」对待，不静默。

### 迁移

- **谁受影响**：
  1. `v0_skeleton/kernel/deephealing_kernel/pack.py` —— 补偿路径退化为恒等（调用保留、计数不变）；
  2. `v0_skeleton/kernel/tests/test_pack_validate.py` —— T-1 / T-2 两处断言；
  3. `v0_skeleton/kernel/tests/test_bus_and_ecs_invariants.py` —— T-3 一处断言；
  4. `v0_skeleton/kernel/tests/test_kernel_digest.py` —— T-4 一处断言（见上）；
  5. **下游读者**：任何按「`world.schema.json` 会拒收 `weather`」推理的实现/审计脚本（现在必须改按「`snapshot.state` 不含 `weather`」这一领域断言推理）；
  6. `02_source/district.pack.spec.md` / `district.pack.schema.json` / `world.seed.json` **不需要**任何改动（这正是「只改一处」的验收面）。
- **如何验证**：`AC-M2-7` —— ① 全量 `pytest tests/ -q -p no:cacheprovider`；② 逐条 M1 命令（`verify_specs.sh --quiet` /
  `test_determinism_replay.py` / `test_pack_validate.py` / `test_bus_and_ecs_invariants.py` / `test_kernel_digest.py`）；
  ③ 基线复算（末检查点 `state_hash == 9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f`）。
- **如何回退**：① 去掉 `world.schema.json` 顶层的 `weather`；② 把 `pack.py` 的 `projection` 恢复为
  `{key: value for key, value in world_seed.items() if key != "weather"}`（即恢复实质过滤）；③ 还原 T-1/T-3 两处断言原文
  （T-2 属 P-5 缺陷关闭，**不随本 ADR 回退**）；④ 重跑 AC-M2-7 与 `verify_specs.sh --quiet`。


## ADR-014 · `embed.text` 的 `remote_api` provider 结构性不可用：标为不可用 + 从默认优先级摘掉（M3 再议恢复）

> 来源：PM r3 变更单（2026-09-22）。architect 独立复核后裁决；落地面见 `06` §GAP-E1。

- **背景**：能力契约 `embed.text` 声明四类 provider，其中 `remote_api`（原 `priority: 10`，**最高**）
  声明 `model: text-embedding-3-small` / `impl: builtin:openai_compatible_embeddings` /
  `requires_secrets: ["HERMES_CUSTOM_TOKENFAB_API_KEY"]`。实测：`POST /v1/embeddings` 对该 model 返回
  **404 `model_not_found`**（端点存在、模型不存在），该通道**无任何嵌入模型**；备选通道 `ca-free` 无凭据。
  ⇒ 该 provider **永不可能成功**，而它在**非回放态**被首先选中 ⇒ 每次调用白发一次注定失败的请求。
- **选项**：① 指向**真实存在**的嵌入通道（须先实测）；② 标为「本通道不可用」并从默认优先级摘掉，
  V0 允许 defer 到 M3，但必须在 ADR + manifest 登记；③ 维持现状（留成「看起来能跑」）。
- **决定**：采用 **②**，但**不是**「只把 `remote_api` 降级」—— 实测证明那会引入回归（见下）。
  最终**两处**数据改动：① `remote_api.priority` **10 → 90**（从默认优先级摘掉）；
  ② `cassette_replay.priority` **20 → 50**。不可用性写入**既有**的 `determinism_note`；
  **不加新字段**：`capability.schema.json` 对 `providers[].items` 是 `additionalProperties: false`，
  新增键会直接破坏 schema 校验（这正是「配置为真 ≠ 效果为真」的自证）。
- **为什么必须同时挪 `cassette_replay`（负例自证，可复算）**：只把 `remote_api` 降到 90、`cassette_replay`
  留在 20 时，**非回放**路由的第一顺位变成 `cassette_replay`；录制态下没有 cassette ⇒ miss ⇒
  `E_CAP_FALLBACK_UNRESOLVED: embed.text has no structured fallback for on_cassette_miss`（**exit 1，录制被打破**）。
  把 `cassette_replay` 挪到 50 后：非回放路由 = `local_model`(30) → `E_LOCAL_MODEL_UNAVAILABLE`
  → fallback `deterministic_rule`(40)，**不再有任何远端尝试**。回放态不受影响（`--replay` 强制
  `cassette_replay`，与 priority 无关）。
- **后果（显式，不许藏）**：`embed.text` 在 M2 **真实可用**的 provider 只有 `deterministic_rule` **一类**，
  与录制产物（仅 `embed.text__deterministic_rule.jsonl`）一致；`local_model` 是诚实 GAP。
  `06` 修-8 表第 9 条「有有效凭据 ⇒ remote_api」对 `embed.text` **不成立**，已在原表就地更正。
- **迁移**：M3 若要恢复远端嵌入 —— **必须先实测出一个真实存在的嵌入通道**（端点 + 模型 id 均实测通过）
  再回填 `priority` / `model`；不许按「应当有」写，也不许以「通道应当支持」为理由恢复优先级。
- **如何验证（含负例自证）**：① 读契约断言 `remote_api.priority == 90` 且 `cassette_replay.priority == 50`；
  ② 非回放态 invoke 一次 `embed.text`（干净 cassette 目录）⇒ `provider_class=deterministic_rule`、
  `remote_api_attempted=false`；③ **负例**：把 `cassette_replay` 退回 20 ⇒ 必须变红
  （`E_CAP_FALLBACK_UNRESOLVED`）；④ `shasum -c V0_M2.sha256` ⇒ **0 非 OK**。实测见 `06` §GAP-E1。
- **如何回退**：把 `remote_api.priority` 改回 `10`、`cassette_replay.priority` 改回 `20`，
  并删去 `determinism_note` 的裁决段 ⇒ 恢复原行为（**含** 404 流量）。
- **附**：契约声明的凭据变量名（`HERMES_CUSTOM_TOKENFAB_API_KEY`）与 REQ §3 字面
  （`HERMES_CUSTOM_TOOLFAB_API_KEY`）不一致，该冲突已由 `06` §显式声明 7 单独登记，本 ADR 不重复裁决。

---

## ADR-015 · `--replay` 是审计路径：降级**不得回填** replay 源（R4-C1 修复 + 重复 key 判据）

> 来源：architect 裁决 `.squad_tools/architect-ruling-r4c1.md`（2026-09-22，**CRITICAL 成立**），
> PM 复现配方 `.squad_tools/pm_repro_r4c1.sh`，三方独立复现（PM 两次 / Raven r4 / architect）。
> 落地面：`02_source/v0_skeleton/kernel/deephealing_kernel/registry.py`、`providers/cassette.py`、
> `tests/test_cassette_no_backfill_r5.py`；登记面见 `06` §修复轮 5。

- **背景（缺陷）**：`--replay --cassette-dir <源目录>` 命中一条**被篡改**的 cassette 记录 ⇒
  store 抛 `CassetteTampered` ⇒ `_fallback_key()` 归到 `on_error` ⇒ 契约 `fallback.on_error = deterministic_rule`
  ⇒ `_fallback()` 内的 `self._cassette.record(...)` **无条件**执行，把**降级输出写回正在被验证的 replay 源目录**。
  实测后果：`relation.infer__deterministic_rule.jsonl` **5 → 6 条**，再跑一次 **6 → 7 条**（非幂等、持续写盘）；
  追加记录与其前一条**共享同一 `prev_hash`** 且不等于被篡改记录的 `hash` ⇒ **哈希链分叉**；
  而 `verify_chain()` 当时只比 `prev_hash` 链与记录自校验 `hash` ⇒ 回填产生的**重复 key 零告警**。
  违反四条：① 本轮关闭判据 ⑤「篡改时零回填」；② `cassette.format.md` §5（`record_if_allowed` **禁止**用于回放跑）；
  ③ `_fallback()` 自身 docstring「禁止静默回填」；④ `--replay` 的对外语义（审计路径改写被审计产物）。
- **根因（读码确认）**：`_fallback()` 的签名里**没有** `replay_mode`，也从不读 `self.default_replay_mode`
  ⇒ 录制与回放两条路径共用同一段录制代码，**没有任何开关区分它们**；`invoke()` 主路径的 `record()`
  同源（`--replay` 下正常不可达，但 `force_provider` 可触达）。
- **选项**：① 只给 `_fallback()` 加 `self.default_replay_mode` 判断（**否**：`invoke(replay_mode=True)` 与
  构造参数不一致时漏判）；② 在 `CassetteStore.record()` 内加全局只读/回放态开关（**否**：把状态藏进 store，
  调用方无从核验，且 store 被录制与回放共用）；③ **把 `invoke()` 解析出的生效 `replay_mode` 显式传入**
  `_fallback()`，两处 `record()` 都以它为守卫（**采用**）。
- **决定**：
  1. `_fallback(..., *, slot, npc_id, replay_mode)` —— 新增显式入参，`invoke()` 的**三处**调用点
     （`on_budget_exhausted` / provider 异常 / `on_invalid_schema`）全部传入 L391 解析出的**生效值**
     `bool(replay_mode or self.default_replay_mode)`；生效回放模式下 `_fallback()` **不写任何 cassette**。
  2. `invoke()` 主路径的 `record()`（`remote_api` / `deterministic_rule`）同样以生效 `replay_mode` 为守卫（F-2）。
  3. 被抑制的回填**必须留痕**：落 `journal` 事件 `cassette.record_suppressed{slot, provider, reason, replay_mode}`
     —— 「零回填」不等于「零痕迹」，审计面要能看见「这里本来会写」。
  4. `verify_chain()` 增加「**同一文件内同一 key 出现两次**」判据（冻结条文 §4.1.2 / §6 / §5.1 已点名该签名）。
- **后果（显式，不许藏）**：
  - 回放跑（`--replay`）在**任何**降级分支下都不再写 `--cassette-dir` ⇒ 该目录跑前/跑后**逐字节相同**。
  - **录制面不变**：非回放跑仍录制（`deterministic_rule` 是 `cassette_replay` 的录制源，录制被禁会直接
    打破「rule ↔ replay 逐字节等价」判据）⇒ 本决定只关「回放态写盘」，不关「录制态写盘」。
  - 回放中「本应回填」的次数现在只出现在 journal（`cassette.record_suppressed`），不再出现在盘上。
  - **未加固面（诚实标注，不许写成已解决）**：`FROZEN-CASSETTE-INTEGRITY-1` 的强度边界不变 ——
    无密钥链可被**整链重签**（R4-L4）；**自洽前缀截断**（删末条、链仍自洽）也不在本判据覆盖内；
    两者都需**外部锚定**（链头签名 / 时间戳载体）才能关闭，V0 无实现 ⇒ 仍记 GAP。
  - `lookup()` 命中路径只校验**命中记录自身**的 `hash`（未复核整文件链），与冻结 §4.3① 的字面
    （「命中即校验该文件的 hash 与文件内 prev_hash 链」）仍有差距；本轮的补偿是命令层 `verify_chain()`
    对**全库**判红（exit ≠ 0），逐字对齐留 M3（**不扩写集**）。
- **如何验证（本轮实测，命令 + 读数见 `06` §修复轮 5 与 `03_artisan_self_test.log`）**：
  ① PM 配方原样跑 ⇒ ④ **`✅ 零回填（未复现）`**，③ 仍 `exit=1` + `E_CASSETTE_TAMPERED`；
  ② 新增测试 **7** 条全绿（实测文件 `tests/test_cassette_no_backfill_r5.py`，`def test_` 计数 = **7**；
  覆盖：源目录前后全量 sha256 逐字节相同 / 重复 key 判红（单元）/ 命令层可见性 / `prev_hash`-only 两形态 /
  生效 `replay_mode` 显式传参 / 干净回放 exit 0 / miss exit ≠ 0；第 7 条为**源码级负例自证**用例，见 ③。
  条数更正：原写 6 条，raven r5 确认轮实测 7，`06` §修复轮 6 复算一致）；
  ③ **负例自证**：把 F-1 守卫退回 `and not (False and replay_mode):`（锚点命中数断言 = 1，
  变异只发生在 `/tmp` 整树副本）⇒ 同一配方**回填复现**（条数 +1、目录 sha 变化）⇒ 判据有牙齿；
  ④ 全量 pytest 全绿、`verify_specs.sh --quiet` OK/0 skipped、基线 `state_hash` 逐位一致。
- **如何回退**：删去 `_fallback()` 的 `replay_mode` 入参及两处 `not replay_mode` 守卫（即恢复无条件
  `record()`），并删去 `verify_chain()` 的重复 key 判据 ⇒ 恢复 R4-C1 的行为（**含**回填与链分叉）。
  **禁止**只回退其中一处（守卫与判据是同一族的两个面）。
- **与 ADR-014 的关系**：互不覆盖。ADR-014 管「非回放态选哪个 provider」，本 ADR 管「回放态能不能写盘」。
