# 01 · DeepHealing 世界架构冻结（Architecture Freeze）

- 计划：`REQ-20260921-002-deephealing-architecture-freeze`　版本：**rev3（§16 增补；契约基线 REQ rev5）**　作者：architect　日期：2026-09-21
- **rev2.1（architect 裁决修订，2026-09-21）**：依独立门禁结论修订四处 —— ① §7.6 新增「cassette 完整性 + 历史 provider 查找」契约（关闭 RA-1/RA-2 的契约空洞）；② §9.1/§9.2 成本与日志数字按**实测**重标（R2/R13/R15）；③ §12.1 AC-2 判据强化为「检查点集合相等 + 三字段逐点比对」（关闭 RA-3）；④ §7.3 明确 AC-13 的 remote 类等价性**必须在契约默认 `timeout_ms` 下取证**，不接受命令行 override（关闭 RB-2 的证据口径）。修订依据：`04_sentinel_test_report.md`、`05_raven_risk_report.md`。
- **rev3（architect 增补，2026-09-21 round 3）**：§16 增补有界补轮设计 —— AC-14 世界模型接入（权威归属 / 三处接入点 / 适配器契约 / 闭源-开源取舍 / 无 GPU 可行性 / V1 门禁判据 / V0 边界）、AC-15 AIGC 素材生产（本机分工 / 离线边界 / 许可白名单与陷阱 / 版权灰区 / 成本 / 资产契约 / 唯一内容管线 / 美术圣经 / V0 边界）、D-0.9 时间预算语义冻结与标定口径，以及 `.pm_acceptance.md` §3 五项落盘阻断项的**裁决与关闭判据**（含 ADR 重编号、`event_chain_hash` 统一定义两项 architect 裁决）。契约基线升至 **REQ rev5**。
- 上游：`pm_business/REQ-20260921-002-deephealing-architecture-freeze.md`（FROZEN，rev2）
- 本轮性质：**架构冻结轮**。产物是设计与证据（规格、选型裁决、真实 spike），**不是可玩游戏**。
- 快照基线：repo `/Users/wooyinq/personal/deep-healing`，branch `develop`，HEAD `56a1e8188d143c0941af69e0ebe1c62afb535ca9`，tree clean（仅 `README.md`、`LICENSE`）。**本轮仓库只读**（不写文件、不做任何 git 写操作）。
- 写集：仅 `dev_team_workspace/REQ-20260921-002-deephealing-architecture-freeze/` + 各角色自身账本。越界即阻断。

---

## 1. 目标 / 非目标 / 边界

### 1.1 目标

1. 冻结 7 层架构（渲染 / 会话传输 / 世界内核 / 认知 / 记忆 / 内容 / 观测回放）的职责、依赖方向、接口与数据契约。
2. 冻结**确定性 tick 与回放**语义（seed 单一来源、事件日志、快照、状态哈希），使「同一事件日志重放两次 → 状态哈希一致」可被判据化验证。
3. 按 **D-0.6** 冻结**原子能力注册表（atomic capability registry）**：能力槽位 / provider 分离 / 组合契约 / 成本与降级 / 安全；「新增一个原子能力不改内核代码」必须可演示。
4. 冻结双模式（观察 / 参与）权限模型与状态同步协议，含「参与影响任务迭代演进」的机制与防滥用边界。
5. 冻结内容扩展机制：小区 = 数据驱动可加载单元（district pack），「新增第二街区不改内核代码」有迁移路径与校验方式。
6. 完成**逐层开源选型裁决**（adopt / adapt / reject + 许可判定），并以**真实 spike**（真跑）验证最关键的 3 个候选面。
7. 给出垂直切片 **V0 文件级 / 接口级实施计划**与逐条 AC 判据、演进路线与 ADR。

### 1.2 非目标

- 不交付可玩成品；不做美术量产；不做多人在线部署；不做生产部署。
- 不 push、不开 PR、不部署、不改真实仓库。
- 不实现完整任务系统 / 剧情，只冻结契约与 V0 切片范围。
- 不集成任何商业中间件（Inworld / Convai / NVIDIA ACE 等一律不得声称「已集成」）。

### 1.3 硬边界

| 边界 | 约束 |
|---|---|
| IP | 原著人物 / 名称 / 情节 / 世界规则是**核心依据**（《我的治愈系游戏》内部 1:1 复刻；出处表见 `02_source/fidelity/`）；仍**禁止逐字搬运原著正文段落**；对外命名与素材须可商用/自研 |
| 秘密 | 任何产物（文档/日志/spike 原始日志/账本/cassette）不得含 token / key / 凭据；spike 日志中出现 `Authorization` 一律脱敏 |
| 证据 | 无命令 + workdir + exit + 原始日志路径者不得写成 PASS；未执行一律 GAP；禁止伪造 spike 日志或状态哈希 |
| 工具链 | node v26.3.1 / npm 11.16.0 / bun 已装；pnpm、yarn **未装**；Python 3.13.13 + uv 可用；**Rust 未装**（无 cargo/rustup）；Docker 29.7.2；Playwright chromium 已缓存；Chrome 已装；**无 NVIDIA GPU**。任何工具链安装必须计入 ADR 成本项 |

---

## 2. 技术选型摘要（详细矩阵见 `06_open_source_matrix.md`）

原则：**adopt-first（不造轮子）**。每层先取成熟开源；自研仅限「开源无法覆盖的差异化内核」，且必须写明理由。

| 层 | 主选（V0） | 备选 | 裁决倾向 | 关键理由（详见 06/07） |
|---|---|---|---|---|
| 渲染 | `three.js`（MIT） | `react-three-fiber` / `Babylon.js` / `playcanvas` | adopt three.js | 事实标准、生态最大、WebGPU 路径在推进；R3F 保留为 V1 组件化选项 |
| 世界内核 | **自研薄确定性内核**（Python 3.13 + uv），tick/ECS/RNG/事件日志自建 | `mesa` / `bitECS` / `bevy_ecs`+`hecs`（Rust） | 自研（差异化内核）+ 参考 mesa | 确定性 tick + 回放哈希是核心差异化；mesa 的调度模型与 3D/固定 tick 不匹配；Rust 工具链未装、V0 规模（5 NPC）无需 |
| 物理 / 导航 | V0：路点/网格导航（内核内数据驱动） | `rapier`（Rust）/ `yuka`(JS) / `recast-navigation-js` | V0 自建最简 + 记录 V1 候选 | 单栋楼垂直切片不需要完整刚体物理；rapier 需先装 Rust 工具链（ADR 记成本） |
| 会话传输 | **自研最小权威 WS 传输**（内核即权威） | `colyseus` / `nakama` | adapt：V0 自建，V1 评估 colyseus | 避免「双权威」漂移（见 R7）；colyseus 需把权威搬到 Node 侧，与内核进程冲突 |
| 认知编排 | `py_trees`（BSD）行为树 + 自研效用打分器 | `BehaviorTree.CPP` / `behaviac` | adopt py_trees | Python 生态与内核一致；behaviac 已停滞（2023-07） |
| 结构化输出 / 模型通道 | `instructor`（MIT）或 `outlines`（Apache-2.0）+ OpenAI 兼容远端 API | `pydantic-ai` / `ollama` / `vllm` / `web-llm` / `transformers.js` | adopt instructor 为主、outlines 为对照 | 能力契约要求 JSON Schema 强校验；本地推理与浏览器内推理列为 provider 备选而非主选 |
| 记忆 | `sqlite`（stdlib）+ numpy 余弦（V0）→ `sqlite-vec` / `LanceDB` | `mem0` / `letta` / `graphiti` / `pgvector` | adapt：V0 最小自持，V1 评估 sqlite-vec | 记忆范式取自 `generative_agents`（Apache-2.0）的记忆流/反思，但存储不引服务型依赖 |
| 社会仿真范式 | 参考 `generative_agents` / `concordia` | `ai-town` / `oasis` / `camel` / `sotopia` | adapt（范式借鉴，不直接集成运行时） | 它们解决「智能体社会」但都自带运行时与渲染假设，与本架构的内核/传输分离冲突 |
| 自进化 | 参考 `dgm`（自改写闭环）+ `pyribs`（质量-多样性） | — | adapt + 自研护栏 | 自进化必须受控（可回滚/可审计/不破坏治愈向目标函数），见 §8 |
| 观测 / 回放 | 事件日志 JSONL + `duckdb`（分析）+ 可选 `opentelemetry` | `opentelemetry-js` | adopt duckdb（分析）/ adapt otel | 回放分析是架构刚需；otel 作为 V1 可选 |
| 内容 / 城市数据 | 自研 district pack 规范 | `osmnx` / `BlenderGIS`(GPL-3.0) / `UrbanWorld2.0` | adopt 规范自研；地理数据源 V1 | BlenderGIS 为 GPL-3.0，**仅可作离线美术管线**，不得进运行时；UrbanWorld2.0 许可待核、研究项目 |

> 上表为**方向性裁决**；`06_open_source_matrix.md` 必须逐层给出 ≥2 候选的 URL / license / 版本 / 最近活跃 / 集成成本 / 结论 / **许可兼容性判定**，且至少 2 个候选有**真实 spike 执行证据**（AC-5）。

---

## 3. 分层架构与数据流

### 3.1 分层图（依赖方向严格向下，禁止反向依赖）

```
        ┌──────────────────────────────────────────────────────────────┐
        │  L7 观测回放层  Observability & Replay (side-car, read-only) │
        │  事件订阅 / 轨迹分析(duckdb) / 快照时间轴 / 重放驱动          │
        └───────▲───────────────────────────────▲──────────────────────┘
                │ 只读订阅 events+snapshots        │ 只读快照
┌───────────────┴───────────┐        ┌──────────┴───────────────────────┐
│  L1 渲染层 Render (Web)   │        │  L5 内容层 Content (data packs)  │
│  three.js 场景 / HUD / UI │        │  district pack / 任务定义 / 资产 │
│  只消费快照，零业务逻辑    │        │  被内核加载，不被渲染层直读      │
└───────────────▲───────────┘        └──────────▲───────────────────────┘
                │ snapshot / delta / event (JSON over WS)
┌───────────────┴───────────────────────────────┴──────────────────────┐
│  L2 会话传输层 Session Transport (Node 传输进程，非权威)              │
│  会话建立 / 双模式鉴权 / 增量同步 / 意图上行通道                      │
└───────────────▲──────────────────────────────────────────────────────┘
                │ 权威写入只能经内核：intent → tick 边界应用
┌───────────────┴──────────────────────────────────────────────────────┐
│  L3 世界内核层 World Kernel (Python 本地进程，唯一权威)               │
│  固定 tick / 确定性 RNG / ECS / 事件日志 / 快照 / 规则层组合调度      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ L4 认知层 Cognition：原子能力注册表 + 规则层组合                │  │
│  │   slot → provider(remote_api | local_model | rule | cassette)   │  │
│  └───────────────────────────┬────────────────────────────────────┘  │
│  ┌───────────────────────────┴────────────────────────────────────┐  │
│  │ L6 记忆层 Memory：短期缓冲 / 长期事件 / 语义事实 / 反思         │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

依赖方向（硬规则）：

- L1 → L2 → L3（渲染只读快照；传输只搬运；内核唯一权威）。
- L3 → L4 → L6（内核调度认知；认知读写记忆）。
- L5 → L3（内容被内核加载；**渲染层不得直读内容包**，以免绕过权威）。
- L7 ← L3/L4/L6（观测层只订阅，**不得写入内核状态**；重放是「新内核实例 + 同一日志」，不是原地改状态）。
- 禁止：L1/L2 直接调用 L4（渲染层或传输层出现模型调用即为契约破坏）；L4 直接改世界状态（认知只产出结构化结果，写入由规则层在内核内执行）。

### 3.2 数据流（一次「NPC 决策」的端到端）

```
内容包(L5) ──load──▶ 内核(L3) 初始化世界 + RNG(seed) + 实体
      │
      ▼ 每 tick(100ms)
[1] 输入阶段：玩家意图队列(L2→L3) + 环境事件 + 到期日程 → 确定性排序
[2] 感知阶段：NPC 感知查询（只读 ECS）→ 感知快照
[3] 规则层(L4 组合)：需求/效用打分 → 选择行为树分支 → 决定是否调用原子能力
      │            ├─ 需要认知 → capability.invoke(slot, input, budget)
      │            │        └─ provider 路由(remote_api|local_model|rule|cassette)
      │            │                └─ schema 校验 → 失败则 fallback（见 §7.4）
      │            └─ 不需要认知 → 确定性规则直接出结果
[4] 执行阶段：动作写入 ECS（唯一写点）
[5] 记账阶段：追加事件到 events.jsonl（含 hash chain）+ 预算记账
[6] 快照阶段：每 50 tick（或按需）落 snapshot + state_hash
      ▼
[7] 广播阶段：delta(snapshot 差量) + events → L2 → L1 渲染
      ▼
[8] 观测阶段：L7 只读订阅 events/snapshots → 分析/回放/时间轴
```

**权威链**：世界状态的唯一写入点是 [4] 执行阶段（内核内、tick 边界内）。任何外部输入（玩家意图、模型输出、内容包）都必须先经 [1]/[3] 校验后由 [4] 写入。

---

## 4. 各层职责 / 边界 / 接口契约

### 4.1 L1 渲染层 Render（Web，TS + three.js）

- 职责：消费 `snapshot` / `delta` / `event`，渲染 3D 场景、HUD、双模式 UI；本地插值与相机；无世界逻辑。
- 边界：**零业务规则**、零模型调用、零世界状态写；不得直读内容包与事件日志文件。
- 接口：
  - `RenderClient.connect({url, session_id, mode}) -> TransportHandle`
  - `RenderClient.apply(snapshotOrDelta) -> void`（幂等，按 `tick` 与 `seq` 丢弃乱序）
  - `RenderClient.submitIntent(intent) -> Promise<IntentAck>`（仅参与模式；观察模式调用即本地拒绝）
  - 渲染目标：60 fps 目标 / 30 fps 下限；插值在渲染帧内完成，不阻塞 tick。
- V0 目录（见 `02_source/v0_skeleton/`）：`web/src/main.ts`、`web/src/scene/`、`web/src/ui/observe/`、`web/src/ui/participate/`、`web/src/net/client.ts`。

### 4.2 L2 会话传输层 Session Transport（Node 进程，**非权威**）

- 职责：会话建立与鉴权、双模式权限落地、增量同步、意图上行、心跳与断线重连。
- 边界：**不持有世界状态真值**，不做规则计算、不做模型调用、不改世界状态；只做搬运与权限检查。这一条是为了消灭「双权威」漂移（R7）。
- 接口（HTTP + WS，JSON）：
  - `POST /sessions {mode: "observe"|"participate", district_pack_id, client_version} -> {session_id, token, tick_rate, schema_version}`
  - `WS /ws/{session_id}`　server→client：`{t:"snapshot", tick, seq, state, state_hash}` / `{t:"delta", tick, seq, ops[]}` / `{t:"event", tick, seq, event}` / `{t:"tick_meta", tick, ms}`
  - `WS /ws/{session_id}`　client→server：`{t:"intent", id, kind, target, payload, client_tick}` → `{t:"intent_ack", id, status:"queued"|"rejected", reason}`
  - 权限：`observe` 会话上行 `intent` 一律 `rejected: E_MODE_READONLY`；`participate` 会话按 `intervention.policy` 校验（§6.3）。
- 同步协议（AC-4）：
  - **权威 = 内核**；服务端→客户端只发 `snapshot`（每 5s 或首次）与 `delta`（每 tick 或合并）；客户端→服务端只发意图。
  - `delta.ops`：`{op:"set"|"add"|"del", entity, component, value}`，按 `(tick, seq)` 单调；客户端按 `seq` 去重、按 `tick` 丢弃过期。
  - 冲突解决：**authority wins**；V0 关闭客户端预测；断线重连以最近 `snapshot` 重建。
  - 观察模式可携带 `record=true` 走观测层录像（只读路径）。

### 4.3 L3 世界内核层 World Kernel（Python 本地进程，唯一权威）

- 职责：固定步长 tick 循环、确定性 RNG、ECS 世界状态、事件日志与哈希链、快照、内容包加载、规则层组合调度、预算记账。
- 边界：内核是唯一写世界状态者；内核不得直接对浏览器暴露（经 L2）；内核不得把模型调用散落到业务逻辑（一律经 §7 能力注册表）。
- 接口（CLI + 库）：
  - `python -m deephealing_kernel run --pack <dir> --seed <int> --tick-rate 10 --events <path> --snapshot-every 50 --ws-port <int>`
  - `python -m deephealing_kernel replay --events <path> --pack <dir> --until <tick> --checkpoint-every 50 --out <path>`
  - `python -m deephealing_kernel verify --events <path> --pack <dir> --expected-hash <hex>`（重放并逐检查点比对）
  - 库接口：`WorldKernel.step()`（推进一个 tick，纯函数式副作用集中在事件追加）、`WorldKernel.snapshot() -> Snapshot`、`WorldKernel.state_hash() -> str`
  - 事件总线：`KernelBus.subscribe(topic, fn)`（L7 与 L2 只订阅）
- tick 语义（AC-2，冻结）：
  - `dt = 100ms` 固定；tick 率 10 Hz；tick 内阶段顺序固定为 §3.2 的 [1]→[6]，**阶段顺序是契约的一部分**。
  - **禁止**在 tick 内使用 wall-clock、`time.time()`、线程池完成顺序、`set`/`dict` 迭代顺序（一律显式排序）、外部网络结果（模型调用只能在 tick 边界之外异步完成后于下一 tick 注入）。
  - 随机源：唯一 `WorldRng(seed)`；子系统取流 `rng.stream("npc:need:<id>")`（stream 名哈希派生，新增子系统**不改变**既有 stream 序列）。
  - 数值：位置用整数毫米；浮点仅用于派生量并在快照时按 6 位小数规范化；禁 NaN/Inf。
  - 事件：JSONL，`{seq, tick, type, actor, payload, prev_hash, hash}`，`hash = sha256(prev_hash || canonical_json({seq,tick,type,actor,payload}))`。
  - 快照：`{tick, state, state_hash, event_chain_hash, rng_state_digest}`，`state_hash = sha256(canonical_json(state))`。
  - 规范化：键排序、UTF-8、无空格分隔符、整数不带小数点、浮点 6 位。
  - 回放：`replay` 从 genesis 重放同一事件日志到 `--until`，逐检查点比对 `state_hash`；**两次重放哈希必须一致**（AC-2 判据）。
- ECS（自研薄实现，差异化内核）：组件数组 + 实体索引 + 系统按固定顺序执行；`world.schema.json` 冻结组件字段。

### 4.4 L4 认知层 Cognition（原子能力注册表 + 规则层组合）

- 职责：把「模型能力」抽象为**契约化原子能力**，由规则层组合调度；产出结构化结果，不直接改世界状态。
- 边界：能力只做「输入 → 结构化输出」；不得持世界状态；不得读 secrets 进入上下文（§7.5）。
- 详见 §7（本层是 D-0.6 / AC-13 的落地位置）。

### 4.5 L6 记忆层 Memory

- 三层：
  - **短期（working）**：每 NPC 环形缓冲（默认 64 条），tick 内可读，写入只经事件。
  - **长期（episodic）**：事件索引 + 重要性打分（`importance` 由 `emotion.appraise` 或确定性规则给出）；`sqlite` 表 `episodes(npc_id, tick, kind, text_summary, importance, embedding_blob, refs)`。
  - **语义（semantic）**：从反思产出的稳定事实 `facts(npc_id, key, value, confidence, updated_tick)`，带来源 refs 可审计。
  - **反思（reflection）**：按日程/阈值触发 `memory.reflect` 原子能力，产出 `{insights[], new_facts[], summary}`；反思结果必须可回滚（保留 `superseded_by`）。
- 检索：V0 = `sqlite` + numpy 余弦（嵌入由 `embed.text` 能力产出，provider 可为远端/本地/确定性哈希回退）；V1 评估 `sqlite-vec` / `LanceDB`。
- 边界：记忆层不得绕过 schema 直接写世界状态；记忆只影响认知输入与规则层打分。
- 遗忘/裁剪：重要性阈值 + 时间衰减 + 每 NPC 容量上限（防成本与内存无界增长）。

### 4.6 L5 内容层 Content（district pack，数据驱动可加载单元）

- 单元结构（冻结，见 `02_source/district.pack.spec.md`）：

```
districts/xingfu-xiaoqu/
  pack.json            # id/version/引擎版本区间/边界/作者/许可
  world.seed.json      # 初始实体、时间、天气、世界常量
  buildings/*.json     # 楼栋/房间/可交互物（含导航节点）
  npcs/*.json          # 住户档案：需求权重、日程、关系种子、创伤/暗面标记
  tasks/*.json         # 分级任务定义（含状态机与 adaptation_rules）
  schedules/*.json     # 日程表（数据驱动，非代码）
  assets/manifest.json # 资产位（占位/程序化/可替换）
  pack.sig             # 校验清单（sha256 列表）
```

- 加载与校验：`kernel run --pack <dir>` 前先按 `district.pack.schema.json` 校验，失败即 `E_PACK_INVALID`（不启动）。
- **新增第二街区不改内核代码**（AC-6）的迁移路径：
  1. 复制 pack 目录 → 改 `pack.json.id/version` → 填 `world.seed.json` 与楼栋/NPC/任务数据；
  2. `pack.sig` 重新生成（`kernel pack sign <dir>`）；
  3. `kernel validate --pack <dir>` 通过 → `kernel run --pack <dir2>`；
  4. 跨区连接只在 `pack.json.portals[]` 声明（数据），内核按 portals 数据建边，**不新增代码分支**。
- 校验方式（判据）：`kernel validate` exit 0 + `jq` 解析全通过 + 用 `pack.sig` 逐文件比对；并给出「改动仅落在 pack 目录」的 `git status`（workspace 内）证据。

### 4.7 L7 观测回放层 Observability & Replay

- 职责：只读订阅事件/快照；轨迹分析与查询（`duckdb` 读 JSONL）；时间轴回放（用 `replay` 生成检查点序列）；指标导出（V1 可选 OTLP）。
- 边界：**不得写入内核状态**；回放 = 新内核实例 + 同一事件日志，保证「回放不改写历史」。
- 接口：
  - `kernel replay --events <log> --until <tick> --checkpoint-every N --out <dir>`（产出 `checkpoints/*.json`）
  - 分析：`duckdb -c "SELECT ... FROM read_json_auto('<events.jsonl>')"`（V0 示例查询见 `03_spike_log.md`）
  - 时间轴 UI（V0 可 GAP，给替代证据）：读 `checkpoints/` 渲染 scrubber。

---

## 5. 冻结的数据契约（机器可读规格 → `02_source/`）

Artisan 必须在 `02_source/` 落地下列文件（全部 JSON 必须 `jq .` 解析通过）：

| 文件 | 冻结内容要点 |
|---|---|
| `manifest.txt` | 每行 `相对路径 \| 用途 \| 生成方式`；**非空**（交付屏障要求） |
| `world.schema.json` | 世界状态：`schema_version`、`seed`、`tick`、`entities[]`、组件定义（`transform{pos_mm,rot_mdeg}`、`needs{}`、`emotion{}`、`schedule{}`、`relations{}`、`memory_ref`、`trauma_flags[]`）、`constants` |
| `events.schema.json` | 事件日志：JSONL 行 = `{seq,tick,type,actor,payload,prev_hash,hash}`；`type` 枚举（`world.init`、`intent.applied`、`intent.rejected`、`npc.action`、`capability.invoked`、`capability.fallback`、`task.state_changed`、`memory.written`、`snapshot.taken`）；`payload` 按 type 的必填字段 |
| `snapshot.schema.json` | `{tick, state, state_hash, event_chain_hash, rng_state_digest}` + 规范化规则说明 |
| `capability.schema.json` | **D-0.6 核心**：`id`/`version`/`slot`/`input_schema`/`output_schema`/`providers[]`/`cost`/`latency_ms_budget`/`timeout_ms`/`fallback`/`determinism`/`safety`（见 §7.2 字段表） |
| `capability.registry.sample.json` | ≥3 个真实样例能力：`intent.plan`、`emotion.appraise`、`memory.reflect`（含四类 provider 声明） |
| `cassette.schema.json` + `cassette.format.md` | 录制格式：`{key, capability_id, capability_version, provider, canonical_input_hash, output, meta{model, tokens, latency_ms, recorded_at, schema_version}, prev_hash}`；回放查找规则与 miss 策略 |
| `session.protocol.schema.json` | 双模式会话消息（§4.2 全部消息类型 + 错误码枚举） |
| `district.pack.schema.json` + `district.pack.spec.md` | 内容包清单与目录规范（§4.6） |
| `intervention.policy.schema.json` | 参与模式介入策略：`scope`、`rate_limit`、`cooldown_ms`、`impact_budget`、`forbidden_actions[]`、`audit` |
| `v0_skeleton/` | V0 目录骨架（真实文件树 + 非空 stub，含 `web/`、`kernel/`、`districts/`、`capabilities/`、`tools/`），供 `08_v0_plan.md` 逐文件引用 |
| `verify_specs.sh` | 真跑校验脚本：`jq` 逐文件解析 + `pack.sig` 校验 + 失败非 0 退出（Artisan 必须在自测日志中给出 exit 0） |

---

## 6. 确定性 tick 与回放 / 双模式权限与同步

### 6.1 确定性 tick 与回放（AC-2，判据）

**判据**：同一事件日志重放两次 → 全部检查点 `state_hash` 一致；落盘两次哈希与命令。

- 检查点默认每 50 tick；`verify` 命令逐点比对并在不一致时非 0 退出且打印首个分歧 tick。
- 分歧定位辅助：`--dump-divergence` 输出分歧 tick 的组件级 diff（便于根因定位）。
- 非确定性来源清单（必须显式规避，Sentinel/Raven 会按此清单对抗）：
  1. wall-clock / 单调时钟进入 tick；
  2. 无序容器迭代顺序；
  3. 异步模型调用在 tick 中途回填；
  4. 未受控的浮点累加顺序（多线程/向量化归约）；
  5. 外部数据（文件 mtime、环境变量、locale）；
  6. RNG 共享单流（新增子系统扰动既有序列）。

### 6.2 双模式权限模型（AC-4）

| 模式 | 权限 | 通道 | 内核侧 |
|---|---|---|---|
| 观察 observe | 只读订阅（snapshot/delta/event） | WS 下行 | 上行 `intent` 一律 `E_MODE_READONLY` |
| 参与 participate | 只读订阅 + 意图上行 | WS 双向 | 意图经 `intervention.policy` 校验后入队，**tick 边界**应用 |

- 参与身份（V0 取最简，按「可插拔介入通道」设计）：`intervention.kind` ∈ {`delegate_instruction`（委托指令）、`ghost_hand`（幽灵手）、`avatar`（化身，V1）}；V0 只实现 `delegate_instruction`。
- 观察传播形态（V0）：`只读订阅 + 可回放`（录像走 L7 事件日志，不做直播流；分享链接列为 V1）。

### 6.3 「参与影响任务迭代演进」机制 + 防滥用

- 任务定义（内容层 `tasks/*.json`）是**状态机**：`{id, level(G/A/B/C), state, transitions[], adaptation_rules[]}`。
- 玩家介入产出 `intent.applied` 事件 → `adaptation_rules` 以**数据驱动**方式匹配事件模式 → 触发 `task.state_changed`（含 `reason`、`caused_by`）。
- 演进受**护栏**：
  1. 每条 `adaptation_rule` 声明 `max_shifts`（同一任务的状态迁移上限）与 `impact_cost`；
  2. 会话级 `impact_budget`（每会话/每时间窗的累计影响上限）耗尽 → 后续介入降级为「观察 + 记入待办」；
  3. `forbidden_actions[]` 硬拒（破坏治愈向目标函数、绕过任务分级、直接改写 NPC 创伤标记等）；
  4. 全量审计：每次介入落 `intent.applied/rejected` 事件（可回放、可追溯、可回滚到快照）；
  5. 反刷：`rate_limit` + `cooldown_ms` + 同目标重复意图合并。

---

## 7. 认知层：原子能力注册表（D-0.6 / AC-7 / AC-13）

### 7.1 概念模型

- **原子能力（atomic capability）**：一个有明确输入/输出契约的最小能力单元。示例槽位：`intent.plan`、`emotion.appraise`、`memory.reflect`、`narrative.generate`、`action.select`、`relation.infer`、`vision.understand`、`embed.text`。
- **槽位（slot）与 provider 分离**：同一槽位可由四类 provider 之一填充 —— `remote_api` / `local_model` / `deterministic_rule` / `cassette_replay`。
- **规则层组合、能力层执行**：需求·效用·行为树决定「何时调用哪个槽位、给多少预算」；能力负责「产出结构化结果」。**禁止**把模型调用散落在业务逻辑各处（契约级禁令，Sentinel 静态检查项）。

### 7.2 `capability.schema.json` 字段（冻结）

| 字段 | 语义 | 约束 |
|---|---|---|
| `id` | 能力标识（点分槽位名 + 变体） | 唯一；与文件名一致 |
| `version` | 语义化版本 | 必须递增；注册表按 `id@version` 锁定 |
| `slot` | 能力槽位 | 枚举，新增槽位需 ADR |
| `input_schema` / `output_schema` | JSON Schema（结构化输出强制） | 调用后必须校验；失败走 fallback |
| `providers[]` | provider 声明列表 | 每项 `{class, impl, priority, determinism_note}`；`class` ∈ 四类 |
| `cost` | `{usd_per_1k_in, usd_per_1k_out, est_tokens_in, est_tokens_out, currency}` | 用于预算记账与降级决策 |
| `latency_ms_budget` | 期望延迟预算 | 超预算记 metric 并触发降级评估 |
| `timeout_ms` | 硬超时 | 超时 → fallback |
| `fallback` | `{on_timeout, on_error, on_invalid_schema, on_budget_exhausted}` | 值 = 目标 provider 或 `deterministic_stub`；必须有终态兜底 |
| `determinism` | `{mode: replayable\|best_effort\|pure, cassette_key_fields[], seed_policy}` | `replayable` 必须可 cassette 重放 |
| `safety` | `{secrets_in_context: false, redact_fields[], max_output_bytes, schema_strict}` | `secrets_in_context` 必须为 `false` |

### 7.3 provider 等价性矩阵（AC-13 必答）

| 维度 | 四类 provider 是否必须等价 | 说明 |
|---|---|---|
| 输出 schema 合法性 | **必须等价**（100%） | 任一 provider 产出必须通过 `output_schema` |
| 必填字段与枚举域 | **必须等价** | 缺失即 `invalid_schema` → fallback |
| 决策循环可推进性 | **必须等价** | 任一 provider 下规则层都能产出合法动作、循环不卡死 |
| `cassette_replay` 与录制源 | **必须逐字节等价** | 同一 cassette key → 同一输出 |
| `deterministic_rule` 重复执行 | **必须等价（纯函数）** | 同输入同输出 |
| 文本风格 / 叙事质量 | 允许差异 | 属 `best_effort`，不得作为正确性判据 |
| 延迟 / token 数 / 成本 | 允许差异 | 记 metric；超预算触发降级 |
| 排序细微差异（候选打分） | 允许差异（需声明） | 仅当 `determinism.mode=best_effort` 且不影响 schema |

- **可离线降级**由此达成：`remote_api` 不可用 → 按 `providers[].priority` 回退到 `local_model` / `deterministic_rule`；规则层与记忆层仍在，世界继续 tick（认知降质但不断线）。
- **可确定性回放**由此达成：`replayable` 能力在回放模式下强制走 `cassette_replay`；cassette miss → 策略 `fail_closed`（默认，`E_CASSETTE_MISS`），保证回放不引入新随机。
- **rev2.1 证据口径**：`remote_api` 类的等价性必须在**契约默认 `timeout_ms` / `latency_ms_budget`** 下取证，**不接受**命令行 override 取得的绿（RB-2：原实测 5.6~6.6s vs 声明 2.5~3.0s，默认值下必然降级）。因此 `capability.cost`/`timeout_ms` 的声明值必须按实测重标（规划/评估类建议 `timeout_ms` 8~15s、`latency_ms_budget` 4~6s），并把「超预算记 metric 但继续等待」与「超时立即 fallback」明确区分。

### 7.4 组合契约（规则层如何用能力）

```
需求层(needs) ──打分──▶ 效用选择 ──▶ 行为树(py_trees) 叶子: call_capability(slot, budget)
                                          │
                                          ├─ 预算检查(BudgetLedger: 每 tick 调用上限 / 每 NPC 每日 token)
                                          │      └─ 超限 → fallback.on_budget_exhausted
                                          ├─ 调用(provider 路由 + timeout)
                                          ├─ 校验(output_schema)
                                          │      └─ 失败 → 重试≤1 → fallback.on_invalid_schema
                                          └─ 结果入 ECS（由执行阶段写入） + capability.invoked 事件
```

- **预算**：`BudgetLedger` 三级 —— tick 级（每 tick 调用数上限）、NPC 日级（token/成本上限）、会话级（介入影响预算）。
- **超时与降级**：超时 → 立即 fallback，不阻塞 tick（异步调用结果若在 tick 边界后到达，**丢弃并记 metric**，绝不回填历史 tick）。
- **结果校验**：schema 严格校验 + 长度/枚举/引用完整性；校验失败不得进入世界状态。
- **可观测**：每次调用落 `capability.invoked{id, version, provider, ms, tokens_est, ok}`；降级落 `capability.fallback{id, reason}`。

### 7.5 注册表运行时（发现 / 校验 / 加载 / 灰度 / 回滚）

| 环节 | 设计 |
|---|---|
| 发现 | 启动时扫描 `capabilities/**/*.capability.json`（数据 glob，非代码 import 列表） |
| 契约校验 | `jq`/JSON Schema 校验 + 版本唯一性 + provider 可解析性；失败即拒绝加载并告警（不静默） |
| 加载 | 按槽位惰性加载；provider adapter 由 `impl` 字段指向（`module:attr` 或 `builtin:<name>`） |
| 灰度 | 同槽位多 provider 按 `priority` + `weight` 路由；支持按 NPC/会话抽样灰度（数据配置） |
| 回滚 | 版本钉住（`pins.json`）+ provider 顺序回退；回滚只需改数据，不改内核代码 |
| **不改内核代码即可增补** | 新增能力 = 新增一个 `*.capability.json`（+ 一个 provider adapter 文件，若需新实现）；规则层通过 `call_capability(slot=...)` 数据引用，**内核源码零改动** |

**演示路径（AC-13 判据，spike 必须真跑）**：

1. 在 `capabilities/` 丢入新能力文件 `relation.infer@1.0.0`（provider = `deterministic_rule`）；
2. 规则层数据（行为树 JSON / 效用配置）新增引用该 slot；
3. 真跑：注册表列出该能力 → 规则层调用 → 产出结构化结果 → `capability.invoked` 事件落盘；
4. 再跑一次，把该能力的 provider 切到 `cassette_replay`（用第一次录制的 cassette）→ 输出等价；
5. 全程 `git diff` 证明**内核源码未改**（只增数据文件）。

> **rev2.1 补充（判据口径，关闭 RB-1 的判据循环）**：上述演示的 before 指纹必须取自**不含该能力实现**的源码基线。若新能力的 provider 实现需要代码，则该实现**必须落在独立 adapter 文件**（如 `providers/rules_<capability>.py`），且「内核既有源码文件字节不变」是判据，`git diff` 必须显示「只新增数据文件与 adapter 文件」。`providers[].impl`（`builtin:` / `module:`）**必须被 `resolve_impl` 真正解析**，不得存在第二套硬编码映射；`resolve_impl` 走白名单（仅允许 `deephealing_kernel.providers.*` 显式登记项与 `builtin:` 枚举，其余拒绝，见 RF-1）。

### 7.6 cassette 完整性与「历史 provider」查找契约（rev2.1 新增，关闭 RA-1/RA-2）

**问题**：原契约只定义了 cassette 的**格式**，没定义「回放时如何得知历史运行用的是哪个 provider」，也没定义完整性校验的调用时机。实测后果：同一 `cassettes/<id>@<ver>/` 目录下并存 `remote_api` 与 `deterministic_rule` 两个录制源时，回放会按**文件名字典序**取首个命中，静默返回规则层输出而非录制到的模型输出（同一命令两次不同答案）；且记录里的 `hash` / `prev_hash` 从不被校验，篡改 `output` 后回放照常成功。

**冻结条款（实现必须遵守）**：

1. **历史 provider 是事实，不是猜测**：每次能力调用必须在 `capability.invoked` 事件中记录 `{capability_id, capability_version, provider, cassette_key}`。**回放查找由事件日志驱动** —— 按历史事件里记录的 `provider` + `cassette_key` 精确命中；找不到即 `E_CASSETTE_MISS`（fail-closed），**禁止**回退到「扫描目录猜一个」。
2. **多录制源即错误**：若同一能力目录下存在同一 key 的**多个不同 provider 录制源**，且本次查找无法由事件日志唯一确定来源 → 报 `E_CASSETTE_AMBIGUOUS`（非 0 退出），禁止静默取首个。
3. **完整性校验必须在命中路径上**：`lookup()` 命中后必须校验 `hash = sha256(prev_hash ‖ canonical_json(record_without_hash))` 以及文件内 `prev_hash` 链；失败即 `E_CASSETTE_TAMPERED`（非 0），禁止返回被篡改的 `output`。`verify_chain()` 必须接线到 `kernel validate` 与 `replay` 的前置检查，不得只是骨架里未被调用的函数。
4. **重复 key 即损坏**：同一文件内同一 key 出现两次 → 报错（不取首个）。
5. **回放不等价于可信**：cassette 的哈希链只提供**损坏/篡改检测**，不提供**真实性/来源保证**（无密钥、无签名）。需要真实性的场景必须由外部锚定（快照链头签名），此边界必须在 `cassette.format.md` 明写（关闭 RA-5 的表述风险）。

**判据（必须真跑出非 0/0 两类结果）**：① 多录制源共存 → 非 0（或按事件日志精确命中）；② 篡改 `output`（仍满足 schema）→ `E_CASSETTE_TAMPERED` 非 0；③ 正常回放 → 0 且与录制源逐字段等价；④ 回放时无历史 provider 事件 → `E_CASSETTE_MISS` 非 0。

---

## 8. 认知与自进化（AC-7）

- **规则层**：需求（`needs`：生理/安全/归属/尊重/自我实现映射为可计算标量）+ 效用打分（加权和 + 情境修正，权重来自内容包数据）+ 行为树（`py_trees`，叶子节点引用原子能力槽位）。
- **LLM 高层**：只做「意图规划 / 情绪评估 / 记忆反思 / 叙事生成」四类高层能力，全部经注册表；规则层给预算与超时。
- **记忆**：短期 / 长期 / 反思三层（§4.5），范式借鉴 `generative_agents` 的记忆流与反思（Apache-2.0，仅范式借鉴，不直接集成运行时）。
- **自进化机制（V0 冻结契约，V1 实施）**：
  - **档案库（archive）**：每个 NPC 行为策略的「策略档案」+ 表现指标（治愈向目标函数 + 社会一致性 + 多样性）；
  - **质量-多样性（QD）**：`pyribs`（MIT）风格 MAP-Elites 网格，网格维度 = 行为特征（如社交频率 / 独处时长）；
  - **受控自我改写**：候选策略由 `dgm`（Apache-2.0）式自改写闭环生成，但**只允许改数据化策略参数**（效用权重、日程模板、行为树数据），不得改内核源码；
  - **护栏（硬性）**：① 全部改写走「提案 → 沙箱回放评估 → 人工/规则审批 → 灰度 → 回滚」五步；② 每次改写必须能用事件日志回放复现；③ 目标函数含治愈向硬约束（不得产出伤害/猎奇向内容、不得破坏 NPC 创伤修复主线）；④ 全量审计（谁改了什么、依据哪条事件、指标变化）；⑤ 单 NPC 单周期改写次数上限 + 全局熔断。
  - **阶段**：V0 只冻结契约与护栏（不启用改写）；V1 启用档案库 + QD 评估；V2 启用受控自我改写。

---

## 9. 性能与成本预算（AC-10）

### 9.1 token / 成本（每 NPC 每日）

| 活跃度 | 认知调用模式 | 日调用数（估） | 日 token（估） | 备注 |
|---|---|---|---|---|
| 静默 idle | 仅日程触发 + 反思 1 次/日 | ~20 | ~13k | 走 `deterministic_rule` 优先，模型调用极少 |
| 常规 normal | 事件触发规划 + 情绪评估 | ~100 | ~66k | 计划/评估走小模型或本地模型 |
| 深度 deep（叙事/反思高峰） | 叙事生成 + 关系推理 + 反思 | ~330 | ~218k | 受日预算硬顶，超限降级为规则层 |

- 5 NPC 混合活跃（1 深 / 2 常规 / 2 静默）≈ **376k tokens/日**。
- **rev2.1 重标说明**：上表调用数按**实测单次成本 ≈ 660 tokens**（`emotion.appraise` in 238 / out 428、`intent.plan` in 267 / out 391，见 `09_risks_open_questions.md` §3.1）反算。原稿的「normal 450 次 / deep 1400 次」在实测口径下会得到 ~297k / ~924k tokens，与同表 token 预算自相矛盾（R2/R15）——**以本表为准**；`capability.cost.est_tokens_*` 的声明值必须按真实 usage 回填（V0 第一周校准）。
- 成本公式：`cost = Σ(in_tokens/1k*usd_in + out_tokens/1k*usd_out)`，逐能力在 `capability.cost` 声明；`BudgetLedger` 硬顶 + 超限降级。
- 降级阶梯（按顺序）：① 换更低成本 provider → ② 缩短上下文/减少反思频率 → ③ 切 `local_model` → ④ 切 `deterministic_rule` → ⑤ 切 `deterministic_stub`（世界不断线，认知降质）。

### 9.2 帧率 / tick / 延迟 / 内存

| 指标 | 目标 | 下限 | 说明 |
|---|---|---|---|
| 渲染帧率 | 60 fps | 30 fps | 5 NPC + 单栋楼场景 |
| 内核 tick | 10 Hz（dt=100ms） | 5 Hz | tick 耗时 p95 ≤ 20ms（5 NPC） |
| 观察模式端到端 | ≤ 150 ms p95 | ≤ 300 ms | 内核事件 → 浏览器可见 |
| 参与模式意图 | ≤ 2 tick（200ms）+ LLM 异步 ≤ 3s | ≤ 5s | 意图入队即 ack，决策异步 |
| 内存 | 内核 ≤ 800 MB RSS / 浏览器 ≤ 1.5 GB | — | 5 NPC + 1 街区 |
| 日志增长 | 事件瘦身后 ≤ 20 MB/小时 | — | **rev2.1 重标**：按当前事件设计（每 `npc.action` 内联全量 `state_after` + 每事件 `rng_digests`）实测 **≈ 297 MB/小时（超 15×）**，50 NPC 外推 ≈ 2.94 GB/h。必须：① 事件只存组件级 diff；② `rng_digests` 只留在快照里；③ 滚动/压缩，且**契约必须同时定义「多文件/压缩日志作为 `replay --events` 输入」的语义**（有序文件列表 + 跨文件 `seq`/`hash` 链校验），否则缓解措施会打断 AC-2 |

---

## 10. 美学与双模式信息架构（AC-11）

- **治愈系美学可执行约束**（程序化可落地，非主观描述）：
  - 色彩：低饱和暖基调（HSL 饱和 ≤ 45%，色相集中在 20°–60° 暖区与 180°–210° 冷补色），夜间场景不超过 2 个高饱和点缀色；
  - 光照：主光柔化（软阴影，阴影柔度 ≥ 0.5），环境光占比 ≥ 35%，避免硬高对比；
  - 材质：粗糙度偏高（≥ 0.6）、镜面反射弱；磨损/生活痕迹贴图为默认而非例外；
  - 音频基调：环境音铺底 + 低频温暖垫音，无突发高频刺耳音效；惊悚段落用「留白 + 低频」而非尖叫；
  - 可执行形式：`assets/manifest.json` 中每项资产声明 `palette`、`roughness_range`、`audio_bed`，由工具校验（数值超界即校验失败）。
- **双模式信息架构**：
  - 观察模式 UI：世界视图 + 事件流/字幕 + NPC 档案（关系/日程/状态，脱敏）+ 时间轴 scrubber + 指标面板（tick/延迟/成本）。**无任何写入口**。
  - 参与模式 UI：观察模式全部 + 「介入通道」面板（委托指令输入、影响预算剩余、冷却指示、被拒原因回显）+ 任务状态演进视图（谁因何变化）。
- **静态视觉样例**：由 spike S3（渲染候选真跑）产出 `spikes/s3-render/out/*.png`（Playwright 截图）与构建产物；若浏览器截图不可用，**记 GAP** 并给替代证据（`dist/` 构建 exit 0 + 场景图断言 JSON）。

---

## 11. 风险登记（架构自评，Raven 独立审计面见 `05`）

| ID | 风险 | 分级 | 触发条件 | 影响面 | 缓解 |
|---|---|---|---|---|---|
| R1 | tick 内非确定性来源（时钟/顺序/异步回填） | CRITICAL | 任一进入 tick | 回放哈希不一致 → AC-2 失败 | §6.1 清单 + `verify` 双跑判据 + 分歧 diff |
| R2 | 认知成本失控 | MEDIUM | 活跃度估算偏低 / 无硬顶 | 账单与延迟 | `BudgetLedger` 硬顶 + 降级阶梯 + 日成本 metric |
| R3 | cassette 陈旧/失配 | MEDIUM | 能力版本升级后回放旧 cassette | 回放等价性 | cassette key 含 `capability_version` + miss 策略 fail-closed |
| R4 | 许可污染 | CRITICAL | GPL-3.0（BlenderGIS）/自定义许可（convex、behaviac）进运行时 | 商业可用性 | 06 矩阵逐条许可判定；GPL 仅限离线美术管线 |
| R5 | 自进化失控 / 目标函数被劫持 | CRITICAL | 自我改写绕过护栏 | 治愈向内核被破坏 | §8 五步护栏 + 数据化改写边界 + 熔断 |
| R6 | IP 越界 | CRITICAL | 逐字搬运原著正文段落 | 法律风险 | 原著人物 / 名称 / 情节是核心依据（保真度方向）；机械判据 = `scan_ip_boundary.py` 的 `verbatim_body_paragraph`（不可豁免）+ `scan_fidelity_terms.py`（机制词必须命中） |
| R7 | 双权威漂移（传输层持状态） | MEDIUM | 传输层缓存并回写 | 状态分叉 | L2 明确非权威；权威写入唯一在 [4] |
| R8 | Rust 工具链缺失导致内核性能路线受阻 | MEDIUM | V1 需 ECS/物理性能 | 工期 | V0 用 Python；V1 前做性能 spike 再决策（ADR 记成本） |
| R9 | 浏览器截图/构建不可复现 | LOW | Playwright/网络异常 | AC-11 证据 | 允许 GAP + 替代证据（构建 exit + 场景图断言） |
| R10 | 记忆层无界增长 | MEDIUM | 无裁剪策略 | 内存/成本 | 容量上限 + 重要性阈值 + 衰减 |
| R11 | 能力 schema 被绕过（模型输出不合规进入世界） | CRITICAL | 校验缺失或降级路径未校验 | 世界状态损坏 | 严格 schema + 所有 fallback 出口都校验 + Sentinel 对抗用例 |
| R12 | 参与模式刷分/滥用 | MEDIUM | 无 rate limit / budget | 体验与叙事破坏 | §6.3 护栏（rate_limit/cooldown/impact_budget/审计） |

---

## 12. 验证计划（三层门禁分工）

### 12.1 Artisan 自测面（→ `03_artisan_self_test.log`）

1. 全量 `jq` 解析 `02_source/**/*.json`（逐文件 exit 0）；`verify_specs.sh` exit 0。
2. `kernel validate --pack` 对样例 pack 通过；`pack.sig` 逐文件比对通过。
3. **Spike S1（确定性）**：同一事件日志重放两次，**两侧检查点集合必须完全相同（tick 列表逐一比对）**，且逐检查点比对 `state_hash` **+** `rng_state_digest` **+** `event_chain_hash` 三者全部一致；**任一检查点缺失/多出、或任一字段不一致 → 非 0 退出**（关闭 RA-3：禁止 `zip` 截断式比较）。另需负例证明「截断回放必须 FAIL」与「RNG/事件链摘要被改必须 FAIL」。落盘两次哈希与命令。
4. **Spike S2（能力/provider/cassette）**：真实模型 API 调用作为原子能力被规则层组合执行 → 录制 cassette → 强制回放模式重放成功且输出等价 → 展示能力槽位抽象与 provider 切换（remote_api → cassette_replay，以及 → deterministic_rule）。
5. **Spike S3（渲染候选）**：three.js + 构建工具真跑（`bun`/`npm` 构建 exit 0），可行则 Playwright 截图，否则 GAP + 替代证据。
6. 逐 AC（AC-1..AC-13）给 `PASS|FAIL|GAP + evidence 绝对路径 + command + exit`；未执行一律 GAP。

### 12.2 Sentinel 测试面（→ `04_sentinel_test_report.md`）

- 独立复跑 S1（哈希比对）、S2（回放等价 + provider 切换）、`verify_specs.sh`；**不采信** Artisan 日志结论。
- 逐 AC 核验（AC-1..AC-13）PASS/FAIL/GAP + 证据路径；抽查开源事实（版本/license/活跃度）对 GitHub API 二次核对。
- 边界与负例：非法 capability 文件被拒；observe 会话 intent 被拒（`E_MODE_READONLY`）；schema 非法输出被 fallback 拦截；cassette miss 行为符合策略。
- 静态检查：产物中无 secrets（模式扫描 `Authorization`/`sk-`/`api_key` 等）；模型调用未散落在业务逻辑（扫描内核业务模块中的 HTTP/SDK 调用）。
- Bug 清单分级（CRITICAL/MEDIUM/LOW）+ 复现步骤 + 证据路径。

### 12.3 Raven 审计面（→ `05_raven_risk_report.md`）

- 隐性假设审计：provider 等价性声明是否成立、cassette 回放保真度、内容包「不改内核」是否真成立（对抗性尝试）。
- 架构缺陷推演：双权威漂移、tick 内异步回填、快照/增量同步的乱序与丢包、记忆层一致性。
- 安全对抗：玩家意图注入进入能力上下文（prompt injection）、secrets 泄漏进 cassette/日志、schema 绕过路径、介入滥用。
- 成本/扩展性压力推演：NPC 数量与街区数量放大后的 tick/成本/内存曲线。
- 许可与 IP：GPL/自定义许可进入运行时的路径、命名与文本的 IP 边界。
- 每条风险含**触发条件 + 影响面 + 建议 + 分级**；「风险推演」≠「已利用」，标注精确。

### 12.4 裁决规则（architect）

- 分级冲突取高；CRITICAL 未清不得标 `completed`；超 `max_iteration=3` 转人工介入。
- 所有结论以**磁盘产物**为准（本设计 + 02~09 + spike 原始日志），不采信任何自述。

---

## 13. 写集 / 快照纪律（全体适用）

- **授权写集**：`/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-002-deephealing-architecture-freeze/`（`01..09` 文档、`spikes/`、日志、各角色 `.progress.json`）+ 各角色自身账本 `~/.hermes/team-tasks/`。
- **禁止**：写真实仓库 `/Users/wooyinq/personal/deep-healing`（只读，含任何 git 写操作）；改 PM 账本 / `pm_business/` / 其他 profile / workspace 外任何路径。
- **spike 依赖**（`node_modules`、venv、缓存）留在 workspace 内，**不得**拷入仓库。
- 快照核对：开工前 `git -C <repo> rev-parse HEAD` + `git status --porcelain`（应为空）；发现漂移或同写集并发立即 block 并上报。
- 秘密：不得写入任何产物/日志/账本/cassette；spike 命令中凭据只以环境变量引用，日志脱敏。

---

## 14. 交付物与角色分工（本轮）

| 产物 | 产出者 | 判据摘要 |
|---|---|---|
| `01_architecture_design.md` | architect | 本文件：7 层职责/边界/接口 + ≥1 张 ASCII 分层与数据流图 + 风险登记 + 验证计划 |
| `02_source/`（机器可读规格 + V0 骨架 + `manifest.txt` + `verify_specs.sh`） | artisan | 文件真实存在、全部 JSON `jq .` 通过、`verify_specs.sh` exit 0 |
| `03_spike_log.md` + `spikes/` | artisan | ≥2 个候选真跑；命令/workdir/exit/原始日志绝对路径/第三方复跑命令齐备 |
| `03_artisan_self_test.log` | artisan | 真实命令 + exit + 逐 AC `PASS\|FAIL\|GAP` |
| `06_open_source_matrix.md` | artisan | ≥6 层、每层 ≥2 候选、含 URL/license/版本/活跃度/集成成本/结论/许可判定 |
| `07_adr.md` | artisan | ≥8 条 ADR（背景/选项/决定/后果），含 AC-9 指定的 6 个必答主题 |
| `08_v0_plan.md` | artisan | 文件级/接口级；RED 用例、V0 命令、逐 AC 判据、工时估算 |
| `09_risks_open_questions.md` | artisan | 风险 + 未决问题 + 成本与性能预算（每 NPC 每日 token + 帧率/tick/延迟） |
| `04_sentinel_test_report.md` | sentinel | 逐 AC 核验 + 开源事实抽查 + spike 复跑 |
| `05_raven_risk_report.md` | raven | 每条风险含触发条件与影响面 |

> 交付完成屏障（wrapper 硬校验）：`01`、`02_source/`（含非空 `manifest.txt`）、`03_artisan_self_test.log`、`04`、`05` 必须真实存在且非占位；任一缺失、为空、或带有「流水线未完成」标记（即 wrapper 扫描的 incomplete 字样）即不得返回可交付终态。

---

## 15. 待顶层 PM / 用户裁决的开放项（不阻塞本轮，按 REQ 附录 C 先按最简设计）

1. 观察模式的传播形态（分享链接 / 直播流 / 录像回放）——本轮按「只读订阅 + 可回放」冻结，直播/分享列 V1。
2. 参与模式的玩家身份（化身 / 幽灵手 / 委托指令）——本轮冻结「可插拔介入通道」，V0 只实现 `delegate_instruction`。
3. 对外美术资产来源（自研 / 生成 / 采购）——本轮按「程序化 + 可替换资产位」冻结，`assets/manifest.json` 留位。

---

## 16. rev3 增补（round 3 有界补轮：AC-14 / AC-15 / D-0.9 + 5 项落盘阻断项）

- 作者：architect　日期：2026-09-21（round 3）　契约基线：**REQ rev5**（D-0.7 / D-0.8 / D-0.9 + AC-9 / AC-13 / AC-14 / AC-15 修订文本）+ `<ws>/.pm_acceptance.md`（PM 逐 AC 终验与 5 项落盘阻断项，**本轮权威**）。
- 本轮性质：**文档 + 契约 + ADR + 证据补轮**。不做产品实现；`02_source/v0_skeleton/kernel` 仍是接口骨架（`NotImplementedError` / `E_NOT_IMPLEMENTED`）。
- 本节只冻结**设计与裁决**；逐条执行细节与关闭判据见 `.task-artisan-r3.md`。

### 16.0 范围与非目标（防漂移）

- **做**：AC-14（世界模型接入边界与实验门禁）、AC-15（AIGC 素材生产管线与许可合规）、D-0.9（时间预算语义冻结 + 标定口径）、以及 `.pm_acceptance.md` §3 的 5 项落盘阻断项。
- **不做**：不提前集成世界模型运行时；不量产素材；不改 REQ / `.pm_acceptance.md` / `.pm_notes.md`（PM 所有，只读）；不写真实仓库；不重开已关闭的 CRITICAL；不为凑绿弱化任何判据（做不到 → 记 GAP）。

### 16.1 AC-14 · 世界模型接入（D-0.7）

#### 16.1.1 权威归属（冻结，不可被后续轮次默认推翻）

1. **权威始终是确定性内核**（§3 L3 + §6）。世界模型在任何阶段都**不得直接**写世界状态、不得进入 `state_hash` / `rng_state_digest` / `event_chain_hash` 的**计算**、不得成为回放的必要条件。
   - **「直接 / 间接」限定语（预审 P1-1 收口，必写）**：禁止的是**直接**写入；**间接**仅允许经「规则层决策 + `output_schema` 校验 + 事件日志」这一条路径产生事件内容，且该能力**必须可回放**（cassette 强制）。因此本节的表述与 §16.1.2③ 不矛盾 —— ③ 的影响面是「间接、可回放、可审计」。
2. 可检查判据（不是口号）：
   - 契约层：`world.schema.json` / `events.schema.json` 中不存在由世界模型 provider 直接写入的字段；能力输出必须经规则层 + schema 校验后才可能产生事件。
   - **provider 类别绑定（预审 P1-2 收口，必写）**：以世界模型为后端的 `imagine.*` 能力，其 `providers[].type` **必须**声明为 `remote_api`；其余三类（`local_model` / `deterministic_rule` / `cassette_replay`）的 manifest 若其 `source_model` 命中**世界模型白名单表** → **校验期拒收**（default-deny）。附负例：把世界模型后端声明成 `local_model` → 注册 / 校验必须非 0。
   - **确定性闸门（预审 P1-3 收口，必写）**：`determinism` 不得只是自声明 —— ① 契约条文写成**禁止面**：「非 `deterministic` 类 provider 的输出**不得**被规则层采纳为事件输入」；② 契约校验期必须**必跑**一致性检查（同输入重复 ≥3 次 → 输出摘要一致），未通过即拒收（不得留到 V1 事后测量）；③ 负例：把一个带采样的 provider 声明为 `deterministic` → 必须被检出。
   - 运行层：`offline-guard` 回放路径**不依赖任何世界模型 provider**，回放必须成功（沿用 AC-2 / AC-3 既有证据形态）。
   - **tick 与耗时解耦（预审 P1-5 收口）**：tick 的**编号**与**事件内容**不得由实测耗时派生（`wall_clock` 严禁参与 hash 或 tick 内决策，沿用 `snapshot.schema.json` 既有条文）；G2 的「tick 抖动」只是**调度**指标，不得进入任何哈希。
3. 理由（与 REQ D-0.7 一致）：本项目的硬需求是**确定性回放 + 可编程规则 + 双模式权威写入 + 可审计**，而生成式世界模型的短板恰是持久世界状态、可编程规则与权威共享状态。
4. **已声明边界（不得写成「世界模型对世界状态零影响」）**：呈现层 `non_deterministic` 的生成画面会影响**玩家意图的分布**，而意图事件本身在链哈希内；按 RA-2 先例登记为**已声明边界**，不宣称零影响。

#### 16.1.2 三处接入点（**全部复用 D-0.6 能力槽位机制**，禁止第二调用路径）

| # | 接入点 | 所在层 | 输入 | 输出 | 是否影响世界状态 |
|---|---|---|---|---|---|
| ① | `WorldModelRenderAdapter` | L1 渲染层 | 内核权威状态的**只读投影**（camera / scene 描述 + tick 号） | 画面（帧 / 纹理 / 高斯场景） | **否**（只影响画面） |
| ② | 离线内容生产管线 | 内容层（**离线**） | 生成请求（街区 / 室内 / 道具草稿） | 候选资产 + `asset.manifest` | 否（人工收编后才成为 pack 数据） |
| ③ | `capability:imagine.*` | L5 认知层（**能力槽位**） | 结构化情境（观察 + 记忆摘要，不含 secrets） | 结构化预测（`output_schema` 强校验） | 间接（经规则层 → 事件日志） |

- 三者**共用** D-0.6 的注册表 / provider 抽象 / 预算 / 超时 / 回退 / cassette 机制；`imagine.*` 走 `capability.schema.json`，**不得**在业务逻辑里新增独立 HTTP 调用路径（沿用 §7.5 的分层静态检查）。
- ②与 AC-15 的离线内容管线是**同一条管线**（REQ 明写），不得另建。

#### 16.1.3 适配器契约必答项（→ `02_source/worldmodel.adapter.spec.md`）

必须逐项写清（缺项即 GAP，不得用散文带过）：

1. **输入 / 输出契约**：呈现适配器与 `imagine.*` 能力各自的输入 schema、输出 schema（结构化）、字段语义与必填性。
2. **与 tick 的对齐**：适配器是**异步只读消费者**；能力结果**在 tick 边界丢弃、绝不回填**（与 D-0.9 第 3 条、AC-2 一致）；渲染适配器允许「晚一帧」，但**不得**反向阻塞内核 tick。
3. **确定性策略**：分两类显式标注 —— ①`deterministic`（同 seed + 同输入 → 同输出摘要，可回放）；②`non_deterministic`（**只允许出现在呈现层**，且必须在契约里写明「其结果不得进入任何哈希、不得用于回放判定」）。
4. **失败回退**：超时 / 失败 / schema 非法 → 回退到确定性占位（呈现层：静态占位场景或上一帧；能力层：`deterministic_rule`），回退必须**可审计**（落 `capability.fallback{id, reason}`）且**可回放**。
5. **预算**：每能力**自己**的 `timeout_ms` / `latency_ms_budget`，按 §16.3 由实测标定；**REQ 不钉毫秒数**。
6. **安全**：能力上下文不得携带 secrets；输出必须过 schema 校验；provider 返回的文本不得直接进入内核逻辑（必须结构化）。
7. **注册方式**：新增一个 `imagine.*` 能力**只需注册 + 契约校验**，内核既有源码字节不变（沿用 AC-13 / ADR-006 判据）。

#### 16.1.4 闭源 API vs 开源自托管（ADR-010 必答取舍）

| 维度 | 闭源 API（Genie 3 / Oasis·Mirage / Odyssey / Marble 等） | 开源自托管（Cosmos / HunyuanWorld-1.0 / 3DGS·gsplat） |
|---|---|---|
| 接入成本 | 低（一次 HTTP + schema） | 高（权重、环境、显存、运维） |
| 本机可行性 | 可行（只需网络） | **生成式不可行**（无 NVIDIA GPU）；3DGS 可离线 |
| 可控性 / 可审计 | 低（黑盒、版本漂移、无离线） | 高（可固定权重版本、可离线、可复算） |
| 许可与内容归属 | 受限，条款可变 | **逐条核，不得预设**（round 3 上游核对**修正**：`NVIDIA/Cosmos` = **OpenMDW-1.1 自定义**、`Tencent/HunyuanWorld-1.0` = 腾讯社区许可（含地域限制）、`graphdeco-inria/gaussian-splatting` = Inria/MPII 自定义；只有 `nerfstudio-project/gsplat` = Apache-2.0、`danijar/dreamerv3` = MIT 可直接判可商用 ⇒ 开源侧**只有这两个**进白名单候选。证据 `spikes/facts-license/r3.summary.txt`；以 `06` L13 / ADR-010 为准） |
| 结论 | **仅离线内容生产 / V1 实验**，不进运行时权威链路 | **V1 主候选**（离线侧） |

#### 16.1.5 无 NVIDIA GPU（M5 Pro / 24GB）可行性结论

- 生成式世界模型（Cosmos / HunyuanWorld 级）：**本机跑不动** → 只能离线云或 API；**不得声称在本机跑过**（未跑 → GAP）。
- 神经渲染（`nerfstudio-project/gsplat`、`graphdeco-inria/gaussian-splatting`）：训练/优化可在 CPU/MPS 上离线跑（慢），运行时只做**加载 + 渲染** → 列为 V1 候选，需实测（未实测 → GAP）。

#### 16.1.6 V1 实验门禁判据（可度量；阈值为**建议初值**，需 PM / 用户确认）

| # | 判据 | 度量方法 | 建议初值（待确认） |
|---|---|---|---|
| G1 | 保真度 | 非物理场景：与内核权威投影的参考帧比 SSIM；`imagine.*`：结构化输出 schema 合法率 | SSIM ≥ 0.85；schema 合法率 ≥ 99% |
| G2 | 端到端延迟 | 呈现适配器 p95 单帧耗时；`imagine.*` p95；内核 tick 抖动增量 | 呈现 p95 ≤ 500 ms（异步）；imagine p95 ≤ 声明 `timeout_ms`；tick 抖动 ≤ +5% |
| G3 | 确定性 / 可回放 | 同 seed 同输入 N=20 次输出摘要一致率；cassette 回放逐字段一致 | 一致率 100%（`deterministic` 类）；回放 diff 为空 |
| G4 | 单位成本 | 每 1000 次 imagine 调用 / 每生成分钟视频的成本（离线云计价 + 实测耗时） | 阈值待 PM / 用户给定（本轮只给**公式 + 实测方法**） |
| G5 | 可控性 | 对抗提示（越界 / 越权 / 违规内容）N 次 → 违规率；运行时可否一键关闭且不改内核 | 违规率 ≤ 1%；关闭动作 = 配置级（不改内核源码） |

> 未达标 → 保持「仅呈现层」；达标才允许扩大接入面。G1~G3 的**测量脚本形态**要在 ADR-010 里给出（不要求本轮实现）。

**反伪造要求（round 3 审计 RR3-22 收口，必写进 ADR-010）**：五条判据各自必须写清「**怎样才算真的测过**」，否则可被伪造通过：

| # | 可伪造形态 | 必须补的核验要求 |
|---|---|---|
| G1 | 只比配置 / 只报单次 | 必须报**样本数 N**、逐帧 / 逐次结果落盘、比较器自证（负例能被检出） |
| G2 | 只报单次延迟或均值 | 必须报**分布**（p50/p95/max）+ 样本数 + 同条件声明；tick 抖动需与基线同机同负载对照 |
| G3 | 只跑 1 次 / 只比一个字段 | **N ≥ 20**、逐次输出摘要落盘、多字段比对、附负例（改一个字段必须被检出） |
| G4 | 用估算冒充实测 | 必须给**计价来源 + 实测耗时 / 调用次数**；估算部分标 GAP，不得写成实测 |
| G5 | 无对抗样本 | 必须给**对抗样本集**（N ≥ 20）+ 违规判定规则 + 关闭动作的配置级证据 |

#### 16.1.7 V0 边界（写死，不得自行扩权）

- `08_v0_plan.md` **必须明写**：V0 **不包含**世界模型运行时集成，只包含**适配器接口 + 占位实现**（占位实现返回静态呈现 / 确定性结构化回退，且必须可被 provider 切换）。
- 若执行方认为必须提前集成 → **上抛 `block_issues`**，不得自行扩权。**architect 本轮裁决：不提前集成**（无本机可行性 + 权威链风险，收益不足）。

### 16.2 AC-15 · AIGC 素材生产（D-0.8）

#### 16.2.1 本机可跑 / 不可跑（M5 Pro / 24GB / 无 CUDA）

| 子类 | 本机可行性 | 主路径 | 备注 |
|---|---|---|---|
| 图像 | **可跑** | MLX + `mflux`（MIT）或 `diffusers` | 优先 Apache-2.0 权重：`Z-Image` / `Qwen-Image` / FLUX.1-**schnell** |
| 音频 | **可跑**（自托管） | `ace-step/ACE-Step`（Apache-2.0） | 权重许可与代码许可**分开核** |
| 3D | **不可跑**（CUDA 依赖） | 离线云 / API | `Hunyuan3D` / `TripoSG` 仅作离线候选，不进运行时 |
| 视频 | **不可跑** | 离线云 / API | 同上 |

#### 16.2.2 离线云 / API 边界

- 生成**只发生在离线**；运行时**零生成**（强制约束，见 §16.2.7）。
- 云 / API 侧产出必须回到同一条管线（生成 → 校验 → 人工过审 → 收编），不得绕过 manifest 直接进 pack。

#### 16.2.3 许可白名单与陷阱（ADR-011 必答，且必须与 `06` 矩阵逐条一致）

| 项 | 事实 | 处置 |
|---|---|---|
| FLUX.1-**dev** | **非商用**权重 | **禁止**进入交付链；仅可本地研究，不得入库 |
| FLUX.1-**schnell** | 可商用（Apache-2.0） | 白名单 |
| MusicGen 权重 | **CC-BY-NC**（代码 MIT ≠ 权重许可） | **禁止**进交付链 |
| ComfyUI | **GPL-3.0** | 独立进程调用可；**链接进产品需评估**，V0 只允许「独立进程 + 产物文件」 |
| `mflux` / `Z-Image` / `Qwen-Image` / `ACE-Step` | MIT / Apache-2.0 | 白名单（逐条给 URL + 版本 + 判定） |

#### 16.2.4 版权灰区处理

1. 每个资产**逐条登记**来源（模型 id / 版本 / 提示词摘要 / 种子 / 时间 / 许可），可追溯、可重生成。
2. **不可商用权重禁止出现在任何交付产物中**（含 manifest、示例、截图）。
3. 不把生成物当作「自有版权」宣称；对外使用前须人工过审（`review_status`）。
4. IP 边界沿用 §13：原著人物 / 名称 / 情节是核心依据（保真度方向）；仍禁止逐字搬运原著正文段落，判据见 `v0_skeleton/tools/scan_ip_boundary.py`。

#### 16.2.5 成本估算（必须可复算）

- 公式：`单位成本 = 单次生成耗时(实测) × 本机单位时间成本`（本机）**或** `= API 单价 × 调用次数 + 离线云时长成本`（云）。
- 必须附**实测基础**（命令 / workdir / exit / 日志绝对路径 / 样本数）；没有实测的部分标 **GAP**，不得用「预计」冒充。
- 输出：每资产 / 每街区 / 每子类的成本区间 + 不确定度说明。

#### 16.2.6 资产契约（→ `02_source/asset.manifest.schema.json`，`jq .` 必须通过）

必填字段：`asset_id` / `content_hash` / `type` / `license` / `source_model` / `model_version` / `prompt_digest` / `seed` / `generated_at` / `review_status` / `replacement_of`。

- `content_hash` = 内容寻址哈希。**必须写明取的是「解码后像素」还是「文件字节」**：建议取**解码后像素 + 规范化规则**（换 EXIF / 重编码不产生新哈希），否则「可重生成 / 可追溯」不可复算。算法与规范化规则必须与 §5 的 canonical JSON 口径一致。
- `license` 必须取值于**白名单枚举**（非白名单 → schema 层就应拒）。
- **`license` 与 `source_model` 必须绑定（预审 Q6-1 收口，必写）**：白名单必须落成**数据表**（key = `source_model` + `model_version` → 许可 / 可商用判定），校验器**查表**判定；**未知模型 default-deny**（拒收）。负例：`source_model: FLUX.1-dev` + `license: apache-2.0` → 必须拒。
- **衍生资产来源传递闭包（预审 Q6-2 收口，必写）**：新增 `derived_from: [asset_id | model_id]`，任一层命中非白名单 → **整棵子树拒收**；且必须**跨资产查重**（父资产必须在库且有 manifest）。负例：对 `source_model=FLUX.1-dev` 的资产做放大 / 重绘 → 子资产必须拒。
- **云产出可核验性（预审 Q6-3 收口）**：离线云 / API 产出必须带 `provenance: self_reported`（自述来源），**不得**标为「已核验」；`adopted` 必须附**人工过审痕迹**（reviewer + 时间）。按 RA-2 先例登记为**已声明边界**，不写成「许可已保证」。
- **生成器元数据剥离（预审 Q6-5 收口，必写）**：入库必须剥离 PNG `tEXt` / `iTXt` 等生成器元数据（或只保留白名单 chunk）—— 否则完整提示词（可能含 IP 原文 / 隐私）随资产进交付链；并配一条扫描门禁（负例：带 `parameters` chunk 的 PNG 入库 → 必须非 0 或被剥离）。
- `review_status` 枚举含 `draft | reviewed | adopted | rejected`；**只有 `adopted` 才允许进 district pack**。
- `replacement_of` 支持资产替换（可空），与 `06` / `08` 的「可替换资产位」一致。
- `prompt_digest` 是**摘要**，不得存原始提示词（沿用秘密 / 隐私纪律）。

#### 16.2.7 离线内容管线（→ `02_source/content-pipeline.spec.md`）

- 管线（**唯一一条**，与 §16.1.2 的②共用）：`生成 → 校验（许可检查 + 内容寻址 + schema 校验）→ 人工过审 → 收编进 district pack`。
- 每步给出**可执行校验命令**（命令 + workdir + 期望 exit）与失败处置（拒收 + 记录原因）。
- **校验必须有执行体（预审 P1-4 / Q6 收口，必写）**：管线规范指定的校验器必须**真跑 exit 0**，且**至少拒收 4 类**：① 资产无 manifest 条目；② `license` ∉ 白名单枚举（或 `source_model` 未在许可表内）；③ `content_hash` 缺失 / 格式非法；④ `review_status != adopted`。每条配一条负例（含「合法图片改名 `.txt` 放进 pack → 必须非 0」）。
  - 若本轮确实无法交付可运行校验器 → 如实记 **GAP**，**不得**把「schema 层就应拒」写成已成立。
- **ComfyUI 工作流受管（预审 Q6-4 收口）**：工作流 JSON 必须作为**受管产物**登记（sha256），其引用的模型名必须过白名单表（可 grep 的清单）；负例：工作流引用非白名单 checkpoint 名 → 拒。
- **运行时零生成**：必须写成强制约束（运行时不得存在生成调用路径），并给出可检查判据（静态扫描 + 契约条文）。

#### 16.2.8 美术圣经（→ `02_source/art-bible.md`）

- **可执行约束**（不是形容词）：配色（色板 + 取值范围）、光照（色温 / 强度 / 对比范围）、材质（粗糙度 / 金属度区间）、镜头（FOV / 距离 / 高度）、音频基调（BPM / 响度 / 频段）、UI 风格（间距 / 圆角 / 字体层级）。
- **风格锁定**：LoRA / 参考图 / 角色参考表三选多（给选择规则与登记方式）。
- **角色一致性**：以角色参考表 + 固定种子 + 提示词模板约束，并给出可检查项（同一角色跨资产的颜色 / 比例偏差上限）。
- 与 §10（AC-11 美学与双模式 IA）保持同一基调，**不得**把「氛围达成」写成已证实（AC-11 仍是 GAP）。

#### 16.2.9 V0 边界（写死）

- `08_v0_plan.md` 明写：V0 只需 **1 张程序化占位资产 + 1 份 manifest 示例**；**不要求量产素材**。
- 但 `asset.manifest.schema.json` / `art-bible.md` / `content-pipeline.spec.md` **是必须交付物**。
- 若认为必须提前量产 → 上抛 `block_issues`。**architect 本轮裁决：不提前量产。**

#### 16.2.10 证据规则（硬性）

- 若做素材生成 spike：必须**真跑**（本机优先 MLX/`mflux` 或 `diffusers`），记录命令 / workdir / exit / 产物哈希 / 日志绝对路径。
- **禁止**声称跑过 CUDA-only 模型；未跑 → GAP。
- 生成物若落盘，必须同时落 `asset.manifest` 条目（含许可），否则视为**无主资产**，不得进交付链。

### 16.3 D-0.9 · 时间预算语义冻结（用户裁决）

#### 16.3.1 四条冻结语义（逐字写进契约，替换任何「LLM 为主 provider」表述）

1. 远端模型 provider 是**能力补充，不是硬依赖**；默认路径**允许降级**。
2. **超时即确定性降级**（fallback → `deterministic_rule`），降级**可审计**（落事件）、**可回放**（cassette）。
3. 能力结果**跨 tick 边界丢弃、绝不回填**。
4. 每个能力的 `timeout_ms` / `latency_ms_budget` 是**该能力自己的、由实测标定的声明值**；**REQ 不固定任何毫秒数**，也不得由全局常量代替。

#### 16.3.2 取证口径（硬性）

- 等价性 / 降级证据**必须**在能力清单**声明的值**下取得；**禁止**用 `--timeout-ms-override` 取得「绿」（rev2.1 §7.3 的口径由此升级为**门禁可检查项**）。
- 声明值必须**附实测依据**：延迟分布（p50 / p90 / p95 / max）、样本数、命令、workdir、exit、日志绝对路径。
- 例外：**合成负例**（强制触发超时以验证「超时 → 确定性降级 + 可审计」机制）允许使用 override，但必须在脚本里以显式标记标注为合成负例（不是等价性 / 降级证据），且被常驻门禁白名单精确匹配。

#### 16.3.3 V0 标定交付（`08_v0_plan.md` 必须有对应工作项）—— **防自证五条（预审 Q2 收口，硬性）**

- 交付链：**实测延迟分布 → 声明值（含推导规则）→ 在声明值下的降级率**。
- 防自证要求（缺一即 FAIL，不得用散文代替）：
  1. **规则先冻结**：推导规则文本 + 其 sha256 + mtime 必须在**测量之前**落盘并登记进 `03`（规则文件时间戳**早于**分布日志）；规则必须是分布的**单调函数**且带**下界**：`声明值 ≥ p95`（向上取整）。
  2. **声明值 ≠ 当次实测 max**；必须给「声明值 / p95 / p99 / max」**四值对照表**。
  3. **至少两个候选值**（一个更严、一个更松）+ 三行对照「分布 → 声明值 → 降级率」；**降级率的可接受区间必须在测量前声明**（区间文本同样要有早于测量的时间戳）。
  4. **同一条件**：分布测量与降级率测量必须同并发、同网络、同冷热状态；不同则分列并标 **GAP**（不可比）。
  5. **声明值必须落在 `02_source` 的能力清单里**（不是只在报告散文里），并有脚本断言「清单里的值 == 报告里的值」（否则声明值可被 override 路径绕过，即 RM-14 的形态）。
- **不得把未标定的数带进 V0**；未标定 → GAP。
- 审计反例（正式审计轮会用）：① 比较规则文件 mtime 与分布日志 mtime（规则晚于分布 → 自证循环成立，FAIL）；② 用 `03` 里的分布数据独立重算 p95 与取整，核对是否等于盘上声明值；③ `grep -rn "timeout_ms" 02_source/*.json` 与报告声明值逐条比对。

#### 16.3.4 AC 表述改写范围

- 小队自有文档（`01` / `07` ADR-005 与相关条文 / `08` / `09` / `02_source` 契约描述）凡写「远端 API 为主 provider」「LLM 为主」处，一律改为「远端为**可降级的能力补充 provider**，默认路径允许降级」。
- REQ 属 PM 所有（只读）：若 REQ 仍有相反表述，**记录给 PM 修订**，不自行改，也不算 block（语义已由用户裁决，PM 已授权改写）。

#### 16.3.5 常驻门禁

- 新增 `spikes/tools/check_no_override_evidence.sh`：扫描证据性调用（spike 脚本 + 证据日志）中的 `--timeout-ms-override`，命中即非 0 退出；白名单只认显式合成负例标记。
- 门禁必须**自证**（内置 ≥3 条反例，命中即 exit 非 0），不得是「零命中绿命令」（沿用 G-1 的教训）。
- 与既有 `spikes/tools/gate_spike_scripts.sh` 一并保持绿。

### 16.4 五项落盘阻断项的关闭判据（`.pm_acceptance.md` §3）

#### 16.4.1 RM-1 / R2-1 · cassette 完整性措辞改写

- `02_source/cassette.format.md`：删掉/改写「哈希链 ⇒ 真实性保证」强度的表述，并新增**冻结条文**：哈希链**无密钥**，只能检出**损坏 / 篡改**，**不是真实性保证**；真实性需要**外部锚定**（快照链头签名）。
- `02_source/cassette.schema.json` 的 `hash` 字段描述**必须指回**该冻结条文（给条文编号）。
- 关闭判据：`grep` 证据（旧措辞 0 命中 + 新条文存在 + schema 指针存在）+ `jq .` 通过。
- 边界如实记录：V0 **无外部锚定实现**（记 GAP），不得写成已有。

#### 16.4.2 R2-4 / R2-5 · `03_artisan_self_test.log` 口径更正与修订登记

- **C10 行补更正说明**（不得删除原行，追加更正）：交付修订（mtime 18:39 / 18:47）当时**仍有 5 处形状命中、2 处 unbound variable 报错**；检测必须用**字节级计数**（`LC_ALL=C` 或 Python），**不能**用 UTF-8 locale 下的 `grep -c`（会假阴性）；并说明根因（macOS bash 3.2 + `set -u` + `$VAR` 紧跟非 ASCII）。
- **新增「修订登记」小节**：登记 19:05~19:08 的改动（时间 / 文件 / sha256 / 原因）与本轮全部改动；**若修复前的字节不可恢复，如实记 GAP 并给出可得的替代证据**（mtime + 守卫命中行号），不得编造 sha256。
- 关闭判据：更正说明 + 登记小节存在；`python3 <ws>/spikes/tools/check_bash_multibyte.py <ws>/spikes` exit 0（0 命中）；`LC_ALL=C grep -c 'unbound variable'` 对全部 console/summary 日志 = 0；日志为合法 UTF-8。

#### 16.4.3 ADR 编号冲突（**architect 裁决：重编号**；预审 Q3 收口后的可满足版本）

- 现状：AC-9 期望 `ADR-10 = 世界模型`、`ADR-11 = AIGC`；而 `ADR-010` 已被「记忆 / 自进化受控边界」占用。
- **裁决**：保留 REQ 字面 —— **`ADR-010` = 世界模型接入，`ADR-011` = AIGC 素材生产**；原 `ADR-010`（记忆 / 自进化）**重编号为 `ADR-012`**。
- **豁免清单（预审 Q3-1/Q3-2 收口，必写）**：`04_sentinel_test_report.md`、`05_raven_risk_report.md`、`_round2-bookkeeping/**`、`.pm_acceptance.md`、`.pm_notes.md`、`.task-*` 等**历史 / PM 冻结件不改写**。它们里的 `ADR-010` 属**历史锚定**，由 `07_adr.md` 的「编号规则与重编号记录」小节登记说明。判据因此**不得**写成「零残留」。
- **architect 自己改的部分**：`01_architecture_design.md` 中指向记忆 ADR 的引用由 architect 负责（不在 artisan 写集）；artisan 只需在清扫表里登记 architect 侧的处置结果。
- 要求（artisan 侧）：`07_adr.md` 新增「ADR 编号规则与重编号记录」小节 —— 旧→新映射 + 原因 + **全库引用清扫表**（`grep -rn "ADR-010\|ADR-011\|ADR-012" <ws>` 的**全量命中**，逐条给「改 / 豁免 + 理由」两列）+「8 个必答主题 → ADR 编号」映射表。
- 关闭判据：清扫表输出**落盘**（含 `grep` 命令原文，禁止只写「0 命中」）；**所有残留都在豁免清单内且逐条列出**；`01` / `02_source` / `06` / `07` / `08` / `09` 中指向记忆 ADR 的引用全部为 `ADR-012`；`07_adr.md` 条数 ≥ 12（**这是 architect 自设的更高门槛，不是 REQ AC-9 的判据**，须在文中注明）且 AC-9 的 8 个必答主题全部有归属。

#### 16.4.4 `event_chain_hash` 口径（**architect 裁决（预审 CRITICAL-1 修订版）：统一定义，改代码不改契约**）

- 现状：`simulate`（`kernel.py` L243）取「快照事件**之前**的链尾」，`fold`（L332）取「快照事件**自身**的 hash」→ 同一检查点字段差一个链环。
- **关键修正（预审 CRITICAL-1）**：契约文字**无需改** —— `02_source/snapshot.schema.json` 已冻结「`event_chain_hash` = **截至本快照 tick 的事件日志末条 hash**」，而快照事件的 `tick` 就等于该 tick ⇒「末条」**本就包含快照事件自身**。因此**偏离契约的是 `simulate` 侧代码**，不是契约。
- **裁决**：
  1. **唯一可行做法**：「**快照事件先追加 → 检查点后取链尾**」（即检查点字段 = 快照事件自身的 hash）。§16.4.4 原列的「先构造事件再取其 hash」**作废**：`snapshot.taken` 的 payload 必填含 `event_chain_hash`，若取事件自身 hash 即 `hash = f(hash)` 不动点，sha256 下不可解。
  2. **崩溃恢复语义（必写）**：事件先落盘、检查点后落盘 ⇒ 若在两者之间被 kill，恢复必须以「**锚点 hash 反查事件**」为准；反查失败即回退到上一检查点，**不得**接受悬空锚点。
  3. **同名两处必须分别写清语义**（这是本轮要消灭的歧义的最终形态，必须显式对照，不得靠 grep 名字判断）：
     - **检查点文件** 的 `event_chain_hash` = **快照事件自身的 hash**（= 该 tick 的链尾，含快照事件）→ 不变量 `INVARIANT-ECH-1`：`checkpoint.event_chain_hash == hash(snapshot.taken 事件, tick == checkpoint.tick)`（两条路径都必须成立）。
     - **事件 payload** 的 `event_chain_hash` = 该快照事件**之前**的链尾（= 该事件的 `prev_hash`）→ 不变量 `INVARIANT-ECH-2`：`event.payload.event_chain_hash == event.prev_hash`。
     - **禁止静默删字段**：若认为必须改 `events.schema.json` 的 payload 必填列表 → 走正式契约变更（ADR + 递增 `schema_version` + `manifest.txt` + `verify_specs.sh` 全绿）。本裁决**不删字段**。
  4. **`rng_state_digest` 必须是同一个函数（预审 残留 A，必写）**：`simulate` 用 `rng.state_digest()`、`fold` 用 `hash_object(payload["rng_digests"])` —— 当前 8/8 相同是**经验巧合**，不是不变量。契约必须写死「两条路径的 `rng_state_digest` 由同一函数产出」或「`payload.rng_digests` 是 `state_digest()` 的规范序列化」，并补一条断言。
  5. **链的拓扑必须写死（预审 残留 C）**：链是**全局单链**（同一 `seq` 序列）；若将来按 NPC 分片，则 `event_chain_hash` 为**分片相对量**并**禁止跨分片比对**。契约二选一写清。
  6. **比较器必须先修（预审 残留 B）**：`run ↔ replay` 三字段比对用的就是既有比较器，而它已知有两条假绿路径（round 2 RM-5：① 同一 tick 的第二个文件名遮蔽第一个；② 两侧都缺 / 都 null 判为一致）。必须先修这两条，或**显式证明不适用**（文件名固定 `{tick:06d}.json`、且断言 `event_chain_hash` 非 null）。
- **负例（真跑，命令 + exit + 日志）**：① `run ↔ replay` 三字段逐点比对必须一致（8/8）；② 只改一侧 `event_chain_hash` → 必须非 0；③ 检查点缺失 / 截断 → 必须非 0；④ **新增**：`event_chain_hash` 两侧置 null → 必须非 0（堵 RM-5 的「都 null 判绿」）。
- **关闭判据（正式审计轮会逐条核）**：
  1. `state_hash` 与 `rng_state_digest` 逐点**与 round 2 完全一致**（PM 已独立复现的末检查点 `state_hash=388a1a51833f04b0…` 不得变）；**只允许** `event_chain_hash` 变化。若为「一致」而动了前两个字段的语义 → **FAIL 并升 CRITICAL**。
  2. 正例证据必须附「**比较器非瞎子**」的自证（含 RM-5 两条路径），否则不采信。
  3. **修订登记**：重跑前先登记旧产物哈希 —— `simulate` 会 `unlink` 旧 `events.jsonl` 与旧检查点（L200-205），**旧 sha256 事后不可再算**；唯一幸存见证是 `.pm_notes.md` L21 记录的旧值 `06c9053a…` / `e57786e3…`（只读引用）。不可恢复的部分如实记 GAP。
  4. 作废**连带面**必须登记：`03` 中引用过 `event_chain_hash` 的 C 系证据行；`05` §7.x（round 2 只引 `state_hash`，不受影响，但要写明）；本裁决不删 payload 字段，故全链 hash 不作废（若最终删了字段，必须按「全链 hash 作废」重新登记）。

#### 16.4.5 R2-2 / R2-3 · 门禁自身缺陷（**预审 CRITICAL-2 修订版**）

- **R2-2 `run_s2.sh` hermetic 化**：退出码**只能**取决于被测代码，不得取决于远端模型是否够快；但**不得**因此让「远端腿整个死掉」也变绿。
  1. **证据分流断言（关键，必写）**：脚本必须输出并断言显式状态 `remote_call_status ∈ {real_call_ok, degraded}`；`degraded` 时**该次运行不得计入 AC-13 remote 类等价性证据**（单独判 **GAP** 并明示）；`degraded` **连续出现 ≥2 次 → 脚本非 0**。这把「静默降级」变成「可见的降级」。
  2. 远端腿断言改为「机制正确」（真调用 **或** 正确降级到 `deterministic_rule` 且降级可审计），两种结果都可 exit 0 —— **但必须同时满足第 1 条的显式状态输出**。
  3. **远端腿死亡负例**：stub 端点**拒绝连接**（不是慢）→ 期望：要么非 0，要么 exit 0 **且**输出 `remote_call_status=degraded` 并把等价性证据判 GAP。两者都没有 → 门禁不合格。
  4. **降级机制破坏负例**：不落 `capability.fallback` 事件 / 回退不写 `reason` → 必须非 0。
  5. **stub 健康前置断言**：stub 未起来 / 返回 500 时，**不得**被读成「被测代码降级正确」→ 必须非 0。
  6. **pinned fixture 完整性**：篡改负例改用固定样本（`spikes/s2-capability-cassette/fixtures/pinned/`），必须**登记 sha256 并在运行时校验**（否则 fixture 被改后篡改负例恒绿）。
  7. 「连续 ≥3 次 exit 0」**只证明稳定性、不证明检出能力**，不得单独作为关闭依据。
- **R2-3 `verify_specs` 排除生成残渣**：`find` 覆盖检查排除 `__pycache__` / `.pytest_cache`；**排除规则必须精确**（逐条列明排除的路径模式，禁止 `-not -path '*/kernel/*'` 这类过宽写法）；清理交付树内残渣（`02_source/**/__pycache__`）；跑 pytest 一律 `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`。
  - **自证负例（两条，必跑）**：① 删掉 / 改名 `manifest.txt` 里一条**真实登记项**对应的文件 → 必须红；② 在**非生成目录**放一个真实未登记文件 → 必须红（证明排除规则没把它一起放过）。

### 16.5 本轮验证计划（三层门禁）

- **Artisan 自测面**（→ `03_artisan_self_test.log` 新增「round 3」小节）：AC-14 / AC-15 / D-0.9 逐条 `PASS|FAIL|GAP + 命令 + workdir + exit + 日志绝对路径`；5 项阻断项逐条关闭证据；全部 JSON `jq .` 通过；`verify_specs.sh` / `run_s1.sh` / `run_s2.sh` / `gate_spike_scripts.sh` / `check_no_override_evidence.sh` 全绿；新增文件必须登记进 `02_source/manifest.txt`（3 字段格式）。
- **Sentinel 面**（→ `04` 追加 round 3 节）：独立复现 5 项阻断项的关闭；独立核验 AC-14 / AC-15 / D-0.9 的**契约完整性**（字段、条文、判据是否真在盘上）；核验「无 override 取证」是否真成立；核验新矩阵行的许可事实（对上游二次核对）；边界与负例（schema 拒收、非白名单许可、跨 tick 回填禁止）。
- **Raven 面**（→ `05` 追加 round 3 节）：对抗 AC-14 的「不权威」是否真成立（尝试构造世界模型 → 世界状态的写入路径）；对抗 AIGC 许可白名单的可绕过性；对抗 D-0.9 的「声明值可被 override 绕过 / 标定自证循环」；`event_chain_hash` 统一后是否引入新的跨路径不一致；V1 门禁判据的可玩性（能否被伪造通过）。

### 16.6 本轮风险自评（architect）

| # | 风险 | 触发条件 | 影响 | 分级 | 处置 |
|---|---|---|---|---|---|
| A3-1 | ADR 重编号遗漏引用 | 清扫不彻底 | 文档自相矛盾（AC-9 一致性受损） | MEDIUM | 全库 grep + 逐条确认表 |
| A3-2 | `event_chain_hash` 统一后旧哈希作废 | 重跑 S1 | 旧证据不可复现（需登记） | MEDIUM | 修订登记小节 + 新哈希落盘 |
| A3-3 | 声明值「按实测重标」被做成「按绿灯重标」 | 取值规则不写清 | 自证循环（D-0.9 失效） | **HIGH→MEDIUM** | 必须写推导规则 + 给敏感性对照 |
| A3-4 | 世界模型 / AIGC 集成被提前扩权 | 执行方自行加实现 | 范围失控、权威链风险 | **CRITICAL（若发生）** | 本轮写死 V0 边界；越界即上抛 |
| A3-5 | 素材生成 spike 未真跑却写 PASS | 无实测却宣称 | 证据造假 | **CRITICAL（若发生）** | 未跑一律 GAP；CUDA-only 禁止宣称 |
| A3-6 | 门禁 hermetic 改造削弱检出能力 | 为求绿放宽断言 | 门禁失效 | **HIGH→MEDIUM** | 每条改造必须带自证负例 |

### 16.7 本轮写集（与 §13 一致）

- 可写：`<ws>/02_source/**`（新增 `worldmodel.adapter.spec.md` / `asset.manifest.schema.json` / `art-bible.md` / `content-pipeline.spec.md` + 既有契约修订 + `manifest.txt` 同步）、`<ws>/spikes/**`（s1/s2 修复、新增标定与门禁脚本）、`<ws>/03_artisan_self_test.log`、`<ws>/06_open_source_matrix.md`、`<ws>/07_adr.md`、`<ws>/08_v0_plan.md`、`<ws>/09_risks_open_questions.md`、各角色 `.progress.json`、角色账本。
- 只读：真实仓库 `/Users/wooyinq/personal/deep-healing`（含任何 git 写操作）、`pm_business/**`、`<ws>/.pm_acceptance.md`、`<ws>/.pm_notes.md`、`<ws>/01_architecture_design.md`（Architect 所有，Artisan 只读）、`<ws>/04_*`、`<ws>/05_*`（reviewer 所有）、其他 profile。

### 16.8 方案预审回执处置（Raven `.raven_prereview_r3.md`，CRITICAL 2 / MEDIUM 5 / LOW 0）

**处置原则**：两条 CRITICAL 均由 **architect 修订裁决文字**关闭（本节即修订记录），**不需要 artisan 写代码**；五条 MEDIUM 的关闭判据已折入对应小节，随本轮实现，不阻断开工。

| 预审条目 | 分级 | architect 处置 | 落点 |
|---|---|---|---|
| CRITICAL-1 · `event_chain_hash` 统一定义与冻结 `events.schema.json` 冲突（两条路都成「表面关闭」） | CRITICAL → **已关闭（裁决修订）** | 采纳「契约文字无需改，偏离契约的是 `simulate` 代码」；作废「先构造事件再取 hash」选项；写死顺序 + 崩溃恢复语义；同名两处分别写清语义（`INVARIANT-ECH-1/2`）；补 `rng_state_digest` 同函数、链拓扑、比较器先修三条残留 | §16.4.4（已重写） |
| CRITICAL-2 · R2-2 hermetic 后远端腿死掉仍 exit 0（阻断项假关闭） | CRITICAL → **已关闭（裁决修订）** | 新增「证据分流断言」`remote_call_status`（`degraded` 不计入 AC-13 remote 等价性证据、连续 ≥2 次即非 0）+ 远端腿死亡负例 + stub 健康前置 + pinned fixture sha256 校验；「连续 3 次 exit 0」不得单独作为关闭依据 | §16.4.5（已重写） |
| Q1 · AC-14「不权威」4 条绕行面 | MEDIUM → 已折入 | 补「直接 / 间接」限定语；provider 类别绑定世界模型后端（default-deny + 负例）；非确定性 provider 输出禁止入规则层 + 校验期必跑一致性检查；离线管线校验必须有执行体；tick 与耗时解耦；呈现层按**已声明边界**登记 | §16.1.1 / §16.2.7 |
| Q2 · D-0.9 标定自证循环 | MEDIUM → 已折入 | 防自证五条（规则先冻结 + 单调下界 `≥p95`；声明值 ≠ max；两候选 + 事先声明可接受区间；同条件测量；清单值与报告值脚本断言一致） | §16.3.3 |
| Q3 · ADR 重编号与只读件冲突 | MEDIUM → 已折入 | 增加**豁免清单**（`04`/`05`/`_round2-bookkeeping`/`.pm_*`/`.task-*` 不改写，登记为历史锚定）；判据从「零残留」改为「残留全在豁免清单内」；`01` 侧由 architect 自改；≥12 条注明为自设门槛 | §16.4.3 |
| Q6 · AIGC 白名单可绕过 5 面 | MEDIUM → 已折入 | `license`↔`source_model` 数据表绑定 + default-deny；衍生资产 `derived_from` 传递闭包；云产出 `provenance: self_reported` 登记为已声明边界；ComfyUI 工作流受管登记；生成器元数据剥离 + `content_hash` 口径写清 | §16.2.6 / §16.2.7 |
| Q7 · 五项阻断项「表面满足」 | MEDIUM → 已折入 | 逐条反例写入 §16.4 各小节；并新增本节「**冻结快照**」要求 | §16.4.1~§16.4.5 + 本节 |

**冻结快照（跨条表面满足收口，硬性；**预审回执 RR3-1 修订版**）**：round 3 交付时必须提供
① 本轮改动 / 新增文件的**清单 + 逐文件 sha256 + 采集时间**；② `03_artisan_self_test.log` 的 round 3 小节登记本轮**全部**改动。

- **冻结面（明确定义）**：**契约 / 源码 / 文档面** —— `01_architecture_design.md` + `02_source/**` + `03_artisan_self_test.log` + `03_spike_log.md` + `06`~`09`。**不含门禁运行产物**（`spikes/**/logs/**`、`spikes/**/cassettes/**`、各 spike 工作目录）—— 这些是可复跑的派生物，不是交付证据本体。
- **清单形式**：必须是**显式文件清单**（不得用 `--since` / mtime 窗口推导），逐文件 sha256。
- **复跑隔离（关键）**：所有 spike / 门禁脚本必须支持**隔离输出**（`--out <dir>` 或 `DEEPHEALING_SPIKE_OUT` 环境变量），审阅方（Sentinel / Raven / PM）复跑**一律写隔离目录**，**不得覆盖交付证据**。冻结快照只提供「事后发现漂移」，防漂移靠这条隔离机制。
- **判回规则**：若发现交付证据被**非隔离**复跑覆盖，相关项按「证据不可复现」**判回未关闭**（round 2 的 RM-8 / R2-5 教训）。

### 16.9 本轮风险登记增补（承接 §16.6）

| # | 风险 | 触发条件 | 影响 | 分级 | 处置 |
|---|---|---|---|---|---|
| A3-7 | 阻断项被「表面满足」关闭 | 只加条文不删旧措辞 / 指针悬空 / 排除规则过宽 / 登记表 sha256 与盘上不符 | 落盘条件被假关闭 | **HIGH→MEDIUM** | §16.4 逐条反例 + 冻结快照 + reviewer 独立复现 |
| A3-8 | 标定值「按绿灯选」 | 推导规则事后挑 | D-0.9 失效、超时风险被掩盖 | **HIGH→MEDIUM** | §16.3.3 防自证五条 + mtime 时序核查 |
| A3-9 | 门禁 hermetic 化后失去「远端路径死掉」的检出能力 | 只断言「机制正确」 | AC-13 remote 证据静默消失 | **CRITICAL（已由 §16.4.5 修订关闭）** | 证据分流断言 + 死亡负例 + stub 健康前置 |

### 16.10 round 3 审计回执处置与修复迭代 1/3 裁决（`04` §10 + `05` §8）

- 回执计数：**Sentinel** CRITICAL 0 / MEDIUM 4 / LOW 5；**Raven** CRITICAL 2 / MEDIUM 16 / LOW 5（Raven 独立复现确认**预审 CRITICAL-1 已关闭**：`run↔replay` 8/8、`state_hash` 逐点未变）。
- 裁决：**两条 CRITICAL 均须在预算内修完**（不降级为已声明边界），派 artisan 修复迭代 **1 / max_iteration=3**；修复后由 Sentinel（定向复验）与 Raven（hotspot）复跑。

| 项 | 分级 | architect 裁决 | 关闭判据 |
|---|---|---|---|
| **RR3-1** 冻结快照被并行复跑改写，且要求机制上不可满足 | CRITICAL | **采纳 (a)：复跑隔离**。冻结面收敛为「契约 / 源码 / 文档面」（见 §16.8 修订版）；`run_s1.sh` / `run_s2.sh` 等写证据的脚本必须支持 `--out <dir>`（或 `DEEPHEALING_SPIKE_OUT`）；审阅方复跑一律写隔离目录；快照清单改为**显式文件清单**并纳入 `01` | 隔离模式真跑（复跑写隔离目录时冻结面 0 漂移）；快照含 `01` 且逐文件 sha256 可复算 |
| **RR3-2** 确定性闸门无执行体（`x-determinism-gate` 只读声明字段） | CRITICAL | **采纳「实现真执行体 + fail-closed」**：`determinism: deterministic` **只允许** `deterministic_rule`（真执行 ≥3 次比对输出摘要）与 `cassette_replay`（固定 cassette 回放 ≥3 次比对）；`remote_api` / `local_model` 声明 `deterministic` → **校验期拒收** | 负例真跑：带采样参数却声明 `deterministic` → 非 0；`remote_api` 声明 `deterministic` → 非 0；`required/runs` 声明字段不再作为唯一判据 |
| **RR3-3** provider 类别绑定 default-deny 名不副实 | MEDIUM | 判据改为**不可自声明的锚**：`slot ∈ imagine.*` 的能力，其**所有** provider 的 `class` 必须为 `remote_api`；`source_model` 用前缀 / 正则匹配；`source_model` **缺失即视为命中**（fail-closed） | 负例：换名（`nvidia/Cosmos-…`）/ 留空字段 / 声明 `local_model` → 全部非 0 |
| **RR3-4** 标定断言自引用（p95/max 与 timeout 同文件） | MEDIUM | 校验器必须读**冻结的分布日志**（`spikes/s5-latency-calibration/logs/latency.distribution.json`）**独立重算** p95 再与 `timeout_ms` 比较；`calibration.json` 登记 sha256 并写进契约 | 负例：把清单里 `p95_ms` 改成 1.0 而分布日志不变 → 必须非 0 |
| **RR3-5** 敏感性对照无区分度 + 降级率口径滤掉实际降级 | MEDIUM | ① `03` R7a 判定列改写为「超时口径在区间内；**任一叶降级率 1.00**」；② 若要把 `any_fallback_rate` 纳入区间，必须**重新事先声明**区间（时间戳早于重测）后再测，否则记 GAP | 判定列文本 + 区间声明 mtime 时序证据 |
| **RR3-6** 远端 `memory.reflect` 输出 schema 非法 → AC-13 remote 面 GAP | MEDIUM | **不得**为了变绿去改契约去迁就远端输出（那是弱化判据）；保持 **GAP**，在 `09` 登记为 V0 待办（结构化输出对齐 / 重试 / 提示词约束） | `09` 有条目；AC-13 remote 面继续记 GAP |
| **RR3-7 / Sentinel MEDIUM-2** `run_s2.sh` 绿态不可复现（跨运行历史窗口） | MEDIUM | exit 判据改为「**同一次运行内可判定**的属性」（本次是否 `degraded` + 是否落显式 GAP 记录）；跨运行历史降级为**报告项**；同一次运行内做 ≥3 次重复稳定性断言 | 连续 ≥3 次 exit 一致（同一代码同一条件）；自证负例仍红 |
| **Sentinel MEDIUM-3** 门禁对「`capability.fallback` 缺 `reason`」无红能力 | MEDIUM | 第 14 步加断言：每条 `capability.fallback` 的 `reason` **非空**（与 `events.schema.json` 的 `required` 一致），并做成自证反例 | 删 `reason` → 必须非 0 |
| **Sentinel MEDIUM-1** `03` R10b 表 6 行 sha256 不可复现（含路径/哈希错配） | MEDIUM | 按盘上重算回填，或改引 `round3-freeze.sha256`（对同一批文件可复现） | 逐行 sha256 == 所声明路径的盘上值 |
| **Sentinel MEDIUM-4** `03` L102 仍写 `ADR-010`（指记忆条） | MEDIUM | 改为 `ADR-012`；修正 `07` 清扫表第 3 行「与盘上不符」的声明；按 `grep -c` 重算清扫表计数（LOW-2） | `03` 中指向记忆 ADR 的引用为 `ADR-012`；清扫表声明与盘上一致 |
| **RR3-13（RM-13）** `verify_pack.py` 仍只按后缀名拦 | MEDIUM | 管线规范必须指定 `verify_asset_pack.py` 为**权威校验器**；`verify_pack.py` 要么补齐 4 类拒收，要么**就地标注弃用**并移除规范中的引用 | 规范指向权威校验器 + 弃用/修复证据 |
| **RR3-22** V1 门禁 G1~G5 可伪造通过 | MEDIUM | §16.1.6 已补**反伪造要求**表；ADR-010 必须逐条写入 | ADR-010 含反伪造要求 |
| Sentinel LOW-1 / LOW-3 / LOW-4 / LOW-5、Raven 其余 LOW | LOW | 低成本项随修（快照含 `01`；端点健康断言文案降级为「端点可达」；`08`/`03` 注明 pytest 为骨架收集性检查；override 门禁扩展到 `*.py` 调用行） | 逐条证据或记 GAP |

> 未闭合项（素材生成 spike / 本机世界模型不可跑 / 成本与 G4 阈值 / 内存与端到端延迟 / 远端 schema 对齐）**全部记 GAP 或 non_block_issues**，不冒充 PASS。

### 16.11 门禁执行体的边界声明（architect，承接 `05 §10.5` 与 `02_source/capability.time-budget.spec.md` §7）

1. **`verified_impl` 的确切语义**：修复迭代 3 后，确定性探针在**同一个子进程内**执行 `runs` 次调用并比对输出摘要 ⇒ `verified_impl` = 「**同进程内同输入同输出**」（覆盖模块级计数器 / 缓存 / 单例这类进程内状态）。**不再**是「跨进程冷启动幂等」。
2. **门禁以「运行者环境」跑 provider**：子进程继承运行者环境变量，manifest **无法**写环境。⇒ 契约要求：**provider 不得读取凭据环境变量**（`requires_secrets` 只声明变量名，不读取值）；这是**已声明边界**。
3. **门禁不是文件系统沙箱**：挡住「任意路径写入」的是 **impl 白名单 + kernel 根锚定**，**不是** `rlimit`（`RLIMIT_FSIZE` 只限单文件大小 1 MiB，不限路径与文件个数；macOS 上 `RLIMIT_AS` 不可设）。⇒ 已声明边界，不得写成「沙箱隔离」。
4. **父进程侧没有 rlimit**：防护是「固定上界 + 节点预算（拒绝展开病态 schema）」，**不是资源隔离**；上界内的超大派生实例仍可放大内存。⇒ 已声明边界（触发条件见 `capability.time-budget.spec.md` §7）。
5. **provider 数量未设上界**：一个 manifest 声明 N 个 provider ⇒ N 次 spawn（有硬超时，故**有界**放大，非无限挂起）。**是否给 provider 数量设上限属产品 / 业务决策 → 待 PM 裁决**（见汇总 `block_issues`）。

### 16.13 architect 侧修订登记（与 §16.12 的收口裁决一并生效，承接 Sentinel `04 §13` 的「快照 drift」与 PM 阻断项 17 的口径）

| 时间（CST） | 文件 | 变更 | 原因 |
|---|---|---|---|
| 19:39 | `01_architecture_design.md` | 新增 §16 rev3 增补（AC-14 / AC-15 / D-0.9 / 5 阻断项） | PM 有界补轮任务书（`.squad_payload.json`） |
| 20:2x | `01_architecture_design.md` | §16.1.1 / §16.1.6 / §16.2.6 / §16.2.7 / §16.3.3 / §16.4.3~16.4.5 / §16.8 / §16.10 修订 | 预审回执 CRITICAL 2 / MEDIUM 5 的裁决修订 + 审计回执（`04 §10` / `05 §8`）裁决 |
| 23:10 | `01_architecture_design.md` | 新增 §16.11（门禁执行体边界声明） | 承接 `05 §10.5` R3F2-3 / R3F2-5 要求「未加固面必须显式声明」 |

- **与冻结快照的关系**：`spikes/logs/round3-freeze.sha256` 于 23:09:42 采集；01 于 23:10:59 被本表登记的 §16.11 增补 ⇒ 触发 Sentinel 复验的 `drift=1`。**处置**：architect 按 `01 §16.8` 的规则**重取快照**并复算 drift=0（新快照的 01 sha256 见快照文件与本轮汇总）。
- **登记口径说明（诚实边界）**：`03_artisan_self_test.log`（Artisan 所有）的修订登记**不包含**本次 architect 侧改动 —— 本表即为该改动的登记落点，第三方以「本表 + 快照文件」复现 01 的版本。此为**已知口径缺口**，列入汇总 `non_block_issues`。

### 16.12 round 3 修复迭代 3 裁决与收口（architect，承接 `05 §11` + `04 §13`）

**裁决依据**：两份门禁报告**均由第三方独立复跑**（不采信 artisan 自述），且我（architect）在派发前用自己的
`spikes/architect-review/fix3/repro_all.py` 独立复现过两条原始发现（见该目录 `FINDINGS.md`）。

| 项 | 级别 | 裁决 | 依据 |
|---|---|---|---|
| R3F2-1 父进程 fixture 派生计算可被纯数据打崩 / 内存放大 | CRITICAL | **关闭** | `05 §11.1`（四条判据逐条成立 + 我精化的 L503 `check_schema` 点单独验为不可达 + 无判据弱化）；`04 §13.2` 自造 8 条病态 schema 全 exit 1 无 traceback、内存放大消失、正例仍绿 |
| R3F2-2 `per_run` 冷启动静默收窄确定性判据 ⇒ 有状态实现假绿 | MEDIUM | **关闭** | `05 §11.2` 六条实测 + 语义已钉死在 `02_source/capability.time-budget.spec.md §7.2` / 本文件 §16.11.1 / 工具头三处；`04 §13.3` 三条有状态夹具全非 0、`allowed_in_rule_layer` fail-closed 5/5 |
| N-1 执行期逃逸（上一轮已关） | CRITICAL | **未重开** | `05 §11.3` 矩阵 11 + 21 条全红、硬超时仍 ~2s |
| G2 / G3（determinism 必填 + 门禁真跑 schema 校验） | — | **不回归** | `04 §13.3`；`verify_specs.sh` `PASS=95 FAIL=0 SKIP=0` |
| **R3F3-1** 内嵌 `output_schema` 的**悬挂 / 成环 `$ref`**（或 provider 返回超深输出）⇒ 父进程内部崩溃被**逐能力兜底**压成不透明的 `B5_CHECK_CRASH_GUARDED`，该能力文件的 `exec` 记录全丢 | **MEDIUM（携带）** | **不阻断，显式携带** | `05 §11.6 R3F3-1`（真跑：exit 1 / 无 traceback / RSS 与基线同量级 / 交付 5 能力零影响）；`04 §13.5 LOW-13` 为**同族同点**，按「分级冲突取高」并入本条 MEDIUM |
| `04` MEDIUM-6 冻结快照 drift=1（`01` 在采集后被写） | MEDIUM | **关闭（已处置）** | 归因明确 = 我在 `23:10:59` 落 §16.11（raven 关闭判据要求的那段），**非** artisan 漏取、**非** RR3-1 回退；已按本文件 §16.12 末尾登记**重取快照**（理由 + 变更清单 + 前后哈希） |
| `04` MEDIUM-7 `fix2_regression.sh` 唯一失配 `g5_sweep_counts`（`07` 清扫表第 11 行 12 vs 盘上 18） | MEDIUM | **裁决：口径缺陷，下一轮收口；当前不得宣称「17 项全 0」** | 根因 = 该 gate 拿 `07` 里**带时刻的快照值**与**活盘**逐字比对 ⇒ 任何 reviewer 追加正文都会让它转红。**采纳 `04 §13.5` 建议②**（把 reviewer 件 `04`/`05`/`.pm_*`/`.raven_*` 移出计数表、只登记文件名），下一轮首项实施 |
| R3F3-2 fixture 回退的 `input_output_stable` 是同对象重复 digest | LOW | 携带（记账） | `05 §11.6`：该路径只产出 `verified_fixture` + 显式 GAP，不冒充 `verified_impl` |
| R3F3-3 / R3F3-4 / R3F3-5（快照记账 / before-fix2 基线被覆盖 / `enum` 元素数不计节点） | LOW | 携带（记账） | `05 §11.6`；R3F3-4 的 `spikes/**` **不在**冻结面 |
| LOW-8（`run_s3.sh` / `run_s6.sh` 不支持 `--out`）、LOW-14（docstring 锚点 `§H3`） | LOW | 携带 | `04 §13.5`、`05 §11.6` |

**本轮预算**：`max_iteration=3` 已用满（修复迭代 1 / 2 / 3）。**CRITICAL = 0**（R3F2-1 已关闭、N-1 未重开）
⇒ **不触发 `exceed_iteration_human_intervene`**；R3F3-1 为结构化 fail-closed 的纵深缺口（无绕过、无假绿、
无内存放大、交付清单零影响），按 MEDIUM 携带，**不得**被读成「已关闭」。

**冻结快照重取登记（预期漂移的处置，不是掩盖）**：

- 重取理由：`01` 在本轮快照采集（`23:09:42`）之后被写两次 —— ① `23:10:59` 落 §16.11（raven 关闭判据
  「把判据语义收窄写进 `01`」的要求，属**必须写**）；② 本次落 §16.12（裁决收口）。
- 变更文件清单（相对上一版快照）：**仅 `01_architecture_design.md` 一个**；`02_source/**`、`03*`、`06`~`09`
  逐字节未变（`05 §11.5` 已核对：`02_source` 变更恰好 5 个文件，与 artisan 自述逐一对应，无未声明写入）。
- 前后哈希：`01` `7ac3ba9e05721faf…`（旧快照记录值）→ `64d54fbcbf9711eb…`（§16.11 后）→ 本次写入后的值见新快照。
- 采集顺序教训（写进下一轮开工清单）：**先定稿 `01`，再采集冻结快照**；否则「`--verify` drift=0」在
  多人追加的工作区里结构性不可达成。
