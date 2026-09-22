# 06 · V0-M1 逐 AC 证据表（Artisan 自测）

- 任务：`REQ-20260921-003-deephealing-v0-m1`（V0 里程碑 M1：确定性内核可跑可重放）
- 角色：artisan（唯一产品 writer）　日期：2026-09-22
- `{ws}` = `/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-003-deephealing-v0-m1`
- 原始命令日志：`{ws}/03_artisan_self_test.log`（由 `spikes/run_ac_evidence.sh` 生成，含命令 + workdir + exit + 关键输出）
- RED 证据：`{ws}/spikes/red/RED.log`（同一套用例跑在**实现前**的接口桩上）
- 复跑纪律：pytest 一律 `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest … -p no:cacheprovider`；
  冻结命令字面写**裸 `pytest`** 的两条（AC-M1-4/AC-M1-5）按原样跑，其字节码残渣在收尾统一清理（§9）。

> **本轮为修复轮 2（iteration 3，最终有界轮）**：§0~§9 是修复轮 1 之后的实测值，
> **§10 = 修复轮 1（iteration 2）**，**§11 = 修复轮 2（iteration 3）**（本轮逐条闭环 F1~F7 / G1~G8）。
> 修复轮 2 写集 = `02_source/v0_skeleton/kernel/**` + `06_v0_m1_self_test.md` + `spikes/**` + `out/**` + `V0_M1.sha256`；
> 真实仓库 `/Users/wooyinq/personal/deep-healing` **零改动**（§11.3 复检）。
> 明确**不做**：不重采样、不调参、不碰任何冻结文件（含 `pack_sign.py` / `verify_pack.py`）、
> 不实现 W3/W7、不改 `01`/`04`/`05`、不做 M2 面（R18/R13/R14/Bug#11/#13/#14）。
> 交付清单口径在本轮有**一处调整**（不再登记易失的 `out/**`），理由见 §11.4。

---

## 0. 快照、写集与交付面

| 项 | 值 | 证据 |
|---|---|---|
| 真实仓库 HEAD | `b421cb01df4bf864b9a3fa48dbf6221c3989dc02` | `03_artisan_self_test.log` §0 / §8 |
| 真实仓库 porcelain | **空**（零改动；不 commit / push / PR / 部署） | 同上 |
| `SEED.sha256` 聚合 | `34fa7f6d252bc4bf966c8dbc4d639a1f08788ed71b9cfa04a0896ca7ba8f7676`（未改写） | 同上 |
| 第二 writer | **无**（`ps` 中本工作区只有 artisan 一个任务进程；`.task-artisan.pid` = 本进程） | 开工核对，见 `03` §0 |
| 冻结文件未改 | 9 份 `*.schema.json` + `verify_specs.sh` + `verify_pack.py` 的 sha256 见 `03` §9（本轮未改任何一个） | `03` §9 |
| `districts/**` | **未改**（`verify_pack.py` 13 files OK；`pack.sig` 未重签） | `03` §1 |
| `{session,web}/**` | 未动 | 写集边界，未产生 mtime 变化 |
| 交付树残渣 | **收尾清理后为 0**（`find` 空输出）；**可持续口径（修复轮 D1，计数在修复轮 2 / G6 改为实测）**：按 REQ §4 字面复跑（**裸 `pytest`**，无 `-p`/无环境变量）会**重新**产生字节码/缓存，**实测计数**（`spikes/measure_literal_residue.py`，在 `/tmp` 完整工作区副本里跑、不动交付树）：AC-M1-4 单步 ⇒ **6 目录 + 7 `.pyc` = 13 条路径**；叠 AC-M1-5 裸 pytest ⇒ **14**；再叠字面 `run` ⇒ **22**。它们被 `GENERATED_PATTERNS` 排除、**不影响 AC-M1-1**（三步 exit 均为 0）；收尾再清一次后仍为空 | `03` §10 / §12 / §3n |

### 0.1 02_source 改动文件清单（**代码/契约**交付面）

> **交付面口径（修复轮 2 / G5 / Sentinel Bug#12）**：`02_source` 是**代码/契约**交付面；
> **AC-M1-5 / AC-M1-6 / AC-M1-7 的判据还依赖「工作区级」产物** —— `spikes/kernel-baseline/**`（基线锚点）、
> `spikes/s5-latency-calibration/**`（标定产物与三份冻结物）、`06_v0_m1_self_test.md`（其中被断言的字符串）。
> Sentinel 独立实测：把 `02_source` **单独**复制走（不带 `spikes/**` 与 `06_*.md`）跑全量 ⇒
> **12 failed / 50 passed / 10 skipped**，失败**全部**归因于这些产物缺失（**不是**代码回归）。
> ⇒ 随交付包一并移交 `spikes/**` 与 `06_*.md`；只取 `02_source` 会看到 12 条红。

**修改（8 个模块去桩 + 2 个测试文件实现 + manifest）**

| 文件 | 动作 |
|---|---|
| `v0_skeleton/kernel/deephealing_kernel/tick.py` | 去桩：`WorldKernel.step/run/snapshot/state_hash` + 确定性桩决策系统 |
| `v0_skeleton/kernel/deephealing_kernel/ecs.py` | 去桩：`World.spawn/despawn/get/query/set_component/to_state/apply_delta/systems` |
| `v0_skeleton/kernel/deephealing_kernel/rng.py` | 去桩：`StreamRng.next_u64/uniform/choice`、`WorldRng.stream/state_digest` |
| `v0_skeleton/kernel/deephealing_kernel/bus.py` | 去桩：订阅/投递 + 订阅者异常隔离 + metrics |
| `v0_skeleton/kernel/deephealing_kernel/events.py` | 去桩：哈希链 append/read_all + `redact()`（点分路径 + glob 主判据）+ ECH 不变量校验 |
| `v0_skeleton/kernel/deephealing_kernel/snapshot.py` | 去桩：canonical 单一来源加载器 + 三哈希 + 检查点读写 + `compare_checkpoints` 字符串协议 + M3 独立完整性断言 |
| `v0_skeleton/kernel/deephealing_kernel/pack.py` | 去桩：7 步校验链 + 强口径 seed 投影 + portal 边 |
| `v0_skeleton/kernel/deephealing_kernel/cli.py` | 去桩：`run/replay/verify/validate/pack sign` + `--ticks` + `--expected-hash` 链外锚点 |
| `v0_skeleton/kernel/tests/test_determinism_replay.py` | 由 `pytest.skip` 改为真用例（R1~R4 + 边界） |
| `v0_skeleton/kernel/tests/test_pack_validate.py` | 由 `pytest.skip` 改为真用例（R8~R11 + R23 + 路径安全 + 判据漂移守卫） |
| `manifest.txt` | 追加 9 行（3 字段格式），覆盖全部新增文件 |

**新增（9 个文件，全部已登记 `manifest.txt`）**

`v0_skeleton/kernel/conftest.py`、`v0_skeleton/kernel/deephealing_kernel/__main__.py`、
`v0_skeleton/kernel/tools/kernel_digest.py`、`v0_skeleton/kernel/tools/calibrate_latency.py`、
`v0_skeleton/kernel/tests/{test_kernel_digest,test_e2e_run_verify,test_bus_and_ecs_invariants,test_events_snapshot_invariants,test_calibrate_latency}.py`

> 与设计 §3 文件表的**差异（加法，已登记）**：设计列了 3 个新测试文件，实际为 5 个
> （多出 `test_events_snapshot_invariants.py` / `test_calibrate_latency.py`）。
> 理由：设计 §6 的 R17/R18/R24/R25 与 R19 需要落点，且 R19 的「工具链自证」按设计 §4.9
> 必须离线可跑。两者都在 `kernel/tests/**` 写集内，且未夹带任何无关重构。
> 另新增 `deephealing_kernel/__main__.py`：冻结命令面全部以 `python -m deephealing_kernel` 形式调用，
> 包内无 `__main__.py` 时该形式无法运行（属实现必需，非范围扩张）。

---

## 1. 逐 AC 判定（AC-M1-1 ~ AC-M1-8）

> 本节是**修复轮之后的最终判定**（每条都在 `03_artisan_self_test.log` 有对应命令 + workdir + exit）。
> 与首轮的差异、以及每条修复的根因/证据，见 §10；未闭合项一律照实写 GAP，不修饰。

### AC-M1-1 契约仍全绿 —— **PASS**

- 命令 / workdir：`cd {ws}/02_source && bash verify_specs.sh --quiet`
- exit：**0**　输出：`verify_specs: OK (95 checks passed, 0 skipped)`（与基线 95/0 一致）
- 关键前提：`manifest.txt` 已覆盖全部 9 个新增文件（首轮曾因漏登记红过 9 条，登记后转绿）
- **跑完 AC-M1-3 之后复跑**（预审 M8）：exit **0**，且 `find 02_source -name '__pycache__' -o -name '.pytest_cache'` 空
- 收尾清理残渣后复跑：exit **0**
- 产物：`{ws}/02_source/manifest.txt`、`{ws}/03_artisan_self_test.log` §1 / §3e / §10

### AC-M1-2 确定性 tick 与回放（含负例） —— **PASS**

- 命令 / workdir：`cd {ws}/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_determinism_replay.py -q -p no:cacheprovider`
- exit：**0**　输出：`6 passed`（**0 skipped**；基线 `18 skipped / 0 passed` 的收集性检查已被真绿取代）
- 用例（设计 §6 R1~R4 + 边界）：
  - R1 `test_replay_twice_yields_identical_checkpoints`：两次 run 三字段逐点一致 + 强制 `run ↔ replay` 比对
  - R2 `test_replay_detects_wall_clock_leak`：**双向断言**（无泄漏 ⇒ 一致；注入 wall-clock ⇒ 分歧；干净 verify 子进程把泄漏日志判红）
  - R3 `test_replay_detects_unordered_iteration`：**跨进程** `PYTHONHASHSEED=1 vs 2`，测试进程不作比较方
  - R4 `test_new_subsystem_does_not_perturb_existing_streams`：含「共享计数器」错误实现对照
  - 边界：`ticks=1/snapshot_every=1`、`ticks=7/snapshot_every=3`（不整除）
- **负例自证（逐条）**：
  - R2：把 `leaked` 从 wall-clock 去掉 ⇒ 两次产物一致（红→绿可逆）。**发现并记录一个零命中绿陷阱**：
    本机 `time.time_ns() % 1000` **恒为 0**（时钟微秒粒度）⇒ 第一版注入退化成常量、负例不红；
    改用微秒分量后分歧稳定出现（见 `03` §2 与 `spikes/debug_leak2.py`）。
  - R3：① `set[str]` 跨进程**必分歧**（`field_diff:… field=state_hash`）；② 反向对照 `set[int]`（恒为 1..5）
    **不**分歧 ⇒ 证明 ① 不是零命中绿；③ 改回 `sorted()` ⇒ 一致。
  - R4：错误实现（共享计数器）被同一条判据判红。

### AC-M1-3 端到端 `run` → `verify` → `replay` —— **PASS**

- 命令 / workdir：`cd {ws}/02_source/v0_skeleton/kernel`
  - `python3 -m deephealing_kernel run --pack districts/xingfu-xiaoqu --seed 20260921 --events {ws}/out/m1-ac3/e.jsonl --snapshot-every 50` → exit **0**
    （925 事件 / 6 检查点 / 链尾 `baecca92…`；`--ticks` 默认 300，属加法扩展）
  - `python3 -m deephealing_kernel verify --events … --pack districts/xingfu-xiaoqu` → exit **0**
    （打印 `chain anchor: not provided`；逐检查点 `state_hash`/`rng_state_digest`/`event_chain_hash` 一致；ECH-1/2/3 成立）
  - `python3 -m deephealing_kernel replay --events … --checkpoint-every 50 --out {ws}/out/m1-ac3/replay` → exit **0**，6 个检查点与 run 侧逐点一致
- **负例①（朴素整行截断）**：删尾部 6 行（链仍连续）⇒ exit **1**，`truncated log: max_tick=298 != plan_ticks=300`，
  **首个分歧 tick = 299**
- **负例②（篡改一条 payload）**：只改 payload 不重算 hash ⇒ exit **1**，`hash mismatch at tick 1`，**首个分歧 tick = 1**
- **负例③（C1 伪造日志）**：`spikes/ac3-forge/forge_log.py`（独立脚本）构造「截断到 tick≤100 + 改写 `world.init.plan_ticks=100`
  + 按冻结公式重算整条链 + 同步改写快照事件 payload 的 `event_chain_hash` + 删 tick>100 的检查点」（925→463 事件）
  - 不传锚点 ⇒ **exit 0**（伪造链自身自洽；这正是**声称边界**，见 §3 C1）
  - `--expected-hash <原始链尾 baecca92…>` ⇒ **exit 1**，`anchor_mismatch`，首个分歧 tick = 100
  - 正向对照：伪造日志 + **伪造自身链尾** ⇒ exit 0（证明锚点比较真的在跑，不是恒红）
  - 正向对照：未篡改日志 + 正确锚点 ⇒ exit 0
- 产物：`{ws}/out/m1-ac3/{e.jsonl,checkpoints/0000{50,100,150,200,250,300}.json}`、
  `{ws}/out/m1-ac3/replay/checkpoints/`、`{ws}/out/m1-ac3-trunc/`、`{ws}/out/m1-ac3-tamper/`、`{ws}/out/m1-ac3-forged/`
- **修复轮 A1（新增判据面）**：`verify` 现在**产出重放事件流**并与日志逐条比对语义序列
  （`(tick, type, actor)` + payload，**不比** `seq`/`prev_hash`/`hash`；豁免面**恰好**是
  `EVENT_STREAM_LOCATOR_KEYS == {"checkpoint_path"}`，由用例钉死）。输出字段：
  `event_stream_compared / event_stream_divergences / event_stream_events_logged / event_stream_events_replayed`。
  - **5 类完全自洽伪造矩阵**（`spikes/ac3-forge/forge_matrix.py`；「事件链 + 快照 payload 的
    `event_chain_hash` + 检查点文件」三处一起重算 ⇒ ECH 与检查点交叉核对**都不会**报警）：
    - `drop_mid_npc_actions`（中段删 15 条 `npc.action`）⇒ **不传锚点 exit 1**，归因 `event_stream:`
    - `tamper_mid_payload`（中段改 payload）⇒ **不传锚点 exit 1**，归因 `event_stream:payload_diff:`
    - `drop_snapshot_event`（删 `snapshot.taken@150` 及其检查点）⇒ **不传锚点 exit 1**，归因 `event_stream:`
    - `drop_one_and_change_last_actor`（删 1 条 + 改末条 `actor`）⇒ **不传锚点 exit 1**，归因 `event_stream:`
    - `truncate_rechain`（截断 + 改 `plan_ticks` + 重算整链 + 同步改检查点）⇒ **不传锚点仍 exit 0**，
      **必须**由 `--expected-hash` 判红 ⇒ 见 §7 GAP-7（**如实记为残余，不修饰**）
  - 未篡改日志 ⇒ 不传锚点 exit 0、传正确锚点 exit 0（**防恒红**）
  - 明细行上限（`cli.MAX_DIVERGENCES = 25`）：一处中段删除会让其后每条都失配 ⇒ 只上报前 25 条 +
    一条 `event_stream:truncated_report:shown=… total=…`；**总数与首个分歧 tick 不受影响**
    （`event_stream_divergences` = **真实总数**，`event_stream_divergences_reported` = 明细行数）
  - 用例：`tests/test_e2e_run_verify.py::{test_forged_log_matrix,test_event_stream_comparison_excludes_only_locators,test_event_stream_report_is_capped,test_claim_boundary_is_rewritten_for_event_stream_strength}`
- **修复轮 A2**：`verify` 的 `claim_boundary` 已按新强度改写（「链自洽 + 检查点与重放一致 +
  **事件流与重放一致**」），并仍明确「**不**代表日志未被篡改，抗改写必须 `--expected-hash`」。

### AC-M1-4 内容包加载与第二街区 —— **PASS**

- 命令 / workdir：`cd {ws}/02_source/v0_skeleton/kernel`
  - `python3 -m deephealing_kernel validate --pack districts/xingfu-xiaoqu` → exit **0**
    （12 实体 / 5 NPC / 2 楼栋 / 1 门户边且 `status=inactive` / `weather_declared_and_dropped=true`）
  - **裸** `pytest tests/test_pack_validate.py -q` → exit **0**（`7 passed`，非 collection error）
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_pack_validate.py -q -p no:cacheprovider` → exit **0**
- 具名用例均在：`test_second_district_requires_no_kernel_change`、`test_tampered_pack_fails_closed`、
  `test_executable_file_in_pack_is_rejected`（另含 `test_pack_validates_and_signature_matches`、
  `test_seed_projection_passes_world_schema`、`test_pack_rejects_path_escape`、
  `test_pack_sign_and_verify_use_same_executable_criteria`）
- 一律用 `tmp_path` 副本，**未**原地篡改 `districts/**`
- 负例自证：篡改数据文件 ⇒ `hash_mismatch` + 非 0；未重签的第二街区 ⇒ 非 0，重签后 ⇒ 0；
  `.py` ⇒ `pack sign` 与 `validate` 双双拒绝；改名后的 shebang 内容 ⇒ `pack sign` 放行（L3 已知）、`validate` 拒收；
  缺 `transform` / `kind` 非法的 seed **重签之后**仍被拒收（证明拦截来自 schema 强口径而非签名失配）

### AC-M1-5 内核源码指纹（W0b） —— **PASS**

- 命令 / workdir：`cd {ws}/02_source/v0_skeleton/kernel`
  - **裸** `pytest tests/test_kernel_digest.py -q` → exit **0**（`4 passed`）
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_kernel_digest.py -q -p no:cacheprovider` → exit **0**
  - `python3 tools/kernel_digest.py --root . --json` → exit **0**，`{"files": 25, "digest": "a1a7b545030ac5f1ff412cc7965c299980d68e5f5fccbb0b828a2842b8fdf84f"}`（**修复轮重取**；首轮为 `8201a770…`、修复轮中途为 `34f4b457…`，因修复轮改了 `ecs/events/pack/rng/snapshot/tick/cli` 与 `calibrate_latency`；与 `03_artisan_self_test.log` §5/§12 逐位一致）
  - `python3 tools/kernel_digest.py --selftest` → exit **0**（1 正例 + **2 条强制负例** + 1 并集正例全按预期）
- **判据① 的口径声明（修复轮 C3）**：正例的 `before` 与 `after` 现在是**同源的两棵隔离副本**
  （`_copy_package(tmp_path/"before_tree")` 与 `+ adapters/relation_infer.py`），即**两棵真实存在的树之间的差集**；
  首轮是「本仓实树 vs 副本」，属半真半假的对照，已改。两条**强制负例**（改 `tick.py` 一字节 / 包根新增 `.py`）保留。
- **基线锚点（预审 M4）复现**：`spikes/kernel-baseline/`（实现前 24 个桩文件的逐字节快照）
  `kernel_digest` = `files=24`、`digest=058e9a548be3c2186fc501441c556a27096c9eebfcca78cf4043b9e496697837` —— **逐位相符**
  （实现后的 `files=25` / `a1a7b545…`（修复轮最终）是**预期变化**：本轮新增 `deephealing_kernel/__main__.py` 并改写了 8 个模块；
  基线锚点的作用是**证明 before 值可复现**，不是要求 before == after）
- **两条强制负例**（都在 `tmp_path` 隔离副本上）：
  - ① 改 `tick.py` 一个字节 ⇒ `changed == ["tick.py"]` ⇒ 判据 `ok=False`
  - ② `deephealing_kernel/` 根新增 `.py` ⇒ `added == ["extra_module.py"]`（越界）⇒ 判据 `ok=False`
- 正例：`deephealing_kernel/adapters/relation_infer.py` ⇒ `changed == []` 且 `added ⊆ adapter 目录并集`；
  REQ 字面路径 `deephealing_kernel/providers/adapters/x.py` 同样被接受（并集口径，设计 §4.8）
- 交付树里**没有**新建 `deephealing_kernel/providers/adapters/`（属 W3 面，预审 M4 第 5 条）
- `tools/kernel_digest.py` **未** `import deephealing_kernel`（`sys.path[0]` = `tools/`；断言按代码行正则校验）
- 产物：`{ws}/spikes/kernel-baseline/BASELINE.txt`、`{ws}/spikes/kernel-baseline/deephealing_kernel/**`

### AC-M1-6 D-0.9 时间预算标定 —— **GAP**（判据 ① PASS / ② PASS / ③ **GAP：不可重复** / ④ GAP）

- 命令 / workdir：`cd {ws}/02_source/v0_skeleton/kernel`
  - `python3 tools/calibrate_latency.py registry` → exit **0**（三份冻结物 sha256 + mtime 登记）
  - `python3 tools/calibrate_latency.py dist --samples 24 --timeout-ms 60000 --out …/latency.distribution.json`
    → **exit 0**，24/24 成功、0 失败，`environment_class = usable`，
    `p50=1040.442 / p90=1194.759 / p95=1253.699 / p99=1273.766 / max=1273.766`（**真实远端调用**）
  - `python3 tools/calibrate_latency.py derive …` → exit **0**，`adopted_ms=1300`、`strict=1300`、`loose=2500`；
    `refuses_to_declare=false`
  - `degrade --formula strict|adopted|loose --runs 10` → 见下表**三次测量**（**同一份 `dist`，未重采样**）
  - `check --calibration … --dist … --degrade strict=… --degrade adopted=… --degrade loose=…` → **exit 1**
    （`E_CALIBRATION_STRUCTURAL`：`adopted == strict` 塌缩；**区间本身无越界**，`problems == []`）

| 行 | 声明值 | 区间（事先声明） | 测量 A | 测量 B | 测量 C（最终证据脚本） |
|---|---|---|---|---|---|
| strict | 1300 ms | `[0.00, 0.40]` | 0/10 = **0.00** ✓ | 2/10 = **0.20** ✓ | 2/10 = **0.20** ✓ |
| adopted | 1300 ms | `[0.00, 0.30]` | 5/10 = **0.50** ✗ | 2/10 = **0.20** ✓ | 1/10 = **0.10** ✓ |
| loose | 2500 ms | `[0.00, 0.10]` | 0/10 = **0.00** ✓ | 0/10 = **0.00** ✓ | 0/10 = **0.00** ✓ |

> 三次测量**共用同一份 `dist`**（`latency.distribution.json` 自 08:44 起未变，**未重采样**），
> 只重跑 `degrade`（每式 10 次真实调用）。`adopted` 行在相邻三次里得到 **0.50 / 0.20 / 0.10**，
> 而区间上界是 **0.30** ⇒ 观测值跨在上界两侧，**判据③在分钟级上不可重复**。

| 判据 | 判定 | 证据 |
|---|---|---|
| ① 规则文件 mtime **早于**分布日志 **且** 两份冻结物与 round-3 逐字节相同 | **PASS** | 规则/区间 `mtime=1790037534`（08:38:54）< 分布日志 `mtime=1790037851`（08:44:11）；`sha256` = `7590eab4b765671860eaa50b68de807606581bfdd439cb3aa6fe2d953edb0feb` / `713dba90df07f63e685fc98dcf276769ba37f2617f9c8a4b38319d8c174bddb4`（预审 C3 关闭） |
| ② `timeout_ms ≥ p95` 且 `≠ max` | **PASS** | `adopted_ms=1300 ≥ p95=1253.699` 且 `1300 ≠ max=1273.766`；`budget ≥ p90` 成立 |
| ③ 严/采用/松三行落在**事先声明**区间 | **GAP（不可重复）** | 测量 A：adopted `0.50 ∉ [0.00,0.30]` **✗**；测量 B/C：三行全 ✓。同一份 `dist`、同一批声明值、同为 `--runs 10`，相邻三次测量给出 `0.50 / 0.20 / 0.10`（上界 0.30 被跨过）⇒ **该判据在分钟级上不可重复**，**不得**按「最后一次绿」标 PASS |
| ④ `check` exit 0 | **GAP** | exit **1**（原因**不是**区间越界，而是 `E_CALIBRATION_STRUCTURAL`：判据③的前提塌缩） |

- **为什么不重标、不调参**：冻结规则明写「某一行的实测降级率落在区间外 → 该行判 **FAIL**（不得事后调整区间，
  只能重标并说明原因）」。`dist` 文件**未重采样**（`latency.distribution.json` 自 08:44 起未变），
  测量 B/C 只是**例行证据脚本**重跑了 `degrade`（每式 10 次真实调用）——三次结果**全部**列出，
  **没有**为了变绿去挑窗口、也没有只报有利的那一次。
- **根因（修复轮 C4，取代首轮「非平稳」这一条单因归因）**：**环境抖动 ＋ 冻结区间口径塌缩**。
  `check` 现在**显式**报告塌缩：七个能力的 `adopted_ms == strict_candidate_ms`（`1300 == 1300`，**7/7 全部塌缩**），
  成因 = 冻结推导规则的 `ceil_to` 窗口让 `strict` 与 `adopted` 落在**同一个窗口**
  （`ceil_to(50, p95) == ceil_to(100, p95) == 1300`，`p95=1253.699`）⇒ 「松一档」**退化**成与 strict 同一值。
  这不是纯数值噪声，而是**判据③的前提不成立**：两行本质上是**同一个值**
  （同一值不可能既满足 `[0.00,0.40]` 又满足 `[0.00,0.30]`，三次测量的差异纯属同一分布的抽样抖动）。
  → 已作为**独立上抛项**列出（见 §7 GAP-2 与 §10 C4）。**仍然不重标、不调参**
  （改 offset/区间 = 改冻结物；调 `adopted` = 挑样本）。
- **判据④ 的口径（加法 A14，请 PM 知悉）**：`check` 对「塌缩」**fail-closed**（`E_CALIBRATION_STRUCTURAL` ⇒ exit 1）。
  理由：前提不成立时，`check exit 0` 会**掩盖**「松一档根本没生效」这件事，而那正是判据③想证明的东西。
  若 PM 认为塌缩只应告警不应改退出码，这是一处**可回退的加法**（改动点只有 `cmd_check` 的一个分支）。
- **修复轮 C5**：`check` 的独立重算从「只比 p90」扩到 **p50/p90/p95/p99/max 五个量逐个比对**；
  反向对照：把 `p90_ms`（或 `max_ms`）只改 1 ms ⇒ `check` 必须非 0 并归因到该量（`03` §6c）。
- **工具链本身已被证明双向可达**（离线、不消耗凭据）：
  `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_calibrate_latency.py -q -p no:cacheprovider` → exit **0**，`7 passed`
  - 干净合成样本 ⇒ `dist` usable、`derive` 产出声明值、三行降级率全在区间内、`check` exit 0
  - 污染合成样本（重尾）⇒ `dist` degraded、`derive` **fail-closed**、`per_capability == {}`（**不产出任何声明值**）、`degrade`/`check` 非 0
  - 陈旧声明值（把 adopted 压到 900 ms）⇒ 降级率越界 ⇒ `degrade` 非 0（**区间闸不是零命中绿**）
  - 分布日志早于规则文件 ⇒ `derive` 非 0
- **差什么 / 下一步谁补**：需要一个**平稳的网络窗口**重采样并重跑 `degrade` 三行（Q1，归 PM/需求侧）；
  本轮**不改** `02_source` 里任何 `timeout_ms`/`calibration` 声明值（`check` 的 INFO 行逐条列出盘上值
  `43400~44400 ms` 与本轮推导值 `1300~2300 ms` 的差异，并注明「Q1 未重标」）。
- 产物：`{ws}/spikes/s5-latency-calibration/{calibration.registry.json,ENVIRONMENT-CLASS.frozen.md,DERIVATION-RULE.frozen.md,ACCEPTED-DEGRADATION-RANGE.frozen.md}`、
  `{ws}/spikes/s5-latency-calibration/logs/{latency.distribution.json,calibration.json,degradation.{strict,adopted,loose}.json,calibrate_latency.console.log}`
- **本轮新增的第三份冻结物**（加法，不放松任何既有判据）：`ENVIRONMENT-CLASS.frozen.md` 在**采样之前**落盘
  （mtime 08:43:34 < 分布日志 08:44:11），把「环境是否可用」写成**测量前声明**的判据
  （`p90 ≤ 20000 ms` 且 `p90/p50 ≤ 3.0` 且 `samples ≥ 20` 且 `failed == 0`），
  使 `derive` 在污染分布下**有依据**地 fail-closed，而不是靠事后判断。

### AC-M1-7 凭据与脱敏 —— **分列两条**

**（a）凭据面 —— PASS**

| 检查 | 命令（workdir = `{ws}`） | 结果 |
|---|---|---|
| 真实凭据值全树扫描 | `grep -rIl --exclude-dir=.git -e "$HERMES_CUSTOM_TOKENFAB_API_KEY" . \| wc -l` | **0 命中**（只统计条数，不回显内容） |
| `Bearer ` 形态清单（交付产物 `02_source` + `out`） | `grep -rIho -e "Bearer [^\",)]*" 02_source \| sort \| uniq -c` | 只有三种形态：`Bearer {credential}`（代码前缀，**值不落盘**）、`Bearer ***REDACTED***`（脱敏值/文档措辞）、`Bearer FIXTURE-NOT-A-CREDENTIAL-1/2`（测试夹具，显式命名为非凭据） |
| 越界形态计数 | `grep -rIn -e 'Bearer ' 02_source out \| grep -v 'Bearer \*\*\*REDACTED\*\*\*' \| grep -v 'Bearer {credential}' \| grep -v 'Bearer FIXTURE-NOT-A-CREDENTIAL' \| wc -l` | **0** |
| 扫描器自证 | `/tmp` 放一个假 token ⇒ 命中 **1** | 证明扫描**不是零命中绿** |
| 事件日志抽查 | `out/**` 与标定日志中 `"prompt"` / `"messages"` 命中数 | **0** |

**（b）请求体面 —— 有调用、无落盘请求体；判据已补（修复轮 C1 修正口径）**

- **首轮表述错误**：写成「本轮没有任何模型调用 ⇒ 该面为空集」。**实际不是空集**：
  W0e 标定打了 **24（`dist --samples 24`）+ 3 式 × 10（`degrade --runs 10`）= 54 次真实远端调用**。
- **正确表述**：请求体面 = 「**有 54 次真实调用**、**无落盘请求体**（三份产物均自报 `transcript_written: false`）」。
- **判据（带自证负例）**：扫描面 = `{ws}/out/**` + `{ws}/spikes/s5-latency-calibration/**`，
  模式 = JSON **对象键** `"prompt":` / `"messages":` / `"raw_headers":` / `"request_body":`（带冒号 ⇒
  不误命中合法的 `"prompt_scope":`）。
  - 真实扫描面命中 **0**（`03` §7 请求体面①②）
  - **反向对照**：把探针文件写进**真实扫描面** `out/.probe-request-body.jsonl` ⇒ 命中 **≥1**；
    移除后回到 **0** ⇒ 证明「0 命中」不是零命中绿
  - 用例：`tests/test_evidence_scan.py`（含 `transcript_written: false` 与真实调用数 54 的断言）
- **显式声明**：M2 引入 W3（能力注册表 / provider 调用）时**必须**把该面扩展为
  「事件日志与 cassette 中不得出现 prompt / 原始请求体」的**完整**判据（本轮只覆盖标定工具链的产物面）。
- 另记（预审 U5）：`capability.safety.prompt_injection_guard`（enum）本轮**无任何判据**覆盖。

> 两条**不得**合并成一句 PASS（预审 M10）。

### AC-M1-8 真实仓库零改动 + 起点溯源 —— **PASS**

- `cd /Users/wooyinq/personal/deep-healing && git rev-parse HEAD` → `b421cb01df4bf864b9a3fa48dbf6221c3989dc02`，exit **0**
- `cd /Users/wooyinq/personal/deep-healing && git status --porcelain` → **空**，exit **0**
- `cd {ws} && shasum -a 256 SEED.sha256` → `34fa7f6d252bc4bf966c8dbc4d639a1f08788ed71b9cfa04a0896ca7ba8f7676`，exit **0**
- 未执行任何 `commit` / `push` / `PR` / 部署。

---

## 2. RED → 最小 GREEN（真实过程）

| 阶段 | 命令 / workdir | exit | 结果 |
|---|---|---|---|
| RED（实现前） | `cd {ws}/spikes/red/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider --tb=no --continue-on-collection-errors` | **1** | `24 failed, 11 passed, 1 error`（日志：`{ws}/spikes/red/RED.log`） |
| GREEN（实现后） | `cd {ws}/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider` | **0** | `42 passed, 10 skipped`（首轮）/ **`62 passed, 10 skipped`（修复轮：新增 20 条判据，见 §10）** |

- RED 沙箱由 `spikes/build_red_sandbox.py` 构建：把**本轮最终版测试文件**跑在
  `spikes/kernel-baseline/deephealing_kernel/`（**实现前**的 24 个接口桩）上，目录深度与真实
  `02_source/v0_skeleton/kernel` 一致（使测试里的 `parents[2]` 仍解析到沙箱自己的 WS_ROOT）。
- RED 里通过的 11 条 = `test_calibrate_latency.py`（只测标定工具本身，不依赖内核实现）+ 少量不依赖内核的断言。
- 10 skipped = `tests/test_capability_registry.py`（6 条，属 **W3**）+ `tests/test_observe_mode_readonly.py`（4 条，属 **W7**）
  —— 见 §7 GAP-1，本轮**有意保留 skip**，未为了让它们变绿而实现 W3/W7。
- 实现过程中由测试真实抓出的**3 个缺陷**（均已修 + 已加回归断言）：
  1. **`tags` 被静默丢弃**：`to_state()` 只导出 `COMPONENTS`（7 个），而 `tags` 是 `world.schema.json`
     允许但不在该元组里的键 ⇒ 内容包声明的 tags 全部从 state 消失（数据丢失）。
     修法：新增 `SCALAR_ENTITY_KEYS = ("tags",)` 与 `ENTITY_KEYS = COMPONENTS + SCALAR_ENTITY_KEYS`，并在用例里断言 tags 存活。
  2. **`kernel_digest` 的 adapter 前缀写错**：`ADAPTER_DIRS` 原写成 `deephealing_kernel/adapters/`，
     而差集里的 relpath 是相对 `deephealing_kernel/` 的 ⇒ 正例被误判越界。
     修法：改为 `("adapters/", "providers/adapters/")`。
  3. **重复 `run` 会污染事件日志**：`EventLog` 以追加模式打开既有日志 ⇒ 同一文件里出现第二条 `seq=0` 的链
     （第二次证据复跑时实测 `seq gap (expected 925, got 0)`）。
     修法：`cli._refuse_existing_log()` —— 目标日志非空即 `E_EVENTS_EXISTS` **fail-closed**，
     并新增 `test_run_refuses_nonempty_event_log`（含「拒绝时不得改动既有日志」的断言与干净目录反向对照）。

---

## 3. §4b 预审关闭项逐条证据（Raven rev2：3 CRITICAL + 10 MEDIUM + LOW + 未加固面）

### CRITICAL

| 项 | 处置 | 关闭证据 |
|---|---|---|
| **C1** `plan_ticks` 锚点在链内可伪造 ⇒ verify 假绿 | ① `--expected-hash` 实现为**链外锚点**且 fail-closed（三态）；② 声称边界写进 `verify` 输出与本文档 | `03` §3d：伪造日志（截断 925→463 + 改 `plan_ticks` 300→100 + 重算整条链 + 改快照 payload 的 `event_chain_hash` + 删 tick>100 检查点）→ **不传锚点 exit 0**（`chain anchor: not provided`）、**传原始链尾 exit 1 `anchor_mismatch`（首个分歧 tick=100）**、传伪造自身链尾 exit 0、未篡改日志 + 正确锚点 exit 0。用例：`tests/test_e2e_run_verify.py::test_verify_anchor_expected_hash`；夹具：`spikes/ac3-forge/forge_log.py`。**声称边界**：不传锚点时 `verify exit 0` **只**代表「确定性一致」，**不代表**「日志未被篡改」（`verify` 的 JSON 输出里带 `claim_boundary` 字段） |
| **C2** AC-M1-4/5 的冻结命令写裸 `pytest` ⇒ 必 collection error | 新增 `kernel/conftest.py` 把 `kernel/` 根插入 `sys.path`，**未**改 REQ/设计的命令文字 | `03` §4/§5：`pytest tests/test_pack_validate.py -q` → exit **0**（`7 passed`）；`pytest tests/test_kernel_digest.py -q` → exit **0**（`4 passed`）；`python3 -m pytest` 形态同样 exit 0。**反向对照**：RED 沙箱里删掉 `conftest.py` 时这两条命令必 `ModuleNotFoundError`（architect 探针 `.squad_tools/probe_pytest_import.log` B/D 段已实证） |
| **C3** AC-M1-6 判据① 是零命中绿（同轮自建规则文件必然 mtime 更早） | 本轮两份冻结物取 002 工作区同名文件的**逐字节副本**并登记 sha256；**未**重写、**未** `touch -t` | `03` §0b：`7590eab4…` / `713dba90…` 与预审给定值逐位相符；两份 mtime = `1790037534`（08:38:54），早于分布日志 `1790037851`（08:44:11）；`tests/test_calibrate_latency.py::test_frozen_artifacts_are_byte_identical_to_round3` 断言这两个常量 |

### MEDIUM

| 项 | 处置 | 关闭证据 |
|---|---|---|
| **M1** seed 校验口径过弱 | 采纳**严格更强**口径：去 `weather` 后的投影**全量**过 `world.schema.json`，同时保留 `$defs/worldSeed` | `tests/test_pack_validate.py::test_seed_projection_passes_world_schema`：投影过 `world.schema.json`；**缺 `transform`** 与 **`kind` 非法**的 seed 副本**重签之后**仍被 `validate` 拒收（exit≠0）；**同一份损坏 seed 过 `$defs/worldSeed` 是绿的** ⇒ 证明弱口径就是假绿 |
| **M2** `redact()` 丢弃 `redact_fields` | 改为以 `redact_fields`（点分路径 + glob）为**主判据**，键名匹配作补充；`Authorization` 类 → `Bearer ***REDACTED***`，其余 → `***REDACTED***` | `tests/test_events_snapshot_invariants.py::test_redact_fields_path_and_glob`：`env.FOO_API_KEY` 被替换（**只按硬编码键名表的实现会漏**，用例内置该错误实现的对照）；`payload.raw_headers.Authorization` 前缀形态命中；原 payload 不被就地修改。`test_event_log_applies_redaction_on_append`：落盘文本里夹具值 0 命中、脱敏形态存在 |
| **M3** run↔replay 是同一实现的自比对 | 新增**独立**完整性断言 `snapshot.check_checkpoint_integrity()`：逐检查点复算 `sha256(canonical_json(checkpoint["state"]))` 与文件 `state_hash` 逐位比对；`verify` 第 6 步调用它。**修复轮 C10 补强**：canonical JSON 的「跨语言逐位一致」判据改为**独立序列化对照**（`tests/test_canonical_contract.py` 内手写编码器，不 import 被测实现）。**边界（修复轮 2 / G7 / Raven R21 附）**：该断言**独立于 run↔replay 轴**，但**共用 `canonical_json`** ⇒ 挡不住序列化实现本身的缺陷（该子类由 C10/F7 的独立编码器与样本覆盖，**不得**读成「M3 已挡住所有共有错误」） | `tests/test_events_snapshot_invariants.py::test_checkpoint_state_hash_selfconsistent`：真产物 → `[]`；**手改 `state_hash` 一个字符** → `state_hash_mismatch`（且端到端 `verify` 非 0）。C10 反向对照：把内核 canonical 实现换成「分隔符带空格」变体（保持 `sort_keys=True`）⇒ 子进程里同一条判据**非 0**；F7 追加「键序按 `key.lower()`」变体 ⇒ 同样**非 0** |
| **M4** adapter 目录不存在 + 三处路径不一致；**新增基线锚点** | 判据取并集 `{adapters/**, providers/adapters/**}` + 两条强制负例 + **不新增** `providers/adapters/`；基线锚点 `files=24` / `058e9a54…` 已复现 | §1 AC-M1-5；`tests/test_kernel_digest.py::{test_digest_baseline_anchor,test_kernel_digest_diff_criterion,test_no_providers_adapters_dir_in_delivery_tree}`；`tools/kernel_digest.py --selftest` exit 0 |
| **M5** R3 负例三条前提 | 全部满足：(a) 注入容器是 `set[str]`；(b) 迭代顺序经 `needs.esteem` 增量**真的进入** `state_hash`（断言分歧字段是 `state_hash`）；(c) 两个产物在**不同子进程**（`PYTHONHASHSEED=1` vs `=2`）产生，测试进程不作比较方 | §1 AC-M1-2；**反向对照**：容器换成 `set[int]`（恒为 1..5）⇒ 必须**不**分歧 —— 用例断言 `compare_checkpoints(...) == []`，证明 ① 不是零命中绿 |
| **M6** `--ticks` 默认 300 使 M3 判据 6 语义漂移 | 记录为跨里程碑风险（M1 自身 AC 不受影响） | §7 上抛项 6 |
| **M7** `compare_checkpoints -> list[str]` 承载不足 | 保持冻结签名，实现**字符串协议**：`missing_in_left:tick=` / `missing_in_right:tick=` / `field_diff:tick=… field=… left=… right=…` / `missing_field:tick=… field=… side=` / `null_field:tick=… field=… side=` / `checkpoint_set_error:<原因>` | `tests/test_events_snapshot_invariants.py::test_verify_checkpoint_set_canonical`：非规范名 `25.json` → `checkpoint_set_error:non_canonical_filename`；同 tick 两份（`000025.json` + `25.json`）→ `checkpoint_set_error:duplicate_tick:25`；缺 tick → `missing_in_left:tick=40`；字段缺失 → `missing_field:… side=left`；字段差异 → `field_diff:tick=20 field=event_chain_hash left=… right=…`。**加法说明**：`side=` 是对冻结前缀的**加法**扩展（前缀与字段名逐字未改），已在模块 docstring 与本文档登记 |
| **M8** AC-M1-3 产物落点未钉死 | 钉死 `{ws}/out/m1-ac3/`（`02_source` 之外），并在 AC-M1-3 之后复跑 AC-M1-1 | `03` §3（产物全在 `{ws}/out/**`）+ §3e（复跑 exit 0 + `find` 空） |
| **M9** `replay --out` / `checkpoints/` 与 W9 面重叠 | `06` 显式声明 W9 仍未做 | §6 声明段 |
| **M10** AC-M1-7 请求体面无判据 | 分列两条；请求体面**修正口径**（有 54 次真实调用、无落盘请求体）并**补上带自证负例的扫描判据**（修复轮 C1） | §1 AC-M1-7（a）/（b）；`03` §7 请求体面①②③；`tests/test_evidence_scan.py` |

### LOW

| 项 | 处置 | 证据 |
|---|---|---|
| **L1** `write_checkpoint` 桩注释与 `{tick:06d}` 不一致 | 按设计实现 `{tick:06d}.json`，桩注释为旧文 | `out/m1-ac3/checkpoints/000050.json … 000300.json`；`compare_checkpoints` 对非规范名报错 |
| **L2** `take_snapshot(world: dict, …)` 保持冻结签名 | **保持** `dict`，调用方传 `world.to_state()`（docstring 写明） | `snapshot.take_snapshot` 签名未改；`tick._take_and_write_checkpoint` 传 `to_state()` |
| **L3** `pack_sign.py` 只按后缀判可执行 | **不改**（属「只许加强」面且非本轮 AC 所需）；用例把该缺陷**固化成断言**，防止被误读为已加固 | `tests/test_pack_validate.py::test_executable_file_in_pack_is_rejected`：改名后的 shebang 内容 `pack sign` 放行（exit 0）、`validate` 拒收（exit≠0） |
| **L4** 顶层残渣不被 `GENERATED_PATTERNS` 排除 | 收尾统一清理生成残渣并复跑 | `03` §10：清理后 `find` 空 + AC-M1-1 exit 0。**修复轮 2 / G6 计数改正**：字面形态 AC-M1-4 裸 `pytest` 单步实测 **6 目录 + 7 `.pyc` = 13 条路径**；叠 AC-M1-5 ⇒ **14**；再叠字面 `run` ⇒ **22**（`spikes/measure_literal_residue.py`，`/tmp` 副本） |
| **L5** 「同口径」措辞不准确 | 改为「口径 = `08` §2 W0b 排除表」并写明与 spike 先例的差异 | `tools/kernel_digest.py` docstring；§1 AC-M1-5 |
| **L6** `--snapshot-every` 与 pack 常量可能不一致 | `run` 把**生效的** `snapshot_every` 写进 `world.init` payload；`replay`/`verify` 一律以**日志记录的生效值**为准；`state.constants` 保持内容包声明值 | `world.init` payload 含 `plan_ticks` 与 `snapshot_every`；`verify` 输出 `snapshot_every_from_log`；`replay` 输出 `snapshot_every_from_log` |

---

## 4. 未加固面显式声明（U1~U17，逐条）

| # | 未加固面 | 本轮事实 / 会被误读成什么 |
|---|---|---|
| **U1** | `verify` 的「重放比对」是**自比对**（与 `run` 共用 `WorldKernel` 实现），且不传锚点时**无外部锚点** | 会被误读成「`verify exit 0` ⇒ 日志完整且未被篡改」。实际只能推出「同一实现两次运行一致」。缓解：M3 独立完整性断言挡住「`state_hash` 算在错误对象上」这类**共有**错误；抗改写必须传 `--expected-hash`。**边界（修复轮 2 / G7 / Raven R21 附）**：M3 的断言**独立于 run↔replay 轴**，但它**共用 `canonical_json`** ⇒ 挡不住「序列化实现本身」的缺陷（该子类由 `tests/test_canonical_contract.py` 的独立编码器覆盖，见 §10.3 C10 与 §11 F7） |
| **U2** | `weather` **静默不入 state**（内容包声明了它，内核状态里没有天气字段） | 会被 M2 误读成「天气已支持」。缓解：`pack.py` 在加载后**显式断言** `world_seed["weather"]` 存在、并在 docstring 写明「有意丢弃」；`validate` 输出 `weather_declared_and_dropped=true`；用例 `test_weather_is_read_explicitly_and_dropped` |
| **U3** | `run` **不做 wall-clock 节流** ⇒ 「10 Hz」是**语义**不是实测 | 会被误读成「世界以 10 Hz 实时推进」。实际是毫秒级跑完 300 tick（=30 秒世界时间）。`--tick-rate` 本轮接受但不节流 |
| **U4** | `02_source` 里**现有**声明值（`timeout_ms` 43400~44400 ms、`p90_ms=42110.951`、`max_ms=54031.089`）来自**被拥塞污染**的分布，属**已知可疑**值 | 会被 M2 读作「已标定正确」。本轮**未改**这些值（Q1 归 PM）；`check --cap-dir` 逐条打印「盘上值 ≠ 本轮推导值」的 INFO |
| **U5** | AC-M1-7 的「prompt / 原始请求体」面本轮**无判据**；`capability.safety.prompt_injection_guard` 同样无判据 | 见 §1 AC-M1-7（b）。M2 引入 W3 时**必须**补 |
| **U6** | `replay --out` / `checkpoints/<tick>.json` 与 **W9** 面重叠 | 会被读成 W9 已完成。见 §6 声明段 |
| **U7** | `verify_specs.sh` **不校验** `world.seed.json` vs `world.schema.json` | 契约矛盾（K1）**不会**被 AC-M1-1 捕获，只有内核 `pack.py` 的口径能捕获（本轮已升级为强口径） |
| **U8** | `plan_ticks` 锚点的**强度边界**（无密钥哈希链不是真实性保证） | 见 §3 C1 的声称边界。契约自身已承认该边界（`cassette.format.md` 的 `FROZEN-CASSETTE-INTEGRITY-1`） |
| **U9** | **内容层零消费**：`npcs/**`、`buildings/**`、`tasks/**`、`assets/manifest.json` 只被**读取 + 计数**，其字段**不进入**世界状态 | 会被 M2 读成「内容层已生效」。实际 `to_state()` 里只有 seed 投影出的 12 实体（id/kind/transform/tags/…）；`tasks` / `assets` 未参与任何系统。另记一处**内容/seed 形状不一致（已逐条核实）**：两侧的 `trauma_flags` **非空条数都是 3/5**（npc-001 `loss-of-spouse` / npc-003 `empty-nest` / npc-004 `caregiver-burnout`），**不是计数冲突**；真正的差异是**这 3 条 flag 在内容侧缺 `healed_tick` 键**（内容侧 `{id, severity, since_tick}`），而 seed 侧同一 flag 是**同一对象 + `healed_tick: null`**。本轮**以 seed 为准**（内容层不消费），未做合并、未改任一文件；`healed_tick` 是否必填属**内容契约**问题（归 PM/内容管线） |
| **U10** | **四层数据面无 schema**：`npcs`/`buildings`/`tasks`/`schedules`/`assets` 在冻结契约里**没有** `$defs` | 会被读成「内容包已被结构校验」。实际只做 **JSON 可解析性**检查（`pack.py` 第 4 步的准确措辞见模块 docstring 与 `test_pack_docstring_matches_implementation`）。补齐 schema = **契约变更**（需 ADR）。注意：`asset.manifest.schema.json` **存在但未被 `pack.py` 使用**（本轮未接，属 W3/内容管线面） |
| **U11** | **符号链接越界**（预审 R7） | **修复轮 B3 已加固**：`pack.py` 对 `rglob` 命中的每个文件与每个读取点做「解析后必须仍在 pack 根内」的守卫（`symlink escape` ⇒ `E_PACK_INVALID`），用例 `test_pack_rejects_symlink_escape` 含「包内目标的真文件必须仍 exit 0」的反向对照。**修复轮 2 / G1 / Raven R16 扩写**：内核侧已加固（含 `pack.sig` 读点，F4）；**冻结的 `pack_sign.py` 与 `verify_pack.py` 都未守符号链接** ⇒ **AC-M1-1 绿不代表 pack 无越界读取**（`verify_pack.py` 才是验证工具，原先只登记了 `pack_sign.py`）。Raven 实证：符号链接逃逸 pack 上 `pack_sign.py` exit 0、`verify_pack.py` exit 0、内核 `load_pack` 拒收。给这两份冻结工具加守卫属**冻结面变更**（需 PM/ADR）。**残余**：目录符号链接子树既不进 `rglob` 也不报 `undeclared_file`（R18，归 M2） |
| **U12** | **无并发 / 多 writer 保护**：`EventLog` 用 `open("a")` 追加，**无文件锁**；`run` 的「日志/检查点非空即拒绝」是 **TOCTOU** 检查 | 会被读成「并发写会 fail-closed」。实际两个 `run` 并发指向同一 `--events` 时，第二个可能在检查后、追加前插入 ⇒ 产生第二条链。本轮**未**加锁（单进程单 writer 是本轮前提，写集纪律另有外部约束） |
| **U13** | **单街区 / 跨街区零判据**：只有 `districts/xingfu-xiaoqu` 一个真实内容包（第二街区是 `tmp_path` 副本） | 会被读成「多街区已支持」。跨街区交互（portal 边只到 `status=inactive`）、街区迁移、街区级隔离**均无判据** |
| **U14** | **cassette 完整性未登记**：`cassette.format.md` 的 `FROZEN-CASSETTE-INTEGRITY-1` 声明了强度边界，但本轮**没有**任何 cassette 完整性判据（无 cassette 文件、无校验器） | 会被读成「cassette 面已覆盖」。W3 引入 provider 调用时**必须**补 |
| **U15** | **`rng_state_digest` 覆盖全部已创建 stream**（修复轮 2 / G4 / Raven R22.2）：新增子系统**会改变**它，而 `state_hash` **不变** | 会被误读成「加子系统不改任何历史哈希」。正确口径：`state_hash` 不变（内容包/实体状态不变），`rng_state_digest` **会变**（它是 `hash_object(rng.digests())`，覆盖全部已创建 stream 的 digest 表）。用例 `test_determinism_replay.py::test_new_subsystem_does_not_perturb_existing_streams` 如实断言两条命题：① 既有 stream 的 digest **逐位不变**；② 世界级 `digests()` / `state_digest()` **必须变化** |
| **U16** | **`verify` 的资源形态**（修复轮 2 / Raven R20）：峰值 ≈ 整份日志 + 一次完整重放（**~60 KB/事件**），远超 `run`（~1 KB/事件） | 会被误读成「verify 与 run 同量级」。实测 32663 事件 → **2.05 GB / 31.9 s** vs `run` **32 MB / 12.4 s**；A1 事件流比对再叠 **+11%**。**本轮验收规模 925 事件即上限**；M2 需流式比对。详见 §7 RISK-2 |
| **U17** | **脱敏族的边界**（修复轮 2 / G8 / Raven R23.1，如实登记，**不改判据**） | `auth_token` / `authtoken` / `session_token` / `refresh_token` / `authorization_header` / `http_authorization` **由命中变漏网**（上一轮的子串实现会命中）；`secretKey` / `private_key` / `bearer` / `x-api-key` / `client_secret` / `password` **两轮都漏**。**本轮无现网影响**：M1 的事件 payload 里不存在这类键（`npc.action` 5 个字段、`world.init` 7 个）。正确修法需「**键名等价 + 值形态**」双判据，**并同时**给 `token_budget` 这类**量词后缀**（`_budget`/`_level`/`_count`/`_holder`）加豁免 —— 属 **M2**（cassette / 能力层会带 `headers.*`）。**不得**把族简单扩为「任一 token 命中」：那会重新引入 `token_budget` 类误伤 |

---

## 5. 交付面新增的**加法**行为（不放松任何检查；请 architect / PM 知悉）

| # | 加法 | 理由 | 证据 |
|---|---|---|---|
| A1 | `run --ticks N`（默认 300） | 冻结命令面**没有**终止上界，而 AC-M1-3 要求该命令自行 exit 0（设计 §4.6 上抛项 3） | `03` §3 |
| A2 | `verify --expected-hash` 链外锚点（三态、fail-closed） | 预审 C1 | `03` §3d |
| A3 | `kernel/conftest.py`（裸 `pytest` 可用） | 预审 C2 | `03` §4/§5 |
| A4 | `--pack` 的**路径回退**：① cwd 相对；② `<v0_skeleton>/<value>` | 冻结命令在 workdir = `.../v0_skeleton/kernel` 下写 `--pack districts/xingfu-xiaoqu`，而 pack 实际在 `.../v0_skeleton/districts/`。**不复制内容包、不改冻结文件**的前提下用只读回退接起来；解析到的目录仍要过**完整** `load_pack` 校验链 | `03` §3/§4（命令原样可跑） |
| A5 | `deephealing_kernel/__main__.py` | 冻结命令面全部以 `python -m deephealing_kernel` 调用，包内必须有该文件 | `03` §3 |
| A6 | `run`/`replay` 对**非空事件日志** fail-closed（`E_EVENTS_EXISTS`） | append-only 证据不允许静默追加（会产生第二条 `seq=0` 链）也不允许静默截断；重跑须显式清空输出目录 | `tests/test_e2e_run_verify.py::test_run_refuses_nonempty_event_log`；`spikes/ac3-forge/reset_out.py` |
| A7 | 新增 `spikes/s5-latency-calibration/ENVIRONMENT-CLASS.frozen.md`（测量前声明环境可用性判据） | 使 `derive` 在污染分布下**有依据**地 fail-closed，而不是靠事后判断（设计 §4.9「工具链必须可自证」） | §1 AC-M1-6；`registry` 登记其 sha256 与 mtime |
| A8 | `compare_checkpoints` 协议的 `side=` 扩展 | 定位缺失发生在哪一侧；前缀与字段名逐字未改 | §3 M7 |
| A9 | `to_state()` 额外导出 `tags` | `tags` 是 `world.schema.json` 允许的 entity 键但不在冻结骨架的 `COMPONENTS` 元组里；不导出即静默丢弃内容包数据 | §2 缺陷 1 |
| A10 | **修复轮 A1**：`verify` 产出重放事件流并与日志逐条比对语义序列 | 关闭「中段删/改事件 + 重算整链」这一类**自洽**伪造（首轮 `verify` 对它 exit 0）。**不改**任何既有参数语义；比对豁免面只有 `checkpoint_path`（运行期定位符，与「世界语义」无关，由用例钉死） | §1 AC-M1-3；`03` §3f；`tests/test_e2e_run_verify.py::test_forged_log_matrix` |
| A11 | **修复轮 C6**：`--pack` 回退命中时打印 `note: --pack resolved via fallback to <abs>` | 回退是加法（A4），但**静默**回退会让「路径写错」看起来像成功；现在显式可见 | `03` §4b；`tests/test_e2e_run_verify.py::test_pack_fallback_note_is_printed`（含「直接命中不打印」的反向对照） |
| A12 | **修复轮 C7**：`run` 的 fail-closed 从「日志非空」扩到「日志非空 **或** 检查点目录已有文件」（`replay` 侧对称） | 只删日志、留旧检查点、再用更少 `--ticks` 重跑，原先 exit 0 后由 `verify` 假红；现在直接拒绝并写明「日志与检查点都必须显式清空」 | `03` §3g；`tests/test_e2e_run_verify.py::test_run_refuses_stale_checkpoints_without_log`（含「整树清空后 exit 0」反向对照） |
| A13 | **修复轮 C9**：`replay` 的检查点落 `<out>/checkpoints/`；`snapshot.taken.payload.checkpoint_path` 的语义钉死为「以**日志目录**为基准的实际写入路径」 | 使该字段在 run 与 replay **两侧产物里都指向真实存在的文件**；且因**不含目录前缀**，run/replay/verify 三条路径的链尾逐 tick 一致（A1 的事件流比对依赖这一点） | `03` §3；`tests/test_events_snapshot_invariants.py::test_checkpoint_path_points_at_real_file_relative_to_log_dir` |
| A14 | **修复轮 C4**：`calibrate_latency check` 新增 `structural_collapse` 报告（`adopted_ms == strict_candidate_ms`） | 「松一档」退化时必须**显式**说出来，否则判据③的失败会被误读成单纯的数值噪声 | `03` §6c；`tests/test_calibrate_latency.py::test_check_reports_adopted_equals_strict_collapse` |

> 以上均为**加法**：未改任何既有参数语义、未放松任何检查、未扩大 `GENERATED_PATTERNS`、未改任何冻结文件。

---

## 6. 显式声明：W9 的 duckdb 查询与观察模式指标面板**仍未做**

本轮实现的是 **W2 冻结 CLI 面**（`replay --out` 产出 `checkpoints/<tick>.json`）。
**W9（观测层）的 duckdb 查询与观察模式指标面板本轮仍未做**：
`02_source/v0_skeleton/tools/duckdb_queries.sql` 与 `web/src/ui/observe/panel.ts` 保持原样未改，
本机亦未安装 duckdb、未执行任何 duckdb 查询。
`checkpoints/<tick>.json` 被做绿**不等于** W9 完成（预审 M9/U6）。

---

## 7. 已知风险、GAP 与上抛项

| # | 类型 | 内容 | 归属 |
|---|---|---|---|
| GAP-1 | 范围冲突 | REQ §3 交付物表写「现有 **4 个**测试文件从收集性检查变为真绿」，但 REQ §2/§6 明确 **W3/W7 不在本轮**。本轮实现 AC 覆盖的两份 + 新增 3 份；`tests/test_capability_registry.py`（6 条，W3）与 `tests/test_observe_mode_readonly.py`（4 条，W7）**保持 `pytest.skip`**，未为了让它们变绿而实现 W3/W7 | **PM 裁决**（设计 §9 上抛项 1） |
| GAP-2 | AC-M1-6 判据③④ | 见 §1：**判据③ 不可重复**——同一份 `dist`、同一批声明值、同为 `--runs 10`，三次测量得 adopted `0.50`（越界 ✗）/ `0.20` ✓ / `0.10` ✓（区间上界 0.30 被跨过）。**修复轮 C4 修订根因**：`check` 显式报出 `adopted_ms == strict_candidate_ms`（`1300 == 1300`，**7/7 全部塌缩**）⇒ 判据③的「松一档」前提**结构上不成立**（两行是同一个值），不只是通道抖动。判据③ **GAP**、判据④ GAP（塌缩 fail-closed）。**未**重标、**未**调参、**未**重采样 `dist` | 需**平稳网络窗口**重采样（Q1）**+** 推导规则的 offset 窗口/区间口径复核（**PM/需求侧裁决**，属冻结物变更）；另请裁决 A14（塌缩是否应改退出码） |
| GAP-3 | 契约矛盾（未改冻结文件） | `world.seed.json` 含 `weather`，`world.schema.json` 顶层 `additionalProperties:false` 不含 `weather`，而 `district.pack.spec.md` §2 第 4 步与 `world.schema.json` 自己的 `description` 都要求「world.seed.json 过 world.schema.json」——**契约内部自相矛盾**。本轮按设计 §4.4 双口径执行（pack 文件过 `$defs/worldSeed`；内核 state 过 `world.schema.json`；seed 投影另过强口径），**未**改任一冻结文件 | **PM 裁决修订方向**（设计 §9 上抛项 2） |
| GAP-4 | 跨里程碑语义漂移 | `--ticks` 默认 300 使 `08` §1 判据 6 的冻结命令语义变为「跑 30 秒世界时间后自行退出」；M3 必须显式带 `--ticks` 或新增 `--until-forever` | PM 知悉（设计 §9 上抛项 6） |
| GAP-5 | 工具缺陷（non_block） | `tools/pack_sign.py` 只按后缀名判可执行文件，改名后的可执行内容可被签名、再由 `validate` 拒收（L3）。本轮**不改**（属「只许加强」面且非 AC 所需） | PM 决定是否纳入后续轮次 |
| GAP-6 | 流程缺陷（non_block） | `role-task` 是一任务一账本（无 per-role 步骤表），任一角色 `done` 会把 architect 的整条流水线标为完成。本轮 artisan 只用 `add`/`step`/`progress`，**未**调用 `done` | PM / 工具侧修复 |
| RISK-1 | 远端通道不平稳 | 同一 1300 ms 声明值在相邻两批各 10 次调用里测得 0/10 与 5/10 降级（含 3 次卡在 1300 ms 上界的 `TimeoutError`）⇒ W0e 的结论对**测量窗口**敏感。`ENVIRONMENT-CLASS.frozen.md` 的判据只拦「分布形态污染」，拦不住「分钟级抖动」 | 记录为**未加固面**（U4 的延伸） |
| RISK-2 | 内核 tick 内语义 | 「10 Hz / dt=100ms」是**语义**，`run` 不节流（U3）。**事件日志规模不是线性增长而是「饱和」（修复轮 2 / G3 / Raven R22.1）**：实测 300 tick → **925**、3000 tick → **2633**、10000 tick → **2793** 事件（NPC 到达目标后不再产事件）；要造大日志必须调 `--snapshot-every`（Raven 用 `1` 造出 32663 事件）。**`verify` 的资源量级（修复轮 2 / G2 / Raven R20）**：`verify` 峰值 ≈ **60 KB/事件**（32663 事件 → **2.05 GB / 31.9 s**），同配置 `run` ≈ **1 KB/事件**（32 MB / 12.4 s）；A1 事件流比对增量 ≈ **+11%**（+210 MB / +3.8 s）。**本轮验收规模 925 事件（AC-M1-3）即本轮上限**；M2 需改流式比对（或加 `--max-events` fail-closed） | 记录（U3 / U16） |
| RISK-3 | `E_EVENTS_EXISTS` 的可用性代价 | 冻结的 AC-M1-3 命令在**已存在** `out/m1-ac3/e.jsonl` 时会 exit 1（fail-closed）。复跑必须先清空 `out/m1-ac3*`（`spikes/ac3-forge/reset_out.py`）。若验收方直接重复跑同一条命令，会看到 exit 1 —— 这是**有意的**，不是回归。**修复轮 C7 补充**：触发条件**不再限于日志**——只要 `checkpoints/` 里有旧文件（哪怕日志已被删掉）也同样拒绝，提示写明「日志与检查点都必须显式清空」；`replay` 侧对称（`<out>/replay.jsonl` 或 `<out>/checkpoints/` 非空） | 请 architect/Sentinel 知悉（A6 / A12） |
| GAP-7 | 判据残余（**未闭合**，如实上报） | **A1 的事件流比对**能判红「中段删/改事件 + 重算整链」这类自洽伪造（4/5 类），但**不能**判红「截断 + 改写 `plan_ticks` + 重算整链 + 同步改检查点」——该伪造产出的是真日志的**自洽前缀**，重放会**合法地**复现它，因此在「无外部锚点」的前提下**结构上不可见**。它**只能**由链外锚点 `--expected-hash` 关闭（已实测 exit 1 `anchor_mismatch`）。用例把这一残余**固化成断言**（`truncate_rechain` 分支断言「无锚点 exit 0 / 传自身链尾 exit 0 / 传原始链尾 exit≠0」），防止后续被误读为「A1 已完全关闭 C1」 | **architect / PM 知悉**：这是设计 §4.6 与 `cassette.format.md` `FROZEN-CASSETTE-INTEGRITY-1` 已承认的强度边界，不是本轮遗漏 |

---

## 8. 证据文件清单（绝对路径）

| 文件 | 内容 |
|---|---|
| `{ws}/03_artisan_self_test.log` | 全部 AC 命令 + workdir + exit + 关键输出（§0~§10） |
| `{ws}/06_v0_m1_self_test.md` | 本文件 |
| `{ws}/spikes/red/RED.log` | RED 证据（实现前桩上的失败） |
| `{ws}/spikes/build_red_sandbox.py` | RED 沙箱构建脚本 |
| `{ws}/spikes/kernel-baseline/{BASELINE.txt,capture_baseline.py,deephealing_kernel/**}` | AC-M1-5 实现前基线锚点（24 文件 / `058e9a54…`） |
| `{ws}/spikes/ac3-forge/{forge_log.py,forge_matrix.py,tamper_payload.py,tamper_quantile.py,truncate_tail.py,read_hash.py,reset_out.py}` | AC-M1-3 负例夹具 + **修复轮 A1 的 5 类自洽伪造矩阵** + **C5 的四分位篡改夹具**（独立脚本） |
| `{ws}/spikes/run_ac_evidence.sh`、`{ws}/spikes/clean_residue.py`、`{ws}/spikes/make_delivery_manifest.py` | 证据生成 / 残渣清理 / 交付清单（修复轮 D3：清单**不含**正在被追加的 `03_artisan_self_test.log`） |
| `{ws}/spikes/s5-latency-calibration/**` | W0e 三份冻结物 + registry + 分布/标定/降级率 + 控制台日志 |
| `{ws}/spikes/debug_leak{,2}.py` | POC 探索：wall-clock 注入的时钟粒度陷阱（负例不得退化成常量） |
| `{ws}/out/m1-ac3/**`、`out/m1-ac3-{trunc,tamper,forged}/**`、`out/m1-ac3-forged-matrix/<mode>/**`、`out/m1-c7/**`、`out/m1-claim/**` | AC-M1-3 端到端产物、三类负例产物、**修复轮 A1 伪造矩阵产物**、**C7 场景产物**、**C5 篡改副本** |
| `{ws}/V0_M1.sha256` | 交付时全量清单（`SEED.sha256` 未改写；**修复轮重取**，自校验见 `03` §11） |

---

## 9. 自审（正确性 / 兼容性 / 安全 / 错误路径 / 并发与资源边界）

- **正确性**：三哈希语义逐条对齐 `snapshot.schema.json`（ECH-1 检查点=含快照事件的链尾；ECH-2 事件 payload=追加前链尾；
  ECH-3 `hash_object(payload.rng_digests) == rng_state_digest`），并有独立完整性断言兜「共有错误」。
- **兼容性**：全部改动在 `kernel/**` 写集内；冻结签名（`take_snapshot(dict,…)`、`compare_checkpoints -> list[str]`、
  `redact(payload, redact_fields)`、`World.__init__(self)`、`EventLog.__init__(path)`）**保持可调用**，
  新参数一律**可选**且带默认值；`canonical_json` 仍只有一份实现（内核按文件路径加载 + import 期断言）。
- **安全**：凭据只从环境变量读、**不落盘**；标定工具**不写**任何 HTTP transcript；事件日志追加前脱敏（点分路径 + glob 主判据）；
  pack 路径穿越（`..` / 绝对路径）与可执行内容（后缀 + 内容魔数双判据）均 fail-closed。
- **错误路径**：链断 / hash 不符 / 截断 / 锚点不符 / 非规范检查点名 / 同 tick 重复 / 检查点集合缺失 / 包签名不符 /
  schema 不符 / 非空日志重跑 —— 全部 fail-closed 且打印可定位信息（首个分歧 tick / 具体文件 / 具体字段）。
- **并发与资源边界**：`run` 单进程单线程；tick 内无 wall-clock / 无网络 / 无 `random` / 无 `os.urandom`；
  `query()` 显式按 id 升序（禁 dict/set 迭代顺序）；`StreamRng` 按子系统分流（新增 stream 不扰动既有序列）；
  标定工具对远端调用设 `--timeout-ms` 上界并对失败样本单独记账（不静默丢弃）。
- **本轮**未**做**：`registry.py` / `providers/**` / `budget.py` / `rules/**` / `memory/**`（W3/W4/W5）、
  `session/**` / `web/**`（W7/W8）、W9 观测层 —— 均保持原状（桩/未改）。
- **修复轮追加自审**：
  - **正确性**：`trauma_flags` 的排序键改为**契约序列化本身**（天然全序）⇒ 同一逻辑状态的
    `state_hash` 不再随输入顺序漂移（B1）；`checkpoint_path` 的语义被**钉死**为「以日志目录为基准的
    实际写入路径」，并因此在 run/replay/verify 三条路径上**不含目录**⇒ 链尾可比（C9，这一条是 A1 的前提）。
  - **兼容性**：修复轮**未改**任何冻结签名；`WorldKernel.__init__` 的**新增参数尝试被撤销**
    （曾为 C9 加 `checkpoint_path_fn`，实测会破坏 run↔replay 链尾一致 ⇒ 改为「常量相对路径 + cli 侧
    把 replay 的检查点写进 `<out>/checkpoints/`」，改动面更小）。`redact()` / `compare_checkpoints` /
    `take_snapshot` / `EventLog.__init__` 签名逐字未动。
  - **安全**：pack 读取路径新增**符号链接越界**守卫（B3，`symlink escape` ⇒ `E_PACK_INVALID`）；
    脱敏的补充判据从**子串包含**收紧为**键名整词等价族**（B2）⇒ 合法键名不再被误脱敏、真密钥仍命中。
  - **错误路径**：`run`/`replay` 的 fail-closed 从「日志非空」扩到「日志**或**检查点非空」（C7）；
    `--pack` 回退改为**显式打印**（C6）；`check` 新增 `E_CALIBRATION_STRUCTURAL`（C4）。
  - **并发与资源边界**：A1 的重放事件流写进 `tempfile.TemporaryDirectory`（不污染交付树、不落 `out/`）；
    比对豁免面被钉成**恰好** `{checkpoint_path}` 并由用例断言（防静默扩大豁免）；`verify` 的时间/空间
    开销从「只推进内核」变为「推进内核 + 落一条临时日志」，仍与 `--ticks` 线性（300 tick ≈ 925 事件）。

---

## 10. 修复轮（iteration 2）逐条闭环 —— A1~A2 / B1~B5 / C1~C10 / D1~D3

> 输入：`04_sentinel_test_report.md`（Sentinel 独立门禁）+ `05_raven_risk_report.md`（Raven 风险推演）
> + 修复任务书 `.task-artisan-fix.md`。**未改** `04`/`05` 任一字节；**未碰**任何冻结文件。
> 每条格式：**做什么 → 命令 + exit → 产物路径**；未闭合项照实标。

### 10.1 A 类（必须闭合）

| 项 | 做了什么 | 命令 / exit | 产物 |
|---|---|---|---|
| **A1** | `verify` 新增**事件流比对**：用同一 pack/seed 重放并**产出事件流**，与日志逐条比 `(tick, type, actor)` + payload（不比 `seq`/`prev_hash`/`hash`），任一分歧 ⇒ fail-closed 且打印首个分歧 tick；豁免面钉死为 `{checkpoint_path}` | `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_e2e_run_verify.py -q -p no:cacheprovider` → exit **0**（11 passed）；`03` §3f 逐类 CLI 复跑 | `kernel/deephealing_kernel/cli.py::_compare_event_streams`、`tests/test_e2e_run_verify.py::test_forged_log_matrix`、`spikes/ac3-forge/forge_matrix.py`、`out/m1-ac3-forged-matrix/**` |
| **A1 残余** | `truncate_rechain`（截断 + 改 `plan_ticks` + 重算整链 + 同步改检查点）**不被**事件流比对判红（自洽前缀，结构上不可见），**只能**由 `--expected-hash` 关闭 | 用例内断言三态：无锚点 exit **0** / 传自身链尾 exit **0** / 传原始链尾 exit **≠0**（`anchor_mismatch`）；`03` §3f 同 | 见 §7 **GAP-7**（如实上报，未修饰） |
| **A2** | `verify` 的 `claim_boundary` 按新强度改写（链自洽 + 检查点与重放一致 + **事件流与重放一致**），并明确「**不**代表未被篡改；抗改写必须 `--expected-hash`」；`cli.py` docstring 同步 | `tests/test_e2e_run_verify.py::test_claim_boundary_is_rewritten_for_event_stream_strength` → exit **0**；`03` §3 | `cli.py`（`CLAIM_BOUNDARY`）、`06` §1 AC-M1-3 |

### 10.2 B 类（正确性缺陷）

| 项 | 根因 | 改动 | 证据 |
|---|---|---|---|
| **B1** `trauma_flags` 排序非全序 | 排序键 `(id, since_tick, severity)` 在「三者相同、仅 `healed_tick` 不同」时**平局**，`sorted` 稳定 ⇒ 平局顺序由**输入顺序**决定 ⇒ 同一逻辑状态两种 `state_hash` | `ecs._normalize_component` 的 `trauma_flags` 分支改用 `key=canonical_json(item)`（契约序列化本身，天然全序） | `tests/test_events_snapshot_invariants.py::test_trauma_flags_total_order_is_input_order_independent` → exit **0**；**反向对照**：在**原始输入**上用旧键 ⇒ 两种顺序（`[200, None]` vs `[None, 200]`），用新键 ⇒ 收敛为同一结果 |
| **B2** 补充脱敏判据是**子串包含** | `("authorization","api_key","token")` 子串匹配会把合法键名 `token_budget` / `authorization_level` / `api_keys_count` / `token-holder` 误判成密钥字段并**整体脱敏**（静默破坏事件语义） | 改为**键名整词等价族**：小写 + 按 `_`/`-`/空白切词后**拼接**，与 `{authorization, apikey, token, accesstoken, secret}` 精确相等才命中；`redact_fields`（点分路径 + glob）仍是**主判据** | `tests/…::test_supplementary_redaction_uses_key_equivalence_not_substring` → exit **0**；**反向对照**：内置子串实现 ⇒ 四个合法键名必被误判；端到端 `redact(doc, [])` 断言合法键名原样保留、`token`/`api_key` 仍脱敏 |
| **B3** 符号链接可越出包外 | `rglob("*") + read_bytes` **静默跟随**符号链接 ⇒ 包外文件被当成包内容读入（`pack.sig` 按解析后内容核对，签名挡不住） | 新增 `pack._assert_within_root(path, root)`（解析后必须仍在 pack 根内，否则 `symlink escape` ⇒ `E_PACK_INVALID`），接到 `verify_signature` 的 rglob 与 `load_pack` 的 4 处读取点 | `tests/test_pack_validate.py::test_pack_rejects_symlink_escape` → exit **0**；**反向对照**：换成包内目标的真文件后必须仍 exit 0（不是「有链接就红」） |
| **B4** `pack.py` docstring 谎报校验链 | 原文写「各数据文件 schema」，实际 `district.pack.schema.json` 只有 3 个 `$defs`（`packManifest`/`packSig`/`worldSeed`），五层数据面**没有** schema，只做 JSON 可解析性检查 | docstring 第 4 步改为准确措辞（「数据文件校验」+ 显式写明五层无 schema、只做可解析性检查） | `tests/test_pack_validate.py::test_pack_docstring_matches_implementation` → exit **0**（断言 `$defs` **恰好**三个 + `_validate_schema` 调用点计数） |
| **B5** `rng.py` docstring 过宽 | 原文写「新增子系统不得扰动既有 stream 序列」，易被读成「加子系统不改历史哈希」 | 收窄为「**既有 stream 的序列**不被扰动（这是『加一个 NPC / 加一个街区不改 **`state_hash`**』的前提）」，并写明 `rng_state_digest` **会**因新增 stream 而变 | `rng.py` docstring + `06` §4 U 面；断言仍在 `test_determinism_replay.py::test_new_subsystem_does_not_perturb_existing_streams`（既有 stream 逐位不变，**不**声称 `rng_state_digest` 不变） |

### 10.3 C 类（判据强度 / 归因）

| 项 | 做了什么 | 命令 / exit | 产物 |
|---|---|---|---|
| **C1** | 请求体面**修正口径**：不是空集，而是「**54 次真实远端调用**（24 + 3×10）、**无落盘请求体**」；补**带反向对照**的扫描判据（探针写进真实扫描面 ⇒ 命中 ≥1 ⇒ 移除后 0） | `tests/test_evidence_scan.py` → exit **0**；`03` §7 请求体面①②③（真实面 0 / 探针 ≥1 / 移除后 0） | `tests/test_evidence_scan.py`、`06` §1 AC-M1-7(b) |
| **C2** | 路径逃逸用例的**归因**收紧：分两段断言——(a) 端到端拒绝**归因到字段** `entrypoints/assets_manifest`；(b) **同一恶意值直达** `_guard_relpath`，断言原因字符串逐字为 `parent traversal not allowed: …` / `absolute path not allowed: …`；并新增**反向对照**（把守卫换成恒 `None` ⇒ 判据必须炸）。**同时声明**：冻结 schema 的 `const` 让该输入在 schema 层就被拦下，守卫对「已过 schema 的输入」不可达（Sentinel Bug#3） | `tests/test_pack_validate.py::{test_pack_rejects_path_escape,test_guard_relpath_negative_control}` → exit **0** | 同上 |
| **C3** | AC-M1-5 判据① 的 `before` 改为**同源隔离副本**（两棵真实树之间的差集），不再「实树 vs 副本」；`06` 写明口径声明 | `tests/test_kernel_digest.py::test_kernel_digest_diff_criterion` → exit **0**（含两条强制负例） | `06` §1 AC-M1-5 |
| **C4** | `check` 新增 `structural_collapse` 报告（`adopted_ms == strict_candidate_ms` 的能力清单），与普通区间越界**分开**（塌缩条目**不进** `problems`），且塌缩本身也使 exit 非 0（前提不成立即 fail-closed）。**前缀偏离声明**：任务书字面写 `E_CALIBRATION: adopted == strict for <caps> …`，本实现用 **`E_CALIBRATION_STRUCTURAL:`** 前缀（正文逐字一致）—— 理由：`E_CALIBRATION:` 已被「区间越界」占用，同前缀就**不满足**「分开报告」这一条 | 真实标定：`check` 输出 `structural_collapse.adopted_equals_strict=true`、7 个能力全列 + `E_CALIBRATION_STRUCTURAL: adopted == strict for […] ⇒ 判据③的「松一档」前提不成立`；`03` §6c。**副产物（重要）**：例行复跑把 `degrade` 重测了两遍，adopted 行在三次相邻测量里为 `0.50`（越界）/ `0.20` / `0.10` ⇒ 判据③**不可重复**，见 §1 与 GAP-2（**三次结果全部列出，不挑有利的那次**） | `tools/calibrate_latency.py::cmd_check`、`tests/test_calibrate_latency.py::test_check_reports_adopted_equals_strict_collapse` |
| **C5** | `check` 的独立重算从 p90 扩到 **p50/p90/p95/p99/max 五量逐个比对** | `tests/…::test_check_recomputes_all_five_quantiles` → exit **0**；**反向对照**：只改 `p90_ms`（或 `max_ms`）1 ms ⇒ `check` 非 0 并归因到该量（`03` §6c） | 同上 |
| **C6** | `--pack` 回退命中时打印 `note: --pack resolved via fallback to <abs>` | `tests/test_e2e_run_verify.py::test_pack_fallback_note_is_printed` → exit **0**（含「直接命中不打印」对照）；`03` §4b | `cli.resolve_pack_dir` |
| **C7** | `run` 的 fail-closed 改为对称：**非空日志 或 已有检查点目录（含文件）**都拒绝，提示写明「日志与检查点都必须显式清空」；`replay` 侧对称 | `tests/…::test_run_refuses_stale_checkpoints_without_log` → exit **0**；`03` §3g（删日志留检查点 ⇒ exit≠0；整树清空 ⇒ exit 0） | `cli._refuse_existing_run_outputs` / `_refuse_existing_replay_outputs` |
| **C8** | 未加固面从 U1~U8 扩到 **U1~U14**（新增内容层零消费、四层无 schema、符号链接残余、无并发/TOCTOU、单街区、cassette 完整性） | 文档条目，证据见 §4 各行的文件/命令 | `06` §4 |
| **C9** | `snapshot.taken.payload.checkpoint_path` 的语义钉死为「以**日志目录**为基准的实际写入路径」；`replay` 的检查点改落 `<out>/checkpoints/` ⇒ 该字段在 run 与 replay 两侧**都指向真实文件**；`check_checkpoint_integrity` docstring 写明「JSON 写读往返不变」的前提 + 加**显式**守卫（违反时报 `json_roundtrip_premise_violated`） | `tests/test_events_snapshot_invariants.py::{test_checkpoint_path_points_at_real_file_relative_to_log_dir,test_checkpoint_integrity_guards_json_roundtrip_premise}` → exit **0**；`03` §3 列出 `out/m1-ac3/replay/checkpoints/` | `tick.py`、`cli.cmd_replay`、`snapshot.check_checkpoint_integrity` |
| **C10** | canonical JSON 的「跨语言逐位一致」判据改为**独立序列化对照**（测试内手写编码器，不 import 被测实现），并加**反向对照**：把内核 canonical 换成「分隔符带空格」变体（保持 `sort_keys=True`）在子进程里跑同一判据 ⇒ 必须非 0 | `tests/test_canonical_contract.py` → exit **0**（含子进程反向对照） | `tests/test_canonical_contract.py`、`06` §3 M3 行 |

### 10.4 D 类（诚实性与一致性）

| 项 | 做了什么 | 证据 |
|---|---|---|
| **D1** | `06` §0/§1 措辞改为「本轮为修复轮（iteration 2）」+ 写集/不做项声明；§1 明示是**修复后**的最终判定 | 本文件头部与 §1 引言 |
| **D2** | RED 计数三处对齐：`06` §2 表格 `24 failed / 11 passed / 1 error`、`spikes/red/RED.log` 末行、末行上方注释（原写「8 passed」已改为「11 passed」并加口径说明）；账本侧另追加一条更正流水 | `06` §2；`spikes/red/RED.log` 第 5~8 行 |
| **D3** | 重取 `V0_M1.sha256` 并自校验；**修复**首轮 exit 1 的成因——清单原先包含**正在被本脚本追加**的 `03_artisan_self_test.log`，生成当刻即过期；现改为**不纳入**该日志（日志自身哈希由日志末段记录），使 `shasum -c` 稳定通过 | `03` §11 / §12：`wrote … entries=642`、`shasum -a 256 -c` **非 OK 行计数 = 0**、条目数 **642**、清单内残渣条目 **0**、日志自身哈希 `005d537d…`（截至该行） |

### 10.5 修复轮改动文件清单（`02_source` 交付面）

**修改**：`deephealing_kernel/{cli,tick,ecs,events,pack,rng,snapshot}.py`、`tools/calibrate_latency.py`、
`tests/{test_determinism_replay,test_e2e_run_verify,test_pack_validate,test_kernel_digest,test_events_snapshot_invariants,test_calibrate_latency}.py`、
`manifest.txt`。

**新增**：`tests/test_canonical_contract.py`、`tests/test_evidence_scan.py`（两者均已登记 `manifest.txt`）。

**测试规模**：修复轮前 `42 passed / 10 skipped` → 修复轮后 **`62 passed / 10 skipped`**（新增 20 条判据，
10 skipped 仍是 W3/W7 的**有意保留**，见 §7 GAP-1）。

**冻结面零改动复检**：9 份 `*.schema.json` + `verify_specs.sh` + `verify_pack.py` 的 sha256 见 `03` §9；
`districts/**` 未改（`pack.sig` 未重签）；`{session,web}/**` 未动。

---

## 11. 修复轮 2（iteration 3，最终有界轮）逐条闭环 —— F1~F7 / G1~G8

> 输入：`04_sentinel_test_report.md` 的「修复轮复验（iteration 2）」节（Bug#9~#15）+
> `05_raven_risk_report.md` 的「修复轮复验（iteration 2）」节（R15~R23 + 「是否引入新 CRITICAL」节）。
> **未改** `01`/`04`/`05` 任一字节；**未碰**任何冻结文件（含 `pack_sign.py`、`verify_pack.py`）。
> 每条格式：**做什么 → 命令 + exit → 产物路径**。

### 11.0 本轮的过程事实（必须先说清楚）

1. **本轮的第一次执行被 provider HTTP 429 中断**（进程死亡，未收尾）。恢复后**重跑了全部证据**，
   下面所有 exit 都是**恢复后重新实测**的值，不是中断前的残留。
2. **恢复过程中自己发现并修掉了两个「假绿」缺陷**（都属本轮工具/夹具面，不是产品缺陷）：
   - **`reset_out.py` 忽略参数**：证据脚本 §3g 写的 `reset_out.py m1-c7` 会**连带删掉
     `out/m1b/**`**，把 §3i/§3j/§3k（F3/F4/F6）的夹具产物在脚本后半段悄悄抹掉 ——
     日志里 exit 仍在，但盘上产物消失，复核者无法复现。已改为**按参数过滤**（无参数 = 全部），
     并在 `03` §11b 加了**夹具存活自证**（7/7 OK）。
   - **`forge_matrix.py` 对「无快照事件」的日志崩溃**：N9 用的 `--snapshot-every 0` 日志没有任何
     `snapshot.taken`，`drop_snapshot_event` / `locator_last_snapshot` 抛 `StopIteration` ⇒ 脚本在
     写盘前就死，**一个产物都不产出**。而证据脚本随后仍对**不存在的路径**跑 `verify`，拿到
     `exit 1`（`E_EVENT_CHAIN: event log not found`）—— **这是假绿**：判红的原因不是篡改被抓，
     而是文件根本不存在。已改为**不适用即显式 `skipped`**，并在 §3h 加了**反假绿前置断言**
     （`test -f <伪造日志>` 必须 exit 0）。
   - 修复后 N9 的**真实**归因是
     `event_stream:payload_diff:index=46 tick=10 type=npc.action field=checkpoint_path logged='../../outside/SMUGGLED-MID.json' replayed=None`。
3. 写集与上一轮相同；真实仓库 `b421cb01…` + porcelain **0 行**（零改动）。

### 11.1 F 类（代码面，逐条实测关闭判据）

| # | 做什么（根因） | 关闭判据实测（命令 / exit / 关键输出） | 产物 |
|---|---|---|---|
| **F1** | `cmd_registry` 幂等（Sentinel Bug#9）：原每次写 `registry_written_at: time.strftime(...)` ⇒ 跑一次就把 `V0_M1.sha256` 自校验变成「641 OK / 1 FAILED」。现改为「**内容字段全同则沿用原时刻且不写盘**」 | `cd {ws}/02_source/v0_skeleton/kernel && python3 tools/calibrate_latency.py registry` ×2 → 各 exit **0**，两次均输出 `"unchanged": true`、`"registry_written_at": "2026-09-22T08:43:38+0800"`；`spikes/s5-latency-calibration/calibration.registry.json` 的 sha256 **三次一致** = `9d440b1696b541a8f59ae6c727818b96065760ae26cd55f5d395700d95dba1f6`；`shasum -a 256 -c V0_M1.sha256` 中该文件行 **OK** | `03` §3l；`tools/calibrate_latency.py::cmd_registry`；`tests/test_calibrate_latency.py::{test_registry_is_idempotent,test_registry_still_rewrites_when_content_changes}`（含「内容真变必须重写」的反向对照 + `finally` 逐字节复原夹具） |
| **F2** | **豁免面收紧为空集**（Raven R15）：`EVENT_STREAM_LOCATOR_KEYS = frozenset()`。前提是该字段在 run/replay/verify 三条路径**取值恒定**（`tick._take_and_write_checkpoint` 恒写 `checkpoints/{tick:06d}.json`，不含目录前缀） | **N8**（只改末条 `snapshot.taken.payload.checkpoint_path` + 重算全链 + 同步改检查点）⇒ exit **1**，归因 `event_stream:payload_diff:index=924 tick=300 type=snapshot.taken field=checkpoint_path logged='../../outside/SMUGGLED-LAST.json' replayed='checkpoints/000300.json'`（修复轮 1 时该构造 exit 0）；**N9**（`--snapshot-every 0` 时改中段 `npc.action` 的该字段）⇒ exit **1**，归因同上（`replayed=None`）；**防恒红**：干净日志 exit **0**、干净的无快照日志 exit **0**；`claim_boundary` 已改写为「payload 比对**无豁免键**」 | `03` §3h；`cli.EVENT_STREAM_LOCATOR_KEYS` / `cli.CLAIM_BOUNDARY`；`tests/test_e2e_run_verify.py::{test_event_stream_comparison_excludes_nothing,test_locator_key_tampering_is_caught}`（N8/N9 双侧 + 防恒红）；夹具 `spikes/ac3-forge/forge_matrix.py` 的 `locator_last_snapshot` / `locator_mid_npc_action` 模式 |
| **F3** | `_refuse_existing_run_outputs` 的 checkpoints 判定 `is_dir()` → **`exists()`**（Raven R23.2）：该路径是普通文件时原先不触发 fail-closed，跑到第一个快照 tick 时抛**未捕获** `FileExistsError`（裸 traceback）并留下**半截日志** | `printf 'not a directory\n' > out/m1b/f3/checkpoints` 后 `run … --ticks 120` ⇒ exit **1**，提示含 `E_EVENTS_EXISTS: refusing to run: … exists but is not a directory`；`Traceback` 计数 **0**；产物目录只有 blocker 文件（**无半截 `e.jsonl`**）；**反向对照**：删掉该文件后同一条命令 exit **0** | `03` §3i；`cli._refuse_existing_run_outputs`；`tests/test_e2e_run_verify.py::test_run_refuses_checkpoints_path_that_is_not_a_directory` |
| **F4** | `pack.sig` 读点纳入符号链接守卫（Raven R17）：`verify_signature` 在 `sig_path.read_text()` **前**调 `_assert_within_root(sig_path, root)` —— 原先是**唯一**未被守卫的读取点 | 把 `pack.sig` 换成指向包外的符号链接 ⇒ `validate` exit **1**，`E_PACK_INVALID: symlink_escape: … pack.sig resolves to …`（修复前 OK）；**反向对照**：换回包内真文件 ⇒ exit **0** | `03` §3j；`pack.py::verify_signature`；`tests/test_pack_validate.py::test_pack_rejects_symlink_pack_sig` |
| **F5** | `verify_signature()` 返回类型口径一致（Raven R19）：**取「返回」** —— 逃逸作为一条 problem **返回**（`symlink_escape: …`），不再抛 `PackInvalid` | 符号链接逃逸时 `verify_signature(pack)` 返回 **非空 `list`**（`type = list`，不抛）；`load_pack(pack)` 仍抛 `PackInvalid`（fail-closed 未放松）；正常 pack ⇒ `verify_signature(PACK_DIR) == []`（既有列表语义断言仍绿） | `03` §3j；`pack.py::verify_signature` docstring；`tests/test_pack_validate.py::test_verify_signature_returns_list_never_raises` |
| **F6** | `verify` 的 `problems` **按文本去重**（Sentinel Bug#15）：`_load_checkpoint_dir` 被三个调用点各自调用 ⇒ 集合级错误出现 3 次 | `run --ticks 6 --snapshot-every 3` ⇒ 复制 `000006.json` 为 `6.json` ⇒ `verify` exit **1**，`problems` = `["checkpoint_set_error:non_canonical_filename:6.json", "checkpoint_set_error:duplicate_tick:6 (000006.json, 6.json)"]` —— 各 **1 次**（修复前各 3 次），且无逐字重复条目 | `03` §3k；`cli.cmd_verify.note`（去重只折叠**逐字相同**条目，不同 tick/文件的诊断仍各自保留）；`tests/test_e2e_run_verify.py::test_verify_problems_are_deduplicated` |
| **F7** | 独立序列化判据的样本扩充（Raven R21）：原 8 个样本的键**全为小写** ⇒ 「键序按 `key.lower()`」子类**检不出**（假绿）。样本扩到 **16 个**，加入大写/混合大小写/下划线/Unicode 键与 ≥2 层嵌套 | 直接 CLI 证据：`python3 spikes/fix2_f7_evidence.py` → 基线（未注入）exit **0**；注入键序变体（`DEEPHEALING_CANONICAL_JSON`）exit **1**，失败 diff 正是 `+ {"a":2,"B":1}` vs 契约 `{"B":1,"a":2}`；`pytest tests/test_canonical_contract.py -q` → **4 passed** exit 0（含分隔符漂移与键序漂移**两条**子进程反向对照 + 「样本真有判别力」自证：`order_sensitive >= 6`） | `03` §3m；`spikes/fix2_f7_evidence.py`；`tests/test_canonical_contract.py::{test_contract_assertion_goes_red_under_lowercase_key_order,test_samples_actually_exercise_case_and_depth}` |

**F 类合计**：7/7 CLOSED，每条都带**反向对照**或**防恒红**（F1 内容变必须重写；F2 干净日志必须绿；
F3 删 blocker 必须绿；F4 换回真文件必须绿；F5 正常 pack 必须空清单；F6 无逐字重复；F7 基线必须绿）。

### 11.2 G 类（文档/声明面，逐条落笔位置）

| # | 写什么 | 落笔位置（已核对存在） |
|---|---|---|
| **G1** | U11 扩写（Raven R16）：**冻结的 `pack_sign.py` 与 `verify_pack.py` 都未守符号链接** ⇒ **AC-M1-1 绿不代表 pack 无越界读取**（`verify_pack.py` 才是验证工具，原先只登记了 `pack_sign.py`）；Raven 实证三态（`pack_sign.py` exit 0 / `verify_pack.py` exit 0 / 内核 `load_pack` 拒收）；加守卫属**冻结面变更**需 PM/ADR | §4 **U11** 行 |
| **G2** | RISK-2 补 `verify` 资源量级（Raven R20）：峰值 ≈ **60 KB/事件**（32663 事件 → 2.05 GB / 31.9 s），`run` ≈ 1 KB/事件（32 MB / 12.4 s）；A1 增量 ≈ **+11%**；**925 事件为本轮上限**；M2 需流式比对 | §7 **RISK-2** 行 + §4 **U16** 行 |
| **G3** | 改正「随 `--ticks` **线性**增长」→ 实测**饱和**（300→925、3000→2633、10000→2793）；造大日志要靠 `--snapshot-every` | §7 **RISK-2** 行（措辞已改） |
| **G4** | 补 **U15**：`rng_state_digest` 覆盖**全部已创建 stream** ⇒ 新增子系统会改它（`state_hash` 不变）；并改正 `ecs.py` docstring 里**不存在**的 `traversal_flags` 字段（R22.3）→ 改为 `entities` / `trauma_flags` / `tags` / `memory_ref.fact_keys` 四项 | §4 **U15** 行；`deephealing_kernel/ecs.py` 模块 docstring |
| **G5** | §0.1 收准（Sentinel Bug#12）：`02_source` 是**代码/契约**交付面；AC-M1-5/6/7 还依赖**工作区级**产物 `spikes/**` 与 `06_*.md`（单独拿走 `02_source` ⇒ **12 failed / 50 passed / 10 skipped**，属产物缺失而非回归） | §0.1 引言段 |
| **G6** | 残渣计数改**实测口径**（Sentinel Bug#10）：AC-M1-4 裸 `pytest` 单步 ⇒ **6 目录 + 7 `.pyc` = 13 条路径**；叠 AC-M1-5 裸 pytest ⇒ **14**；再叠字面 `run` ⇒ **22**（原先写的 5/6 项不准确） | §0 残渣行 + §3 **L4** 行；实测脚本 `spikes/measure_literal_residue.py`（`/tmp` 完整工作区副本，不动交付树）；`03` §3n |
| **G7** | M3 行与 U1 各补一句（Raven R21 附）：该断言**独立于 run↔replay 轴**，但**共用 `canonical_json`** ⇒ 挡不住序列化实现本身的缺陷（**不得**读成「M3 已挡住所有共有错误」） | §3 **M3** 行 + §4 **U1** 行 |
| **G8** | 脱敏族边界**如实登记**（Raven R23.1，**不改判据**）：`auth_token`/`authtoken`/`session_token`/`refresh_token`/`authorization_header`/`http_authorization` **由命中变漏网**；`secretKey`/`private_key`/`bearer`/`x-api-key`/`client_secret`/`password` **两轮都漏**；正确修法需「键名等价 + 值形态」双判据**并同时**给 `token_budget` 类量词后缀加豁免（否则重新引入误伤），属 **M2**；本轮事件 payload 不含这类键 ⇒ **无现网影响** | §4 **U17** 行（新增） |

**G 类合计**：8/8 已落笔（`06` 内逐条可 grep：`U11`/`RISK-2`/`U15`/`§0.1`/`L4`/`M3`/`U1`/`U17`）。

### 11.3 收尾回归（本轮重跑值）

| 项 | 命令 / workdir | exit | 结果 |
|---|---|---|---|
| 全量回归 | `cd {ws}/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider` | **0** | **71 passed / 10 skipped**（修复轮 1 后为 62；本轮新增 9 条） |
| REQ 字面形态 | `cd {ws}/02_source/v0_skeleton/kernel && pytest tests/test_pack_validate.py -q` | **0** | **12 passed** |
| 契约面（第 1 遍） | `cd {ws}/02_source && bash verify_specs.sh --quiet` | **0** | `verify_specs: OK (95 checks passed, 0 skipped)` |
| 契约面（e2e 之后复跑） | 同上（`03` §3e） | **0** | 同上 |
| 契约面（清残渣后复跑） | 同上（`03` §10） | **0** | 同上 |
| e2e `run → verify → replay` | `03` §3 | 全 **0** | 925 事件 / 6 检查点 / 链尾 `baecca92…`；`verify` 逐检查点三哈希一致 |
| 锚点三态 | `03` §3d | 0 / 0 / **1** / 0 | 不传锚点 exit 0；传原始链尾 **exit 1 `anchor_mismatch`**；传伪造自身链尾 exit 0；未篡改+正确锚点 exit 0 |
| 朴素截断 / 篡改 | `03` §3b / §3c | **1** / **1** | `truncated log: max_tick=298 != plan_ticks=300`（首个分歧 tick 299）；`hash mismatch at tick 1` |
| 伪造矩阵（5 类自洽） | `03` §3f | 4 类 **1**、`truncate_rechain` **0** | 与修复轮 1 一致；`truncate_rechain` 是**已登记残余**（只能由 `--expected-hash` 关闭） |
| **N8 / N9（本轮新增）** | `03` §3h | **1** / **1** | 归因均为 `payload_diff field=checkpoint_path`；干净日志 **0** |
| registry 幂等 | `03` §3l | **0** ×2 | sha256 不变、`unchanged: true` |
| 夹具存活自证 | `03` §11b | — | **7/7 OK** |
| 残渣 | `python3 spikes/clean_residue.py 02_source` + `find` | **0** / 空 | 交付树零残渣 |
| 交付清单 | `python3 spikes/make_delivery_manifest.py` + `shasum -a 256 -c V0_M1.sha256` | **0** | **非 OK 行 = 0**（条数与口径见 §11.4） |
| 真实仓库 | `git rev-parse HEAD` / `git status --porcelain` | **0** | `b421cb01df4bf864b9a3fa48dbf6221c3989dc02` / porcelain **0 行** |

### 11.4 交付清单口径变更（本轮**唯一**的口径调整，请知悉）

修复轮 1 的 `V0_M1.sha256` **已过期**：8 个文件 FAILED，且仍在引用**已被清理**的 `out/m1-c7/**`。
根因是清单把 **`out/**`（易失运行产物目录）** 也登记了 —— `spikes/ac3-forge/reset_out.py` 会在复跑
AC-M1-3 前整棵删掉 `out/m1-ac3*` / `out/m1-c7` / `out/m1-claim` / `out/m1b`，而 `out/sentinel*/**`
又是**其他角色**的审计目录。⇒ 任何一次正常复跑都会让 `shasum -c` 立刻 FAILED，清单失去证据锚点价值。

**本轮口径**（`spikes/make_delivery_manifest.py` 已改，docstring 写明理由）：
- **登记**：`02_source/**`、`06_v0_m1_self_test.md`、`spikes/**`（排除生成残渣 `__pycache__`/`.pytest_cache`/`*.pyc`）；
- **不登记**：`SEED.sha256`、`V0_M1.sha256` 自身、`03_artisan_self_test.log`（边跑边追加）、**`out/**`**；
- `out/**` 的可核验性由 `03_artisan_self_test.log` 的**命令 + workdir + exit + 关键输出**承担（每条都写了产物路径）。
- 结果：**条目数 276**、**非 OK 行 = 0**；且**在「连跑 `registry` 两次」之后复跑 `shasum -c` 仍为非 OK 行 = 0**
  （F1 幂等的直接意义 —— 修复轮 1 的清单在同一动作下会变成 641 OK / 1 FAILED）；
  清单内**不含**任何 `out/**` 条目、也不含 `__pycache__`/`.pyc`/`.pytest_cache`（grep 计数 0）。

