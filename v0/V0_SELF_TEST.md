# V0_SELF_TEST.md — V0 全量验收矩阵（AC-1 ~ AC-15，M4 收口轮）

- 计划：`REQ-20260921-006-deephealing-v0-m4`（FROZEN rev2）　里程碑：M4（W9 + W10 + W11 + W12 + 呈现面）
- 作者：**artisan**　轮次：第 1 轮　任务：`REQ-20260921-006-m4-r1`；**r2 修订**（修复轮 `REQ-20260921-006-m4-r2`）；
  **r3 修订**（补轮 `REQ-20260921-006-m4-r3`：F5′ 监听顺序前移 + F7 观察面并发上限/干净收尾 + F6 计时判据容差锚定）
- **r2 修订摘要**：AC-1/AC-M4-4 判据补强（F1/F2，登记 `C-15`）、AC-M4-11 证据面订正（F4）、
  AC-M4-9④ 监听窗口写明（F5，登记 `C-16`）；逐条明细与重取登记见 `06_v0_m4_self_test.md` §M4-r2。
- **r3 修订摘要**：AC-M4-9④ 改为**实测口径**（`run --ws-port` 运行期间外部真连入）并**取代** r2 的
  `C-16` 症状描述（登记 `C-18`）；观察面并发上限 + 封存 fail-closed（`C-19`）；计时判据容差锚定
  实测窗口（`C-20`）。逐条读数与冻结面重取登记见 `06_v0_m4_self_test.md` §M4-r3。
- 工作区：`/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-006-deephealing-v0-m4`
- 本文件是**新增**文件；每条判据给：`判定` / `命令（含 workdir）` / `实测输出` / `证据（绝对路径）` / **`自证反例`**
- 口径：**零命中不算证据**（附注入反例）；**exit=2 判红**（工具自身出错不得读成「零命中」）；不得为绿放宽判据；
  任何口径变化**逐条登记**（见 `06_v0_m4_self_test.md` §M4-C 的 C-1 ~ C-20）
- 复跑一律：`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider`

约定简写：`<ws>` = 上表工作区；`<kernel>` = `<ws>/02_source/v0_skeleton/kernel`；
`<session>` = `<ws>/02_source/v0_skeleton/session`；`<web>` = `<ws>/02_source/v0_skeleton/web`。

---

## §0 起点快照（开工核对，无漂移）

| 项 | 期望 | 实测 | 判定 |
|---|---|---|---|
| `find 02_source -type f \| wc -l` | 150 | **150** | ✅ |
| `shasum -a 256 SEED.sha256` | `34fa7f6d…7676` | **同值**（本轮字节未变） | ✅ |
| 仓库 `develop` / HEAD / dirty | `develop` / `a9e3a57` / `0` | **同值** | ✅ |
| `verify_specs.sh --quiet`（起点） | — | **OK (130 checks passed, 0 skipped)** exit 0 | ✅ |
| 内核 `pytest -q`（起点，纯净副本） | — | **151 passed** exit 0 | ✅ |
| 内容包 `districts/**` | 零字节改动 | **30/30 与仓库 `a9e3a57` 同名文件逐字节相同** | ✅ |

---

## §1 逐 AC 矩阵

### AC-1 分层架构与职责冻结 — **PASS**

- 命令（workdir `<kernel>`）：
  ```bash
  rg -n "requests|httpx|openai|urllib|socket\." deephealing_kernel/rules/*.py ; echo exit=$?
  ```
- 判据 = **两条命令**（workdir `<kernel>`；r2 起由「HTTP token 扫描」**补强**为「扫描 + 代码面」）：
  ```bash
  # ① HTTP/SDK token 静态扫描（命令行面 = `rules/*.py` glob，**不是**显式文件清单）
  rg -n "requests|httpx|openai|urllib|socket\." deephealing_kernel/rules/*.py ; echo exit=$?
  # ② 规则层全量 + 决策路径零接触 provider 层的**代码面**判据（r2 新增，登记 C-15 / §M4-r2 · F1）
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_rules_layer.py -q -p no:cacheprovider
  ```
- 实测（r2 重跑）：① `exit=1`（**零命中**）；② `7 passed`、exit 0。
  ⇒ 决策路径（L1/L2/L4）无任何网络/SDK 调用；模型调用唯一出口在
  `deephealing_kernel/providers/remote_api.py`（L3 能力层，非决策路径）。
- **自证反例（r2 口径：注入只在 `/tmp` 隔离镜像里做，不再就地改交付面再复原）**：
  三态读数全文 `<ws>/spikes/s15-autonomy/logs/ac-m4-4-three-state.txt`；门脚本
  `ac-m4-4-three-state-gate.sh`（同目录，可原样重跑）。三态实测：

  | 状态 | 注入 | ① `rg` | ② `pytest` |
  |---|---|---|---|
  | 交付面（未注入） | — | `exit=1` | `7 passed`（绿） |
  | 反例 A | `from ..providers import remote_api` + 一次引用（`decision.py:19` / `:477`） | `exit=1`（**token 扫描对项目自身 provider 是盲区**） | **`1 failed`（红）** ← r2 之前这里是 `6 passed` **假绿** |
  | 反例 B | `import urllib.request`（`decision.py:474`） | `exit=0`（真命中） | **`2 failed`（红）** |
- **扫描面口径（C1 落地；r2 订正为与盘上逐字一致）**：
  ① 命令行面 = `deephealing_kernel/rules/*.py`（**glob 通配，不是显式文件清单**），并断言 `rg` **退出码**——
  零命中=1 正常；**exit=2 判红**（不得把工具自身错误读成「零命中」）。
  ② 测试面 = `deephealing_kernel/rules/**/*.py`（`rglob` **动态枚举** + **非空断言** + 显式断言含 `decision.py`）。
  ③ 「判据面 ≠ 声称面」的修法：token 扫描看不见**项目自身**的模型出口 `providers.remote_api`
  ⇒ 补一条**代码面**判据（AST；注释与 docstring 天然不在名字面内，故 `decision.py` docstring 里的
  `providers.remote_api` 字样不会让干净树恒红）：规则层全量禁 `remote_api`/`local_model`/网络与 SDK 根，
  且**决策模块 `decision.py` 与 `providers` 包零接触**。
- 证据：`<ws>/03_artisan_self_test.log`（M4-r2 · F1 段）；
  `<kernel>/tests/test_rules_layer.py`（`_rules_layer_files()` 全量枚举 + `test_decision_path_has_no_model_seam`）

### AC-2 确定性 tick 与回放 — **PASS**

- 命令（workdir `<kernel>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_determinism_replay.py -q -p no:cacheprovider
  ```
- 实测：全绿；同一事件日志重放两次全部检查点 `state_hash` 一致；**两个非确定性负例被检出**
  （wall-clock 泄漏、set 迭代序）。
- **自证反例**：两个负例本身就是注入式反例——把 wall-clock / 无序迭代注入决策阶段 ⇒ 检测器**必须变红**
  （双向断言：干净侧必须一致、注入侧必须分歧）。注入点已随决策阶段迁移并**登记**（`06` C-1/C-2）。
- 证据：`<kernel>/tests/test_determinism_replay.py`；`<ws>/spikes/s15-autonomy/logs/determinism-baseline.json`

### AC-3 能力 provider 切换与 cassette — **PASS**

- 命令（workdir `<kernel>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_capability_registry.py -q -p no:cacheprovider
  ```
- 实测：全绿；remote→cassette→rule 三类真跑，断网回放逐字段等价。
- **自证反例**：既有负例（cassette miss / tamper / no-backfill）仍全绿——
  `tests/test_cassette_miss_cli.py`、`tests/test_cassette_tamper_cli.py`、`tests/test_cassette_no_backfill_r5.py`
  （本轮只**显式**加 `--ws-port 0`，判据语义零变化，登记 C-5）。
- 证据：`<kernel>/tests/test_capability_registry.py`；既有 `spikes/s2-*` 证据面

### AC-4 双模式权限与同步 — **PASS**

- 命令（workdir `<kernel>` / `<session>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_observe_mode_readonly.py -q -p no:cacheprovider
  cd <session> && npm test
  ```
- 实测：内核侧全绿；会话侧 `tests 21 / pass 21 / fail 0 / duration_ms 87.99` exit 0。
- **自证反例**：observe 模式上行 `E_MODE_READONLY` 负例；会话侧新增 4 条 M4 用例含反例
  （配额超限、TTL 到期回收、有界队列丢最旧 + 审计计数、桥无网络面）。
- 证据：`<session>/test/session.test.js`；`<ws>/03_artisan_self_test.log`（M4-3 V-2）

### AC-5 渲染候选真跑 — **PASS**

- 命令（workdir `<web>`）：
  ```bash
  npm run build          # ✓ built in 500ms, exit 0
  npm test               # tests 4 / pass 4 / fail 0, exit 0
  node scripts/scene_assert.mjs   # scene_assert: PASS=31 FAIL=0 / OK, exit 0
  ```
- 实测：构建 exit 0（`../../../.build/web/assets/index-CaaNx_Vu.js 491.41 kB`）；`scene_assert` **不回退**（31/31）。
- **自证反例**：`scene_assert` 的既有负例（读法切换 / 相机入参身份 / 两读窗口内 resize）保持可红。
- 证据：`<ws>/spikes/s16-liveworld/logs/{live-desktop-surface.png,live-narrow-surface.png,…}`（6 张真截图）；
  `<web>/scripts/scene_assert.mjs`

### AC-6 内容扩展机制 — **PASS**

- 命令（workdir `<kernel>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_pack_validate.py -q -p no:cacheprovider
  ```
- 实测：全绿；「复制 pack → 改 id → 重签 → validate → run，`kernel/` 零改动」成立。
- **自证反例**：本轮 `tests/test_world_clock.py` 用 `/tmp` 副本**改包**（改 `time_scale_note` 后重签）验证
  `tick0_minutes` 随之改变（实测 **510**）⇒ 证明相位确实是**派生**而非硬编码；副本目录名必须等于
  `pack.json.id`（`xingfu-xiaoqu`）否则 schema 拒绝（负例）。
- 证据：`<kernel>/tests/test_world_clock.py`；`<ws>/02_source/district.pack.spec.md`

### AC-7 认知与自进化契约 — **PASS**

- 命令（workdir `<kernel>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_capability_registry.py tests/test_budget_ledger.py -q -p no:cacheprovider
  ```
- 实测：全绿；四类高层能力经注册表；护栏契约存在且 V0 不启用改写。
- **自证反例**：`BudgetLedger` 硬顶去掉 ⇒ 用例变红（既有负例保持可红）。
- 证据：`<ws>/02_source/07_adr.md`（ADR-012 + 本轮 ADR-017）；`<kernel>/tests/test_budget_ledger.py`

### AC-8 观测回放 — **PASS**

- 命令（workdir `<ws>`）：
  ```bash
  bash spikes/s14-observability/run_observability.sh       # exit 0
  ```
- 实测：`replay --checkpoint-every 50` ⇒ 检查点 **count=6**（== 300/50，逐点 ticks `[50,100,150,200,250,300]`）；
  链自洽 `broken_links=0`、`last_seq=2519`、`events=2520`；分析查询**真跑**（4 组，逐组 `sql_equivalent` 映射）；
  时间轴 UI 读 `checkpoints/`（`replay.json`）。
- **自证反例**：
  1. 在日志里造**一处断链** ⇒ 同一自检 `broken_links=2`（判据变红）；
  2. 分析前后 `events.jsonl` 的 sha256 **不变**（只读性自证）；
  3. 检查点目录为空时**先做非空断言**（预审 M5 的处置：`compare_checkpoints` 空目录不得判「一致」）。
- 证据：`<ws>/spikes/s14-observability/logs/{observability-report.json,replay.json,broken-chain.json,events-sha-before.txt,events-sha-after.txt,replay-checkpoints.txt}`

### AC-9 ADR — **PASS**

- 命令（workdir `<ws>/02_source`）：
  ```bash
  grep -c "^## ADR-" 07_adr.md
  ```
- 实测：**17**（≥8）；本轮**追加 M4 段 + ADR-017**（事件类型枚举新增 `npc.decision`），历史段逐字未改。
- **自证反例**：ADR-017 逐字写明「`events.schema.json` **不承载** `schema_version` 顶层键」，
  版本化由 ADR + `06` 登记承载（预审 M2 的处置③）——即断言的是**实际存在的载体**，不是想当然的字段。
- 证据：`<ws>/02_source/07_adr.md`

### AC-10 成本与性能预算 — **PASS**

- 命令（workdir `<kernel>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_budget_ledger.py -q -p no:cacheprovider
  ```
- 实测：全绿；每 NPC 每日 token 三档 + 帧率 / tick / 延迟 / 内存**均有数值**；`BudgetLedger` 硬顶生效；
  本轮 `npc.decision` 的体积**已折算进预算**（1500 条 / 300 tick × 5 NPC，payload 660360 B，占全量 **84.26%**）。
- **自证反例**：去掉硬顶 ⇒ 用例变红（既有负例）；体积占比由 `observability_report.py` 独立统计
  （非自报字段）。
- 证据：`<ws>/spikes/s14-observability/logs/observability-report.json`（`event_statistics.by_type`）；
  `<ws>/spikes/s15-autonomy/logs/decision-observability.json`

### AC-11 美学与双模式信息架构 — **PASS**（主观成分如实标注）

- 命令（workdir `<ws>` / `<web>`）：
  ```bash
  node spikes/s16-liveworld/ambience_assert.mjs --logs spikes/s16-liveworld/logs --tag live
  cd <web> && node scripts/scene_assert.mjs
  ```
- 实测：`ambience_assert: PASS=21 FAIL=0` exit 0；`scene_assert: PASS=31 FAIL=0` exit 0；
  观察模式**无写入口**（真浏览器实测 `observe_panel_write_controls=[]`）。
- **取数源**（逐条 `ambience_source` 标注，**来自内容包既有段，非臆造**）：
  `districts/xingfu-xiaoqu/assets/manifest.json#aesthetic_constraints.{palette.saturation_max_pct=45, material.roughness_min=0.6, lighting.ambient_ratio_min, lighting.shadow_softness_min, audio.allowed_beds}`、
  `districts/xingfu-xiaoqu/buildings/courtyard-01.json#ambience`、
  `districts/xingfu-xiaoqu/worldview.json#tone.surface|tone.underneath`、
  `art-bible.md#§美学数值约束`。
- 真浏览器像素统计（从**真实截图解码**，HUD 矩形按 `devicePixelRatio` 剔除）：
  desktop 背景占比 0.8727 / 非背景像素 147966 / 饱和度 p95 **35.294 ≤ 45**；narrow 背景占比 0.7104 / p95 **35.294 ≤ 45**。
- **自证反例**：注入 `{roughness 0.1, metalness 0.8, specular 非空, p95 90, 非背景占比 0}` ⇒ 同一判定 **false**。
- **口径边界（如实）**：art-bible「饱和度 ≤ 45」约束的是**主色板声明**（`tools/aesthetic_check.py` 校验），
  **不是**逐像素渲染值；underneath 读法像素 p95 实测 **51.22 > 45** ⇒ 已在报告 `reading_boundary` 字段显式登记，
  判据只断言「两读法可分辨」，两个读数都写进报告（**不隐藏**）。
- 证据（r2 订正：**只列内容与 PASS 结论一致的文件**，逐条已 `cat` 核对）：
  `<ws>/spikes/s16-liveworld/logs/ambience-assert.out`（21 条检查 + 两档视口像素读数，末行 `ambience_assert: PASS=21 FAIL=0`）、
  `<ws>/spikes/s16-liveworld/logs/browser-live-live.json`（真浏览器两档视口原读数）。
  **同目录 `ambience-report.CRASH.txt` 不是证据**：它是**某次失败运行**的 stderr 崩溃栈
  （`TypeError: Cannot read properties of undefined (reading 'light_k')`），r2 已改名以免被误读为报告
  （登记 `C-17`；根因见 `06` §M4-r2 · F4）

### AC-12 参与影响任务演进 — **PASS**

- 命令（workdir `<kernel>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_task_adaptation.py -q -p no:cacheprovider
  ```
- 实测：全绿；`adaptation_rules` 数据驱动触发 `task.state_changed`，含 `max_shifts` 上限与审计。
- **基线口径变更（登记 C-3）**：旧硬断言 `state_hash == 9a4ae3da…` / `chain_tail == baecca92…`（M1/M2 口径）
  ⇒ 改为「**确定性自洽**」口径（两次独立运行逐位相同）+ **本轮新基线**作回归锚：
  `state_hash = 0d79e5f349cad67d8ebc623fb7e49a17082e0170d0b5a5c3de62715ea42a2dca`、
  `chain_tail = 81669e9685e5dec845d0d5060321c0eba66939063997941c5be5f2e0d97d8cb6`
  （原因：决策路径由班表桩切换为「需求 → 效用 → 行为树」，**预期非回归**；变更时刻 epoch 1790130629）。
  旧值以**注释存档**，历史文档段（`07_adr.md`）只**追加**说明、不改。
- **自证反例**：`test_default_run_without_intents_is_bit_identical` 改为「两次独立运行逐位相同」的双向口径；
  另用**独立 seed 的内核副本**（`other_dir`）做「不同输入必须不同」的反例。
- 证据：`<kernel>/tests/test_task_adaptation.py`；`<ws>/spikes/s15-autonomy/logs/determinism-baseline.json`；
  `06_v0_m4_self_test.md` §M4-D

### AC-13 原子能力注册与补充 — **PASS**

- 命令（workdir `<kernel>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
    "tests/test_capability_registry.py::test_new_capability_requires_no_kernel_source_change" \
    tests/test_kernel_digest.py -q -p no:cacheprovider
  ```
- 实测：**5 passed in 0.20s**，exit 0；丢入新能力文件 + adapter ⇒ 注册表发现并调用成功；
  **既有内核源码字节不变，只新增数据 + adapter**。
- **自证反例**：R26 / R12 两条强制负例保持可红（改内核源码 ⇒ 指纹判据变红）。
- 证据：`<kernel>/tests/test_kernel_digest.py`；既有 `spikes/s2-*` 同口径证据

### AC-14 世界模型适配器 — **PASS**

- 命令（workdir `<ws>/02_source` / `<kernel>`）：
  ```bash
  bash verify_specs.sh --quiet          # 其中的 REQUIRED_FILES 含 worldmodel.adapter.spec.md
                                        #   与 v0_skeleton/kernel/deephealing_kernel/adapters/{__init__.py,determinism_probe.py}
  cd <kernel> && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
    tests/test_kernel_digest.py::test_providers_adapters_dir_is_an_authorized_adapter_face -q -p no:cacheprovider
  ```
- 实测：契约检查全绿（130 checks，含上述必需文件存在性）；适配器面用例 **1 passed in 0.03s**（exit 0）；
  V0 只交付**适配器接口与占位实现**（`deephealing_kernel/adapters/`），**运行时零世界模型调用**。
- **自证反例**：AC-1 的静态扫描（`rules/*.py` 零命中 + 注入 `urllib.request` 真命中）+ 本用例的
  「适配器目录是**被授权的**适配器面」判据 ⇒ 静态面与授权面双向；运行时零调用由 AC-4/AC-8 的真跑读数旁证。
- 证据：`<ws>/02_source/worldmodel.adapter.spec.md`；
  `<kernel>/deephealing_kernel/adapters/{__init__.py,determinism_probe.py}`；`<kernel>/tests/test_kernel_digest.py`

### AC-15 资产非量产 — **PASS**

- 命令（workdir `<ws>/02_source`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/aesthetic_check.py "v0_skeleton/districts/xingfu-xiaoqu/assets/manifest.json"
  # → aesthetic_check: OK (5 assets)                                          exit 0
  PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/verify_asset_pack.py \
    --pack v0_skeleton/assets-sample --manifest v0_skeleton/assets-sample/asset.manifest.sample.json \
    --license-table asset.license.table.data.json --runtime-tree v0_skeleton
  # → asset pack verify: assets=1 files=2 rejects=0                           exit 0
  ```
- 实测：两条 exit 0；示例过 schema；**内容包 `districts/**` 零字节改动**
  （30/30 与仓库 `a9e3a57` 的同名文件逐字节相同）；`verify_specs.sh` 的 #8/#10/#11 三项覆盖
  （美学数值 / 资产包 + 运行时零生成 / 许可枚举一致性）全绿。
- **自证反例**：`aesthetic_check.py` 非 0 即拒（数值越限 ⇒ 变红）；`verify_asset_pack.py` 的 `rejects`
  计数与 `--runtime-tree` 的零生成扫描都带拒绝路径；本轮 `ambience_assert` 另加注入反例（见 AC-11）。
- 证据：`<ws>/03_artisan_self_test.log`（M4-0 的内容包核对）；
  `<ws>/02_source/v0_skeleton/tools/{aesthetic_check.py,verify_asset_pack.py}`；`/tmp/m4_aesth.txt`、`/tmp/m4_assetpack.txt`

---

## §2 M4 增量 AC（AC-M4-1 ~ AC-M4-11）

| AC | 判定 | 一句话结论 | 证据 |
|---|---|---|---|
| AC-M4-1 契约全绿 + 三轮不回退 | **PASS** | `verify_specs: OK (130 checks passed, 0 skipped)` exit 0 | `06` §M4-B |
| AC-M4-2 观测层（W9） | **PASS** | 检查点 6 == 300/50；`broken_links=0`；造断链 ⇒ 2；只读 | `spikes/s14-observability/logs/*` |
| AC-M4-3 成本与性能预算 | **PASS** | 三档 token / 帧率 / tick / 延迟 / 内存均有数值；`npc.decision` 体积已折算 | `spikes/s14-observability/logs/observability-report.json` |
| AC-M4-4 分层 + 决策路径零模型 | **PASS** | `rg` `rules/*.py` 零命中（exit=1）+ `pytest tests/test_rules_layer.py` **7 passed**（exit 0）；反例 A `providers.remote_api` 注入 ⇒ **红**（r2 前为 `6 passed` 假绿）、反例 B `urllib` ⇒ 红 | `03` M4-r2 · F1 段；`spikes/s15-autonomy/logs/ac-m4-4-three-state.txt` |
| AC-M4-5 全量证据矩阵 | **PASS** | 本文件 AC-1..AC-15 每条含命令 + 实测 + 证据 + 自证反例 | 本文件 |
| AC-M4-6 端到端一键验收 | **PASS** | verify_specs → pytest → npm test → run → verify(--expected-hash) → replay → validate → 观测 → 实时通道，逐环 exit 0 | `spikes/*/logs/*` |
| AC-M4-7 真实仓库零改动 + 起点溯源 | **PASS** | `develop` / `a9e3a57` / dirty=0；`SEED.sha256` = `34fa7f6d…`（字节未变） | 本文件 §0 |
| AC-M4-8 自主决策（W11）①~⑥ | **PASS** | 1200 条 `npc.decision`；10 条证据窗口（最小间距 0.0604 > 0.05）；独立复算一致；退回桩 ⇒ 0 条 | `spikes/s15-autonomy/logs/*` |
| AC-M4-9 活的世界（W12）①~⑦ | **PASS** | 观察者 0 时 tick 仍增长；②a 偏差 0 分钟；②b 跨 300.056s 误差 0.0556 ≤ 1；④ **`run --ws-port <n>` 运行期间外部真连入 22912 次、响应首行 `HTTP/1.1 200 OK`**（r3 顺序前移后重取；判据含 `--ws-port 0` 负向对照 0/57846）；Host 403 / 405 / 503；恢复 `state_hash` 逐位相同 | `spikes/s16-liveworld/logs/m4-r3-wsport-probe.py`；`03` M4-r3 · F5′ 段 |
| AC-M4-10 实时观察 = 此刻 ①~④ | **PASS** | 世界 tick 102 == 通道 tick 102（墙上钟 10:40:33）；重连后 51 > 1；回放型对照 ⇒ 判据变红 | `<kernel>/tests/test_live_observation.py` |
| AC-M4-11 呈现面升级 ①~⑤ | **PASS**（⑤ 主观成分已标注） | 真 Chromium 两档视口 6 张截图、console 4/0/0/0；观察窗连入 233 → reload 238；氛围 21/21 | `spikes/s16-liveworld/logs/*` |

> **AC-M4-9② 的口径拆分（登记 C-4）**：②a 锚定精度（≤1 分钟）/ ②b 节流精度（跨 ≥300 真实秒 |Δ|≤1）/
> ②c **如实披露**原始钟面偏差（+295 分钟，**非判据**）。REQ 的 ②③ 在「1 tick = 1 世界分钟 × 1 tick/真实秒」下算术互斥。
>
> **AC-M4-9④ 的实测口径（登记 C-16 → **r3 由 C-18 取代**）**：`run --ws-port <n>` 的监听**确实会建立**，
> 但旧实现里它排在整轮 tick **之后** ⇒ 真子进程下外部可连窗口 **≈ 22µs（不可观测）**，
> 而 `run` 自报 `"listening": true` 并被 ④ 当证据引用。**问题不是「没监听」，是「声明了一个外部
> 无法观测的窗口，却把它当可用观察面」**。**r3 已把监听前移到 tick 循环之前**（实现自己已冻结的
> 设计 D-M4-4「显式给端口时真的监听并服务同一只读端点」，不是改契约）⇒ ④ 现在是**实测口径**：
> 运行期间外部真连入并读到 `HTTP/1.1 200 OK`（含 `--ws-port 0` 负向对照）。逐条读数见 `06` §M4-r3 · F5′。
> **取代声明**：本条取代 `06_v0_m4_self_test.md` §M4-r2 · r2-4 与 `C-16` 行里对监听窗口的
> **症状式描述**（把可连窗口说成只落在进程收尾；那是根因未定位时的近似，**不是结论**），
> 理由 = **根因已定位（启动顺序）并已修**。
> **r2 的历史读数（保留为 RED 证据，**不再是当前口径**）**：`run --ticks 3000 --ws-port` 全程 5ms 轮询
> **79 次 0 次连入**、自报 `live_channel.listening=true`、进程退出后 `ConnectionRefusedError`；
> `run` 确实真去 bind（自建 listener 占住端口 ⇒ `E_ADDRINUSE` exit 1）。读数见 `03` M4-r2 · F5 段。
> **r3 复现与关闭**：修前树（`/tmp/m4r3-prefix` 副本）同一判据 **0 次连入 / 64346 次 refused**；
> 修后树 **22912 次连入 / 首行 `HTTP/1.1 200 OK`**；负向对照（`--ws-port 0`）**0 / 57846**。
> 一条命令复跑：`python3 spikes/s16-liveworld/logs/m4-r3-wsport-probe.py`（exit 0 = PASS）。

---

## §3 端到端一键验收（AC-M4-6）逐环读数

| 环 | 命令（workdir） | exit | 关键读数 |
|---|---|---|---|
| 1 契约 | `bash verify_specs.sh --quiet`（`<ws>/02_source`） | 0 | `OK (130 checks passed, 0 skipped)` |
| 2 内核全量 | `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider`（`<kernel>`） | 0 | 见 §4 |
| 3 会话层 | `npm test`（`<session>`） | 0 | tests 21 / pass 21 / fail 0 |
| 4 呈现层 | `npm run build` + `npm test` + `node scripts/scene_assert.mjs`（`<web>`） | 0 | built in 500ms / 4 pass / `PASS=31 FAIL=0` |
| 5 运行 | `python3 -m deephealing_kernel run --ws-port 0 --pack ../districts/xingfu-xiaoqu …`（`<kernel>`） | 0 | 300 tick，事件 2520 条，`chain_tail` 已记 |
| 6 验证 | `python3 -m deephealing_kernel verify --pack ../districts/xingfu-xiaoqu --events <run/events.jsonl> --expected-hash 81669e96…8cb6`（`<kernel>`） | 0 | `verify: OK (chain self-consistent; per-checkpoint state_hash/rng_state_digest/event_chain_hash agree; INVARIANT-ECH-1/2/3 hold; event stream matches replay)`；`event_stream_divergences=0`；`snapshots=6` |
| 7 回放 | `replay --checkpoint-every 50`（`<kernel>`） | 0 | 检查点 6 == 300/50 |
| 8 观测 | `python3 tools/observability_report.py`（`<kernel>`） | 0 | `broken_links=0`；4 组查询真跑 |
| 9 实时通道 | `node spikes/s16-liveworld/browser-accept-live.mjs`（`<ws>`） | 0 | 两档视口 6 张截图；console 4/0/0/0 |

**端到端链路上的一条真实红灯（已根因定位并修复，登记 C-13）**：第 2 环首轮跑出
`1 failed, 186 passed in 2155.60s`——`tests/test_e2e_run_verify.py::test_verify_detects_truncated_log`
的夹具前提失效（M4 起**每 tick 事件数 4 → 9**，删 6 行不再跨过 tick 边界 ⇒ `truncated log` 分支不可达；
**产品侧截断检测未退化**：event-stream 比较先报出 6 处 `missing_in_log`，exit 1 不变）。
已按「**改夹具、不改判据**」修复并**新增前提断言** `max_tick(kept) < plan_ticks` 防再次静默退化；
复验 `tests/test_e2e_run_verify.py` ⇒ **15 passed in 14.57s** exit 0。
根因隔离读数（截断 6/8/12/20/40 行对照）见 `06_v0_m4_self_test.md` §M4-E.7。

---

## §4 全量内核 pytest（W10 的主读数）

- 命令（workdir `<kernel>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
  ```
- 实测（**两轮，如实记录**）：
  - **首轮**：`1 failed, 186 passed in 2155.60s (0:35:55)`，exit=1 —— 失败用例
    `tests/test_e2e_run_verify.py::test_verify_detects_truncated_log`（夹具前提失效，**非产品缺陷**；
    根因隔离 + 修复见 §3 的红灯说明与 `06` §M4-E.7，登记 C-13）
  - **修复后复跑**：**`187 passed in 2052.06s (0:34:12)`，exit=0** ✅
- 对照起点：纯净副本（`a9e3a57`）**151 passed** ⇒ 本轮新增 **4** 个测试文件、净增 **36** 条用例，全绿。
- 证据：`/tmp/m4_full_pytest.txt`（首轮红）、`/tmp/m4_full_pytest2.txt`（复跑绿）；
  `<ws>/03_artisan_self_test.log`（M4-3 V-1 / M4-13）

---

## §5 已知 GAP（如实，不掩盖）

| # | GAP | 原因 | 替代证据 | 归属 |
|---|---|---|---|---|
| G-1 | AC-M1-6 标定判据③**不可重复** | 环境/标定不可复现（M1 起 GAP） | 不重采样、不调参、不改口径；依赖该值的结论写明不确定性 | Q1 |
| G-2 | **duckdb 未真跑** | 本机无 CLI 也无 python 模块；`pip install --no-index duckdb` ⇒ `No matching distribution`（离线失败） | `observability_report.py` **同语义**实现 + 逐组 `sql_equivalent` 映射；`duckdb-cli.txt` / `duckdb-pip-install.txt` 存档 | artisan 已处置；PM 备案 |
| G-3 | `06-acceptance-record.md §20` / `R3-RAV-M1` **原文不在本工作区** | 文件缺失（预审 G1/G2 已 `grep` 零命中实证） | 以 `refs/m3-delivered/06_v0_m3_self_test.md` 的 R3-H 原文为处置依据 | PM 补原文 |
| G-4 | 「治愈系氛围达成」 | 主观 | 判据只判**数值面**（取数源 + 像素统计），显式声明 `subjective_residual` | 产品 |
| G-5 | `--allow-remote` 打开后**无鉴权** | 需 PM 授权才加 token | 只读、无写面；默认 loopback；启动横幅与 `/live/meta` 都打印 `bind_policy.warning` | PM 裁决 |
| G-6 | 恢复后**事件链不连续** | `plan_ticks` 写在首条 `world.init`（根因已隔离） | `state_hash` 逐位相同是判据；链尾差异**逐字段归因**为边界（登记 C-12） | 已登记 |
| G-7 | **行为多样性弱点** | `safety` 只被 `flee` 缓解 ⇒ 压力饱和 ⇒ 主导 95.2%、分支退化 `restore` 95.2% | 判据（间距 > 0.05、独立复算、退回桩变红）仍全绿 | architect/PM 裁决是否标定 |
| G-8 | `test_verify_detects_truncated_log` **夹具前提失效**（首轮全量 1 failed） | M4 起每 tick 事件数 4 → **9** ⇒ 删 6 行不再跨过 tick 边界，`truncated log` 分支不可达（**检测未退化**：event-stream 比较仍报 6 处分歧，exit 1） | **已修复**：夹具改删 12 行 + **新增前提断言** `max_tick(kept) < plan_ticks`；复验 `15 passed in 14.57s`；登记 C-13 | 已处置（备案） |

---

## §6 冻结面 `V0_M4.sha256`（本轮新建）

- 生成：`PYTHONDONTWRITEBYTECODE=1 python3 V0_M4.gen.py`（workdir `<ws>`）⇒ `files=197`（exit 0）
- 自检：`shasum -a 256 -c V0_M4.sha256 | grep -c 'OK$'` ⇒ **197**（exit 0）；重生成 `cmp` **逐字节相同**（幂等）
- 采集面 / 排除项：在文件头部**显式声明**（镜像 `V0_M3.sha256` 的口径）
- 覆盖核对：`02_source` 条目 **160 == `find 02_source -type f | wc -l` 的 160**（`comm -13` 输出为空）
- **自审发现并已修正的一条**（登记 C-14 / `06` §M4-E.8）：首版把运行产物排除模式（`*.png` 等）
  无条件套到全树 ⇒ 误排除 `02_source/v0_skeleton/assets-sample/placeholder-001.png`（**交付的占位资产**）
  ⇒ 条目数 159 < 160。已改为**路径感知**（运行产物模式**只在 `spikes/**` 下生效**）。严重级 **MEDIUM**。
- **声明（沿用 R5-RAV-M3）**：**被排除路径不得承载判据性结论**；判据性读数一律落在面内文件里。

---

## §7 声明

- 本文件是 **artisan 自验（V0）**，**不是**独立审查。Sentinel 的功能测试结论与 Raven 的风险推演结论由对应角色出。
- 本文件所有读数均为**真实命令**产出（含 workdir 与 exit），未使用任何伪造或「零命中绿命令」。
- 每条门禁均带**自证反例**（隔离执行，不污染交付面）。
- 任何判据口径变化逐条登记于 `06_v0_m4_self_test.md` §M4-C（C-1 ~ C-12）。
