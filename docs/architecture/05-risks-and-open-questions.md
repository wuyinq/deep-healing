# 09 · 风险登记 · 未决问题 · 成本与性能预算

- 计划：`REQ-20260921-002-deephealing-architecture-freeze`　作者：artisan　日期：2026-09-21
- 上游：`01_architecture_design.md` §9/§11（architect 自评）、本轮 S1~S4 真跑数据（`03_spike_log.md`）
- 说明：本文的「实测」列只写**真跑得到的数字**；未测的一律写「未测」或 `GAP`，不写估计当结论。Raven 的独立审计面见 `05`。

---

## 1. 风险登记（承接 01 §11，并补本轮实测到的新风险）

| ID | 风险 | 分级 | 本轮实测状态 | 触发条件 | 影响面 | 缓解 |
|---|---|---|---|---|---|---|
| R1 | tick 内非确定性来源（时钟/顺序/异步回填） | CRITICAL | **已用 S1 负例证明可检出**：wall-clock 与迭代顺序泄漏各造成 8/8 检查点分歧 | 任一进入 tick | 回放哈希不一致 → AC-2 失败 | §6.1 清单 + `verify` 双跑判据 + `--dump-divergence`；S1 已把两个负例固化为用例 |
| R2 | 认知成本失控 | MEDIUM | **实测比声明更差**：单次 `emotion.appraise` 远端调用 in=238/out=428 tokens、5.95s；声明值 est 420/60（输出低估 ~7×） | 活跃度估算偏低 / 无硬顶 | 账单与延迟 | `BudgetLedger` 三级硬顶 + 降级阶梯；**必须先按实测重标 `capability.cost`/`est_tokens_*`**（见 §3.1 与 Q1/Q2） |
| R3 | cassette 陈旧/失配 | MEDIUM | **已实装并真跑**：key 含 `capability_version`；换上下文后 3 叶全 miss 且 fail-closed（exit 1） | 能力版本升级后回放旧 cassette | 回放等价性 | key 含版本 + miss 策略 fail-closed（`cassette.format.md` §5） |
| R4 | 许可污染 | CRITICAL | 已逐条核：BlenderGIS **GPL-3.0**、convex/behaviac/vllm/ollama/pgvector/qdrant **待核**（见 06 §L12） | GPL/自定义许可进运行时 | 商业可用性 | GPL 仅限离线美术管线；待核项不得进运行时；V0 依赖清单只含 MIT/Apache/BSD |
| R5 | 自进化失控 / 目标函数被劫持 | CRITICAL | V0 不启用改写（只冻结护栏）；**目标函数目前只有文字约束 + 少量数值，护栏偏空** | 自我改写绕过护栏 | 治愈向内核被破坏 | 五步护栏 + 只改数据化参数 + 熔断；**V1 启用前必须把治愈向目标函数做成可计算指标**（Q4） |
| R6 | IP 越界 | CRITICAL | 本轮交付物已做命名审查：只用「幸福小区 / 1 号楼 / 夜班住户 / 备考住户」等结构性与角色性描述，**未使用任何原著人物姓名/台词/情节** | 复制原文/人物名 | 法律风险 | 内容包 `pack.json.license=proprietary-self-authored`；素材自研/程序化；Raven 复核文本 |
| R7 | 双权威漂移（传输层持状态） | MEDIUM | **结构上已消除**：V0 自研 L2 无世界状态真值、无规则计算、无模型调用（S2 证明模型调用只在 provider 内） | 传输层缓存并回写 | 状态分叉 | L2 明确非权威；权威写入唯一在 tick 执行阶段；若 V1 采用 colyseus 则该风险立刻复活（ADR-003） |
| R8 | Rust 工具链缺失导致内核性能路线受阻 | MEDIUM | 实测 **无 cargo/rustup**；S1 Python 原型 2000 tick（5 NPC）耗时 **0.67s ≈ 0.34 ms/tick** | V1 需 ECS/物理性能 | 工期 | V0 用 Python；V1 前做性能 spike 再决策（ADR-001） |
| R9 | 浏览器截图/构建不可复现 | LOW | **已消除**：S3 构建 exit 0 + 截图 2 张（WebGL2 真渲染，76 帧，无 console error） | Playwright/网络异常 | AC-11 证据 | 已产出 `out/*.png` + 场景断言 JSON；**round 2 更正**：场景断言只覆盖**配置项**，「治愈系氛围达成」记 **GAP**（画面级度量显示无天空，见 `03_artisan_self_test.log`「round 2 · C5」）；截图归属已加服务实例自证（`spikes/s3-render/logs/s3_server_instance.json`）；注意 playwright 与缓存 chromium 版本需对齐（§4.3） |
| R10 | 记忆层无界增长 | MEDIUM | 契约已冻结（容量上限 + 重要性阈值 + 衰减 + `superseded_by`），**实现未做、未测** | 无裁剪策略 | 内存/成本 | V0 实施 W5；需补容量压测（Q6） |
| R11 | 能力 schema 被绕过（模型输出不合规进入世界） | CRITICAL | **本轮实测到真实触发**：模型把 `new_facts` 返回成字符串数组 → `jsonschema` 判 `on_invalid_schema` → 自动降级并落 `capability.fallback` 事件 | 校验缺失或降级路径未校验 | 世界状态损坏 | 严格 schema + **所有 fallback 出口都校验**（cassette 命中后也校验）+ Sentinel 对抗用例 |
| R12 | 参与模式刷分/滥用 | MEDIUM | 权限判定部分已可执行（observe → `E_MODE_READONLY`）；限流/冷却/预算**未实现** | 无 rate limit / budget | 体验与叙事破坏 | §6.3 护栏（rate_limit/cooldown/impact_budget/审计），V0 实施 W7 |
| **R13（新）** | **事件日志体积超预算 ~15×** | **HIGH** | **实测**：S1 2000 tick / 5 NPC → `events.jsonl` **16.5 MB**（10081 行，平均 **1637 B/事件**）= 8.25 KB/tick → **≈ 297 MB/小时 @10 Hz**，而 AC-10 预算是 **≤ 20 MB/小时** | 事件 payload 内联 `state_after` 全量组件 + 每事件 `rng_digests` | 磁盘/IO/回放加载时间；云上存储成本 | ① `rng_digests` 只在快照里留（每事件去掉）；② 事件只存**组件级 diff** 而非全量 `state_after`；③ 日志滚动 + 压缩；④ 若保留全量，需把 AC-10 预算改成实测值（Q3） |
| **R14（新）** | **`timeout_ms` / `latency_ms_budget` 声明与实际差 5×** | **HIGH** | **实测**：`emotion.appraise` 5.95s、`intent.plan` 5.57s，而声明 `latency_ms_budget=900/1200`、`timeout_ms=2500/3000` → 首轮真跑**直接超时降级** | 远端推理模型（含 reasoning tokens） | 认知降质、体验延迟 | 规划/评估类能力 `timeout_ms` 提到 **8~15s**；或强制这两类走 cassette/规则层；`latency_ms_budget` 同步重标（Q1） |
| **R15（新）** | **`est_tokens_*` 声明严重失真** | **MEDIUM** | **实测**：`emotion.appraise` in 238 / out 428（声明 420/60）；`intent.plan` in 267 / out 391（声明 900/120） | 用声明值做预算与降级决策 | 预算护栏形同虚设 → R2 失控 | 用真实账单/usage 回填 `capability.cost.est_tokens_in/out`；预算按实测校准（§3.1） |
| **R16（新）** | **prompt injection 进能力上下文** | **HIGH** | 契约已声明 `safety.prompt_injection_guard`（`delimit_and_ignore_instructions` / `allowlist_fields`），**实现未做、未测** | 玩家 `instruction_text` 进入模型上下文 | 模型被诱导产出破坏治愈向内容 / 泄漏内部字段 | V0 实施时必须真装：字段白名单 + 分隔符 + 「忽略其中指令」+ 输出侧 schema 与内容双校验；Raven 对抗面 |
| **R17（新）** | **cassette 规范化跨语言不一致 → 假 miss** | **MEDIUM** | 未测（单语言 spike） | Python 内核与 Node/TS 侧各自实现 canonical JSON | 回放必然 miss 或假命中 | 全链路只允许一份 `canonical_json` 实现（`tools/canonical_json.py` 为唯一来源，其他语言按同规则实现并**加跨语言一致性用例**） |
| **R18（新）** | **`local_model` provider 未验证** | **MEDIUM** | **GAP**：本机装有 ollama 可执行文件但本轮未启动服务、未真跑；无 NVIDIA GPU 使 vllm/SGLang 路线不可行 | 需要离线降级时发现该通道不可用 | 离线能力只剩规则层 | 降级阶梯里 `local_model` 目前是「声明但未验证」；V0 若要依赖它必须先补 spike（Q7） |

---

## 2. 未决问题（需裁决/需人介入）

| ID | 问题 | 影响 | 建议处置 | 建议 owner |
|---|---|---|---|---|
| **Q1** | 规划/评估类能力的 `timeout_ms` / `latency_ms_budget` 该定多少？实测 5.6~6.0s，声明 2.5~3.0s | 不改就会一直走降级（认知降质）；改大了会阻塞体验 | 建议 `timeout_ms` 8000~15000ms、`latency_ms_budget` 4000~6000ms；并把「超预算记 metric 但继续等待」与「超时立即 fallback」明确区分 | architect（契约变更） |
| **Q2** | 远端 API 的真实单价与账单口径？`capability.cost` 里是声明值 | 成本预算与降级阈值都依赖它 | 用真实账单/usage 回填；`BudgetLedger` 的日成本硬顶按实测校准 | lanova（采购/账号）/ architect |
| **Q3** | 事件日志体积预算：AC-10 写 ≤ 20 MB/小时，实测 ~297 MB/小时 | 存储/IO 成本，回放加载时间 | 三选一：① 改事件设计（去 `rng_digests`、改存组件 diff）② 保留设计、把预算改成实测值 + 滚动/压缩 ③ 降低采样（只在关键 tick 存全量） | architect（契约）+ sentinel（复测） |
| **Q4** | 治愈向目标函数如何变成可计算指标？现在只有文字约束 + `healing_delta` 数值 | 自进化护栏（R5）与任务奖励都依赖它 | V1 启用自进化前必须先定义指标与阈值（可测、可回放、可审计） | architect + raven（滥用面） |
| **Q5** | `pyribs` PyPI 包（0.0.2）与 GitHub 仓库（MIT，2026-07 活跃）的关系？ | V1 引入 QD 的可行性 | 引入前核对 PyPI 包发布者与仓库对应关系；不确定则改为从仓库安装并锁 commit | architect |
| **Q6** | 记忆层容量/裁剪压测口径（每 NPC 上限、衰减半衰期） | R10 无界增长 | V0 实施 W5 时补压测：长历史 + 多 NPC 下的 RSS 与检索延迟 | artisan（V0）+ sentinel（复测） |
| **Q7** | `local_model` 通道要不要在 V0 就验证？ | R18；离线降级只剩规则层 | 建议 V0 至少做一次 ollama CPU 小模型真跑（或明确写「V0 不支持本地模型」） | lanova（预算/优先级） |
| **Q8** | 多 pack 并存（多街区同时加载）要不要进 V1？ | 状态合并的确定性复杂度（ADR-008 的 V0 简化） | V1 再议；若要做，必须先解决「跨 pack 状态的规范化与哈希」 | architect |
| **Q9** | `duckdb` CLI 未安装 → 观测层示例查询未真跑 | AC-8 的 V0 证据强度 | 安装 duckdb CLI（`brew install duckdb` 或 PyPI 包）后复跑 `tools/duckdb_queries.sql` | artisan（V0） |
| **Q10** | 玩家文本的审计留存：只存 digest 会不会让「回放复现玩家介入」做不到？ | 审计与回放的取舍 | 若回放需要复现介入，则需存「可回放的最小结构」（如指令模板 + 参数），而非原文 | architect + raven |

---

## 3. 成本预算（每 NPC 每日 token）

### 3.1 实测基线（本轮真跑，非估计）

| 能力 | provider | in tokens | out tokens | 延迟 | 来源 |
|---|---|---|---|---|---|
| `emotion.appraise@1.0.0` | `remote_api` | **238** | **428** | **5947 ms** | `spikes/s2-capability-cassette/cassettes/emotion.appraise@1.0.0/remote_api.cassette.jsonl`（meta） |
| `intent.plan@1.0.0` | `remote_api` | **267** | **391** | **5571 ms** | 同上（`intent.plan@1.0.0/remote_api.cassette.jsonl`） |
| `emotion.appraise` | `deterministic_rule` | 0 | 0 | **0.107 ms** | `spikes/s2-capability-cassette/logs/s2_offline.result.json`（events） |
| `intent.plan` | `deterministic_rule` | 0 | 0 | **0.052 ms** | 同上 |
| `memory.reflect` | `deterministic_rule`（远端输出不合 schema 被拦后降级） | 0 | 0 | **0.076 ms** | 同上 |

**结论**：单次「远端小模型调用」实测约 **650~670 tokens**（其中输出占 6 成，reasoning tokens 计入输出）。这是本节所有估算的基准，**不是** `capability.cost.est_tokens_*` 里那个失真值（R15）。

### 3.2 三档活跃度的日 token（按实测 660 tokens/次 重算）

| 活跃度 | 认知调用模式 | 日远端调用数（目标） | 日 token（实测口径） | 规则层承担 | 备注 |
|---|---|---|---|---|---|
| **静默 idle** | 仅日程触发 + 反思 1 次/日 | **≈ 20** | **≈ 13k** | 其余全部 | 与 01 的 12k 基本吻合；远端调用几乎只在反思 |
| **常规 normal** | 事件触发规划 + 情绪评估 | **≈ 100** | **≈ 66k** | 低价值决策走规则 | 01 写「~450 次调用 / 65k tokens」→ **按实测口径 450 次会是 ~297k**，超 4.5×。**必须二选一：把调用数降到 ~100，或把日预算提到 ~300k**（Q2 裁决） |
| **深度 deep** | 叙事生成 + 关系推理 + 反思 | **≈ 330** | **≈ 218k** | 兜底 | 与 01 的 220k 吻合（01 的 1400 次同样偏多，按实测应 ~330 次） |

- **5 NPC 混合（1 深 / 2 常规 / 2 静默）**：按实测口径 ≈ **2×13k + 2×66k + 1×218k = 376k tokens/日**（与 01 的 380k 一致 —— 巧合但说明 01 的**总量**结论站得住，**分档调用数**需要按实测下调）
- **成本公式**：`cost = Σ(in/1k × usd_in + out/1k × usd_out)`，逐能力在 `capability.cost` 声明；`BudgetLedger` 硬顶 + 超限降级
- **降级阶梯**（按顺序）：① 换更低成本 provider → ② 缩短上下文/减少反思频率 → ③ 切 `local_model`（**未验证**，R18）→ ④ 切 `deterministic_rule` → ⑤ 切 `deterministic_stub`（世界不断线，认知降质）
- **校准动作**：V0 第一周用真实 usage 回填 `capability.cost.est_tokens_in/out`，并把 `BudgetLedger` 的日 token 上限按上表设定（**这是把 R2/R15 关掉的唯一办法**）

---

## 4. 性能预算（帧率 / tick / 延迟 / 内存 / 日志）

### 4.1 预算表（来自 01 §9.2，含本轮实测状态）

| 指标 | 目标 | 下限 | 本轮实测 | 状态 |
|---|---|---|---|---|
| 渲染帧率 | 60 fps | 30 fps | 浏览器内 **76 帧**（Playwright 1200ms 内，含初始化）；`webgl2=true`、软阴影开启 | 基线通过（S3），真实 fps 需在 V0 用性能面板测 |
| 内核 tick | 10 Hz（dt=100ms），p95 ≤ 20ms（5 NPC） | 5 Hz | **S1 原型 2000 tick / 5 NPC = 0.67s → 均值 0.34 ms/tick**（含事件写入与每 25 tick 快照） | 余量充足（**注意**：原型只做最简决策，不含记忆检索与能力调用） |
| 观察模式端到端 | ≤ 150 ms p95 | ≤ 300 ms | 未测（V0 才能测：内核→L2→浏览器） | GAP |
| 参与模式意图 | ≤ 2 tick（200ms）+ LLM 异步 ≤ 3s | ≤ 5s | 未测；但**远端 LLM 实测 5.6~6.0s**，已超 3s 目标 → 需把「LLM 异步 ≤3s」改成「异步不阻塞 tick，UI 显示 pending」 | 需重标（R14/Q1） |
| 内存 | 内核 ≤ 800 MB RSS / 浏览器 ≤ 1.5 GB | — | 未测 | GAP |
| 日志增长 | ≤ 20 MB/小时 | — | **实测 ≈ 297 MB/小时**（R13） | **超预算 15×，必须处置** |

### 4.2 日志体积测算（可复核）

```
events.jsonl (S1, 2000 tick, 5 NPC) = 16,500,538 bytes / 10,081 行
平均每事件                            = 1,636.8 bytes
每 tick（5 NPC + 偶尔快照事件）        = 16,500,538 / 2000 ≈ 8,250 bytes
@10 Hz                                = 82,500 B/s ≈ 297 MB/小时
预算（AC-10）                          = ≤ 20 MB/小时  →  超 14.9×
checkpoints/（80 个文件，全量状态）     = 320 KB 总计（≈4 KB/个）→ 不是瓶颈
```

**主要膨胀源**：每个 `npc.action` 事件内联了 `state_after`（全量 needs/emotion/pos/schedule）+ `rng_digests`（所有 stream 的摘要）。

### 4.3 环境相关的实测注意事项（复跑前必读）

1. **`playwright@1.63` 期望 `chromium_headless_shell-1243`，本机缓存为 `chromium-1234`** → 截图脚本回退 `channel=chrome` 成功；纯 headless-shell 需 `npx playwright install chromium`（未执行）
2. **node 有两个安装**：非交互 shell 里 `node` → `/Users/wooyinq/.local/bin/node`（**v22.23.2**，`.hermes/node` 软链）；`/opt/homebrew/bin/node` 是 **v26.3.1**。本轮 S3 构建与 S4 连接都在 v22.23.2 下跑通；涉及 Node 版本相关行为时必须显式记录 `node -v` 与 `which -a node`
3. **`colyseus@0.18` 的依赖耦合**：`@colyseus/schema ^5.0.8`、客户端必须 `@colyseus/sdk`、`Room` 从 `@colyseus/core` 导入、`@type` 装饰器需构建步骤（S4 实测）
4. **`timeout_ms` 覆盖**：spike 用 `--timeout-ms-override 20000` 才跑通远端调用；V0 实现不应依赖命令行覆盖，而应改契约值（Q1）

---

---

## 6. round 3 增补：AC-14 / AC-15 / D-0.9 的新风险与未决项

### 6.1 新风险（本轮实测/新查）

| ID | 风险 | 触发条件 | 影响 | 分级 | 处置 |
|---|---|---|---|---|---|
| **R3-1** | 远端 `memory.reflect` 的输出**不满足 `output_schema`**（实测：模型把 `insights` 返回为对象、`new_facts` 返回为字符串，而契约要求 `insights: string[]` / `new_facts: object[]`） | 每次真实远端调用（10/10 次运行复现） | 该叶**永远走 `on_invalid_schema` 降级**；AC-13「provider 输出 schema 合法性等价」在该叶不成立；remote 类等价性证据对 memory.reflect 实际来自 cassette/规则层 | **MEDIUM** | 两条路二选一：① 收紧提示词/改用结构化输出库强制（ADR-006 的 instructor 路径）；② 修订 `memory.reflect` 的 `output_schema` 使其与模型能力匹配。**本轮不改契约数值/结构**，只登记（→ V0 待办见 §6.1.1）。证据：`spikes/s5-latency-calibration/logs/degradation.adopted.json` 的 `runs[].other_fallback_reasons` |
| **R3-2** | 标定分布受**网络拥塞**影响极大：24 次真实调用 p50 = 7.44 s、p95 = 43.36 s、max = 54.03 s（同一 API 通道） | 测量窗口内端点负载高 | 按冻结规则推导出的声明值 ≈ **43–44 s**，远大于 round 2 的历史样本（5.57–6.60 s）→ 声明值是否代表「常态」需 PM 判断 | **MEDIUM** | ① 本轮**不**事后调整规则（那会变成自证）；② 建议 V0 在**多时段**重复标定并取保守上界；③ 该分布已如实落盘（`logs/latency.distribution.json`） |
| **R3-3** | 世界模型 / AIGC 的**离线云成本不可核验** | 无 GPU、无云账号实测 | AC-14 G4 与 AC-15 成本估算都只能给公式 | **MEDIUM** | G4 阈值**待 PM / 用户给定**；AC-15 成本数字记 **GAP**（不得用「预计」冒充） |
| **R3-4** | 上游许可事实与 `01 §16.1.4` 旧表述冲突（Cosmos 并非 Apache-2.0，实为 **OpenMDW-1.1**） | 逐条核对上游 | 若照旧表述决策会误判「许可干净」 | **MEDIUM** | 已在 `06` L13 与 ADR-010 更正；`01` 属 architect 只读件 → 建议 architect 侧同步修订 |
| **R3-5** | `content_hash` 的「解码后像素 + 规范化」口径**未实现**（V0 示例取 `file_bytes`） | 换 EXIF / 重编码 | 「可重生成 / 可追溯」在该口径下不可复算 | LOW | V0 补像素解码器 + 规范化规则；当前已如实标注（`asset.manifest.sample.json` 的 `meta.note`） |
| **R3-6** | `imagine.predict` 的 `remote_api` provider 的 `impl` = `module:deephealing_kernel.providers.worldmodel_placeholder:predict_remote` —— **该模块在 V0 骨架里不存在**（只有 `cassette.py` / `deterministic_rule.py` / `local_model.py` / `remote_api.py`） | 任何解析 `providers[].impl` 的执行体（本轮的确定性闸门只解析 `deterministic_rule` / `cassette_replay`，故**未被覆盖**） | impl 指针悬空：世界模型占位实现落地前，该 provider 无法被真解析；「provider 可解析」这一主张对 `imagine.*` 不成立 | LOW | V0 实现 `08_v0_plan.md` 的 `provider-rule` / 世界模型占位时一并关闭（或把 impl 指向真实模块）；本轮**不**新增占位模块（§16.0 明确不做 V0 产品实现） |

#### 6.1.1 R3-1 → V0 待办（F10 / RR3-6 收口，round 3 · 修复迭代 1 登记）

architect 裁决（`01 §16.10` RR3-6）：**不得**为求绿去改契约迁就远端输出（那是弱化判据）。
因此本项**保持 GAP**，并登记为 **V0 待办**（须在 V0 动手时关闭）：

| 待办 | 具体动作 | 验收方式 | 关联 |
|---|---|---|---|
| **V0-TODO-1** 结构化输出对齐 | 用 ADR-006 的 instructor/jsonschema 路径**强制** `memory.reflect` 输出形状：`insights: string[]`、`new_facts: object[]`（含 `confidence`）；不得靠「模型自己听话」 | 在**声明值**下真跑 ≥10 次，`on_invalid_schema` 降级次数 = **0**，且逐次输出过 `output_schema` | AC-13 remote 面 / ADR-006 |
| **V0-TODO-2** 重试策略 | schema 非法时的**有限重试**（N≤2）+ 重试后仍非法才降级；重试必须落事件（可审计） | 负例：注入非法输出 → 重试发生且被记录；重试耗尽 → 降级 + `capability.fallback.reason=on_invalid_schema` | D-0.9 第 2 条 |
| **V0-TODO-3** 提示词约束 | 提示词模板显式给出字段形状与示例（`insights` 是字符串数组，不是对象数组） | 同 V0-TODO-1 的验收 | ADR-006 |

> **AC-13 remote 面在本轮**（含修复迭代 1）**继续记 GAP**：`run_s2.sh` 实测 `remote_call_status=degraded`，
> 脚本已把本次运行排除出 AC-13 remote 类等价性证据并写入 `logs/ac13_remote_equivalence.gap`。
> **不得**因「脚本 exit 0」把它读成 PASS（详见 `03_artisan_self_test.log` 的 AC-13 行与 R7b）。

### 6.2 新未决问题（需裁决 / 需人介入）

| ID | 问题 | 影响 | 建议处置 | 建议 owner |
|---|---|---|---|---|
| **Q11** | 声明值取 **43–44 s** 是否可接受？ | 直接决定远端是否还在「默认路径」上；也影响 tick 关键路径的等待上限 | 二选一：① 接受（远端为能力补充、超时即降级，43 s 是当前网络下的实测上界）；② 收紧为「常态窗口」标定（多时段采样 + 取保守上界），并把更严候选作为 V0 默认 | **PM / 用户**（D-0.9 属用户裁决域） |
| **Q12** | AC-14 的 G4（单位成本）阈值 | 无阈值则 V1 实验门禁的 G4 无法判定 | 由 PM / 用户给定；本轮只交付公式 + 实测方法 | PM / 用户 |
| **Q13** | 世界模型 / AIGC 的离线云不可核验项（云侧产出无法本地复算） | 「许可已保证」不可宣称 | 按 RA-2 先例登记为**已声明边界**（`provenance.self_reported`）；对外使用前人工过审 | architect + raven |
| **Q14** | `imagine.*` 的真实调用**未实测**（本机无 GPU / 无世界模型端点） | 该能力的声明值属**代理标定**（同一 API 通道分布 + 冻结 offset） | V1 拿到端点后重标；本轮标 GAP | architect（V1） |
| **Q15** | REQ 中是否仍有「远端 API 为主 provider / LLM 为主」的相反表述？ | D-0.9 第 4 条要求同步改写；REQ 属 PM 只读 | **待 PM 修订**（本轮不自行改 REQ，也不据此判 block） | lanova（PM） |
| **Q16** | `memory.reflect` 的输出契约与真实模型能力不匹配（见 R3-1） | 该叶的 remote 等价性证据不成立 | 见 R3-1 的两条路 | architect + artisan（V0） |

### 6.3 成本区间（带实测基础或标 GAP）

| 项 | 区间 / 公式 | 实测基础 | 状态 |
|---|---|---|---|
| 远端模型调用延迟 | **7.44 s（p50）～ 43.36 s（p95）**，max 54.03 s | 24 次真实调用（round 3，`logs/latency.distribution.json`） | **实测**（注意 R3-2 的拥塞边界） |
| 远端模型 token 成本 | `est_tokens_in/out` × 声明单价 | `capability.cost` 为**声明值**，未用真实账单校准 | **GAP**（承 Q2） |
| 图像/音频本机生成成本 | `单次生成耗时(实测) × 本机单位时间成本` | **无实测**（本轮未做素材生成 spike） | **GAP** |
| 3D / 视频离线云成本 | `API 单价 × 调用次数 + 离线云时长成本` | **无实测**（无云账号、无 GPU） | **GAP** |
| 世界模型单位成本（G4） | `每 1000 次 imagine 调用成本 / 每生成分钟视频成本` | **无实测** | **GAP + 阈值待 PM 给定**（Q12） |

---

## 7. 给 Sentinel / Raven 的定向提示（round 3 增补）

- **Sentinel**：请独立复跑 `spikes/s5-latency-calibration/calibrate.py check`、`spikes/tools/check_no_override_evidence.sh`、
  `spikes/s6-asset-pipeline/run_s6.sh`、`spikes/s7-capability-binding/run_s7.sh`，并**独立核验**：
  ① 规则文件 mtime 是否真早于分布日志；② 清单声明值是否与报告逐值一致；③ 资产校验器是否真拒收 4 类以上；
  ④ `event_chain_hash` 的 `run↔replay` 8/8 是否可复现（`bash spikes/s1-determinism/run_s1.sh`）。
- **Raven**：本轮新增的对抗面 —— ① 「世界模型不权威」的绕行面（provider 类别换枚举值 / 非确定性输出入规则层，
  见 `spikes/s7-capability-binding/` 的负例能否被绕过）；② 标定的自证面（规则是否真先冻结、降级率口径是否被事后放宽）；
  ③ 白名单的绕行面（`derived_from` 传递闭包 / 工作流 checkpoint 引用 / 元数据残留）；
  ④ `remote_call_status` 分流是否真能把「远端腿死掉」变成可见的红。

### 7.1 承接 round 2 的定向提示（原文保留，仍有效）

- **Sentinel**：请独立复跑 `spikes/s1-determinism/run_s1.sh`、`spikes/s2-capability-cassette/run_s2.sh`、`spikes/s3-render/run_s3.sh`、`02_source/verify_specs.sh`，并**不采信**本文与 `03_spike_log.md` 的结论；重点复测：cassette miss 的 fail-closed、非法能力被拒、pack 篡改非 0 退出、`kernel-digest` 前后一致。
- **Raven**：本轮的**隐性假设**清单在 `06`（许可待核项）与 `07`（ADR 后果段的 ⚠️ 条目）；建议优先对抗：① 事件日志体积与预算（R13）② prompt injection 进能力上下文（R16）③ 「新增能力不改内核代码」是否只在**数据契约不变**的前提下成立（例如新增 slot 是否真的不用改规则层解析代码）④ cassette 规范化跨语言一致性（R17）⑤ colyseus 若引入后的双权威路径（R7）。
