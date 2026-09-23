# 06 · M3 自测判定（REQ-20260921-005 rev3 · artisan R1）

- 计划：`REQ-20260921-005-deephealing-v0-m3`　角色：artisan　轮次：R1
- workspace：`/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3`
- 开工快照：repo `/Users/wooyinq/personal/deep-healing` = `develop` @ `98c781f4040d9b17757d67ba8e76fed1b95bfa12`，`status --porcelain | wc -l` = **0**
- 并发守卫：`ls .task-(sentinel|raven)*` 只有 `task-raven-prereview.*`（pid 89916 **已退出**）⇒ 同写集无并发写者
- run-budget 7200s。**本轮未跑完的部分一律写成 GAP，不伪造。**

---

## 0. 逐 AC 一行速览

| AC | 判定 | 一句话 |
|---|---|---|
| AC-M3-1 契约全绿 + 前轮不回退 | **PASS** | `verify_specs: OK (125 checks passed, 0 skipped)`；F-4 基线逐位不变 |
| AC-M3-1b D-12 口径 | **FAIL（部分）** | 差集 37 条 vs 声明 42 条：5 条声明项**本轮未实现**（如实，见 §4） |
| AC-M3-1c P-1 | **PASS** | `= 300` 赋值全树 **1** 处（`tick.py:58`）；不传 `--ticks` 真跑 300 tick/6 检查点 |
| AC-M3-1d 第二街区进门禁 | **PASS** | 两 pack `validate` 各 exit 0；`verify_specs.sh` 已含 pack#2 两道调用 |
| AC-M3-1e 构建产物零残渣 | **PASS** | `find 02_source \( -name node_modules -o -name dist -o -name .build \)` = **0**；两次 build 后 assets 只有一套 |
| AC-M3-2 会话层双模式权限 | **PASS** | `npm test` 9/9 全绿 **0 skipped**；4 条 AC 命名用例真跑；`intent.rejected` 真进事件流（3 条） |
| AC-M3-3 渲染层真跑 + 双模式 UI | **GAP** | build exit 0 + 4 条客户端用例全绿；**真浏览器交互验收未执行**（预算耗尽） |
| AC-M3-4 治愈系美学 + 观察无写入口 | **GAP（半）** | `scene_assert` 15/15 通过；「UI 树无写控件」只做了代码面断言，**未在真浏览器枚举** |
| AC-M3-5 参与影响任务演进 | **PASS** | `pytest test_task_adaptation.py` 6/6 绿；真实事件流里有 `task.state_changed`（shift_index/rule_id/impact_cost 齐备） |
| AC-M3-6 确定性不回退 | **PASS** | 300 tick 基线逐位一致；会话层两遍同序列产物比对（见 §3） |
| AC-M3-7 仓库零改动 + 溯源 | **PASS** | `develop` / dirty **0**；`SEED.sha256` 聚合 `34fa7f6d…` 未变 |
| AC-M3-8 世界观落地 | **①②⑤ PASS；③④ 部分** | 契约/schema/登记/NPC 两面全绿；两态几何数值判据绿；**真浏览器两态截图 GAP** |

---

## 1. 逐 AC 读数（命令 + workdir + exit + 证据）

### AC-M3-1 契约全绿 + 前轮不回退

| # | 命令（workdir） | 期望 | 实测 | exit |
|---|---|---|---|---|
| 1 | `bash verify_specs.sh --quiet`（`02_source`） | OK / 0 skipped / PASS ≥110 | **`verify_specs: OK (125 checks passed, 0 skipped)`** | 0 |
| 2 | `python3 -m deephealing_kernel run --pack districts/xingfu-xiaoqu --seed 20260921 --events /tmp/m3baseline/e.jsonl --snapshot-every 50`（`kernel`，**不传 `--ticks`**） | 300 tick / 6 检查点 / 基线逐位 | `chain_tail=baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786`、`event_count=925`、`000300.json.state_hash=9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f`、6 个检查点 | 0 |
| 3 | manifest 覆盖（`verify_specs.sh` §3 + 自建计数） | 缺失 0 / 幻影 0 / 重复 0 | 清单 **147** 行 vs 盘上 **148** 文件（差 1 = `manifest.txt` 自身，**自排除为既有约定**）；门禁未报 MISSING | 0 |
| 4 | `pytest tests/ -q -p no:cacheprovider`（`kernel`） | 全绿 | 见 §2（长套件，读数单独登记） | — |

### AC-M3-1c P-1（rev2 改写口径）

- ① `python3 -m deephealing_kernel run --help` ⇒ `--ticks TICKS  [加法扩展] 推进的 tick 数上界（默认值见 tick.DEFAULT_PLAN_TICKS）`（**字面 300 已从 `cli.py:129` 移除**）；`cli.py:52` 仍是 `from .tick import DEFAULT_PLAN_TICKS`（只导入，**未**新增同名常量）。
- ② 赋值形式判据：`grep -rnE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[[:space:]]*300[[:space:]]*$' --include=*.py --include=*.sh --include=*.js --include=*.ts .` ⇒ **1**（`deephealing_kernel/tick.py:58`）。
- ② 白名单（其余含 `300` 的位置，逐条给理由）：

| 位置 | 理由 |
|---|---|
| `deephealing_kernel/cli.py:17` | 模块 docstring 的历史说明（**不是**默认值来源） |
| `deephealing_kernel/cli.py:75` | 注释里的「实测 300 tick 的日志可产出 3.5k 行」（**不是**默认值来源） |
| `deephealing_kernel/tick.py:52` | 权威常量旁的**语义 docstring 句**（D-3 要求就写在这里） |
| `districts/*/schedules/weekday.json` 的 `end_tick: 300` | **pack 数据**（日程块结束 tick），不是默认值 |
| `districts/*/tasks/task-001.json` 的 `repeat_within_ticks: 300` | **pack 数据**（防刷重复窗口），不是默认值 |
| `kernel/tests/test_task_adaptation.py:145/206/214` | 本轮**新增测试**里的比较/调用（`range(301)`、`kernel.run(300)`、`assert last["tick"] == 300`），**不是**赋值 |
| `cli.py:129` | 本轮已修 ⇒ **不再命中** |

- ③ 不传 `--ticks` 真跑 ⇒ `ticks: 300`、6 个检查点（与 F-4 同读数）。

### AC-M3-1d 第二街区进门禁

| 命令（workdir `kernel`） | 实测 | exit |
|---|---|---|
| `python3 -m deephealing_kernel validate --pack districts/xingfu-xiaoqu` | `{"pack_id": "xingfu-xiaoqu", "npcs": 5, "tasks": 2, ...}` | 0 |
| `python3 -m deephealing_kernel validate --pack districts/xingfu-xiaoqu-north` | `{"pack_id": "xingfu-xiaoqu-north", "npcs": 5, "tasks": 2, ...}` | 0 |

`verify_specs.sh` 新增（§7b）：`verify_pack.py v0_skeleton/districts/xingfu-xiaoqu-north` + `PYTHONPATH=v0_skeleton/kernel python3 -m deephealing_kernel validate --pack <pack#2>`（**两条**）+ pack#1 的 `validate`。负例见 §5。

### AC-M3-1e 构建产物零残渣

| 命令（workdir `<ws>`） | 期望 | 实测 |
|---|---|---|
| `/usr/bin/find 02_source \( -name node_modules -o -name dist -o -name .build \) \| wc -l` | 0 | **0** |
| `cd 02_source/v0_skeleton/web && npm run build`（连跑两次） | exit 0；`.build/web/assets` 只有一套 | exit **0** ×2；`assets/` = `index-0DdkbXF_.js` + `.map`（**一套**） |

### AC-M3-2 会话层

| # | 命令（workdir） | 实测 | exit |
|---|---|---|---|
| 1 | `npm test`（`02_source/v0_skeleton/session`） | **9 passed / 0 failed / 0 skipped**；4 条 AC 命名用例**逐字存在且真跑**：`test_observe_session_intent_rejected_with_readonly_code` / `test_participate_intent_applied_only_at_tick_boundary` / `test_rate_limit_and_cooldown_enforced` / `test_impact_budget_exhausted_downgrades_to_observe` | 0 |
| 2 | `pytest tests/test_observe_mode_readonly.py -q`（`kernel`） | **4 passed**（桩已全部变成真断言；docstring 运行命令改为 `pytest`） | 0 |
| 3 | `pytest tests/test_task_adaptation.py -q` | **6 passed** | 0 |
| 4 | 真跑事件流（`spikes/s12-session/runtime/logs/kernel-events.jsonl`） | `intent.rejected` **3** 条（`reason_code: E_MODE_READONLY`）、`intent.applied` **2** 条、`task.state_changed` **2** 条 | — |

`task.state_changed` 真实 payload（逐字摘自事件流）：
```
{"caused_by":"p8-part","decision":"shift","from_state":"dormant","impact_cost":3.0,
 "reason":"玩家委托把关心送达","rule_id":"rule-001-warmth","shift_index":1,
 "task_id":"task-001","to_state":"offered"}
```

### AC-M3-5 参与影响任务演进

- 数据驱动：规则/状态集全部来自 `districts/*/tasks/task-001.json` 的 `adaptation_rules`（内核侧 **0** 个 `if task_id` 分支）。
- D-14 求值顺序：`order_rules()` 把守卫规则（`effect.no_op` 或 `max_shifts == 0`）排到最前，命中即**短路**。
- 防刷机器判据：同目标**连续两次** `delegate_instruction` ⇒ 第二次 `decision=guard_no_op`、**不产生** `task.state_changed`（审计流水 `[shift, guard_no_op]`）。
- `max_shifts` 硬上限：用测试自带数据文档驱动（A 规则 `max_shifts:2` 迁移 s0→s1、B 规则重置回 s0）⇒ 第三次 A 命中时 `max_shifts_reached`，迁移次数恰好 **2**。
- 审计记录：`task.state_changed` 带 `rule_id` / `shift_index` / `decision` / `impact_cost`；`impact_cost=3.0` 与 `intervention.policy.impact_budget.cost_table.delegate_instruction` **同值**（预算联动）。
- 无 intent 基线：`test_default_run_without_intents_is_bit_identical` 断言 300 tick 的 `state_hash` / `chain_tail` / 检查点集合逐位不变。

### AC-M3-6 确定性

- 基线逐位一致（见 AC-M3-1 #2）。
- 会话层两遍同序列：`spikes/s12-session/zero-residue.mjs` 的两次桥运行产物见 §3（`p8-zero-residue.json`）。

### AC-M3-7 仓库零改动 + 溯源

| 命令 | 实测 |
|---|---|
| `git -C /Users/wooyinq/personal/deep-healing rev-parse --abbrev-ref HEAD` | `develop` |
| `git -C … status --porcelain \| wc -l` | **0** |
| `shasum -a 256 SEED.sha256` | `34fa7f6d252bc4bf966c8dbc4d639a1f08788ed71b9cfa04a0896ca7ba8f7676`（与起点一致） |

### AC-M3-8 世界观落地

| 项 | 判定 | 证据 |
|---|---|---|
| ① 契约成立 | **PASS** | `worldview.schema.json` 落 `02_source/`（与 `district.pack.schema.json` 同级）；两 pack 各带 `worldview.json`；`pack.entrypoints.worldview = "worldview.json"` 且已进 `required`；`district.pack.spec.md` 增 §7/§8；`verify_specs.sh` 用 `schema_validate.py`（jsonschema 4.26.0）真跑校验 |
| ② NPC 两面 | **PASS** | 10/10 NPC 同时具备 `narrative_hooks` + `healing_face` + `hidden_face`（`verify_specs.sh` §7d 断言，`NPC_FACE_TOTAL ≥ 10`）；旧消费方复核：`narrative_hooks` 的消费点**只有 pack 数据自身**，内核/会话/渲染 0 命中 |
| ③ 同一几何两态 | **部分 PASS** | 机器判据（顶点数 288 / 实体 id 12 项 / 坐标 / digest 逐项相同）绿；**真浏览器两态截图 GAP** |
| ④ scene_assert 两条新断言 | **PASS** | `two_reads_share_geometry` + `underneath_does_not_raise_saturation` 真跑通过（`scene_assert: PASS=15 FAIL=0`） |
| ⑤ 异常锚点双读 | **PASS** | `anom-01` 表层读法/深层读法两段文本齐备；`reveal_at_tick=55`；`panel.ts::renderAnomalyReads` 按 `tick >= reveal_at_tick` 切换读法（真浏览器读数 GAP） |
| IP 边界 | **PASS（含命中能力证明）** | 关键词扫描（血腥/怪物/Jump Scare/跳吓/鬼/怨念/诅咒/神龛/怪谈）命中 **1** 文件 = `worldview.schema.json` 的 `$comment`（**自命中**：该注释本身就是「零血腥/怪物/Jump Scare」的边界声明，已白名单化）；命中能力探针 `/tmp/m3-ip-probe.txt` 注入 ⇒ grep 命中 **1**（**有命中能力**）；`xingfu-xiaoqu-north` 在 `world.ts`/`main.ts` 命中 **0**（深层态不是第二个 pack/第二张地图） |

---

## 2. 长套件读数（单独登记）

`cd 02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider`

- 读数与 exit 见 `spikes/s12-session/logs/m3-kernel-pytest.txt`（本轮**后台跑完后回填**；若未及回填，以该文件为准，**不得**用「自述全绿」替代）。

---

## 3. P-8（O-M2-1）零残渣判据 —— **逐字节**

- 脚本：`spikes/s12-session/zero-residue.mjs`（workdir `<ws>`，exit **0**）
- 判据①：跑前/跑后 `02_source/**` 全量 sha256 清单**逐字节相同**
  - 前：`spikes/s12-session/logs/m3-source-manifest-before.txt`（148 文件）
  - 后：`spikes/s12-session/logs/m3-source-manifest-after.txt`（148 文件）
  - 差集：`changed=[] added=[] removed=[]` ⇒ **byte_identical: true**
  - 排除集**逐条列明**（照抄 `verify_specs.sh:131-140` 的 `GENERATED_PATTERNS`）：`__pycache__`、`*.pyc`、`.pytest_cache`、`.DS_Store`、`node_modules`、`.venv`、`dist`、`attic-*`
- 判据②：运行时 `deephealing_kernel.__file__` =
  `…/spikes/s12-session/runtime/02_source/v0_skeleton/kernel/deephealing_kernel/__init__.py`
  ⇒ 位于**副本路径**下（`kernel_inside_copy: true`），**不是**交付树
- 副本布局说明（本轮实测得到的必要修正）：内核以 `parents[2]` 定位 `<v0_skeleton>/tools/canonical_json.py`、
  以 `parents[3]` 定位 `<02_source>/district.pack.schema.json` ⇒ 桥必须复制**整个 `02_source/`**（去掉生成残渣）
  才能保住相对路径；只复制 `kernel/**` 会 `FileNotFoundError`（已实测）。
- 证据：`spikes/s12-session/logs/p8-zero-residue.json`

### D-8 第 4 条（architect 侧清理，**如实登记**）

`02_source` 下 14 个 `__pycache__/*.pyc`（153 → 139 文件）由 architect 用 `/tmp/arch-clean-pycache.py` 删除
（`removed_files=14 removed_dirs=3`）。这是**解释器副作用**（不是任何人的编辑），且被所有门禁排除
（`V0_M2.sha256` / `SEED.sha256` / `manifest.txt` 的 pycache 命中数均为 0）。属对 `02_source` 的写入，**在此声明**。
本轮全程 `PYTHONDONTWRITEBYTECODE=1`（桥、内核、pytest、门禁），且桥额外传 `-B`。

---

## 4. D-12 冻结面口径（三条并列读数）

| 口径 | 读数 |
|---|---|
| 1. M1/M2 **行为判据**复跑 | `verify_specs.sh` OK/0 skipped/125 PASS；F-4 基线逐位一致；内核套件见 §2 |
| 2. 五个根级文件**字节不变** | `V0_M1.sha256` `c004e39c…`、`V0_M2.sha256` `e9094c00…`、`06_v0_m1_self_test.md` `c1273b56…`、`06_v0_m2_self_test.md` `507b92c8…`、`SEED.sha256` `34fa7f6d…` —— 全部未改（`shasum` 前后相同） |
| 3. `shasum -c V0_M2.sha256` 非 OK 集合 == 声明清单 | **FAIL（部分）**：差集 **37** 条 vs 声明 SECTION A **42** 条 |

### 4.1 差集 vs 声明的双向比对（**如实报 FAIL**）

- 差集里**未声明**的行：**0**（零未声明漂移）。
- 声明里**不在差集**的行：**5** —— 这些是**本轮未实现的结转项**，不是漏声明：

| 声明行 | 未实现原因 | 归属 |
|---|---|---|
| `kernel/deephealing_kernel/registry.py` | R-M2-1（pin 内容摘要 ↔ 解析产物一致）**本轮未做** | M4 / 下轮 |
| `kernel/tests/test_calibrate_latency.py` | 随 P-9 一起未做 | M4 / 下轮 |
| `kernel/tools/calibrate_latency.py` | P-9（D-10 绝对路径 + `--force-rewrite` 迁移）**本轮未做** | M4 / 下轮 |
| `tools/pack_sign.py` | R-M2-3（目录符号链接 fail-closed）**本轮未做** | M4 / 下轮 |
| `tools/verify_pack.py` | 同上 | M4 / 下轮 |

- 另：`03_artisan_self_test.log` 在本轮**追加 M3 段后**进入差集（本文件写定时仍与 M2 版逐字节相同）。
- **判据 ①（声明里有、差集里没有 ⇒ 必须红）**：**已按设计变红** —— 这正是它要抓的东西；本轮**接受该红**，
  处置写进 §7 结转表，**不**为了变绿而事后删除声明行（那正是 3A-M6 禁止的「反向生成」）。
- **判据 ②（差集里有、声明里没有 ⇒ 必须红）**：本轮**未命中**（0 条）⇒ 该方向无红。

### 4.2 声明清单的先于性

`spikes/s12-session/m3-change-face.txt` 写于**任何编码之前**（文件内含声明时点说明），
依据任务书 §5.3/§5.4 而非 `shasum -c` 输出。

---

## 5. 负例自证（D-13：一律隔离执行）

> **R3 / G3 作废标注（就地，行 198–216）**：本节引用的 `spikes/s12-session/logs/negctl-summary.json`
> 与 `negctl-scene-assert.log` / `negctl-scene-assert-saturation.log` 是 **R1 的崩溃型假红**
> （实测 `^FAIL` = **0** / `ERR_MODULE_NOT_FOUND` = **3** / `^PASS` = 0 —— 那是模块解析崩溃，
> 不是断言判红；汇总还把 `turned_red: true` 给了它们且无 `verdict`/`crash_markers` 区分）。
> **它们已被 R2 的 F1 证据集取代、作废**，并已移入 `spikes/s12-session/logs/superseded/`
> （含 `README.md` 说明取代关系；`V0_M3.sha256` 的排除项写明 `superseded/**`）。
> 交付面上**不并存**两套互斥结论 —— 本节余下的读数仅作历史记录，**不得**再作为有效证据引用。

- 脚本：`spikes/s12-session/negctl.py`（workdir `<ws>`，**exit 0**）
- 副本根：`/tmp/m3-negctl/**`（整树副本；**未**改 `02_source` 再改回来）
- **交付面证明**：`negctl-summary.json` 的 `delivery_face_sha_before == delivery_face_sha_after`
  ⇒ `delivery_face_unchanged: true`
- 汇总读数：`spikes/s12-session/logs/negctl-summary.json`（`all_turned_red: true`）

| # | 门禁 | 注入方式（隔离副本） | 期望 | 实测红 |
|---|---|---|---|---|
| N-1 | observe 拒写（会话层） | `mode.js::checkUpstream` 改成恒返回 `null` | `npm test` 红 | **exit 1 ✓** |
| N-2 | observe 拒写（内核侧） | `tick.py::submit_intent` 的 `mode != "participate"` 分支短路掉 | `pytest` 红 | **exit 1 ✓** |
| N-3 | `max_shifts` 硬上限 | `rule-a` 的 `max_shifts: 2` → `999` | `pytest` 红 | **exit 1 ✓** |
| N-4 | P-8 判据① | 隔离副本里对真实文件改 1 字节 | 清单比对红 | **红 ✓** |
| N-5 | P-8 判据② | 把副本机制退回「直接 `sys.path.insert` 交付树」 | 来源判据红 | **未执行（GAP）** |
| N-6 | AC-M3-1d（pack#2） | 删 pack#2 的 `worldview.json` | `verify_specs` 红 | **exit 1 ✓** |
| N-7 | AC-M3-1e（零残渣） | 造 `02_source/v0_skeleton/web/dist/x.js` | `verify_specs` 红 | **exit 1 ✓** |
| N-8 | AC-M3-8① | 删 `tone.underneath` | schema 校验红 | **exit 1 ✓** |
| N-9 | AC-M3-8② | 删某 NPC 的 `hidden_face` | `verify_specs` 红 | **exit 1 ✓** |
| N-10 | AC-M3-8③ | 深层态换一套坐标（几何源注入偏移） | `scene_assert` 红 | **exit 1 ✓** |
| N-11 | AC-M3-8④ | 把深层态饱和调高（14 → 44） | `scene_assert` 红 | **exit 1 ✓** |
| N-12 | L-1 manifest 锚定 | 注入「含该子串但非该文件」的条目 + 删真条目 | `verify_specs` 红 | **exit 1 ✓** |

- **11 条 turned_red=true；N-5 未执行**（预算耗尽）⇒ N-5 标 **GAP**，**不**标 PASS。
- 逐条日志：`spikes/s12-session/logs/negctl-*.log`（含命令、exit、stdout/stderr 尾部）。

---

## 6. 关键命令与证据路径（绝对路径）

| 证据 | 路径 |
|---|---|
| 改动面声明（**编码前**写定） | `<ws>/spikes/s12-session/m3-change-face.txt` |
| P-8 零残渣读数 | `<ws>/spikes/s12-session/logs/p8-zero-residue.json` |
| 02_source 跑前/跑后清单 | `<ws>/spikes/s12-session/logs/m3-source-manifest-{before,after}.txt` |
| 内核真实事件流 | `<ws>/spikes/s12-session/runtime/logs/kernel-events.jsonl` |
| 会话层真实下行消息（供 schema 校验） | `<ws>/spikes/s12-session/logs/emitted-messages.jsonl` |
| 内核长套件读数 | `<ws>/spikes/s12-session/logs/m3-kernel-pytest.txt` |
| 负例日志 | `<ws>/spikes/s12-session/logs/negctl-*.log` |

---

## 7. 结转项处置表（P-1…P-10 / M3-1…M3-7 / M1 8 条 MEDIUM / M2 未关项）—— **禁止静默丢失**

| # | 项 | 本轮处置 | 证据 / 理由 |
|---|---|---|---|
| **P-1** | `--ticks` 默认 300 语义漂移 | **关闭** | `tick.py:58` 单一权威 + 语义 docstring + `cli.py:129` 字面已修 + AC-M3-1c 三读数 |
| **P-2** | GAP-7 自洽前缀截断 | **接续（口径不变）** | 会话/渲染层零「无锚点信任」路径；`verify --expected-hash` 语义未动 |
| **P-3** | M1 的 8 条 MEDIUM 残余 | **逐条接续**：M2 已关闭的部分沿用 M2 读数；**本轮未新增关闭** | 见 M2 `06` §P-3 表；本轮未触碰相关代码 |
| **P-4** | M2 的 `non_block_issues`/GAP | **逐条接续，无消失** | 见 M2 `06`；本轮未改其判定口径 |
| **P-5** | AC-M1-6 标定判据③不可重复 | **不重采样、不调参**（声明口径） | 会话层限流/冷却/预算**不消费**标定值：`policy.js` 的窗口/冷却/预算是**契约默认值**（`intervention.policy.schema.json` 的 `default`），与 `s5` 标定值无耦合 |
| **P-6** | M3-1…M3-7 | M3-1/M3-2/M3-4/M3-6/M3-7 **沿用 M2 判定**；M3-3 见下；M3-5 本轮不做 | — |
| **P-7** | M2 的 5 条 GAP | **逐条接续**（GAP-7 不放松；GAP-E1 维持；`local_model` 维持 SLOT DESIGN ONLY；自洽前缀截断；`lookup()` 字面差距） | 本轮未触及嵌入通道 ⇒ GAP-E1 维持 |
| **P-8** | O-M2-1 结构性 | **关闭** | `p8-zero-residue.json`：逐字节相同 + 副本来源 + 两个负例脚本 |
| **P-9** | 标定缓存不可移植 | **本轮不做 + 理由 + 归属 M4** | 理由：预算耗尽（R-9 已预警）。处方已由 D-10/3A-C3 定死（相对路径 + `--force-rewrite` 迁移 + 3 条判据 + 负例），下轮可直接执行 |
| **P-10 R-M2-1** | `pin` 只做存在性校验 | **本轮不做 + 归属 M4** | 理由同上；D-11 的处方（pin 版本内容摘要 ↔ 解析产物一致 + 负例）已定 |
| **P-10 R-M2-3** | `rglob` 不跟随目录符号链接 | **本轮不做 + 归属 M4** | 理由同上；处方（显式枚举目录符号链接并 fail-closed + 负例）已定 |
| **P-10 R-M2-4** | `--cognition` 默认 provider 随凭据漂移 | **本轮不做 + 归属 M4** | 理由同上；处方（显式常量 + 凭据在场/不在场两档读数 + 负例）已定 |
| **P-10 L-1** | manifest 覆盖判据子串非锚定 | **关闭（修法①）** | `verify_specs.sh:172` 改为 `awk -v p="$rel" 'index($0, p " \| ")==1 {found=1} END{exit !found}'`；改后仍 `OK / 0 skipped / 125 PASS`；负例见 §5 N-12 |
| **P-10 新增门禁** | 第二街区必须进门禁 | **关闭** | `verify_specs.sh` §7b（pack#2 `verify_pack` + 两条 `validate`）；负例见 §5 N-6 |

---

## 8. 本轮已知风险 / 未覆盖项（如实）

1. **AC-M3-3 / AC-M3-4 / AC-M3-8③ 的真浏览器交互验收未执行**（预算耗尽）。
   已有的替代证据（**不构成替代判据**）：`npm run build` exit 0、`render-client.test.ts` 4/4 绿、
   `scene_assert.mjs` 15/15 绿、`spikes/s12-session/run-session.mjs` 已实现「HTTP + WS + 静态服务」三合一
   （`.build/web` 由同一服务提供，Playwright 脚本 `spikes/s13-render/verify.mjs` 未落地）。
2. **内核全量 pytest 读数**：长套件已后台启动，读数落 `spikes/s12-session/logs/m3-kernel-pytest.txt`。
   本轮**未在 7200s 内等到终值** ⇒ 该条判据**不得**标 PASS。
3. `spikes/s13-render/**` 本轮**未产出**（无截图、无 console 输出）⇒ AC-M3-3 的硬性证据缺失。
4. 依赖安装形态：`npm install --no-audit --no-fund`（不带参数）`added 18 packages in 11s` exit 0；
   esbuild 的 postinstall 被环境 allow-scripts 拦下，但 `vite build` 仍 exit 0（esbuild 二进制已随包落盘）。

---

## 9. 上抛（block_issues，非阻断）

1. **D-4**：REQ §3 两处路径字面与盘上不符（`02_source/districts/…` 与 `kernel/tasks/` 均不存在）——
   按盘上真实位置实现（pack 根 + pack 的 task 数据），**不改需求**。
2. **D-12**：`V0_M2.sha256` 全量快照口径在 M3 增长下按设计会红 ⇒ 已按 rev2 的三条并列口径执行。
3. **预算**：本轮 7200s 不足以覆盖 P1（真浏览器）+ P2（两态截图）+ 全部结转项。
   建议下轮把「真浏览器验收」与「P-9/R-M2-1/R-M2-3/R-M2-4」拆成两条并行轨道。

================================================================================
## R2 段（修复轮 · REQ-20260921-005-deephealing-v0-m3）—— artisan 判定
================================================================================

- 轮次：R2（修复轮，迭代 2/3）　任务书：`<ws>/.task-artisan-r2.md`　run-budget：7200s
- 开工快照：`develop` @ `98c781f4040d9b17757d67ba8e76fed1b95bfa12`，porcelain **0**；同写集无 live writer
- 交付面：`02_source` **150** 文件（R1 末 148 + `test_budget_downgrade_void.py` + `scan_ip_boundary.py`）
- 逐 F 读数与负例见 `03_artisan_self_test.log` 的 **R2 段**（每条含命令 + workdir + exit + 读数 + 副本路径）
- 负例口径：**交付面冻结后**把 8 条 harness 一次跑齐（`03` 的 R2-15），8 个汇总的
  `delivery_face_sha_tree` 全部相同（`c284b86f…`）、`delivery_face_unchanged=true`、`crashes=[]`

### R2-A 逐 F 项关闭判据

| 项 | 关闭判据（任务书） | 实测 | 判定 |
|---|---|---|---|
| **F1** | ①注入 D-7 禁止形态必须红 ②无注入必须绿 ③负例在带依赖副本里跑且日志有真 `FAIL` 行 ④汇总区分 crash/judged_red | `PASS=22 FAIL=0`；`f1a/f1b` 变红且 **`FAIL two_reads_share_geometry`**；`crashes=[]`、无 `ERR_MODULE_NOT_FOUND`；`turned_red` 只给 judged_red | **PASS** |
| **F2** | ①不传 mode ⇒ rejected + 无 `intent.applied` ②显式 participate 正常 ③负例改回可写缺省 ⇒ 红 | `f2_pristine` 8/8；两条负例 `all_checks_pass=False` | **PASS** |
| **F3** | ①降级后 `pending_intent_count()==0` ②每条作废意图有事件/ack ③负例静默作废 ⇒ 红 ④policy 字段名/语义同步 | 场景 B `void_ack.pending_after=0`、`kernel_rejected_budget_exhausted=33`、场景 A `session_voided_acks=33`；2 条负例红；`observe_and_queue` 全树 0 命中 | **PASS** |
| **F4** | 两档视口 × 两态截图 ≥4 + console 零报错（给实际输出）+ AC-M3-4 双判据 + 下行 tick 流 + 负例 | 6 张截图；`console_errors=0`（4 条全为 WebGL warning，见 `console-pristine.jsonl`）；观察模式控件表只有 2 个只读按钮、写接口真跑被拒；`snapshot+delta+tick_meta`，delta 覆盖 5 NPC；负例 4 条判据变红 | **PASS** |
| **F5** | `grep -c '/Users/'` = 0 + 幂等测试全绿 + 门禁断言在场 + 负例变红 | **0**；13 passed；`verify_specs` 新增断言 PASS；2 条负例红 | **PASS** |
| **F6** | 两条判据各带负例真跑读数并在 06 登记 | pin 摘要绑定（字节级）+ 目录链接 fail-closed；`f6_neg_pin_digest_disabled` / `f6_neg_dir_symlink_guard_removed` 均按预期。**R3 / G9 措辞更正：该声称收缩为「防单侧漂移」—— 不读成「防篡改」**（`pins.json` 的 `digests` 与被保护对象在同一棵树里，两侧同改可自洽；见 R3 段 G9） | **PASS** |
| F7 | 全部写入后重采 before/after；交付面逐字节相同；理由 + 前后哈希登记 | `150/150`、`changed=[]`、`delivery_face_byte_identical=true`；`taken_at_epoch=1790096985`（**交付面最后一处写入之后**重采）；清单哈希 `2564404e…`（前后同值） | **PASS** |
| F8 | 判据改写 + M2 继承缺陷单独登记 + 双向负例 + 时间锚 | `non_ok 46 == declared 46`、双向空差集；4 条负例红；`declared_at_epoch=1790096082` + `shasum -c` 原文在 `m3-change-face.json` | **PASS** |
| F9 | 三处硬编码区间改从 schema/art-bible 读；「无镜面」改断言返回值 | `manifest=[20,60] art-bible=[20,60]`、`schema=[3200,5200]`、`metalness=0.04`（返回值） | **PASS** |
| F10 | 实现（同 id 窗口内合并）或删除并声明；判据：同 id 两次 ⇒ 第二次 merged/rejected | 同 id 窗口内 ⇒ `queued + detail(merged)`、队列只 1 条、tick 边界只 1 条 `intent.applied`；窗口外不合并 | **PASS** |
| F11 | 实现最小录像（只读落 logs，不写世界）或降级声明 | 注入式 recorder；真跑 7 条下行消息、未开录像会话零字节、内核事件数不变 | **PASS** |
| F12 | 扫描器进 `v0_skeleton/tools/`（含 `--probe`）+ 进 `verify_specs.sh` + 白名单写进脚本；注入必命中 / 移除 0 命中 | 两条门禁断言 PASS；`--probe` 20→24→20；3 条负例（含清空白名单）按预期 | **PASS** |
| F13 | URL 由 `district_pack_id` 决定；删死代码；tone 数值全树单一定义点 | `/packs/<id>/worldview.json`；`FALLBACK_WORLDVIEW` 已删；tone 数值 grep 0 命中 | **PASS** |
| F14 | 在 06 记录全量终值 | `151 passed in 888.24s (0:14:48)`（0 failed / 0 skipped）；快速回归口 `56 passed in 3.87s` | **PASS** |

### R2-B 逐 AC 重判（只列与 R1 不同的）

| AC | R1 | R2 | 依据 |
|---|---|---|---|
| AC-M3-3（渲染层真跑 + 双模式 UI） | GAP | **PASS** | 真 Chromium 两档视口、真交互（切换读法/模式、填输入 + 点「委托」⇒ `queued`）、reload 后回读（tick 前进、模式复位、会话重连）、6 张截图 |
| AC-M3-4（美学 + 观察无写入口） | GAP（半） | **PASS** | ① **真浏览器枚举 UI 控件清单**：观察模式 `writeControls()==[]`、文档级控件表仅 2 个只读按钮；② 写接口被拒真跑：客户端本地拒 + **服务端 WS 上行拒**（`E_MODE_READONLY`）；③ `scene_assert PASS=22`（含 F1/F9 新判据） |
| AC-M3-8③（同一几何两态） | 部分（判据无牙齿） | **PASS** | 机器判据改为**两次独立装配**且注入可红（`f1a/f1b`）；真浏览器读数 `geometryFor('surface')/('underneath')` 逐项相同（12 实体/288 顶点/digest） |
| AC-M3-8⑤（异常锚点双读） | 代码面 PASS | **PASS** | 真浏览器（desktop 采样跨过揭示 tick）：`reveal_at_tick=55`，表层截图在 `surface_tick_at_shot=49`（**< 55**）显示表层读法、深层截图在 `underneath_tick_at_shot=61`（**> 55**）显示 `underneath` 读法（`#anomaly-read` 文本 + dataset 双读数）；narrow 采样为 `144/145`（均 > 55，只覆盖揭示后读数，如实登记） |
| AC-M3-1b（D-12 双向） | FAIL（部分） | **PASS** | 修正口径后双向成立（46 == 46，差集双向为空）+ 4 条负例 |
| AC-M3-1 / 1c / 1d / 1e / 2 / 5 / 6 / 7 | PASS | **PASS（回归）** | `verify_specs: OK (128 checks passed, 0 skipped)`；`session npm test 13/13`；`web npm test 4/4`；内核全量见 R2-D；基线三条逐位不变（见 R2-D）；仓库 `develop` / porcelain 0 |

### R2-C 本轮**明确不做**（含理由与归属里程碑，**禁止静默**）

| 项 | 处置 | 理由 | 归属 / 升级条件 |
|---|---|---|---|
| **M3-06** 会话主体维度配额 / 会话 TTL | **不做** | 会话层全树**无 `listen(`/`createServer`** ⇒ 当前无网络面，渡鸦判 MEDIUM；本轮无授权新增会话回收机制（改动面会扩散到 `sessions/queues/outboxes/log` 四个 Map 的生命周期与 `createSession` 契约） | **M4**：一旦接上 WS/HTTP 监听 ⇒ **升为 CRITICAL**，必须先落「每主体会话数/总介入率配额 + 会话 TTL + 回收」 |
| **M3-13** 桥把 stdin 的 `impact_cost` 原样交给内核 | **不做** | 仅审计字段失真（内核不据此扣预算；预算在会话层记账），渡鸦判 LOW | **M4**（与 M3-13 的审计口径一起收） |
| M3-15（**一半**：声明清单时间锚 + 双向负例） | **本轮做** | F8 的一部分 | — （已完成，见 R2-A/F8） |
| M3-15 剩余：`impact_cost` 审计链路 | 不做 | 同 M3-13 | M4 |

### R2-D 回归读数（内核全量 + 基线）

| # | 命令（workdir） | 实测 | exit |
|---|---|---|---|
| 1 | `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider`（`02_source/v0_skeleton/kernel`） | **`151 passed in 888.24s (0:14:48)`**（exit 0；日志 `/tmp/r2-artisan/kernel-full.log`） | 0 |
| 2 | `python3 -m deephealing_kernel run --pack districts/xingfu-xiaoqu --seed 20260921 --events /tmp/r2-artisan/m3base/e.jsonl --snapshot-every 50`（`kernel`，不传 `--ticks`） | `chain_tail=baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786`、`event_count=925`、`000300.json state_hash=9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f`；**独立复跑**（`/tmp/r2-artisan/m3base2/`）⇒ 三条读数逐位相同、两份 `e.jsonl` `cmp` 逐字节相同 | 0 |
| 3 | `bash 02_source/verify_specs.sh`（`<ws>`） | `verify_specs: OK (128 checks passed, 0 skipped)` | 0 |
| 4 | `npm test`（`session` / `web`） | `13/13` / `4/4` | 0 |
| 5 | `node scripts/scene_assert.mjs`（`web`） | `PASS=22 FAIL=0` | 0 |
| 6 | `git -C /Users/wooyinq/personal/deep-healing status --porcelain \| wc -l` | **0**（`develop`） | 0 |

**R2 终值（内核全量套件）**：`151 passed in 888.24s (0:14:48)`，exit 0（workdir `02_source/v0_skeleton/kernel`；
命令 `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider`；完整输出 `/tmp/r2-artisan/kernel-full.log`）。
R1 只留了部分读数（142 用例 ≈ 15.5 min），本轮补全为**全量终值**：**151 passed / 0 failed / 0 skipped**，
耗时 14:48（机器同时被其它会话占用，属**上界**读数）。未做快/慢分组拆分（F14 的「可选」项，本轮未做）。

### R2-E M2 继承缺陷登记（单独登记，不计入本轮改动）

- `02_source/v0_skeleton/kernel/tools/calibrate_latency.py`：`V0_M2.sha256` 记 `e30be65b…`，
  而 M2 提交态为 `23fed40d…`（R1 已独立复现；M3 R1 **未动过**该文件）。
- **R3 / G10 措辞更正（就地）**：R2 段原写「继承偏差本身在盘上**无法再复算**（真实仓库无 M2 提交对象）」——**与事实不符**。
  该条**可复算**：`git -C /Users/wooyinq/personal/deep-healing cat-file -e 98c781f4040d9b17757d67ba8e76fed1b95bfa12^{commit}` ⇒ exit **0**；
  `git show 98c781f4040d9b17757d67ba8e76fed1b95bfa12:v0/02_source/v0_skeleton/kernel/tools/calibrate_latency.py | shasum -a 256`
  ⇒ **`23fed40d564e7ba0b21024accbd760b55e665a5e44cf0f8be08b996a970a00f2`**（= R1 读数）。
  R3 已**亲跑复算**（命令 + exit 见 `03_artisan_self_test.log` 的 R3 段）；判据结果不受影响（`非 OK == 声明 ∪ 继承偏差` 双向仍成立）。
  下面这段保留原措辞以便对照，**以上面这行为准**：
- 判据口径修正：`非 OK 集合 == 声明清单 ∪ {该 1 条继承偏差}`（实现见 `ac-m3-1b-check.py`
  的 `inherited_m2_deviations`；本轮实际 `changed_explained_by_inherited_deviation=[]`，因为该条已被本轮声明覆盖）。

### R2-F 门禁冻结面 / 重取登记

- `04_sentinel_test_report.md` / `05_raven_risk_report.md` / `01_*` / `refs/**` / `pm_business/**` /
  真实仓库 / `V0_M1.sha256` / `V0_M2.sha256` / `SEED.sha256` / `06_v0_m1_*` / `06_v0_m2_*`：**本轮零改动**。
- **`V0_M3.sha256` 重取登记**（最后一步执行）：
  - **重取理由**：R2 全部写入（交付面 + spikes 证据面 + `03`/`06` 追加）完成后重取，使清单与最终字节一致；
    R1 的清单在 R2 修复前定格，按设计必然失配。
  - **变更清单**：`02_source/**` 46 个文件改动 + 2 个新增（`test_budget_downgrade_void.py`、`scan_ip_boundary.py`）；
    `spikes/s12-session/**` 与 `spikes/s13-render/**` 新增判据驱动/负例/日志/截图；
    根级 `03_artisan_self_test.log`、`06_v0_m3_self_test.md` 追加 R2 段。
  - **采集面外新增文件（显式声明）**：`<ws>/V0_M3.sha256.retake.json` —— 重取登记（重取链 + 终值哈希）。
    放在采集面外是**有意**的：清单包含 `06`，若把清单自身哈希写进 `06`，写完即自我作废；放在采集面外可稳定登记。
  - **前后哈希**：重取前（R1 清单，175 条目）`V0_M3.sha256` sha256 =
    `16552d53c1da1ae4a77c5db9697eba0d49feaae9c0863e9f4836e088a73c4e04`；
    条目数 175 → **255**。R2 的重取链（每次都是「先写完 → 再重取」）：
    ① `447d5e601983ac5f831e4a6aa98628a50b6339b6c0e2503f5d407d3a9f6eced2`（R2 段首次落盘后）
    → ② `a7b365a59592321c02c9f0a20ba9850eb88b81e9492487d125f17dca7569aee7`（修正 `03` 的 P-8 时间锚后）
    → ③ `349aaa749c2d63e68414becc5ce38c2dbd80f18d4794f55c689fdfe4d3ff8378`（修正 `03` 的 F8/P8 读数后）。
    本段文字定稿后**再重取一次**（清单终值 = 该次重取打印的 sha256，登记在
    `<ws>/V0_M3.sha256.retake.json` 与回给 architect 的摘要中；复算命令 `shasum -a 256 V0_M3.sha256`）。
  - 采集面与排除项**逐字沿用** R1 清单头部声明，并**显式扩展**排除 `spikes/*/runtime*/**`
    （运行期副本：桥把 `02_source` 整树复制到运行目录；R1 已排除 `spikes/s12-session/runtime/**`，
    R2 按同一规则覆盖 `spikes/s13-render/runtime*`）。
  - **自引用滞后（如实声明）**：`V0_M3.sha256` 自身不入清单，但清单**包含 `06_v0_m3_self_test.md`**；
    本登记段写入后又重取了一次清单 ⇒ 复跑 `shasum -a 256 V0_M3.sha256` 得到的哈希会比上面链上的 ③ 再新一版，
    差异**仅为本登记段的文字**。故终值不写进本段（写进来又会自我作废），而登记在**清单采集面之外**的
    `<ws>/V0_M3.sha256.retake.json`（该文件不在采集面 ⇒ 可稳定登记）+ 回给 architect 的摘要。
  - 校验方式：`shasum -a 256 -c V0_M3.sha256`（在 `<ws>` 下）应**全 OK**。

### R2-G 已知风险 / 未覆盖面（如实登记）

1. **离线渲染退化**（F13 的代价）：渲染层不再自带基调 ⇒ 无会话层/无宿主静态服务时**不渲染场景**
   （不再伪造世界状态）。M4 若需要离线，应由构建期从 pack 文件注入（单一数据源不变）。
2. **`/packs/<id>/worldview.json` 路由在 spike 宿主**（`spikes/s13-render/serve.mjs`）而非交付面：
   交付面尚无 HTTP 监听（与 M3-06 同源）⇒ 该路由随 M4 的 WS/HTTP 服务一起进交付面。
3. **Playwright 版本漂移**：本机缓存为 `chromium-1234`，而 `playwright@1.63` 默认找 `-1243`（未下载）
   ⇒ 驱动显式 `executablePath` 指向缓存二进制（`browser-accept.mjs` 里写死候选路径 + `PW_CHROMIUM` 覆盖）。
4. **F4 证据与最终 bundle 的关系**：R2 最后一处交付面改动是 `lighting.ts` 的**注释**（去重 tone 数值），
   重建后 JS 产物文件名/字节**不变**（`assets/index-BZDGZLmT.js`，483.79 kB）⇒ F4 的浏览器读数与截图仍然对应最终 bundle。
5. **`record` 录像形态**：只落**下行消息**（不含上行原文、不含 token）；未做录像文件的轮转/保留期（M4）。
6. **内核全量套件耗时**：见 R2-D（长套件，读数单列）；未做快/慢分组拆分（可选改进，未做）。

================================================================================
## R3 段（最后一次修复迭代 3/3 · REQ-20260921-005-deephealing-v0-m3）—— artisan 判定
================================================================================

- 轮次：R3　任务书：`<ws>/.task-artisan-r3.md`　判据权威：`01_architecture_design.md` §3B-1　run-budget 5400s
- 开工快照：repo `/Users/wooyinq/personal/deep-healing` = `develop` @ `98c781f4040d9b17757d67ba8e76fed1b95bfa12`，`status --porcelain | wc -l` = **0**（收尾复测仍 0）
- 本轮范围：**只修 G1–G10**（G1/G2 两条 CRITICAL 优先）；改动面声明写在**任何编码之前**：
  `spikes/s12-session/m3-change-face.txt` 的 `SECTION A-R3`（含 epoch 时间锚）
- 负例口径：**一律**在 `/tmp/r3-artisan/**` 的整树副本上注入；`turned_red` 只给 `judged_red`；
  每条负例的「交付面 sha256 未变」由各 harness 的 `delivery_face_unchanged` 字段给出
- 逐 G 的命令 + workdir + exit + 读数见 `03_artisan_self_test.log` 的 **R3 段**（本节只给关闭判据与结论）

### R3-A 逐 G 项关闭判据

| 项 | 关闭判据（§3B-1） | 实测 | 判定 |
|---|---|---|---|
| **G1**（CRITICAL · Sentinel r2：3D 世界不可见） | ① `setSize(clientWidth,clientHeight,false)` + resize/DPR + canvas 盒随视口变化（桌面/窄屏各一读数）② HUD 之外非背景像素占比 ≥ 阈值 ③ 重采桌面 + ≥390px、两态各一张（≥4 张）并给像素读数 ④ 负例：`setSize` 退回固定 300×150 ⇒ 像素判据必须红 | ① 桌面 `canvas_rect` = **1440×900**（=`window.inner*`）、窄屏 **390×844**；`gl.drawingBuffer` = 同值（DPR=1）② **阈值 0.05**；实测 HUD 外非背景占比：桌面 **0.1238 / 0.1238 / 0.1285**、窄屏 **0.3569 / 0.3569 / 0.3569**（6 张全过）③ 本轮**重采 6 张**（`pristine-{desktop,narrow}-{surface,underneath,after-reload}.png`，1440×900 / 390×844）④ 负例**两条**：`f4_neg_pinned_buffer_only` ⇒ `*_drawing_buffer_follows_canvas` **红**；`f4_neg_fixed_canvas`（连同 `#scene` 显式尺寸一起退回 R3 之前形态）⇒ `*_canvas_rect_fills_viewport` + `*_world_visible_outside_hud` **红**，且 6 张截图 HUD 外非背景占比 = **0.0**、包围盒 `(16,16)-(399,278)` / `(8,8)-(381,258)`、背景占比 **0.9221 / 0.7150** —— 与 architect §3B 亲验读数**逐值吻合**（证明负例真的复现了旧缺陷） | **PASS** |
| **G2**（CRITICAL · Raven r2 R2-C1） | ① `geometry_digest` 纳入每 box 的 `position` attribute 指纹（或 `size`+`geometry.parameters`）② 判据经 `createScene()` 的 `geometryFor/entityIds/setReading` 取数 ③ 三条负例必须红（尺寸 / `rebuild()` 路径 / 装配后网格层）④ 静态判据：`scene_assert.mjs` 出现 `createScene`/`geometryFor` 调用点 | ① `EntityShape` = `size` + `geometry.parameters` + `position_attribute_digest`（微米级量化 FNV-1a 64）并进 `geometry_digest`；自证判据 `geometry_digest_detects_size_change` 证明「只换尺寸、顶点数不变（恒 24）⇒ digest 必变」② `scene_assert.mjs` 经 `createScene()` 句柄取数，且**两条路径都跑**：装配函数产物 + **场景图 mesh 层读回**（`assemblyReport()`）③ `f1e`（尺寸）/`f1f`（`rebuild()` 内改坐标）/`f1g`（装配后改 mesh geometry）**全红**，`fail_names` 分别含 `two_reads_share_geometry` / `two_reads_share_rendered_geometry`；`f1g` 即 Raven r2 的 a5 形态（旧判据下**不红**）④ `verify_specs.sh` §12c 机器判据 PASS（`createScene=8 geometryFor=8 setReading=6 assemblyReport=7`）；`scene_assert: PASS=27 FAIL=0` | **PASS** |
| **G3**（Raven r2 R2-M3：两套互斥结论并存） | R1 崩溃型假红移入 `superseded/`；`06` 的 M3 段**就地**标注「已被 R2 取代、作废」（给行号）；`V0_M3.sha256` 排除项写明 `superseded/**` | ① `mv` 三个文件到 `spikes/s12-session/logs/superseded/`（+ `README.md` 说明取代关系与「不得再引用」）② `06` 的 §5 首部新增作废标注（**行 193–200**，指向原 198–216 行），F6 行的声称收缩（G9）也在同一段就地标注 ③ `V0_M3.sha256` 头部排除项新增 `superseded/**`（见 R3-E）④ 崩溃型证明：`^FAIL`=0 / `ERR_MODULE_NOT_FOUND`=3 / `^PASS`=0 | **PASS** |
| **G4**（Raven r2 R2-M4：白名单整份豁免） | 白名单降为**行/文本级**；扫描器自身用自排除；负例：往 `art-bible.md` 追加真越界 ⇒ 必须红 | ① 白名单改为 `DECLARATION_SITES`（站点）+ **同一行必须含禁令词**（`PROHIBITION_LINE`）的**行级豁免**；扫描器自身改由 `_is_scanner_copy()` **自排除**（不依赖绝对路径，副本同样成立）② `f12_neg_art_bible_out_of_bounds`：往 `art-bible.md` 追加「第 3 章…怪物肢解…血腥特写…Jump Scare」⇒ `unwhitelisted_hits=3`、**exit 1**（修复前 `exit 0`）；对照 `f12_pristine` exit 0 / 0 未豁免；注入探针 ⇒ 4 条未豁免、exit 1 | **PASS** |
| **G5**（Raven r2 R2-M5：已 ack 为 queued 却永不应用） | 合并键含 `target`；被合并对象**已离开队列** ⇒ 按新意图入队；判据：同 id 二次提交后 `pending_intent_count() ≥ 1` 或 ack ≠ `queued`；负例红 | ① 合并三条件：同 id + 窗口内 + **被合并条目仍在队列** + **同 target**；`server.onTickBoundary`/`downgradeToObserve` 落 `markIntentLeavesQueue()` ② `g5_pristine`：窗口内合并（队列仍 1 条）→ 出队后同 id 再提交 ⇒ `ack=rejected(E_COOLDOWN)` 且 `pending_intent_count()=2`（判据成立）；同 id 不同 target ⇒ 不合并、两条各占一个队列条目 ③ 负例 `g5_neg_revert_to_r2_merge`（退回「只看同 id+窗口」）⇒ `swallowed_by_merge=true`、判据**红** ④ 会话套件新增 2 条用例真跑（16/16 全绿） | **PASS** |
| **G6**（Raven r2 R2-M2：锚覆盖不全） | `ENVIRONMENT-CLASS.frozen.md` 加硬编码 sha256 锚；`verify_specs.sh` 增「registry 三条 sha256 == 工具内锚 + 盘上实算」；负例：篡改该文件后跑**普通** `registry` ⇒ `E_FROZEN_MISMATCH` exit≠0 | ① `FROZEN_ENVCLASS_SHA256 = 962cba08…`（与另两份同形；三条锚的**单一定义点** `FROZEN_ANCHORS`，`registry`/`check` 都从这里取）② `verify_specs.sh` §12b 新判据 PASS：`calibration frozen anchors: 3/3 (tool anchor == on-disk sha256 == registry entry)` ③ 负例 A：篡改 `ENVIRONMENT-CLASS.frozen.md` ⇒ `E_FROZEN_MISMATCH` **exit 1**（修复前 `rewritten:true` / exit 0）；负例 B（对照）：篡改 `ACCEPTED-DEGRADATION-RANGE.frozen.md` ⇒ exit 1 ④ 门禁命中能力：只改 registry 的 sha256 ⇒ §12b 判据**红**；只改工具内锚 ⇒ 同判据**红**；未篡改副本 ⇒ 同判据**绿**（非恒红）⑤ 幂等仍成立（`rewritten:false` / `unchanged:true`） | **PASS** |
| **G7**（Raven r2 R2-M6：无条件宣告作废） | `bridge != 'ok'` / `pending_after > 0` 时不得发 `rejected` 作废 ack ⇒ 重试或如实状态 + `downgrade_void_incomplete` 审计；判据：注入「桥超时」⇒ 非作废 ack 或错误事件 | ① 桥侧作废**先重试一次**；仍未确认 ⇒ **保留**会话队列 + ack 降级为 `rejected`+`E_KERNEL_UNAVAILABLE`+detail `rejected_pending_kernel` + 额外 `error` 事件 + `downgrade_void_incomplete` 审计（`voidIncomplete` 读数）② `g7_pristine`（注入 `bridge:'timeout'`）：`void_declarations=0`、`honest_acks=33`、`error_events=1`、`retained_in_queue=33`、`incomplete=1`、`audit=1`、桥侧重试 **2** 次 ③ 负例 `g7_neg_unconditional_void`（作废确认恒真）⇒ `void_declarations=33`、判据**红** ④ 会话套件新增用例真跑 | **PASS** |
| **G8**（Raven r2 R2-M1：边界 + 归属） | `void_intents` 只能作废**本会话**意图（`session_id` 归属校验）+ 负例（跨会话 ⇒ 拒）；边界声明写进 `06` | ① 内核 `void_pending_intents` 的 `session_id` **必填**（缺失/空 ⇒ `ValueError`，零作废）；桥 `void_intents` 缺/空/非字符串 `session_id` ⇒ `refused=E_SESSION_UNKNOWN` + 零作废 ② `g8_pristine_kernel`：跨会话作废只动 `sess_b`（`pending_after=1`）、无归属调用被拒（`pending_after` 不变）、再作废 `sess_a` ⇒ 队列归零 ③ `g8_pristine_bridge`（真桥 + stdin）：`void(sess_b)`⇒`voided=["i-b-1"]`/`pending_after=1`；`void(无 session_id)`⇒`refused=E_SESSION_UNKNOWN`/`pending_after=1`；`void(sess_a)`⇒`voided=["i-a-1"]`/`pending_after=0` ④ 负例两条（内核退回 R2 过滤 / 桥退回 R2 形态）⇒ 判据**红** ⑤ 边界声明见 R3-H | **PASS** |
| **G9**（Raven r2 R2-M7：声称过大） | `06` 里 pin 摘要判据的声称收缩为「防单侧漂移」（不得读成「防篡改」） | R2-A 表的 F6 行**就地**追加：「**R3 / G9 措辞更正：该声称收缩为「防单侧漂移」—— 不读成「防篡改」**（`pins.json` 的 `digests` 与被保护对象在同一棵树里，两侧同改可自洽）」；未加链外锚（本轮不新增机制，属 M4 决策） | **PASS** |
| **G10**（Sentinel r2 LOW：事实错误） | `06` 里「继承偏差无法再复算」更正为「**可复算**」并给命令 | R2-E 段**就地**更正（含命令与读数）：`git cat-file -e 98c781f…^{commit}` ⇒ exit **0**；`git show 98c781f…:v0/02_source/v0_skeleton/kernel/tools/calibrate_latency.py \| shasum -a 256` ⇒ `23fed40d…`（= R1 读数）；原措辞保留以便对照 | **PASS** |

### R3-B 逐 AC 重判（只列与 R2 不同的）

| AC | R2 | R3 | 依据 |
|---|---|---|---|
| **AC-M3-3（渲染层真跑 + 双模式 UI）** | PASS | **PASS（本轮才真正成立）** | R2 的「PASS」只覆盖交互/控件/下行流，**不含可见性**（Sentinel r2 CRITICAL-R2-1）。R3 补齐：canvas 盒随视口（1440×900 / 390×844）、绘制缓冲跟随、HUD 之外非背景像素占比 0.1238/0.3569（阈值 0.05），且两条负例可复现旧缺陷（HUD 外占比 0.0） |
| **AC-M3-8③（同一几何两态）** | PASS | **PASS（判据换成真形状指纹 + 装配路径取数）** | 顶点数**不是**形状指纹（恒 24）；R3 的 `shape_digests` 对尺寸敏感（自证 + `f1e` 红），且新增 mesh 层读回判据（`f1f`/`f1g` 红、Raven a5 形态已封堵） |
| AC-M3-1 / 1c / 1d / 1e / 2 / 4 / 5 / 6 / 7 / 8①②⑤ | PASS | **PASS（回归）** | `verify_specs: OK (129 checks passed, 0 skipped)`；`session npm test 16/16`；`web npm test 4/4`；`scene_assert PASS=27 FAIL=0`；F-4 基线三条读数逐位不变（`chain_tail=baecca92…`、`event_count=925`、`000300.json state_hash=9a4ae3da…`），两次运行 `e.jsonl` **逐字节相同**；定点 pytest **41 passed**；仓库 `develop` / porcelain 0 |

### R3-C 本轮明确不做（含理由与归属，**禁止静默**）

| 项 | 处置 | 理由 / 归属 |
|---|---|---|
| G2 的「链外锚」、G9 的加锚选项 | **不做** | 任务书 §3B-1 把 G9 的加锚列为**可选**；链外锚是机制新增（属 M4 决策），本轮只做措辞收缩 |
| R2-M1 的「桥只接受会话层下发的 mode（令牌/签名）」 | **不做** | 属机制新增（令牌/双 fd），且 §3B-2 已把「桥 = 本地驱动，不是安全边界」写成显式边界；升级条件见 R3-H |
| Sentinel r2 的 MEDIUM-R2-2（两态截图亮度差判据） | **部分**：像素判据覆盖「可见性」，未加「亮度差」断言 | 本轮范围是 G1–G10；两态差异已有 `underneath_lowers_luminance/ambient/light_k` 数值判据 + 浏览器 `two_reads_same_geometry`，观感面留 M4 |
| R2-L1 悬空符号链接、R2-L2 未知读法崩溃、R2-L3 静态 seed、R2-L4 门禁载体 | **不做**（R2-L4 由 §12c 部分覆盖） | 均为 LOW，不在 G1–G10 范围 |

### R3-D 回归读数（本轮亲跑）

| # | 命令（workdir） | 实测 | exit |
|---|---|---|---|
| 1 | `bash verify_specs.sh --quiet`（`02_source`） | `verify_specs: OK (129 checks passed, 0 skipped)` | 0 |
| 2 | `npm test`（`session`） | **16 tests / 16 pass / 0 fail**（含 R3 新增 3 条） | 0 |
| 3 | `npm test`（`web`） | **4 tests / 4 pass / 0 fail** | 0 |
| 4 | `node scripts/scene_assert.mjs`（`web`） | **`scene_assert: PASS=27 FAIL=0`** | 0 |
| 5 | 定点 `pytest`（`test_budget_downgrade_void` / `test_observe_mode_readonly` / `test_task_adaptation` / `test_e2e_run_verify` / `test_calibrate_latency`，`kernel`） | **41 passed in 7.73s** | 0 |
| 6 | 300 tick 基线 ×2（`run` 不传 `--ticks`，产物落 `/tmp/r3-artisan/m3base{,2}`） | `chain_tail=baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786`、`event_count=925`、`000300.json state_hash=9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f`；两遍 `e.jsonl` `cmp` **逐字节相同**（`tick.py` 本轮有改动 ⇒ 该条是**必须**的回归判据） | 0 |
| 7 | `git -C /Users/wooyinq/personal/deep-healing status --porcelain \| wc -l` | **0**（`develop`） | 0 |
| 8 | 生成残渣扫描（`02_source` 内 `node_modules`/`dist`/`.build`/`__pycache__`/`*.pyc`） | **0** 条 | 0 |

- **内核全量套件**：R3 只跑**受影响子集**（41 passed，见上表 #5），**未重跑** 888s 全量（R2 的
  `151 passed in 888.24s` 仍为最近一次全量读数）⇒ 本条**如实标注**为「受影响子集 + R2 全量旁证」，不冒充全量。

### R3-E 门禁冻结面 / 重取登记

- `04_sentinel_test_report.md` / `05_raven_risk_report.md` / `01_*` / `refs/**` / `pm_business/**` /
  真实仓库 / `V0_M1.sha256` / `V0_M2.sha256` / `SEED.sha256` / `06_v0_m1_*` / `06_v0_m2_*`：**本轮零改动**。
- **`V0_M3.sha256` 重取登记**（**最后一步**执行）：
  - **重取理由**：R3 全部写入（交付面 + spikes 证据面 + `03`/`06` 追加 + `superseded/` 迁移）完成后重取，
    使清单与最终字节一致；R2 的清单在 R3 修复前定格，按设计必然失配。
  - **变更清单**：`02_source/**` **12** 个文件改动（`web/index.html`、`web/src/scene/world.ts`、`web/src/main.ts`、
    `web/scripts/scene_assert.mjs`、`verify_specs.sh`、`tools/scan_ip_boundary.py`、`session/src/policy.js`、
    `session/src/server.js`、`session/test/session.test.js`、`session/bridge/kernel_bridge.py`、
    `kernel/deephealing_kernel/tick.py`、`kernel/tools/calibrate_latency.py`）；
    `spikes/s13-render/**`（驱动/判据/日志/截图/负例）、`spikes/s12-session/**`（负例套件 + `superseded/` 迁移 + 变更声明）；
    根级 `03_artisan_self_test.log`、`06_v0_m3_self_test.md` 追加 R3 段。
  - **排除项新增**：`superseded/**`（作废证据集，见 G3）。
  - **采集面外文件（显式声明）**：`<ws>/V0_M3.sha256.retake.json`（重取链 + 终值哈希；放在采集面外是**有意**的：
    清单包含 `06`，若把清单自身哈希写进 `06`，写完即自我作废）。
  - **前后哈希**：重取前（R2 清单，255 条目）`V0_M3.sha256` sha256 = `93443b70…`（R2 终值）；
    重取后条目数与终值哈希登记在 `<ws>/V0_M3.sha256.retake.json`（复算命令 `shasum -a 256 V0_M3.sha256`）。
  - **自引用滞后（如实声明）**：`V0_M3.sha256` 自身不入清单，但清单**包含 `06_v0_m3_self_test.md`**；
    本登记段写入后又重取一次清单 ⇒ 复跑得到哈希会比 R2 链上的值更新，差异**仅为本段文字**。
  - 校验方式：`shasum -a 256 -c V0_M3.sha256`（在 `<ws>` 下）应**全 OK**（`superseded/**` 已排除）。

### R3-F 已知风险 / 未覆盖面（如实登记）

1. **`createScene` 的 headless 退化**：无 WebGL 环境（Node）下渲染器退化为空实现（只有光栅化不可用），
   几何与场景图照常装配 —— `scene_assert` 因此能与浏览器跑**同一条装配路径**。这是为「判据经应用装配路径取数」
   付出的设计代价，已在 `world.ts` 与 `scene_assert.mjs` 的注释里显式说明。
2. **像素判据依赖固定 HUD 包围盒**：判据用真浏览器读到的 `#hud` 矩形（不是硬编码坐标），
   若未来 HUD 变成可拖拽/自适应，阈值需要重测。
3. **G1 的 DPR 分支未在本机实测**：本机 `devicePixelRatio = 1`（headless 默认），
   DPR>1 的路径只做了「缓冲 ≥ canvas 盒 且 ≤ 盒×min(dpr,2)」的区间判据，未在 2x 屏幕上真跑。
4. **桥的 `mode` 仍是调用方自述**（R2-M1 残留）：本轮只加了 `void_intents` 的**归属**校验；
   「显式 `participate` 即可写世界」是 D-1 的设计边界，升级条件见 R3-H。
5. **内核全量套件未重跑**（见 R3-D 末注）。
6. **`spikes/s12-session/logs/` 下 R1 其余非崩溃型日志仍在**：它们不是 G3 点名的作废对象，
   但**汇总结论以 R2/R3 的证据集为准**（`superseded/README.md` 已写明「不并存」的处置）。

### R3-G 交付面卫生

- `02_source` 文件数 **150**（与 R2 一致：本轮**零新增文件**、零删除）；`manifest.txt` **未改**（无新增/删除文件）。
- `02_source` 内 `node_modules`/`dist`/`.build`/`__pycache__`/`*.pyc` = **0**（收尾实测；全程 `PYTHONDONTWRITEBYTECODE=1`/`-B`）。
- `spikes/s5-latency-calibration/*.frozen.md` **字节未动**（G6 只加工具内锚，不改冻结物）；
  `calibration.registry.json` 内容未变（幂等读数 `rewritten:false`）。

### R3-H 边界声明（写进交付物，供下一位读者）

- **桥（`session/bridge/kernel_bridge.py`）是本地驱动，不是安全边界**：`intent` 的 `mode` 由调用方**显式声明**，
  缺省 fail-closed（16 种非法形态全拒）；`step` 推世界、`snapshot` 只读；本轮新增的 `void_intents`
  **必须带 `session_id`**（内核侧 `session_id` 亦为必填 ⇒ 无归属/跨会话作废一律拒），
  但「显式 `participate`」仍即可写世界 —— 这与 D-1「会话层是唯一上行入口」一致。
- **升级条件**：**M4 一旦把桥 / 会话层接上 WS（或任何网络）监听 ⇒ 本层升为 CRITICAL**，
  必须先落「桥只接受会话层下发的 mode（令牌/签名或双 fd）+ 每主体会话配额 + 会话 TTL + 回收」，
  否则「自述权限」会变成可远程触达的第二个权限入口。
- **本轮是最后一次修复迭代（3/3）**：R3 之后的聚焦复验若冒出**新 CRITICAL**，按
  `exceed_iteration_human_intervene` 上抛 PM，**不再开新一轮**。
- `spikes/s5/**` 不在 `V0_M3.sha256` 采集面 ⇒ 该目录的改动必须**主动**登记进 `m3-change-face.txt`（本轮 G6 的
  工具内锚改动落在 `02_source/v0_skeleton/kernel/tools/calibrate_latency.py`，在采集面内；冻结物字节未动）。

### R3-I 与双门禁的对应

| 门禁条目 | 处置 |
|---|---|
| Sentinel r2 **CRITICAL-R2-1**（3D 世界不可见） | **G1** ⇒ 已修，像素判据 + 两条负例（含与 architect 探针逐值吻合的旧缺陷复现） |
| Raven r2 **R2-C1**（几何判据换层皮） | **G2** ⇒ 已修，形状指纹 + 装配路径（含 mesh 层）+ 三条负例 |
| Raven r2 R2-M1（桥权限自述 / 跨会话作废） | **G8** ⇒ 归属校验必填 + 双负例；边界与升级条件见 R3-H |
| Raven r2 R2-M2（锚覆盖不全） | **G6** ⇒ 三条锚 + 门禁判据 + 4 条负例 |
| Raven r2 R2-M3（两套互斥结论） | **G3** ⇒ `superseded/` + 就地作废标注 + 排除项 |
| Raven r2 R2-M4（白名单整份豁免） | **G4** ⇒ 行级豁免 + 自排除 + `art-bible` 真越界负例 |
| Raven r2 R2-M5（已 ack 却永不应用） | **G5** ⇒ 合并键含 target + 出队登记 + 负例 |
| Raven r2 R2-M6（无条件宣告作废） | **G7** ⇒ 重试 + 如实 ack + 错误事件 + 审计 + 负例 |
| Raven r2 R2-M7（pin 声称过大） | **G9** ⇒ 就地收缩为「防单侧漂移」 |
| Sentinel r2 LOW-R2-1（继承偏差不可复算） | **G10** ⇒ 就地更正为「可复算」+ 亲跑命令与读数 |
| Sentinel r2 MEDIUM-R2-1（网格层绕过） | **G2③c**（`f1g`）⇒ 已封堵 |
| Sentinel r2 MEDIUM-R2-2（两态截图无可见性读数） | **G1②**（像素判据）部分覆盖；亮度差断言未做（见 R3-C） |

================================================================================
## R4 段（**有界补丁轮** · 关闭 `R3-C1`，**判据层** · `--max-iteration 1`）—— artisan 判定
================================================================================

- 轮次：R4（PM 授权的有界补丁轮，**只有一轮**）　任务书：`<ws>/.task-artisan-r4.md`　run-budget 3600s
- 判据权威：`01_architecture_design.md` §3C　约束：`<ws>/.round4-constraint.txt`
- 开工快照：repo `/Users/wooyinq/personal/deep-healing` = `develop` @ `98c781f4040d9b17757d67ba8e76fed1b95bfa12`，
  `status --porcelain | wc -l` = **0**（收尾复测仍 0）
- 本轮范围：**只**关闭 `R3-C1`（判据层）。未新增 AC、未改 AC 口径、未放宽既有判据、未删既有负例、未改实现语义
- 改动面声明写在**任何编码之前**：`spikes/s12-session/m3-change-face.txt` 的 `SECTION A-R4`（epoch 锚 1790102600）
- 负例口径：一律 `/tmp/r4-artisan/**` 的整树副本；`turned_red` 只给 `judged_red`；逐 case 实测
  `delivery_face_unchanged`；`crash` 单列（本轮 0 条）
- 逐条命令 + workdir + exit + 读数 + 负例配方 + RED 阶段读数见 `03_artisan_self_test.log` 的 **R4 段**

### R4-A 逐条关闭判据

| 项 | 关闭判据（§3C） | 实测 | 判定 |
|---|---|---|---|
| **R4-A 判据加宽**（§3C-2） | 每 box 的 `scale`（三分量）+ `rotation`/`quaternion`（四分量）进**形状指纹**与 `geometry_digest`；`assemblyReport()` 的 mesh 层读回同样纳入并给可逐项比较的读数；`two_reads_share_rendered_geometry` 比较面扩到 ids / shape_digests / mesh_positions / **mesh_scales** / **mesh_rotations** / geometry_digest；取数仍一律经 `createScene()` 句柄 | `EntityBox` 增 `scale`/`quaternion`（默认 `[1,1,1]`/`[0,0,0,1]`）且 `rebuild()` **真写入** mesh；`EntityShape`/`shapeDigestString()` 纳入二者（6 位小数）；`assemblyReport()` 从 mesh 读回 `mesh.scale`/`mesh.quaternion` 并新增 `mesh_scales`/`mesh_rotations`（12/12 实体）；基线 `scene_assert: PASS=29 FAIL=0` exit 0（**旧 27 条一条未掉**） | **PASS** |
| **R4-B 相机一致性判据**（§3C-3） | `SceneHandle` 增 `cameraReport()`（`position[3]`/`quaternion[4]`/`fov`/`near`/`far`/`aspect`，**从 `THREE.Camera` 实例读回**）；`scene_assert.mjs` 增 `two_reads_share_camera`（**同一视口下**两态逐项相同，两次读法之间**不做 resize**）；`aspect` 是否参与相等断言由实现决定并在此声明 | `cameraReport()` 只读活相机实例；新增 `two_reads_share_camera`（读数 `position=[18,14,24]` / `fov=45` / `near=0.1` / `far=500` 两态逐项相同）+ `scene_handle_camera_report_is_live`（分量形状 + 有限数 + `cameraReport().aspect == viewport().aspect` 自证读数来自活相机）。**`aspect` 不参与相等断言**（信息性读数；理由见 R4-D） | **PASS** |
| **R4-C 负例**（§3C-4） | 4 条 case（scale / rotation / camera / 对照 position），**一律整树副本**（`NEGCTL_ROOT=/tmp/r4-artisan`）；`turned_red` 只给 `judged_red`，每条给 `delivery_face_unchanged=true`；载体二选一并声明 | 载体选**新增** `spikes/s13-render/negctl/f5_r4_judgement_negctl.py`（复用 `negctl_lib`；**未改** `f1_*` 既有 CASES）。`r4_neg_mesh_scale` / `r4_neg_mesh_rotation` / `r4_neg_camera_switch` 全 `judged_red`（`fail_names` 分别为 `two_reads_share_rendered_geometry` ×2 / `two_reads_share_camera`），对照 `r4_ctl_position_shift` **仍红**；`turned_red=4/4`、`crashes=[]`、`escapes=[]`、逐 case `delivery_face_unchanged=True`、`all_ok=True` | **PASS** |
| **R4-D 边界声明**（§3C-5） | 在 `06` R4 段写清**覆盖什么 / 不覆盖什么**，并显式写明**不是防篡改机制** | 见下方 **R4-D** 段（逐字照 §3C-5 口径） | **PASS** |
| **R4-E 回归守卫**（§3C-6 / 任务书 R4-E） | `world.ts` 有改动 ⇒ **必须**复跑官方门禁驱动 `python3 -B spikes/s13-render/negctl/f4_browser_negctl.py` ⇒ `all_ok=True`、`delivery_face_unchanged=True`、pristine `judged_green`、3 条负例全 `judged_red` 且 pattern 命中 | 复跑（修正 `geometry_digest` 口径后 ⇒ 终值）exit 0：`all_ok=True`、`delivery_face_unchanged=True`、`[f4_pristine] all_checks_pass=True failed=[]`、3 条负例 `all_checks_pass=False` 且 `patterns` 全部命中（失败集合**只剩**期望 pattern） | **PASS** |

> **RED（修复前）可复核证据**：加宽**前**在整树副本上跑同一 4 条 case ⇒ `r4_neg_mesh_scale` /
> `r4_neg_mesh_rotation` / `r4_neg_camera_switch` 全部 `judged_green`（`PASS=27 FAIL=0` exit 0 = **逃逸**），
> 对照 `r4_ctl_position_shift` `judged_red`（`PASS=26 FAIL=1` exit 1）⇒ **逐项复现** PM 的读数 B/C/D/E。
> 证据：`spikes/s13-render/logs/f5-r4-negctl-summary-red.json`、`spikes/s13-render/logs/r4-red-before-widening.log`。

### R4-B 逐 AC 重判（只列与 R3 不同的）

| AC | R3 | R4 | 依据 |
|---|---|---|---|
| **AC-M3-8③（同一几何两态）** | PASS（判据 = 真形状指纹 + 装配路径） | **PASS**（R4 面**覆盖**：装配变换进形状指纹 + mesh 层读回 + `mesh_scales`/`mesh_rotations`；R4 面**不覆盖**：相机投影面（`zoom`/`projectionMatrix`/`viewOffset`）、几何拓扑面（`index`/`groups`）、世界根与父级变换、`visible`/`layers`/`renderOrder`/第二相机 —— 逐条见 **R5 段**的覆盖/不覆盖清单） | R3 的 PASS 建在 `two_reads_share_rendered_geometry` 上，而该判据**名不副实**（比较面缺 `scale`/`rotation`、相机**零判据**）⇒ 按 PM 口径属**假绿**（CRITICAL `R3-C1`）。R4 加宽后：装配变换进指纹 + mesh 层读回 + 逐项暴露，相机新增一致性判据；三条注入真变红、对照仍红，且**实现语义一字未改**（默认单位变换、两态仍共用同一几何、基线 `PASS=29 FAIL=0`）。**R5 复验**：R4 面未闭合的四类（`R4-C1`/`R4-C2`/`R4-M1` + 对象面）在 R4 树上实测**逃逸**（13 条，见 R5 段），R5 闭式面闭合后逐条真红 |
| AC-M3-1 / 1c / 1d / 1e / 2 / 3 / 4 / 5 / 6 / 7 / 8①②④⑤ | PASS | **PASS（回归）** | `verify_specs: OK (130 checks passed, 0 skipped)`；`session npm test 16/16`；`web npm test 4/4`；`scene_assert PASS=29 FAIL=0`；内核受影响子集 **41 passed**；F-4 基线三条读数**逐位不变**（`chain_tail=baecca92…` / `event_count=925` / `000300.json state_hash=9a4ae3da…`）；仓库 `develop` @ `98c781f`、porcelain **0**；`02_source` 文件数 **150**、生成残渣 **0** |

### R4-C 本轮明确不做（含理由与归属，**禁止静默**）

| 项 | 处置 | 理由 / 归属 |
|---|---|---|
| 把相机一致性判据也加进**真浏览器**驱动（`f4` / `browser-accept.mjs`） | **不做** | §3C-3 只要求 `scene_assert.mjs` 的 `two_reads_share_camera`；`f4` 本轮只作**回归守卫**复跑（world.ts 有改动 ⇒ 必须复跑）。浏览器侧加相机读数属**可选强化**，且需动 `browser-accept.mjs` 的读数结构 ⇒ 留 M4/后续（不扩张本轮范围） |
| 在 `main.ts` 暴露 `cameraReport()` | **不做** | `main.ts` **不在** R4 写集白名单内（§3C-7）；浏览器侧当前无消费方 ⇒ 无必要 |
| 链外锚 / 防篡改机制 | **不做** | 本判据是**一致性判据**，不是防篡改（见 R4-D，参照 G9 处置口径）；加锚属机制新增，不在本轮范围 |
| 内核**全量**套件重跑 | **不做**（只跑受影响子集 41 passed） | 本轮**未触及内核侧**（`shasum -c` 差集里内核文件 **0** 条）；R2 的 `151 passed / 756.14s`（PM 亲跑）为最近一次全量读数（旁证） |

### R4-D 边界声明（覆盖 / 不覆盖；供下一位读者，**逐字照 §3C-5 口径**）

- **覆盖**：
  1. 每 box 的 `size` / `geometry.parameters` / `position` attribute 摘要（微米级量化 + FNV-1a 64）；
  2. **装配层与装配后 mesh 层**的 `position` / `scale` / `quaternion`（`assemblyReport()` 从 mesh 读回，
     并给 `mesh_positions` / `mesh_scales` / `mesh_rotations` 三份可逐项比较的读数）；
  3. 两态**相机参数逐项一致**：`position` / `quaternion` / `fov` / `near` / `far`（`cameraReport()` 从
     `THREE.Camera` 实例读回）；
  4. 全部经 `createScene()` 句柄取数（含 **headless 退化路径** = 与浏览器**同一条装配路径**）。
- **不覆盖**：
  1. 光栅化 / 像素层结果（材质色、光照、shader 输出）—— 由治愈系数值断言（`underneath_lowers_*` 等）
     与**真浏览器**证据（`f4` 的像素判据 / 截图）**另**覆盖；
  2. `meshes` 表**之外**的对象（`scene.background` / `fog` / 额外 `Group`）；
  3. `aspect` 之外的渲染器状态（尺寸变化由 `viewport()` 判据覆盖）；GL 状态（blend / depth 等）；
  4. 绕过 JS 层的运行时篡改（如直接改 WebGL buffer）。
- **口径（硬）**：本判据是**一致性判据**，**不是**防篡改 / 完整性机制 —— **不得**读成「防篡改」
  （参照 G9 处置口径：本判据只能证明「两态读到的装配结果一致」，**不能**证明「没有人能改这两处」）。
- **`aspect` 口径声明**：`aspect` 是**视口派生量**（由 `resize()` 从画布盒推导），**不参与**
  `two_reads_share_camera` 的相等断言，只作**信息性**读数；视口尺寸的正确性由 `viewport_follows_canvas_box`
  与 `f4` 的 `*_canvas_rect_*` / `*_drawing_buffer_follows_canvas` 覆盖。理由：把视口派生量混进
  「读法切换不得造成差异」的断言，会让判据在**合法 resize** 下假红。
- **装配 `geometry_digest` 不含世界坐标（有意口径，与 R3 一致）**：`mesh_positions` 是**跨 tick 合法变化**的量
  （真浏览器里 delta 会移动 NPC），若拼进摘要则判据会**假红**（本轮实测已复现并修正，见 `03` R4-7）。
  坐标由 `mesh_positions` **单独逐项比较**（在静态状态上跑），`scale`/`quaternion` 是恒定装配变换 ⇒ 进摘要安全。

### R4-E 门禁冻结面 / 重取登记

- `04_sentinel_test_report.md` / `05_raven_risk_report.md` / `01_*` / `refs/**` / `pm_business/**` /
  真实仓库 / `V0_M1.sha256` / `V0_M2.sha256` / `SEED.sha256` / `06_v0_m1_*` / `06_v0_m2_*`：**本轮零改动**。
- **开工时的冻结面差集（如实登记一条 R3 遗留漂移）**：`shasum -a 256 -c V0_M3.sha256` 实测
  **262 OK / 37 非 OK**。分类（mtime 为证）：**34 条** = `spikes/s13-render/logs/**` 的 R3 时代 f4 产物
  （截图 / `browser-accept-*.json` / `console-*.jsonl` / `serve-summary-*.json` / `negctl-f4_*.log`）
  + `spikes/s12-session/logs/emitted-messages.jsonl`，mtime **02:28:02–02:32:06**，**晚于** R3 清单重取时刻
  **02:08:35** ⇒ 属 **R3 遗留漂移**（清单定格后又跑了一次真浏览器 f4），**不是本轮引入**；其余 **3 条**为本轮声明面。
  该读数与 `.round4-constraint.txt` §0 记的「299 OK / 0 FAILED」**不一致**，本轮**无法复现**该读数，如实记录。
- **`V0_M3.sha256` 重取登记**（**最后一步**执行；工具 = `spikes/s12-session/scripts/retake-v0-m3.py`，采集面/排除项**逐字沿用**）：
  - **重取理由**：R4 全部写入（交付面 2 文件 + `spikes/**` 证据面 + `03`/`06` 追加 R4 段）完成后重取，
    使清单与最终字节一致；同时**归零**上面那 34 条 R3 遗留漂移（本轮 f4 复跑已重写同一批产物）。
  - **变更清单（`02_source`）**：**2** 个文件 —— `v0_skeleton/web/src/scene/world.ts`、
    `v0_skeleton/web/scripts/scene_assert.mjs`（**零新增 / 零删除**，`02_source` 文件数仍 **150**）。
  - **变更清单（采集面其余）**：`spikes/s13-render/negctl/f5_r4_judgement_negctl.py`（新增负例载体）、
    `spikes/s13-render/logs/`（`negctl-r4_*.log` ×5、`f5-r4-negctl-summary.json`、
    `f5-r4-negctl-summary-red.json`、`r4-red-before-widening.log`、`r4-green-after-widening.log`、
    `r4-diff-review.log`、`r4-f4-run.log`）、`spikes/s13-render/logs/` 的 R3 时代 f4 产物（f4 复跑重写）、
    `spikes/s12-session/m3-change-face.txt`（`SECTION A-R4`）、根级 `03` / `06`（追加 R4 段）。
  - **采集面外文件（显式声明）**：`<ws>/V0_M3.sha256.retake.json`（重取链 + 终值哈希；放采集面外是**有意**的：
    清单包含 `06`，若把清单自身哈希写进 `06`，写完即自我作废）。
  - **前后哈希**：重取前（R3 清单，299 条目）`V0_M3.sha256` sha256 = `1745b029c38d8f32647ce35ae861d4d82d5ee863d63a8d5969d3e74d144d63d3`；
    重取后条目数与终值哈希登记在 `<ws>/V0_M3.sha256.retake.json`（复算命令 `shasum -a 256 V0_M3.sha256`）。
  - **重取后自校验**：`cd <ws> && shasum -a 256 -c V0_M3.sha256` ⇒ **全部 OK / 0 条非 OK**（exit 0）；
    实测条目数与终值登记在采集面外的 `<ws>/V0_M3.sha256.retake.json`（字段 `entries` / `final_sha256` / `self_check`）。
  - **自引用滞后（如实声明）**：`V0_M3.sha256` 自身不入清单，但清单**包含 `06_v0_m3_self_test.md`**；
    本段写入后**才**重取 ⇒ 复跑得到哈希即最终值，无滞后（重取是本轮**最后一步**）。

### R4-F 已知风险 / 未覆盖面（如实登记）

1. **`createScene` 的 headless 退化**（沿用 R3）：无 WebGL 时渲染器退化为空实现，只有光栅化不可用；
   几何与场景图照常装配 ⇒ `scene_assert` 与浏览器跑**同一条装配路径**（不是为绿放宽：被断言的量一个没变）。
2. **装配 `geometry_digest` 有意不含世界坐标**（见 R4-D）：只读 `geometry_digest` 的消费者看不到坐标变化，
   必须同时读 `mesh_positions`。这是为**避免跨 tick 假红**付出的设计代价（本轮实测复现过该假红）。
3. **相机判据的 `aspect` 被排除**（见 R4-D）：若未来有人在两次读法之间 `resize()`，本判据不会察觉 ——
   属**有意**口径（视口尺寸另有判据），但读者不得把它读成「相机完全未变」的充分证明。
4. **本判据不是防篡改**（见 R4-D）：它证明一致性，不证明完整性；绕过 JS 层的运行时篡改（直接改 WebGL buffer）
   不在覆盖内。
5. **R3 遗留漂移的流程风险仍在**：`V0_M3.sha256` 是**时点快照**，而 f4 会重写 `spikes/s13-render/logs/**`
   与 `spikes/s12-session/logs/emitted-messages.jsonl` ⇒ **清单定格后任何一次真浏览器复跑都会让 34 条失配**。
   本轮按「重取放最后一步」处置；M4 建议把 f4 产物纳入排除项或每次复跑后重取（属 M4 决策，本轮不扩张范围）。
6. **内核全量套件未重跑**（见 R4-C）：本轮未触及内核侧，只有受影响子集 41 passed + PM 亲跑的 151 passed 旁证。
7. **浏览器侧未加相机判据**（见 R4-C）：`two_reads_share_camera` 只在 Node 侧（与浏览器同一装配路径）跑；
   真浏览器只由 f4 的既有判据覆盖。

### R4-G 交付面卫生

- `02_source` 文件数 **150**（与 R3 一致：本轮**零新增 / 零删除**）；`manifest.txt` **未改**。
- `02_source` 内 `node_modules` / `dist` / `.build` / `__pycache__` / `*.pyc` / `.pytest_cache` = **0**
  （收尾实测；全程 `PYTHONDONTWRITEBYTECODE=1` / `-B`；全树 `*.pyc` 亦为 0）。
- 真实仓库 `/Users/wooyinq/personal/deep-healing`：`develop` @ `98c781f`，`porcelain` = **0**（未 add/commit/push）。

### R4-H 与双门禁的对应（供 Sentinel / Raven 复验）

| 门禁条目 | 处置 |
|---|---|
| PM 裁决 `R3-C1`（**CRITICAL**：`two_reads_share_rendered_geometry` 名不副实，可被 `scale`/`rotation` 注入绕过） | **R4-A** ⇒ 装配变换进形状指纹 + mesh 层读回 + `mesh_scales`/`mesh_rotations` 逐项比较；`r4_neg_mesh_scale` / `r4_neg_mesh_rotation` 真变红 |
| PM 裁决 `R3-C1` 第二半（D-7「禁止换相机」**零判据**） | **R4-B** ⇒ 新增 `two_reads_share_camera` + `scene_handle_camera_report_is_live`；`r4_neg_camera_switch` 真变红（该 case 的**期望**失败点即该判据）。**R4 面不覆盖**：相机 `zoom` / 手改 `projectionMatrix` / `setViewOffset`（PM 复现 `R4-C1` 逃逸）⇒ 由 **R5-A** 的相机结构面闭合 |
| 负例可复核性（Raven r2 的既有口径） | **R4-C** ⇒ 4 条 case 全在 `/tmp/r4-artisan` 整树副本；逐 case `delivery_face_unchanged` 实测；`crash` 单列（0 条）；对照负例仍红 |
| 「判据不得被读成防篡改」（G9 口径） | **R4-D** ⇒ 边界声明就地写明「一致性判据 ≠ 防篡改」 |
| 回归不得退化 | **R4-E** ⇒ 官方门禁 `f4_browser_negctl.py` `all_ok=True`；`verify_specs` 130 / 0 skipped；session 16/16；web 4/4；`scene_assert PASS=29 FAIL=0`；F-4 三条读数逐位不变；仓库 porcelain 0 |
| **本轮为有界补丁轮（`--max-iteration 1`）** | 未冒出新的 CRITICAL；若 Sentinel / Raven 复验冒出需修复的新 CRITICAL ⇒ 按 `exceed_iteration_human_intervene` 上抛 PM，**不再开新一轮** |

---

## R5 段（**终局有界轮** · 判据闭式化 + 去过度声称 + 冻结面口径修正 · `--max-iteration 1`）—— artisan 判定

- 计划：`REQ-20260921-005-deephealing-v0-m3`；约束权威 `<ws>/.round5-constraint.txt`（PM 对 `R4-C1` / `R4-C2` / `R4-M1` / `R4-M4` 的裁决）；设计输入 `<ws>/.r5-architect-design.md`
- **编码前 epoch 锚：1790104852**（2026-09-23 03:20:52 CST）—— 见 `spikes/s12-session/m3-change-face.txt` 的 `SECTION A-R5`；该值**早于** R5 的第一次代码改动（也早于该文件的第一次追加）
- 逐条真实命令 + workdir + exit + 读数 + 负例配方 + RED 相位读数见 `03_artisan_self_test.log` 的 **R5 段**
- **这是本问题的最后一轮**：本轮未再自开新一轮、未自行降级、未把判据调回放行

### R5-A 逐条关闭判据

| 项 | 关闭判据（§1.1 / §1.2 / §1.3） | 实测 | 判定 |
|---|---|---|---|
| **R5-A 判据闭式化**（§1.1） | 两态比较面从「逐字段白名单」改为对**结构性场景状态**的**闭式摘要**：几何 `index`（`{present,count,digest}`，无 index 显式 `null`）/ `groups`（逐组 `start/count/materialIndex`）/ 每个 attribute 的 `{name,itemSize,count,digest}`（至少 `position`/`normal`/`uv`，缺失显式 `null`）；每 mesh 的 `matrixWorld` **16 分量逐项**（覆盖根变换 / 父级 Group / `matrixAutoUpdate`）/ `visible` / `layers.mask` / `renderOrder`；场景**根子树**的对象身份与父子关系；相机 `matrixWorld` / `projectionMatrix`（各 16）/ `zoom` / `view_offset`（含 `enabled`）/ `fov` / `near` / `far`；**「实际用于渲染的相机身份」**（约束 §1.1 的**原措辞**）—— R5 落地的比较量是**渲染入参身份**（`renderer.render(scene, camera)` 的入参，由包装器**自报**；**不等于**「渲染器内部真正使用的相机」，限定见 R5-C 第 7 条） | `world.ts`：新增 `structureReport()`（遍历式摘要，几何结构 + 对象结构）、渲染器包装器（**逐次记录 `renderer.render()` 的实际入参**）、`renderOnce()` / `renderCameraReport()`、`cameraReport()` 扩面；`scene_assert.mjs`：`two_reads_share_rendered_geometry` **改名并加宽**为 `two_reads_share_scene_structure`、`two_reads_share_camera` 扩面、新增 `two_reads_use_same_render_camera` + `scene_handle_structure_report_is_live`；基线 `node scripts/scene_assert.mjs` ⇒ `PASS=31 FAIL=0` exit 0（**既有 27 条一条未掉**；R4 = 29 ⇒ 条数**上升**，未下降）；**渲染与装配语义**未变（R5 只**增读数与包装**，逐条列出：`structureReport()` / `renderOnce()` / `renderCameraReport()` / 渲染包装器（记录 `renderer.render()` 入参）/ `cameraReport()` 扩面 —— `scale`/`quaternion` 仍默认单位变换，两态仍共用同一几何与相机）；**不覆盖项**见 R5-C 的 13 条 | **PASS** |
| **R5-B 去过度声称**（§1.2） | 断言名去掉 `rendered`；`06` R4-A/R4-B 与 R5 段去**绝对**措辞（改「覆盖 X（逐条）/ 不覆盖 Y（逐条）」）；就地写明「本判据是一致性判据，**不是**防篡改 / 完整性机制」（G9） | 名字取 `two_reads_share_scene_structure`（**名字即比较面**）；R4-A/R4-B 的「本轮才真正成立」「唯一失败点即该判据」**已就地更正**（更正声明见 **R5-D**）；`scene_assert.mjs` 头注 + 本段就地写明 G9 口径 | **PASS** |
| **R5-C 冻结面口径修正**（§1.3） | 可重生成的运行产物移出哈希面 + 清单头部**显式声明** + 最后一步重取 + **任意次数真浏览器复跑后 `shasum -c` 仍全 OK**，并**单独报** `02_source` OK 条数 | 排除项变更 `removed=110` / `added=1`（逐条命中声明模式、**全部**在 `spikes/*/logs/` 子树内、**全部**是可重生成运行产物）；头部显式声明「运行产物 = 可重生成，不入哈希面；其判据结论由门禁退出码与 `06` 登记承担」；**复跑 f4 前后对整条采集面（202 条）逐文件 sha256 ⇒ 差异为空**；重取后复跑 f4 再 `shasum -c` ⇒ **全 OK**（读数见 **R5-F**） | **PASS** |
| **R5-D 负例矩阵 A–I**（约束 §4-2） | 每条真跑；每条给 注入 → exit / `PASS` / `FAIL` / **期望 fail name** / **自算的 `delivery_face_unchanged`**；`turned_red` 只给 `judged_red`；`crash` 单列 | GREEN 相位：`turned_red=23`、`escapes=[]`、`crashes=[]`、逐 case `delivery_face_unchanged=True`、`all_ok=True`；RED 相位（**加宽前**整树副本）：13 条**真逃逸**（B×4 / C×1 / D×3 / E×3 / G×2）⇒ 逐条复现 PM 的 `R4-C1` / `R4-C2` / `R4-M1` | **PASS** |
| **R5-E 回归守卫** | `world.ts` / `scene_assert.mjs` 有改动 ⇒ 复跑官方门禁 `f4_browser_negctl.py` + 全量回归 | f4 ⇒ `all_ok=True`、`delivery_face_unchanged=True`；`verify_specs: OK (130 checks passed, 0 skipped)`；session `16/16`；web `4/4`；内核受影响子集 **41 passed**；300 tick 三条读数**逐位不变**；`02_source`=**150** / 残渣 **0**；仓库 `develop` @ `98c781f`、porcelain **0** | **PASS** |

### R5-B 覆盖清单（逐条 —— 覆盖清单 = 本判据比较面的**全部条目**；其**不覆盖项**见 R5-C 的 **13 条**）

1. **几何结构面**：`geometry.index`（`present` / `count` / 数组摘要；无 index ⇒ 显式 `null`）、`geometry.groups`（逐组 `start` / `count` / `materialIndex` + 组数组摘要）、每个 attribute 的 `name` / `itemSize` / `count` / 摘要（**至少** `position` / `normal` / `uv`，缺失者显式 `null`）。
2. **对象结构面**：每个 mesh 的 `matrixWorld` **16 分量逐项**（量化 `1e-6`；覆盖根变换 / 父级 Group / `matrixAutoUpdate` 的**效果** —— 见 R5-C 第 12 条的**限定**）、`visible`、`layers.mask`、`renderOrder`。
3. **场景根子树**：对象**身份**（稳定身份 = `name`，无名字时 `类型#序号`）与**父子关系**（`{id, parentId, type}` 有序列表 + 摘要）。
4. **相机结构面**：`matrixWorld` / `projectionMatrix`（各 16 分量逐项）/ `zoom` / `view_offset`（含 `enabled`）/ `fov` / `near` / `far`。
5. **渲染入参身份**（R5-FIX / F6(b) 限定：= 包装器**自报**的 `renderer.render(scene, camera)` **入参**（`类型#uuid`），**不等于**「渲染器内部真正用于渲染的相机」，见 R5-C 第 7 条）⇒ 「第二相机（用于 underneath 渲染）」形态有牙。
6. **R4 面保留**（不得回退）：`entity_ids` / `shape_digests` / `mesh_positions` / `mesh_scales` / `mesh_rotations` / 装配 `geometry_digest`；**既有 27 条断言一条未掉**。
7. **负例可复核性**：一律整树副本 + 逐 case **自算**的 `delivery_face_unchanged`（交付面目录级 sha256 跑前/跑后）+ `crash` 单列 + `turned_red` 只给 `judged_red`。

### R5-C 不覆盖清单（逐条 + 理由）

1. **光照 / 材质色相与明度**：两态**按设计必须不同**（AC-M3-8④ 正是这条）⇒ 纳入闭式面会与设计冲突；由 `underneath_does_not_raise_saturation` / `underneath_lowers_luminance` / `underneath_lowers_ambient` / `underneath_lowers_light_k` 单独判。**范围限定（R5-FIX）**：本条只声明「**色相与明度**」；材质的 `roughness` / `metalness` / `map` **不在**闭式面内（见第 11 条）。
2. **光栅化 / GPU 层结果**（直接改 WebGL buffer、shader 篡改）：JS 层读数看不见。本判据是**一致性判据**，不是 GPU 层完整性机制。（**Node 面无可真注入的路径** ⇒ 该条为**推演**，由 f4 的像素判据承担；Sentinel 以 `grep` 复核「`scene_assert.mjs` 内 0 处真读 WebGL」。）
3. **摘要取完之后的时序篡改**：判据只在读数窗口内比较；窗口外（或两读完成之后）的改动不在面内。
4. **DOM / HUD 层**：由 f4 的控件表（观察模式无写控件）与像素判据（HUD 之外可见世界）覆盖，不在本判据面。
5. **`aspect`**（视口派生量）：**字段级**不参与相等断言（纳入会与合法 `resize()` **假红**，R4-E-b 实测 `1.6 → 1.125`）⇒ 保持**信息性**读数；视口尺寸由 `viewport_follows_canvas_box` 覆盖。**限定（R5-FIX / F6(a)）**：`projectionMatrix` 由 `aspect` 派生且**在面内** ⇒ 本判据对**两读窗口内**的视口变化**间接敏感**（实测 `two_reads_share_camera` **红**：`/tmp/sentinel-r5/cases/green/h_x_resize_inside_window`、`/tmp/raven-r5/results.jsonl` 的 `r3b`）—— 不可读成「`aspect` 变化不影响判据」。
6. **两读窗口内改变视口**（画布尺寸变化）：此时 `projectionMatrix` **合法**变化 ⇒ 本判据会红。这是**口径边界**（沿用 R4 的「两读之间不做 resize」），R5 的 H 组给出两种合法 resize 形态的读数（窗口内幂等 resize 仍绿；窗口外改视口仍绿）。
7. **`render()` 入参以外的「间接换相机」形态**（例如在渲染器内部替换相机对象、或渲染前临时改写渲染器状态）：本轮只覆盖**入参身份**这一层。**限定（R5-FIX / F6(b)）**：本判据比较的量是「**渲染入参身份**」= 包装器**自报**的 `renderer.render(scene, camera)` 入参，**不等于**「渲染器内部真正用于渲染的相机」；反证 = Raven `r2a`（渲染器内部换相机 ⇒ `PROBE stub_saw=INDIRECT` 而 `recorded=PerspectiveCamera#c29ae076…` ⇒ 判据**绿**）。
8. **量化边界 `1e-6`**（R5-FIX / F1①，Raven `R5-RAV-M2` ①）：结构量与矩阵分量按 `Math.round(v*1e6)` 量化 ⇒ **低于 `1e-6` 的真实世界差异不可见**。实测（世界真变、判据绿）：`r2b`（`mesh.position.x += 4e-7`；`PROBE true_x=33.000000400000`）、`r2c`（`scale += 4e-7`）；**对照** `r2d`（`+= 2e-6`）**红** ⇒ 边界 ≈ `1e-6`。理由：量化是为消除浮点尾差噪声（否则基线假红）；亚微米级差异在本项目语义内不构成「不同几何」。
9. **渲染相关状态** `scene.fog` / `scene.background` / `renderer.sortObjects` / `mesh.frustumCulled`（R5-FIX / F1②）：不在闭式面内。实测（世界真变、判据绿）：`r2e`（`fog.far*=2` + 颜色）、`r2f`（`scene.background`）、`r2g`（`renderer.sortObjects`）、`r2h`（`mesh.frustumCulled`）。理由：闭式面按 §1.1 只枚举「几何 / 对象 / 相机」三结构面；渲染相关状态属**呈现层**，且两态**按设计**允许不同（背景 / 雾随读法变化是本项目语义）。
10. **相机自身 Object3D 层状态** `camera.layers.mask`（R5-FIX / F1③）：相机结构面枚举的是 `matrixWorld` / `projectionMatrix` / `zoom` / `view_offset` / `fov` / `near` / `far`，**不含**相机自身的 `layers` / `visible` / `renderOrder`。实测（世界真变、判据绿）：`r2n`（`camera.layers.mask = 2`）。理由：该字段决定「哪些对象被相机看到」，属**渲染可见性选择**；纳入需与第 9 条一并设计（属 M4 范围）。
11. **材质层** `roughness` / `metalness` / `map`（R5-FIX / F1④）：闭式面**不含**材质。实测（世界真变、判据绿）：`r2k`（`roughness=0.05` / `metalness=0.9` / `color`）。理由：与第 1 条同源 —— 光照与材质**按设计**两态必须不同；且第 1 条此前只写了「色相与明度」，故此处**显式补全**材质面。
12. **flag 本身 `matrixAutoUpdate`**（R5-FIX / F1⑤）：闭式面里进摘要的是**效果**（`matrixWorld` 16 分量），**不是**该 flag 的取值。实测：`r2l2`（关 `matrixAutoUpdate` 但 `matrix` 已同步 ⇒ 世界**未变** ⇒ 判据绿，**正确**）；其**效果面** `r2l` / `r2m`（关了自动更新后改 `matrix`）**红**。⇒ **就地限定 R5-B② 的措辞**：`matrixWorld` **覆盖 `matrixAutoUpdate` 的效果**（当 flag 改动使世界矩阵变化时），**不覆盖** flag 取值本身；**无条件**成立的是「根变换 / 父级 Group / `matrixAutoUpdate` 的效果」三者。
13. **判据取数点被钉常量 / 缓存 / 判据体自比**（R5-FIX / F1⑥，`R5-RAV-C1` 的 5 个形态）：**域外**（属**判据侧**改写，非场景侧注入）⇒ 判据**变绿**是**设计内的声明边界**，不是实现缺陷。architect 的裁定（**逐条**，见下）为 **MEDIUM（声明缺口）**，处置 = 写进本清单 + 登记 M4（**不开新一轮、不降级判据**）。

> **architect 裁定（`R5-RAV-C1`：MEDIUM（声明缺口），**不是** CRITICAL）—— 逐条理由**：
> 1. 该 5 个形态**全部**要求改写**判据自身的取数点**（`world.ts` 的 `structureReport()` / `cameraReport()` / 渲染入参记录）或**判据体**（`scene_assert.mjs` 的 `camUnderneath = camSurface`）—— 属**判据侧**改写；
> 2. PM 对 `R4-C1` / `R4-C2` / `R4-M1` 的 CRITICAL 口径针对的是**场景侧**注入（被审对象真的变了而判据说绿）；
> 3. **G9 已声明**：本判据是**一致性判据**，**不是**防篡改 / 完整性机制 ⇒ 判据侧改写**在声明域外**；
> 4. 判据自身源码（`world.ts` / `scene_assert.mjs`）**在冻结面内**（清单 150/150 OK）⇒ 判据侧改写由**清单**发现，不由判据发现；
> 5. Raven 的 **R1-对照** 实测：同族注入**不钉取数点**时**全红** ⇒ 判据在忠实实现上**不是恒真函数**；
> 6. Raven 自述「**未发现「实现忠实时仍可绕过」的新形态**」。
>
> **本判据是「一致性判据」，不是防篡改 / 完整性机制（G9 口径）**：它证明「同一几何 / 同一相机」在两态下按结构封闭地一致，**不**证明未被篡改、也**不**提供链外锚或完整性证明。
> **取数点被钉常量 / 缓存 / 自比 ⇒ 判据变绿**（实测 5 形态，见 `05_raven_risk_report.md` 的 M3-r5 段 `R5-RAV-C1`，第 **2965–2974** 行；读数 `/tmp/raven-r5/results.jsonl`）；**本判据不防护判据侧改写，判据侧改写由冻结清单发现**。
> ⇒ 因此：**不得**把 `scene_assert` 读作「实现未被篡改」的证据；该读法属过度声称（登记 M4）。

### R5-D 更正声明（§1.2 明令；指向被更正的原文）

- 被更正的原文（`06` 在本轮写集内；architect 显式授权**就地更正**）：
  1. **R4-B 逐 AC 重判**表（`AC-M3-8③` 行）原文为「**PASS（本轮才真正成立）**」⇒ 已改为「PASS（R4 面**覆盖**：装配变换进形状指纹 + mesh 层读回 + `mesh_scales`/`mesh_rotations`；R4 面**不覆盖**：相机投影面 / 几何拓扑面 / 世界根与父级变换 / `visible`/`layers`/`renderOrder`/第二相机 —— 逐条见 R5 段）」。
  2. **R4-H 与双门禁的对应**表（`R3-C1` 第二半行）原文为「（唯一失败点即该判据）」⇒ 已改为「（该 case 的**期望**失败点即该判据）」+ 就地列出 R4 面的不覆盖项。
- 更正理由：这两处是**绝对措辞**（隐含「已完整 / 唯一」），与 R4 面**实测的不覆盖项**矛盾（R4 面未闭合 `R4-C1` / `R4-C2` / `R4-M1`）⇒ 按「覆盖 X / 不覆盖 Y」逐条改写。
- 声明位置：**本段** + `SECTION A-R5`（编码前声明，`spikes/s12-session/m3-change-face.txt`）+ 重取登记（**R5-F**）。**`04` / `05` 的既有轮次内容未动**（逐字节未改）。
- **引文说明（防误读）**：`grep -n` 这两句在 `06` 里的命中**全部落在本段与 R5-A 的更正声明引文**内 —— 它们是「被更正对象的**原文引文**」，只用于**指认更正对象**，**不构成本段的主张**；`06` 的 **R4-A / R4-B 段内已无**这两句（更正生效）。
- **口径不一致的登记**（本轮未动，如实上报，不静默）：`06` 的 **R3 段**（`AC-M3-3` 行，第 437 行）仍含同类绝对措辞。§6 的授权**只覆盖 R4-A / R4-B**，且 R3 段属**既有轮次内容**（与 `04`/`05` 同口径 ⇒ 不动）⇒ **未更正**，登记为口径不一致，归属 **M4**（本轮不扩张写集、不自行取舍）。
- **口径不一致的登记（R5-FIX 补充，如实上报）**：`06` 的 **R4-B 逐 AC 重判**表（`AC-M3-8③` 行）仍含同类绝对措辞「**实现语义一字未改**」（与 R5-A 行被 Raven `L1` 点名的那处同源）。**R5-FIX 的写集只覆盖「R5 段内声明修正 + `R5-FIX` 小节」** ⇒ 该处位于 **R4 段**、**不在本轮写集内** ⇒ **未更正**，登记为口径不一致，归属 **M4**。（R5 段内**已无**该措辞：`grep -n "全部\*\*牙齿\|实现语义一字未改"` 在 R5 段 0 命中。）
### R5-E 负例矩阵（A–I）逐条读数

载体：**新增** `spikes/s13-render/negctl/f6_r5_structure_negctl.py`（复用 `negctl_lib`；**未改**任何既有驱动 / 既有 CASES；`NEGCTL_ROOT=/tmp/r5-artisan`，RED 相位 `/tmp/r5-artisan-red`）。RED 相位的「加宽前」整树副本 = **R5 编码开始前冻结**的 `02_source`（`/tmp/r5-pristine/02_source`，150 文件），保证「加宽前必须是绿（逃逸）」这一负例侧证据真实可复核。

**读法限定（R5-FIX / F2 + F6(c)，两条）**：

- **I 组（表内组名 `I 不得恒真 / 不得自命中`）的语义改述**：I 组的读数（**取数点被钉 ⇒ 负例变绿**）**只证明判据对取数点敏感**，**不构成**「非恒真 / 非自命中」的证据（「负例在世界真变时变绿」正是恒真 / 自命中的定义）；**「非恒真」由 A–G 组「世界真变 ⇒ 真红」承担**（本表 A–G 共 20 条真红 + Sentinel C 组 23 条注入 / 6 条泛化变体 + Raven R1-对照）。**本轮补两条 I 组原缺的形态**（Raven `r1c` / `r1d` 实测变绿）：`cameraReport()` 首调后缓存、渲染入参记录被伪造 —— 读数见 `/tmp/raven-r5/results.jsonl` 与 `05_raven_risk_report.md` 的 M3-r5 段第 **2976–2981** 行（`R5-RAV-M1`）。
- **措辞更正：「断言体零字面量」⇒「被比较的结构量零期望常量」**：三条 R5 判据的**被比较结构量**确实**无期望常量**（只做「两态读数互相比较」）；但断言体内**仍含**非期望常量 —— `scene_assert.mjs` 第 **289** 行的读法标签 `'surface'` / `'underneath'` 与 `two_reads_use_same_render_camera` 的**存活阈值** `renders >= 1` / `>= 2`（Sentinel `LOW-R5-2`、Raven `L3`）。
  **更正落点（如实登记，本轮写集外）**：该措辞的原文在 **`02_source/v0_skeleton/web/scripts/scene_assert.mjs` 第 277 行注释**与 **`03_artisan_self_test.log` 的 R5-7 第 2 条**（第 **3788** 行）—— 两者**本轮均冻结**（`02_source/**` 一字节不许改、`03` 禁改）⇒ 本段为**声明层更正**，两处原文的措辞更正**登记 M4**（不改代码、不改判据）。

**GREEN（R5 判据面）** — `f6-r5-negctl-summary.json`（source=`/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3/02_source`，neg_root=`/tmp/r5-artisan`，`all_ok=True`，`all_delivery_face_unchanged=True`，`turned_red=23`，`crashes=[]`）

| 组 | case | 注入 → 读数（exit / PASS / FAIL） | 期望 fail name | `delivery_face_unchanged`（逐 case 自算） | 判定 |
|---|---|---|---|---|---|
| 0 阳性对照 | `r5_pristine` | exit=0 PASS=31 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_scale` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_rotation` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_camera_position` | exit=1 PASS=30 FAIL=1（two_reads_share_camera） | `two_reads_share_camera` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_ctl_position_shift` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_scale_tiny` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_quaternion` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_single_box` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_scale_nonuniform` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| B R4 **未抓** 3 类（必须真红） | `r5_b_camera_zoom` | exit=1 PASS=30 FAIL=1（two_reads_share_camera） | `two_reads_share_camera` | `True` | OK |
| B R4 **未抓** 3 类（必须真红） | `r5_b_camera_zoom_bare` | exit=1 PASS=30 FAIL=1（two_reads_share_camera） | `two_reads_share_camera` | `True` | OK |
| B R4 **未抓** 3 类（必须真红） | `r5_b_projection_matrix` | exit=1 PASS=30 FAIL=1（two_reads_share_camera） | `two_reads_share_camera` | `True` | OK |
| B R4 **未抓** 3 类（必须真红） | `r5_b_view_offset` | exit=1 PASS=30 FAIL=1（two_reads_share_camera） | `two_reads_share_camera` | `True` | OK |
| C 几何拓扑面 | `r5_c_geometry_index` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| D 世界根 / 父级变换 / matrixAutoUpdate | `r5_d_root_offset` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| D 世界根 / 父级变换 / matrixAutoUpdate | `r5_d_parent_group_offset` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| D 世界根 / 父级变换 / matrixAutoUpdate | `r5_d_matrix_auto_update` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| E 对象面 | `r5_e_visible` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| E 对象面 | `r5_e_layers_mask` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| E 对象面 | `r5_e_render_order` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| F 渲染相机身份 | `r5_f_second_render_camera` | exit=1 PASS=30 FAIL=1（two_reads_use_same_render_camera） | `two_reads_use_same_render_camera` | `True` | OK |
| G 泛化（不同数值变体） | `r5_g_scale_other_values` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| G 泛化（不同数值变体） | `r5_g_root_offset_other_value` | exit=1 PASS=30 FAIL=1（two_reads_share_scene_structure） | `two_reads_share_scene_structure` | `True` | OK |
| G 泛化（不同数值变体） | `r5_g_camera_zoom_other_value` | exit=1 PASS=30 FAIL=1（two_reads_share_camera） | `two_reads_share_camera` | `True` | OK |
| H **不得假红** | `r5_h_legal_resize_idempotent` | exit=0 PASS=31 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| H **不得假红** | `r5_h_legal_resize_outside_window` | exit=0 PASS=31 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| H **不得假红** | `r5_h_legal_delta` | exit=0 PASS=31 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| I **不得恒真 / 不得自命中** | `r5_i_pinned_geometry_digest` | exit=0 PASS=31 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| I **不得恒真 / 不得自命中** | `r5_i_pinned_objects_digest` | exit=0 PASS=31 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| I **不得恒真 / 不得自命中** | `r5_i_camera_same_read_twice` | exit=0 PASS=31 FAIL=0（—） | `—（期望绿）` | `True` | OK |

**RED（加宽前整树副本）** — `f6-r5-negctl-red-summary.json`（source=`/tmp/r5-pristine/02_source`，neg_root=`/tmp/r5-artisan-red`，`all_ok=True`，`all_delivery_face_unchanged=True`，`turned_red=9`，`crashes=[]`）

| 组 | case | 注入 → 读数（exit / PASS / FAIL） | 期望 fail name | `delivery_face_unchanged`（逐 case 自算） | 判定 |
|---|---|---|---|---|---|
| 0 阳性对照 | `r5_pristine` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_scale` | exit=1 PASS=28 FAIL=1（two_reads_share_rendered_geometry） | `two_reads_share_rendered_geometry` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_rotation` | exit=1 PASS=28 FAIL=1（two_reads_share_rendered_geometry） | `two_reads_share_rendered_geometry` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_camera_position` | exit=1 PASS=28 FAIL=1（two_reads_share_camera） | `two_reads_share_camera` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_ctl_position_shift` | exit=1 PASS=28 FAIL=1（two_reads_share_rendered_geometry） | `two_reads_share_rendered_geometry` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_scale_tiny` | exit=1 PASS=28 FAIL=1（two_reads_share_rendered_geometry） | `two_reads_share_rendered_geometry` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_quaternion` | exit=1 PASS=28 FAIL=1（two_reads_share_rendered_geometry） | `two_reads_share_rendered_geometry` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_single_box` | exit=1 PASS=28 FAIL=1（two_reads_share_rendered_geometry） | `two_reads_share_rendered_geometry` | `True` | OK |
| A R4 已抓 8 类（必须仍红） | `r5_a_mesh_scale_nonuniform` | exit=1 PASS=28 FAIL=1（two_reads_share_rendered_geometry） | `two_reads_share_rendered_geometry` | `True` | OK |
| B R4 **未抓** 3 类（必须真红） | `r5_b_camera_zoom` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| B R4 **未抓** 3 类（必须真红） | `r5_b_camera_zoom_bare` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| B R4 **未抓** 3 类（必须真红） | `r5_b_projection_matrix` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| B R4 **未抓** 3 类（必须真红） | `r5_b_view_offset` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| C 几何拓扑面 | `r5_c_geometry_index` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| D 世界根 / 父级变换 / matrixAutoUpdate | `r5_d_root_offset` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| D 世界根 / 父级变换 / matrixAutoUpdate | `r5_d_parent_group_offset` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| D 世界根 / 父级变换 / matrixAutoUpdate | `r5_d_matrix_auto_update` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| E 对象面 | `r5_e_visible` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| E 对象面 | `r5_e_layers_mask` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| E 对象面 | `r5_e_render_order` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| G 泛化（不同数值变体） | `r5_g_scale_other_values` | exit=1 PASS=28 FAIL=1（two_reads_share_rendered_geometry） | `two_reads_share_rendered_geometry` | `True` | OK |
| G 泛化（不同数值变体） | `r5_g_root_offset_other_value` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |
| G 泛化（不同数值变体） | `r5_g_camera_zoom_other_value` | exit=0 PASS=29 FAIL=0（—） | `—（期望绿）` | `True` | OK |

- **RED 相位「加宽前」实测逃逸：13 条真逃逸 + 1 条阳性对照**（`pre_widening_escapes` 字段**含对照**；GREEN 相位该字段为 `[]` —— 同名字段在两份 JSON 里语义不同，**如实登记**）：真逃逸 13 条 = `r5_b_camera_zoom`, `r5_b_camera_zoom_bare`, `r5_b_projection_matrix`, `r5_b_view_offset`, `r5_c_geometry_index`, `r5_d_matrix_auto_update`, `r5_d_parent_group_offset`, `r5_d_root_offset`, `r5_e_layers_mask`, `r5_e_render_order`, `r5_e_visible`, `r5_g_camera_zoom_other_value`, `r5_g_root_offset_other_value`；**第 14 条 `r5_pristine` 是阳性对照**（无注入、按构造必绿），**不计入逃逸**。
  - **口径更正来源（如实登记）**：architect 任务书原写「RED 汇总该字段为 `[]`」——**该前提有误**（`[]` 出现在 **GREEN** 汇总；两份文件被搞混），**Sentinel 已证伪**（`04_sentinel_test_report.md` 的 M3-r5 段 `LOW-R5-1`，第 **2610 / 2596–2600** 行：RED 汇总该字段**非空**且恰为这 14 条）。**以 Sentinel 的读数为准**，本行按其口径改写。
  - 旁证（**独立**复现）：`04` 的 M3-r5 段 B 组（第 **2405–2429** 行）用**自建** R4 形态参照树逐条复现 **13 条真逃逸**（B×4 / C×1 / D×3 / E×3 / G×2），与本节口径一致。
- 相位证据（副本内判据在场情况）：`judgement_present_in_copy` ⇒ 加宽前 `old_rendered=True, structure=False, render_camera=False`；加宽后 `structure=True, render_camera=True`（逐 case 记录在 `negctl-r5_*.log`）

### R5-F 冻结面口径 / 重取登记（`R4-M4`）

**排除项变更（逐条；`spikes/s12-session/logs/**` 与 `spikes/s13-render/logs/**` 下）**：`*.png` / `browser-accept-*.json` / `console-*.jsonl` / `negctl-*.log` / `*-summary.json` / `serve-summary-*.json`（**R5-POST 定向补齐**，理由见 R5-G①）/ `emitted-messages.jsonl`。

**过宽控制（必须给读数）**：

- `--dry-run` 读数：`entries=202 previous_entries=311`，`added=['spikes/s13-render/negctl/f6_r5_structure_negctl.py']`，`removed=` **110** 条（逐条列出，见 `03` 的 R5 段）。
- 逐条核对：**110/110 全部命中声明模式**（`removed_not_matching_declared_patterns=[]`）、**110/110 全部落在两个 logs 子树内**（`removed_outside_the_two_log_dirs=[]`）、**110/110 全部是可重生成的运行产物**（归类：`*.png` 24 / `browser-accept-*.json` 4 / `console-*.jsonl` 4 / `*-summary.json` 14 / `negctl-*.log` 59 / `serve-summary-*.json` 4 / `emitted-messages.jsonl` 1；`UNCLASSIFIED=[]`）。
- `added` 唯一一条 = **R5 新增的负例载体本体**（源码，非运行产物；已在 `SECTION A-R5` 声明），不是被排除项带进来的。
- **定向保留**：`must_stay_missing_from_collection_face=[]` ⇒ 15 条「必须仍在哈希面内」的条目**全部仍在**（`f4_browser_negctl.py` / `browser-accept.mjs` / `r4-diff-review.log` / `r4-f4-run.log` / `r4-green-after-widening.log` / `r4-red-before-widening.log` / `f5-r4-negctl-summary-red.json` / `m3-kernel-pytest.txt` / `m3-source-manifest-{before,after}.txt` / `p8-freeze-recheck.json` / `p8-zero-residue.json` / `emitted-messages-session-tests.jsonl` / `session-record-sess_*.jsonl` / `m3-change-face.txt`）。

**过窄控制（硬）**：

- **复跑前/后整面指纹**：对**仍在采集面内**的全部 **202** 条逐文件取 sha256 ⇒ 跑一次 f4 真浏览器复跑后**差异为空**（`FINGERPRINT_UNCHANGED=YES`）⇒ 排除集合对「f4 复跑」是**完备**的（无「被复跑改写却仍在面内」的文件）。
- **重取后复跑再校验**：重取 `V0_M3.sha256` 之后**再跑一次** f4，随后 `shasum -a 256 -c V0_M3.sha256` ⇒ **全 OK**（读数：`OK=202 / FAILED=0`，exit 0）。**交付面与证据面分开报**：`02_source` OK 条数 = **150**（`grep -c '^02_source.*: OK$'`）。

**重取登记（理由 + 变更清单 + 前后哈希 + 条目数）**：

- 理由：`R4-M4`（清单把**可重生成的运行产物**钉进哈希面 ⇒ 出口前任何一次真浏览器复跑都会让 `shasum -c` 变红，被误读成「交付面被改」）+ 本轮交付面/证据面写入。
- 前：`V0_M3.sha256` 文件 sha256 = `83961466e9e5a0dac644824a6c1afe592665bc4e3d89ab8b2ebd8db32c70be60`（R4 收尾态，**311** 条目，325 行）。
- 后：**202** 条目（含 **23 行**头注 ⇒ **225 行**）；重取后的清单自身 sha256 与 `retake_chain_r5` 一并落在 `V0_M3.sha256.retake.json`（该文件在采集面**之外**，可稳定登记终值，不自我作废）。
- 变更清单：**+1**（`spikes/s13-render/negctl/f6_r5_structure_negctl.py`）；**−110**（运行产物，逐条见上）；另有若干**内容变更**（`world.ts` / `scene_assert.mjs` / `m3-change-face.txt` / `03` / `06` / `retake-v0-m3.py`）。
- **`V0_M3.sha256` 只在最后一步重取**（重取前已确认无其它写入者：reviewer 未在跑）。

### R5-G 冲突与缺口登记（**如实上报，不自行取舍**）

1. **约束 §1.3 的枚举有一处缺口（已按意图补齐并声明）**：字面模式 `*-summary.json` **不覆盖** f4 每个 case 的 `serve-summary-<tag>.json`（其结尾是 `-summary-<tag>.json`），而该文件**确被 f4 每次复跑重写**——实测：R4 清单在一次 f4 复跑后 **29 条 FAILED** 里就有 **4 条**是 `serve-summary-*.json`。⇒ 若不排除，§1.3 的**硬验收**（任意次数复跑后 `shasum -c` 全 OK）**必然不成立**。处置：按 §1.3 的**意图**（可重生成的 f4 运行产物移出哈希面）补一条**定向**模式 `spikes/s13-render/logs/serve-summary-*.json`，并在 `SECTION A-R5-POST`（**明确标注 post-hoc**）+ 本段 + 最终汇总登记。**未放宽任何判据**。
2. **任务书 §7.2 点名的文件不存在**：「AC-M3-8③⑤ 双读证据 `worldview-two-reads.*`」在全树 `rglob('*worldview-two-reads*')` **0 命中**。实际的双读证据分两类：① **稳定**类（`f4_browser_negctl.py` 驱动本体、`r4-*.log`、`f5-r4-negctl-summary-red.json`、`06` 登记）**仍在**哈希面内；② **运行产物**类（`browser-accept-*.json` 的两态读数 + 截图）按 §1.3 移出哈希面，其**判据结论**由门禁退出码 + `06` 登记承担。该文件名属**任务书笔误**，已如实上报（未按不存在的前提做「定向保留」）。
3. **写集扩展**（architect 授权，设计 §5）：`spikes/s12-session/scripts/retake-v0-m3.py` 实际改动为 `EXCLUDE_SUBPATHS`（前缀 → 整路径 glob）+ 其**唯一消费行**（`rel.startswith(prefix)` → `fnmatch.fnmatch(rel, pattern)`）+ `HEADER`；消费行变更在 `SECTION A-R5-POST` 标注 **post-hoc**（编码前声明只写了「两处」）。理由：§1.3 强制要求排除项变更，而清单**只能**由该工具生成 ⇒ 无替代路径。**非阻断**。

### R5-H 已知风险 / 未覆盖项（如实登记）

1. **稳定身份口径**：结构摘要的对象身份用 `name`（无名字时 `类型#序号`）—— 不用 `id`/`uuid`（每次 `rebuild()` 都会变，会把「同一结构」误判成不同）。若未来实现给 mesh 改名或插入无名对象，结构摘要会变 ⇒ 属**有意**口径，不是假红。
2. **相机面含 `projectionMatrix`** ⇒ 两读**窗口内**的合法视口变化会红（口径边界，见 R5-C⑥；H 组已给两种合法 resize 形态读数）。
3. **本判据不是防篡改**（见 R5-C 末的 G9 声明）：它证明一致性，不证明完整性。
4. **未覆盖「摘要取完之后」的时序篡改与 GPU / 光栅层**（R5-C③②）；**未覆盖 DOM/HUD 层**（R5-C④）。
5. **R4 登记的非阻断项**（Raven `R4-M2`/`R4-M3`、Sentinel `MEDIUM-R4-1` 等）本轮**只接续登记**，处置**归属 M4**（本轮为一轮为限，不再自开新一轮）。

### R5-I 交付面卫生

- `02_source` 文件数 **150**（**零新增 / 零删除**；`manifest.txt` 未改）；生成残渣（`node_modules` / `dist` / `.build` / `__pycache__` / `*.pyc` / `.pytest_cache`）在 `02_source` 内 = **0**；全程 `PYTHONDONTWRITEBYTECODE=1` + `python3 -B`。
- 真实仓库 `/Users/wooyinq/personal/deep-healing`：`develop` @ `98c781f`，`porcelain` = **0**（未 add/commit/push/checkout/branch；未改仓库任一字节）。

### R5-J 与双门禁的对应（供 Sentinel / Raven 复验）

| 门禁条目 | 处置 |
|---|---|
| PM 裁决 `R4-C1`（相机投影面逃逸：`zoom` / 手改 `projectionMatrix` / `setViewOffset`） | **R5-A** ⇒ 相机结构面（`matrixWorld`/`projectionMatrix`/`zoom`/`view_offset`/`fov`/`near`/`far`）；RED 相位 4 条**真逃逸**，GREEN 相位 4 条真红（`two_reads_share_camera`） |
| PM 裁决 `R4-C2`（几何拓扑面逃逸：`setIndex`） | **R5-A** ⇒ 几何结构面 `index`/`groups`/`attributes`；RED 1 条逃逸 ⇒ GREEN 真红（`two_reads_share_scene_structure`） |
| PM 裁决 `R4-M1`（世界根 / 父级变换逃逸） | **R5-A** ⇒ 每对象 `matrixWorld` 16 分量逐项 + 根子树父子关系；RED 3 条逃逸 ⇒ GREEN 真红 |
| PM 裁决 `R4-M4`（冻结面口径缺陷） | **R5-C/R5-F** ⇒ 运行产物出哈希面 + 头部声明 + 最后一步重取 + 复跑后 `shasum -c` 全 OK + 交付面/证据面分开报 |
| 过度声称（§1.2） | **R5-B/R5-D** ⇒ 断言改名 + `06` R4-A/R4-B 就地更正（含更正声明）+ G9 口径就地写明 |
| 「判据不得恒真 / 不得自命中」 | **R5-E 的 I 组**（**R5-FIX / F2 改述**）：**取数点被钉 ⇒ 负例变绿** —— 这只证明**判据对取数点敏感**，**不构成**「非恒真」证据；**「非恒真」由 A–G 组「世界真变 ⇒ 真红」承担**（Sentinel C 组 23 条注入 + 6 条泛化变体全部精确真红；Raven R1-对照「不钉取数点 ⇒ 全红」）。**I 组本轮补两条**（原缺）：`cameraReport()` 首调后缓存 + 渲染入参记录被伪造（Raven `r1c` / `r1d` 实测变绿，`/tmp/raven-r5/results.jsonl`） |
| 「取数点被钉常量 / 缓存 / 自比」 | **R5-C 第 13 条**（域外，architect 裁定 MEDIUM）：写进「不覆盖」+ 登记 M4；**不**改判据、**不**开新一轮 |
| 「判据不得假红」 | **R5-E 的 H 组**：合法幂等 `resize()` / 窗口外改视口 + 合法 delta ⇒ **仍绿** |
| 回归不得退化 | **R5-E** ⇒ f4 `all_ok=True`；`verify_specs` 130 / 0 skipped；session 16/16；web 4/4；`scene_assert PASS=31 FAIL=0`；300 tick 三条读数逐位不变；仓库 porcelain 0 |
| **本轮为终局有界轮（`--max-iteration 1`）** | 未再自开新一轮、未自行降级、未把判据调回放行；新的绕过类一律写进 R5-C「不覆盖」+ 登记 M4 |

### R5-FIX 声明修正轮（**非新一轮** · 只改**声明与登记** · 不改代码 / 判据 / 负例 / 实现语义）

- 定位：**续作 R5**（`--max-iteration 1` 不变）。**不是**新一轮迭代，**不是**判据 / 实现修复。
- 触发（两名门禁的**声明层**缺口）：Sentinel = **0 CRITICAL / 0 MEDIUM / 4 LOW / 1 GAP**（`R4-C1`/`R4-C2`/`R4-M1` 判据层关闭成立、`R4-M4` 冻结面修正生效，**不阻断**；`04` 的 M3-r5 段）；Raven = 未发现「实现忠实时仍可绕过」的新形态，但指出 `06` 声明层 **4 MEDIUM + 3 LOW** 未闭合（`05` 的 M3-r5 段）。PM 约束 §1.1（明确仍不覆盖，逐条给理由）+ §1.2（R5 段不得出现绝对措辞）⇒ **把缺口如实写进声明**即完成本轮要求。
- **编码前 epoch 锚：1790108410**（2026-09-23 04:20:10 CST）—— 该值**早于**本小节的落盘；本轮的改动面在 `spikes/s12-session/m3-change-face.txt` 的 `SECTION A-R5-FIX`（**明确标注 post-hoc**）逐条声明。

**F1 — `06` R5-C「不覆盖」由 7 条补到 13 条（逐条给理由与实测证据）** ⇒ 见上方 **R5-C 第 1–13 条**（新增 6 条 = ⑧量化边界 `1e-6` / ⑨渲染相关状态 / ⑩相机自身 Object3D 层状态 / ⑪材质层 / ⑫flag 本身 `matrixAutoUpdate` / ⑬判据取数点被钉常量·缓存·自比）。**证据（绝对路径）**：`/tmp/raven-r5/results.jsonl`（`r2b`/`r2c`/`r2d`/`r2e`/`r2f`/`r2g`/`r2h`/`r2k`/`r2l`/`r2l2`/`r2m`/`r2n`）+ `05_raven_risk_report.md` 的 M3-r5 段第 **2983–2988** 行（`R5-RAV-M2`）。**architect 裁定（`R5-RAV-C1` = MEDIUM 声明缺口，非 CRITICAL）的 6 条理由**已逐条写进 R5-C 末的引注块（依据 `.task-artisan-r5fix.md` §2，未自行取舍）。

**F2 — R5-J「判据不得恒真 / 不得自命中」改述 + 补 2 形态** ⇒ 见上方 **R5-J 表**（改述为「取数点被钉 ⇒ 负例变绿 = 判据**对取数点敏感**，**不构成**『非恒真』证据；『非恒真』由 **A–G 组『世界真变 ⇒ 真红』**承担」）+ **R5-E 的读法限定**（补 `cameraReport()` 首调后缓存、渲染入参记录被伪造两条形态；Raven `r1c`/`r1d` 实测变绿）。

**F3 — 第 792 行计数 / 口径** ⇒ 见上方 **R5-E 的 RED 段**（改为「**13 条真逃逸 + 1 条阳性对照**」+ 登记「GREEN 相位该字段为 `[]`」）。
- **前提更正（如实登记）**：任务书原写「RED 汇总该字段为 `[]`」—— **该前提有误**（`[]` 在 **GREEN** 汇总），**Sentinel 已证伪**（`04` 的 M3-r5 段 `LOW-R5-1` 第 **2610** 行、事实表第 **2596–2600** 行）⇒ **以 Sentinel 读数为准**。

**F4 — 去绝对措辞** ⇒ ① R5-B 标题由「这就是本判据的**全部**牙齿」改为「覆盖清单 = 本判据比较面的**全部条目**；其**不覆盖项**见 R5-C 的 **13 条**」；② R5-A 行「**实现语义一字未改**」改为「**渲染与装配语义**未变（R5 只**增读数与包装**：`structureReport()` / `renderOnce()` / `renderCameraReport()` / 渲染包装器 / `cameraReport()` 扩面 —— 逐条列出；`scale`/`quaternion` 仍默认单位变换）」。

**F5 — G9 声明旁补一句** ⇒ 见 R5-C 末（「**取数点被钉常量 / 缓存 / 自比 ⇒ 判据变绿**（实测 5 形态，见 `05` M3-r5 段 `R5-RAV-C1` 第 **2965–2974** 行）；**本判据不防护判据侧改写，判据侧改写由冻结清单发现**」+ 「不得把 `scene_assert` 读作『实现未被篡改』的证据」）。

**F6 — 措辞加限定** ⇒ ① R5-C 第 5 条（`aspect`）：补「字段级不参与相等断言；但 `projectionMatrix`（`aspect` 派生）**在面内** ⇒ 对**窗口内**视口变化**间接敏感**」（实测：`/tmp/sentinel-r5/cases/green/h_x_resize_inside_window`、Raven `r3b` ⇒ 红）；② 「实际用于渲染的相机身份」⇒ 限定为「**渲染入参身份**」（R5-A / R5-B 第 5 条 / R5-C 第 7 条；反证 Raven `r2a`）；③ 「断言体零字面量」⇒「**被比较的结构量**零期望常量」（见 R5-E 的读法限定；原文两处在 `02_source/.../scene_assert.mjs` 第 **277** 行注释与 `03` 的 R5-7 第 2 条（第 **3788** 行），**两者本轮冻结** ⇒ 声明层更正 + **登记 M4**）。

**F7 — 重取工具的「声明 ↔ 实现」一致性**（`spikes/s12-session/scripts/retake-v0-m3.py`；**采集面语义未变**）：
- (a) **`runtime*` 收紧到与声明一致**：原实现「任意位置的 `runtime*` 分量」会静默排除 `02_source/**`（Raven 实测 `02_source/runtime-notes.md` / `02_source/v0_skeleton/web/runtime-snapshot.json` 被排除）⇒ 改为**仅 `spikes/<dir>/runtime*/**`**。**硬要求读数**：`python3 -B spikes/s12-session/scripts/retake-v0-m3.py . --dry-run` ⇒ `entries=202 previous_entries=202`、**`added=[]`**、`removed=[]`（exit 0；证据 `/tmp/r5fix-dryrun.txt`）⇒ **交付面无条目被静默隐藏**。正反两侧另用**最小假 ws**核验（`python3 -B /tmp/r5fix-f7a.py` ⇒ `mismatches=[]`，exit 0）：`02_source/runtime-notes.md` 与 `02_source/v0_skeleton/web/runtime-snapshot.json` **现在被采集**；`spikes/s13-render/runtime-x/**` 与 `spikes/s12-session/runtime/**` **仍被排除**。
- (b) **s12 侧补齐 `serve-summary-*.json`**：头部声明两个 logs 子树都排除，R5 实现只有 s13 侧 ⇒ 补 s12 侧**同模式**（两目录对称）。读数：s12 侧当前该模式 **0 命中** ⇒ `--dry-run` 的 `removed` **不变**、`added=[]`（同上证据）。
- (c) **三方对齐（头部 / docstring / 实现）**：头部去掉「`V0_M3.sha256`（自身）」⇒ 改为「**自身不入清单** —— 不可自哈希；`V0_M3.sha256.retake.json` 亦不在面内」，docstring 同口径（`ROOT_FILES` 仅 03/06，**未**把清单纳入自身）。
- (d) **新增两条头部声明句**：① **验收口径 = f4 真浏览器复跑**；**非 f4 驱动**（f5/f6/f1…）复跑会重写**它们自己的**产物、其中部分**仍在**面内（`f5-r4-negctl-summary-red.json` / `r4-*-widening.log`）⇒ 按「重取登记」规则处理，**登记 M4**；② 排除**仅按名字模式**（`fnmatch`，`*` 可跨 `/`）⇒ **被排除路径不得承载判据性结论**；判据结论落在**门禁退出码**与 `06`/`03` 登记（含「AC-M3-8③⑤ 原始双读运行读数外置」的残余，登记 M4）。

**F9 — 收尾复验（真实命令 + workdir + exit + 读数）**：

| # | 命令（workdir） | exit | 读数 | 判定 |
|---|---|---|---|---|
| 9.1 | `node scripts/scene_assert.mjs`（`<ws>/02_source/v0_skeleton/web`） | **0** | `scene_assert: PASS=31 FAIL=0` / `OK` | **PASS**（与 FIX **前**逐字一致 ⇒ 判据未动） |
| 9.2 | `bash verify_specs.sh --quiet`（`<ws>/02_source`） | **0** | `verify_specs: OK (130 checks passed, 0 skipped)` | **PASS** |
| 9.3 | `PYTHONDONTWRITEBYTECODE=1 python3 -B spikes/s13-render/negctl/f4_browser_negctl.py`（`<ws>`） | **0** | `delivery_face_unchanged=True`、`all_ok=True` | **PASS** |
| 9.4 | `shasum -a 256 -c V0_M3.sha256`（`<ws>`，**F8 重取之后**） | **0** | **202 OK / 0 FAILED**；`02_source` OK = **150** | **PASS**（读数见 `V0_M3.sha256.retake.json` 的 `post_retake_verification` 与本轮汇总） |
| 9.5 | `find 02_source -type f \| wc -l` / 残渣扫描 / 仓库快照（`<ws>`） | 0 | **150** / 残渣 **0** / `develop` @ `98c781f`、porcelain **0** | **PASS** |
| 9.6 | `shasum -a 256 02_source/v0_skeleton/web/src/scene/world.ts 02_source/v0_skeleton/web/scripts/scene_assert.mjs`（`<ws>`） | 0 | `world.ts` = `07c42b82cdea8dab2f4552cf520440264450e12b4f01920fc9b3342feb464347`；`scene_assert.mjs` = `faec656cee9feb918a6ff266eb3cb55a80cd70c7fee78fb2d65eb50cf88ebb0a` —— 与 FIX **前**（`/tmp/r5fix-pre-sha-live.txt`）**逐位相同** | **PASS** |

**F10 — 明确没改什么（硬边界自证）**：
- **`02_source/**` 一字节未改**：`world.ts` / `scene_assert.mjs` 的 sha256 与 FIX 前**逐位相同**（F9.6）；交付面**全树指纹** `find 02_source -type f -exec shasum -a 256 {} \; | sort | shasum -a 256` ⇒ `43120274228b27d980febab0b9066af9ed8968a4fafd71fa945b6a92ccb83f47`，与 FIX 前**逐位相同**（也与 Sentinel 独立自算的开工/收尾指纹一致）。**无代码 / 无判据 / 无负例 / 无实现语义改动**。
- 未改 `04` / `05`（含其 M3-r5 段）、未改 `03`、未改 `V0_M1.sha256` / `V0_M2.sha256` / `SEED.sha256` / `06_v0_m1_*` / `06_v0_m2_*` / `REQ-*` / `pm_business/**`；未做 `git` 写操作；未放宽判据 / 未删负例 / 未新增 AC 或依赖；未在交付面注入负例。
- 本轮**只**写了：`06`（本 R5 段的声明修正 + 本小节）、`spikes/s12-session/scripts/retake-v0-m3.py`（仅 F7 的声明↔实现一致性）、`V0_M3.sha256`（**F8 最后一步重取**）、`V0_M3.sha256.retake.json`、`spikes/s12-session/m3-change-face.txt`（`SECTION A-R5-FIX`）、`.artisan.progress.json` + 账本（progress）。
- **未自开新一轮、未自行降级、未把判据调回放行**；`R5-RAV-C1` 按 architect 裁定 = **MEDIUM（声明缺口）**，处置 = 写进 R5-C 第 13 条 + 登记 **M4**。
- 全程 `PYTHONDONTWRITEBYTECODE=1` / `python3 -B`；`02_source` 生成残渣 **0**。
