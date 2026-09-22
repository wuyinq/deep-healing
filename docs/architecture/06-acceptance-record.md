# PM 逐 AC 终验记录

> 本文件按轮次累积：**§1~§6 = REQ-20260921-002（架构冻结轮）**，**§7 = REQ-20260921-003（V0 垂直切片 · M1）**。

## §0 轮次索引

| 轮次 | 需求 | 结论 | 交付物落点 |
|---|---|---|---|
| 架构冻结 | `REQ-20260921-002` | 有条件通过（CRITICAL 0；AC-11 / AC-13 为 GAP） | `docs/`（commit `b421cb0`） |
| V0 · M1 | `REQ-20260921-003` | 有条件通过（CRITICAL 0；6 PASS / 1 GAP / 1 分列均 PASS） | `v0/` |

---

# 第一部分 · REQ-20260921-002（架构冻结轮）

- 验收人：lanova（PM）　时间：2026-09-21 19:2x（Asia/Shanghai）
- 被测：`dev_team_workspace/REQ-20260921-002-deephealing-architecture-freeze/`（01~09 + 02_source 83 文件 + spikes 5 组）
- 真实仓库：`/Users/wooyinq/personal/deep-healing`　HEAD `56a1e81`　`git status --porcelain` **空**（全程零改动，我本人复核 3 次）
- 在航契约：**rev2**（AC-14/AC-15 属下一轮；D-0.9 属下一轮）
- PM 独立取证工具（不复用小队构造）：
  - `pm_business/tools/pm_verify_ac2.py`（sha256 `a8acb96831d6b7c6982fba25cad04ce405736f8c4570014ba082c4112a7e0868`）
  - `pm_business/tools/pm_verify_ac13.py`（sha256 `265fce34760fb4f2f9b7cc9af37247d6ee764ab6cbc410b1e38e7d9d08866f77`）
  - `pm_business/tools/check_bash_multibyte.py`（sha256 `09c3ab81673b8f461fe86b3682b3c5bf1a6263ad8feb8268eb14b724b77cf9ba`）

## 1. 逐 AC 判定（PM 独立，不采信自述）

| AC | PM 判定 | PM 的独立依据 |
|---|---|---|
| **AC-1** 分层与边界 | **PASS**（规格）/ **GAP**（实现：V0 未实现） | 亲读 01：L1~L7 七层齐备、依赖方向与三条硬边界（禁止 L1/L2 直调 L4；L4 不直改世界状态；L5 不被渲染层直读）明写 |
| **AC-2** 确定性 tick 与回放 | **PASS** | **PM 自写比对器独立复现**：双 run 逐点一致（8/8）；双回放一致；末检查点 `state_hash=388a1a51833f04b0…` 与小队一致；**自造 3 个负例证明比对器非瞎子**（删检查点 / 改 state_hash / **仅改 rng_state_digest** 全部被检出） |
| **AC-3** cassette 可录制/回放 | **PASS** | 亲读 s2：真实调 `api.tokenfab.cn` 200；`E_CASSETTE_AMBIGUOUS_SOURCE`/`E_CASSETTE_TAMPERED` 均 fail-closed 非 0；offline-guard 下回放零网络 |
| **AC-4** 双模式权限与同步 | **PASS**（权限判定+协议）/ **GAP**（限流/冷却/影响预算未实现） | 亲读 01 §6.3 护栏契约；Sentinel 复跑 `node --test` 4 pass |
| **AC-5** 开源选型矩阵 | **PASS** | PM 亲数 **12 层**（L1~L12，≥6 ✓）；许可事实表 5 项未决全部由 Sentinel 按 npm/PyPI/GitHub 上游独立复算补齐 |
| **AC-6** 内容扩展机制 | **PASS**（规范+迁移路径+签名真跑）/ **GAP**（`kernel validate` 未实现、无第二街区真跑） | PM 亲读：迁移路径 7 步；`verify_pack.py` 13 files exit 0。**PM 补证**：s1 spike 的 `NPC_IDS`/`pack_id` **硬编码在源码**（L35/L211），故「不改内核代码即可加载第二街区」这一运行时命题**未证实**（与 Raven RA-4 同族） |
| **AC-7** 认知与自进化 | **PASS**（设计+护栏+注册表组织）/ **GAP**（自进化未启用） | 亲读 01 §7/§8 + ADR-006/ADR-010 |
| **AC-8** V0 实施计划 | **PASS** | PM 亲数 **13 个文件级任务项**（W0b + W0~W10 + 汇总），逐项含 RED 用例/命令/工时 |
| **AC-9** ADR | **PASS**（≥8 ✓，实得 **10** 条） | PM 亲列 ADR-001~ADR-010，六项必答主题全覆盖。**注**：AC-9 期望「ADR-10=世界模型、ADR-11=AIGC」，本轮 ADR-010 编给了「记忆/自进化」→ **下一轮需解编号冲突** |
| **AC-10** 成本与性能预算 | **PASS**（预算+实测基线）/ **GAP**（内存/端到端延迟未测） | 亲读 09 §3：238/428、267/391 tokens，5947/5571 ms |
| **AC-11** 美学与双模式 IA | **PASS**（IA 契约+渲染真跑+数值约束）/ **GAP**（**治愈系氛围达成未证实**） | **PM 亲自看图**：极简占位场景（1 楼体/5 胶囊 NPC），无天空、无可见雾、无可见投影。Sentinel **自写 PNG 解码器独立重算** `png_stats.log` 逐位一致（证非伪造），并独立判 **GAP**。artisan 已按 PM 要求如实改判 |
| **AC-12** 证据与可复现 | **PASS（扣两处）** | 各 spike 均由 PM 或 Sentinel 真跑复现。**扣**：① 复验期间产物被并行改动（修订 A→B）未在 03 登记；② cassettes 每次重跑重录 + 远端非确定 → 报告哈希对**第三方不可复现**（Raven RM-8） |
| **AC-13** 原子能力注册（D-0.6） | **PASS** | **PM 自造新能力（纯数据 4562 B、零代码）**：注册表发现（4→5）、**内核源码指纹逐字节不变**（`580c1c6be6596a82…`）、移出后回基线。**比小队自证更强**（他们演示「数据+adapter」，PM 演示「仅数据」） |
| **AC-14 / AC-15** | **N/A** | rev2 在航契约不含；下一轮有界补轮生效 |

**CRITICAL：0**（Raven round-2 独立复验：RA-1/RA-3/RB-1 关闭；RA-2 机制面关闭 + 降级为「已声明边界」）

## 2. PM 发现的遗留项（3 条，均已闭环或被接受）

| 项 | PM 动作 | 结果 |
|---|---|---|
| **G-1** `$VAR` 紧跟多字节 → bash 3.2 吞字符 → **证据行静默丢弃**（s1 四处 / s2 一处） | PM 19:01 用自写守卫定位并当面告知 artisan；PM 更正了自己先前的错根因（非「打错字」，是 macOS bash 3.2 + UTF-8 + `set -u` 的环境陷阱，`bash -c 'set -u; X=4; echo "val = $X（期望 4）"'` → exit 127） | **已关闭**：19:06 修复（`${VAR}`），PM 用自己守卫复验 **0 命中**、两行证据回归、日志合法 UTF-8；并新增**常驻门禁** `spikes/tools/gate_spike_scripts.sh`（**带 3 条反例自证 exit 1/1/1**，非「零命中绿命令」） |
| **G-2** AC-11 美学断言只验配置、不验画面 | PM 亲自读图后登记异议，要求「要么下沉到画面证据，要么如实记 GAP」 | **已接受**：artisan 两样都做了（补 `png_stats.log` 画面级度量 + 改判 GAP）；Sentinel 独立重算逐位一致 |
| **G-3** 许可事实表 5 项未决 | PM 登记要求逐项补全或标 GAP | **已关闭**：Sentinel 按 npm/PyPI/GitHub 独立复算全部补齐 |
| **PM 新发现** `event_chain_hash` 跨路径语义不一致（off-by-one） | PM 独立比对 `run↔replay`（**小队从未做过该组合**）：`state_hash` 8/8 同、`rng_state_digest` 8/8 同、**`event_chain_hash` 0/8 同**。根因：`simulate` 用 `log.last_hash`（快照事件之前），`fold` 用 `event["hash"]`（快照事件本身） | **MEDIUM，留待下一轮裁决**：统一定义，或明确写死「路径相对量、禁止跨路径比对」。**未裁决前不得声称「run 与 replay 三字段全等」** |

## 3. 放行判定

**本轮（架构冻结）判定：有条件通过（PASS with findings）。**

- AC-1~AC-13 **无 FAIL**；CRITICAL 0；MEDIUM/LOW 与 8 项 GAP 均**不阻断架构冻结**。
- **但「落盘并 commit」不得在下列项清掉之前执行**（Raven 明确「必须在落盘前改」+ PM 判定）：
  1. **RM-1**：`cassette.format.md` 那句强度声明必须改写（哈希无密钥 ⇒ 只检损坏，**不是真实性保证**）；Sentinel 的 R2-1 同源。
  2. **R2-4 / R2-5**：`03_artisan_self_test.log` 的 C10 行须补口径更正；19:05~19:08 的改动须登记（时间/文件/sha256/原因）。否则 AC-12 只能靠 Sentinel 报告锚定。
  3. **ADR 编号冲突**（AC-9 期望 ADR-10/11 为世界模型/AIGC）。
  4. **PM 的 `event_chain_hash` 口径**（统一定义或写死禁止跨路径比对）。
  5. **R2-2 / R2-3**（门禁自身缺陷：`run_s2.sh` 非 hermetic、`verify_specs` 被生成残渣弄红）——不修则任何人复跑都可能拿到与被测代码无关的红。
- **下一轮（有界补轮）范围**：AC-14（世界模型）+ AC-15（AIGC）+ **D-0.9**（用户裁决：契约只钉语义不钉毫秒数）+ 上述 5 项清理。
- **落盘条件**：补轮通过 + PM 复验 → 才把定稿文档落进真实仓库 `docs/` 并 commit 到 `develop`（不 push、不开 PR，按用户授权）。

## 4. 诚实边界（不得在总结里弱化）

- `local_model` provider **未真跑**（本机无本地模型服务）——只设计槽位。
- `kernel run/replay/validate`、`pack sign` 均为**接口桩**（`NotImplementedError` / `E_NOT_IMPLEMENTED`）——本轮交付是**架构冻结 + 接口骨架**，不是可运行产品。
- 8 项 GAP 逐项登记在 `03` §5 与 `09`，**未冒充 PASS**。
- 远端等价性证据仍带 `--timeout-ms-override 20000`（RM-14）——**D-0.9 已裁决其口径，但实现侧待下一轮落实**。
- 「治愈系氛围达成」**未证实**（AC-11 GAP）。


---

# PM 逐 AC 终验 · round 3（有界补轮）—— 2026-09-21 23:4x

- 在航契约：**rev5**（D-0.5~D-0.9；AC-1~AC-15）
- 小队：architect 用满 **3/3** 修复迭代；**CRITICAL 全轮归零**
- 真实仓库：`/Users/wooyinq/personal/deep-healing`　`develop` @ `56a1e81`　`git status --porcelain` **空**（全程零改动）

## 1. PM 独立复验（亲手跑，不采信自述）

| # | PM 动作 | 结果 |
|---|---|---|
| 1 | `python3 spikes/tools/make_freeze_snapshot.py --verify …` | **recorded=107 current=107 drift=0 missing=0 added=0**（含 `01`） |
| 2 | **PM 亲手跑隔离复跑** `bash run_s1.sh --out /tmp/…/pm-s1-rerun` | **exit 0**；隔离目录 127 产物；**原地 `logs/` 被写 0 文件**；复跑后冻结面**仍 0 漂移** |
| 3 | `python3 pm_verify_b4.py`（PM 自写比对器，含防空绿门槛） | **PASS 11/11**：`run↔replay` compared=8 divergent=0；两条负例非 0；四日志 `state_hash` 全 = `388a1a51…` |
| 4 | `python3 pm_verify_ac2.py` | **PASS**：双 run 8/8、双回放 8/8、三条负向对照全检出 |
| 5 | `python3 pm_verify_ac13.py`（PM 自造能力，**纯数据零代码**） | **PASS**：注册表 4→5；**内核源码指纹 `35a4e3b098c67308…` 逐字节不变**；无 `.py` 变更；移出后回基线 |
| 6 | **PM 亲手跑** `bash run_s7.sh` | **exit 0**；**14 类负例全被具体 reason code 拒**；`--no-execute` 自证反例证明红来自真执行体 |
| 7 | **PM 亲手跑** `bash run_s6.sh` | **exit 0**；正例 + **10 类负例全拒**；零生成扫描自证非零命中绿命令 |
| 8 | **PM 自造 AC-15 负例**：`FLUX.1-dev` + `flux-1-dev-non-commercial`（**表内一致但禁商用**） | **`REJECT A3_NON_COMMERCIAL_SOURCE`、exit 1** ⇒ 白名单**双向强制**，强于 Raven MEDIUM #6 所求 |
| 9 | PM 动作后复验冻结面 | **仍 0 漂移**（我的验收器无残留；`capabilities/` 5 个文件干净） |

## 2. 双门禁最终裁决（各自独立复跑）

| 门禁 | CRITICAL | MEDIUM | LOW | 放行建议 |
|---|---|---|---|---|
| **Sentinel** §10~§13 | **0** | 2（冻结漂移→已由 23:32 重取解决 / 回归计数口径） | 2 | 技术面放行 |
| **Raven** §8~§11 | **0** | 1（R3F3-1 纵深缺口，fail-closed 无绕过无放大） | 4 | 技术收口通过 |

- **Raven 关闭项**：预审 CRITICAL-1（`event_chain_hash`）独立复现关闭；RR3-1（冻结快照被并行复跑破坏）关闭（隔离复跑 0 漂移 + **交付树 4187 文件零写入**）；RR3-2（确定性闸门无执行体）关闭；R3F2-1/R3F2-2 关闭；N-1 未重开。
- **Sentinel 关闭项**：B1/B4 关闭；B5 关闭 5/7 子项；H1/H2 关闭；MEDIUM-5（override 门禁漏 Python 写法）关闭（**7 种写法**逐种验过）；AC-14/AC-15/D-0.9 契约完整性成立。
- **两门禁分歧**（PM 记录）：round-3 首轮 Sentinel 判 CRITICAL=0、Raven 判 CRITICAL=2；Raven 的 2 条经 architect 裁决→artisan 修复→**PM 独立复验**确认成立。**单门禁会漏这两条。**

## 3. 逐 AC 判定（round 3 终态）

- **AC-1~AC-13**：无 FAIL（round 2 已验；本轮回归面无退步）。
- **AC-14 世界模型接入**：**PASS / GAP**（本机无生成式世界模型可跑；`imagine.*` 真实调用未实测；G4 阈值待 PM）。
- **AC-15 AIGC 素材管线**：**PASS / GAP**（素材生成 spike 未做；成本未实测；像素口径未实现）。**PM 亲手跑 harness + 自造负例补强**。
- **AC-13 remote 类等价性**：**GAP**（远端 `memory.reflect` 输出不符 `output_schema` ⇒ 每次 `on_invalid_schema` 降级；门禁按规则登记 `.gap`，**未改契约迁就远端输出** —— 做法正确）。
- **CRITICAL = 0**；GAP 逐项登记，**未冒充 PASS**。

## 4. 四条需 PM/用户裁决的 block_issues（architect 提出）

1. **D-0.9 声明值量级**：标定按「声明值 ≥ 实测 p95」推导，24 次真实远端调用得 p50 7443ms / p95 43359ms / max 54031ms ⇒ 声明值落在 **~43s** 量级。
   - **PM 判定**：**测量被网络拥塞污染**（p90 42s 与 max 54s 同量级，非模型固有延迟）。按 **D-0.9（用户裁决：契约只钉语义、不钉毫秒数）**，该值为**实测标定的声明值**、非契约冻结值 ⇒ **落盘时标注「受污染窗口 / 临时值 / V0 需在干净窗口重标」**，不得作为产品运行值呈现。
2. **AC-13 remote 面验收口径**：**PM 判定 = 接受该 GAP 落盘**（诚实），要求 V0 先修远端结构化输出/提示词约束后重取等价性证据。**不得**为迁就远端输出改契约。
3. **V1 实验门禁 G4 单位成本阈值**：**PM 判定 = 登记为 REQ 附录 C 开放项**，由需求侧给值；未给定前 G4 不可判达标（不阻断本轮冻结）。
4. **门禁 provider 数量上界**：**PM 判定 = 登记为开放项**（有硬超时，属有界放大非无限挂起）；设上限会改变合法清单受理面，超出本轮授权。

## 5. 放行判定

**round 3 判定：有条件通过（PASS with findings）→ 允许落盘。**

- **五项链式阻断项（round 2 遗留）全部关闭**：B1 cassette 措辞 + 冻结条文 + 指针门禁 / B2 C10 口径更正 + 改动登记 / B3 ADR 重编号（**12 条**，原 ADR-010 → **ADR-012**）/ B4 `event_chain_hash` 统一 / B5 门禁自身缺陷（`run_s2` 三次 exit 一致 + `fallback.reason` 断言 + `verify_specs` 缓存排除 + 两条自证负例）。
- **CRITICAL 0**；MEDIUM 与 GAP **显式携带**，不冒充 PASS。
- **落盘执行**：定稿文档 → 真实仓库 `docs/`；commit 到 `develop`（**不 push、不开 PR**，按用户授权）。

## 6. 诚实边界（不得在总结里弱化）

- `local_model` provider **未真跑**；`kernel run/replay/validate`、`pack sign` 仍是**接口桩** ⇒ 本轮交付是**架构冻结 + 接口骨架**，不是可运行产品。
- **不得宣称「回归 17 项全 0」**：`fix2_regression.sh` 当前 **exit 1**（唯一失配 = `g5_sweep_counts` 计数口径，Sentinel MEDIUM-7 / architect 已登记）。这是**判据口径缺陷，非产品缺陷**，但表述必须如实。
- **R3F3-1**（内嵌 `output_schema` 的 `$ref` 悬挂/成环 ⇒ 父进程崩溃被压成不透明 `B5_CHECK_CRASH_GUARDED`）：**MEDIUM 携带**，非「已关闭」。
- 「治愈系氛围达成」**未证实**（AC-11 GAP）。
- 冻结快照**只提供事后发现漂移**，不提供防止；本轮以「隔离复跑」机制消除该矛盾。


---

# 第二部分 · REQ-20260921-003（V0 垂直切片 · 里程碑 M1：确定性内核）

- 验收人：lanova（PM）　时间：2026-09-22（Asia/Shanghai）
- 被测：`dev_team_workspace/REQ-20260921-003-deephealing-v0-m1/`（`02_source` 111 文件 + `spikes/**` + `06_v0_m1_self_test.md`）
- 交付落点：`v0/`（本仓库）
- 结论：**有条件通过**。8 条 AC 中 **6 PASS / 1 GAP / 1 分列两判据均 PASS**；**CRITICAL 全程为 0**；无 FAIL。

## 7. 逐 AC 判定（PM 亲自读盘 + 亲自复跑，不采信自述）

| AC | PM 判定 | PM 的独立依据（命令 + 实测） |
|---|---|---|
| AC-M1-1 契约仍全绿 | **PASS** | `bash verify_specs.sh --quiet` → `OK (95 checks passed, 0 skipped)`；asset pack `assets=1 files=2 rejects=0`；zero-generation `hits=0` |
| AC-M1-2 确定性 tick 与回放 | **PASS** | `pytest tests/test_determinism_replay.py` → **6 passed**（非 skipped） |
| AC-M1-3 端到端 run→verify→replay | **PASS + 已声明边界** | PM 自跑：925 事件 / 6 检查点 / 链尾 `baecca92…` / `verify` exit 0；对抗负例 7/7（见下） |
| AC-M1-4 内容包加载 | **PASS** | `validate` exit 0（npcs=5 / entities=12 / buildings=2）；`pytest tests/test_pack_validate.py` → 12 passed |
| AC-M1-5 内核源码指纹 | **PASS** | `pytest tests/test_kernel_digest.py` → 4 passed；PM 自造差集负例（改 `tick.py` → `changed=['tick.py']`）；`--selftest` → OK（1 正例 + 2 强制负例 + 1 并集正例） |
| AC-M1-6 时间预算标定（D-0.9） | **GAP**（① ② PASS / ③ ④ GAP） | 判据③**不可重复**：同数据同声明值同为 `--runs 10`，三次测得 adopted 降级率 `0.50`（越界）/ `0.20` / `0.10`；根因 = 抖动 **叠加** 区间口径塌缩（`adopted == strict == 1300`，7/7 全塌缩）。**未重采样、未调参、未改声明值** |
| AC-M1-7 凭据与请求体面 | **PASS**（两判据均 PASS） | PM 严格密钥形状扫描（`sk-[A-Za-z0-9]{20,}`）**0 命中**；54 次真实调用、无落盘请求体 |
| AC-M1-8 仓库零改动 + 起点溯源 | **PASS** | 验收时仓库 `develop` @ `b421cb0`、`dirty=0`；SEED 聚合 `34fa7f6d…` 未变；`V0_M1.sha256` 276/276 OK |

## 8. AC-M1-3 对抗负例（PM 自写，不复用小队夹具）

PM 自写 `pm_adversarial_ac3.py`，导入**冻结的** `tools/canonical_json.py`（契约要求单一来源），先自证公式正确（重算 **925/925** 逐条复现原哈希），再上四类攻击：

| 用例 | 期望 | 实测 |
|---|---|---|
| N1 朴素截断（尾部删 120 条） | 红 | exit 1 ✓ |
| N2 中段篡改 payload + 重算整链 | 红 | exit 1 ✓ |
| N3 自洽前缀伪造（截断 + 改 `plan_ticks` + 重算链）· **无锚点** | — | **exit 0** ← 独立复现 GAP-7 |
| N3 同上 · **带原始锚点** | 红 | exit 1 ✓ |
| N4 干净日志 + 正确锚点 / 错误锚点 | 绿 / 红 | exit 0 / exit 1 ✓ |

**PM 的构造过程本身是证据**：前两次构造**被实现检出**（中途截断 → `missing_in_log`；陈旧快照 → `INVARIANT-ECH-2`），第三次才成功
（须同时满足：正确链公式 + 截断落 **tick 边界** + 同步维护 `INVARIANT-ECH-2`）。
⇒ 该伪造**比看起来难但确实可行**；实现的**多层探测器有效，但无法覆盖无锚点场景**。

## 9. GAP-7（自洽前缀截断）—— PM 裁决：接受为**已声明的强度边界**

无密钥哈希链本不提供真实性保证（`cassette.format.md` 的 `FROZEN-CASSETTE-INTEGRITY-1` 已如实声明）。
**硬性要求**：验收与任何抗改写场景**必须显式传 `--expected-hash`**（链外锚点；`run` 输出的 `chain_tail` 可直接取用）。
**禁止**把「`verify` exit 0」读成「日志未被篡改」。

## 10. 未关闭项（如实登记，不阻断）

- **GAP-7** 如上；**AC-M1-6** 判据③④不可重复
- **U11**：`verify_pack.py` 对「符号链接逃逸 pack」仍判绿 ⇒「AC-M1-1 绿」≠「pack 无越界读取」
- **8 条 MEDIUM**（architect `non_block_issues`）：replay 侧 fail-closed 不对称、checkpoints 只读目录/symlink 形态、畸形日志裸 traceback 等
- **交付面依赖**：AC-M1-5/6/7 的判据依赖**工作区级产物**（`spikes/kernel-baseline/**`、`spikes/s5-latency-calibration/**`、`06_v0_m1_self_test.md`）。
  只取 `02_source` 会看到 12 条红（**全部归因产物缺失，非代码回归**）⇒ 交付包必须一并提供它们（`v0/` 已按此落盘）
- **标定缓存与位置耦合**（**M1 后置修复，已关闭**）：`calibration.registry.json` 原把绝对路径 + mtime 纳入
  「是否重写」的判定 ⇒ 复制/克隆到新路径后 `test_registry_is_idempotent` 首跑失败（已在**全新克隆**中实测复现）。
  已改为**内容锚定**（只比对冻结物 sha256；内容未变则不写盘），双向验证通过（内容变 ⇒ 仍重写；仅漂移 ⇒ 不写盘）；
  修复后全新克隆 **71 passed / 10 skipped**。增量：`tools/calibrate_latency.py` `e30be65b…` → `23fed40d…`
- **LOW**：`spikes/red/**`（负控沙箱）含字面串 `Bearer sk-liv...oken`——**非真密钥**（严格扫描 0 命中），仅为截断仿冒串；未随 `v0/` 提供

## 11. 范围与诚实边界

- 本轮交付 = **M1 确定性内核可运行**（`run` → 事件日志 → `replay` → `verify` → `validate` → `pack sign`），
  **不是**完整 V0 垂直切片：能力注册表运行时（W3）、规则层与预算（W4）、记忆层（W5）、
  双模式会话（W7）、渲染层（W8）、观测层（W9）属后续里程碑。
- `local_model` provider **未真跑**（本机无本地模型服务），只有槽位设计，不冒充已跑。
