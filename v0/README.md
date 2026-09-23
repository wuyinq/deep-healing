# v0 —— DeepHealing V0 垂直切片（里程碑 M1 + M2 + M3）

本目录是 V0 的**可验证交付单元**。里程碑在**同一棵树上继续生长**（不另起目录）。

## 这里有什么

```
v0/
  02_source/                      产品源（规格 + 骨架代码，150 文件）
    *.schema.json / *.spec.md     冻结契约（M3 新增 worldview.schema.json）
    07_adr.md                     架构决策记录：冻结 12 条 ADR 逐字 + ADR-13/14/15（M2）+ M3 新增
    verify_specs.sh               契约与交付面自校验（自定位，可在任意路径运行）
    manifest.txt                  02_source 下每个文件的清单（覆盖检查的判据）
    v0_skeleton/
      kernel/                     确定性内核 + 能力注册表 + 四类 provider + 规则层 + 预算 + 记忆层 + 任务演进
      districts/xingfu-xiaoqu/    幸福小区内容包（M3 新增 worldview.json：治愈内核 + 悬疑外壳两态）
      districts/xingfu-xiaoqu-north/   第二街区（M2 新增：纯数据驱动，零内核改动）
      capabilities/               原子能力声明（含 relation.infer@1.0.0）
      tools/                      校验与标定工具
      session/                    L2 会话传输层（M3：双模式权限 / 增量同步 / 意图上行；Node）
      web/                        L1 渲染层（M3：three.js，只消费快照，零业务逻辑）
      assets-sample/
  spikes/                         内核测试套件依赖的产物 + 里程碑真跑证据
    kernel-baseline/              内核源码指纹基线（实现前快照）
    s5-latency-calibration/       时间预算标定产物 + 三份冻结物
    s8-registry/ s9-rules/ s10-memory/ s11-pack2/   M2 真跑 spike（仅 V0_M2 冻结面条目）
    s12-session/ s13-render/      M3 真跑 spike（仅 V0_M3 冻结面条目：38 + 12）
  06_v0_m1_self_test.md           M1 逐 AC 判定书（内核测试会读取其中的真实调用计数）
  06_v0_m2_self_test.md           M2 逐 AC 判定书
  06_v0_m3_self_test.md           M3 逐 AC 判定书
  03_artisan_self_test.log        M1 + M2 + M3 实现自测日志
  V0_M1.sha256 / V0_M2.sha256 / V0_M3.sha256   各里程碑冻结时刻的交付面清单（**证据**，见下）
  SEED.sha256                     起点溯源（从上一里程碑播种时的聚合哈希）
```

## 怎么验证

```bash
# 1) 契约与交付面自校验
cd v0/02_source && bash verify_specs.sh --quiet
#    期望：verify_specs: OK (130 checks passed, 0 skipped)

# 2) 内核测试套件
cd v0/02_source/v0_skeleton/kernel
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider
#    期望：151 passed, 0 skipped
#    （M2 口径的 4 条 skip 已在 M3 变成真断言，不再跳过）

# 3) 会话层 / 渲染层（Node >= 22）
#    ⚠️ 依赖提升在 <工作区根>/node_modules（D-9）：02_source 内零 node_modules / 零 dist / 零 .build。
#    本目录不随仓库提供 node_modules；跑测试前请在 02_source/v0_skeleton 之上准备提升根
#    （依赖：ws ^8 / three ^0.180 / typescript ^5.6 / vite ^7 / playwright ^1.48）。
cd v0/02_source/v0_skeleton/session && npm test   # 期望：16 tests / 16 pass / 0 fail
cd v0/02_source/v0_skeleton/web     && npm test   # 期望：4 tests / 4 pass / 0 fail

# 4) 端到端：跑一次世界 → 校验日志 → 回放比对
mkdir -p /tmp/dh
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel run \
    --pack districts/xingfu-xiaoqu --seed 20260921 \
    --events /tmp/dh/e.jsonl --snapshot-every 50 --ticks 300
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel verify \
    --events /tmp/dh/e.jsonl --pack districts/xingfu-xiaoqu \
    --expected-hash "$(tail -1 /tmp/dh/e.jsonl | python3 -c 'import json,sys; print(json.load(sys.stdin)["hash"])')"
#    期望：exit 0；925 事件 / 6 检查点 / chain_tail baecca92… / state_hash 9a4ae3da…
```

> ⚠️ **`verify` 必须带 `--expected-hash`（链外锚点）。**
> 不带锚点时 `exit 0` 只证明「确定性一致」（链自洽 + 检查点与重放一致 + 事件流与重放一致），
> **不证明「日志未被篡改」**：无密钥哈希链不是真实性保证。已实测：截断日志 + 改写 `plan_ticks` +
> 重算整链 ⇒ 产出真日志的**自洽前缀**，无锚点时 `verify` 仍 `exit 0`。
> 该强度边界是**已声明**的（见 `02_source/cassette.format.md` 的 `FROZEN-CASSETTE-INTEGRITY-1`），
> 不是未知缺陷——但任何把「`verify` exit 0」读成「未被篡改」的下游结论都是错的。

## M3 落盘口径（重要，审计用）

1. **落盘范围 = `V0_M3.sha256` 冻结面**（202 条：`02_source/**` 150 + `spikes/**` 50 +
   `03_artisan_self_test.log` + `06_v0_m3_self_test.md`）。
   工作区里 `spikes/s12-session/**`（398 文件）与 `spikes/s13-render/**`（1275 文件，含真浏览器
   PNG 与 console jsonl）的**运行产物与 scratch 不在冻结面内，未随本仓库提供**——这是 M3 R4-M4
   冻结面口径修正的结果（把**可重生成的运行产物**移出哈希面，与既有 `runtime*/**`、`superseded/**` 同类），
   目的是让「任意次数真浏览器复跑之后 `shasum -c` 仍全 OK」这一硬验收成立。
   ⇒ 交付面（`02_source`）与证据面**分开报**：本仓库 `02_source` **150/150 OK**。
2. **registry P-9 迁移（跨面改动，已声明）**：`spikes/s5-latency-calibration/calibration.registry.json`
   是**派生缓存**；M3 的 P-9 把它三处 `path` 由**绝对路径改为相对路径**（M3 门禁新增断言要求 `absolute=0`，
   旧版绝对路径形态会被判红）。该文件**不在**任何里程碑冻结面内（派生缓存惯例），故落盘时在仓库内
   **就地 `registry --force-rewrite` 迁移**；迁移后 `shasum -c V0_M3.sha256` 仍是 **202 OK / 0 FAILED**。
   **幂等已复验**：迁移后连跑 `registry`（不带 flag）⇒ `rewritten=false`、**逐字节不变**（`5078be30…`）。
3. **`V0_M1.sha256` / `V0_M2.sha256` / `V0_M3.sha256` 是冻结时刻的证据，不是本仓库内的完整性检查。**
   它们覆盖当时工作区里的**全部**交付面（M1 276 条 / M2 238 条 / M3 202 条），其中一部分未随本目录提供
   （M1 的 `spikes/red/**`、`spikes/ac3-forge/**` 等负控沙箱；M2 的 scratch 目录）。
   里程碑在**同一棵树**上继续生长 ⇒ 越早的清单在本仓库里失配越多。**实测（M3 落盘后）**：
   - `V0_M3.sha256` ⇒ **202 OK / 0 FAILED**（本次落盘面，全绿）
   - `V0_M2.sha256` ⇒ **192 OK / 46 FAILED**（45 条 `02_source` 被 M3 演进 + `03_artisan_self_test.log` 追加；
     M2 落盘当时是 237 OK / 1 FAILED，那 1 条是下条所述的 `calibrate_latency.py`）
   - `V0_M1.sha256` ⇒ 95 OK / 181 FAILED / 128 缺失（含未随仓库提供的负控沙箱）

   **以上失配全部是预期行为**（见下条与「已知限制」第 2 条），不是交付面被改。
   本目录内的完整性检查是 `verify_specs.sh` 与内核测试套件。
4. **`V0_M2.sha256` 原样落盘（保持冻结真相）**：其 `02_source/v0_skeleton/kernel/tools/calibrate_latency.py`
   一条记录的是 **M2 拿到的输入** `e30be65b…`，而本仓库该文件是 **M1 后置修复版** `23fed40d…`
   （内容锚定，修掉位置耦合）——M3 未改动它。沿用 M1 先例：清单保持冻结真相，divergence 文档化。

## 已知限制（如实记录，未粉饰）

1. **标定缓存与位置耦合 —— 已修（M1 后置修复，已随本仓库生效）**：
   `spikes/s5-latency-calibration/calibration.registry.json` 是**派生缓存**，记录三个冻结文件的路径/mtime/sha256。
   原实现把「路径 + mtime」也纳入**是否重写**的判定 ⇒ 复制或克隆到新路径后首跑必改写该文件，
   `tests/test_calibrate_latency.py::test_registry_is_idempotent` **在克隆里首跑即红**（已在全新克隆中实测复现）。
   **修法**：幂等判定改为**内容锚定** —— 只比对各冻结物的 `sha256`；内容未变则**不写盘、逐字节保留**既有文件。
   修复后全新克隆 **71 passed / 10 skipped**（M1 口径），无需任何人工补救。
   *冻结清单增量（如实记录）*：`calibrate_latency.py` `e30be65b…` → `23fed40d…`。
   **M3 进一步收敛（P-9，已关闭）**：registry 内嵌的**绝对路径已全部改为相对路径**（3 → 0），
   运行时解析；旧形态可用 `registry --force-rewrite` 一次性迁移。**残留边界**：mtime 字段仍随检出漂移
   （不构成完整性判据；判据是 `verify_specs.sh` 的内容锚检查）。
2. **`local_model` provider 未真跑**：本机无本地模型服务，只有槽位设计。不冒充已跑。
3. **`embed.text` 远端结构性不可用（GAP-E1，M2 登记）**：该能力在所用通道上 `/v1/embeddings` 端点与
   目标嵌入模型均不存在（通道 19 个模型中含 embed 的 0 个）⇒ 录制态每次触发都发一次注定 404 的请求，
   `local_model` 本机无服务 ⇒ 该能力实际只剩 `deterministic_rule`。ADR-014 已把契约优先级收敛
   （`remote_api` 10→90、`cassette_replay` 20→50），`06` 已如实登记。
4. **时间预算标定判据 ③ 不可重复**（AC-M1-6 记为 GAP，M2/M3 未变，M3 已作 P-5 逐条处置）：同一份数据、
   同一批声明值、同为 `--runs 10`，相邻三次测量给出 adopted 降级率 `0.50`（越界）/ `0.20` / `0.10`；
   根因是环境抖动 **叠加** 冻结区间的口径塌缩（`ceil_to(50,p95) == ceil_to(100,p95) == 1300`，七个能力全部塌缩）。
   **未重采样、未调参、未改任何声明值。**
5. **一致性判据 ≠ 防篡改（M3 明确声明，G9）**：`scene_assert` 系列断言证明的是**场景结构一致性**，
   不是「未被篡改」。5 类**判据侧改写**（钉摘要常量 / 缓存读数 / 伪造入参记录 / 判据体自比等）**不被判据捕获**；
   判据源码本身在冻结面内（`02_source` 150/150 OK）⇒ 判据侧改写由**清单**这一独立机制发现。
   **禁止**把 `scene_assert` 读作「未被篡改」的证据。
6. **真浏览器验收证据的运行产物不入本仓库**：M3 的真浏览器验收（canvas 盒随视口、HUD 外非背景像素占比、
   双档×双态截图、console 零报错）在工作区 `spikes/s13-render/**` 与 `spikes/s12-session/**` 完整留存；
   其中**可重生成的运行产物**（PNG / `browser-accept-*.json` / `console-*.jsonl` / `*-summary.json` 等）
   按 M3 冻结面口径**移出哈希面且未随仓库提供**。⇒ 本仓库**不含**真浏览器截图证据，
   复现需按 `spikes/s13-render/browser-accept.mjs` 自行真跑（脚本与负控脚本**在**冻结面内）。
7. **M3 结转 M4 的开口项（逐条登记，禁止静默）**：判据层非覆盖 13 条中的「相机自身 `Object3D` 层状态」
   「渲染相关状态（fog/background/sortObjects/frustumCulled）」「材质层属性」「量化边界 `1e-6`」「判据取数点自命中」；
   冻结面非 f4 驱动（f5/f6/f1）产物是否出哈希面、`runtime*` 前缀过宽、被排除路径不得承载判据结论；
   `06` R3 段残留绝对措辞；链外锚（AC-M3-8③⑤ 原始运行读数外置后无独立锚）；
   桥权限自述（**一旦接网络监听即升 CRITICAL**）；`delta` 位移在读法切换时被 `rebuild(latestState)` 吃掉。
   逐条依据见 `docs/architecture/06-acceptance-record.md` 第四部分。
8. **范围**：M1 = 确定性内核可运行；M2 = 能力注册表 + 四类 provider + 规则层与预算 + 记忆层 + 第二街区内容包；
   M3 = 双模式会话层（W7）+ 渲染层与 UI（W8）+ 世界观落地。观测层（W9）、集成验收（W10）属 **M4**。

## 溯源

| 项 | 值 |
|---|---|
| 需求书 | `REQ-20260921-003`（M1）、`REQ-20260921-004`（M2）、`REQ-20260921-005`（M3，rev5）；上游 `REQ-20260921-002` 架构冻结 |
| 验收 | **M1**：有条件通过（6 PASS / 1 GAP / 1 分列均 PASS，CRITICAL 0）；**M2**：通过（8/8 AC PASS，CRITICAL 0，残留 FAIL 0）；**M3**：**通过**（逐 AC PASS，**CRITICAL 0**，残留 MEDIUM/LOW/GAP 已逐条登记 M4） |
| 冻结计划 | `docs/architecture/04-v0-plan.md`（13 工作包 / 4 里程碑 M1~M4） |
| 契约副本 | `docs/specs/` 是**架构冻结轮**的契约发布视图（冻结时刻快照，**不随里程碑同步**：M1/M2 均未改，现有 5 份与 `02_source` 已漂移）；**可自校验的源**是 `02_source/` |
| 落盘提交 | 见本目录所在仓库的提交历史（M1 / M2 / M3 各一笔提交） |
| M3 终验 | `dev_team_workspace/REQ-20260921-005-deephealing-v0-m3/08_pm_verdict.md` + `08_pm_verdict_r5.md`（工作区，不随仓库提供） |
