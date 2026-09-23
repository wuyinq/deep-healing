# 06 · 开源选型矩阵（逐层）

- 计划：`REQ-20260921-002-deephealing-architecture-freeze`　作者：artisan　日期：2026-09-21
- 原则：**adopt-first**（不造轮子）；自研仅限开源无法覆盖的差异化内核，且必须写明理由
- 事实来源（全部可复核，非记忆）：
  - `spikes/facts-license/facts.summary.txt` + `facts.summary.tsv` + `out/*-latest.json` + `out/pypi-*.json` + `out/github-*.json`（npm registry / PyPI / GitHub API 原始响应，命令 `bash spikes/facts-license/probe_facts.sh`，exit 0）
  - `/tmp/dh-research/oss-landscape.json`、`oss-landscape-2.json`（上游事实，部分仓库 license 抓取失败返回 `NONE`）
  - `spikes/s1..s4` 的真跑日志（`03_spike_log.md`）
- 工具链事实（计入成本）：Rust **未装**（无 cargo/rustup）、pnpm/yarn **未装**、**无 NVIDIA GPU**、Docker 29.7.2 可用、Playwright 缓存 `chromium-1234`（与 `playwright@1.63` 期望的 1243 不匹配，回退系统 Chrome）、node v26.3.1 / npm 11.16.0 / bun 1.3.14 / Python 3.13.13 + uv 0.12.1

## 许可判定口径（本表统一）

| 判定 | 含义 |
|---|---|
| **可进运行时 / 可商用** | MIT / Apache-2.0 / BSD-3-Clause / ISC / MPL-2.0（MPL 限文件级传染，允许链接使用） |
| **仅离线管线** | GPL-3.0 及更强 copyleft：只允许在离线美术/数据加工阶段使用，**产物不得进入运行时与交付物** |
| **待核** | 自定义/未声明许可（NOASSERTION / NONE）：未取得书面确认前**不得进运行时**，也不得作为 V0 依赖 |
| **不可用** | 无许可或明确限制商用 |

---

## L1 · 渲染引擎

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本（实测/评估） | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **three.js** | github.com/mrdoob/three.js · npm `three` | **MIT**（npm registry 实查） | 0.186.0 | 2026-09 高频 | **低**：S3 真跑 `vite build` exit 0，dist 478 kB / gzip 121 kB，tsc 全绿；场景断言 11 项全通过；WebGL2 真渲染截图成功 | **adopt（V0 主选）** | 事实标准、生态最大、文档与示例最全；MIT → **可进运行时、可商用** ✅ |
| **@react-three/fiber** | github.com/pmndrs/react-three-fiber · npm `@react-three/fiber` | **MIT**（npm 实查；上游 JSON 抓取失败返回 NONE） | 9.7.0 | 2026-09-20 | **中**：需引入 React + 组件化重写渲染层，与「渲染层零业务逻辑」不冲突但会改变 UI 技术栈；纸面对照，未真跑 | **adapt（V1 选项）** | 声明式组件化利于 HUD/双模式 UI；但 V0 规模（单栋楼 5 NPC）不值得引入 React 运行时。MIT → 可进运行时、可商用 ✅ |
| **@babylonjs/core** | github.com/BabylonJS/Babylon.js · npm `@babylonjs/core` | **Apache-2.0**（npm 实查） | 9.27.1 | 2026-09 高频 | **中高**：自带物理/导航/材质体系，但 bundle 更大、与 three 生态不通用；纸面对照，未真跑 | **reject（V0）** | 功能更全但更重；无 GPU/无 3D 美术量产的本轮不需要其强项。Apache-2.0 → 可进运行时、可商用 ✅ |
| playcanvas | github.com/playcanvas/engine · npm `playcanvas` | **MIT**（npm 实查） | 2.22.3 | 2026-09-21 | 中：引擎 + 自有编辑器体系，运行时集成尚可 | reject | 生态小于 three；编辑器绑定对「数据驱动内容包」无额外价值。MIT → 可商用 ✅ |
| Godot（导出 Web） | godotengine/godot | 上游 JSON 抓取失败（`no json`）→ **MIT 待二次核对** | — | — | **高**：需完整引擎工程与导出管线，与「浏览器端轻渲染 + 内核权威」架构冲突 | reject | 架构不匹配（引擎即运行时权威）；且需另建工程。许可为 MIT（社区共识，**本轮未取得权威响应，标记待核**） |

**该层裁决**：adopt `three.js`；R3F 保留 V1 组件化选项；Babylon/Godot/playcanvas reject（V0）。

## L2 · 世界内核 ECS / 语言

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本 | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **自研薄确定性内核（Python 3.13）** | 本轮 `spikes/s1-determinism/`（真跑） | 自有 | — | — | **低-中**：S1 真跑，纯 stdlib 完成 tick/RNG 分流/事件哈希链/快照/重放；无额外依赖 | **adopt（V0）** | 确定性 tick + 回放哈希是本项目**差异化内核**，开源 ECS 的调度模型与之不匹配；Python 与 L4/L6（认知/记忆）同语言，省一次跨进程边界 |
| **mesa** | github.com/projectmesa/mesa · PyPI `mesa` | **Apache-2.0**（PyPI classifier 实查） | 3.5.1 | 活跃 | **中**：Agent 调度模型面向 ABM 研究，非固定 dt 游戏 tick；要接进确定性 tick 需绕开其调度器 | **adapt（参考，不集成）** | 借其「agent 生命周期 / 数据收集器」概念；直接集成会把非确定性调度带进内核。Apache-2.0 → 可商用 ✅ |
| bitECS | github.com/NateTheGreatt/bitECS · npm `bitecs` | **MPL-2.0**（npm 实查；上游 JSON 同） | 0.4.0 | 2026-08 | 中高：TS 侧 ECS，需把内核放 Node/浏览器 | reject | 会把权威推到 Node 侧（与 L3 会话层冲突）。MPL-2.0 文件级 copyleft → 可链接使用、可商用 ⚠️（需保留其文件许可声明） |
| hecs / bevy_ecs | github.com/Ralith/hecs | **Apache-2.0**（上游 JSON 实查） | — | 2026-09-08 | **高**：**本机 Rust 未装**（无 cargo/rustup），需先补工具链 + 跨语言边界（PyO3 或 FFI） | reject（V0）/ V1 评估 | 性能路线候选，但 V0 规模（5 NPC、10 Hz）不需要；R8 已登记。Apache-2.0 → 可商用 ✅ |

**该层裁决**：V0 自研 Python 薄内核；mesa 作范式参考；Rust ECS 在 V1 前做性能 spike 再定。

## L3 · 物理 / 导航

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本 | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **自建路点图导航（数据驱动）** | 本轮 `02_source/v0_skeleton/districts/.../buildings/*.json` 的 `nav_nodes` | 自有 | — | — | **低**：纯数据 + 图搜索；单栋楼 11 个路点已落盘 | **adopt（V0）** | 垂直切片（1 栋楼）不需要刚体物理；路点图即可支撑日程移动与「到达」判定 |
| recast-navigation（JS/WASM） | github.com/isaac-mason/recast-navigation-js · **npm `recast-navigation`** | **MIT**（npm 实查） | 0.43.1 | 2026-07-06 | 中：WASM 体积 + 需从网格烘 navmesh | **adapt（V1）** | V1 多楼栋/多街区时启用；MIT → 可进运行时、可商用 ✅。**包名注意**：真实可安装的包名是 `recast-navigation`（0.43.1，MIT）；`recast-navigation-js` 在 npm 上 **404 不存在**，不得作为依赖名（仓库名 ≠ 包名） |
| rapier | github.com/dimforge/rapier | **Apache-2.0**（上游 JSON 实查） | — | 2026-09-20 | **高**：Rust 侧（需装工具链）或 JS/WASM 版本；V0 无刚体需求 | reject（V0）/ V1 评估 | 物理不是治愈向玩法的核心；引入会显著增加确定性风险（浮点 + 求解器迭代顺序）。Apache-2.0 → 可商用 ✅ |
| yuka | github.com/Mugen87/yuka | **MIT**（npm 实查） | 0.7.8 | 2026-09-05 | 低-中：纯 JS 游戏 AI（转向/寻路/模糊逻辑） | adapt（参考） | 其「转向行为 + 目标驱动」与 NPC 移动可互补；V0 先自建最简。MIT → 可商用 ✅ |

**该层裁决**：V0 自建最简路点导航；V1 在 recast-navigation 与 yuka 之间按「是否需要 navmesh」定。

## L4 · 会话 / 权威服务器

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本（**实测**） | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **自研最小权威 WS 传输（Node，非权威）** | 本轮 `02_source/v0_skeleton/session/`（接口已冻结） | 自有 | — | — | **低**：只用 `ws`（**MIT**，8.21.3）；无状态搬运，权威留在 Python 内核 | **adopt（V0）** | 唯一能保证「单一权威」（内核）的方案；L2 只做鉴权/搬运/权限，双权威风险 R7 从结构上消失 |
| **colyseus** | github.com/colyseus/colyseus · npm `colyseus` | **MIT**（npm 实查） | 0.18.6 | 活跃 | **中高（S4 真跑）**：143 个依赖目录 / 196 MB / 首次安装约 3 分钟；`@type` 装饰器需 TS/babel 构建步骤；`defineTypes` 已 deprecated；客户端必须 `@colyseus/sdk@0.18.2`（旧 `colyseus.js@0.16` 协议不兼容）；`Room` 需从 `@colyseus/core` 导入；`@colyseus/schema` 版本强耦合（`^5.0.8`） | **adapt（V1 评估）** | 能力（房间/状态同步/重连）成熟，但**它假定权威在 Node 侧**；采用即意味着把内核搬到 Node 或加跨进程权威桥 → 正是 R7 的入口。MIT → 可商用 ✅ |
| nakama | github.com/heroiclabs/nakama | **Apache-2.0**（上游 JSON 实查） | — | 2026-09-07 | 高：Go 服务 + 需 Docker 部署 + 自有 match handler 运行时 | reject（V0） | 面向生产级社交后端（账号/排行/匹配），本轮不需要；引入即引入部署面。Apache-2.0 → 可商用 ✅ |
| networked-aframe | github.com/networked-aframe/networked-aframe | **MIT**（上游 JSON 实查） | — | 2026-09-10 | 中：A-Frame 生态绑定 | reject | 与 three.js 直控路线重复且约束更大。MIT → 可商用 ✅ |

**该层裁决**：V0 自研最小 WS 传输（`ws` MIT）；V1 若需房间/重连/匹配能力再评估 colyseus，且必须先解决权威归属。

## L5 · 认知编排（行为树 / 效用）

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本 | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **py_trees + 自研效用打分** | github.com/splintered-reality/py_trees · PyPI `py_trees` | **BSD-3-Clause**（PyPI 实查） | 2.6.0 | 2026-09-17 | **低**：纯 Python，与内核同语言；叶子只声明槽位（`call_capability`） | **adopt（V0）** | 行为树负责「何时调用哪个能力」，效用负责「候选打分」；两者都在规则层，模型调用被赶到 provider 层（契约级禁令） |
| BehaviorTree.CPP | github.com/BehaviorTree/BehaviorTree.CPP | **MIT**（上游 JSON 实查） | — | 2026-09-20 | 高：C++ 侧 + 需绑回 Python 内核 | reject（V0） | 性能非本轮瓶颈。MIT → 可商用 ✅ |
| **behaviac** | github.com/Tencent/behaviac | **NOASSERTION（自定义）** — 上游 JSON 实查 | — | **2023-07-07（停滞）** | — | **reject** | 双重问题：① **最近活跃 2023-07**，近三年停滞；② 自定义许可 → **许可判定：待核，不得进运行时**。R4 许可风险项 |
| concordia（编排参考） | github.com/google-deepmind/concordia | 上游未覆盖（**待核**） | — | — | 中：自带 agent 运行时假设 | adapt（仅范式） | 借其「情境化 agent + 角色扮演」范式，不集成运行时 |

**该层裁决**：adopt `py_trees`（BSD-3）为主；behaviac 因停滞 + 自定义许可 reject。

## L6 · 模型通道与结构化输出

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本（**实测**） | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **instructor** | github.com/567-labs/instructor · PyPI `instructor` | **MIT**（PyPI 实查；上游 JSON 同） | 1.17.0 | 2026-09-18 | **低**：`uv pip install` 实测 exit 0（拉入 openai/httpx 等）；与 pydantic 校验天然配合 | **adopt（主选，V0）** | 结构化输出必须**强校验**（R11）；instructor 把「模型输出 → schema」收敛为一层，与能力 `output_schema` 对齐 |
| **outlines** | github.com/dottxt-ai/outlines · PyPI `outlines` | **Apache-2.0**（PyPI 实查） | 1.3.3 | 2026-09-19 | 低-中：实测 `uv pip install` exit 0（含 outlines-core 0.2.14 + pillow） | **adopt（对照）** | 约束解码路线（本地模型侧更强）；本轮作为 instructor 的对照与 V1 本地推理配套 |
| pydantic / jsonschema（校验底座） | PyPI `jsonschema` | **MIT**（PyPI 实查） | 4.26.0 | 活跃 | **低**：S2 真跑实际用上，**真实拦下**了不合 schema 的模型输出（`memory.reflect` 的 `new_facts` 类型错误） | **adopt（V0 必备）** | 校验不能只是「声明」；S2 的失败路径证明它有实战价值 |
| OpenAI 兼容远端 API（tokenfab / deepseek-v4.1-flash） | `https://api.tokenfab.cn/v1` | 服务侧商用条款（**非开源许可**，属采购/账号条款） | — | — | **低**：S2 真跑成功；单次实测 2.33s（含 reasoning tokens） | **adopt（V0 主通道）** | 需注意：`timeout_ms=2500/3000` 对推理模型偏紧（实测降级），V0 建议提到 8~15s |
| vllm / SGLang | github.com/vllm-project/vllm · github.com/sgl-project/sglang | vllm 上游 JSON `NONE`（**待核**）；SGLang **Apache-2.0** | — | 2026-09 | **高**：**本机无 NVIDIA GPU**，本地大模型推理不现实 | reject（V0） | 硬件不满足；许可上 vllm 待核、SGLang 可商用 |
| ollama | github.com/ollama/ollama · 本机 `/opt/homebrew/bin/ollama` | 上游 JSON `NONE`（**待核**） | 本机已装可执行文件 | 2026-09-19 | 中：CPU 小模型可行（无 GPU）；**本轮未启动服务、未真跑**（GAP） | adapt（降级候选，未验证） | 作为 `local_model` provider 的降级位保留；**未真跑不得写成可用** |
| web-llm / transformers.js（浏览器内推理） | github.com/mlc-ai/web-llm（**Apache-2.0**）、github.com/huggingface/transformers.js（**Apache-2.0**） | Apache-2.0（上游 JSON 实查） | — | 2026-09 | 中：把推理放渲染层 → **违反「渲染层零模型调用」**（除非作为独立 provider 进程） | reject（V0）/ V1 备选 | 许可 ✅ 但架构冲突；若 V1 要用，必须作为 provider 适配器而非渲染层直连 |

**该层裁决**：V0 = instructor + jsonschema 强校验 + 远端 API；本地/浏览器推理留 provider 位但不启用。

## L7 · 记忆存储

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本 | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **sqlite（stdlib）+ numpy 余弦** | Python stdlib | 公共领域（sqlite）/ **BSD-3**（numpy） | Python 3.13.13 自带 | — | **低**：零外部服务、零网络；表结构已在 `02_source/v0_skeleton/kernel/deephealing_kernel/memory/store.py` 冻结 | **adopt（V0）** | 记忆只影响认知输入，不需要服务型数据库；同时避免「记忆层成为第二权威」 |
| sqlite-vec | github.com/asg017/sqlite-vec · PyPI `sqlite-vec` | **MIT / Apache-2.0 双许可**（PyPI 实查） | 0.1.9 | 活跃 | 低：sqlite 扩展，V0 后期可平滑替换 numpy 暴力检索 | **adapt（V1 首选）** | 与 V0 同栈（sqlite），迁移成本最低；双许可 → 可商用 ✅ |
| LanceDB | github.com/lancedb/lancedb · PyPI `lancedb` | **Apache-2.0**（PyPI classifier 实查：`License :: OSI Approved :: Apache Software License`） | 0.39.0 | 活跃 | 中：引入列式存储 + 自有 API | adapt（V1 备选） | 规模上去（多街区/长历史）时更强；Apache-2.0 → 可商用 ✅ |
| mem0 / letta / graphiti | github.com/mem0ai/mem0（**Apache-2.0**）、letta-ai/letta（**Apache-2.0**）、getzep/graphiti（**Apache-2.0**） | Apache-2.0（PyPI/上游实查） | mem0ai 2.1.0 | 活跃 | 中高：自带 agent 运行时/服务依赖，会与内核抢权威 | reject（V0） | 许可 ✅，但架构冲突（它们假定自己是记忆与 agent 的 owner）。范式可借鉴 |
| pgvector / qdrant | github.com/pgvector/pgvector（**NOASSERTION → 待核**）、github.com/qdrant/qdrant（上游 `no json` → **待核**） | 待核 | — | — | 高：需部署数据库服务 | reject（V0） | 引入部署面且许可未核实。R4 相关 |

**该层裁决**：V0 = sqlite + numpy；V1 优先 sqlite-vec；服务型向量库本轮不引入。

## L8 · 社会仿真 / 认知范式（范式借鉴，不集成运行时）

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本 | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **generative_agents** | github.com/joonspk-research/generative_agents | **Apache-2.0**（GitHub API 实查） | — | 2024-08 | **低（仅范式）**：记忆流 + 反思 + 日程三层结构可直接映射到 L6 记忆层与 L5 规则层 | **adapt（范式）** | 记忆流/反思/重要性打分是治愈向 NPC 的核心范式；但其运行时（前端 + 服务）不集成。Apache-2.0 → 可商用 ✅ |
| concordia | github.com/google-deepmind/concordia | **待核**（上游未覆盖） | — | — | 低（仅范式） | adapt（范式） | 情境化角色扮演与「游戏主控」概念可参考；**许可未核实，不得集成代码** |
| ai-town / oasis | a16z-infra/ai-town、oasis（上游未覆盖） | **待核** | — | — | 中：自带渲染与运行时假设 | reject（V0） | 与本架构的内核/传输分离冲突；许可待核 |
| sotopia / camel | 上游未覆盖 | **待核** | — | — | 低（仅范式） | adapt（评估中） | 社会互动评测范式可借鉴，V0 不引入 |

**该层裁决**：只借鉴范式（记忆流/反思/社会一致性），不集成任何运行时；许可未核者一律不引代码。

## L9 · 自进化（QD / 自改写）

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本 | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **pyribs（MAP-Elites）** | github.com/icaros-usc/pyribs · PyPI `pyribs` | **MIT**（GitHub API 实查；PyPI 未声明 license 字段） | PyPI 0.0.2（占位/早期） | 2026-07-22 | 低：纯 Python 库，网格 + 档案库 API 直接可用 | **adapt（V1 启用）** | QD 网格（社交频率/独处时长）适合「策略多样性」；V0 只冻结契约不启用。MIT → 可商用 ✅ |
| **dgm（自改写闭环参考）** | github.com/jennyzzt/dgm | **Apache-2.0**（GitHub API 实查） | — | 2025-08-13 | 中：闭环范式参考，不集成其执行器 | **adapt（范式 + 护栏）** | 自改写必须受控（五步护栏 + 只改数据化策略参数）；直接引入其「自改代码」会突破护栏（R5）。Apache-2.0 → 可商用 ✅ |
| —（无第二开源候选满足护栏要求） | — | — | — | — | — | 自研护栏 | 本项目要求「改写只碰数据、必须可回放、必须可回滚」，没有现成开源同时满足 |

**该层裁决**：V0 只冻结契约与护栏；V1 启用 pyribs 档案库 + QD；V2 才启用受控自改写。

## L10 · 观测 / 回放

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本 | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **事件日志 JSONL + 自研 replay/verify** | 本轮 `spikes/s1-determinism/`（真跑）+ `02_source/v0_skeleton/kernel/.../snapshot.py` | 自有 | — | — | **低**：S1 真跑证明可行（8 检查点、双跑一致、分歧可定位） | **adopt（V0）** | 回放是 AC-2 的判据来源，必须与内核同源；外部工具无法替代 |
| duckdb | github.com/duckdb/duckdb · PyPI `duckdb` | **MIT**（PyPI classifier 实查：`License :: OSI Approved :: MIT License`） | 1.5.5（PyPI） | 2026-08-31 | 低：直接 `read_json_auto('events.jsonl')` 做分析；**本机未装 CLI，`tools/duckdb_queries.sql` 未真跑（GAP）** | **adopt（V1 分析）** | 轨迹分析/成本统计的理想工具；MIT → 可商用 ✅ |
| OpenTelemetry（JS/Python） | github.com/open-telemetry/opentelemetry-js | **Apache-2.0**（上游 JSON 实查） | — | 2026-09-14 | 中：需接入 exporter/collector | adapt（V1 可选） | 指标/追踪标准；V0 用事件日志 + 指标面板即可。Apache-2.0 → 可商用 ✅ |

**该层裁决**：V0 = 事件日志 + 自研 replay/verify（已有真跑证据）；duckdb 进 V1 分析面。

## L11 · 内容 / 城市数据

| 候选 | URL | license | 版本 | 最近活跃 | 集成成本 | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|---|
| **自研 district pack 规范** | 本轮 `02_source/district.pack.schema.json` + `district.pack.spec.md` + 样例 pack（13 文件已签名） | 自有 | 1.0.0 | — | **低**：纯数据 + schema 校验；`pack.sig` 已真跑（`verify_pack.py` exit 0，篡改后 exit 1） | **adopt（V0）** | 「新增第二街区不改内核代码」要求数据驱动，现成格式无法直接满足（要 portals/entrypoints/签名与迁移路径） |
| osmnx | github.com/gboeing/osmnx | **MIT**（上游 JSON 实查） | — | 2026-07-31 | 中：真实路网数据获取，V1 可选 | adapt（V1） | 若要做真实城市尺度街区，用 OSM 数据；MIT → 可商用 ✅ |
| **BlenderGIS** | github.com/domlysz/BlenderGIS | **GPL-3.0**（上游 JSON 实查） | — | 2025-12-20 | — | **reject（运行时）/ 仅离线管线** | **许可判定：GPL-3.0 → 只能限定在离线美术管线**，其产出与代码**不得进入运行时、不得进入交付产物**。R4 |
| **UrbanWorld2.0** | github.com/tsinghua-fib-lab/UrbanWorld2.0 | **NONE（无许可声明）→ 待核** | — | 2026-09-07 | 高：研究项目，21 stars | **reject（V0）** | **许可判定：待核 → 不得进运行时**；且为研究原型。R4 |
| **convex-backend** | github.com/get-convex/convex-backend | **NOASSERTION（自定义）→ 待核** | — | 2026-09-09 | 高：自有后端范式（reactive DB） | **reject** | **许可判定：自定义许可待核 → 不得进运行时**；与内核权威模型冲突。R4 |

**该层裁决**：V0 自研 pack 规范；真实地理数据 V1 用 osmnx（MIT）；GPL/自定义/待核项一律隔离。

## L12 · 许可风险项（单列，供 Raven 复核）

| 项 | license（事实来源） | 能否进运行时 | 能否商用 | 本项目的处置 |
|---|---|---|---|---|
| **BlenderGIS** | **GPL-3.0**（上游 JSON 实查） | ❌ **否** | ⚠️ 仅离线管线内部使用 | 只允许在离线美术管线；产出需人工复核是否构成衍生；**不得进运行时与交付物** |
| **convex-backend** | **NOASSERTION**（上游 JSON 实查） | ❌ 待核 | ❌ 待核 | 不引入 |
| **behaviac** | **NOASSERTION** + 停滞（2023-07） | ❌ 待核 | ❌ 待核 | 不引入（已 reject） |
| **UrbanWorld2.0** | **NONE**（上游 JSON 实查） | ❌ 待核 | ❌ 待核 | 不引入 |
| **vllm / ollama** | 上游 JSON 抓取为 `NONE`（vllm）；ollama 同 | ❌ 待核 | ❌ 待核 | 仅作 provider 位；启用前需取得许可确认 |
| **pgvector / qdrant** | NOASSERTION / 抓取失败 | ❌ 待核 | ❌ 待核 | V0 不引入 |
| bitecs | **MPL-2.0**（npm 实查） | ✅ 可（文件级 copyleft） | ✅ 可 | 若引入需保留其文件许可声明；本轮未引入 |
| sqlite-vec | MIT / Apache-2.0 双许可（PyPI 实查） | ✅ | ✅ | V1 首选 |
| Godot | 上游抓取失败（社区共识 MIT，**未取得权威响应**） | ✅（待核） | ✅（待核） | 本轮 reject，无需核 |

---

## L13 · 世界模型 / 神经渲染（AC-14 / D-0.7）

**事实来源（round 3 二次核对，真跑）**：`bash spikes/facts-license/probe_facts_r3.sh`（命令 + 时间见 `spikes/facts-license/r3.summary.txt`，原始响应 `spikes/facts-license/out/r3-*.json`）。
**核对时间（UTC）**：2026-09-21T12:04Z。

| 候选 | URL | license（上游实查） | GPU 要求 | 集成成本 | 结论 | 理由与许可判定 |
|---|---|---|---|---|---|---|
| **NVIDIA Cosmos**（必含） | github.com/NVIDIA/Cosmos（11877★） | **OpenMDW-1.1（自定义，非 Apache-2.0）** — GitHub `license.spdx_id=NOASSERTION`，回读 `LICENSE` 首段 = `OpenMDW License Agreement, version 1.1` | 生成式推理需 **NVIDIA GPU**（本机 **无** → 不可跑） | 高（权重 + 显存 + 运维） | **reject（运行时）/ V1 离线侧待核** | **许可判定：自定义许可（OpenMDW-1.1）→ 待核**，未逐字核条款前不得进交付链。**修正**：`01 §16.1.4` 旧表述「Cosmos Apache-2.0」**不成立**，以本行为准 |
| **Tencent HunyuanWorld-1.0**（必含） | github.com/Tencent-Hunyuan/HunyuanWorld-1.0（2937★） | **腾讯社区许可**（`NOASSERTION`；`LICENSE` 首段 = `TENCENT HUNYUANWORLD-1.0 COMMUNITY LICENSE AGREEMENT`，**明示不适用于欧洲地区**） | lite 版可跑 4090；本机 **无 NVIDIA GPU** → 不可跑 | 高 | **reject（运行时）/ V1 离线侧待核** | **许可判定：自定义 + 地域限制 → 待核**；地域条款对交付链是实质限制 |
| **nerfstudio-project/gsplat**（必含之一） | github.com/nerfstudio-project/gsplat（5707★） | **Apache-2.0** ✅（上游实查） | 训练偏好 CUDA；CPU/MPS 可离线慢跑；运行时仅加载 + 渲染 | 中（离线管线） | **adapt（V1 离线侧）** | **许可判定：可商用 ✅**；神经渲染唯一「许可干净」候选（**运行时性能未实测 → GAP**） |
| **graphdeco-inria/gaussian-splatting**（必含之一） | github.com/graphdeco-inria/gaussian-splatting（23935★） | **Inria/MPII 自定义许可**（`NOASSERTION`；`LICENSE.md` 首段 = `Gaussian-Splatting License`，**非商用倾向**） | 同上 | 中 | **reject（交付链）** | **许可判定：自定义研究许可 → 待核**；训练/复现可离线研究，产物不得进交付链 |
| `danijar/dreamerv3` | github.com/danijar/dreamerv3（3811★） | **MIT** ✅ | 训练需 GPU（本机不可跑）；仅作范式参考 | — | **reject（运行时）/ 范式借鉴** | 许可是 MIT（干净），但本机不可跑；只借鉴范式 |
| **闭源 API 对照：Decart Oasis / Mirage** | decart.ai（闭源 API，实时逐帧生成） | 采购条款（非开源） | 只需网络（本机可行） | **低**（一次 HTTP + schema） | **reject（运行时权威链路）** | **许可判定：黑盒 + 版本漂移 + 无离线 → 只允许离线内容生产 / V1 实验**（与 ADR-010 一致） |
| **闭源 API 对照：Google Genie 3 / World Labs Marble** | deepmind.google（Genie 3，未开放 API）；worldlabs.ai（Marble，闭源产品） | 闭源产品条款 | 只需网络 | 低（若开放） | **reject（运行时）** | 未开放 / 不可控；本轮只作对照，不引入 |

**该层裁决**：世界模型**全部不进运行时权威链路**；离线侧 V1 主候选 = **gsplat（Apache-2.0 ✅）**；Cosmos / HunyuanWorld-1.0 / gaussian-splatting 一律**待核**（自定义许可）。
**本机可行性**：生成式世界模型**本机不可跑**（无 NVIDIA GPU）→ **GAP**（未实测，不得声称跑过）。

## L14 · AIGC 素材生成（图像 / 3D / 音频 / 视频）（AC-15 / D-0.8）

**事实来源**：同 L13（`spikes/facts-license/r3.summary.txt`；HunyuanVideo / Wan2.1 为追加探测，见 `out/r3-github-Tencent-Hunyuan-HunyuanVideo.json`、`out/r3-github-Wan-Video-Wan2.1.json`）。
**可商用判定口径**：代码许可与**权重许可分开核**；`待核` = 未取得可商用结论 → 不得进交付链。

### 图像（≥2）

| 候选 | URL | license | 可商用 | GPU / 本机 | 结论 | 理由 |
|---|---|---|---|---|---|---|
| **Tongyi-MAI/Z-Image**（必含） | github.com/Tongyi-MAI/Z-Image（12039★） | **Apache-2.0** ✅ | ✅ 可商用 | 可本机（MLX/mflux 或 diffusers） | **adopt（V0 白名单）** | 许可干净 + 本机可跑 |
| **QwenLM/Qwen-Image**（必含） | github.com/QwenLM/Qwen-Image（8353★） | **Apache-2.0** ✅ | ✅ 可商用 | 可本机（显存要求高于 Z-Image，需实测） | **adopt（白名单）** | 许可干净 |
| **FLUX.1-schnell**（必含） | huggingface.co/black-forest-labs/FLUX.1-schnell | **Apache-2.0** ✅（权重许可；仓库 `black-forest-labs/flux` 代码 Apache-2.0） | ✅ 可商用 | 可本机（mflux/diffusers） | **adopt（白名单）** | 与 **FLUX.1-dev（非商用）** 必须区分 |
| **FLUX.1-dev**（对照，禁入） | huggingface.co/black-forest-labs/FLUX.1-dev | **非商用权重**（FLUX.1-dev Non-Commercial License） | ❌ **禁** | 可本机 | **reject** | 非商用权重禁止进交付链（许可表 `adjudication=reject`） |
| **mflux**（必含，工具） | github.com/filipstrand/mflux（2355★）/ PyPI `mflux` | **MIT** ✅（GitHub + PyPI 双查） | ✅（工具） | 本机可跑（MLX） | **adopt（工具，tool_only）** | 工具许可干净；**产物许可由被调权重决定** |
| `diffusers` | PyPI `diffusers` | **Apache-2.0** ✅ | ✅（工具） | 本机可跑（CPU/MPS） | **adopt（工具）** | 编排库，产物许可同样取决于权重 |

### 3D（≥2）

| 候选 | URL | license | 可商用 | GPU / 本机 | 结论 | 理由 |
|---|---|---|---|---|---|---|
| **Tencent-Hunyuan/Hunyuan3D-2**（必含） | github.com/Tencent-Hunyuan/Hunyuan3D-2（14926★） | **腾讯自有条款**（`NOASSERTION`；`LICENSE` 首段 = `TENCENT HUNYUAN 3D 2.0 COMMUNITY LICENSE AGREEMENT`，含地域限制） | ❌ **待核 → 拒收** | CUDA 依赖 → 本机不可跑 | **reject（交付链）** | 自定义 + 地域限制；本轮保守拒收 |
| **VAST-AI-Research/TripoSG**（必含） | github.com/VAST-AI-Research/TripoSG（1798★） | **MIT**（代码）✅ / **权重许可未核** | ❌ 待核（权重） | CUDA 依赖 → 本机不可跑 | **reject（本轮）** | 代码 MIT 可商用，但权重许可与运行环境未核 → 不进交付链 |

### 音频（≥2）

| 候选 | URL | license | 可商用 | 本机 | 结论 | 理由 |
|---|---|---|---|---|---|---|
| **ace-step/ACE-Step**（必含） | github.com/ace-step/ACE-Step（4849★） | **Apache-2.0** ✅ | ✅ 可商用 | 可自托管（CPU/MPS） | **adopt（白名单）** | 许可干净 |
| **MusicGen**（对照，禁入） | github.com/facebookresearch/audiocraft（23640★） | 代码 **MIT** / **权重 CC-BY-NC** ❌ | ❌ **禁** | 可本机（CPU） | **reject** | **代码 MIT ≠ 权重许可**；权重 CC-BY-NC 禁商用（ADR-011 陷阱项） |

### 视频（≥2）

| 候选 | URL | license | 可商用 | 本机 | 结论 | 理由 |
|---|---|---|---|---|---|---|
| **Wan-Video/Wan2.1** | github.com/Wan-Video/Wan2.1（17018★） | 代码 **Apache-2.0** ✅ / **权重许可未核** | ❌ 待核（权重） | 需大显存（本机不可跑） | **reject（本轮）/ V1 离线云待核** | 代码许可干净；权重条款未核 |
| **Tencent-Hunyuan/HunyuanVideo** | github.com/Tencent-Hunyuan/HunyuanVideo（12551★） | **自定义**（`NOASSERTION`；`LICENSE` 路径 404，未取得原文） | ❌ 待核 | 需大显存（本机不可跑） | **reject（本轮）** | 许可未取得原文 → 待核，不得进交付链 |

### 工作流编排

| 候选 | URL | license | 可商用 | 结论 | 理由 |
|---|---|---|---|---|---|
| **ComfyUI**（必含） | github.com/comfyanonymous/ComfyUI（134232★） | **GPL-3.0** ✅（上游实查；首轮 301 未跟随重定向，round 3 修正为 `-L` 后得 GPL-3.0） | 代码可商用但 **copyleft** | **adapt（独立进程）** | V0 只允许「**独立进程 + 产物文件**」；**不得链接进产品**；工作流 JSON 作为**受管产物**登记 sha256，其引用的 checkpoint 必须过白名单表（`spikes/s6-asset-pipeline/logs/n8_workflow_nonwhitelist.log`） |

**该层裁决**：白名单 = `Z-Image` / `Qwen-Image` / `FLUX.1-schnell` / `ACE-Step`（模型）+ `mflux` / `diffusers`（工具）；禁入 = `FLUX.1-dev` / `MusicGen` 权重；待核 = `Hunyuan3D-2` / `TripoSG` / `Wan2.1` 权重 / `HunyuanVideo`。数据表落点：`02_source/asset.license.table.data.json`。

---

## 真跑证据汇总（≥2 个候选有真实执行证据 —— 实际做到 4 个）

| 候选 | spike | 关键证据 |
|---|---|---|
| three.js + vite | **S3** | `vite build` exit 0（dist 478 kB）、tsc exit 0、11 项场景断言全通过、WebGL2 截图 2 张 |
| instructor / outlines / jsonschema | **S2** | `uv pip install` 三次 exit 0；jsonschema 真拦下不合 schema 的模型输出 |
| colyseus | **S4** | 安装（143 依赖/196 MB/3 min）+ 启动 + 连接 + 状态同步 exit 0；4 个版本耦合坑 |
| 远端模型 API（tokenfab） | **S2** | 真实 chat/completions 调用成功（2 叶走 remote_api），transcript 中 `Authorization` 脱敏 |
| 自研内核（Python） | **S1** | 双跑哈希一致 + 两个非确定性负例被检出 |
| 自研 pack 签名/校验 | 02_source | `pack_sign.py` 生成 13 文件签名，`verify_pack.py` exit 0；篡改后 exit 1 |

---

## 许可事实表修订记录（PM F-5 收口）

来源：`spikes/facts-license/facts.summary.txt`（复跑命令 `bash spikes/facts-license/probe_facts.sh`，exit 0）。

| # | 原状 | 根因 | 处置 | 现状 |
|---|---|---|---|---|
| 1 | `lancedb 0.39.0` → `unknown` | 探针只读 PyPI `.info.license`（为 `null`），忽略 `.info.classifiers` | 探针改为 license_expression → license（非空）→ **classifier** 依次回退 | **Apache-2.0**（`License :: OSI Approved :: Apache Software License`） |
| 2 | `duckdb 1.5.5` → `unknown` | 同上（`.info.license` 为 `null`） | 同上 | **MIT**（`License :: OSI Approved :: MIT License`） |
| 3 | `pyribs 0.0.2` → 许可列空白 | `.info.license` 为**空字符串**，`//` 判空失败 → 输出空列 | 探针显式 `select(length>0)`；PyPI 确实未声明 → 启用**替代来源** GitHub API | **MIT**（`https://api.github.com/repos/icaros-usc/pyribs` → `license.spdx_id=MIT`） |
| 4 | `recast-navigation-js` → npm 404 | **包名有误**（仓库名 ≠ npm 包名） | 探针改用真实可安装包名；404 项留档防误装 | **`recast-navigation` 0.43.1 / MIT**；`recast-navigation-js` 标注为 GAP+404 |
| 5 | `vite` 一行列错位（许可列填了 URL） | 探针取 npm **全量**文档（vite 5.5 MB），`curl --max-time 30` 截断 → jq 解析失败 → 版本/许可列为空 → `column -t` 整行错位 | 探针改取 `<pkg>/latest` 单版本文档（几 KB）；截断的旧证据移入 `out/attic-corrupt/` | **vite 8.3.0 / MIT**，全表 23 行均为 5 字段、无空列 |

- 校验命令：`awk -F'\t' 'NR>1 && NF!=5' facts.summary.tsv`（期望零输出）；`grep -c 'unknown\|GAP' facts.summary.tsv`（期望仅 404 留档行 2 处）。
