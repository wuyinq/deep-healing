# 06 · V0-M2 逐 AC 证据表（Artisan 自测）

- 任务：`REQ-20260921-004-deephealing-v0-m2`（V0 里程碑 M2 = W3~W6 + M1 遗留 P-1~P-6）
- 角色：artisan（本轮唯一产品 writer）　日期：2026-09-22
- `{ws}` = `/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-004-deephealing-v0-m2`
- 设计输入（只读）：`{ws}/01_architecture_design.md`（= `01_m2_design.md`，两份逐字节一致，
  sha256 `25bf2ca3b5ff9a1e174f64d5507cd548c9883406327aad8a1b80c38c2f32739b`）
- 自测日志（M1 段**逐字保留** + M2 段**当场重跑捕获**）：`{ws}/03_artisan_self_test.log`
  （M1 段 176593 字节为字节前缀；M2 段 50 条命令，`nonzero_exits: []`）
- 本轮冻结面自校验：`{ws}/V0_M2.sha256`
- 复跑纪律：`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest … -p no:cacheprovider`

---

## §0 开工快照与基线

| 项 | 值 |
|---|---|
| 真实仓库 | `/Users/wooyinq/personal/deep-healing` |
| branch | `develop` |
| HEAD | `f5f7762`（全 40 位：`f5f7762…`，即 M1 后置修复提交） |
| `status --porcelain` | **空（dirty=0）** |
| 起点基线 `verify_specs.sh --quiet` | `verify_specs: OK (95 checks passed, 0 skipped)`，exit 0 |
| 收尾 `verify_specs.sh --quiet` | `verify_specs: OK (110 checks passed, 0 skipped)`，exit 0 |
| `SEED.sha256` 聚合 | `34fa7f6d252bc4bf966c8dbc4d639a1f08788ed71b9cfa04a0896ca7ba8f7676`（与 M1 起点一致，文件未被修改） |
| `02_source` 文件数 | **134**（M1 起点 111 ⇒ **+23**） |
| 残渣扫描（`__pycache__` / `.pytest_cache` / `*.pyc`） | **0** |
| 并发 writer | 仅本 artisan 进程（`ps -eo pid,etime,command \| grep 'hermes -p artisan'` 单条命中） |

### §0.1 HEAD 与任务书字面的差异（**显式声明**）

任务书 §0.3 / §6 写的期望 HEAD 是 `b421cb0`（= M1 的**冻结提交**）。盘上实际是 `f5f7762`
（`fix(v0): 标定缓存改为内容锚定，消除位置耦合（M1 后置修复）`），其前一笔是
`984cd9c feat(v0): 落盘 V0 垂直切片 M1 交付单元`。

**性质**：这是 M1 的**交付事实**，不是本轮 writer 引入的漂移。判定口径：

1. 真实仓库 `develop` @ `f5f7762`、`status --porcelain` **空** ⇒ 「M2 全程零改动」成立；
2. `b421cb0` 仍是冻结架构提交、且仍是 `02_source` 的**起点**（`V0_M1.sha256` / `SEED.sha256` 均在位且未被本任务修改）；
3. 因此 AC-M2-8 按「`develop` + dirty=0 + 起点溯源未变」判定，并把 HEAD 差异**如实登记**为对任务书字面的偏差。

### §0.2 429 中断与续跑说明

上一轮 session `20260922_115839_8c78ae` 在 44 分钟后被 provider **HTTP 429（server is at capacity）**
打死，当时自述进度 70%（实现面已落地、`verify_specs` 110/0 绿、全量 102 passed / 4 skipped、第二街区全绿），
**收尾产物尚未落盘**：`spikes/s10-memory/**`、根级 `03` / `06` / `V0_M2.sha256`。

本轮续跑**只做收尾**：

1. 补 `spikes/s10-memory/**`（记忆层真跑证据，含逐字节比对器与负例）；
2. 写根级 `03_artisan_self_test.log`（M1 段逐字保留 + M2 段当场重跑捕获）；
3. 写 `06_v0_m2_self_test.md`（本文件）与 `V0_M2.sha256`；
4. **重跑**关键门禁自证（不凭上轮记忆）：`verify_specs`、全量 pytest、基线复算、四组负例探针。

**续跑轮对实现面零改动**：续跑写集只有 `spikes/s10-memory/**`、根级 `03`/`06`/`V0_M2.sha256`、
`.squad_tools/artisan-*.py` 探针，以及 `spikes/s8-registry/**`、`spikes/s9-rules/**`、`spikes/s11-pack2/**`
的证据重跑（scratch），**未改** `02_source/**` 任何实现文件。

---

## §AC-M2-1 契约门禁全绿 + U11 关闭 + manifest 穷尽

**命令**：`cd {ws}/02_source && bash verify_specs.sh --quiet`　**workdir**：`{ws}/02_source`
**实测**：`verify_specs: OK (110 checks passed, 0 skipped)`　**exit**：`0`
**期望**：`OK` 且 **0 skipped**（PASS 计数随新增文件增长：M1 起点 95 ⇒ 本轮 110；+15 条来自新增 JSON/能力/pack 文件）。

### 负例自证 ①：U11 A/B（符号链接逃逸 pack）

A 证的工具来源 = 真实仓库 `git show HEAD:v0/02_source/v0_skeleton/tools/*.py`（**只读**取出到隔离目录）
⇒ 结论可随时复算，不依赖上一轮现场（上一轮的临场 A 证已被 `uv` 中断覆盖，本轮改为可复算形态）。

- **A 证（修复前）**：`pack_sign.py` exit **0**；`verify_pack.py` exit **0**
  （stdout: `verify_pack: OK (13 files, pack_id=xingfu-xiaoqu version=0.1.0)`）；
  `pack.sig` 里 `world.seed.json` 条目的 sha256 = `cf100831a05cd1f6be91cb41cdb53f257ddee00c57cbdff8d57cc82f6ffd2ac6`，
  包外文件内容 sha256 **同值** ⇒ `sig_entry_equals_outside_content = true`。
  证据：`{ws}/spikes/s8-registry/logs/u11-before.json`
- **B 证（修复后）**：`verify_pack.py` exit **1**，stderr 含结构化
  `E_PACK_INVALID: symlink escape: … resolves to … which is outside pack root …`；`pack_sign.py` exit **1**（写侧同样拒收）；
  包外目标文件 sha256 前后一致 = **true**；无 `Traceback`。
  证据：`{ws}/spikes/s8-registry/logs/u11-after.json`
- **B 证两条断言缺一不可**（设计 §4 P-1）：① exit 1 + 结构化诊断；② 包外文件 sha256 前后一致。两条均成立。

### 负例自证 ②：P-5 三类负例（写侧魔数 / `pack.sig` 符号链接 / 读侧逃逸）

| 负例 | 期望 | 实测 |
|---|---|---|
| 改名 `.txt` 的 shebang 内容 | 写侧 + 读侧都拒收 | `pack sign` exit **1**、`verify_pack` exit **1**，诊断 `E_PACK_INVALID: executable file in content pack: …（判据：内容魔数=shebang 脚本）` |
| `pack.sig` 指向包外文件的符号链接 | 写侧拒收且**不改写包外文件** | `pack sign` exit **1**（`refusing to write pack.sig through a symlink`）；包外文件前后一致 = **true**、哨兵内容仍在 = **true** |

证据：`{ws}/spikes/s8-registry/logs/p5-probes-after.json`

**自证反例（退回旧形态 ⇒ 门禁必须变红）** —— `python3 .squad_tools/artisan-p5-revert-negative-control.py`：

- ① 逃逸符号链接：仓库 HEAD 的**修复前** `verify_pack.py` exit **0**（`verify_pack: OK (13 files…)`），
  且 `pack.sig` 记录的是**包外内容哈希**（`sig_entry_equals_outside_content = true`）；
- ② `pack.sig` 符号链接：修复前写侧 exit **0**，且包外文件**被改写**
  （`76c5abe819218a7e10e579b498f436840fc5cd69543337cd24affbd65bc7fd0c` → `72e6cc90bb1a3e1690a4922d3226af760ba6145ac84d1e99e64f8c6817490650`）；
- ③ 改名 shebang：修复前写侧 exit **0**（放行）。
- 工具来源 sha256：`pack_sign_legacy` = `a00c614f054535cacd9d57720d54c85749ebcc64bd8b87b0d840d9b1d77c8d76`、
  `verify_pack_legacy` = `03d0c7a102e9acf4ac22d43b5e6de9f23221f461ce4d2fdab9c4b5e75851a2a4`。
- 证据：`{ws}/spikes/s8-registry/logs/p5-revert-negative-control.json`

### 负例自证 ③：manifest 覆盖穷尽 + 无幻影条目

命令：`cd {ws} && python3 .squad_tools/artisan-manifest-sync.py --check`（exit 0）

- manifest 行数 = **133**；`02_source` 非生成文件数 = **133**；**缺失 = 0**；**幻影条目 = 0**；
  子串判据复算缺失 = 0；三字段格式异常 = 0。
- 登记顺序固定：**先写文件 → 再登记 `manifest.txt` → 再跑 `verify_specs.sh --quiet`**（实测 `OK` + 0 skipped）。
- 证据：`{ws}/spikes/s8-registry/logs/manifest-exhaustiveness.json`

**L-1 残留（未加固）**：manifest 覆盖率判据是**子串**而非锚定（路径 A 是路径 B 前缀时可被掩盖），
且两条 `GENERATED_PATTERNS`（`attic-*/*`、`*/dist/*`）可隐藏同名真实文件。本轮**不改** `verify_specs.sh`
（未被授权），登记为 LOW 遗留；「无幻影条目」这一面由上述独立探针补齐。
**L-2 残留（未加固）**：`verify_specs.sh` 仍不校验 `world.seed.json` ↔ `world.schema.json`（M1 U7 未变）；
本轮该面由内核侧强口径覆盖（`load_pack` 的 `_validate_schema(projection, world_schema, …)`，ADR-13 后为恒等投影）。

**AC-M2-1 判定：PASS**（`OK` / 0 skipped / exit 0 + U11 B 证两条断言齐备 + manifest 穷尽且无幻影 + 三组反例均变红）

---

## §AC-M2-2 能力注册表真跑 + 新增能力零内核改动

**命令**：
① `jq . 02_source/capability.schema.json`（exit 0）；
② `cd {ws}/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_capability_registry.py -q -p no:cacheprovider`；
③ `python3 {ws}/.squad_tools/artisan-kernel-digest-evidence.py`

**期望 / 实测**：

- ① `jq .` exit **0**（JSON 合法）；
- ② **6 passed（全部真跑，非 skip）**，exit **0**。契约字段齐备由 `capability.schema.json` 的
  `x-*` 元数据节 + `tests/test_capability_registry.py` 的真跑 schema 校验共同覆盖；
- ③ `kernel_digest` 差集：`changed == []`，`added == ["providers/adapters/__init__.py",
  "providers/adapters/relation_infer.py"]`（⊆ adapter 目录并集 `("adapters/", "providers/adapters/")`），
  `removed == []`，`criterion_ok = true`。
  `digest_before = 4f22e6cbd71d014998b76acdf170ca425402c86dd0ca13a1a4b2276e0b1dc1d2` →
  `digest_after = 44570f5437a778d259534af6c199ddaf2ceb172ff159eb0a99699e522311a06a`。
  （修复轮 2 更正：此前误写为 `56dd3538…`/`8cebd74f…`，与盘上证据不符 —— Sentinel Bug#1，见 §显式声明 8。）
  证据：`{ws}/spikes/s8-registry/logs/kernel-digest-evidence.json`

**`before` 采集时点（设计 §7 / M-1 纪律，含声明）**：设计要求的 `before` 采集时点 =
「W3~W6 代码写完并冻结之后、`relation.infer` 数据 + adapter 加入**之前**」，落盘到
`spikes/s8-registry/baseline-after-m2-code/**`。本轮执行顺序里 adapter 与代码在**同一工作会话**内写完，
因此 `before` 是**重建**的：`baseline-after-m2-code/` = 当前内核**去掉** `deephealing_kernel/providers/adapters/**`
（移除文件清单与该目录内每个文件的 sha256 落进证据 JSON）。这与设计纪律的**实质**一致：
`before` 不含 adapter、`after` 含 adapter，两侧其余文件逐字节相同，因此差集只反映 adapter 的加入。

**判据自证**：`PYTHONDONTWRITEBYTECODE=1 python3 tools/kernel_digest.py --selftest` exit **0**：
`[① 正例 adapter 新增] ok=True` / `[② 负例 改 tick.py 一字节] changed=['tick.py'] ok=False` /
`[③ 负例 包根新增 .py] added=['extra_module.py'] ok=False` / `[④ 正例 providers/adapters/ 并集] ok=True`。
**自造负例**：隔离副本里改 `tick.py` 一字节 ⇒ `changed == ["tick.py"]`、`criterion_ok = false`（同上证据 JSON）。

**四类非法能力负例（逐类给 reason code）** —— 全部在 `tests/test_capability_registry.py::test_invalid_capability_file_is_rejected` 内真跑：

| # | 负例 | 期望 reason code | 实测 |
|---|---|---|---|
| ① | 缺 `safety` | `E_CAP_SCHEMA` | 命中 |
| ② | `safety.secrets_in_context = true` | `E_CAP_SCHEMA` | 命中 |
| ③ | `impl` 未登记（`module:somewhere_else.module:fn`） | `E_CAP_UNREGISTERED` | 命中 |
| ④ | schema 合法但**无适配器** / 强制未注册 provider | `E_CAP_PROVIDER_UNRESOLVED` | 命中（两条可达路径） |
| ⑤ | 同 `id@version` 重复文件（不同子目录，`rglob` 都扫到） | `E_CAP_DUPLICATE_ID` | 命中 |
| ⑥ | 同 `id` 多版本且 `pins.json` 未钉 | `E_CAP_VERSION_CONFLICT` | 命中 |

**归因声明（不放松判据）**：`providers[].class` 的**枚举面**由 `capability.schema.json` 先关掉
（写 `magic_model` ⇒ `E_CAP_SCHEMA`），因此 ④ 走的是「schema 合法但无适配器 / 强制未注册 class」这条
**可达路径**，而不是「任意非 0 就算过」。用例内同时对枚举外取值断言 `E_CAP_SCHEMA`，两条路径都有牙齿。

**AC-M2-2 判定：PASS**

---

## §AC-M2-3 三类 provider 真跑 + provider 矩阵 + 脱敏面

**命令**（真跑日志落盘）：

```
# record（真实调用 + 录制）
cd {ws}/02_source/v0_skeleton/kernel
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel run \
  --pack districts/xingfu-xiaoqu --seed 20260921 \
  --events {ws}/spikes/s8-registry/smoke-rec-final/e.jsonl \
  --snapshot-every 50 --ticks 60 --cognition --memory \
  --cassette-dir {ws}/spikes/s8-registry/smoke-cassettes-final
# replay（强制回放，fail-closed）
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel run \
  --pack districts/xingfu-xiaoqu --seed 20260921 \
  --events {ws}/spikes/s8-registry/smoke-rep-final/e.jsonl \
  --snapshot-every 50 --ticks 60 --cognition --memory --replay \
  --cassette-dir {ws}/spikes/s8-registry/smoke-cassettes-final
```

**实测**：两次 exit **0**。注册表 6 槽位全部装载、`validation_errors == []`：

```
["embed.text", "emotion.appraise", "imagine.predict", "intent.plan", "memory.reflect", "relation.infer"]
```

**provider 矩阵（本轮真跑口径）**：

| provider class | 本次真跑 | 实测计数（cognition.jsonl 的 `capability.call`） | 证据 |
|---|---|---|---|
| `remote_api` | **真实调用**（`POST /chat/completions`，脱敏） | 10 条（`intent.plan` ×5、`emotion.appraise` ×5） | `smoke-rec-final/cognition/cognition.jsonl` |
| `local_model` | **诚实 GAP**（未跑） | 0 条；`local_model_available = false` | `smoke-rec-final/cognition/summary.json` |
| `deterministic_rule` | 真跑（含 fallback 降级与 `embed.text` 录制源） | 5 条（`relation.infer` fallback）+ `embed.text` **5 条（全部是 `deterministic_rule`，不是远端路径；见 §GAP-E1）** | 同上 |
| `cassette_replay` | 真跑（**强制回放**，0 次远端调用） | **15 条全部** | `smoke-rep-final/cognition/cognition.jsonl` |

- **回放语义**：`--replay` 下 `registry.default_replay_mode = True` ⇒ **所有** `invoke` 强制走
  `cassette_replay`，miss 即抛 `E_CASSETTE_MISS`（fail-closed，**不降级、不静默切远端**）；
  对应用例 `test_capability_registry.py::test_cassette_miss_is_fail_closed`（含「先录制后回放必命中」的反向对照）。
- **逐字节等价**：record 与 replay 的 15 条 `capability.call` 按 `(slot, output_digest)` 逐条比对
  ⇒ **完全一致**（`diff` 空）。cassette 文件：
  `smoke-cassettes-final/{intent.plan,emotion.appraise}__remote_api.jsonl`、
  `{embed.text,relation.infer}__deterministic_rule.jsonl`。
- **四键口径（F-13 / M-6）**：`cassette_key_fields` 含 `capability_id` / `capability_version` /
  `canonical_input_hash` / **`provider`**；「改 provider ⇒ 键变化」由
  `test_provider_switch_remote_to_cassette_to_rule` 断言。
- **`local_model` 诚实 GAP（硬约束 R-10）**：本机**无本地模型服务**；
  `LocalModelProvider.available()` 对 `http://127.0.0.1:11434/api/tags` 发只读探测后返回 **False**
  （真跑输出）；`invoke()` 抛结构化 `E_LOCAL_MODEL_UNAVAILABLE` 交由 fallback 链降级，**绝不伪造输出**。
  **本轮不宣称 `local_model` 跑过。**
- **断网真跑的替代**：设计允许「断网**或**强制回放模式」；本轮用**强制回放**（`--replay`）跑通完整决策循环，
  15 次调用全部命中 cassette、0 次远端调用 ⇒ 离线可复现成立。

### 凭据面（双判据扫描 + 注入探针）

命令：`cd {ws} && python3 .squad_tools/artisan-ac-m2-8-and-credential-scan.py`（exit **0**）

- 扫描面：`02_source/**` + `spikes/**` + `.squad_tools/**` + `03`/`06`/`V0_M2.sha256`，
  共 **624** 个文件；判据 = ① **键名**（`api_key|authorization|access_token|…` + ≥16 字符值）
  ② **值形态**（`sk-…` / `Bearer …`（非 `***REDACTED***`）/ `ghp_…` / `xox…`）
  ③ **环境变量值逐字**（能力契约 `requires_secrets` 声明的变量名取值）；
  **只打印命中文件名与判据名，绝不打印值**。
- 命中结果：**非「工具名字面」命中 = 0**。仅 3 个文件命中 `toolfab_literal` 判据 ——
  `02_source/v0_skeleton/kernel/deephealing_kernel/providers/remote_api.py` 及其两份隔离副本，
  原因是该文件的**注释**里写明「**禁止**加 `TOOLFAB` 别名回退」（即：字面出现在**禁令说明**里，
  不是凭据、也不是可用变量名）。该面**已在下方 §显式声明 6** 单独登记。
- **注入探针（证明扫描器有牙齿）**：往 `spikes/s8-registry/logs/credential-injection-probe.txt`
  写入假值 `api_key = "sk-9f4c2b7a1e6d8a3c5b0f7d2e4a6c8b1d"`（**不含**任何夹具标记）
  ⇒ 扫描**命中**（判据 `key_name` + `value_shape`）；删除探针后非工具名命中回到 **0**。
- 证据：`{ws}/spikes/s8-registry/logs/ac-m2-8-and-credential-scan.json`
- **本轮真跑用的凭据变量名 = 冻结面声明的 `HERMES_CUSTOM_TOKENFAB_API_KEY`**（值绝不落盘；实现按契约声明读，
  代码里**不加** `TOOLFAB` 别名回退）。REQ §3 字面写的 `HERMES_CUSTOM_TOOLFAB_API_KEY` 在环境中**不存在** ——
  见 §显式声明 6（需 PM 更正 REQ 字面）。

**AC-M2-3 判定：PASS**（三类 provider 真跑输出落盘 + `local_model` 诚实 GAP + 矩阵含等价性与达成方式
+ 凭据扫描零命中 + 注入探针命中）

---

## §AC-M2-4 规则层真跑 + 预算语义 + 降级负例

**命令**：
① `pytest tests/test_budget_ledger.py -q -p no:cacheprovider` → **7 passed**，exit **0**；
② `pytest tests/test_rules_layer.py -q -p no:cacheprovider` → **6 passed**，exit **0**；
③ 决策循环真跑日志 = §AC-M2-3 的 `smoke-rec-final/cognition/cognition.jsonl`
（`capability.call` 15 条 + `cognition.cycle` 5 条 + `memory.write` 5 条）。

**「调用原子能力 → 校验结果 → 决定后续」至少一次**：真实跑里由行为树的 `selector` 体现 ——
`needs_pressure ≥ 0.30` 成立时走 `sequence`（`intent.plan` → `emotion.appraise` → `relation.infer`），
`relation.infer` 的远端输出**未过 `output_schema`** ⇒ 落 `provider.invalid_output` +
`capability.fallback`（`on_invalid_schema` → `deterministic_rule`），后续分支据此继续；
用例 `test_behaviour_tree_selector_falls_through_on_failure` 断言「条件成立只走第一条分支 / 不成立走第二条」。

**三级预算语义（实测）**：

| 档位 | 语义 | 实测 |
|---|---|---|
| tick 级 | 超上限 ⇒ `allow_call` 返回 `(False, "per_tick")` ⇒ `fallback.on_budget_exhausted` | `test_per_tick_cap_is_enforced`（含「下一 tick 配额重置」反向对照） |
| NPC 日级 | 超 token ⇒ `(False, "npc_daily")` ⇒ **降级到 `deterministic_rule`** | `test_npc_daily_token_cap_is_enforced` + `test_budget_exhaustion_degrades_to_deterministic_rule` |
| 会话级 | `spend_impact` 耗尽 ⇒ `(False, 剩余)`，由策略层转 `E_BUDGET_EXHAUSTED` | `test_spend_impact_exhaustion` |

**超时 ⇒ 确定性降级且进日志**：`skill` 侧由注册表统一执行 —— provider 抛错 ⇒ 记 `provider.error`
（含 `reason`）⇒ 走 fallback 链 ⇒ 记 `capability.fallback`（`reason` + `target`）；
真跑日志里可见 `on_invalid_schema`（10 条）+ `on_budget_exhausted`/`on_timeout` 的对应记录。

**负例自证：把降级改成「静默回填」⇒ 门禁必须变红**：
`test_budget_exhaustion_degrades_to_deterministic_rule` 内注入 `_silent_backfill`（不落 `capability.fallback`
事件、直接把输出当成功返回）⇒ 该用例用来判「降级可审计」的两条断言**必然不成立**
（`fallback_reason != "on_budget_exhausted"` 且 journal 里无 fallback 事件）。

**代码里零毫秒常量**：`test_timeout_comes_from_the_capability_contract` 断言
「provider 收到的 `timeout_ms` == 能力契约的 `timeout_ms` 声明值」，并对
`budget.py` / `rules/*.py` 做毫秒字面量扫描（`(timeout_ms|latency_ms|ms)\s*[:=]\s*\d{2,}`）⇒ 命中 0。

**AC-M2-4 判定：PASS**

---

## §AC-M2-5 记忆三层真跑 + 确定性

**命令**：
① `pytest tests/test_memory_layers.py -q -p no:cacheprovider` → **8 passed**，exit **0**；
② `python3 {ws}/.squad_tools/artisan-s10-memory-evidence.py` → exit **0**，`problems: []`。

**真跑证据（全部落 `spikes/s10-memory/**`）**：

| 判据 | 实测 | 证据 |
|---|---|---|
| 三层真跑 | `working` 2 / `episodes` 3 / `facts` 2（两个独立库同值） | `logs/memory-layers.json` |
| 唯一写入点 + **默认 flag 关闭 ⇒ 零写入** | flag 关：`write_count = 0`、episodes total = 0、`prune` 返回 0；flag 开：同调用真的写入（episodes total = 1） | `logs/write-point.json` |
| 同 seed 同输入 ⇒ 检索**逐字节一致** | 两个独立库的 `digest` **同值**、记录逐条相同，比对器判定 `CONSISTENT` | `logs/retrieval-digest-compare.json` |
| **负例**：改 tie-break / 依赖容器迭代序 | 两处变异均被判 `INCONSISTENT`（摘要与基线不同） | `logs/retrieval-digest-negative.json` |
| `prune` 软删 + 容量不超上限 | 容量 2、写入 5、`prune` 返回 3；活跃 ≤ 2；**行仍保留 5 条**且被裁行带 `superseded_by` | `logs/prune-soft-delete.json` |
| 旧事实保留 `superseded_by` | 覆盖 `resident.mood`：活跃值 = `安心`；历史 2 条；旧行 `superseded_by` **指向新 ref** | `logs/supersede-history.json` |
| CLI 真跑（`run --cognition --memory`） | exit 0；`memory_write_count = 10`（= 2 × 5 事件：每 NPC 一条 episodes + 一条 working）；检索摘要落 `retrieval_digests` | `logs/cognition-memory-run.json` |
| **记忆不写世界状态** | 带 / 不带认知层的 `chain_tail` **逐位相同**（`b4a9b6aa…`），`state_hash` 不受影响 | `logs/world-state-boundary.json` |

**排序口径**：`相似度 desc → tick desc → ref asc`；相似度按 6 位小数量化后比较，无嵌入的候选记 `0.0`
（不跳过 —— 跳过会让结果依赖「谁有嵌入」，不可复现）。
**AC-M2-5 判定：PASS**

---

## §AC-M2-6 第二街区（零内核改动）

**命令**：

```
cd {ws}/02_source/v0_skeleton/kernel
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel validate --pack districts/xingfu-xiaoqu-north   # exit 0
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel run --pack districts/xingfu-xiaoqu-north \
  --seed 20260921 --events {ws}/spikes/s11-pack2/out-north-final/e.jsonl --snapshot-every 50 --ticks 100   # exit 0
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel verify \
  --events {ws}/spikes/s11-pack2/out-north-final/e.jsonl --pack districts/xingfu-xiaoqu-north            # exit 0
```

**实测**：

- `validate` exit **0**：`{"pack_id": "xingfu-xiaoqu-north", "version": "0.2.0", "entities": 12, "npcs": 5,
  "buildings": 2, "tasks": 2, "schedules": 1, "portal_edges": 1, "inactive_portals": ["portal-north-south"],
  "weather_declared_and_dropped": true}`；
- `run` exit **0**、`verify` exit **0**（`verify: OK (chain self-consistent; …; event stream matches replay)`）。

**迁移路径**（`district.pack.spec.md §3`）：复制 `districts/xingfu-xiaoqu` → 改
`id`/`version`/`display_name`/`bounds_mm` + portal 指回第一街区 → **重签** `pack.sig`
（复用冻结的 `tools/pack_sign.py`，非手写）。脚本：`.squad_tools/artisan-make-second-district.py`。
**校验方式**：`validate` / `run` / `verify` 三条命令 + `kernel_digest` 差集。

**内核源码指纹 before/after 差集**（**真实时序对**：先取当前 digest，再重跑第二街区生成脚本，再取 digest）：

- `changed == []`、`added == []`、`removed == []`；
  `digest_before == digest_after == 44570f5437a778d259534af6c199ddaf2ceb172ff159eb0a99699e522311a06a`
  （修复轮 2 更正：此前误写 `8cebd74f…`，与盘上证据不符 —— Sentinel Bug#1，见 §显式声明 8）；
- `criterion_ok = true`。证据：`{ws}/spikes/s8-registry/logs/kernel-digest-evidence.json` 的 `ac_m2_6` 节。

**负例自证**：`tests/test_pack_validate.py::test_second_district_requires_no_kernel_change` 断言
「未重签 ⇒ `validate` 非 0」「重签 ⇒ exit 0」「改 `pack.sig` 一个 sha256 ⇒ 再次非 0」，
并在隔离副本上比对 `kernel_digest` 前后一致。

**AC-M2-6 判定：PASS**

---

## §AC-M2-7 M1 判据不回退 + 基线复算

**命令 ①**：`cd {ws}/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider`
**实测**：`102 passed, 4 skipped`，exit **0**。

**新基线如实记录 + 与 M1 的逐条解释**：

| 项 | M1（起点） | M2（本轮实测） | 变化解释 |
|---|---|---|---|
| passed | 71 | **102** | +31：新增用例（`test_capability_registry` 6 条由 **skip 转真跑**、`test_budget_ledger` 7、`test_memory_layers` 8、`test_rules_layer` 6、`test_io_shape_guards` 4） |
| skipped | 10 | **4** | −6：`test_capability_registry.py` 的 6 条由 `skip` 转**真跑**（AC-M2-2 判据）；余下 4 条 = `test_observe_mode_readonly.py`（session 传输层，属 **W7**，本轮非目标） |

**命令 ②**（逐条 M1 命令）：

| 命令 | 实测 | exit |
|---|---|---|
| `bash verify_specs.sh --quiet` | `OK (110 checks passed, 0 skipped)` | 0 |
| `pytest tests/test_determinism_replay.py -q` | **6 passed** | 0 |
| `pytest tests/test_pack_validate.py -q` | **12 passed**（T-1/T-2 改写后） | 0 |
| `pytest tests/test_bus_and_ecs_invariants.py -q` | **6 passed**（T-3 改写后） | 0 |
| `pytest tests/test_kernel_digest.py -q` | **4 passed**（T-4 改写后） | 0 |

**命令 ③**（基线复算，architect 逐字给的命令）：

```
cd {ws}/02_source/v0_skeleton/kernel
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel run --pack districts/xingfu-xiaoqu \
  --seed 20260921 --events {ws}/spikes/s8-registry/baseline-recompute-final/e.jsonl \
  --snapshot-every 50 --ticks 300
```

**实测**：

- `chain_tail = baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786` ✔ **与设计 F-10 逐位一致**；
- `checkpoints/000300.json` 的 `state_hash = 9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f` ✔ **与设计 F-10 逐位一致**；
- 交叉验证：`verify` exit **0**（`chain self-consistent; per-checkpoint … agree; INVARIANT-ECH-1/2/3 hold; event stream matches replay`）。

**结论：`state_hash` / `chain_tail` 基线值均未变化**（M1 默认路径字节不变成立）。

**AC-M2-7 判定：PASS**

---

## §AC-M2-8 真实仓库零改动 + 起点溯源

**命令**：`git -C /Users/wooyinq/personal/deep-healing rev-parse --abbrev-ref HEAD` /
`rev-parse --short HEAD` / `status --porcelain`；`shasum -c SEED.sha256`（在 `{ws}`）

**实测**：

- branch = `develop`；HEAD = `f5f7762`（**任务书字面写 `b421cb0`** ⇒ 见 §0.1 的显式声明）；
- `status --porcelain` **空**（dirty = 0）；
- `shasum -a 256 SEED.sha256` = `34fa7f6d252bc4bf966c8dbc4d639a1f08788ed71b9cfa04a0896ca7ba8f7676`
  ⇒ `SEED.sha256` 文件**未被修改**，聚合与 M1 起点一致。

**`V0_M1.sha256` 的 divergence 全量清单**（`shasum -c V0_M1.sha256` 的非 OK 行逐条列出）：

- 汇总：`276` 条登记中 **OK = 150**、**`FAILED`（内容不一致）= 23**、**`FAILED open or read`（盘上不存在）= 103**。
- **`02_source` 前缀的 `FAILED`（内容不一致）= 22 条**，逐条：

```
02_source/capability.schema.json
02_source/manifest.txt
02_source/v0_skeleton/capabilities/pins.json
02_source/v0_skeleton/kernel/deephealing_kernel/budget.py
02_source/v0_skeleton/kernel/deephealing_kernel/cli.py
02_source/v0_skeleton/kernel/deephealing_kernel/memory/retrieve.py
02_source/v0_skeleton/kernel/deephealing_kernel/memory/store.py
02_source/v0_skeleton/kernel/deephealing_kernel/pack.py
02_source/v0_skeleton/kernel/deephealing_kernel/providers/cassette.py
02_source/v0_skeleton/kernel/deephealing_kernel/providers/deterministic_rule.py
02_source/v0_skeleton/kernel/deephealing_kernel/providers/local_model.py
02_source/v0_skeleton/kernel/deephealing_kernel/providers/remote_api.py
02_source/v0_skeleton/kernel/deephealing_kernel/registry.py
02_source/v0_skeleton/kernel/deephealing_kernel/rules/behaviour_tree.py
02_source/v0_skeleton/kernel/deephealing_kernel/rules/utility.py
02_source/v0_skeleton/kernel/tests/test_bus_and_ecs_invariants.py
02_source/v0_skeleton/kernel/tests/test_capability_registry.py
02_source/v0_skeleton/kernel/tests/test_kernel_digest.py
02_source/v0_skeleton/kernel/tests/test_pack_validate.py
02_source/v0_skeleton/tools/pack_sign.py
02_source/v0_skeleton/tools/verify_pack.py
02_source/world.schema.json
```

- **`spikes` 前缀的 `FAILED`（内容不一致）= 1 条**：`spikes/s5-latency-calibration/calibration.registry.json`
- **`FAILED open or read`（盘上不存在）= 103 条，全部在 `spikes/` 下**：
  `spikes/red/**` 87 条、`spikes/ac3-forge/**` 7 条、8 个 `spikes/*.py` 探针、`spikes/run_ac_evidence.sh`。
- **`02_source` 的新增文件（不在 `V0_M1.sha256` 清单里）= 23 条**（与「文件数 +23」一致）：
  `07_adr.md`、`relation.infer@1.0.0.capability.json`、第二街区 15 个文件、
  `providers/adapters/{__init__.py,relation_infer.py}`、`rules/requirement.py`、
  `tests/{test_budget_ledger,test_io_shape_guards,test_memory_layers,test_rules_layer}.py`。

### 与设计 §1.3 预期清单**逐条比对**

| 设计预期 | 实际 | 结论 |
|---|---|---|
| `capability.schema.json` | 在 FAILED 列表 | ✔ 一致（P-3 补写） |
| `world.schema.json` | 在 FAILED 列表 | ✔ 一致（ADR-13） |
| `v0_skeleton/tools/pack_sign.py` | 在 FAILED 列表 | ✔ 一致（P-5 写侧加固） |
| `v0_skeleton/tools/verify_pack.py` | 在 FAILED 列表 | ✔ 一致（P-1/P-5 读侧加固） |
| `kernel/deephealing_kernel/**`（实现面） | 在 FAILED 列表（12 个模块） | ✔ 一致（W3~W6 实现） |
| `v0_skeleton/capabilities/**` | 仅 `pins.json` 在 FAILED；`relation.infer` 是**新增**（无登记条目） | ✔ 一致（新增文件只会出现在「新增清单」而非 divergence） |
| `v0_skeleton/districts/**`（第二街区） | **全部为新增**，无 divergence 条目 | ✔ 一致（新增 pack 不在 M1 清单里） |
| `kernel/tests/**`（T-1/T-2/T-3 + 新增用例） | 4 条在 FAILED + 4 条新增 | ✔ 一致 |
| `manifest.txt` | 在 FAILED 列表 | ✔ 一致（补全 133 行） |
| `07_adr.md`（新增） | 在**新增清单**（M1 无该文件） | ✔ 一致 |
| **`spikes/**` 下 M1 既有条目「不得」出现 divergence** | **不成立，需解释** | ✘ 见下 |

**`spikes` 面的两处偏差（逐条解释）**：

1. **`spikes/s5-latency-calibration/calibration.registry.json` FAILED（内容不一致）**
   —— 这是**环境事实**（`.round1-constraint.txt` 的 KNOWN SEEDING ISSUE 已登记）：该文件内嵌
   **绝对 workspace 路径**，因此在种子化到新 workspace 后**必然**与 M1 的值不同；PM 已在种子化时
   `python3 tools/calibrate_latency.py registry` 就地重生成以让
   `test_calibrate_latency.py::test_registry_is_idempotent` 首跑即绿。本轮实测该文件在跑测试前后
   sha256 **不变**（幂等），且它属 `spikes/**`（非 `02_source` 交付面）⇒ **不是冻结面被破坏**，
   是**跨 workspace 不可移植**的既有事实。处置沿用约束文件结论：交付时必须就地重生成。
2. **`spikes/red/**` 等 103 条 `FAILED open or read`（盘上不存在）**
   —— 这些路径在**本 workspace 从未被种子化**：`.round1-constraint.txt` 明确写
   「seeded from M1 delivered state: `02_source` (111 files), `refs/`, `spikes/{kernel-baseline,
   kernel-baseline-recheck,s5-latency-calibration}`」—— `spikes/red/**`、`spikes/ac3-forge/**` 与 8 个
   根级探针**不在种子清单内**，因此 `V0_M1.sha256` 里对应条目在本 workspace **无法命中**。
   **性质**：这是**起点种子化的取舍**（V0_M1.sha256 是从上游 workspace 的全量冻结面生成的清单，
   而本 workspace 只需其中与交付相关的一部分），**不是本轮 writer 删除文件**。
   判定口径：`02_source/**` 下**没有任何** `FAILED open or read`（表内 103 条全部在 `spikes/` 下）。
   ⚠ 该结论的正确性依赖「上游 workspace 仍保留这些文件」；本角色**只读**核对过本 workspace，
   上游路径不在本任务书授权的核对范围内 ⇒ **该面登记为需 architect 复核项**。

**「这是本轮授权改动，不是冻结面被破坏」的论证**：

1. `SEED.sha256`（起点溯源聚合）**未被修改**（sha256 仍 `34fa7f6d…`），`V0_M1.sha256` 文件本身也未被改写；
2. `02_source` 的 22 条 divergence **逐条落在设计 §1.3 的授权改动面内**（见上表）；
3. `refs/**`、根级 `06_v0_m1_self_test.md`、`01_architecture_design.md` / `01_m2_design.md`、
   `.pm_notes.md`、`.raven_prereview.md`、`.round1-constraint.txt` **零改动**（本轮写集不含它们）；
4. 新增面由 **`V0_M2.sha256`** 承接（本轮冻结面自校验清单，`shasum -c` 0 非 OK）。

**AC-M2-8 判定：PASS**（`develop` + dirty=0 + `SEED.sha256` 未变 + divergence 逐条登记并与设计预期比对，
2 处 `spikes` 偏差已解释并升级为待复核项）

---

## §本轮不做项（P-4 的「不做」5 条，逐条给理由）

设计 §4.2 列出 M1 8 条 MEDIUM 中本轮**不做**的 5 条，逐条理由如下：

1. **畸形但链自洽日志（`world.init` 缺 `plan_ticks`）裸 traceback** ——
   修它要动「`events.schema.json` 的必填口径」（`plan_ticks` 是否必填），属**契约变更**，
   按纪律须走 PM/ADR；本轮授权写集不覆盖 `events.schema.json`。
2. **`AC-M1-6` 判据③口径塌缩** —— 属 **Q1（平稳窗口重采样）**，需要 PM 裁决采样口径与样本量；
   在裁决前任何改动都可能把「判据塌缩」换成「判据不可达」。
3. **独立序列化判据样本有界（round-half-even vs 四舍五入）** —— 契约**文字**变更属 **PM 决策**
   （会同时影响 `snapshot.schema.json` 的 normalization 条款与下游复算口径）。
4. **`AC-M1-7(b)` 请求体扫描是行级正则** —— 改判据强度（行级 → 结构化）属 **PM 决策**；
   本轮只把该扫描器的**反向对照**保留在 `test_evidence_scan.py` 里。
5. **目录符号链接子树不进 `rglob` 的穷尽性假设** —— 属 **M3/M4 面**（内容包加载的进一步加固）；
   本轮只**登记**，不做实现。注：`pack_sign.py` 的**文件级**写侧逃逸已由 P-5 授权关闭（不在「不做」之列）。
   **收-5（Raven R-M2-3）补充**：该条已在双门禁报告里展开为 `U-M2-15`（见 `05_raven_risk_report.md` M2 段）——
   实测「**目录**符号链接 pack 在冻结工具侧（`pack_sign.py` / `verify_pack.py`）判绿」
   （两个工具的 `rglob("*")` 只跟随文件的 `is_file()`，**目录**符号链接不入遍历 ⇒ 整棵子树被跳过）；
   而内核侧 `load_pack` 的 `_assert_within_root` 对目录符号链接**会拒收**。因此必须写明：
   **`verify_pack: OK` 不等于 pack 无逃逸** —— 冻结工具的 `OK` 只覆盖「签名清单一致性 + 文件级逃逸」，
   目录级逃逸的守卫在**内核侧**（`kernel validate` / `run` 才是权威拒收点）。本轮未改冻结工具（未授权），
   该假设缺口维持「不做、已登记」状态，关闭属 M3/M4。

---

## §显式声明

### 1. `V0_M1.sha256` divergence 全量清单

见 §AC-M2-8（22 条 `02_source` FAILED + 1 条 `spikes` FAILED + 103 条 `spikes` MISSING + 23 条新增），
已与设计 §1.3 预期清单逐条比对（多 2 处 `spikes` 偏差，均给出解释）。

### 2. `state_hash` 是否变化 + `388a1a51…` vs `9a4ae3da…` 的差异（**必写**）

- **`state_hash` 未变化**：末检查点（300 ticks）`state_hash =
  9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f`，
  `chain_tail = baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786`，两者均与设计 F-10 **逐位一致**。
- **`388a1a51…` 是 round-2 见证值、盘上零命中**：本轮 `grep` 复核未在任何盘上产物里找到该值；
  设计要求「必须把 `388a1a51…`（round-2 见证值、盘上零命中）与 `9a4ae3da…`（盘上真值）的差异写进 `06`」，
  故在此登记：**基线判定一律以 `9a4ae3da…` 为锚点**；`388a1a51…` 只能作为文档陈述，
  **不得**当判据锚点（需 PM 提供 round-2 产物路径才能追认其来源）。
- 认知层**不影响**该基线：带与不带 `--cognition --memory` 的 `chain_tail` **逐位相同**
  （`b4a9b6aa…`，见 `spikes/s10-memory/logs/world-state-boundary.json`）；
  设计 §3.4b(3) 声明的「带 `--cognition` 的产物只与自身比、不与 M1 基线比 `rng_state_digest`」照旧成立。

### 3. T-1 / T-2 / T-3 三处判据口径改写（逐条登记）

> 三条已在 `02_source/07_adr.md` 的 ADR-13「后果」节**逐条登记**（该文件 = `refs/07_adr.frozen.md` 逐字 + ADR-13，`grep -c '^## ADR-'` = **13**）。

**T-1 · `tests/test_pack_validate.py::test_seed_projection_passes_world_schema`**

- **改前断言**：`projection`（去 `weather`）过 `world.schema.json`，且「**原样（含 weather）必红**」
  （`with pytest.raises(jsonschema.ValidationError)`）—— 那是契约矛盾（K1）的机器可读证据。
- **改后断言**：**原样**过 `world.schema.json`（单口径）；投影仍在但已退化为恒等；
  新增负例「顶层未声明字段 `humidity` ⇒ 必红」「`weather` 内未声明子字段 `pressure_hpa` ⇒ 必红」；
  原样的两条结构负例（缺 `transform` / `kind` 非法，均在重签后跑）**逐字保留**。
- **为什么不是放松判据**：判据没有变空。它从「schema 拒收 weather」换成「schema **接受** weather
  （与 `$defs/worldSeed` 同构）但**仍然拒收未声明字段**」——牙齿由 `additionalProperties:false`
  的两条负例承担；两条结构负例一字未改。
- **自证反例**：用例内即时构造 `degraded`（删掉 `properties.weather` 的 schema，= 退回改前形态）
  ⇒ 「原样过 schema」那条断言**必红**（已落进用例，非纸面声明）。

**T-2 · `tests/test_pack_validate.py::test_executable_file_in_pack_is_rejected`（② 段）**

- **改前断言**：`_sign(by_magic).returncode == 0`（编码 docstring 自称的「L3 已知缺陷：写侧只按后缀名」）。
- **改后断言**：`_sign(by_magic).returncode **!= 0`** + 输出含结构化 `E_PACK_INVALID`；
  并新增「判据归因」断言（`notes.txt` 的后缀**不在** `FORBIDDEN_SUFFIXES`，而 `executable_kind()` 必须
  返回 `shebang 脚本`）—— 证明拒收来自**内容魔数**而非后缀名。
- **为什么不是放松判据**：**不是把负例改正例**。改名 shebang 内容仍然**必须被拒**，
  只是拒的位置从「只读侧」变成「读写两侧」（判据由 1 处变 2 处，强度只增不减）。
- **自证反例**：`.squad_tools/artisan-p5-revert-negative-control.py` 用仓库 HEAD 的**修复前**工具实测
  写侧 exit **0**（放行）；把 `pack_sign.py` 退回「只按后缀名」⇒ 本用例第一段断言必红。

**T-3 · `tests/test_bus_and_ecs_invariants.py::test_state_passes_world_schema`（反向对照段）**

- **改前断言**：`jsonschema.validate(state + weather)` **必须抛**（牙齿 = schema 拒收 `weather`）。
- **改后断言**（三段，缺一不可）：
  ① 正向：`state` 过 `world.schema.json` **且** `"weather" not in state`；
  ② **反向对照（有牙齿）**：把 `weather` 注入 `state` 副本 ⇒ `canonical_json` / `state_hash`
  **必须与真实值不同**（证明正向断言不是空转）；
  ③ **schema 牙齿保留**：注入**未声明**字段 `humidity` ⇒ `jsonschema.validate` **必须抛**。
- **为什么不是放松判据**：「`snapshot.state` 不得含 `weather`」这条**领域约束一字未改**；
  牙齿从「借 schema 的拒收」（只证 schema 形状）换成「哈希差异 + 领域断言」（证**真实哈希受影响**），
  并另用 `humidity` 负例把 `additionalProperties:false` 的牙齿**原地保留**。
- **自证反例**：用例内即时构造 `relaxed`（去掉顶层 `additionalProperties:false` 的 schema）⇒ ③ 必红；
  ② 已把「正向断言非空转」量化成真实哈希差异。

> **M1 判据强度**：T-1/T-2/T-3 三处均为「判据口径随契约/缺陷状态变化而**等价或更强**」，
> 未删除、未放宽任何一条既有负例；**无**「把负例改正例」「调参绕过」「改冻结措辞」的情形。

### 4. **T-4 判据口径改写（授权清单外，需 architect / PM 追认）**

> **状态：`T-4 → RATIFIED by architect（见 .squad_tools/architect-rulings.md R-1）`**（修复轮 2 回写；
> 附带条件已满足 —— 本状态字段即追认结论的回写落点。任何后续里程碑若再次改变该目录的语义，
> 必须重新登记，不得沿用本次追认。追认**仅覆盖 T-4 一处**；T-1/T-2/T-3 属设计 §1.3 显式授权范围。）

- **文件**：`tests/test_kernel_digest.py`（M1 文件，**不在**设计 §1.3 的 M-7 追加授权清单内）。
- **改前断言**：`test_no_providers_adapters_dir_in_delivery_tree` 断言
  `not (…/deephealing_kernel/providers/adapters).exists()`；原 docstring 明写「属 **W3 面**，
  预审 M4 第 5 条」⇒ 这是 **M1 期的里程碑范围约束**。
- **改后断言**：`test_providers_adapters_dir_is_an_authorized_adapter_face` —— 该目录**存在**
  且**只作 adapter 实现面**（`relation_infer.py` / `__init__.py` 在位），
  并复验 `kernel_digest` 的并集判据对它成立、对**包根新增**仍不成立。
- **为什么必须改**：设计 §3.1 **明列** `providers/adapters/relation_infer.py` 为本轮 W3 授权产物
  （`kernel_digest.py` 的 `ADAPTER_DIRS` 并集口径本就把该目录当豁免面）。落地该授权面**必然**撞上这条
  M1 里程碑约束 —— 属于「授权产物 vs M1 范围断言」的直接冲突，不是顺手改动。
- **为什么不是放松判据**：约束从「禁止新建该目录（W3 前的范围冻结）」换成「该目录存在，
  且**只有**它与 `adapters/` 是新增豁免面，**包根新增仍必须红**」——
  M1 真正要保的性质（新增能力不改既有内核文件）**一字未改**，而且现在有真实文件在守它。
- **自证反例**：用例内把 `ADAPTER_DIRS` 收窄回 `("adapters/",)`（= 退回「不承认该目录」的形态）
  ⇒ 并集正例**必红**。
- **处置**：**最小改写 + 逐条登记（此处 + `07_adr.md` ADR-13 的 T-4 行）+ 在摘要里显式标注需追认**；
  未追认前按「已登记的越界候选」对待，**不静默**。

### 5. 未加固边界（已知残留）

> **修复轮 2 追加（收-1 ~ 收-4，来源 Raven R-M2-4 / R-M2-6 / R-M2-9 / R-M2-10）**：

| # | 项 | 如实声明 |
|---|---|---|
| 收-1 | `--cognition` 的默认 provider 随**环境凭据状态漂移** | 环境里有有效凭据（`HERMES_CUSTOM_TOKENFAB_API_KEY` 可用）⇒ `intent.plan` / `emotion.appraise` 的 `remote_api` provider 真跑（真实调用远端）；凭据缺失或失效 ⇒ `RemoteApiProvider.invoke` 抛 `RemoteApiError` ⇒ 注册表按 `fallback` 链**确定性降级**到 `deterministic_rule`。因此「带 `--cognition` 的产物只与自身比」还必须加「**同环境状态**」二字：跨环境 / 跨时间的产物对比**必须**走 `--replay`（cassette 逐字节回放）或 scrubbed env（先卸载凭据再跑）。否则同一命令在两台机器上会产出**不同**的 `capability.call` 序列（一个 remote_api、一个 deterministic_rule），而这不是缺陷，是契约声明的降级路径 —— 但对比者必须知道。 |
| 收-2 | `spikes/s10-memory/logs/world-state-boundary.json` 里的 `chain_tail b4a9b6aa…` 是**短运行自证值** | 该值 = 「60 ticks、`--cognition` 与否成对对比」这一**实验内部**的链尾，用于证明「认知/记忆层不写世界状态」（两个值逐位相同）。它**不是** M1 基线，**不得**当作 AC-M2-7 的锚点引用。M1 基线比对见 §AC-M2-7：`state_hash = 9a4ae3da…` / `chain_tail = baecca92…`（300 ticks，architect 逐字命令复算）。 |
| 收-3 | 记忆层三层的删除语义**不同** | **`episodes` / `facts` 是软删**：`prune()` 与 `supersede()` 只写 `superseded_by`（行保留，可回滚、可审计 —— `test_memory_layers.py::test_prune_is_soft_and_bounded` 断言「行仍在库」）。**`working` 是易失层**：环形缓冲的容量裁剪就是**物理 DELETE**（`append_working` 的 `DELETE … ORDER BY tick DESC, ref DESC LIMIT -1 OFFSET ?`）—— 短期缓冲本就无审计语义，超容量即淘汰最旧。 |
| 收-4 | `memory.sqlite` **无文件级访问控制** | 「唯一写入点」是**应用层纪律**，不是 OS 级保证：`MemoryStore` 的 `write_enabled` 门（默认关闭 ⇒ 零写入）+ CLI 的 `--memory` 默认关 + 「规则层/认知层一律经 `MemoryStore` 写」的代码纪律。**防篡改**依赖目录权限与进程纪律（sqlite 文件本身可被任何有写权限的进程直接改）。V0 不引入加密/HMAC（属 M3+ 面与 ADR 范畴）。 |

### 6. 未加固边界（M1/M2 既有的 LOW/登记项）

| # | 边界 | 状态 | 说明 |
|---|---|---|---|
| L-1 | manifest 覆盖率判据是**子串**非锚定；两条 `GENERATED_PATTERNS` 可隐藏同名真实文件 | **未加固** | 本轮不改 `verify_specs.sh`（未授权）；已登记为 LOW 遗留，「无幻影条目」由独立探针补齐 |
| L-2 | `verify_specs.sh` 不校验 `world.seed.json` ↔ `world.schema.json` | **未加固** | M1 U7 未变；该面由内核侧 `load_pack` 强口径覆盖 |
| U7 | 同上（起点种子化的 LOW） | **保留** | 沿用 M1 登记 |
| U11 | 符号链接逃逸 | **已关闭** | P-1：`verify_pack.py` / `pack_sign.py` 读写两侧守卫；A/B 两条断言齐备 |
| — | `local_model` provider | **诚实 GAP** | 本机无本地模型服务；只交槽位设计 + `available()=False` 真跑输出；**不宣称跑过** |
| — | `cassette.meta.redacted_fields` | **契约冲突，已登记** | 骨架 docstring 提到 `meta.redacted_fields`，但 `cassette.schema.json` 的 `$defs/meta` 是 `additionalProperties:false` 且无该字段 ⇒ **不能落进记录**。处置：脱敏自证改由 `redaction_report()` 在**记录之外**给出；本轮**不改**冻结 schema（未授权） |
| — | 认知层 `rng_state_digest` 可比性 | **已声明** | 带 `--cognition` 的产物**只与自身比**，不与 M1 基线比 `rng_state_digest`（设计 §3.4b(3)） |
| — | `spikes/red/**` 等 103 条不在本 workspace | **待 architect 复核** | 起点种子化未包含这些路径（见 §AC-M2-8）；上游保留性未由本角色核对 |
| — | `spikes/s5-latency-calibration/calibration.registry.json` divergence | **已解释** | 内嵌绝对路径 ⇒ 跨 workspace 不可移植；种子里已就地重生成（约束文件已知项）；交付须就地重生成 |

### 7. 凭据变量名冲突（REQ 字面 vs 冻结面）

- **REQ §3 字面**：`HERMES_CUSTOM_TOOLFAB_API_KEY` —— 环境里**不存在**（`env | grep -c` = 0）。
- **冻结面声明**：`HERMES_CUSTOM_TOKENFAB_API_KEY` —— 存在、本轮真跑用它会话即用（`env | grep -c` = 1）。
- **实现处置**：凭据变量名**只从能力契约的 `requires_secrets[]` 读**（单一来源），代码里**不硬编码**变量名，
  **不加** `TOOLFAB` 别名回退（会把一个环境里不存在的名字固化进实现，日后同名变量出现会产生来源歧义）。
- **落盘面**：扫描命中 3 处 `TOOLFAB` 字面，全部是 `providers/remote_api.py`（及其隔离副本）里
  「**禁止**加 `TOOLFAB` 别名回退」这条**禁令注释**，不是凭据、也不是可用变量名。
- **需 PM 裁决**：建议更正 REQ §3 的字面为 `HERMES_CUSTOM_TOKENFAB_API_KEY`（本轮不改冻结契约）。

### 8. `verify_specs.sh` 起点 95 ⇒ 收尾 110 的增量来源

+15 条全部来自新增可校验对象：`07_adr.md` 不在 `REQUIRED_FILES` 内但 `manifest` 覆盖检查按文件数增长；
新增 `relation.infer@…capability.json`（能力结构断言 + 标定断言 + 四键断言 + schema 真校验各 1~2 条）、
第二街区 `pack.sig`（`verify_pack.py` 覆盖计数随文件数增长）、新增 JSON 的 `jq` 解析条目。
**无一条是「放松后新增的绿灯」**：`SKIP` 仍为 0、`FAIL` 为 0。

---

## §修复轮 2（第 1 轮双门禁后的修复与登记）

> 本节由修复轮 2 追加。第 1 轮双门禁结论：**CRITICAL 0** / MEDIUM 4 + 文档级缺口；
> 修复项来源：`04_sentinel_test_report.md` M2 段、`05_raven_risk_report.md` M2 段、
> architect 裁决 `.squad_tools/architect-rulings.md`（R-1 ~ R-4）。

### 修-1 · R-M2-1（MEDIUM）· pins 多版本旁路 —— 已修复

- **缺陷**（architect 独立复现）：`validate()` 对 pin 只做**存在性**校验（pin 指向的版本不在盘上才报错），
  **不参与 `capability(slot)` 的版本解析** ⇒ 投放 `relation.infer@9.9.9` 副本 + pins 钉 `1.0.0` 时
  `validate()` 返回 `[]` 而 `capability()` 解析到**未钉**的 `9.9.9` —— 「回滚只需改 pins（纯数据）」失效。
- **修复**：`registry.py` 新增 `_pins` 缓存 + `_pinned_version()` + `_resolve_by_slot(pins)` ——
  **pin 钉住的版本在解析时胜出**；pin 指向不存在的版本 ⇒ `validate()` 报
  `E_CAP_VERSION_CONFLICT`（不得静默取唯一现存版本）。
- **关闭判据（三条全过）**：`tests/test_pins_resolution.py` **7 passed**，exit 0：
  ① 投放 `@9.9.9` + pins 钉 `1.0.0` ⇒ `capability("relation.infer")["version"] == "1.0.0"`（含端到端
  `invoke` 证据：`test_pinned_version_actually_served_by_invoke` 实测 provider 收到的 capability 文档就是 1.0.0）；
  ② pins 钉 `3.3.3`（不存在）⇒ `validate()` 非空且含 `E_CAP_VERSION_CONFLICT`，`capability()` fail-closed 抛错；
  ③ **负例自证**：`test_negative_control_ignoring_pin_makes_criterion_1_red` 用 monkeypatch 复现修复前形态
  （pin 不参与解析 + `_by_slot` 按文件遍历后写者覆盖）⇒ `capability()` 解析到 `9.9.9` ⇒ 判据 1 **变红**。
- 回归：单版本能力无 pin 不受影响（`test_single_version_capability_unaffected`）。

### 修-2 · R-M2-2（MEDIUM）· cassette miss 在命令层不可见（exit 0）—— 已修复

- **缺陷**（architect 独立复现 `/tmp/arch-m2-r2b`）：`run --cognition --replay --cassette-dir <空>`
  ⇒ **exit 0**、无 `E_CASSETTE_MISS` 诊断、`summary.fallback_counts == {}`、无 fail-closed 计数；
  journal 里是 `cognition.degraded`（5 条）。方向正确（`capability.call = 0`，**绝不静默切远端**），
  但只看 exit 的自动化验收会把 fail-closed 读成绿。
- **根因**：`behaviour_tree.tick` 的 action 节点 `except Exception → FAILURE` 把 `CassetteMiss`
  吞成普通分支失败（selector 转下一条分支），miss 因此**永远到不了命令层**。
- **修复（两条都做）**：
  1. `rules/behaviour_tree.py`：action 节点**先捕 `CassetteMiss` 并原样向上抛**（不吞）；
     `cli._run_cognition` 显式 `except CassetteMiss` 结构化落 journal（`fail_closed: true`）；
     `cmd_run` 在 `_run_cognition` 返回后检查 `fail_closed_events`，> 0 ⇒ stderr 打印结构化
     `E_CASSETTE_MISS: replay mode had N cassette miss(es) …`（无 traceback）+ **exit 1**。
  2. `summary.json` 顶层新增 **`fail_closed_events: N`**（= journal 里 `cassette.miss` 条数）
     与 **`degraded_reasons`**（miss 发生的槽位列表），使「有 miss」在产物里一眼可见。
- **关闭判据（四条全过）**：`tests/test_cassette_miss_cli.py` **4 passed**，exit 0：
  ① replay + 空 cassette ⇒ exit **1** + stderr 结构化 `E_CASSETTE_MISS` + **无 `Traceback`**；
  ② `summary.fail_closed_events == 10` == journal 里 `cassette.miss` 条数（`test_summary_fail_closed_count_matches_journal`），
     且 `fallback_counts == {}`、journal 无任何 `capability.call`（**没有降级、没有切远端** —— 方向保持）；
  ③ **负例自证**：`test_negative_control_exit_zero_makes_criterion_red` 通过**测试钩子**
     `DH_NEGATIVE_HIDE_CASSETTE_MISS=1` 复现修复前形态（miss 被吞 + 从汇总抹掉）⇒ exit 回到 **0**、
     `E_CASSETTE_MISS` 诊断消失 ⇒ 判据 ① 两条**都变红**；且盘上 journal 仍记录 miss（信息不丢，只是不再 fail-closed —— 这正是缺陷形态）；
  ④ **回归**：正常回放（先录制齐全的 cassette，含 `--memory` 使 `embed.text` 也被录制）⇒ **exit 0**、
     15 次 `capability.call` 全部 `cassette_replay`、`fail_closed_events == 0`（正常路径未被判红）。
- **测试钩子的边界声明**：`DH_NEGATIVE_HIDE_CASSETTE_MISS` **仅供**负例自证使用；
  生产路径设置它 = 绕过 fail-closed 语义（属判据放松），钩子已在代码注释里写明。
- **明确不做**（任务书 §3）：不通过「删/绕 cassette 回放路径」消除 miss；不动 `--ticks`；不放松任何契约判据。

### 修-3 · Sentinel Bug#1（MEDIUM）· `06` 的 kernel_digest 数字与盘上证据不符 —— 已更正

- **事实**：本文件原写 `digest_before = 56dd3538…` / `digest_after = 8cebd74f…`；
  盘上证据（`spikes/s8-registry/logs/kernel-digest-evidence.json`、`03_artisan_self_test.log`、
  Sentinel 独立复算）均为 `4f22e6cb…` / `44570f54…`。属「自述文字未随最终重跑更新」。
- **更正**：§AC-M2-2 与 §AC-M2-6 的四个数字已改为盘上真值，并注明更正来源。
- **关闭判据（修复轮 3 修正自报计数，收-7）**：该判据的**机器可读形态**是「判据复述不得再用旧值」——
  旧值只允许出现在**更正说明本身**（即本节与 §AC-M2-2/§AC-M2-6 的括注）。artisan 在修复轮 2 自报
  「旧值 grep = 2」，Sentinel 复验实测为 **4**（更正说明里的缩写 `56dd3538…`/`8cebd74f…` 与
  全长哈希各计一次所致）—— 再次证明「自报 grep 计数」不可靠。**修复轮 5（收-7 修正）**：原断言把**节级范围写成行级**，
 且断言文本**自命中**（`grep -n '56dd3538\|8cebd74f' 06 | grep -v 更正` 实测 **3 行**，
 不是声称的 0）⇒ 改为**带范围 + 自排除**的形态，并按字面复跑贴读数（workdir = `{ws}`）：

  ```
  $ sed -e '/^### 修-3/,/^### 修-4/d' 06_v0_m2_self_test.md | grep '56dd3538\|8cebd74f' | grep -v 更正 | wc -l
  0          # 不变式：节外且非更正行 ⇒ 旧值不得被判据复述行复用
  $ sed -n '/^### 修-3/,/^### 修-4/p' 06_v0_m2_self_test.md | grep -c '56dd3538\|8cebd74f'
  5          # 节内命中（= 更正说明 + 本节断言文本自身，属允许范围）
  ```

 即：**旧值的合法落点只有两类** —— 本节（修-3）内的更正说明，以及 §AC-M2-2/§AC-M2-6 里
 含「更正」二字的括注行；其余任何位置出现旧值 ⇒ 断言变红。
 - architect 裁决 R-2：判据结论不受影响（`changed == []`、`added ⊆ adapter 面` 成立且被两方独立复现）。

### 修-4 · T-4 追认回写 —— 已完成

- architect 裁决 **R-1：RATIFIED**（`.squad_tools/architect-rulings.md`）。
- 已回写：§显式声明 4 顶部状态行
  **`T-4 → RATIFIED by architect（见 .squad_tools/architect-rulings.md R-1）`**，
  并写明附带条件（后续里程碑再改该目录语义须重新登记；追认仅覆盖 T-4 一处）。
- 关闭判据（修复轮 3 修正自报计数，收-7；**修复轮 5 再修正断言形态**）：artisan 修复轮 2 自报
  「`grep -c 'RATIFIED'` = 1」，Sentinel 复验实测为 **4**（状态行 + ADR-13 T-4 行 + 本节 + §显式声明 4 引文）。
  原断言用**全文全串计数** ⇒ 被「本节引文 + 断言文本自身」污染（按字面实测 **3**，不是声称的 1）。
  改为**带行首锚点 + 范围**的形态，按字面复跑贴读数（workdir = `{ws}`）：

  ```
  $ grep -c '^> \*\*状态：`T-4 → RATIFIED by architect（见 .squad_tools/architect-rulings.md R-1）`' 06_v0_m2_self_test.md
  1          # 不变式：状态行（判定要求的落点）恰好 1 处
  $ sed -n '/^## §显式声明/,/^## §修复轮 2/p' 06_v0_m2_self_test.md | grep -c 'T-4 → RATIFIED by architect'
  1          # 对照：§显式声明节内全串命中（引文不在本节内 ⇒ 仍为 1）
  $ grep -c 'T-4 → RATIFIED by architect（见 .squad_tools/architect-rulings.md R-1）' 06_v0_m2_self_test.md
  4          # 旧口径留档：= 状态行 + §修-4 引文 + 上面两条断言命令文本自身 ⇒ 不能用（自命中）
  ```

### 收-1 ~ 收-5（文档级，见 §显式声明 5 表格）

四条 Raven 文档级发现（R-M2-4 环境漂移 / R-M2-6 短运行自证值 / R-M2-9 删除语义 / R-M2-10 无文件级访问控制）
已以「收-1 ~ 收-4」逐条写进 **§显式声明 5（修复轮 2 追加表）**；R-M2-3（目录符号链接 + `verify_pack: OK`
不等于无逃逸）已补进 **§本轮不做项第 5 条**（指向 Raven `U-M2-15`）。全部为文档回写，**不改代码**。

---

## §修复轮 3（收口轮）· R2-M1 / R2-M2 修复 + R2-L1/L2 收口

> 第 2 轮修复经双门禁聚焦复验：修-1..4 全部真关闭、CRITICAL 0；对抗复验在**修复引入的新面**上
> 发现 2 条 MEDIUM（R2-M1 slot 冲突旁路 / R2-M2 cassette 篡改仍被树吞）。本节由收口轮追加。

### 修-5 · R2-M1（MEDIUM）· slot 冲突旁路 —— 已修复

- **缺陷**（Raven 实证）：`validate()` 与 `_resolve_by_slot` 按 **id** 聚合版本、pin 按 **id** 查找，
  **slot 维度不在任何判据里** ⇒ 投放一个文件名合法（`relation.infer.rogue@2.0.0`）、`slot` 与真身相同、
  `id` 不同的 rogue 文档 ⇒ `validate()` 返回 `[]`、`capability("relation.infer")` 解析到 rogue
  —— pins 钉住语义被**第三个维度**旁路。
- **修复**：`registry.py` 新增 `E_CAP_SLOT_CONFLICT` reason code；`validate()` 按 slot 聚合**去重的 id 集合**，
  一个 slot 被 ≥2 个不同 id 声明 ⇒ 报 `E_CAP_SLOT_CONFLICT`（含冲突双方 id、各自版本列表与文件路径）；
  冲突期间 `_slot_conflicts` 非空 ⇒ `capability()` **抛错**（fail-closed）、`slots()` 返回空（不半装载）。
- **判据 2 的口径选择（写明理由）**：`capability(slot)` 在冲突形态下选**抛错**而非返回真身 ——
  冲突意味着「哪个文档是权威」无法从数据判定，任何静默取舍都会让审计者拿到与清单不一致的实现；
  调用方应先修数据（去掉 rogue 文档或改 slot）再跑。
- **关闭判据（四条全过）**：`tests/test_slot_conflict.py` **7 passed**，exit 0：
  ① rogue 文档 ⇒ `validate()` 非空且含 `E_CAP_SLOT_CONFLICT`（双方 `id@version` 可见）；
  ② `capability()` 抛 `CapabilityError`（不静默返回 rogue/真身），`slots()` 不半装载；
  ③ **负例自证**：`test_negative_control_without_slot_conflict_check_makes_criterion_1_red`
  用 monkeypatch 复现「不查 slot 冲突」⇒ `validate()` 变空、`capability()` 解析到 rogue ⇒ 判据 1 **变红**；
  ④ **回归**：正常 6 槽 `validate() == []`；`@9.9.9` + pins 钉 `1.0.0` 仍解析 `1.0.0`（**修-1 不回退**）。
- **口径说明**：同 `id` 多版本**不是** slot 冲突（由 pin / `E_CAP_VERSION_CONFLICT` 管辖）——
  首版实现按 `id@version` 计数曾误伤修-1 场景，已改为按**去重后的 id 集合**计数并有回归用例钉住。

### 修-6 · R2-M2（MEDIUM）· cassette 篡改仍被树吞 ⇒ 命令层 exit 0 —— 已修复

- **缺陷**（Raven 实证）：修-2 只把 `CassetteMiss` 提为命令层可见；单条 cassette 记录被改 `output`
  ⇒ 链哈希失配 ⇒ `summary.cassette_chain_errors` 有明细、journal 有
  `provider.error(CassetteTampered)` + `capability.fallback(on_error)`，但 **exit 0**、树 5/5 SUCCESS、
  `fail_closed_events = 0` ⇒ 「被篡改的回放源」在命令层同样读成绿。
- **修复（与 miss 同等可见）**：
  1. `registry.py`：`CassetteTampered` 发生时显式记 **`cassette.tampered`** 事件（`fail_closed: true`）
     —— 它是独立 fail-closed 信号，不是普通 provider 错误；
  2. `rules/behaviour_tree.py`：action 节点 `except CassetteTampered` **原样上抛**（不吞）；
  3. `cli._run_cognition`：显式 `except CassetteTampered` 结构化落 journal；
  4. `summary.json` 顶层新增 **`cassette_tampered_events: N`**（= journal 里 `cassette.tampered` 条数，
     **不得只埋在嵌套字段里**）；`cassette_chain_errors` 仍保留明细；
  5. `cmd_run`：`--replay` 下 `tampered > 0` 或 chain_errors 非空 ⇒ stderr 结构化
     **`E_CASSETTE_TAMPERED`** + **exit 1**。
- **关闭判据（五条全过）**：`tests/test_cassette_tamper_cli.py` **5 passed**，exit 0：
  ① 篡改单条记录（改 `output` 字段保留 JSON 合法性，让**链校验**去抓）⇒ exit **1** +
  `E_CASSETTE_TAMPERED`（无 Traceback）+ `summary.cassette_tampered_events ≥ 1`；
  ② **回归**：干净回放（cassette 齐全未篡改）⇒ **exit 0**、`cassette_tampered_events == 0`、chain_errors 空；
  ③ **回归**：miss 形态仍 **exit ≠ 0**（`test_miss_regression_unchanged`，**修-2 不回退**）；
  ④ **负例自证**：`test_negative_control_tamper_treated_as_warning_makes_criterion_1_red` 用**测试钩子**
  `DH_NEGATIVE_TAMPER_AS_WARNING=1` 复现修复前形态（篡改只记嵌套字段不算失败）⇒ exit 回到 **0**、
  `E_CASSETTE_TAMPERED` 消失 ⇒ 判据 ① **变红**；且 `cassette_chain_errors` 与 journal 篡改事件**仍留痕**
  （信息不丢，只是不再 fail-closed —— 这正是缺陷形态）；
  ⑤ **方向不变**：篡改时 `cassette.tampered` 事件 `fail_closed: true`、fallback 只来自被篡改的那次调用、
  **零回填、零远端切换**。
- **明确不做**（任务书 §2）：不删链校验、不降级为警告、不把 `E_` 诊断降级成 exit 0。

### 收-6 · R2-L2（LOW）· `--replay` 路径与凭据状态正交 —— 已声明

**`--replay` 路径与凭据状态正交**：回放源**缺失**（miss）或**被篡改**（tampered / 链哈希失配）一律
fail-closed（exit 非 0 + 结构化 `E_` 诊断），**不随凭据漂移** —— `--replay` 强制 `cassette_replay` 路由
发生在任何凭据读取之前，miss/tamper 判定只看 cassette 文件本身。这与收-1（**非 replay** 路径的
默认 provider 随凭据状态漂移）是两个不同的面：跨环境/跨时间对比要么全走 `--replay`（正交、可复现），
要么显式声明环境状态（非 replay 路径）。

### 修-8 · 收口轮后**仍然存在**的未加固面（**必填声明**；不得读成「已全面加固」）

| # | 面 | 级别 | 触发条件与边界 | 本轮处置 |
|---|---|---|---|---|
| 1 | **负例自证钩子可绕过命令层 fail-closed**（R2-L1） | LOW | `DH_NEGATIVE_HIDE_CASSETTE_MISS=1`（修-2 钩子）与 `DH_NEGATIVE_TAMPER_AS_WARNING=1`（修-6 钩子）：设置后对应形态的命令层 fail-closed 被绕过、exit 回 0 | **本轮不改钩子**（负例自证的必需品——「退回修复前 ⇒ 门禁变红」必须可复算）。声明：① 两钩子**仅用于**负例自证用例，生产**不得设置**（属判据放松）；② 绕过后 **`cognition.tree_error` / `cassette.tampered` 仍留痕**（journal 与 summary 的 registry_journal 可见），不是完全静默；③ 触发需**攻击者已控制进程环境**（能设环境变量）⇒ 与「攻击者已能改盘上 cassette / 直接跑任意命令」的既有威胁模型重叠，故定级 LOW |
| 2 | 目录符号链接子树不进 `rglob`（R-M2-3 残余 / U-M2-15） | LOW | 冻结工具（`pack_sign.py` / `verify_pack.py`）对**目录**符号链接判绿；内核侧 `load_pack` 会拒收 | 维持「不做、已登记」；`verify_pack: OK` **不等于** pack 无逃逸（权威拒收点在内核侧）；关闭属 M3/M4 |
| 3 | manifest 覆盖率判据是**子串**非锚定（L-1） | LOW | 路径 A 是路径 B 前缀时可被掩盖；`attic-*/*`、`*/dist/*` 两条 GENERATED_PATTERNS 可隐藏同名真实文件 | 本轮不改 `verify_specs.sh`（未授权）；「无幻影条目」由 `.squad_tools/artisan-manifest-sync.py --check` 独立补齐 |
| 4 | `verify_specs.sh` 不校验 `world.seed.json` ↔ `world.schema.json`（L-2 / U7） | LOW | 该面由内核侧 `load_pack` 强口径覆盖 | 保留 U7 登记 |
| 5 | U11 的文件级逃逸已关闭，但工具与内核判据**双实现** | LOW | `pack_sign.py` / `verify_pack.py` / `pack.py` 三处镜像同一判据，由 `test_pack_sign_and_verify_use_same_executable_criteria` 防漂移 | 漂移守卫在位；合并实现属 M3 |
| 6 | `local_model` 诚实 GAP | — | 本机无本地模型服务；`available()=False` 真跑输出；**不宣称跑过** | 维持槽位设计 |
| 7 | cassette 完整性链**无密钥**（FROZEN-CASSETTE-INTEGRITY-1） | 契约边界 | 链只检损坏/篡改，**不是真实性保证**；真实性需外部锚定 | 契约既定边界，非本轮范围 |
| 8 | `memory.sqlite` 无文件级访问控制（收-4） | LOW | 「唯一写入点」是应用层纪律（`write_enabled` 门 + CLI 默认关） | 防篡改依赖目录权限与进程纪律；加密/HMAC 属 M3+ |
| 9 | 非 replay 路径的默认 provider 随凭据漂移（收-1） | 契约声明的降级路径 | 有有效凭据 ⇒ remote_api；无/失效 ⇒ 确定性降级。**r3 更正：对 `embed.text` 不成立** —— 该能力的 remote_api 即使凭据有效也**不可能**成功（通道无嵌入模型），见 §GAP-E1 与 ADR-014 | 跨环境对比必须 `--replay` 或 scrubbed env（使用方纪律） |
| 10 | 认知层 `rng_state_digest` 只与自身比（§3.4b(3)） | 声明边界 | 带 `--cognition` 的产物不与 M1 基线比 `rng_state_digest` | 照旧成立 |

### GAP-E1 · `embed.text` 的 `remote_api` 结构性不可用（PM r3 变更单；architect 独立复核）

- **声明（必须显式，不得被「注册表支持四类 provider」这类整体性表述覆盖）**：`embed.text` 的 `remote_api`
  provider 在 tokenfab 上**永不可能成功** ⇒ 该 provider **实质不可用**，且非回放态**每次调用都会发出一次注定失败的请求**。
- **PM 实测（脱敏，可复算）**：

  ```
  RemoteApiProvider().invoke(embed.text cap, {"texts":[...]}, timeout_ms=30000)
    → RemoteApiError: remote_api HTTP 404 on /embeddings
  同适配器 intent.plan（/chat/completions）同次探测 SUCCESS ⇒ 404 专属 embeddings 端点
  POST /v1/embeddings {"model":"text-embedding-3-small"} → 404 model_not_found
  tokenfab /v1/models：19 个模型，含 "embed" 的 0 个
  备选 ca-free 无凭据（HERMES_CUSTOM_CA_FREE_API_KEY 不存在）
  证据面：录制产物只有 embed.text__deterministic_rule.jsonl，无 embed.text__remote_api.jsonl
  ```

- **architect 独立复核（凭据只以布尔形式出现，不落任何值）**：

  ```
  HERMES_CUSTOM_TOKENFAB_API_KEY present: True (len=48)
  HERMES_CUSTOM_TOOLFAB_API_KEY  present: False
  POST https://api.tokenfab.cn/v1/embeddings {"model":"text-embedding-3-small","input":["hello"]}
    → HTTP 404 {"error":{"code":"model_not_found",
                "message":"model \"text-embedding-3-small\" does not exist"}}
  ```

  ⇒ 404 是 `model_not_found`（**模型不存在**），不是路由不存在 —— 通道**根本没有嵌入能力**。
- **L205 误导表述已纠正**：该行 `embed.text` 的 5 条录制**全部是 `deterministic_rule`**，远端从未成功过一次。
- **契约收敛（本变更单已落地，两处数据改动）**：
  ① `remote_api.priority` **10 → 90**（从默认优先级摘掉）；② `cassette_replay.priority` **20 → 50**。
  不可用性写入既有的 `determinism_note`（`capability.schema.json` 对 `providers[].items` 是
  `additionalProperties: false` ⇒ **不能新增字段**，不可用性只能落在既有字段上）。
  登记面：`02_source/07_adr.md` **ADR-014** + `02_source/manifest.txt`。
- **为什么是两处而不是一处（负例自证，实测可复算）**：只降 `remote_api`（`cassette_replay` 留 20）⇒ 非回放第一顺位
  变成 `cassette_replay` ⇒ 录制态无 cassette ⇒ miss ⇒ **`E_CAP_FALLBACK_UNRESOLVED`（exit 1，录制被打破）**。
  实测两条命令（均在交付树外的只读副本上跑，`PYTHONDONTWRITEBYTECODE=1`）：

  ```
  # 固定树（remote_api=90, cassette_replay=50），干净 cassette 目录
  → {"provider_class":"deterministic_rule","dim":128,"journal_events":["provider.error","capability.fallback"],
     "remote_api_attempted":false}                                  # 无 404 流量

  # 负例（只把 cassette_replay 退回 20）
  → deephealing_kernel.registry.CapabilityError: E_CAP_FALLBACK_UNRESOLVED:
    embed.text has no structured fallback for on_cassette_miss      # EXIT=1（变红）
  ```

- **副作用（显式）**：非回放默认路由 = `local_model`(30) → `E_LOCAL_MODEL_UNAVAILABLE`
  → fallback `deterministic_rule`(40)。即 `embed.text` 在 M2 **真实可用**的 provider 只有
  `deterministic_rule` **一类**；`local_model` 是诚实 GAP。回放态不受影响（`--replay` 强制 `cassette_replay`）。
- **M3 待办**：恢复远端嵌入的前提是**先实测出一个真实存在的嵌入通道**（端点 + 模型 id 均实测通过），
  再回填 `priority` / `model`；**不许按「应当有」写**。

### 修复轮 3 的门禁重跑（实测）

全部真跑记录见 `03_artisan_self_test.log` 的「修复轮 3」段（生成脚本
`.squad_tools/artisan-append-03-fix3.py` 当场捕获，含命令 / workdir / exit / 关键输出）。

**摘要（实测值）**：

| 判据 | 实测 | exit |
|---|---|---|
| `tests/test_slot_conflict.py`（修-5 全判据 + 负例 + 回归） | **7 passed** | 0 |
| `tests/test_pins_resolution.py` + `tests/test_capability_registry.py`（修-1 回归） | **13 passed** | 0 |
| `tests/test_cassette_tamper_cli.py`（修-6 全判据：篡改可见 ①、干净回放回归 ②、负例自证 ④） | **5 passed** | 0 |
| `tests/test_cassette_miss_cli.py`（修-2 回归 ③：miss 仍 exit 1 + 负例） | **4 passed** | 0 |
| `bash verify_specs.sh --quiet` | `OK (110 checks passed, 0 skipped)` | 0 |
| manifest 穷尽 + 无幻影（`artisan-manifest-sync.py --check`） | 135 文件 / 缺失 0 / 幻影 0 | 0 |
| 基线复算 `000300.json` 的 `state_hash` | **`9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f`**（逐位不变） | 0 |
| 残渣扫描（`__pycache__` / `.pytest_cache` / `*.pyc`） | **0** | — |

### `V0_M2.sha256` 重取登记（设计 §8 规则；修复轮 3）

- **重取理由**：修复轮 3 改动 `02_source` 冻结面（`registry.py` 修-5/修-6、`cli.py` 修-6、
  `rules/behaviour_tree.py` 修-6）、新增测试（`test_slot_conflict.py`、`test_cassette_tamper_cli.py`）、
  `manifest.txt` 补 2 行、根级 `06` / `03` 更新 ⇒ 原清单失配，必须重取。
- **变更文件清单**：上述 5 个实现/测试文件 + `manifest.txt` + `06_v0_m2_self_test.md` + `03_artisan_self_test.log`
  + `.squad_tools/artisan-{append-03-fix3,recollect-v0m2,manifest-sync}.py` + `spikes/**` 证据重跑产物；
  另有一处口径修正：`spikes/s9-rules/logs/v0m2-recollection.json`（重取动作**自身的**输出，内含采集前哈希）
  **自引用必失配** ⇒ 排除出冻结面（06/03 以文件名引用，内容可由脚本随时复算）。
- **前后哈希**：逐文件 旧 → 新 见 `spikes/s9-rules/logs/v0m2-recollection.json`
  （修复轮 3 实测 drift：changed 1（03 追加后）/ entries **237** / removed 1（自引用排除））。
- **重取后自校验**：`shasum -c V0_M2.sha256` ⇒ **0 非 OK**（237 条全 OK，实测）。

### `V0_M2.sha256` 重取登记（收尾补完 · 采集顺序错误修正）—— 06 **最后一次**修改

- **重取理由**：收口轮（修复轮 3）**收尾顺序错误** —— `V0_M2.sha256` 采集**早于**
  `06_v0_m2_self_test.md` / `02_source/07_adr.md` / `02_source/manifest.txt` 的**最后一次写入**
  （实测：V0_M2 于 16:30 采集，06 于 16:31 又被写入，07_adr.md / manifest.txt 在采集后仍有改动）
  ⇒ **采集后静默改动**（设计 §8 明令禁止的顺序）。PM 终验第 12 条要求「`V0_M2.sha256` 重校验
  **0 非 OK**」⇒ 当前**必红**（`shasum -a 256 -c` 实测 3 条 FAILED：
  `02_source/07_adr.md`、`02_source/manifest.txt`、`06_v0_m2_self_test.md`）。
- **变更文件清单**（相对上一版 `V0_M2.sha256`，即修复轮 3 登记版）：
  `06_v0_m2_self_test.md`（本节登记 + 前次登记段微调）、`02_source/07_adr.md`、`02_source/manifest.txt`；
  除上述 3 个外**无其它**（`02_source/**` 源码、`refs/**`、根级 M1 冻结文件、双门禁报告均未动）。
- **前后哈希**：
  - 重取前 `V0_M2.sha256` 文件自身 sha256 = `c94219152c28bf512410bfb76426ce1c1120fe30580f8c0ac520780acc3c4e3b`；
  - 重取后 `V0_M2.sha256` 文件自身 sha256 不再登记 —— `V0_M2.sha256` **不在冻结面清单内**（采集面为
    `02_source` + 指定 `spikes/*` 子集 + `03`/`06` 两个根级文件），登记自身哈希会造成
    「登记→重取→登记过期」的自指漂移；验收判据是**清单内全部条目** `shasum -a 256 -c` 0 非 OK。
- **本次重取后自校验**：`cd {ws} && shasum -a 256 -c V0_M2.sha256` ⇒ **0 非 OK**（全部条目 OK，实测见 03 收尾补完段/本节下方命令输出）。

### `V0_M2.sha256` 重取登记（设计 §8 规则）

- **重取理由**：修复轮 2 改动了 `02_source` 冻结面（`registry.py`、`cli.py`、`rules/behaviour_tree.py`）
  与根级产物（`06_v0_m2_self_test.md`、`03_artisan_self_test.log`），并新增测试文件
  （`test_pins_resolution.py`、`test_cassette_miss_cli.py`）⇒ 原清单失配，必须重取。
- **变更文件清单**（相对上一版 `V0_M2.sha256`）：上述 5 个改动文件 + 2 个新增测试文件 + `06` 本身 +
  `.squad_tools/artisan-*.py` 探针更新 + `spikes/**` 证据重跑产物。
- **前后哈希**：见 `spikes/s9-rules/logs/v0m2-recollection.json`（逐文件 旧哈希 → 新哈希）。
- **重取后自校验**：`shasum -c V0_M2.sha256` ⇒ **0 非 OK**（实测见 03 修复轮 2 段）。

---

## §凭据面（扫描命令 + 命中数 + 注入探针结果）

**扫描命令**：

```
cd {ws} && python3 .squad_tools/artisan-ac-m2-8-and-credential-scan.py
```

**结果**（exit **0**）：

- 扫描文件数：**624**（`02_source/**` + `spikes/**` + `.squad_tools/**` + 根级本轮产物）；
- 判据：① 键名（`api_key|apikey|authorization|access_token|auth_token|client_secret|secret_key|password|passwd`
  + ≥16 字符值）② 值形态（`sk-…` / `Bearer …`（非 `***REDACTED***`）/ `ghp_…` / `xox…`）
  ③ 环境变量值逐字（能力契约声明的变量名取值）；
- **凭据值命中数 = 0**（非「工具名字面」命中 = **0**；仅 3 处 `toolfab_literal` = 禁令注释，见 §显式声明 6）；
- **注入探针结果**：写入假值 `api_key = "sk-9f4c…"`（不含夹具标记）⇒ 扫描**命中**
  （判据 `key_name` + `value_shape`）；删除探针后非工具名命中回到 **0** ⇒ **扫描器有牙齿**；
- 证据：`{ws}/spikes/s8-registry/logs/ac-m2-8-and-credential-scan.json`

**脱敏纪律落实**：日志/报告里的 Authorization 一律 `Bearer ***REDACTED***`；
请求体只记 canonical 化摘要（`canonical_input_hash`），**不记原始请求体**；
时间/追踪类响应头（`Date` / `x-request-id` / `cf-ray` / `server-timing` …）由
`remote_api.redact_headers()` **整条剥离**，不进 cassette；**凭据值不落任何盘上文件**。

---

## §交付物清单（本轮）

**根级**：`03_artisan_self_test.log`（M1 段逐字保留 + M2 段）、`06_v0_m2_self_test.md`（本文件）、`V0_M2.sha256`
**`02_source/`**：`07_adr.md`（13 条 ADR）、`capability.schema.json`、`world.schema.json`、`manifest.txt`（133 行）、
`v0_skeleton/kernel/deephealing_kernel/{registry,budget,pack,cli}.py` + `providers/**` + `rules/**` + `memory/**`、
`v0_skeleton/capabilities/**`（6 能力 + `pins.json`）、`v0_skeleton/districts/{xingfu-xiaoqu,xingfu-xiaoqu-north}/**`、
`v0_skeleton/tools/{pack_sign,verify_pack}.py`、`v0_skeleton/kernel/tests/**`（含 4 个新增用例文件）
**`spikes/`**：`s8-registry/**`（注册表/凭据/U11/P-5 证据 + baseline 快照 + cassette 产物）、
`s9-rules/**`（P-4 四元组 + revert 反例）、`s10-memory/**`（三层/唯一写入点/逐字节比对器/负例）、
`s11-pack2/**`（第二街区 validate/run/verify 产物）

---

## §修复轮 5 · R4-C1（CRITICAL）修复 + 收-7 断言修正（2026-09-22）

> 来源：architect 裁决 `.squad_tools/architect-ruling-r4c1.md`（**CRITICAL 成立**，三方独立复现）
> + PM 复现配方 `.squad_tools/pm_repro_r4c1.sh`（**原样跑，未改一行**）。本轮只修这一条 CRITICAL
> 与一条 LOW 文档级缺口（收-7）；方案决定登记在 `02_source/07_adr.md` **ADR-015**。
> 本节由修复轮 5 追加；`06` 在此之前的内容**未删改**（除 §修-3/§修-4 的收-7 断言按本节 5.5 就地修正）。

### 5.1 快照与写集

- 真实仓库：`/Users/wooyinq/personal/deep-healing` · branch `develop` · HEAD `f5f77622b9c9` ·
  `git status --porcelain` **0 行**（开工与收工同值；全程未 `add`/`commit`/`push`/部署）。
- 落地写集（逐条实测）：`02_source/v0_skeleton/kernel/deephealing_kernel/registry.py`（F-1/F-2）、
  `.../deephealing_kernel/providers/cassette.py`（F-3/F-3b）、
  `.../kernel/tests/test_cassette_no_backfill_r5.py`（F-4，**新增**）、`02_source/07_adr.md`（ADR-015）、
  `02_source/manifest.txt`（补 1 行 + 就地更新 2 行）、本文件（`06`）、`03_artisan_self_test.log`、
  `V0_M2.sha256`（重取）、`.squad_tools/artisan-r5-*`。**未动** `01_architecture_design.md` / `refs/**` /
  `04`/`05` / `06_v0_m1_self_test.md` / `V0_M1.sha256` / `SEED.sha256`。
- 探针隔离：**全部**复现 / 负例 / 形态矩阵都在 `/tmp/artisan-r5/**` 的整树副本上跑
  （`PYTHONDONTWRITEBYTECODE=1`）；交付树残渣实测 **0**（见 5.6）。

### 5.2 RED —— 先复现缺陷（PM 配方**原样**跑；`/tmp/artisan-r5/repro-before`）

```
$ cd {ws} && bash .squad_tools/pm_repro_r4c1.sh /tmp/artisan-r5/repro-before
=== ① 同 seed 录制（不带 --replay）===
  rec exit=0
  录制: 3 文件
=== ② 篡改 relation.infer 最后一条（不断链）===
  篡改索引 4，条数 5
  跑前: 3752b5a939e05ffc0037a947 / 5 条
=== ③ 回放（--cassette-dir 指向被篡改的源）===
  rep exit=1  诊断=E_CASSETTE_TAMPERED
=== ④ 源目录 diff（★核心判定）===
  ❌ 回填成立：源被改写
     3c3
     < 3752b5a939e05ffc0037a9479847bd08e42917238b5ff77ca13b3f07c519bfa5  relation.infer__deterministic_rule.jsonl
     ---
     > 80ef5a955fbb4137d00684a541a850f2c07ff1ab45471c9ac3130d539c871a5b  relation.infer__deterministic_rule.jsonl
  relation.infer 条数: 跑前 5 / 跑后 6
=== ⑤ 降级证据 ===
   {"slot": "relation.infer", "provider": "deterministic_rule", "fallback_reason": "on_error", "ok": true}
```

> 绝对 sha 与 architect 裁决里的 `d41c4451…` 不同属**预期**：cassette 记录含 `meta.recorded_at`，
> 文件 sha 随运行时刻变化。判据是**不变式**：「条数 5 → 6 / 目录 sha 变化 / exit=1 + `E_CASSETTE_TAMPERED`」，
> 这三条与裁决读数逐条一致。

### 5.3 F-1 / F-2 · 回放态**零回填**（代码，最小修复）

- **F-1**：`_fallback()` 新增显式入参 `replay_mode`（**生效值**，由 `invoke()` L391 的
  `bool(replay_mode or self.default_replay_mode)` 解析后传入），三处调用点（`on_budget_exhausted` /
  provider 异常 / `on_invalid_schema`）全部传入；`_fallback()` 内的 `record()` 以 `not replay_mode` 为守卫。
  **不读 `self.default_replay_mode`** —— `invoke(replay_mode=True)` 与构造参数不一致时会漏判（有专门用例钉住）。
- **F-2**：`invoke()` 主路径的 `record()`（`remote_api` / `deterministic_rule`）同样以生效 `replay_mode` 为守卫。
  `--replay` 下该路径正常不可达（路由强制 `cassette_replay` + L411 fail-closed），但 `force_provider` 可触达 ⇒ 一并堵。
- **留痕（新增，非判据）**：回放模式下被抑制的回填落 journal 事件
  `cassette.record_suppressed{slot, provider, reason, replay_mode}` —— 「零回填」不等于「零痕迹」，
  审计面必须能看见「这里本来会写」。
- **根因（一句话）**：录制与回放两条路径**共用同一段录制代码**，`_fallback()` 的签名里没有 `replay_mode`、
  也从不读回放开关 ⇒ 没有任何开关区分二者；改动把「生效回放态」显式带进该函数，回放态一律不写盘。

### 5.4 F-3 / F-3b · `verify_chain()` 判据补齐

- **F-3（新增判据）**：同一文件内**同一 key 出现两次** ⇒ 记 problem（冻结条文 `cassette.format.md`
  §4.1.2 / §6 / §5.1 已点名「重复 key = 文件损坏 ⇒ `E_CASSETTE_TAMPERED`」，此前**零告警**）。
  回填产生的追加记录**链上完全自洽**（`prev_hash` = 前一条 `key`、`hash` 自签），因此只有这条判据能抓它。
- **F-3b（`prev_hash`-only 形态）**：**实测该形态已被现有两条判据覆盖，`verify_chain()` 未做结构性改动**，
  由新增用例 `test_prev_hash_only_tamper_forms_are_rejected` 钉住。形态矩阵（`/tmp/artisan-r5/probe` 整树副本，
  `PYTHONDONTWRITEBYTECODE=1`；同一夹具、修复前后各跑一次）：

| 形态 | 构造 | 修复**前** | 修复**后** |
|---|---|---|---|
| `clean` | 未篡改回放（对照） | exit 0，`verify_chain=[]` | exit 0，`verify_chain=[]` |
| `p1_prev_hash_only` | 末条只改 `prev_hash`（不重签） | exit 1 + `E_CASSETTE_TAMPERED`（`prev_hash mismatch` + `hash mismatch`） | exit 1 + `E_CASSETTE_TAMPERED`（同） |
| `p2_prev_hash_resigned` | 末条改 `prev_hash` **并自洽重签**自身 `hash` | exit 1 + `E_CASSETTE_TAMPERED`（`prev_hash mismatch`） | exit 1 + `E_CASSETTE_TAMPERED`（同） |
| `p3_dup_key_append` | 自洽追加一条**同 key** 记录（= 回填签名） | **exit 0**，`verify_chain=[]`，`summary.cassette_chain_errors=[]` | **exit 1 + `E_CASSETTE_TAMPERED`**，`verify_chain=['…:5 duplicate key c12b3b96… (same key appears more than once in file)']` |
| `p4_tail_truncate` | 删末条（自洽前缀） | exit 1 + `E_CASSETTE_MISS`（被删记录恰是被命中那条） | exit 1 + `E_CASSETTE_MISS`（同） |

  ⇒ **r3 的「仅改 `prev_hash` ⇒ exit 0」本轮独立复跑不可复现**（与 r4 结论一致）；
  真正零告警的一格是 **p3（重复 key）**，已由 F-3 关闭。
- **未加固面（诚实标注，不许写成已解决）**：`p4` 的**自洽前缀截断**在本夹具里因「被删记录恰被命中」
  才转成 `E_CASSETTE_MISS`；若截掉的是**从未被命中的尾部记录**，链仍自洽 ⇒ 仍无判据（需**外部锚定**：
  链头签名 / 时间戳载体）。同族还有**整链重签**（R4-L4）。二者均属 `FROZEN-CASSETTE-INTEGRITY-1`
  已声明的强度边界，V0 无锚定实现 ⇒ **仍记 GAP**，不因本轮修复而改变。
- **另一处口径差距（登记，不扩写集）**：`lookup()` 命中路径只校验**命中记录自身**的 `hash`，
  未复核整文件 `prev_hash` 链，与冻结 §4.3① 的字面（「命中即校验该文件的 hash 与文件内 prev_hash 链」）
  仍有差距；本轮补偿是命令层 `verify_chain()` 对**全库**判红（exit ≠ 0）。逐字对齐留 M3。

### 5.5 F-4 / F-5 · 测试、负例自证与收-7 断言修正

- **F-4 新增用例**：`02_source/v0_skeleton/kernel/tests/test_cassette_no_backfill_r5.py`（7 条）：
  ① 篡改回放 ⇒ 源目录**跑前/跑后全量 sha256 逐字节相同** + 仍 exit ≠ 0 + `E_CASSETTE_TAMPERED` +
  `cassette.record_suppressed` 留痕；② 同一 key 重复 ⇒ `verify_chain()` 判红（单元）；③ 重复 key 的
  **命令层可见性**（= 回填签名，修复前 exit 0）；④ `prev_hash`-only 两形态判红（F-3b 钉住）；
  ⑤ **生效 `replay_mode` 显式传参**（构造 `replay_mode=False` + 调用 `replay_mode=True` ⇒ 仍不得写盘）；
  ⑥ 回归：干净回放 exit 0；⑦ 回归：miss ⇒ exit ≠ 0 + `E_CASSETTE_MISS`。
- **负例自证（判据有牙齿）**：把 F-1 守卫退回 `and not (False and replay_mode):`（= 还原无条件 `record()`），
  **锚点命中数断言 = 1**；变异**只发生在 `tmp_path` 的 02_source 整树副本**（交付树源码在用例末尾逐字节复核）。
  退回后同一流程 ⇒ 源目录 sha 变化、条数 **+1** ⇒ ① 变红。读数：
  ```
  $ cd {ws}/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 \
      python3 -m pytest tests/test_cassette_no_backfill_r5.py::test_negative_control_reverting_f1_guard_reproduces_backfill -q -p no:cacheprovider
  .                                                                        [100%]
  1 passed in 107.63s (0:01:47)
  ```
- **F-5 收-7 两条断言（按字面复跑贴读数，workdir = `{ws}`）**：

  ```
  # r6 反自命中构造：被统计的字面串拆成两段变量、运行时再拼接 ⇒ 断言命令文本自身**不含连续字面串**，
  # 「命令文本被统计进去」这一类自命中在结构上不可能再发生（r5 的两条断言正是栽在这里）。
  $ P1='56dd'; P2='3538'; Q1='8ceb'; Q2='d74f'
  $ R1='T-4 → RATIFIED by architect'; R2='（见 .squad_tools/architect-rulings.md R-1）'
  $ sed -n '/^### 修-3/,/^### 修-4/p' 06_v0_m2_self_test.md | grep -c "$P1$P2\|$Q1$Q2"
  5
  $ sed -e '/^### 修-3/,/^### 修-4/d' 06_v0_m2_self_test.md | grep "$P1$P2\|$Q1$Q2" | grep -v 更正 | wc -l
  0
  $ grep -c "^> \*\*状态：\`$R1$R2\`" 06_v0_m2_self_test.md
  1
  $ sed -n '/^## §显式声明/,/^## §修复轮 2/p' 06_v0_m2_self_test.md | grep -c "$R1"
  1
  $ grep -c "$R1$R2" 06_v0_m2_self_test.md
  4
  # 负例（判据有牙）：把「排除更正说明行」的过滤去掉 ⇒ 读数 2 必须 ≠ 0（变红）
  $ sed -e '/^### 修-3/,/^### 修-4/d' 06_v0_m2_self_test.md | grep "$P1$P2\|$Q1$Q2" | wc -l
  2
  ```
  前两条替换原「节级范围写成行级 + 断言文本自命中」的旧断言（旧口径实测 3 行，不是声称的 0）；
  后三条把「状态行恰好 1 处」改为**带行首锚点**的形态（旧口径被本节引文与断言命令文本自身污染 ⇒ 实测 4）。
  断言文本就地更新在 §修-3 / §修-4 两节（**结论不变**：旧值确实只在更正说明与含「更正」的括注行；
  状态行确实恰 1 处）。
- **r6 就地修正（本轮，F-5 复发）**：上列 5 条读数的**命令文本原先自带被统计的字面串** ⇒ 读数 2（0 → **1**）、
  读数 5（4 → **6**）被**命令自身**污染；PM r5 确认轮实测 `5 / 1 / 1 / 1 / 6`，artisan r6 复跑一致。
  修法 = 字面串拆成两段变量拼接（`$P1$P2` / `$Q1$Q2` / `$R1$R2`），命令文本不含连续字面串
  ⇒ 修后读数 **5 / 0 / 1 / 1 / 4**（修前/修后与负例的完整读数见 §修复轮 6）。
  **§修-3 / §修-4 两节内的断言命令文本逐字保留、不defang**：它们落在读数 1 / 读数 5 的**统计范围之内**，
  命中数已被期望值显式计入（读数 1 的 5 = 节内 3 行更正说明 + 2 行节内断言命令文本；读数 5 的 4 =
  状态行 + §修-4 引文 + §修-4 两条断言命令文本）。改动它们会**改动判据本身**，属超范围。

### 5.6 F-6 登记面 + 出口判据逐条读数

| # | 判据（任务书 §5） | 命令（workdir） | 实测 | exit |
|---|---|---|---|---|
| 1 | PM 配方**原样**跑 ⇒ ④ 零回填 | `bash .squad_tools/pm_repro_r4c1.sh /tmp/artisan-r5/repro-after`（`{ws}`） | ④ **`✅ 零回填（未复现）`**；③ `rep exit=1`、诊断 `E_CASSETTE_TAMPERED`；⑤ 降级仍发生（`fallback_reason=on_error`）⇒ 非「零命中假绿」 | 0 |
| 2 | 负例：退回 F-1 守卫 ⇒ ④ 变红 | 见 5.5（副本树变异 + 锚点计数 = 1） | 源目录 sha 变化、条数 +1 ⇒ **判据有牙齿** | 0 |
| 3 | 重复 key ⇒ `verify_chain()` 判红 | 见 5.4 矩阵 `p3` + 用例 ②/③ | `…:5 duplicate key c12b3b96…`；命令层 exit 1 + `E_CASSETTE_TAMPERED` | 0 |
| 4 | `verify_specs.sh --quiet` | `cd 02_source && bash verify_specs.sh --quiet` | **`verify_specs: OK (110 checks passed, 0 skipped)`** | 0 |
| 5 | 全量 pytest | `cd 02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider` | **未完成（GAP，不得写成全绿）**：时间预算耗尽时该跑仍在进行（`-q` 已输出 **45 个通过点、无 FAILED、无 error**，进程被显式终止）。可用的分项读数：`tests/test_cassette_no_backfill_r5.py` 首轮整文件跑 **`5 passed in 342.55s`**（当时 6 条，负例因夹具路径缺陷失败 ⇒ 已修并单跑 **`1 passed in 107.63s`**）；**补入 F-3b 用例后（现 7 条）未取得整文件读数** ⇒ 判据 5 **GAP** | — |
| 6 | 基线 `state_hash` 逐位一致 | `cd kernel && … run --pack districts/xingfu-xiaoqu --seed 20260921 --events {ws}/.squad_tools/artisan-r5-baseline/e.jsonl --snapshot-every 50 --ticks 300` | `checkpoints/000300.json` `state_hash = 9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f`（**逐位一致**）；`chain_tail = baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786` | 0 |
| 7 | `shasum -a 256 -c V0_M2.sha256` ⇒ 0 非 OK | `cd {ws} && shasum -a 256 -c V0_M2.sha256 \| grep -vc ': OK$'` | **0**（见 5.7 重取登记） | 0 |
| 8 | 收-7 两条断言按字面成立 | 见 5.5 | 5 / **0** / **1** / **1** / 4 | 0 |
| 9 | ADR 数 = 15 / manifest 穷尽 / 残渣 0 / 仓库 dirty 0 | `grep -c '^## ADR-' 02_source/07_adr.md`；`python3 .squad_tools/artisan-manifest-sync.py --check`；`find . -name '__pycache__' -o -name '.pytest_cache' -o -name '*.pyc' \| wc -l`；`git -C /Users/wooyinq/personal/deep-healing status --porcelain \| wc -l` | ADR **15**；manifest **138 文件 / 138 行 / 缺失 0 / 幻影 0**；残渣 **0**；dirty **0** | 0 |

### 5.7 逐条回填（本轮任务书 §2 / §5）

| 项 | 内容 | 判定 | 证据 |
|---|---|---|---|
| F-1 | `_fallback()` 回放态不得 `record()`，**生效** `replay_mode` 显式传入 | **PASS** | `registry.py`（三处调用点 + 守卫）；用例 ⑤；`06` 5.6 #1 |
| F-2 | `invoke()` 主路径 `record()` 同源守卫 | **PASS** | `registry.py` L448 区；`force_provider` 路径由守卫覆盖 |
| F-3 | `verify_chain()` 增「同一 key 重复出现」判据 | **PASS** | `cassette.py::verify_chain`；矩阵 `p3`；用例 ②③ |
| F-3b | `prev_hash`-only 形态 | **PASS（已覆盖，无代码改动）** | 矩阵 `p1`/`p2` + 用例 ④；r3 结论不可复现（与 r4 一致） |
| F-4 | 新增测试 + **源码级负例自证** | **PASS（含 1 条待跑）** | `tests/test_cassette_no_backfill_r5.py`（7 条）：①~③⑤~⑦ 有实测读数（5 passed 整文件首轮 + 负例单跑 1 passed）；**第 4 条（F-3b 钉住用例）随文件补入后未取得整文件读数 ⇒ 随判据 5 一并 GAP**；负例读数见 5.5 |
| F-5 | 修 `06` 收-7 两条断言（按字面复跑贴读数） | **PASS** | 5.5；§修-3 / §修-4 就地更新 |
| F-6 | ADR-015 + manifest 穷尽 + `06` 修复段 | **PASS** | `02_source/07_adr.md` ADR-015；`manifest.txt` 138 行；本节 |
| — | 未授权改动 / 门禁产物改动 | **PASS（未发生）** | `01`/`refs`/`04`/`05`/M1 冻结文件均未动（5.1 写集） |

### 5.8 已知风险 / 未覆盖面（诚实清单）

- **自洽前缀截断 + 整链重签**仍无判据（需外部锚定）⇒ `FROZEN-CASSETTE-INTEGRITY-1` 已声明，**GAP 保留**。
- `lookup()` 未复核整文件链（冻结 §4.3① 字面差距）⇒ 命令层 `verify_chain()` 全库判红兜底，**逐字对齐留 M3**。
- 回放态「本应回填」的次数现在只在 journal（`cassette.record_suppressed`）可见，**不在盘上** ⇒
  若下游审计只读盘上产物，会看不到这一信号（判据本身要求零回填，故为**有意**取舍）。
- 负例用例需复制 02_source 整树（1.3 MB）+ 两次 CLI 跑，单条耗时 ~108 s ⇒ 全量 pytest 时长上升
  （实测见 5.6 #5），**不影响判据**。

### 5.9 `V0_M2.sha256` 重取登记（修复轮 5 · R4-C1）

- **重取理由**：本轮改动 `02_source` 冻结面（`registry.py`、`providers/cassette.py`）、新增测试
  （`test_cassette_no_backfill_r5.py`）、`manifest.txt` 补 1 行 + 更新 2 行、`07_adr.md` 追加 ADR-015、
  根级 `06` / `03` 更新 ⇒ 原清单失配，按设计 §8 登记重取。
- **重取方式**：`.squad_tools/artisan-r5-recollect-v0m2.py`（与修复轮 2/3 版**同口径**：采集面
  `02_source/**` + `spikes/{s8-registry,s9-rules,s10-memory,s11-pack2}/**` + 根级 `03`/`06`；
  排除 `*-scratch` / `__pycache__` / `.pytest_cache` / `*.pyc` / `.DS_Store`；**自引用日志排除**，
  旧版 `spikes/s9-rules/logs/v0m2-recollection.json` **保留不覆盖**）。
- **前后哈希**：逐文件 旧 → 新 见 `spikes/s9-rules/logs/v0m2-recollection-r5.json`
  （本轮实测：changed / added / removed 与 entries 见该文件）。
- **采集顺序（设计 §8 纪律）**：本节与 `03` 段**定稿后**才执行最后一次采集 ⇒ **不存在采集后静默改动**。
- **重取后自校验**：`cd {ws} && shasum -a 256 -c V0_M2.sha256` ⇒ **0 非 OK**（见 5.6 #7）。

---

## §修复轮 6 · 文档收口（PM r5 确认轮裁决）（2026-09-22）

> 本轮**只改文档、零代码**：`02_source/**` 的 `.py` / `.json` / capability 文件与 r5 冻结值**逐字节一致**
> （§6.7 #8 的重取 `changed` 清单 = 机器可读证明）。r5 的代码修复（R4-C1 = **PASS**，PM + sentinel + raven
> 三方独立确认关闭）**未被动过**：§修复轮 5 及其以前的全部旧段**逐字保留**，唯一就地改动 = §5.5 的断言命令文本。
> 本节**刻意不复述**两类字面串 —— 旧 `kernel_digest` 值（`56dd…` / `8ceb…`，全长见 §修-3）与 T-4 追认**全串**
> （前缀 `T-4 → RATIFIED by architect`，全串见 §修-4）：它们是读数 2 / 读数 5 的**统计对象**，在统计范围外
> 复述会重演 F-5 同类自命中 —— 这正是本轮要修的东西。

### 6.1 快照与写集

- workdir（= `{ws}`）= `/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-004-deephealing-v0-m2`。
- 真实仓库 `/Users/wooyinq/personal/deep-healing`：`rev-parse --abbrev-ref HEAD` = `develop`，
  `status --porcelain | wc -l` = **0**（本轮**零写入**；未 commit / push / PR / 部署）。
- 本轮写集（**仅文档**）：`06_v0_m2_self_test.md`（§5.5 就地修正 + 本节）、`02_source/07_adr.md`
  （**仅** ADR-015 测试条数 6 → 7）、`03_artisan_self_test.log`（追加 r6 读数）、`V0_M2.sha256`（定稿后重取）、
  `.squad_tools/artisan-r6-*`、`.artisan.progress.json`、`/tmp/artisan-r6/**`。
- **未动**：任何 `.py` / `.json` / capability 文件 / `tests/**`（**零代码改动**）；`01_*` / `04_*` / `05_*` /
  `refs/**` / `SEED.sha256` / `06_v0_m1_self_test.md` / `V0_M1.sha256`；`02_source/manifest.txt`
  （本轮无文件增删 ⇒ 逐字节不变，见 §6.7 #6）。

### 6.2 F-1 RED —— 修前按字面复跑（判据被自身命令文本污染）

| # | 命令（workdir = `{ws}`，**r5 修前形态**） | 期望 | 修前实测 | 污染源 |
|---|---|---|---|---|
| 1 | `sed -n '/^### 修-3/,/^### 修-4/p' 06_v0_m2_self_test.md \| grep -c '<旧值串>'` | 5 | **5** ✓ | — |
| 2 | `sed -e '/^### 修-3/,/^### 修-4/d' … \| grep '<旧值串>' \| grep -v 更正 \| wc -l` | 0 | **1** ✗ | §5.5 中**读数 1 的命令文本自身**（该行含旧值串、且不含「更正」二字 ⇒ 逃过 `grep -v`） |
| 3 | 带行首锚点的状态行 `grep -c`（全串锚定） | 1 | **1** ✓ | — |
| 4 | `sed -n '/^## §显式声明/,/^## §修复轮 2/p' … \| grep -c 'T-4 → RATIFIED by architect'` | 1 | **1** ✓ | — |
| 5 | 全文 `grep -c '<追认全串>'` | 4 | **6** ✗ | §5.5 中**读数 3、读数 5 两条命令文本自身**各含追认全串 |

- **修前实测串**：`5 / 1 / 1 / 1 / 6`（exit 0）—— 与 PM r5 确认轮读数**逐位一致**（artisan r6 独立复跑）。
- **根因**：断言命令写在**被它统计的同一个文件**里，且命令文本**原样包含**被统计的字面串 ⇒ 该行必然自命中。
  读数 2 的 `grep -v 更正` 恰好只挡住「含『更正』二字」的那条自身命令（读数 2 的命令行），挡不住读数 1 的命令行；
  读数 5 是全文全串计数 ⇒ 两条含全串的命令行各 +1。
- 与 F-5 要修的缺陷**同一类**（断言文本自命中），属「修复本身产生新边界」家族。

### 6.3 F-1 GREEN —— 反自命中构造 + 修后读数 + 负例自证

- **修法**（§5.5 就地，**不删段位**）：被统计字面串拆成**两段变量**、运行时拼接
  （`$P1$P2` / `$Q1$Q2` / `$R1$R2`）⇒ 命令文本不再含**连续**字面串 ⇒ 自命中在结构上不可能发生。
- **修后按字面复跑**（workdir = `{ws}`）：

  ```
  $ P1='56dd'; P2='3538'; Q1='8ceb'; Q2='d74f'
  $ R1='T-4 → RATIFIED by architect'; R2='（见 .squad_tools/architect-rulings.md R-1）'
  $ sed -n '/^### 修-3/,/^### 修-4/p' 06_v0_m2_self_test.md | grep -c "$P1$P2\|$Q1$Q2"
  5
  $ sed -e '/^### 修-3/,/^### 修-4/d' 06_v0_m2_self_test.md | grep "$P1$P2\|$Q1$Q2" | grep -v 更正 | wc -l
  0
  $ grep -c "^> \*\*状态：\`$R1$R2\`" 06_v0_m2_self_test.md
  1
  $ sed -n '/^## §显式声明/,/^## §修复轮 2/p' 06_v0_m2_self_test.md | grep -c "$R1"
  1
  $ grep -c "$R1$R2" 06_v0_m2_self_test.md
  4
  ```

- **修后读数**：`5 / 0 / 1 / 1 / 4`（exit 0）—— 与任务书 §4.4 期望**逐位一致**。
- **负例自证（判据要有牙）**：把「排除更正说明行」的过滤（`grep -v 更正`）去掉 ⇒ 读数 2 **变红**：

  ```
  $ sed -e '/^### 修-3/,/^### 修-4/d' 06_v0_m2_self_test.md | grep "$P1$P2\|$Q1$Q2" | wc -l
  2
  ```

  两行 = §AC-M2-2 / §AC-M2-6 的**更正括注行**（含「更正」二字 ⇒ 被正常判据排除；去掉过滤即暴露）
  ⇒ 判据不是「恒零」的假绿。
- **边界声明（不许读成「已全面自免疫」）**：§修-3 / §修-4 两节内的断言命令文本**逐字保留、不 defang** ——
  它们落在读数 1 / 读数 5 的**统计范围之内**，命中数已被期望值 5 / 4 **显式计入**（读数 1 的 5 = 节内 3 行
  更正说明 + 2 行节内断言命令文本；读数 5 的 4 = 状态行 + §修-4 引文 + §修-4 两条断言命令文本）。
  改动它们 = **改动判据本身**，属超范围。

### 6.4 F-2 · 两条 LOW 登记（r5 确认轮 raven）

**(a) `SEED.sha256` 只校验聚合（不是逐行）**

- AC-M2-8 的溯源判据校验的是 `SEED.sha256` **文件自身**的聚合哈希 =
  `34fa7f6d252bc4bf966c8dbc4d639a1f08788ed71b9cfa04a0896ca7ba8f7676`（= M1 起点值，本轮**未被修改**）⇒ **PASS 口径不变**。
- **逐行**复跑（read-only）：`cd {ws} && shasum -a 256 -c SEED.sha256` ⇒ **72 OK / 28 FAILED**，
  另有 1 行 `shasum: WARNING: 28 computed checksums did NOT match` 汇总行 ⇒ **29 行非 OK**（= PM / raven 口径的
  「72 OK / 29 FAILED」），exit **1**。清单共 100 行 = 72 + 28。
- **判定：不是本轮回归。** 逐行清单比的是 **M1 起点字节**，而 M1/M2 期间被**授权**改动的文件
  （如 `02_source/manifest.txt`、`capability.schema.json`、`v0_skeleton/capabilities/*.capability.json`）
  必然失配 ⇒ 属 `06` §显式声明 1 / §AC-M2-8 已登记的 **M1 起点 divergence**。
- **登记（LOW）**：AC-M2-8 的判据文本须明写「**只校验聚合、不校验逐行**」，否则读者会把 29 行非 OK
  误读成「冻结面被破坏」。

**(b) 残渣读数是时间条件量 + demo 世界根因**

- 明写：`残渣 0` 是**时间条件量**，不是不变式 —— `02_source/**` 在 **21:29** 曾有 **3 个 `__pycache__` /
  13 个 `.pyc`**；**21:31** 被 PM 隔离到 `/tmp/dh-m2-residue-quarantine-20260922`（r6 实测该目录现存
  **13 个 `.pyc`**）；**21:34 起**实测 **0**；artisan r6 复测仍 **0**（见 §6.7 #7）。
- **根因登记（PM 观测，照写）**：`/private/tmp/dh-demo/live/world_live.py` 用 `sys.path.insert`
  **直接 import 交付树里的内核**（`{ws}/02_source/v0_skeleton/kernel`；该文件 L44~L47：
  `DEFAULT_KERNEL = Path.home()/…/02_source/v0_skeleton/kernel` → `KERNEL = Path(os.environ.get("DH_KERNEL", DEFAULT_KERNEL))`
  → `sys.path.insert(0, str(KERNEL))`）⇒ 该 demo 世界**每次（重）启动都会在冻结面内重新生成 `__pycache__`**。
  ⇒ 「**冻结面零残渣**」与「**demo 世界在跑**」**不可同时保证**；`PYTHONDONTWRITEBYTECODE=1` 只覆盖 artisan 自己的探针。
- **登记（LOW）**：残渣判据须带**采集时刻**与「demo 世界是否在跑」的上下文，或改用显式口径
  （「冻结面 + 排除 `__pycache__` / `*.pyc`」并声明理由）。

### 6.5 F-4 · M3 开口项登记（**只登记，不实现**）

| # | 来源 | 问题 | 影响 | 建议关闭方式 |
|---|---|---|---|---|
| M3-1 | raven H2/H3（MEDIUM） | 非回放跑把 `--cassette-dir` 指向**审计源** ⇒ 源被**追加**（先污染后判红）；诊断文案在非回放跑上误报 `replay mode detected` | 审计源可被非审计跑改写；诊断误导排障 | `record()` 拒同 key 追加；或「非回放 + 非空 `--cassette-dir`」时 **fail-closed** |
| M3-2 | raven H4（MEDIUM） | `lookup()` 只校验**命中记录自身** `hash`，不复核**整文件链** | 不经 `cmd_run` 的调用方**无兜底** | 命中即复核整文件链（对齐冻结 §4.3① 字面） |
| M3-3 | raven H8（MEDIUM） | `V0_M2.sha256` 采集面**排除了 504 个已存在文件**（含 `spikes/s8-registry/baseline-after-m2-code/**` 整套旧内核副本）；`is_scratch` 按**名称后缀**匹配对 `02_source/**` 同样生效（今日实际命中 0） | 冻结面**口径不可见** ⇒ 「0 非 OK」的强度依赖未公开的排除清单 | 采集器输出「**排除清单 + 计数**」并冻结 |
| M3-4 | raven H9（MEDIUM，非 r5 新增） | `DH_NEGATIVE_TAMPER_AS_WARNING=1` 在**生产 CLI 路径**上把篡改降为 warning（`exit 0`） | 环境变量可**静默放松** fail-closed | 收进**测试可注入参数**，或加非测试进程守卫 |
| M3-5 | raven B-9a/b/c（GAP） | 重排序 + 重签 / 复制整文件 / 跨文件搬运 ⇒ `verify_chain()` **零告警** | 无密钥链可被整链重签、跨文件搬运 | M3 锚定方案一并覆盖（其中「文件名 ↔ `capability_id`/`provider` 一致性」**不需外部锚点**即可关闭一半） |
| M3-6 | raven A-7（LOW） | `_fallback()` 的 `replay_mode: bool = False` **默认值** | 未来新增调用点漏传 ⇒ **静默回退**到修复前行为 | 改必填，或默认取 `self.default_replay_mode` |
| M3-7 | sentinel | `tests/test_calibrate_latency.py::test_registry_is_idempotent` **与树位置绑定**（`calibration.registry.json` 内嵌**绝对路径**） | **任何副本上跑必红一例**（PM 在 `cp -R` 与 `cp -p` 两份副本上各复现 `1 failed / 131 passed / 4 skipped`，diff 分别落在 `mtime` 与 `path` 字段）；**原位**跑 `132 passed / 4 skipped / 0 failed` | M3 去掉**绝对路径绑定**（相对路径 + 运行时解析） |

- 以上 7 条**均为登记**；本轮**未实现**任何一条（写集只允许文档）。

### 6.6 F-3 · ADR-015 测试条数更正（6 → 7）

- `02_source/07_adr.md` ADR-015「如何验证」②：「新增测试 **6** 条全绿」⇒ 改为 **7** 条，并注明实测文件
  `tests/test_cassette_no_backfill_r5.py`（`def test_` 计数 = **7**）。
- 复算命令 + 读数（workdir = `{ws}`）：
  `grep -c 'def test_' 02_source/v0_skeleton/kernel/tests/test_cassette_no_backfill_r5.py` ⇒ **7**（exit 0）。
  7 条 = 篡改零回填 / 重复 key（单元）/ 命令层可见性 / `prev_hash`-only 两形态 / 生效 `replay_mode` 显式传参 /
  干净回放 exit 0 / miss exit ≠ 0；其中负例自证用例为 `test_negative_control_reverting_f1_guard_reproduces_backfill`。
- **未动** ADR-13 的编号风格（cosmetic，PM 接受现状）；ADR-015 之外**未改**任何 ADR 内容。

### 6.7 出口判据逐条读数（本轮任务书 §4）

| # | 判据 | 命令（workdir） | 期望 | 实测 | exit |
|---|---|---|---|---|---|
| 1 | 定稿**后**最后一次重取 | `cd {ws} && python3 .squad_tools/artisan-r6-recollect-v0m2.py` | 重取成功、0 非 OK | 见 §6.8 | 0 |
| 2 | 冻结面自校验 | `cd {ws} && shasum -a 256 -c V0_M2.sha256 \| grep -vc ': OK$'` | 0 | **0**（**238 / 238 OK**，清单 238 行） | 0 |
| 3 | 契约门禁 | `cd {ws}/02_source && bash verify_specs.sh --quiet` | OK / 0 skipped | **`verify_specs: OK (110 checks passed, 0 skipped)`** | 0 |
| 4 | F-1 五条读数 + 负例 | 见 §6.3（§5.5 同一命令块） | 5 / 0 / 1 / 1 / 4；负例 ≠ 0 | **5 / 0 / 1 / 1 / 4**；负例 **2**（变红） | 0 |
| 5 | ADR 数 + ADR-015 条数 | `grep -c '^## ADR-' 02_source/07_adr.md`；`grep -c 'def test_' …test_cassette_no_backfill_r5.py` | 15；7 | **15**；**7** | 0 |
| 6 | manifest 穷尽（**自建检查器**） | `cd {ws} && python3 .squad_tools/artisan-r6-manifest-check.py` | 缺失 0 / 幻影 0 / 重复 0 | **缺失 0 / 幻影 0 / 重复 0**（清单 **138** 行 vs 盘上 **138** 文件；唯一「缺失」= `manifest.txt` **自身**，**自排除为约定**，已在检查器里写死并输出） | 0 |
| 7 | 残渣 + 仓库 dirty | `cd {ws} && find . -name '__pycache__' -o -name '.pytest_cache' -o -name '*.pyc' \| wc -l`；`git -C /Users/wooyinq/personal/deep-healing status --porcelain \| wc -l`；`rev-parse --abbrev-ref HEAD` | 0；0；`develop` | 残渣 **0**（2026-09-22 22:2x 采集，时间条件量见 §6.4b）；dirty **0**；**`develop`** | 0 |
| 8 | **零代码改动自证** | §6.8 重取的 `changed` 清单 | 只有文档/日志 | **changed 3 条 = `02_source/07_adr.md` + 根级 `06` + `03`**；`added` 0 / `removed` 0 ⇒ `02_source/**` 的 `.py` / `.json` / capability 与 r5 冻结值**逐字节一致** | 0 |
| 9 | 全量 pytest | **未重跑**（任务书 §4.9 明令） | 引用 PM 独立读数 | **引用 PM 独立读数：`132 passed / 4 skipped / 0 failed`**（**原位**跑；来源 = PM r5 确认轮，见 `.pm_notes.md`）。r5 §5.6 #5 的 **GAP 由该 PM 读数闭合**；artisan 未冒名重跑 | — |
| 10 | 时间预算 ~25 min | — | — | 见 §6.8 结论 | — |

### 6.8 重取登记 + 结论

- **重取脚本**：`.squad_tools/artisan-r6-recollect-v0m2.py`（与 r5 版**同口径**：采集面 = `02_source/**` +
  `spikes/{s8-registry,s9-rules,s10-memory,s11-pack2}/**` + 根级 `03`/`06`；排除 `*-scratch` / `__pycache__` /
  `.pytest_cache` / `*.pyc` / `.DS_Store`；**自引用日志排除**，旧 `v0m2-recollection.json` 与
  `v0m2-recollection-r5.json` **保留不覆盖**，本轮新增 `-r6`）。
- **干跑预览**（`.squad_tools` 外的 `/tmp/artisan-r6/preview-recollect.py`，只读）：`03` 段追加前 `changed` = **2**
  （`02_source/07_adr.md` + `06`）⇒ 与定稿后的 **3** 条差值**恰为** `03` 本段追加 ⇒ 采集面内**没有任何代码文件**变化。
- **重取前后哈希**：逐文件 旧 → 新 见 `spikes/s9-rules/logs/v0m2-recollection-r6.json`。
- **结论行**：
  - `r5 出口判据 #8（F-5 字面断言） = ` **PASS**（修前 `5 / 1 / 1 / 1 / 6` → 修后 `5 / 0 / 1 / 1 / 4`，负例 = 2 变红）
  - `文档 LOW 登记 = ` **2 条**（`SEED.sha256` 只校验聚合；残渣读数是时间条件量 + demo 世界根因）
  - `M3 开口项登记 = ` **7 条**（M3-1 ~ M3-7，只登记不实现）
  - `ADR-015 测试条数 = ` **7**（原写 6，已更正）；`ADR 总数 = ` **15**（未变）
  - `零代码改动 = ` **成立**（重取 `changed` 3 条全为文档/日志；`02_source/**` 代码与数据逐字节一致）
  - `M2 文档面 = ` **可收口**（判据 #8 由 FAIL 转 PASS；两条 LOW 已登记；M3 开口项已入册；冻结面 0 非 OK、门禁 OK/0 skipped）
