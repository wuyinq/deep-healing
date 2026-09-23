# 06_v0_m4_self_test.md — M4（V0 收口轮）自测与验收记录

- 计划：`REQ-20260921-006-deephealing-v0-m4`（FROZEN rev2）　里程碑：**M4 = W9 观测层 + W10 全量验收 + W11 自主决策 + W12 活的世界 + 呈现面**
- 作者：**artisan**（本轮唯一产品写入者）　轮次：第 1 轮
- 权威输入：`01_m4_design.md`（**§11/§12 优先于 §2~§7**）、`REQ-20260921-006-deephealing-v0-m4.md` rev2、`.round1-constraint.txt`
- 本文件是**新增**文件（交付路径初始为空；`03` 以 `refs/m3-delivered/03_artisan_self_test.log` 为起点追加 M4 段，历史段未丢）

---

## §M4-0 起点快照核对（开工第一件事，实测）

| 项 | 期望 | 实测 | 判定 |
|---|---|---|---|
| `find 02_source -type f \| wc -l` | 150 | **150** | ✅ 无漂移 |
| `shasum -a 256 SEED.sha256` | `34fa7f6d252bc4bf966c8dbc4d639a1f08788ed71b9cfa04a0896ca7ba8f7676` | **同值**（文件本轮**零改动**） | ✅ |
| 真实仓库 `/Users/wooyinq/personal/deep-healing` | `develop` / `a9e3a57` / `porcelain=0` | **`develop` / `a9e3a57` / `0`** | ✅ 只读，零写入 |
| `bash 02_source/verify_specs.sh --quiet`（起点） | — | **`OK (130 checks passed, 0 skipped)` exit 0** | ✅ 起点读数 |
| 内核 `pytest -q`（起点） | — | **`151 passed`，exit 0**（时长 1076.99s） | ✅ 起点读数 |
| 内容包 `districts/**` | 零字节改动 | **30 个文件 sha256 逐字节等于 `a9e3a57` 的 `v0/02_source` 同名文件** | ✅ |

> **起点内核 pytest 读数的取数方式（如实说明）**：首轮基线运行期间本轮编辑已开始落盘（子进程类用例会读**当时**的盘），
> 读数被污染（`28 failed`）⇒ **弃用该读数**，改用 `/tmp` 上的 **`a9e3a57` 纯净副本**
> （`cp -R <repo>/v0/{02_source,spikes,06_v0_m1..m3,SEED.sha256,V0_M*.sha256}` ⇒ `/tmp/m4base_v0_*`）重取：
> `151 passed`。命令与副本路径见 `03` M4 段。**该副本只读仓库，未对仓库做任何写入。**

**结论（沿用设计 §0 的两条）**：① `SEED.sha256` 是**起点溯源**文件（本轮字节不变）；本轮自己的冻结面是新建的 `V0_M4.sha256`。
② 内容包**零改动** ⇒ 所有新增语义都从既有内容包数据**派生**。

---

## §M4-A Raven 方案预审处置表（C1/C2/C3 + 13 MEDIUM + 5 LOW + 3 GAP）

> 预审产物：`.raven_prereview-m4.md`（373 行）。处置**逐条**如下（与设计 §11.1 一致；**CRITICAL 三条先处置再编码**）。

| 预审条目 | 级别 | 处置 | 落点 | 落地状态 |
|---|---|---|---|---|
| **C1** 静态检查扫描面不含 `rules/` 包（零命中假绿） | CRITICAL | **采纳** | D-M4-12 | ⚠️ **r1 的「已落地」声称不实，r2 已订正并真正落地**：<br>① r1 原文称「扫描面改**显式文件清单**（`printf` + `find`）」且「`test_rules_layer.py` 清单改 `rules/**/*.py` 全量 + 非空断言」——**盘上两条都不成立**（命令行面实际是 `rules/*.py` **glob 通配**；测试清单实际是 3 个硬编码文件名，**不含 `decision.py`**）。<br>② **r2 实测的残留缺陷**：把 `from ..providers import remote_api` + 一次引用注入 `rules/decision.py` ⇒ `rg` 仍 `exit=1`、`pytest tests/test_rules_layer.py` 仍 `6 passed`（**双假绿**）。<br>③ **r2 落地**：测试清单改 `rglob` **动态全量** + **非空断言** + 显式断言含 `decision.py`；新增**代码面**判据 `test_decision_path_has_no_model_seam`（AST，注释/docstring 天然不在名字面内）⇒ 规则层全量禁 `remote_api`/`local_model`/网络与 SDK 根，且决策模块与 `providers` 包零接触（登记 **C-15**）。<br>④ **r2 三态实测**：交付面干净 `7 passed`（exit 0）/ 反例 A `remote_api` 注入 **红**（`decision.py:19`,`:477`）/ 反例 B `urllib` 注入 **红**（`decision.py:474`）；门脚本 `spikes/s15-autonomy/logs/ac-m4-4-three-state-gate.sh` + 读数 `ac-m4-4-three-state.txt` |
| **C2** AC-M4-9②③ 算术互斥 | CRITICAL | **采纳 + 裁决口径（②a/②b/②c 拆分 + deadline 锚定 + 如实披露原始量）** | D-M4-13 | ✅ **已落地**（含口径变更登记，见 §M4-C）；**上抛 PM** 见 §M4-H |
| **C3** `run --ws-port` 默认开监听 / 生命周期未定义 / 与桥声明冲突 | CRITICAL | **采纳** | D-M4-4 / D-M4-14 | ✅ **已落地**：默认改 **0**、`live --port` 默认 **8899**、`--ws-port` 别名、端口被占 ⇒ `E_ADDRINUSE` exit 1、全树字面 `NOT listened on` **零命中**、桥同步处置、既有用例适配清单见 §M4-C |
| M1（P-1..P-9 缺席） | MEDIUM | **采纳** | §12.1 | ✅ 见 §M4-F.1 |
| M2（`npc.decision` 与冻结枚举/ADR 冲突） | MEDIUM | **采纳** | D-M4-2 | ✅ 枚举追加成员 + **ADR-017** + `schema_version` 载体口径登记（见 §M4-E.3） |
| M3（`npc.decision` 证据字段被钉常量） | MEDIUM | **采纳** | D-M4-15 | ✅ 独立复算判据（重算 utility/branch/dominant_need 与事件值逐字段一致）+ 行为可分辨性（间距 > 0.05） |
| M4（负例形态必然 TypeError） | MEDIUM | **采纳** | D-M4-1 | ✅ 负例走 `decision_source="deterministic_stub"` 构造参数；另补「注入点仍有效」对抗用例 |
| M5（`compare_checkpoints` 空目录判一致） | MEDIUM | **采纳** | D-M4-15① | ✅ 比较前**非空断言** + 期望点数写死（`test_observability.py`） |
| M6（`pack_profiles` 不存在于 `WorldKernel`） | MEDIUM | **采纳** | D-M4-15⑥ | ✅ 新增构造参数，**单一权威 = `pack.npcs`**（`tick.build_pack_profiles`），登记构造面变更 |
| M7（世界钟相位来自散文 + `day_ticks` 双声明） | MEDIUM | **采纳** | D-M4-3 | ✅ 一致性断言 + `grep "420" world_clock.py live.py` 零命中（含可达性对照）+ 改包反例（`/tmp` 副本重签 ⇒ `tick0_minutes == 510`）+ 区分 600:1 与 1× |
| M8（节流无 deadline 锚定） | MEDIUM | **采纳** | D-M4-13 | ✅ `next = start + n*pace` + `sleep(max(0, next-now))` + 输出 `max_drift_ms` |
| M9（`--allow-remote` 越权面：Host/CORS/并发/超时） | MEDIUM | **采纳** | D-M4-16 | ✅ Host 校验 403 / **不设** ACAO / `nosniff` / 并发上限 503（+1 反例）/ 连接写超时 / 404·405 不回吐异常原文 |
| M10（桥仍声明「接受但不监听」） | MEDIUM | **采纳** | D-M4-4 | ✅ 全树字面零命中 + 字段改名为 `ws_port` / `bridge_serves_network: false` |
| M11（「独立于观察者」只有自报字段） | MEDIUM | **采纳** | D-M4-15⑤ | ✅ 「0 个 vs 2 个观察者」同窗口对照 + 连接数由**测试进程自记账** |
| M12（`manifest.txt` 谓词未钉死） | MEDIUM | **采纳（命令形态就地更正，见 §M4-E.2）** | D-M4-19 | ✅ 谓词输出**恰好一行 `manifest.txt`**（含更正说明与字面命令读数） |
| M13（AC-M4-8② 无阈值；+0.05 翻转窗口） | MEDIUM | **采纳** | D-M4-20 | ✅ 证据必须附 `utility_score` 间距且 **> 0.05**（实测最小间距见 §M4-B AC-M4-8） |
| L1（`behaviour_tree.tick` 与模块 `tick` 同名） | LOW | **采纳** | D-M4-22 | ✅ `decision.py` 用 `from . import behaviour_tree as bt`；无 `from .behaviour_tree import tick` |
| L2（两可措辞） | LOW | **已关闭** | §2 | ✅ D-M4-2 就地改为已判定事实 |
| L3（`npc.decision` 体积/预算耦合未评估） | LOW | **采纳** | D-M4-21 | ✅ 全量事件 + 体积折算进预算（见 §M4-B AC-M4-3） |
| L4（§5.3 与 §4.1 互相打脸） | LOW | **已关闭** | §5.3 | ✅ 就地更正为「抽取次数不恒定、确定性靠两次运行逐位相同」 |
| L5（`live --port` 默认未给） | LOW | **已关闭** | D-M4-4 | ✅ 默认 8899 |
| G1/G2（`R3-RAV-M1` / 「13 条非覆盖」原文不在工作区） | GAP | **如实登记 + 替代口径** | §12.2 / §M4-H | ✅ 见 §M4-E.4（原文缺失，上抛 PM） |
| G3（`live`/SSE/真浏览器预审无法实测） | GAP | 属实现门禁 ⇒ 由 Sentinel/Raven 实现后覆盖 | §6.2/§6.3 | ✅ 本轮已实现并给出实测（§M4-B AC-M4-9/10/11） |

---

## §M4-B 逐 AC 判定（M4 增量）

> 完整 `AC-1 ~ AC-15` 矩阵在 **`V0_SELF_TEST.md`**（每条带命令 + 实测 + 证据路径 + **自证反例**）。

| AC | 判定 | 命令（workdir） | 实测输出 | 证据（绝对路径） |
|---|---|---|---|---|
| **AC-M4-1** 契约全绿 + 三轮判据不回退 | **PASS** | `bash verify_specs.sh --quiet`（`<ws>/02_source`）+ `pytest -q -p no:cacheprovider`（`kernel`） | `verify_specs: OK (130 checks passed, 0 skipped)` exit 0；内核全量 **187 passed in 2052.06s**，exit 0（首轮 `1 failed` 已根因定位并修复，见 §M4-E.7） | `<ws>/V0_SELF_TEST.md` AC-M4-1 行；`/tmp/m4_verify_specs2.txt`、`/tmp/m4_full_pytest2.txt` |
| **AC-M4-2** 观测层 | **PASS** | `replay --checkpoint-every 50` + `tools/observability_report.py`（`kernel`） | 检查点 **6 == 300/50**；`broken_links=0`；造断链后 `broken_links=2`；分析前后 `events.jsonl` sha256 不变 | `<ws>/spikes/s14-observability/logs/{replay.json,observability-report.json,broken-chain.json,events-sha-{before,after}.txt}` |
| **AC-M4-3** 成本与性能预算 | **PASS** | `pytest tests/test_budget_ledger.py -q -p no:cacheprovider`（`kernel`） | 全绿；三档 token / 帧率 / tick / 延迟 / 内存**有数值**；`npc.decision` 体积已折算（1200 条 / 240 tick × 5 NPC） | `<ws>/spikes/s15-autonomy/logs/decision-observability.json`；`V0_SELF_TEST.md` AC-M4-3 行 |
| **AC-M4-4** 分层 + 决策路径零模型 | **PASS** | ① `rg -n "requests\|httpx\|openai\|urllib\|socket\." deephealing_kernel/rules/*.py ; echo exit=$?`（命令行面 = `rules/*.py` **glob 通配**，**不是**显式文件清单）；② `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_rules_layer.py -q -p no:cacheprovider`（`kernel`；r2 起含**代码面**判据） | ① 零命中 ⇒ `exit=1`；② **7 passed**、exit 0。**注入反例（r2 口径：只在 `/tmp` 隔离镜像里注入，不在交付面就地改再复原）**：`from ..providers import remote_api` + 一次引用 ⇒ ② **`1 failed`（红）**（r2 前为 `6 passed` **假绿**）；`import urllib.request` ⇒ ① `exit=0`（真命中）+ ② **`2 failed`（红）** | `V0_SELF_TEST.md` AC-1 / AC-M4-4 行；`spikes/s15-autonomy/logs/ac-m4-4-three-state.txt` |
| **AC-M4-5** 全量证据矩阵 | **PASS** | 读盘核对 `V0_SELF_TEST.md` | AC-1..AC-15 每条含 `判定/命令/实测/证据路径` + 自证反例 | `<ws>/V0_SELF_TEST.md` |
| **AC-M4-6** 端到端一键验收 | **PASS** | `verify_specs.sh` + `pytest -q` + `npm test`(session/web) + `run→verify(--expected-hash)→replay→validate→观测查询→实时通道` | 见 `V0_SELF_TEST.md` AC-M4-6 行的逐环读数 | `<ws>/spikes/{s14-observability,s16-liveworld}/logs/*` |
| **AC-M4-7** 真实仓库零改动 + 起点溯源 | **PASS** | `git -C /Users/wooyinq/personal/deep-healing rev-parse --abbrev-ref HEAD && … --short HEAD && git status --porcelain \| wc -l`；`shasum -a 256 <ws>/SEED.sha256` | `develop` / `a9e3a57` / `0`；`34fa7f6d…` | §M4-0；`V0_SELF_TEST.md` §起点 |
| **AC-M4-8** 自主决策（W11）①~⑥ | **PASS** | `pytest tests/test_autonomous_decision.py -q -p no:cacheprovider -s`（`kernel`） | `7 passed`；① 240 tick × 5 NPC = **1200** 条 `npc.decision`；② **10 条证据窗口**（每条「班表说 X / 它选了 Y / 因为需求 Z / 分支 B / 间距」，最小间距 **0.0604 > 0.05**）；③ 两次运行 `state_hash`/`chain_tail` 逐位相同；④ 退回桩 ⇒ 决策事件 **0** 条、动作面退化为 `{hold, move}`；⑤ 静态检查见 AC-M4-4；⑥ 基线登记见 §M4-D | `<ws>/spikes/s15-autonomy/logs/{decision-observability,behaviour-discriminability,determinism-baseline,negative-stub}.json`；`<ws>/02_source/v0_skeleton/kernel/tests/test_autonomous_decision.py` |
| **AC-M4-9** 活的世界（W12）①~⑦ | **PASS**（②c 为**披露项**，非判据） | `pytest tests/test_world_clock.py tests/test_live_observation.py -q -p no:cacheprovider -s`（`kernel`）；`python3 spikes/s16-liveworld/measure_live.py` | ① 断开所有观察者后 `observers=0` 且 tick 增长（三读数）；②a 锚定差 **0 分钟**；②b 跨 **300.0 真实秒** `\|tick 增量 − 真实秒\| ≤ 1`；②c 原始偏差 **+295 分钟**（**属预期**，已披露）；③ 60 真实秒 ⇒ tick 增量 60；④ `live --port` 真监听（原始 socket 连上并收到 HTTP 200）；⑤ 去节流 ⇒ 判据红；⑥ Host 403 / 无 ACAO / 405 拒写 / 无 secrets；⑦ 停止→恢复 `state_hash` 逐位相同；**④ 口径（登记 C-18，取代 C-16）**：`run --ws-port <n>` **运行期间外部真连入 22912 次、响应首行 `HTTP/1.1 200 OK`**（r3 把监听前移到 tick 循环之前后重取；负向对照 `--ws-port 0` ⇒ 0/57846） | `<ws>/spikes/s16-liveworld/logs/*.json`；`<ws>/spikes/s16-liveworld/runtime/kernel-live/live_state.json` |
| **AC-M4-10** 实时观察 = 此刻 ①~④ | **PASS** | `pytest tests/test_live_observation.py -q -p no:cacheprovider -s`（`kernel`） | ① 三方读数：世界 tick **102** / 通道 tick **102** / 墙上钟 10:40:33；② 重连后 tick **51 > 1**；③ 通道读数 == 内核直读（逐字段，且改内核状态后读数随之变）；④ 回放型通道对照 tick **0** vs 世界 **101** ⇒ ① 判据**变红** | `<ws>/02_source/v0_skeleton/kernel/tests/test_live_observation.py`；`<ws>/spikes/s16-liveworld/logs/browser-live-live.json` |
| **AC-M4-11** 呈现面升级 ①~⑤ | **PASS**（⑤ 的**主观成分**如实标注） | `node spikes/s16-liveworld/browser-accept-live.mjs` + `node spikes/s16-liveworld/ambience_assert.mjs` + `node scripts/scene_assert.mjs` | ① 真 Chromium **两档视口**（1440×900 / 390×844）**6 张截图**；console **实测 4 条 warning / 0 error / 0 pageerror / 0 bad response**（原始输出见 `console-live.jsonl`）；② `scene_assert: PASS=31 FAIL=0`（不回退）；③ 观察窗接实时通道：连入 tick 233 / 世界钟 10:53 / 墙上钟 10:49，reload 后 **238**（仍当前）；④ 氛围判据 `PASS=19 FAIL=0`（**取数源 = 内容包 `ambience` / `aesthetic_constraints` 段**，逐条 `ambience_source` 标注 + 注入反例变红）；⑤ 主观残余如实标注 | `<ws>/spikes/s16-liveworld/logs/{live-desktop-*.png,live-narrow-*.png,console-live.jsonl,browser-live-live.json,ambience-assert.out}` |

---

## §M4-C 判据变更登记（**任何口径变化逐条登记；不得静默**）

| # | 变更 | 旧口径 | 新口径 | 原因 | 登记位置 |
|---|---|---|---|---|---|
| C-1 | `tests/test_determinism_replay.py` **注入点迁移** | `tick_mod.stub_decide`（2 处） | `tick_mod.autonomous_decide`（2 处，包装函数增 `pack_profiles` 关键字） | 决策阶段唯一入口迁移（D-M4-1） | 本表；`03` M4 段；测试文件内注释 |
| C-2 | 同上：**意图不变** | 把非确定性注入决策阶段 ⇒ 检测器必须变红 | **同**（保持双向断言：干净侧必须一致、注入侧必须分歧） | 判据**机制**不回退 | 同上 |
| C-3 | `tests/test_task_adaptation.py` **基线硬断言改写** | `state_hash == 9a4ae3da…` / `chain_tail == baecca92…`（硬断言） | 「**确定性自洽**」口径（两次独立运行逐位相同）+ **本轮新基线**作回归锚；旧值以注释存档 | REQ AC-M4-8⑥ 明令；决策路径切换必然改基线 | 本表；`V0_SELF_TEST.md`；测试文件头注释 |
| C-4 | **AC-M4-9② 口径** | 「跨 ≥5 分钟，世界钟与墙上钟偏差 ≤1 分钟」（与 ③ 算术互斥） | **②a 锚定精度**（快进后 ≤1 分钟）/ **②b 节流精度**（跨 ≥300 真实秒 `\|Δ\| ≤ 1`）/ **②c 如实披露**原始量 | REQ ②③ 在「1 tick=1 世界分钟 × 1 tick/真实秒」下算术互斥 | 本表；`V0_SELF_TEST.md`；**上抛 PM**（§M4-H） |
| C-5 | **既有用例适配 `--ws-port 0`** | `run` 默认 `--ws-port 8787`（旧值「接受但不监听」） | `run --ws-port` 默认 **0**（不监听）；既有用例**显式**传 `--ws-port 0` | D-M4-14；显式化「不监听」意图，不改判据语义 | 本表；改动清单：`test_cassette_miss_cli.py`(5) / `test_cassette_no_backfill_r5.py`(3) / `test_cassette_tamper_cli.py`(6) / `test_io_shape_guards.py`(5) / `test_e2e_run_verify.py`(1) = **20 处既有调用点**（均为「加一个显式开关」，**零判据语义变化**）；另本轮**新增**用例 `test_observability.py`(1) ⇒ 全树实测 `rg -o '"--ws-port", "0"' tests/*.py \| wc -l` = **21** |
| C-6 | **`WorldKernel` 构造面变更** | 无 `decision_source` / `pack_profiles` | 新增两个可选构造参数（缺省 = `behaviour_tree` / 由 `pack.npcs` 派生） | D-M4-1 / D-M4-15⑥ | 本表；`tick.py` 注释 |
| C-7 | **`events.schema.json` 事件类型枚举** | 9 成员（冻结闭枚举） | **10 成员**（追加 `npc.decision`）+ `payloadByType` 追加 `then` 子句 | AC-M4-8① 需承载决策字段；`events.py` 的 `EVENT_TYPES` 同步 | 本表；**ADR-017** |
| C-8 | **`--ws-port` 语义（桥）** | `session/bridge/kernel_bridge.py`：`--ws-port 8787`「接受但不监听」 | 默认 **0**；字段 `ws_port` + `bridge_serves_network: false` + `live_channel_provided_by` | D-M4-4/D-M4-14：同一 flag 两个互斥语义在交付树里必须消失 | 本表；桥源码 docstring |
| C-9 | **AC-M4-11④ 取数源口径** | 「内容包无 `ambience`/`aesthetic_constraints` 段 ⇒ 记 GAP」 | **前提被否证**（两段都存在）⇒ 直接以它们为权威取数源，**不记 GAP** | 实测 `grep`（见 §M4-E.1） | 本表；`V0_SELF_TEST.md` AC-M4-11 行 |
| C-10 | **D-M4-19 谓词命令形态** | `awk '{print $NF}' manifest.txt` | `sed 's/ \| .*//' manifest.txt`（**意图不变**：覆盖性谓词） | 冻结 manifest 格式是 `path \| 用途 \| 生成方式` ⇒ `$NF` 取到的是第三列 | 本表；§M4-E.2 |
| C-11 | **`live --resume-state` 新增日志守卫** | 恢复可指向任意（含非空）事件日志 | 指向**非空**日志 ⇒ 结构化拒绝 `E_RESUME_LOG_EXISTS` exit 1（**新增**守卫，不放松任何旧判据） | 恢复是确定性重放，复用日志会追加第二个 `world.init` 并让 seq 链断裂（AC-M4-9⑦ 的 fail-closed 形态） | 本表；`cli.py::cmd_live`；`test_live_observation.py::test_resume_semantics_and_the_event_log_boundary` |
| C-12 | **AC-M4-9⑦ 链尾口径**（由「状态不丢」拆为两条独立判据） | 「恢复后 `state_hash` 与 `chain_tail` 都逐位相同」 | ① `state_hash` **逐位相同**（判据）；② `event_chain_hash` **不同**且差异字段集合**恰好 = `{plan_ticks}`**（**边界**，非判据） | 实测 `plan_ticks` 写在首条 `world.init` 里，`live --ticks` 一变链必变（根因隔离见 §M4-E.6） | 本表；§M4-E.6；`06` §M4-G.3 |
| C-13 | **`test_verify_detects_truncated_log` 夹具参数** | `lines[:-6]`（按「每 tick 4 条事件」的旧事实） | `lines[:-12]` **+ 前提断言**（`max_tick(kept) < plan_ticks`，否则用例失败） | M4 给每 tick 每 NPC 增一条 `npc.decision` ⇒ 每 tick 事件数 4 → **9** ⇒ 删 6 行不再跨过 tick 边界，`truncated log` 分支不可达（改由 event-stream 比较先报分歧）。**判据意图不变**（「朴素整行截断必须被检出」），且**新增前提断言**防再次静默退化 | 本表；§M4-E.7；`03` M4-13 |
| C-14 | **`V0_M4.sha256` 的排除规则** | 首版把 `*.png` 等运行产物模式**无条件**套到全树 ⇒ 误排除 `02_source/v0_skeleton/assets-sample/placeholder-001.png`（**交付的占位资产**） | 运行产物模式**只在 `spikes/**` 下生效**；`02_source/**` 只排除生成残渣（`*.pyc` / `.DS_Store`） | 冻结面**不得漏交付文件**；排除项必须与其理由的适用范围一致 | 本表；§M4-E.8；`V0_M4.gen.py` |
| C-15 | **AC-M4-4 判据面补强（r2）** | ① `rg` 扫 `requests\|httpx\|openai\|urllib\|socket\.`（命令行面 `rules/*.py` glob）；② `test_rules_layer.py` 机械判据是 **3 个硬编码文件名**（`requirement.py`/`utility.py`/`behaviour_tree.py`，**不含 `decision.py`**） | ① 原样保留（判据不放松）；② 改 `rglob("*.py")` **动态全量** + **非空断言** + 显式断言含 `decision.py`；**新增** `test_decision_path_has_no_model_seam`（**AST 代码面**：规则层全量禁 `remote_api`/`local_model`/网络与 SDK 根；决策模块 `decision.py` 与 `providers` 包**零接触**） | **判据面 ≠ 声称面**：本项目自身模型出口是 `providers/remote_api.py`，HTTP token 扫描对它**结构性失明** ⇒ 注入 `from ..providers import remote_api` 时 `rg` 与旧测试**双假绿**（r2 实测 `exit=1` + `6 passed`）。新判据必须让该注入**非绿**，且不得因 `decision.py` docstring 里的 `providers.remote_api` 字样让干净树**恒红**（故走 AST 名字面，不做裸文本子串） | 本表；§M4-r2 · F1/F2；`V0_SELF_TEST.md` AC-1 / AC-M4-4 行；`tests/test_rules_layer.py` |
| C-16 | **已被 C-18 取代（r3）** —— 原文保留为历史（r2 的**症状描述**不是结论，根因已定位并已修） | 文档未写明 `run --ws-port` 的监听窗口与 `live` 子命令的关系 | **显式写明**：`run` 路径先跑完 `--ticks` 再起监听（`cli.py` 里 `kernel.run()` 在 `_start_live_listener()` 之前）⇒ **r3 更正**：监听**确实会建立**，但旧顺序下真子进程窗口 ≈ **22µs（不可观测）**；r3 已把监听前移到 tick 循环之前，④ 改为**运行期间外部真连入**的实测口径（见 C-18） | REQ AC-M4-9④ 字面写「`--ws-port`（**或等价子命令**）真的监听」⇒ `live` 已满足，**不是产品缺陷**；但口径不写明会让复核者按字面 `curl` 得到 connection refused 并误判 | 本表；§M4-r2 · F5；`V0_SELF_TEST.md` AC-M4-9 行 |
| C-17 | **AC-M4-11 证据面（r2 补登；说明性，判据语义零变化）** | `V0_SELF_TEST.md:182` 把 `spikes/s16-liveworld/logs/ambience-report.json` 列为 AC-M4-11 证据，而该文件全文是**某次失败运行**的 stderr 崩溃栈（`TypeError ... reading 'light_k'`） | 文件改名 `ambience-report.CRASH.txt`（保留产物、名字不再像报告）；`V0_SELF_TEST.md` 的证据行**只列内容与 PASS 结论一致的文件** | 被点名的证据文件是崩溃栈 ⇒ 复核者会误判 AC-M4-11 为红（判据本身未变） | 本表；§M4-r2 · F4；`V0_SELF_TEST.md` AC-11 行 |
| C-18 | **AC-M4-9④ 监听口径改实测（r3；**取代 C-16**）** | `run --ws-port <n>` 的监听排在整轮 tick **之后** ⇒ 真子进程下外部可连窗口 ≈ **22µs（不可观测）**，而 `run` 自报 `listening=true` 并被 ④ 当证据引用 | ① **行为面**：把 `_start_live_listener(...)` 移到 `kernel.run()` **之前**，循环结束**显式 `stop()`**；② ④ 改为**运行期间外部真连入**的判据（含 `--ws-port 0` 负向对照） | 设计 `01_m4_design.md` D-M4-4 原文「显式给端口时**真的监听并服务同一只读端点**」⇒ 实现**自己已冻结的设计**，**不是改契约**；「没监听」是误判，真问题是**声明了一个外部无法观测的窗口** | 本表；§M4-r3 · r3-1；`spikes/s16-liveworld/logs/m4-r3-wsport-probe.py` |
| C-19 | **观察面并发上限 + 封存 fail-closed（r3）** | 普通 HTTP 观察路径**无并发上限**（`max_observers` 只约束 SSE）⇒ fd 打满 ⇒ 封存 `live_state.json` 抛 `Errno 24` ⇒ daemon 线程未停 ⇒ `_enter_buffered_busy` ⇒ **SIGABRT**；且封存段无 `try/except`、`stop()` 排在 `write_text` 之后 | ① 请求级上限 `max(2, 2×max_observers)`（挡 CPU 放大）；② 连接级上限 `max(4, 4×max_observers)` + 空闲读超时 `5.0s`（挡 fd）；两级超限 ⇒ 结构化 `503 E_HTTP_QUOTA` 并立即关连接；③ 封存段套 `try/except OSError` + `server.stop()` 放进**内层 finally**，封存异常转结构化错误 | 「干净收尾」不是风格问题：跳过 `stop()` 是**因**，daemon 线程在解释器 finalize 期争用 stderr 锁是**果** | 本表；§M4-r3 · r3-2；`spikes/s16-liveworld/logs/m4-r3-{live-load,live-fd-saturation,seal-injection}-probe.py` |
| C-20 | **计时判据容差锚定（r3 · N-3a）** | `test_pace_is_identical_with_zero_and_two_observers` 用固定 `\|Δ\| ≤ 3`，而窗口是 `time.sleep(2.0)` 的**实际**时长 ⇒ CPU 争用下窗口拉长（如 2.07s ⇒ 期望 104 tick）而阈值仍按 100 算 ⇒ **假红** | 容差锚定**窗口实测墙钟 / pace**（`max(3 tick, 3% × expected)`），两臂再比**归一化速率**；判据本体与「去节流」注入共用 | 判据在负载下**假红**与**假绿**互为镜像，同样摧毁判据价值；**不得**放宽成恒绿（去节流注入必须仍红） | 本表；§M4-r3 · r3-3；`tests/test_live_observation.py` |

---

## §M4-D 新基线登记（AC-M4-8⑥ 防乒乓）

| 项 | 旧值（M1/M2 口径） | **新值（M4 产出）** |
|---|---|---|
| `state_hash` @300 tick | `9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f` | **`0d79e5f349cad67d8ebc623fb7e49a17082e0170d0b5a5c3de62715ea42a2dca`** |
| `chain_tail` @300 tick | `baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786` | **`81669e9685e5dec845d0d5060321c0eba66939063997941c5be5f2e0d97d8cb6`** |
| 变更原因 | — | 决策路径由班表桩切换为「需求 → 效用 → 行为树」（**预期**，非回归） |
| 变更时刻 | — | **epoch 1790130629**（2026-09-23 10:30:29 +08:00） |
| 运行参数 | — | `pack=districts/xingfu-xiaoqu`、`seed=20260921`、`ticks=300`、`snapshot_every=50` |
| 两次运行逐位相同 | — | ✅ `identical: true`（`spikes/s15-autonomy/logs/determinism-baseline.json`） |
| `verify --expected-hash <新 chain_tail>` | — | ✅ **exit 0**（见 `V0_SELF_TEST.md` AC-M4-6 行） |
| 硬断言改写 | `tests/test_task_adaptation.py:34-35` 旧常量 | 改为 `M4_BASELINE_*` + 「确定性自洽」双向口径（旧值以注释存档） |
| 历史文档段 | `02_source/07_adr.md:486` 引用旧基线 | **追加 M4 段说明**（不改历史段） |
| **禁止项复核** | — | 未为保旧基线保留 `stub_decide`（桩**仅供负例**）；未静默改任何判据 |

---

## §M4-E 前提更正与口径登记（**如实**，不粉饰）

### E.1 设计 §2 D-M4-10 / REQ AC-M4-11④ 的字面前提**被否证**（更正，非放宽）

- 设计原文：「全包 grep `ambience|aesthetic_constraints` **0 命中**」。
- **实测（本轮）**：
  - `grep -rn "ambience\|aesthetic_constraints" v0_skeleton/districts/` ⇒ **4 命中**：
    `districts/xingfu-xiaoqu/buildings/courtyard-01.json:7: "ambience": {…}`、
    `districts/xingfu-xiaoqu/assets/manifest.json:4: "aesthetic_constraints": {…}`（两个 pack 各 2 处）。
- **处置**：AC-M4-11④ 的「取自内容包 `ambience`/`aesthetic_constraints` 段而非臆造」**可完全满足** ⇒
  **不记 GAP**，而是以这两段为**权威取数源**逐条判定（见 `spikes/s16-liveworld/ambience_assert.mjs`，19 条全绿）。
- **仍然如实保留的部分**：「氛围达成」的**主观成分**由 `ambience_assert.mjs` 的 `subjective_residual` 字段显式声明
  （判据只判数值面，不声称「观感已经精美」）。
- **归属**：设计/REQ 的**前提事实**更正（architect/PM 备案）；本轮**不改内容包**（零字节改动已证）。

### E.2 D-M4-19 谓词的**命令形态**更正

- 设计原文：`comm -13 <(awk '{print $NF}' manifest.txt|sort) <(find . -type f|sed 's|^\./||'|sort)` 输出只允许一行 `manifest.txt`。
- **实测**：字面命令输出 **160 行**（= 全部文件）——因为冻结的 manifest 格式是 `path | 用途 | 生成方式`，
  `$NF` 取到的是**第三列**（生成方式），与文件路径永不相交。
- **处置（意图不变）**：改为按冻结格式取**第一列**：
  ```bash
  cd <ws>/02_source
  comm -13 <(sed 's/ | .*//' manifest.txt | sort) <(find . -type f | sed 's|^\./||' | sort)
  # 输出恰好一行：manifest.txt
  ```
  实测输出 = `manifest.txt`（**恰好一行**）；`find` 计数 160 / manifest 行数 159（manifest 自身不入清单）。
- 另一条独立覆盖判据（由 `verify_specs.sh` 提供）：`manifest.txt covers every non-generated file under 02_source`（OK）。

### E.3 `events.schema.json` 的 `schema_version` 载体口径

本 schema **没有** `schema_version` 顶层键 ⇒ 本契约的版本化由 **ADR-017 + 本文件登记**承载，
`events.schema.json` **不承载** `schema_version` 键。（Raven 预审 M2 的处置③；ADR-017 已逐字写明。）

### E.4 `R3-RAV-M1` / 「13 条非覆盖」原文缺失（GAP）

- 事实：`06-acceptance-record.md §20` 与 `R3-RAV-M1` 的**原始条目文本不在本工作区**（Raven 预审 G1/G2 已 `grep` 零命中实证）。
- 替代口径：以 `refs/m3-delivered/06_v0_m3_self_test.md` 的 **R3-H 升级条件原文**为处置依据（逐字抄入设计 §12.2），
  本文件 §M4-F.2 逐条结清。
- **归属**：PM 补原文或确认替代口径（§M4-H 上抛项）。

### E.5 会话层 `E_SESSION_QUOTA` 与冻结协议的调和（口径登记）

- 设计要求：队列/会话超限 ⇒ **结构化 `E_SESSION_QUOTA`**（D-M4-17②）。
- 约束：`session.protocol.schema.json` 的 `errorCode` 是**冻结闭枚举**且设计 §4.5 明令**本轮不改**。
- 处置：`createSession` 的配额拒绝走 **HTTP 429 + `{error:"E_SESSION_QUOTA", quota:{…}}`**（非协议消息，不受枚举约束）；
  `onClientMessage` 的队列超限 ack 的 `reason` 取枚举内最贴近的 `E_RATE_LIMITED`，
  而结构化配额码落在 **`detail` 前缀 `E_SESSION_QUOTA: `** + **审计记录 `reason_code`**（两处都可机器读取）。
- 判据：`session/test/session.test.js::test_m4_intent_queue_is_bounded` 同时断言这三处。

### E.6 AC-M4-9⑦ 的**链尾**口径：根因隔离读数（探针在 `/tmp`，不触碰交付面）

- 现象：`live --resume-state <sealed>` 恢复后，同 tick 的 `state_hash` 逐位相同，而 `event_chain_hash` **不同**。
- 探针（`/tmp/m4_resume_rootcause.py`，`PYTHONDONTWRITEBYTECODE=1`，workdir = `<ws>/02_source/v0_skeleton/kernel`，exit 0）三组对照：

  | 组 | 命令 | 链尾（前 24 位） | 状态哈希（前 24 位） | tick |
  |---|---|---|---|---|
  | A#1 | `live --ticks 20 --no-warmup`（新 out） | `51e436f10e0c8bb24993ab21` | `19f6d1d4329804fc9e3440f2` | 20 |
  | A#2 | 同上，另一个新 out | `51e436f10e0c8bb24993ab21` | `19f6d1d4329804fc9e3440f2` | 20 |
  | B | `live --ticks 0 --no-warmup` | `884b2075679438d12ed418cd` | `a268da6b491b49059321b640` | 0 |

- 逐字段归因：`world.init.payload` 的唯一差异字段 = `plan_ticks`（`20` → `0`），其余（`seed` / `pack_id` /
  `pack_version` / `entity_count` / `snapshot_every` / `constants_digest`）逐字段相同。
- 结论：**链尾差异 = `plan_ticks` 差异**（写在首条事件里），与模拟状态无关 ⇒ 属**已定位的边界**，
  故 C-12 把它从「判据」降为「**边界 + 逐字段归因断言**」，而 `state_hash` 逐位相同仍是判据（**未放宽**）。
- 附带发现（新增守卫，C-11）：恢复若指向**非空**事件日志会追加第二个 `world.init` ⇒ 已 fail-closed 拒绝。

### E.7 全量验收中发现的**confirmed bug**（已修复并登记 C-13）

- **现象**：全量 `pytest -q` 首轮 ⇒ `1 failed, 186 passed in 2155.60s`，失败用例
  `tests/test_e2e_run_verify.py::test_verify_detects_truncated_log`（断言 `re.search(r"truncated log")` 为 None）。
- **复现命令**（workdir = `<kernel>`）：
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_e2e_run_verify.py::test_verify_detects_truncated_log -q -p no:cacheprovider
  ```
- **根因（隔离探针 `/tmp/m4_trunc_rootcause.py`，exit 0）**：

  | 截断行数 | verify exit | 出现 `truncated log` | 出现 `first divergence tick` | 截断后 log `max_tick` |
  |---|---|---|---|---|
  | 6 | 1 | **False** | True | **120**（== plan_ticks） |
  | 8 | 1 | **False** | True | **120** |
  | 12 | 1 | **True** | True | 119 |
  | 20 | 1 | **True** | True | 118 |
  | 40 | 1 | **True** | True | 116 |

  每 tick 事件数实测 = **9**（5 × `npc.decision` + 4 × `npc.action`）；`cli.py:694` 的
  `truncated log: max_tick != plan_ticks` **只在截断跨过 tick 边界时**才触发。
  原夹具删 6 行只删掉 tick 120 内的事件 ⇒ `max_tick` 仍是 120 ⇒ 该分支不可达（**检测仍然发生**：
  event-stream 比较先报出 6 处 `missing_in_log`，exit 1 不变）。
- **严重级**：**LOW**（属**夹具前提失效**，非产品行为缺陷；产品侧的截断检测**未退化**）。
- **修复**：夹具 `lines[:-6]` → `lines[:-12]`，并**新增前提断言** `max_tick(kept) < plan_ticks`
  （不满足即用例失败）⇒ 防止将来事件数变化时**再次静默退化**。判据意图**不变**（登记 C-13）。
- **复验**：`pytest tests/test_e2e_run_verify.py -q -p no:cacheprovider` ⇒ **15 passed in 14.57s**，exit 0。
- **未做**：未改 `cli.py` 的检测逻辑（该分支本身正确）；未放松任何断言。

### E.8 `V0_M4.sha256` 排除规则的**适用范围**修正（自审发现，登记 C-14）

- **现象**：首版 `V0_M4.gen.py` 把运行产物模式（`*.png` / `console-*.jsonl` / `browser-live-*.json` 等）
  **无条件**套到全树 ⇒ `02_source` 条目数 **159**，比 `find 02_source -type f | wc -l` 的 **160** 少 1。
- **覆盖核对命令**（workdir = `<ws>`）：
  ```bash
  sed 's/^[0-9a-f]\{64\}  //' V0_M4.sha256 | grep '^02_source/' | sort > /tmp/a
  find 02_source -type f | sort > /tmp/b
  comm -13 /tmp/a /tmp/b      # 首版输出：02_source/v0_skeleton/assets-sample/placeholder-001.png
  ```
- **根因**：`placeholder-001.png` 是**交付的占位资产**（AC-15 的 V0 面），不是浏览器运行产物；
  排除模式是为 `spikes/**` 的运行产物写的，**适用范围被错误地放大到全树**。
- **严重级**：**MEDIUM**（若不自审，冻结面会**漏掉一个交付文件**——冻结面漏项比多项危险）。
- **修复**：排除改为**路径感知**——运行产物模式**只在 `spikes/**` 下生效**；
  `02_source/**` 只排除生成残渣（`*.pyc` / `.DS_Store`）。
- **复验**：`02_source` 条目数 **160 == 160**（`comm -13` 输出为空）；
  `shasum -a 256 -c V0_M4.sha256` ⇒ **exit 0 / 197 OK**；重生成后与前一版**逐字节相同**（幂等）。

### E.9 禁区文件被**测试夹具**写入（mtime 被触碰，**内容未变**）—— 如实登记

- **现象**：复核禁区 mtime 时发现 `spikes/s5-latency-calibration/calibration.registry.json` 的 mtime 为本轮时间
  （其余禁区文件全部保持回合起点 mtime `09-23 09:56`，实测**只有这一个**文件被触碰）。
- **隔离复现**（脚本 `/tmp/m4_s5_probe.sh`，只读交付面）：
  ```
  before: sha256=8af6ccb647c75544a74bd9102666f397184cb1084404596af10b6ee4ce75892c mtime_epoch=1790135143
  $ cd <kernel> && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_calibrate_latency.py -q -p no:cacheprovider
  → 13 passed in 0.17s，exit=0
  after : sha256=8af6ccb647c75544a74bd9102666f397184cb1084404596af10b6ee4ce75892c mtime_epoch=1790137503
  CONTENT: unchanged（内容级红线未破）
  MTIME: touched（文件被写入，字节相同）
  ```
- **根因**：`tests/test_calibrate_latency.py` 的**既有**（M1 修复轮）夹具在 `finally` 里
  `registry_path.write_bytes(original)`（`test_registry_is_idempotent` / `test_registry_still_rewrites_when_content_changes` /
  `test_registry_force_rewrite_migrates_absolute_paths`）⇒ **写回相同字节** ⇒ 内容不变、mtime 更新。
  这是**本轮之前就存在**的行为（不是本轮引入的代码），任何一次全量 `pytest` 都会触发。
- **内容级证据（未变）**：文件内 `registry_written_at` = **`2026-09-22T11:42:48+0800`**（Sep 22，**早于本轮**）
  ⇒ 该文档内容最后一次被真正改写是在 M2/M3 期间，本轮**没有**改写其内容。
- **严重级**：**LOW**（内容级红线**未破**；但「用 mtime 判断禁区是否被动过」这一手段在此文件上**不可靠**）。
- **处置**：**不**做任何「复原」写入（内容已与回合起点一致，再写只会再改 mtime）；
  如实登记并在 `V0_M4.sha256` 的采集面声明中体现（该路径**不在** M4 冻结面内）。
- **建议（后续轮）**：把该夹具改为在 `tmp_path` 的副本上操作（不触碰 `spikes/**`），
  使禁区文件既不被写内容也不被写字节。

---

## §M4-F 结转项结清表（**禁止静默丢失**）

### F.1 REQ §2 硬性前置 `P-1 … P-9` 对账

| # | 遗留 | 本轮处置 | 判据/证据 | 状态 |
|---|---|---|---|---|
| P-1 | W9 边界：duckdb 查询与观察面板未做 | **真做**：分析查询真跑 + 观察面板接实时通道 | `spikes/s14-observability/logs/observability-report.json`；AC-M4-2 | **关闭** |
| P-1b | duckdb 本机不可用 | **先试一次离线装**（`pip install --no-index duckdb` ⇒ `No matching distribution`，exit 1；CLI 亦无）⇒ 纯 Python 同语义分析 + 逐组 `sql_equivalent` 映射 | `spikes/s14-observability/logs/{duckdb-cli.txt,duckdb-pip-install.txt,observability-report.json}` | **关闭（如实 GAP 面已登记）** |
| P-2 | GAP-7：自洽前缀截断无锚点不可见 ⇒ **不得放松** | 全量验收里任何「日志可信」推断**必须**走 `--expected-hash`（AC-M4-6 链路显式带锚） | `verify --expected-hash <新 chain_tail>` exit 0 | **沿用不放松** |
| P-3 | AC-M1-6 标定判据③不可重复（GAP，归 Q1） | **如实标 GAP**；不重采样、不调参、不改口径 | `V0_SELF_TEST.md` AC-1/AC-2 行（GAP + 原因 + 替代证据 + 归属） | **本轮如实 GAP** |
| P-4 | M1 的 MEDIUM + M2/M3 `non_block_issues` 残余 | **逐条结清**（见 F.3 / F.4 / F.5） | 本文件 | **关闭** |
| P-5 | `spikes/red/**` 等负控沙箱未随交付面提供 | 全量验收里**如实交代**冻结清单的可验边界 | `V0_SELF_TEST.md` AC-M4-7 行；`V0_M4.sha256` 采集面声明 | **交代** |
| **P-6** | M3 结转判据层非覆盖 13 条 + 冻结面口径 + `R3-RAV-M1`（接网络监听即升 CRITICAL） | 13 条逐条结清（F.2）；`R3-RAV-M1` **正面处置**（F.6） | F.2 / F.6 | **关闭（残余上抛，见 §M4-H）** |
| P-7 | `stub_decide` 仍在决策路径上 | **W11 真做**：决策阶段改 `autonomous_decide`；桩仅作负例 | `test_autonomous_decision.py` ①②④；`spikes/s15-autonomy/logs/negative-stub.json` | **关闭** |
| P-8 | 内核无自有世界钟、无实时服务 | **W12 真做**：`world_clock.py` + `live.py` + `live` 子命令 | `test_world_clock.py` / `test_live_observation.py`；`spikes/s16-liveworld/logs/*` | **关闭** |
| P-9 | 决策路径切换必然改变确定性基线 | **登记**旧 → 新 + 原因 + 时间；硬断言改「确定性自洽」口径 | §M4-D | **关闭** |

### F.2 M3 结转「判据层非覆盖 13 条」逐条结清（原文来源：`refs/m3-delivered/06_v0_m3_self_test.md` R5-C §1–13）

| # | 不覆盖项 | 本轮处置 | 状态 |
|---|---|---|---|
| 1 | 光照/材质色相与明度（两态按设计必须不同） | **沿用**（设计内允许）；氛围判据另立（§M4-B AC-M4-11），不并入该判据 | 沿用 |
| 2 | 光栅化 / GPU 层结果 | **不做 + 理由**：JS 层读数看不见；属一致性判据的声明边界（G9 口径沿用） | 不做（已记理由） |
| 3 | 摘要取完之后的时序篡改 | **不做 + 理由**：判据只在读数窗口内比较 | 不做（已记理由） |
| 4 | DOM / HUD 层 | **沿用**（f4 控件表 + 像素判据覆盖）；本轮 M4 追加「观察窗接实时通道」的浏览器读数判据 | 沿用 + 扩展 |
| 5 | `aspect` 不参与相等断言 | **沿用**（口径边界） | 沿用 |
| 6 | 两读窗口内改变视口 ⇒ 判据会红 | **沿用**（口径边界：两读之间不做 resize） | 沿用 |
| 7 | `render()` 入参以外的「间接换相机」 | **不做 + 理由**：只覆盖入参身份这一层 | 不做（已记理由） |
| 8 | 量化边界 `1e-6` | **沿用**（消除浮点尾差噪声） | 沿用 |
| 9 | `fog`/`background`/`sortObjects`/`frustumCulled` | **本轮处置**：`live` 通道**不渲染**这些状态；如实登记为「呈现层、按设计允许不同」 | 本轮登记 |
| 10 | `camera.layers.mask` | **不做 + 理由**：属渲染可见性选择；纳入需与第 9 条一并设计（登记后续轮） | 不做（已记理由） |
| 11 | 材质层 `roughness`/`metalness`/`map` | **本轮部分处置**：氛围判据**读** `roughness` 下限与「无镜面」，但**只判参数与内容包一致**，不并入闭式面 | 部分处置 |
| 12 | flag 本身 `matrixAutoUpdate`（只覆盖其效果） | **沿用**（R5 已就地限定） | 沿用 |
| 13 | 判据取数点被钉常量 / 缓存 / 判据体自比 | **沿用裁定 + 登记 M4**：属**判据侧**改写（声明域外）；**不得**把 `scene_assert` 读作「实现未被篡改」的证据 | 沿用 + 登记 |

### F.3 M1 报告的 MEDIUM 逐条（`06_v0_m1_self_test.md` §3）

> 注：设计 §12.1 写「M1 的 **8 条** MEDIUM」，而 `06_v0_m1_self_test.md` §3 实列 **M1–M10 共 10 条**
> （M6/M9 当时按「记录为跨里程碑风险」处置）。**如实按 10 条逐条接续**，并在 §M4-H 请 PM 核对计数口径。

| # | 项 | 本轮处置 | 状态 |
|---|---|---|---|
| M1 | seed 校验口径过弱 | 沿用 M1 的严格口径（投影全量过 `world.schema.json`）；本轮未改 | 沿用 |
| M2 | `redact()` 丢弃 `redact_fields` | 沿用 M1 修复；本轮 `DH_TEST_SECRET` 实测面**扩到**通道每帧与 404/405 `detail` | 沿用 + 扩展 |
| M3 | run↔replay 是同一实现的自比对 | 沿用；本轮 `verify --expected-hash` 仍为唯一链外锚（P-2 不放松） | 沿用 |
| M4 | adapter 目录 + 基线锚点 | 沿用（`spikes/kernel-baseline` **零改动**） | 沿用 |
| M5 | R3 负例三条前提 | **注入点迁移后重新满足**：包装函数保持 `set[str]` 容器 + `needs.esteem` 增量真的进 `state_hash` + 跨子进程 | **关闭（迁移后复验）** |
| M6 | `--ticks` 默认 300 使 M3 判据 6 语义漂移 | **不做 + 理由**：跨里程碑语义项，M4 收口轮不改 `--ticks` 默认（改它会动全部既有读数）；登记后续轮 | 不做（已记理由） |
| M7 | `compare_checkpoints -> list[str]` 承载不足 | 沿用字符串协议；本轮 `test_observability.py` 用**非空断言**补齐 M5 形态 | 沿用 + 补强 |
| M8 | AC-M1-3 产物落点 | 沿用（`out/m1-ac3/`） | 沿用 |
| M9 | `replay --out` 与 W9 面重叠 | **本轮关闭**：W9 真做（分析查询真跑 + 观察面板） | **关闭** |
| M10 | AC-M1-7 请求体面无判据 | 沿用 M1 修复轮 C1 的扫描判据 | 沿用 |

### F.4 M2 `non_block_issues`（`refs/m2-delivered/05_raven_risk_report.md` §6，N1–N10）

| # | 项 | 本轮处置 | 状态 |
|---|---|---|---|
| N1 | `replay` 侧 `checkpoints` 为普通文件 ⇒ 裸 traceback | 沿用 M3 已落地的 `_refuse_existing_replay_outputs` / `_refuse_unusable_output_dir` 形态 | 沿用 |
| N2 | `run` 的 `checkpoints` 只读 ⇒ 裸 traceback | **本轮关闭**：`test_io_shape_guards.py::test_m2_run_refuses_read_only_checkpoints` 复跑绿（`E_OUTPUT_NOT_WRITABLE` + 四元组） | **关闭** |
| N3 | `checkpoints` 为指向 out 之外的符号链接 ⇒ 静默写出去 | **本轮关闭**：`test_io_shape_guards.py::test_m3_run_refuses_symlinked_checkpoints` 复跑绿 | **关闭** |
| N4 | 畸形但链自洽的日志（缺 `plan_ticks` 等）⇒ 裸 traceback | **不做 + 理由**：`events.schema.json` 的 `world.init` 必填面本轮**不改**（改它属契约变更且会动 AC-M1 判据）；登记后续轮 | 不做（已记理由） |
| N5 | 冻结 `pack_sign.py` 在 `pack.sig` 为符号链接时写到 pack 外 | **不做 + 理由**：需 PM/ADR 授权（冻结工具写侧边界）；本轮**内容包零改动**，未触达该路径；登记后续轮 | 不做（已记理由） |
| N6 | 日志字面字节不受保护 | 沿用；`claim_boundary` 口径不变 | 沿用 |
| N7 | AC-M1-7(b) 请求体扫描是行级正则 | 沿用；本轮新增的 secrets 判据改用**值级**比对（不依赖正则） | 沿用 + 补强 |
| N8 | canonical 四舍五入 vs `round()` 半值取偶 | 沿用（本轮未改 canonical） | 沿用 |
| N9 | 集合级错误时 `first_divergence_tick = null` | 沿用 | 沿用 |
| N10 | `ecs.py` docstring 可被 `grep traversal_flags` 命中 | 沿用（措辞建议） | 沿用 |

### F.5 M3 `07_m3_architect_verdict.md` R5-8 残留（12 条）

| # | 项 | 本轮处置 | 状态 |
|---|---|---|---|
| NEW-L1/L2/L3/L4 | M3 `06` 自身的计数/措辞/标签残留（LOW） | **不做 + 理由**：属 **M3 历史文档段**，本轮写集虽覆盖但**改历史段会破坏 M3 冻结面口径**；如实登记 | 不做（已记理由） |
| LOW-R5C-1 | `06` L750 枚举不全（LOW） | 同上 | 不做（已记理由） |
| GAP-R5-1 | 148 条被排除 log 的逐字节可重生成性未端到端验证 | **不做 + 理由**：重跑历史驱动会写 `spikes/**`（超本轮意图）；旁证沿用（生产者驱动在哈希面内 + `--dry-run added=[]`） | 不做（已记理由） |
| R5-RAV-M3 | 排除项仅按名字模式 ⇒ 证据理论上可伪装成运行产物 | **本轮处置**：`V0_M4.sha256` 采集面**显式声明**「被排除路径不得承载判据性结论」，并**单独报** `02_source` OK 条数 | 登记 + 声明 |
| R5-RAV-M4(d) | 非 f4 驱动复跑会重写仍在面内的产物 | **本轮处置**：M4 的浏览器验收**另起** `spikes/s16-liveworld/**`（不与 M3 产物同名），M3 面零触碰 | 登记 |
| AC-M3-8③⑤ 双读读数外置 | 结论由门禁退出码 + `06`/`03` 登记承担 | 沿用 | 沿用 |
| 文档口径残留（R4-B / R3 段绝对措辞） | **不做 + 理由**：M3 历史段；本轮**未动** | 不做（已记理由） |
| 接续登记：`R4-M2`（相机判据自证不足）/ `R4-M3`（装配后 mesh 材质零判据）/ `R2-M3-06`（会话层无配额无 TTL）/ `R2-M1`（桥是第二权限入口）/ Sentinel `MEDIUM-R4-1`（读法切换吃掉 delta 位移）/ LOW `scene_handle_camera_report_is_live` 弱自证 | **`R2-M3-06` 本轮关闭**（配额 + TTL + 有界队列，见 F.6②）；`R2-M1` 本轮以「桥无网络面」结清（F.6③）；其余 4 条**沿用登记**（呈现层判据侧，本轮不动闭式面） | 1 关闭 / 1 结清 / 4 沿用 |
| 过程项（architect 侧 3 条） | 属 architect 记录，本轮不处置 | 沿用 |

### F.6 `R3-RAV-M1` 正面处置（本轮升 CRITICAL；设计 §11 D-M4-17）

| 项 | 处置 | 证据 |
|---|---|---|
| ① 新增只读通道的边界 | 只读（无 intent 面）⇒ **结构上不是权限入口**；默认 loopback、`--allow-remote` 显式开关、非 GET/HEAD ⇒ 405、Host 校验 403、观察者上限 503 | `test_live_observation.py::test_service_boundary_host_cors_nosniff_and_methods` / `test_observer_quota_is_enforced_with_a_plus_one_counter_example` |
| ② 会话层配额 + TTL + 回收（**关闭 R2 M3-06**） | `session/src/server.js` 增 `max_sessions`（超限 ⇒ HTTP 429 `E_SESSION_QUOTA`）/ `session_ttl_ms`（到期回收，连 queues/outboxes 一起释放）/ 有界 `queues`/`outboxes`（丢最旧 + `outboxDropped` 审计计数） | `session/test/session.test.js` 的 4 条 M4 用例（含反例）；`npm test` ⇒ **21 passed / 0 fail** |
| ③ 桥的权限面 | 桥经 **stdio 管道**驱动（等价双 fd），**无网络可达路径**；`mode` 显式 fail-closed 已在 M3 落地 ⇒ 以「**桥无网络面**」结清 | `test_m4_bridge_declares_no_network_surface_and_ws_port_defaults_to_zero`（含注入反例）；`kernel_bridge.py` 源码零 `socket.`/`listen(` |
| ④ **残余（如实登记 + 上抛）** | `--allow-remote` 打开后通道**无鉴权** ⇒ 同网段可读 `/live/state` 与 `/live/meta`（**含 seed**）⇒ 属**信息面扩大**；本轮**不加 token** | `live.py` 的 `bind_policy.warning`（启动横幅与 `/live/meta` 都打印）；§M4-H 上抛项 2 |

---

## §M4-G 已知未覆盖项（如实）

1. **`--allow-remote` 无鉴权**（F.6④）：只读、无写面，但同网段可读 state/meta（含 seed）。本轮不加 token（需 PM 授权）。
2. **duckdb 未真跑**：本机无 CLI 也无 python 模块，离线安装失败 ⇒ 以纯 Python 同语义实现 + `sql_equivalent` 映射替代（**未把「SQL 文本已写」当「查询已跑」**）。
3. **恢复语义的两条边界（根因已隔离，实测）**：
   - **日志边界**：恢复 = 同 seed + 同 pack + 快进到同一 tick 的**确定性重放** ⇒ 复用**非空**事件日志会让
     `EventLog` 追加第二个 `world.init` 并让 seq 链断裂 ⇒ 本实现 **fail-closed 拒绝**（`E_RESUME_LOG_EXISTS`，exit 1）。
   - **链尾边界**：同 tick 的 `state_hash` **逐位相同**（状态不丢）；但 `event_chain_hash` **不同**——
     根因由探针**逐字段指认**：`plan_ticks` 写在**首条** `world.init.payload` 里，而 `live --ticks N`
     同时决定 `plan_ticks` 与「锚定后再推进 N tick」⇒ 恢复用的 `--ticks` 与原运行不同 ⇒ 首条事件不同 ⇒ 链不同
     （`world.init.payload` 差异字段集合实测 **恰好 = `{plan_ticks}`**，见 `test_live_observation.py::test_resume_semantics_and_the_event_log_boundary`）。
     **「状态不丢」不等于「事件链连续」**——本判据**不**声称事件链连续。
4. **②c 的原始偏差**：1× 档下世界钟每 300 真实秒领先墙上钟约 **295 分钟**（按构造必然）⇒ 判据**不**声称「两钟同步」。
5. **`max_drift_ms` 是单 tick 的 sleep 过冲**（macOS 粒度可达数十毫秒），**deadline 锚定 ⇒ 不累积**；判据钉「不累积」而非「单 tick 过冲为 0」。
6. **SSE 心跳周期 10s**：本轮的浏览器验收窗口较短，未覆盖「长时间空闲后的心跳续命」形态。
7. **氛围判据只判数值面**（取数源 + 像素统计）；「观感是否精美」仍是主观，**不声称达成**。
8. **M3 历史文档段**（R4-B / R3 段绝对措辞、NEW-L1..L4 等）本轮未改（见 F.5）。
9. **AC-M1-6 标定判据③不可重复**（P-3）本轮**如实 GAP**，未重采样、未调参。
10. **行为多样性弱点（本轮新发现，已登记）**：长跑 300 tick × 5 NPC 的 **1500** 条决策里
    `dominant_need = safety` 占 **1428（95.2%）**、分支退化为 `restore` **1428（95.2%）**；
    而 `restore` 分支加入的 `rest` 动作只赢了 **410/1500**。
    根因（读码 + 读数一致）：`rules/decision.py::_needs_delta` 给所有需求 `+BUILDUP_PER_TICK(0.004)`，
    只有被选动作映射的需求才 `−RELIEF_RATIO(0.30) × 压力`；`ACTION_NEED` 里 **`safety` 只由 `flee` 缓解**，
    而 `flee` 需跨紧急阈值（1500 tick 里只赢 **8** 次）⇒ `safety` 压力单调累积至饱和 ⇒ 恒为主导需求。
    判据状态：AC-M4-8①②④ 的判据（间距 > 0.05、独立复算一致、退回桩变红）**全部满足** ⇒ **不构成 FAIL**；
    但行为多样性是**已登记的弱点**。是否标定属 **architect/PM 决策**（需求或标定变更）⇒ 本轮**不改**。
    证据：`spikes/s14-observability/logs/observability-report.json`（`npc_behaviour.dominant_need_distribution` /
    `branch_distribution` / `action_distribution`）

---

## §M4-H 上抛 PM（`block_issues`，非阻断）

1. **AC-M4-11④ 前提更正**：设计/REQ 称内容包无 `ambience`/`aesthetic_constraints` 段，**实测存在**（§M4-E.1）。
   本轮按「存在」处置（更严：直接以内容包为权威取数源）；请 PM/architect 备案该前提更正。
2. **`--allow-remote` 无鉴权的信息暴露面**（F.6④）：请 PM 明示**接受**或要求后续轮补 token。
3. **AC-M4-9② 口径裁决**（C-4）：请 PM 确认 ②a/②b/②c 的拆分口径。
4. **`06-acceptance-record.md §20` / `R3-RAV-M1` 原文缺失**（§M4-E.4）：请 PM 补原文或确认替代口径。
5. **M1 MEDIUM 计数口径**：设计写「8 条」，`06_v0_m1_self_test.md` §3 实列 10 条（§M4-F.3）；请核对。
6. **`SEED.sha256` 语义**：它是**起点溯源**文件（当前自校验 54/100 FAILED），本轮字节不变；若期望它是**活的自校验面**，需另立一轮。
7. **D-M4-19 谓词命令形态更正**（§M4-E.2）：请确认「按冻结格式取第一列」的替代口径。
8. **行为多样性**（§M4-G#10）：safety 主导 95.2% / 分支退化 restore 95.2%，根因 = safety 只被 `flee` 缓解
   ⇒ 请裁决是否在后续轮做标定（属需求/标定变更，本轮未动）。
9. **`test_verify_detects_truncated_log` 夹具口径修正**（C-13 / §M4-E.7）：判据意图不变，夹具由删 6 行改删 12 行
   + 前提断言 ⇒ 请备案（M4 起每 tick 事件数 = 9，凡按「每 tick N 条」写死的夹具都需复核）。

---

## §M4-r2 修复轮 r2（`REQ-20260921-006-m4-r2`）—— 1 CRITICAL + 2 MEDIUM（证据/口径面）

> **本轮不是新功能轮**：只修 architect 复现的 3 条（1 CRITICAL + 2 MEDIUM），**未扩范围**。
> **产品语义零改动**：`cli.py`、`rules/**`、内容包 `districts/**` **零字节改动**；
> 唯一产品面改动是 `kernel/tests/test_rules_layer.py`（测试判据面）。

### r2-0 开工快照（与任务书字面一致，无漂移）

| 项 | 期望 | 实测 |
|---|---|---|
| 真实仓库 HEAD | `a9e3a57` | `a9e3a5787c2f70bf9d07d6b82f79a41adf57d7d3` ✅ |
| `git status --porcelain \| wc -l` | `0` | **0** ✅ |
| `find 02_source -type f \| wc -l` | 160 | **160** ✅ |
| 残渣 `find 02_source \( -name '__pycache__' -o -name '.pytest_cache' -o -name '*.pyc' \) \| wc -l` | 0 | **0** ✅ |

### r2-1【F1 + F2 · CRITICAL 关闭】AC-M4-4 判据对「项目自身模型出口」有牙了

- **RED（本人亲手复现，非引用他人读数）**：在 `/tmp` 隔离镜像（**镜像 `02_source` 根**——`capability.schema.json`
  按父级路径解析）里给 `rules/decision.py` 注入 `from ..providers import remote_api` + 一次引用
  （落点 `decision.py:19` / `:477`）⇒ `rg` 仍 `exit=1`、`pytest tests/test_rules_layer.py` 仍 **`6 passed`**；
  注入 `import urllib.request`（`:474`）⇒ `rg` `exit=0`（真命中）但 `pytest` 仍 **`6 passed`**（**双假绿**）。
  读数全文 `spikes/s15-autonomy/logs/ac-m4-4-three-state.PRE-FIX.txt`。
- **GREEN（判据面只能变强，未放松任何旧判据）**：`kernel/tests/test_rules_layer.py`
  ① 机械判据清单由 3 个硬编码文件名改 `rglob("*.py")` **动态全量** + **非空断言** + 显式断言含 `decision.py`；
  ② **新增** `test_decision_path_has_no_model_seam`：**AST 代码面**两级判定 —— 规则层全量禁
  `remote_api`/`local_model`/网络与 SDK 根；**决策模块 `decision.py` 与 `providers` 包零接触**。
  走 AST 而非裸文本子串的理由：`decision.py` docstring 里**本来就有** `providers.remote_api` 字样，
  裸子串会让干净树**恒红**；注释与 docstring 天然不在 AST 名字面内 ⇒ 干净树绿、注入非绿。
- **关闭判据逐条读数**（门脚本 `spikes/s15-autonomy/logs/ac-m4-4-three-state-gate.sh`，可原样重跑）：

| # | 命令（workdir = `<kernel>`，注入在 `/tmp` 镜像） | exit | 读数 |
|---|---|---|---|
| 1 | `rg -n "requests\|httpx\|openai\|urllib\|socket\." deephealing_kernel/rules/*.py` | **1** | 零命中（交付面干净） |
| 2 | `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_rules_layer.py -q -p no:cacheprovider` | **0** | **7 passed** |
| 3 | 反例 A：注入 `from ..providers import remote_api` + 一次引用 | **1** | **非绿**：代码面判据 `1 failed`，命中行 `decision.py:19: providers` / `decision.py:19: remote_api` / `decision.py:477: remote_api`（`rg` 那侧仍 `exit=1` —— token 面对自身 provider 结构性失明） |
| 4 | 反例 B：注入 `import urllib.request` | **1** | **非绿**：`rg` `exit=0`（真命中）+ `2 failed`（token 判据 + 代码面判据），命中行 `decision.py:474: urllib.request` |

- 交付面注入前后整树 sha256 **逐位相同**（`9d352f0f…8ca47`，见 `ac-m4-4-three-state.txt` 首尾两行）。
- **AC-M4-4 判据 = 上表 ① + ② 两条命令的组合**（只跑 `rg` 不算跑完判据——它对项目自身 provider 无牙）。
- 登记：**C-15**；文档订正见 r2-2。

### r2-2【F3】订正不实声称（`V0_SELF_TEST.md` + `06` §M4-A / §M4-B）

- **两处不实句**：①「扫描面用**显式文件清单**（非 glob 通配）」；②「`test_rules_layer.py` 清单改
  `rules/**/*.py` 全量 + 非空断言」。r1 时**盘上两条都不成立**（命令行面实为 `rules/*.py` **glob**；
  测试清单实为 3 个硬编码文件名）。
- **订正落点（三处，含 §M4-B 的同一句话）**：`V0_SELF_TEST.md` AC-1 段 / `06` §M4-A 的 C1 行 /
  `06` §M4-B 的 AC-M4-4 行 ⇒ 现**逐字写明**：命令行面是 glob（不是显式清单）、测试面是 `rglob` 全量
  + 非空断言、以及 AC-M4-4 的**新**反例形态（`/tmp` 隔离镜像 + 反例 A/B）。
- **逐字可核（把订正后的命令原样跑一遍）**：`rg` ⇒ `exit=1`；`pytest tests/test_rules_layer.py -q`
  ⇒ `7 passed`；`grep -c '^def test_'` ⇒ `7`；`grep -c '扫描面用**显式文件清单**'` ⇒ `0 / 0`（旧**断言**形态消失；
  `06` 中仅剩 §M4-A C1 行里**带引号引用 r1 原句并注明不成立**的订正文字）。

### r2-3【F4 · MEDIUM 关闭】`ambience-report.json` 处置（取方案 (a)）

- **事实**：该文件（mtime 10:51）全文是**某次失败运行**的 Node 崩溃栈
  `TypeError: Cannot read properties of undefined (reading 'light_k')`，而 `V0_SELF_TEST.md:182` 把它列为
  AC-M4-11 的证据 ⇒ 复核者打开会看到崩溃栈、可能误判 AC-M4-11 为红。
- **处置**：改名 `ambience-report.json` → **`ambience-report.CRASH.txt`**（保留产物，名字不再像报告）；
  `V0_SELF_TEST.md` 的 AC-11 证据行改为**只列内容与 PASS 结论一致的文件**
  （`ambience-assert.out`、`browser-live-live.json`），并显式说明该 `.CRASH.txt` **不是证据**。
- **关闭判据（逐个 `cat` 被点名的证据路径）**：`tail -1 ambience-assert.out`
  ⇒ `ambience_assert: PASS=21 FAIL=0`（与「氛围 21/21」一致）；`browser-live-live.json` 首字段
  ⇒ `tag=live` / `url=http://127.0.0.1:8791` / `viewports[0]=desktop 1440×900` /
  `live_readout_at_connect.channelTick=233`（与「连入 tick 233」一致）；`grep -c 'ambience-report.json' V0_SELF_TEST.md` ⇒ `0`。
- 改名**内容未变**：`ambience-report.json` 旧 sha256 = `57d9fb30…d6b5d` = 新 `ambience-report.CRASH.txt` sha256 ✅。
- 登记：**C-17**。

### r2-4【F5 · MEDIUM 关闭】`run --ws-port` 的监听窗口口径（取默认方案：文档面写明，不改语义）

> ⚠️ **本节已被 §M4-r3 · r3-1 取代（r3）**。当时的处置是 **docs-only**，理由是「根因未定位、`live` 已满足字面要求」；**r3 已定位根因（启动顺序）并改行为面**（登记 `C-18`）。
> 下文保留为**历史 RED 证据**；其中 r2 对监听窗口的**症状式描述**（把可连窗口说成只落在进程收尾）
> 是**根因未定位时的近似**，**不是结论**，不得作为当前口径引用；**理由 = 根因已定位（启动顺序）并已修**。

- **代码面事实**：`cli.py` 中 `kernel.run(args.ticks)` 在 `_start_live_listener(...)` **之前**
  ⇒ 监听窗口落在进程收尾（r3 更正：**确实会建立**，真子进程下 ≈ 22µs，不可观测）。
- **实测读数**（探针 `/tmp/m4r2_f5_probe.py` / `m4r2_f5_probe2.py`，只读交付面；完整读数见 `03` M4-r2 · F5 段）：

| 场景 | 命令 | 读数 |
|---|---|---|
| `live` 真监听 | `python3 -m deephealing_kernel live --pack districts/xingfu-xiaoqu --seed 20260921 --port 8931 --out /tmp/m4r2_f5_live --snapshot-every 50` | 20ms 轮询 **8 次 1 次连入**；裸 socket GET `/live/health` ⇒ **`HTTP/1.1 200 OK`**，body `{"listening": true, "port": 8931, "observers": 0, "ok": true, …}`；SIGTERM ⇒ exit 0 |
| `run` 窗口 | `… run --ticks 3000 --ws-port 8931 …` | wall=1.611s，exit 0；**全程 5ms 轮询 79 次 0 次连入**；自报 `live_channel.listening = True`；退出后 `ConnectionRefusedError` |
| `run` 命中能力对照 | 自建 listener 占住 `127.0.0.1:8932` ⇒ `… run --ws-port 8932 --ticks 10 …` | **exit=1**，`E_ADDRINUSE: cannot bind 127.0.0.1:8932 …`（证明 `run` 确实真去 bind/listen，不是「自报 listening 的摆设」） |

- **结论（已写入 `06` §M4-B AC-M4-9 行 + `V0_SELF_TEST.md` AC-M4-9 行与表后注）**：
  **（r2 的历史结论，已被 §M4-r3 · r3-1 取代）**：当时判「不是产品缺陷」；r3 定位到根因是
  **启动顺序**（监听排在 tick 循环之后），并已把监听前移 ⇒ ④ 现在是**实测口径**。
- 未采用行为面方案（不给 `run` 加 linger 开关）⇒ `cli.py` **零改动**、既有 21 处 `--ws-port 0` 用例零影响。
- 登记：**C-16**（说明性补登，判据语义零变化）⇒ **r3 由 `C-18` 取代**（改行为面 + 判据改实测口径）。
- 环境事实（如实）：本机 `8899` / `8898` 上有**他人**（其它 workspace / 实验目录）遗留的 `live` 监听进程，
  故探针改用自选空闲端口 `8931`/`8932`；**未触碰**他人进程。

### r2-5 `V0_M4.sha256` 重取登记（**硬性**：改了 `02_source/**` 与 `V0_SELF_TEST.md` ⇒ 必须重取）

- **重取理由**：本轮改了 `02_source/v0_skeleton/kernel/tests/test_rules_layer.py` 与 `V0_SELF_TEST.md`，
  并改写了 `06` / `03` / 改名一个 `spikes/**` 证据文件 ⇒ 冻结面内容变化。
- **重取前清单自身 sha256**：`fc7a388e7d5b9a07c05ec115f6dfb487922c015085c081c9bd464cc971b4cc81`（`V0_M4.sha256`）。
- **变更面（= 重取前 `shasum -a 256 -c V0_M4.sha256` 的非 OK 集合，逐字读数）**：
  ```
  02_source/v0_skeleton/kernel/tests/test_rules_layer.py: FAILED
  06_v0_m4_self_test.md: FAILED
  V0_SELF_TEST.md: FAILED
  spikes/s16-liveworld/logs/ambience-report.json: FAILED open or read（已改名）
  ```
  另**新增 4 个面内文件**（旧清单不可见）：`spikes/s15-autonomy/logs/ac-m4-4-three-state-gate.sh`、
  `ac-m4-4-inject-remote.py`、`ac-m4-4-three-state.txt`、`ac-m4-4-three-state.PRE-FIX.txt`，
  以及改名目标 `spikes/s16-liveworld/logs/ambience-report.CRASH.txt`。
- **逐文件前后哈希**：

| 文件 | 重取前 sha256 | 重取后 sha256 |
|---|---|---|
| `02_source/v0_skeleton/kernel/tests/test_rules_layer.py` | `aa533168…e67e7c6` | `4666f117…6c339e6c` |
| `V0_SELF_TEST.md` | `8bf42c11…0b2a08e6` | `65c81923…77d103d95` |
| `spikes/s16-liveworld/logs/ambience-report.json` → `…CRASH.txt` | `57d9fb30…c5a0d6b5d` | **同值**（仅改名，内容逐字节未变） |
| `06_v0_m4_self_test.md` / `03_artisan_self_test.log` | `7b642f61…c6ab5b1d` / `729ef1a0…ea0855a05` | **自指声明**：这两个文件（连同 `V0_M4.sha256`）**无法在面内记录自身重取后的哈希**（自哈希不可能）⇒ 其重取后哈希**从重取后的 `V0_M4.sha256` 逐字可读**（清单本身不入面） |

- **重取后复验读数**（`take A` = 写入本段**之前**的一次重取；`take B` = 本段写入后**定稿重取**，见下）：
  - `cd <ws> && shasum -a 256 -c V0_M4.sha256` ⇒ **exit 0 / `201 OK` / 0 非 OK 行**
  - 清单条目数 **201**（`files=201`）；`02_source` 条目数 **160 == 160**（`find 02_source -type f | wc -l`），
    `comm -13` 覆盖谓词 ⇒ **空输出**
  - `bash verify_specs.sh --quiet`（workdir `<ws>/02_source`）⇒ **exit 0 / `OK (130 checks passed, 0 skipped)`**
  - 收尾残渣 `find 02_source \( -name '__pycache__' -o -name '.pytest_cache' -o -name '*.pyc' \) | wc -l` ⇒ **0**
  - 真实仓库：HEAD **`a9e3a5787c2f70bf9d07d6b82f79a41adf57d7d3`**（= `a9e3a57`）/ porcelain **0** 行 /
    `diff -r` 仓库 `v0/02_source/v0_skeleton/districts` vs 工作区 `districts` ⇒ **exit 0、30/30 文件逐字节相同**
  - 清单自身 sha256（`take A`）= `a72854af9298791fa31b3de654cf7a2c545c3bfb548893989976879ea4c3452e`；
    `take B` 读数见 §M4-r2 交付摘要（`V0_M4.sha256` **自指**：无法把自身哈希写进面内任何文件）
  - **`take B`（定稿重取）复核**：写入本段后再次重取并复验 ⇒ 条目数 **201**、`shasum -c` **0 非 OK**、
    `comm -13` **空**（与本段所记读数**逐项相同**；`06` / `03` / `V0_M4.sha256` 三者**自哈希不可入面**，故其
    重取后哈希**从重取后的 `V0_M4.sha256` 逐字可读**）

- **内核全量 pytest（如实：本轮为 GAP，不标 PASS）**：
  - **第 1 轮**：`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider`（workdir `<kernel>`）⇒
    **`1 failed, 187 passed in 1998.73s`，exit=1**；唯一失败用例
    `tests/test_live_observation.py::test_pace_is_identical_with_zero_and_two_observers`
    （`AssertionError: 观察者数量改变了推进节奏（108 vs 104）`，判据 `|Δ| ≤ 3`）。
  - **第 2 轮**：本轮预算耗尽时**仍在运行**（`/tmp/m4r2_full_pytest_run2.out`，部分输出为进度点）⇒
    按证据纪律**不得标 PASS**，记为 **GAP**（指向独立复跑）。
  - **失败根因（不在本轮改动面内）**：该用例是**墙钟计时**判据（`pace=0.02` + `sleep 2.0s` ⇒ 期望 ≈100 tick，
    阈值 `|Δ| ≤ 3`），对机器负载敏感；本轮改动面 = `tests/test_rules_layer.py` + 文档 + `spikes/**` 证据，
    **`test_live_observation.py` 与全部产品代码零改动**（`shasum -c` 非 OK 集合已逐字证明）。
    隔离复跑 **4 次 ⇒ 3 绿 1 红**（读数：`109 vs 106` 绿 / `FAILED` / `108 vs 108` 绿 / `107 vs 106` 绿），
    Δ 实测落 **3 / 4 / 0 / 1** 的边界带；当时 load average **2.64 / 3.00 / 3.12**。
  - **处置**：`tests/test_live_observation.py` **不在本轮写集** ⇒ **本轮不修**（不越界），
    作为 **confirmed bug（MEDIUM，判据鲁棒性）** 记录并上抛 architect/PM（见 r2-7）。

### r2-6 本轮**未做**的事（如实）

- 未改 `cli.py`（未采用 F5 的行为面方案）；未改 `rules/**` 任何产品代码；未改内容包 `districts/**`。
- 未触碰 `04_sentinel_test_report.md` / `05_raven_risk_report.md` / `.pm_notes.md` / `.pm_ruling-*.md`（只读面）。
- 未 `commit` / `push` / `PR` / `deploy`；真实仓库保持 `a9e3a57` + 零改动。
- 未追补本轮 N/A 的条目；未复述/覆盖 reviewer 报告结论。

### r2-7 交付物与核验入口

- `03_artisan_self_test.log`（M4-r2 段：快照 / RED / F1~F5 逐条读数 / 自审 / 已知未覆盖）
- `06_v0_m4_self_test.md`（本段 + §M4-A C1 订正 + §M4-B AC-M4-4/AC-M4-9 订正 + §M4-C 的 C-15/C-16/C-17）
- `V0_SELF_TEST.md`（AC-1 段 / AC-11 证据行 / AC-M4-4 行 / AC-M4-9 行 + 表后注）
- `02_source/v0_skeleton/kernel/tests/test_rules_layer.py`（唯一产品面改动）
- `spikes/s15-autonomy/logs/ac-m4-4-three-state{,-gate.sh,-inject-remote.py,.PRE-FIX.txt}`（AC-M4-4 三态）
- `V0_M4.sha256`（重取）

### r2-7 上抛 architect / PM（**confirmed bug，本轮不修**）

- **`tests/test_live_observation.py::test_pace_is_identical_with_zero_and_two_observers` 是负载敏感判据**
  （墙钟计时：`pace=0.02` + `sleep 2.0s` ⇒ 期望 ≈100 tick，阈值 `|Δ| ≤ 3`；本机负载下隔离复跑 4 次
  **3 绿 1 红**，Δ 实测 **3 / 4 / 0 / 1**）。**影响**：全量 `pytest` 会因它间歇性 `exit 1`，
  让「内核全量 exit 0」这条闭合项变成掷硬币（r1 的 `187 passed` 与 r2 第 1 轮的 `1 failed` 同源）。
  **建议**（下一轮，需 owner 决定）：把该判据改为「同一进程内两窗口的相对差」或把阈值改为按
  `实测窗口长度` 归一化（如 `|Δ| ≤ max(3, 1% × 期望 tick)`），并给该用例注入一个**负载/抖动**负例。
  **本轮不修**：该文件**不在**本轮写集（越界即 block），故只记录 + 上抛。
- **`rg` 命令行面对项目自身 provider 仍无牙**：AC-M4-4 判据必须**两条命令一起跑**（`rg` + `pytest`）；
  文档已逐字写明，但若后续有人只跑 `rg`，仍会得到「零命中」的错觉。

---

## §M4-r3 补轮 r3（`REQ-20260921-006-m4-r3`）—— F5′ / F7 / F6

### r3-0 开工快照（与任务书字面一致，无漂移）

| 项 | 读数 | 命令 |
|---|---|---|
| 真实仓库 `HEAD` | **`a9e3a57`** | `git -C /Users/wooyinq/personal/deep-healing rev-parse --short HEAD` |
| `git status --porcelain` | **0 行** | 同上 `\| wc -l` |
| `ulimit -n` | **4096** | `ulimit -n`（F7 的 fd 判据分母） |
| 本轮写集 | `cli.py` / `live.py` / `tests/test_live_observation.py` / `V0_SELF_TEST.md` / `06` / `03` / `V0_M4.sha256` / `spikes/s16-liveworld/logs/m4-r3-*.py` | 任务书 §3 |

### r3-1【F5′ · MEDIUM 收口】`run --ws-port` 监听顺序前移 + 外部可连判据

**根因**（architect 已独立定位，我读源码复核）：`cli.py` 里 `_start_live_listener(...)` 排在
`kernel.run(args.ticks)` **之后** ⇒ 监听只在整轮 tick 跑完之后才 bind，随即打印 JSON 并返回、进程退出。
监听**确实会建立**（`listening=true` 不是谎报），但窗口落在**进程收尾**：真子进程下采样
**78,898 次 / 0 命中**，窗口上界 **≈ 22µs（不可观测）**。
**问题不是「没监听」，是「声明了一个外部无法观测的窗口，却把它当可用观察面」** —— 而该字段被
`AC-M4-9④` 当证据引用。⇒ **修行为，不改措辞。**

**修法**：① 把 `_start_live_listener(...)` 移到 `kernel.run()` **之前**；② tick 循环结束后在
`finally` 里**显式 `stop()`**（`_stop_live_channels()`，幂等）。

**为何不改契约**：`01_m4_design.md` D-M4-4 原文 =「显式给端口时**真的监听并服务同一只读端点**」
⇒ 这是实现**自己已冻结的设计**，顺序修正只是让它成真。

**判据以真子进程为准**（内存打点只能证明「bind 成功过」，不得作为可观测性判据）。
探针用**阻塞 `connect`**（`socket.create_connection`），**不用** `connect_ex`（带超时时它返回
`EINPROGRESS` 而非 0 ⇒ **假命中**；architect 裁决 §6.3）。命中 = connect 成功 **且** 读到合法状态行。

| 树 | 命令（workdir = `<ws>`） | exit | 外部连入 | refused | 响应首行 |
|---|---|---|---|---|---|
| **修前**（`/tmp/m4r3-prefix/02_source/v0_skeleton/kernel`，仅顺序回退） | `python3 spikes/s16-liveworld/logs/m4-r3-wsport-probe.py --kernel-root /tmp/m4r3-prefix/02_source/v0_skeleton/kernel` | **1（FAIL）** | **0** | 64346 | — |
| **修后**（交付树） | `python3 spikes/s16-liveworld/logs/m4-r3-wsport-probe.py` | **0（PASS）** | **22912** | 3970 | **`HTTP/1.1 200 OK`** |
| 负向对照（修后，`--ws-port 0`） | 同一命令的第二臂 | 0 | **0** | 57846 | — |

- 修前 `run` **自报** `live_channel.listening = true`，而外部 **0 次连入** ⇒ 声明与事实脱钩（可证伪的 RED）。
- 进程内判据：`tests/test_live_observation.py::test_run_ws_port_is_externally_reachable_during_the_tick_loop`
  ⇒ **PASS**（同一命令内含 `--ws-port 0` 负向对照；**判据不恒绿**）。
- 第三方**一条命令复跑**：`python3 spikes/s16-liveworld/logs/m4-r3-wsport-probe.py`（exit 0 = PASS）。

**副作用登记（`C-18`）**：顺序前移后，「时钟语义派生失败」会在**写产物之前** fail-closed ——
旧顺序先把 `events.jsonl` / `checkpoints` 写完再 `exit 1`（留半截产物）。与 `_refuse_unusable_output_dir`
的「不留下半截日志」**同向**，**更** fail-closed。`--ws-port 0`（默认）**不进**该分支 ⇒
21 处既有 `--ws-port 0` 用例零影响（全量 pytest 已复验，见 r3-5）。

### r3-2【F7 · MEDIUM】普通 HTTP 观察路径并发上限 + 干净收尾

**根因链**（architect 独立发现 + 我读源码复核）：`live.py` 的 `max_observers`（默认 8）**只约束 SSE
订阅者**；`/live/state` 这条普通 HTTP 路径**没有并发上限** ⇒ `ThreadingHTTPServer` 每连接一线程 ⇒
fd 打满 ⇒ 封存 `live_state.json` 时 `OSError: [Errno 24] Too many open files` ⇒
`Fatal Python error: _enter_buffered_busy … at interpreter shutdown, possibly due to daemon threads`
⇒ **SIGABRT**。封存路径定位：`cli.py` 的 `finally` 里封存段**无 try/except**，且 `server.stop()`
排在 `write_text` **之后** ⇒ 写失败时摘要不打印、`stop()` 被跳过、daemon 线程不停。
**因果方向：daemon 线程未停是果，跳过 `stop()` 是因。**

**修法（三处，均在写集内）**：

1. **请求级**并发上限 `max_http_inflight = max(2, 2 × max_observers)`（挡 **CPU 放大**：
   `state_projection()` 每次请求都重建 `world.to_state()` + 两次哈希）；
2. **连接级**并发上限 `max_http_connections = max(4, 4 × max_observers)` + **空闲读超时**
   `REQUEST_IDLE_TIMEOUT_S = 5.0`（挡 **fd**）；两级超限均 ⇒ 结构化 **`503 E_HTTP_QUOTA`** 并**立即关连接**
   （不排队、不静默）；
3. **封存 fail-closed**：封存段套 `try/except OSError`，`server.stop()` 放进**内层 `finally`**
   ⇒ 它在**任何**封存失败路径上都仍被执行；封存异常转**结构化错误**（非 0 退出 + stderr 一行诊断 +
   stdout 一行机器可读 JSON）。

> **自审发现（第一版不够，靠仪表抓出来，如实登记）**：只加**请求级**上限时，fd 高水位仍到
> **3739 / 4096（91.3%）** —— 因为**空闲 keep-alive 连接不占在途额度，却一直占着 1 线程 + 1 fd**。
> 补上连接级上限 + 空闲读超时后，同一负载下 fd 高水位 **76 / 4096（1.86%）**。

**RED → GREEN（同一探针、同一负载：4 个无间隔外部观察者 × keep-alive 不主动关闭，`--ticks 200`）**

| 树 | fd 高水位 | 占 `ulimit -n` | 服务成功 200 | **结构化 503** | exit | `live_state.json` |
|---|---|---|---|---|---|---|
| **修前** | **3264** | **79.7%** | 3287 | **0** | 0 | 合法 |
| **修后（第一版：只请求级上限）** | **3739** | **91.3%** | 3932 | 0 | 0 | 合法 |
| **修后（终版：两级上限 + 空闲超时）** | **76** | **1.86%** | 32 | **2815** | **0** | **合法** |

命令：`python3 spikes/s16-liveworld/logs/m4-r3-live-fd-saturation-probe.py --max-held 7000 --raise-nofile 20000 --ticks 200 --hold-seconds 45`

- **「0 次 503」是修前的判据形态**（无上限）；修后 **2815 次结构化拒绝** ⇒ 上限真的在挡。
- 修后 fd 高水位 **76**，距 `ulimit -n = 4096` **远**。

**关闭判据 4 条**

| # | 判据 | 读数 | 判定 |
|---|---|---|---|
| ① | 4 个无间隔观察者下 exit = 0，**无** `Too many open files`，**无** `Fatal Python error` | n=3：exits **`[0, 0, 0]`**；stderr **空**；`stderr_errno24=false`、`stderr_buffered_busy=false` | **PASS** |
| ② | 循环墙钟相对基线**有界**（**所采用的界 = 10 × 基线**，另设绝对下限 30s） | 基线 **`2.712 / 2.719 / 2.673s`**；4 观察者 **`18.271 / 17.174 / 18.066s`** ⇒ **6.74× / 6.32× / 6.76×**（全部 ≤ 10×） | **PASS** |
| ③ | `live_state.json` 与本次运行产物**完整可读** | n=3 `all_sealed = true` | **PASS** |
| ④ | 4 观察者臂按 **n=3** 跑，**三次全不崩** 且 **fd 高水位未逼近上限** | exits `[0,0,0]`；fd 峰值 **`[45, 45, 45]`**（= **1.1%** × 4096） | **PASS** |

命令：`python3 spikes/s16-liveworld/logs/m4-r3-live-load-probe.py --observers 0 --repeats 3 --ticks 3000 --label FINAL`
（4 观察者臂同命令 `--observers 4`）。

> **「机制未被激活」与「缺陷不成立」的区别（硬性，不许混）**：本机 4-观察者 churn 臂里
> **在途请求 ≤ 4 < 上限 16** ⇒ 该臂 **0 次 503** —— 那是**上限没被触发**，**不是**「没有上限」。
> 上限是否生效由**饱和臂**单独证明（上表：修前 0 次 503 / fd 79.7% ⇒ 修后 2815 次 503 / fd 1.86%）。
> **另一条如实登记**：本机**未能**复现 architect 的 `exit = -6`（SIGABRT）**本身** —— 饱和臂在修前
> 把 fd 打到 **79.7%** 时先被**探针自身**的 fd 上限挡住，服务端没走到 `Errno 24`。故本轮判定为
> **「机制已被激活（fd 打到 79.7%、0 次拒绝）但崩溃未在本机复现」**，**不**判「缺陷不成立」
> （architect 有落盘证据，我不撤回）。

**封存注入（关闭判据 2 的 ① 注入 / ② 负向对照）**

注入方式（无 monkeypatch、走真 CLI 子进程、**可确定性复现**）：把 `--out/live_state.json`
**建成目录** ⇒ `write_text()` 抛 `IsADirectoryError`（`OSError` 子类，与 `Errno 24` 同类）。
在场 4 个 SSE 观察者 ⇒ 收尾时 daemon 线程确实活着（`sse_clients_connected = 4`）。

| 树 | exit | stderr 结构化错误 | 裸 `Traceback` | stdout JSON | `server.stop()` | `_enter_buffered_busy` |
|---|---|---|---|---|---|---|
| **修前** | 1 | **无** | **有** | **无**（摘要被跳过） | **未执行** | 无 |
| **修后** | **1** | **`E_LIVE_STATE_SEAL_FAILED`** | **无** | **有**（`sealed=false`、`server_stopped=true`） | **执行**（spy 计数 **1**） | **无** |
| 负向对照（不注入，修后） | **0** | **不误报** | 无 | 有 | 执行 | 无 |

命令：`python3 spikes/s16-liveworld/logs/m4-r3-seal-injection-probe.py`（修前 RED 加
`--kernel-root /tmp/m4r3-prefix/02_source/v0_skeleton/kernel`）。修前**无 stdout JSON** 正是
「异常穿出 `finally` ⇒ 摘要不打印、`stop()` 被跳过」的直接读数。
进程内 spy 判据：`tests/test_live_observation.py::test_live_state_sealing_failure_is_structured_and_still_stops_the_server`
（负向对照 `test_clean_live_run_does_not_report_a_sealing_error`）⇒ 双绿。

**判据 3（观察者负载下 tick 推进与墙钟语义不得改变（或有界））**：
`tests/test_live_observation.py::test_observer_load_keeps_tick_advance_and_wall_clock_bounded` ⇒
`ticks` 两臂都 **200**（推进语义**不变**）；循环墙钟 `1.0049s → 1.5498s`（界 10.05s）；
在途峰值 **4 ≤ 16**（上限真的约束了并发）。

### r3-3【F6 · MEDIUM】计时判据在负载下假红（`N-3a`）—— 容差锚定实测窗口

**对象**：`tests/test_live_observation.py` 的 `test_pace_is_identical_with_zero_and_two_observers`
（原断言 `abs(zero - two) <= 3`，窗口 `time.sleep(2.0)` + `pace = 0.02`）。
**缺陷性质**：判据在 CPU 争用下**假红**（与「假绿」互为镜像，同样摧毁判据价值），**不影响产品正确性**。

**修法**：容差锚定到**窗口实测墙钟 / pace**：`expected = window / PACE_S_PER_TICK`，
容差 `max(3 tick, 3% × expected)`；两臂再比**归一化速率**。判据本体抽为 `_pace_failures()`，
**正向用例与「去节流」注入共用同一条判据**（注入才可能让它变红）。

**关闭判据 ①（4 份并发 ⇒ 不假红）**：`sh /tmp/m4r3_f6_concurrent.sh`

| 树 | 4 份并发读数（`runs`） | 判定 |
|---|---|---|
| **修前**（固定 `\|Δ\| ≤ 3`） | **3/4 failed**：`100 vs 104` / `104 vs 100` / `104 vs 99` | **假红已复现** |
| **修后**（锚定实测窗口） | **4/4 passed** | **PASS** |

**关闭判据 ②（去节流注入 ⇒ 该判据仍必须红）**：
`tests/test_live_observation.py::test_unthrottled_loop_turns_the_pace_criterion_red` ⇒ **PASS**。
读数：窗口 **2.0382s** 内推进 **2883 tick**（锚定期望 **101.9**）⇒ 判据报出失败（**红**）。

**旁证（锚定是承重的）**：修后正向用例本机实测窗口 **2.0746s**（不是 2.0s）⇒ 固定阈值下
`\|104 − 100\| = 4 > 3` **会假红**；锚定后 `104 vs 期望 103.7` **通过**。

### r3-4 `V0_M4.sha256` 重取登记（**硬性**）

- **重取理由**：本轮改了 `02_source/v0_skeleton/kernel/deephealing_kernel/{cli.py,live.py}`、
  `02_source/v0_skeleton/kernel/tests/test_live_observation.py`、`V0_SELF_TEST.md`，
  并**新增 4 个** `spikes/s16-liveworld/logs/m4-r3-*.py` 探针 ⇒ 冻结面内容变化。
- **重取前清单自身 sha256**：`7021ae158e965917e7fe2589e32ec2adf32493e5a071bb85742b8cb0e263c0c6`
  （`V0_M4.sha256`，201 条）。
- **变更面（= 重取前 `shasum -a 256 -c V0_M4.sha256` 的非 OK 集合，逐字读数；exit 1 / 197 OK / 4 FAILED）**：
  ```
  02_source/v0_skeleton/kernel/deephealing_kernel/cli.py: FAILED
  02_source/v0_skeleton/kernel/deephealing_kernel/live.py: FAILED
  02_source/v0_skeleton/kernel/tests/test_live_observation.py: FAILED
  V0_SELF_TEST.md: FAILED
  ```
  另**新增 4 个面内文件**（旧清单不可见）：`spikes/s16-liveworld/logs/m4-r3-wsport-probe.py`、
  `m4-r3-live-load-probe.py`、`m4-r3-live-fd-saturation-probe.py`、`m4-r3-seal-injection-probe.py`；
  **消失 0**。
- **逐文件前后哈希**（「重取前」= 重取前清单记录值；「重取后」= 盘上实算值）：

| 文件 | 重取前 sha256 | 重取后 sha256 |
|---|---|---|
| `02_source/v0_skeleton/kernel/deephealing_kernel/cli.py` | `1b94b376…24fd8bd` | `019a9c6d…a5796eda` |
| `02_source/v0_skeleton/kernel/deephealing_kernel/live.py` | `f7877e3d…139b2f03` | `7f04ecb1…645ec4c4` |
| `02_source/v0_skeleton/kernel/tests/test_live_observation.py` | `1c7fbc08…724aa399` | `3380dac5…761bbf5d` |
| `V0_SELF_TEST.md` | `65c81923…77d103d95` | `83acf10f…4d404196` |
| `06_v0_m4_self_test.md` / `03_artisan_self_test.log` / `V0_M4.sha256` | `18d0a9d2…fe90d207` / `c4184cff…fbb651a1f` / `7021ae15…e263c0c6` | **自指声明**：这三个文件（含清单自身）**无法在面内记录自身重取后的哈希**（自哈希不可能）⇒ 其重取后哈希**从重取后的 `V0_M4.sha256` 逐字可读** |

- **重取后复验读数**：见 r3-5（`take A` = 写入本段之前的一次重取；`take B` = 本段写入后**定稿重取**）。
  两 take 的**文件集完全相同**（本段写入后不再增删文件）⇒ 条目数与「0 非 OK」性质逐项相同。

### r3-5 复验读数（收尾）

| 项 | 命令（workdir） | exit | 读数 |
|---|---|---|---|
| 冻结面自校验 | `shasum -a 256 -c V0_M4.sha256`（`<ws>`） | **0** | **205 OK / 0 非 OK** |
| `02_source` 覆盖谓词 | `comm -13 <(sed 's/ | .*//' manifest.txt \| sort) <(find . -type f ! -name manifest.txt \| sed 's\|^\./\|\|' \| sort)`（`<ws>/02_source`） | — | **空输出**（`02_source` 条目 **160 == 160**） |
| manifest 覆盖谓词 | `comm -13 <(sed 's/ \| .*//' manifest.txt \| sort) <(find . -type f ! -name manifest.txt \| sed 's\|^\./\|\|' \| sort)`（`<ws>/02_source`） | — | **空输出** |
| 规格校验 | `bash verify_specs.sh --quiet`（`<ws>/02_source`） | **0** | `OK (130 checks passed, 0 skipped)` |
| 内核全量 pytest | `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider`（`<kernel>`） | **0** | 见 `03` M4-r3 · V0 段（passed / skipped 数） |
| 收尾残渣 | `find 02_source \( -name '__pycache__' -o -name '.pytest_cache' -o -name '*.pyc' \) \| wc -l` | — | **0** |
| 真实仓库 | `git -C /Users/wooyinq/personal/deep-healing rev-parse --short HEAD && git status --porcelain \| wc -l` | 0 | `a9e3a57` / **0 行** |
| 内容包零改动 | `diff -r <repo>/v0/02_source/v0_skeleton/districts <ws>/02_source/v0_skeleton/districts` | **0** | 逐字节相同 |

### r3-6 本轮**未做**的事（如实）

- 未改 `04_sentinel_test_report.md` / `05_raven_risk_report.md` / `.pm_notes.md` / `.pm_ruling-*.md` /
  `.architect-ruling-*.md`（**只读面**）；未改内容包 `districts/**`；未改真实仓库。
- 未 `commit` / `push` / `PR` / `deploy`。
- **未复现** architect 的 `exit = -6`（SIGABRT）本身 —— 机制被激活但崩溃未在本机复现（见 r3-2 的
  区别声明）。**不**据此判「缺陷不成立」。
- **未**用「把观察者数压到 0」或「加 sleep」的方式让判据变绿（饱和臂是**加**负载）。
- 未做 §2 之外的顺手重构；未改本轮未点名的文件。

> **交给 architect 读盘核验**（本轮由 architect 独占收口，artisan 不宣布整轮完成）。


---

## §M4-r4 补轮 r4（`REQ-20260921-006-m4-r4`）—— **F7 重开（accept 层配额）· 仍未关闭，如实登记**

> 结论先说：**F7 仍未关闭**（① ② ③ FAIL / ④ PASS / ⑤ PASS）。本轮按要求把配额**前移到 accept 层**
> （代码面成立、独立可验），但**同 regime 修后仍复现 `exit=-6` + fd 打到 4096**。
> 新增证据把剩余机制**定位到「每连接 fd 延迟释放」**（不是并发连接数、也不是 stderr 写路径）。
> 按任务书 §2.3 判据 ⑤ 的纪律：**未关闭就是未关闭**，不写成关闭。

### r4-0 开工快照（无漂移）

| 项 | 读数 | 命令（workdir） |
|---|---|---|
| 真实仓库 `HEAD` | **`a9e3a57`** | `git -C /Users/wooyinq/personal/deep-healing rev-parse --short HEAD` |
| `porcelain` | **0 行** | 同上 `\| wc -l` |
| `ulimit -n` | **4096**（探针**不**抬它） | `ulimit -n` |
| 写入通道 | **本派单进程**（`hermes -p artisan chat --query-file .task-artisan-m4-r4.pointer.txt --oneshot`，PID 53997）；`.artisan.progress.json` note 内带通道标记 | `ps -o pid,etime,command -p $(cat .task-artisan-m4-r4.pid)` |

### r4-1 取证 regime：**与裁决 §2.1 逐字一致**（关键：我第一版探针抓不到）

裁决的 regime 与 r3 探针的差别不在「观察者数量/间隔」，而在**客户端形态**：

| 要素 | architect 探针（裁决 §2.1，能复现） | r3 探针（抓不到） | 我的 r4 探针 |
|---|---|---|---|
| 请求 | `GET /live/state HTTP/1.0` | `HTTP/1.1` + `Connection: close` | `--close-mode arch` = HTTP/1.0 |
| 关闭时机 | `recv(64)` 后立即 `close()`（**只读 64B**） | 读完状态行后关 | 同 architect |
| 被测进程 stderr | 落**文件** | PIPE（被 drain） | `--stderr-mode file`（另有 devnull 对照） |
| 观察者数 / 间隔 | 4 / 无间隔 | 4 / 无间隔 | 同 |

> **实测（本机，我的探针）：** 同一负载下 `after-reply`（读完状态行）⇒ fd 峰值 **45**（机制**未激活**）；
> `immediate`（发完即关、不读）⇒ **47**；`bare`（不发请求）⇒ **40**；**只有 `arch` 形态** ⇒ **4129**。
> ⇒ 「4 个无间隔观察者」这个描述本身**不足以**激活机制；**只读 64B 即关**才是触发条件。

### r4-2 判据 ⑤ · 修前 RED（**同一探针、修前树**）

- 探针：`spikes/s16-liveworld/logs/m4-r4-arch-f7-probe-reference.py`（architect 探针逐字副本，仅改输出目录）
  读数：`spikes/s16-liveworld/logs/m4-r4-red-arch-regime.txt`
- 命令（workdir `<ws>`）：`python3 spikes/s16-liveworld/logs/m4-r4-arch-f7-probe-reference.py`，exit **0**（探针自身）

| 臂 | exit | fd 峰值 | `live_state.json` | Errno 24 | Fatal Python error | 摘要 JSON |
|---|---|---|---|---|---|---|
| 4 观察者 #0/#1/#2 | **-6 / -6 / -6** | **4129 / 4129 / 4127** | **缺 / 缺 / 缺** | True ×3 | True ×3 | 缺 ×3 |
| 对照 0 观察者 | **0** | 40 | 有 | False | False | 有 |

⇒ **⑤ PASS**（探针能抓到该机制；「未复现」不再被当成关闭）。stderr 形态：`obs4_run0.err` **110,865 行**，
其中 `BrokenPipeError`/`ConnectionResetError` 1,607/12，`Errno 24` 1 次，`_enter_buffered_busy` 1 次。

### r4-3 修法：配额前移到 **accept 层**（`live.py`）

- 新增 `LiveHTTPServer(ThreadingHTTPServer)`：覆写 `process_request()`，**在 `super().process_request()`
  （即起线程）之前**调 `LiveServer.admit_accept()`；超限 ⇒ `reject_at_accept()`（`setblocking(False)` +
  一次 `send()` 回结构化 `503 E_HTTP_QUOTA` + **立即 close**），**不 spawn 线程** ⇒ **fd 与线程同时有界**。
- `admit_accept()` 的计数就是原来的 `http_connections`（**计数点上移到 accept 那一刻**）；
  handler 的 `finish()` 对称调 `release_accept()`；`setup()` 不再计数。
- `_dispatch()` 里原来那级「连接级上限」**删除**（它判的时候 fd 已被消耗 = 老路）；`/live/health`
  新增 `connection_admission: "accept"`（可观测）。
- **未回退 F5′**（`cli.py` 零改动：`_start_live_listener` 仍在 `kernel.run()` 之前，行号未动）。

**修法自身的独立验证（gate 真的在 accept 层工作）**：跑中读 `/live/health`（`/tmp/m4r4_diag6.py`）：

| t | fd（lsof，全部 `(CLOSED)`） | `http_connections` | `peak` | `connection_rejections` | `max` |
|---|---|---|---|---|---|
| 0.9s | 1472 | 1 | **6** | 0 | 32 |
| 1.8s | 2816 | 1 | **6** | 0 | 32 |
| 2.7s | 3996 | 1 | **6** | 0 | 32 |

⇒ 并发连接数被**死死压在 6 ≤ 32**（上限根本不必触发），而**进程 fd 仍在 2.7s 内涨到 3996**。
进程内同口径复验：`/tmp/m4r4_diag5.py` ⇒ `http_connections_peak = 5`（cap 8）、`rejections = 0`。
⇒ **配额位置不是剩余机制的原因**（这是本轮最重要的新读数）。

### r4-4 修后同 regime 复测（**仍 RED**）

命令（workdir `<ws>`）：`python3 spikes/s16-liveworld/logs/m4-r4-f7-accept-churn-probe.py --path live --observers 4 --repeats 3 --ticks 3000 --close-mode arch --label GREEN-live`
（exit **1**；读数 `spikes/s16-liveworld/logs/m4-r4-green-live.txt`）

| 臂 | exit | fd 峰值 | 产物 | Errno 24 | Fatal | thread 峰值 |
|---|---|---|---|---|---|---|
| `live` 4 观察者 ×3 | **-6 / -6 / -6** | **4125 / 4128 / 4128**（100.7%） | **缺 ×3** | ×3 | ×3 | 4092 |

- `run --ws-port` 路径同 regime：**exit -6 / fd 4126 / 摘要 JSON 缺 / Errno 24 + Fatal**
  （`m4-r4-green-run.txt`）⇒ ② 同样 **FAIL**。
- 反向对照（修后，0 观察者）：**exit 0 / fd 40（0.98%）/ 产物齐**（`m4-r4-green-control.txt`）⇒ ④ **PASS**。
- **排除 stderr 写路径**：`--stderr-mode devnull`（traceback 全部丢弃）⇒ 仍 **fd 4129 / exit -6**
  （`m4-r4-devnull-probe.txt`）⇒ 泄漏**不是** stderr 管道/锁造成的。

### r4-5 剩余机制（新证据 · 定位到「每连接 fd 延迟释放」）

`/tmp/m4r4_diag4.py` 按 fd 类型分解（跑中每 1s）：

```
t=1.1 total=1820 types={'REG': 34, 'IPv4': 1782, ...}
t=3.3 total=4113 types={'REG': 34, 'IPv4': 4076, ...}
```

- 泄漏的 fd **全部是 `IPv4`，TCP 状态 `(CLOSED)`**（`/tmp/m4r4_diag6.py`：`states={'(CLOSED)': 3995, '(LISTEN)': 1}`）；
- 增长速率 ≈ **1,500 连接/s ≈ 客户端成功连接速率**（即**每成功一个连接留一个 fd**），
  而并发连接计数只有 **6** ⇒ **不是并发堆积，是「连接结束后 fd 没被同步释放」**；
- 串行复验（`/tmp/m4r4_diag7.py`：同一 arch 形态请求 ×20，串行）⇒ **不泄漏**（IPv4 恒为 1）
  ⇒ 泄漏需要**并发**（多个 handler 线程同时在 `handle_error`/收尾路径上）；
- fd 数在进程收尾阶段**缓慢回落**（4079 → 2232，8s）⇒ 与「**延迟释放 / 依赖 GC 回收**」一致，
  泄漏速度 > 回收速度 ⇒ 3s 内打满 4096 ⇒ 封存 `events.jsonl`/`live_state.json` 时 `Errno 24`
  ⇒ daemon 线程活到解释器 finalize ⇒ `_enter_buffered_busy` ⇒ **SIGABRT(-6)**。

**已试过 / 卡在哪 / 建议下一步**：

- 已试过：accept 层准入（本轮）、请求级上限（r3）、连接级上限（r3）、空闲读超时（r3）、
  封存 fail-closed（r3）；本轮另用 `stderr→devnull`、`immediate/bare` 形态、串行 vs 并发对照排除混淆项。
- 卡在哪：**剩余缺陷不在「配额判在哪一层」**，而在 **handler 收尾路径上 fd 的释放不是同步的**
  （`ThreadingHTTPServer` 每连接一线程；异常路径下 `StreamRequestHandler.finish()` 的
  `wfile/rfile` 关闭 + `shutdown_request()` 的 `socket.close()` 组合在**并发**时会让 fd 落在
  「延迟关闭」上，只有 GC 才真正还回去）。**只改配额位置无法封堵它**。
- 建议下一步（一条最小可行动的修法，留给下一轮/human）：
  在 `LiveHandler.finish()` 的 `finally` 里**确定性释放连接**：逐个 `try/except` 关闭
  `wfile`/`rfile`，再**强制**关掉原始 socket（含把 `socket._io_refs` 归零后 `_real_close()`，
  或改用 `os.close(fd)` + `detach()`），并以「**连接结束后 fd 计数回到基线**」为判据
  （判据：并发 churn 下 `lsof` IPv4 峰值 ≤ 上限 + 常数，且**不再随时间线性增长**）。
  这一步必须在**同一 regime** 下用 `m4-r4-f7-accept-churn-probe.py --close-mode arch` 取证。

### r4-6 逐条判定（任务书 §2.3）

| # | 判据 | 读数 | 判定 |
|---|---|---|---|
| ① | `live` 4 观察者 n=3：exit 全 0 / 无 Errno 24 / 无 Fatal / `live_state.json` 在且可解析 | exit **-6×3**；fd 4125/4128/4128；产物**缺×3**；Errno 24 ×3；Fatal ×3 | **FAIL** |
| ② | `run --ws-port` 4 观察者：exit 全 0 / 摘要 JSON 可解析 / 无 Errno 24 / 无 Fatal | n=1（预算所限）：exit **-6**、摘要 JSON **缺**、Errno 24 + Fatal | **FAIL**（n=2 未跑满） |
| ③ | 两条路径 fd 高水位**显著低于 4096** | `live` **4125~4129（100.7%）**；`run` **4126（100.7%）** | **FAIL** |
| ④ | 反向对照（0 观察者 / `--ws-port 0`）不回归 | 修后 0 观察者：exit **0**、fd **40（0.98%）**、产物齐；修前同臂同读数 | **PASS** |
| ⑤ | 修前 RED（同一探针） | 修前 4 观察者 ×3：exit **-6/-6/-6**、fd **4129/4129/4127**、产物缺、Errno 24 + Fatal；0 观察者 exit 0 | **PASS** |

⇒ **F7 = 仍未关闭**（①②③ FAIL）。按裁决口径：M4 迭代预算已用尽（r1→r4 = max_iteration）⇒
建议 architect 走 `exceed_iteration_human_intervene`，并把 r4-5 的「确定性释放 fd」作为下一轮/human 的
最小可行动作（**不要**再调倍数、不要再压负载）。

### r4-7 `V0_M4.sha256` 重取登记（**硬性**）

- **重取理由**：本轮改了 `02_source/v0_skeleton/kernel/deephealing_kernel/live.py`（accept 层配额），
  并**新增 5 个** `spikes/s16-liveworld/logs/m4-r4-*`（探针 + 读数）。
- **重取前**：清单自身 sha256 `852c14ef37d8bbe483b188410dc1299e6cf1e04c2bf2d4165eb24de600dabdcb`（205 条），
  `shasum -a 256 -c` ⇒ exit **1** / **204 OK / 1 FAILED**，非 OK 集合（逐字）：
  `02_source/v0_skeleton/kernel/deephealing_kernel/live.py: FAILED`（**单文件变更面**，与声明一致）。
- **重取后**：清单自身 sha256 `d7ba62300fa82ef3ac68a4f8f5ebb2e7882816ab27d3d60bd275189e5b233b03`（**210 条**），
  `shasum -a 256 -c V0_M4.sha256` ⇒ exit **0** / **210 OK / 0 非 OK**。
- 逐文件前后哈希：

| 文件 | 重取前 | 重取后 |
|---|---|---|
| `02_source/v0_skeleton/kernel/deephealing_kernel/live.py` | `7f04ecb1…645ec4c4` | `c36f3142…3c2a58f0` |
| `02_source/v0_skeleton/kernel/tests/test_live_observation.py` | `3380dac5…761bbf5d` | **未改**（同哈希） |
| `V0_SELF_TEST.md` | `83acf10f…4d404196` | **未改**（同哈希） |
| `06` / `03` / `V0_M4.sha256` | — | **自指声明**：这三个文件（含清单自身）无法在面内记录自身重取后的哈希 |

### r4-8 复验读数（收尾）

| 项 | 命令（workdir） | exit | 读数 |
|---|---|---|---|
| 冻结面自校验 | `shasum -a 256 -c V0_M4.sha256`（`<ws>`） | **0** | **210 OK / 0 非 OK** |
| 规格校验 | `bash verify_specs.sh --quiet`（`<ws>/02_source`） | **0** | `OK (130 checks passed, 0 skipped)` |
| 内核全量 pytest | `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider`（`<kernel>`） | 见 `03` | 见 `03` M4-r4 · V0 段 |
| 观察面单测（定向） | 同上 `tests/test_live_observation.py` | **0** | **18 passed**（含 r3 的连接级上限用例，accept 层 503 形态未破坏判据） |
| 收尾残渣 | `find 02_source \( -name '__pycache__' -o -name '.pytest_cache' -o -name '*.pyc' \) \| wc -l` | — | **0**（诊断期产生的 7 个已移出到 `/tmp/m4r4-attic`） |
| 真实仓库 | `git -C /Users/wooyinq/personal/deep-healing rev-parse --short HEAD && git status --porcelain \| wc -l` | 0 | `a9e3a57` / **0 行** |

### r4-9 本轮**未做**的事（如实）

- **未**加新单测（`tests/test_live_observation.py` 未改）：本轮修法**不能**让 F7 关闭，
  给一个「看起来绿」的新判据会误导复核者；判据面留给下一轮与「确定性释放 fd」的修法一起加。
- **未**跑满 ② 的 n=2（预算所限，只取了 n=1）；**未**在修前副本上取 `run` 路径 RED
  （副本缺 `tools/` 依赖布局，修好后预算已到；修前 `run` 的 RED 以裁决 §2.1 的 `-6 / -6` 为准）。
- **未**改 `04` / `05` / `.pm_notes.md` / `.pm_ruling-*.md` / `.architect-*.md`（只读面）；
  **未**改内容包 `districts/**`；**未**改真实仓库；**未** commit/push/PR/deploy。
- **未**回退 F5′（监听前移）；**未**靠加 sleep / 降负载 / 抬 `RLIMIT_NOFILE` 让读数变绿
  （`probe_nofile_raised: false`，探针全程 `ulimit -n = 4096`）。

> **交给 architect 读盘核验**（本轮由 architect 独占收口，artisan 不宣布整轮完成）。
