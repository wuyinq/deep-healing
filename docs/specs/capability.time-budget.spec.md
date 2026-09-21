# 能力时间预算语义与标定口径（`capability.time-budget.spec.md`）

配套机器可读条文：`capability.schema.json` 的 `x-time-budget-semantics`（带编号）+ `calibration` / `rule_layer_adoption` 块。
本文件是人读版：语义、声明值的实测依据要求、禁止 override 取证、合成负例例外规则。

## 1. 四条冻结语义（逐字，REQ D-0.9 / 用户裁决）

1. **远端模型 provider 是能力补充，不是硬依赖**；默认路径**允许降级**。
   - 禁止表述：「远端 API 为主 provider」「LLM 为主」——见 §5 的改写与 `grep` 证据。
2. **超时即确定性降级**（fallback → `deterministic_rule`），降级必须**可审计**（落
   `capability.fallback{capability, from_provider, to_provider, reason}`，含中间转移）且**可回放**（cassette）。
3. 能力结果**跨 tick 边界丢弃、绝不回填**（迟到结果只记 metric；`wall_clock` 严禁参与 hash 或 tick 内决策）。
4. 每个能力的 `timeout_ms` / `latency_ms_budget` 是**该能力自己的、由实测标定的声明值**；
   **REQ 不固定任何毫秒数**，也不得由全局常量代替。声明值必须附 `calibration` 块的实测依据。

## 2. 声明值的实测依据（缺一即 FAIL）

每个能力的 `calibration` 块必须给齐：

| 字段 | 含义 | 要求 |
|---|---|---|
| `sample_count` | 实测样本数 | ≥ 20（D15） |
| `p50_ms` / `p90_ms` / `p95_ms` / `p99_ms` / `max_ms` | 延迟分布（最近秩法分位） | 与分布日志逐位一致 |
| `derivation_rule` + `derivation_rule_sha256` | 推导规则文本与其 sha256 | 规则文件 mtime **早于**分布日志 mtime |
| `candidate_strict_ms` / `candidate_loose_ms` | 两个候选值（更严 / 更松） | 三行对照「分布 → 声明值 → 降级率」 |
| `accepted_degradation_range` | 降级率可接受区间 | **测量前**声明（区间文本 mtime 早于降级率日志） |
| `command` / `workdir` / `exit` / `log_path` | 取证四件套 | 命令 + 工作目录 + 退出码 + 日志绝对路径 |
| `degradation_log_path` | 声明值下的降级率日志 | 无实测则记 `gap_note` |

### 防自证五条（硬性，`01 §16.3.3`）

1. **规则先冻结**：规则文本 + sha256 + mtime 早于分布日志；规则是分布的**单调函数**且带下界 `声明值 ≥ p95`。
2. **声明值 ≠ 当次实测 max**；给「声明值 / p95 / p99 / max」**四值对照表**。
3. **两个候选值** + 三行对照；**降级率可接受区间必须在测量前声明**。
4. **同条件**：分布测量与降级率测量同并发 / 同网络 / 同冷热；不同则分列并标 **GAP**。
5. **清单值与报告值脚本断言一致**（防 override 路径绕过，RM-14 形态）。

本轮落点：`spikes/s5-latency-calibration/`（`DERIVATION-RULE.frozen.md`、`ACCEPTED-DEGRADATION-RANGE.frozen.md`、
`calibration.registry.json`、`calibration.json`、`logs/latency.distribution.json`、`logs/degradation.*.json`），
校验脚本 `calibrate.py check`。

## 3. 取证口径（硬性）

- 等价性 / 降级证据**必须**在能力清单**声明的值**下取得。
- **禁止**用 `--timeout-ms-override` 取得「绿」。
- 常驻门禁：`spikes/tools/check_no_override_evidence.sh`（扫描 spike 脚本与证据日志；命中即非 0；
  门禁内置反例自证，不是「零命中绿命令」）。

## 4. 合成负例例外规则（唯一例外，白名单精确匹配）

- 允许 override 的**唯一**情形：强制触发超时以验证「超时 → 确定性降级 + 可审计」机制的**合成负例**。
- 必须在脚本里于该调用**紧邻的上一行**写显式标记：

  ```
  # DH-SYNTHETIC-NEGATIVE: <一句话说明这条 override 只用于合成负例，不作等价性/降级率证据>
  <命令含 --timeout-ms-override ...>
  ```

- 该次运行**不得**计入 AC-13 remote 类等价性证据，也**不得**计入降级率统计。
- 白名单**只认该标记**；其余任何 `--timeout-ms-override` 命中即门禁非 0。
- **门禁的扫描口径（精确）**：`--timeout-ms-override` 必须作为**命令行参数**出现（token 后紧跟空白或行尾）且该行不是注释行，
  才算「证据性调用」；注释、散文说明、JSON 的 note/description 文本不算。
- **门禁的排除目录（逐条列明，禁止宽泛通配）**：`spikes/raven-review/**`、`spikes/sentinel-review/**`、
  `spikes/architect-verify/**` —— 第三方复核副本（历史快照），不在 Artisan 写集内，改写等于销毁证据。
- 本轮白名单条目（逐条登记，禁止通配）：`spikes/s2-capability-cassette/run_s2.sh` 第 14 步
  （`--timeout-ms-override 50`，合成负例：验证中间降级链可重建；标记行紧邻调用行）。

## 5. AC 表述改写（REQ D-0.9 第 4 条）

凡「远端 API **为主** provider」「LLM **为主**」的表述，一律改为
「远端为**可降级的能力补充 provider**，默认路径允许降级」。
落点：`07_adr.md`（ADR-005 标题与正文）、`08_v0_plan.md`、`09_risks_open_questions.md`、`02_source` 契约描述。
REQ 属 PM（只读）：若 REQ 仍有相反表述，只在 `09` 登记「待 PM 修订」，不自行改 REQ、不据此判 block。

## 6. 与 AC 的对应

- **AC-13 / D-0.9**：契约冻结语义不冻结数值；各能力声明值由实测标定（本文件 §2）。
- **AC-2**：降级必须可回放（cassette）且不破坏确定性（§1 第 3 条）。
- **AC-12**：每条声明值附命令 / workdir / exit / 日志绝对路径。

## 7. H3 · 确定性闸门 / 派生计算的**确切边界**（round 3 修复迭代 3 显式声明）

本节是「**把未加固面写明**」的落点（Raven `05 §10.5`；任务书 §2 H3）。
凡本节写「已加固」的，都给出上界数值与判据；凡写「未加固 / 只记录」的，都给出触发条件。
**不允许**用「已加固」这类笼统措辞覆盖仍然存在的边界。

### 7.1 校验期对 `output_schema` / `input_schema` 的派生计算（fixture 回退）加固到什么程度

`verify_capability_binding.py` 的 fixture 回退路径（`builtin_reference_rule` → `minimal_instance`）
与探针输入派生（`probe_input`）**都读 manifest 数据**，修复迭代 2 时它们在**父进程、`try` 之外、
无资源上限** ⇒ 纯数据即可让门禁 traceback / 内存放大（R3F2-1）。本轮加固为三层：

1. **使用前健全性检查**（`check_embedded_schema`）：先 `schema_bounds`（**迭代**遍历，不递归 ——
   递归检查器自己会先 `RecursionError`），再 `schema_validate.check_schema`（引擎合法性）。
2. **上界数值**（硬编码常量，`verify_capability_binding.py` 头部同源）：

   | 上界 | 数值 | 交付清单实测最坏值 | 说明 |
   |---|---|---|---|
   | `MAX_SCHEMA_DEPTH = 32` | 嵌套深度 | 6 | 超界 ⇒ `B5_SCHEMA_UNHEALTHY` |
   | `MAX_SCHEMA_NODES = 512` | schema 节点数 | 16 | 超界 ⇒ `B5_SCHEMA_UNHEALTHY` |
   | `MAX_SCHEMA_MIN_ITEMS = 256` | 单处 `minItems` | 1 | 超界 ⇒ `B5_SCHEMA_UNHEALTHY` |
   | `MAX_DERIVED_NODES = 512` | **派生实例**节点预算 | ≤ 16 | 乘性展开也挡得住 ⇒ `B5_SCHEMA_DERIVATION_REFUSED` |

   另：`enum` 必须是**非空数组**（`enum` 非数组或空数组 ⇒ `B5_SCHEMA_UNHEALTHY`）。
3. **失败面收口**：派生计算入 `try`，异常一律转**显式拒收**；逐能力兜底
   （`B5_CHECK_CRASH_GUARDED`）保证「一个数据文件」不会让整轮门禁丢掉全部判据记录；
   清单不可解析 ⇒ `B0_UNREADABLE_MANIFEST`。fixture 回退的 `output_compliant=true`
   **由引擎真验证**（不再只是断言）。

**仍未加固**（逐条，给触发条件）：

- **父进程没有 rlimit**：`_apply_limits` 只作用于子进程；macOS 上 `RLIMIT_AS` 也不可设
  （`applied=None`）。父进程侧的防护是**上界 + 节点预算**（拒绝展开病态 schema），
  **不是资源隔离** —— 触发条件：一个落在上界**之内**、但派生实例很大的 schema（例如
  节点数 500 的宽 schema）仍会占用父进程内存（有界，实测基线量级 30 MB）。
- **上界是固定常量**，不是按能力协商的配额：超界的**合法** schema 同样被拒收（fail-closed，
  宁可拒收不展开）。触发条件：未来某能力的 `output_schema` 深度 > 32 或 `minItems` > 256。

### 7.2 `verified_impl` 的**确切语义**（H2 / R3F2-2）

- **`verified_impl` = 「同一子进程内同输入同输出」**（一次 spawn、进程内调用 `runs=3` 次、比对
  输出摘要）+ 输出过 `output_schema` + impl 可解析，三者齐备。进程内可变状态
  （模块级计数器 / 缓存 / 单例 / 「第 2 次调用才抛错」）**在此可见并被拒收**
  （`B5_DETERMINISM_INCONSISTENT` / `B5_DETERMINISM_EXEC_FAILED`）。
- 它**不证明**：跨进程 / 跨重启幂等；也不证明「随环境变量 / PID / 文件系统 / 导入期时钟变化」的行为。
  触发条件：provider 在**导入期**或首次调用时把 `os.urandom` / `PID` / 宿主名 / 文件内容读进模块级状态。
- 因此：**依赖进程内状态、或依赖上述外部量的 provider 必须声明 `non_deterministic`**
  （缺失即归一化为 `non_deterministic`，`B2_DETERMINISM_FIELD_MISSING`），**不得进规则层**。
- 隔离目标不变：仍是一个独立子进程 + 硬超时（超时 `killpg`）+ rlimit。副作用：`runs` 次调用
  **共享**该子进程的 `RLIMIT_CPU=5s`（修复前是每次 spawn 各 5s）—— 对 V0 骨架的纯函数 provider
  远低于该量级（实测 < 0.1s），但这是**收紧**的资源边界，如实记录。
- 子进程回传协议：`outputs` 必须是长度 `runs` 的数组；不符 ⇒ `B5_DETERMINISM_PROTOCOL_MISMATCH`
  拒收（**不**按 1 次结果冒充 `runs` 次）。

### 7.3 本轮**未关闭**的 R3F2 条目（逐条记 GAP / 只记录，含触发条件）

| 条目 | 级别 | 本轮处置 | 触发条件 / 边界 |
|---|---|---|---|
| **R3F2-3** 子进程继承运行者环境；rlimit 不是文件系统沙箱 | LOW | **声明**（本节 + 工具头部）。`01` 只读，**未写入 `01`** ⇒ 记 GAP：建议 architect 在 `01` 加固说明中补一句「门禁以**运行者环境**跑 provider，provider 不得读取凭据环境变量（`requires_secrets` 只声明变量名）」与「**不是**文件系统沙箱：挡住任意路径写入的是 impl 白名单，不是 rlimit」 | 子进程继承**运行者环境变量**（manifest 无法写环境 ⇒ 运行者面）；`RLIMIT_FSIZE` 只限单文件大小（1 MiB），不限路径与文件个数 |
| **R3F2-5** provider 数量**线性放大** | LOW | **声明**（本节）。本轮**未设** provider 数上界 —— 那会改变合法清单的受理面（业务决策，超出修复授权） | 一个 manifest 声明 N 个 provider ⇒ N 次 spawn（本轮已从 3N 降到 N）。10⁴ provider ≈ 10⁴ 次 spawn；每次都有硬超时 ⇒ **有界**放大面，非无限挂起 |
| **R3F2-6** `IMPL_SHAPE_RE` 用 `$` 收尾，允许尾随换行 | LOW | **只记录**（判据面未改：改 `\Z` 会改动已有 reason code）。实测尾随换行仍被拒 | `builtin:cassette_replay\n` 通过形状层、被登记表**精确匹配**拒收（`B5_IMPL_BUILTIN_NOT_REGISTERED`）。仅当将来把形状判据当「登记名合法性」用才会踩到 |
| **R3F2-7** 路径层与 import 层对「空组件点串」判定不一致 | LOW | **只记录**（双向 fail-closed，无需改） | `module:deephealing_kernel..x:y`：路径层折叠空组件、import 层 `ModuleNotFoundError` ⇒ 判 `B5_DETERMINISM_EXEC_UNRESOLVED`。**不得**把「路径层已解析」读成「已放行」 |
| **R3F2-4** stdout 的 manifest 注入 | LOW | **随修**（人类可读行对 `id` / `detail` 做控制字符转义；`--json` 面本来安全） | 修复前：含 `\n` 的 `id` 可在人类可读 stdout 造出假 `REJECT …` 行 |
| **R3F2-8** `probe_input` 对畸形 `input_schema` 无保护 | LOW | **随修**（同 H1：入 `try` + 上界） | 修复前：`input_schema.properties` 非对象 ⇒ `AttributeError` 逃出门禁 |

### 7.4 承接（**未关闭、照旧携带**，不冒充 PASS）

AC-13 remote 面（`remote_call_status=degraded`）、`any_fallback_rate` 未纳入可接受区间、
`imagine.predict` 的 `remote_api` impl 指针悬空、V0 骨架 provider 未实现
（`B5_GAP_IMPL_NOT_IMPLEMENTED`，显式 GAP 记录）。

