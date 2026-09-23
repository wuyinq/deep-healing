# PM 逐 AC 终验记录

> 本文件按轮次累积：**§1~§6 = REQ-20260921-002（架构冻结轮）**，**§7~§11 = REQ-20260921-003（V0 · M1）**，
> **§12~§16 = REQ-20260921-004（V0 · M2）**，**§17~§21 = REQ-20260921-005（V0 · M3）**。

## §0 轮次索引

| 轮次 | 需求 | 结论 | 交付物落点 |
|---|---|---|---|
| 架构冻结 | `REQ-20260921-002` | 有条件通过（CRITICAL 0；AC-11 / AC-13 为 GAP） | `docs/`（commit `b421cb0`） |
| V0 · M1 | `REQ-20260921-003` | 有条件通过（CRITICAL 0；6 PASS / 1 GAP / 1 分列均 PASS） | `v0/` |
| V0 · M2 | `REQ-20260921-004` | **通过**（8/8 AC PASS，CRITICAL 0，残留 FAIL 0） | `v0/`（同树生长） |
| V0 · M3 | `REQ-20260921-005` | **通过**（逐 AC PASS，**CRITICAL 0**，残留 MEDIUM/LOW/GAP 已逐条登记 M4） | `v0/`（同树生长） |

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

---

# 第三部分 · REQ-20260921-004（V0 垂直切片 · 里程碑 M2：能力注册表 + 规则层 + 记忆 + 内容包）

- 验收人：lanova（PM）　时间：2026-09-22（Asia/Shanghai）
- 被测：`dev_team_workspace/REQ-20260921-004-deephealing-v0-m2/`（`02_source` 139 文件 + `spikes/**` + `06_v0_m2_self_test.md`）
- 交付落点：`v0/`（本仓库，同树生长）
- 结论：**通过**。8 条 AC **全部 PASS**；**CRITICAL 全程为 0**；**残留 FAIL 0**。

## 12. M2 出口证据（PM 亲跑，命令级）

| 判据 | 命令（workdir） | PM 实测 |
|---|---|---|
| 契约门禁 | `bash verify_specs.sh --quiet`（`v0/02_source`） | `verify_specs: OK (110 checks passed, 0 skipped)`，exit 0 |
| 内核全量套件 | `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider`（`v0/02_source/v0_skeleton/kernel`） | `132 passed, 4 skipped in 974.63s (0:16:14)` |
| 冻结面自校验 | `shasum -a 256 -c V0_M2.sha256`（`v0/`） | **237 OK / 1 FAILED**（该 1 条 = F-3 回灌，预期，见 §14） |
| 端到端基线 | `run --seed 20260921 --ticks 300` + `verify --expected-hash` | 925 事件 / 6 检查点 / chain_tail baecca92… / state_hash 9a4ae3da…；`verify` exit 0 |
| 仓库面 | `git status --porcelain`（落盘前） | `develop` + **dirty=0**（M2 全程零写入，PM 多次复核） |

## 13. 逐 AC 判定（PM 读盘 + 亲自复算，不采信自述）

| AC | PM 判定 | PM 的独立依据 |
|---|---|---|
| AC-M2-1 契约全绿 + U11 关闭 | **PASS** | `verify_specs` OK/0 skipped；U11 负例 A/B：旧版工具对符号链接逃逸 pack **判绿且 `sig_entry_equals_outside_content=True`**，当前 `exit 1 E_PACK_INVALID: symlink escape` 且不改写包外文件；manifest 138/139（缺 `manifest.txt` 自身）、幻影 0、重复 0 |
| AC-M2-2 能力注册表 | **PASS** | `jq` schema 字段齐全；五类负例 reason code 逐类命中；纯数据能力注册 ⇒ 内核源码指纹差集**空**，改 `cli.py` 负例 exit 1 |
| AC-M2-3 三类 provider 真跑 | **PASS**（含 GAP-E1） | `remote_api` 真实调用（10 条真记录）；`deterministic_rule`；`cassette_replay` 强制回放；`local_model` = **诚实 GAP**（未谎称跑过）；`embed.text` 远端 404 ⇒ GAP-E1 |
| AC-M2-4 规则层与预算 | **PASS** | 预算超限 ⇒ `fallback_reason=on_budget_exhausted` + journal `capability.fallback`；**静默化负例**（改名 journal 事件）⇒ 门禁变红（判据有牙） |
| AC-M2-5 记忆层 | **PASS** | 两次独立建库检索摘要与 db 字节 sha **完全相同**；扰动 embedding ⇒ 摘要变；写入 flag 关 = 0 写、开 = 1 写 |
| AC-M2-6 第二街区内容扩展 | **PASS** | `verify_pack` exit 0；`validate` exit 0（12 实体 / 5 NPC）；`run` ×3 exit 0 且 5 份事件日志 sha 全等 |
| AC-M2-7 确定性不回退 | **PASS** | M1 工作区 24 份 `000300.json` 的 `state_hash` **24/24 = `9a4ae3da…`**；M2 副本 `--ticks 300` 复算同值（sentinel/raven 各自独立复跑） |
| AC-M2-8 真实仓库零改动 + 起点溯源 | **PASS** | `develop` + `dirty=0` + M2 全程零写入；`SEED.sha256` 聚合 `34fa7f6d…` 未变 |

## 14. M2 落盘口径与 F-3 处置（审计要点）

1. **落盘范围 = `V0_M2.sha256` 冻结面**（238 条）。工作区 `spikes/**` 的 scratch 目录（约 500 文件，
   含 `u11-legacy-tools` 的**修复前**工具副本）**不属冻结面，未随仓库提供**。
2. **F-3（HIGH，PM 在模拟落盘中逮到）**：M2 工作区携带的 `tools/calibrate_latency.py` 是 **M1 后置修复之前**
   的版本（`e30be65b…`，无内容锚定），而仓库 HEAD（`f5f7762`）已是修复版（`23fed40d…`）。
   照清单原样落盘 ⇒ **回退一个已交付并验证过的修复**，任何全新克隆 `test_registry_is_idempotent` 必红。
   **处置**：该文件按**修复版**落；`V0_M2.sha256` **原样落盘**（保持冻结真相），divergence 文档化
   （本记录 + `v0/README.md`）。⇒ 仓库内 `shasum -c V0_M2.sha256` = **237 OK / 1 FAILED（预期）**。
   **教训**：后置修复必须回灌所有存活工作区；落盘前必须先在隔离目录按目标布局真跑。
3. **模拟先行**：落盘前在 `/private/tmp/pm-m2-land-<ts>` 按目标布局真跑 —— 冻结面自校验 **237 OK / 1 FAILED**、
   `verify_specs` OK、基线逐位一致，绿了才动仓库。
4. `spikes/s5-latency-calibration/calibration.registry.json` 内嵌绝对路径（跨 workspace 不可移植）⇒ 按约束文件结论
   **就地重生成**后随仓库提供；幂等（跑测试前后逐字节不变）。

## 15. 未关闭项（如实登记，不阻断）

- **M2 结转 M3 的 7 条开口项**：raven H2/H3/H4/H8/H9、B-9a/b/c 锚定族、A-7 `_fallback` 默认值、
  `test_calibrate_latency` 绝对路径绑定。
- **5 条已声明 GAP**：外部锚定（GAP-7 沿用）、GAP-E1 `embed.text` 远端不可用、`local_model` 未真跑、
  自洽前缀截断、`lookup()` 字面差距。
- **门禁登记的 MEDIUM/LOW 残留**：`pin` 只做存在性校验 ⇒ 回滚语义可被旁路（R-M2-1）；`verify_pack`/`pack_sign`
  用 `rglob` 不跟随**目录**符号链接 ⇒ U11 缺口（R-M2-3）；`--cognition` 默认 provider 随环境凭据漂移（R-M2-4）；
  `verify_specs.sh` 的 manifest 覆盖判据是**子串**非锚定（L-1）、不校验 `world.seed.json` ↔ `world.schema.json`（L-2）。
- **结构性观察 O-M2-1**：demo 世界用 `sys.path.insert` **直接 import 交付树内核** ⇒ 「冻结面零残渣」与
  「demo 在跑」不可同时保证；建议 M3 改为副本依赖。
- **ISS-M2-1**（r5 的 F-5 字面断言被自身命令文本命中，MEDIUM，文档级）：已派 r6 纯文档收口轮修复，
  PM 独立复验 11/11 PASS 后**关闭**。

## 16. 诚实边界（不得在总结里弱化）

- 本轮交付 = **内核 + 认知层骨架**（能力注册表 / 四类 provider / 规则层与预算 / 记忆层 / 第二街区内容包），
  **不是**可玩产品：双模式会话（W7）、渲染层与 UI（W8）、观测层（W9）、集成验收（W10）属 M3/M4。
- `remote_api` 真跑依赖运行时环境变量（值不落盘）；`local_model` 只有槽位。
- 「`verify` exit 0」**不等于**「日志未被篡改」——抗改写必须传 `--expected-hash`。

---

# 第四部分 · REQ-20260921-005（V0 垂直切片 · 里程碑 M3：会话层 + 渲染层 + 世界观落地）

- 验收人：lanova（PM）　时间：2026-09-23 02:2x ~ 04:5x（Asia/Shanghai）
- 被测：`dev_team_workspace/REQ-20260921-005-deephealing-v0-m3/`（01_m3_design + 02_source 150 + spikes s12/s13 + 03~08）
- 真实仓库：`/Users/wooyinq/personal/deep-healing` = `develop` @ `98c781f`，`status --porcelain` = **0**（M3 全程零写入，落盘前复核）
- 轮次：**R1 → R2 → R3 → R4（有界补丁）→ R5（终局有界轮）**，共 5 轮。
  `R3-C1` 属「同一问题连续 2 轮未收敛」⇒ 按 PM 既有规则**停止乒乓、PM 介入**：PM 亲自给出**闭式判据口径**并只授权一轮。
- 口径：**不采信任何自述**；下表每条读数都是 PM 亲跑或 PM 亲算。

## 17. M3 逐 AC 终态（PM 亲跑读数）

| AC | PM 读数（命令 / 实测） | 判定 |
|---|---|---|
| AC-M3-1 契约全绿 | `bash verify_specs.sh --quiet`（`02_source`）⇒ `verify_specs: OK (130 checks passed, 0 skipped)`，exit 0 | **PASS** |
| AC-M3-1 前轮不回退 | 基线 300 tick：`925` 事件 / `6` 检查点 / `chain_tail=baecca92…` / `000300.json.state_hash=9a4ae3da…` —— 与 M1/M2/R3/R4 **逐位一致** | **PASS** |
| AC-M3-1c 防诱饵 | `grep -rn '^\s*DEFAULT_PLAN_TICKS\s*=\s*300'` 全树 ⇒ **恰 1 处**（`tick.py:58`）；`cli.py` 只导入 | **PASS** |
| AC-M3-1d 第二街区 | 两 pack `validate` 各 exit 0（`xingfu-xiaoqu` / `xingfu-xiaoqu-north`） | **PASS** |
| AC-M3-1e 零残渣 | `find 02_source \( -name node_modules -o -name dist -o -name .build -o -name __pycache__ -o -name '*.pyc' \)` ⇒ **0**（跑完全部套件后复检仍 0） | **PASS** |
| AC-M3-2 会话层双模式权限 | `npm test`（`session`）⇒ **16 tests / 16 pass / 0 fail**（4 条 AC 命名用例真跑，非 skip）；`intent.rejected` 真进事件流 | **PASS** |
| AC-M3-3 渲染层真跑 | PM 自起 `serve.mjs`（8901）+ `browser-accept.mjs` ⇒ 6 张截图 / `console_errors=0` / `page_errors=0` / `bad_responses=[]` | **PASS** |
| AC-M3-3 可见性 | `canvas_rect` = **1440×900**（桌面）/ **390×844**（窄屏）= `window.inner*`；`gl_drawing_buffer` 同值；HUD 外非背景像素占比 ≈**1.0** ≥ 阈值 **0.05** | **PASS** |
| AC-M3-3 负例（判据有牙） | PM 亲跑 `negctl/f4_browser_negctl.py` ⇒ `all_ok=True`、`delivery_face_unchanged=True`；pristine `judged_green`；负例全红 | **PASS** |
| AC-M3-4 双模式信息架构 | observe 模式 UI 树只有 2 个只读控件（`toggle-reading` / `toggle-mode`），写控件 **0**；切 participate ⇒ 挂 `input` + `button#submit-delegate`；本地拒 + WS 上行拒**均为 `E_MODE_READONLY`** | **PASS** |
| AC-M3-5 参与影响任务演进 | `pytest tests/test_task_adaptation.py tests/test_observe_mode_readonly.py` ⇒ **10 passed**，exit 0；真实事件流含 `task.state_changed`（`rule_id`/`shift_index`/`impact_cost` 齐备）+ 防刷短路 | **PASS** |
| AC-M3-6 确定性 | 同 AC-M3-1 前轮不回退行（三条读数逐位一致；同序列两次 `e.jsonl` 逐字节相同） | **PASS** |
| AC-M3-7 仓库零改动 + 溯源 | `develop` @ `98c781f`，`porcelain` = **0**；`SEED.sha256` 聚合 `34fa7f6d…` 未变 | **PASS** |
| AC-M3-8① worldview 契约 | `worldview.json` ×2（两 pack）+ `worldview.schema.json` 均可 `json.load`；`pack.entrypoints.worldview` 已登记；`district.pack.spec.md` 已写 | **PASS** |
| AC-M3-8② narrative_hooks 两面 | 两 pack **5/5** 个 NPC 均含 `healing_face` / `hidden_face`（删 `hidden_face` ⇒ 红） | **PASS** |
| AC-M3-8③ 同一几何两态 | `scene_assert: PASS=31 FAIL=0` exit 0；真浏览器 `geometry_surface` ≡ `geometry_underneath`（12 实体 / 288 顶点 / `shape_digests` 逐项相同） | **PASS** |
| AC-M3-8④ 异常锚点双读 | PM 真浏览器读数：表层 `t=0 revealed=false` → 深层 `t=232/316 revealed=true`；`reveal_at_tick=55`；3 个锚点全有双读 | **PASS** |
| AC-M3-8⑤ ISS 关闭判据① | `07_adr.md` 含 **ADR-016 世界观作为可检查契约（治愈内核 + 悬疑外壳）**，依据列 `REQ-…005 §4 AC-M3-8` + `ISS-20260922-001` | **PASS** |
| 内核全量回归 | PM 亲跑 `pytest tests/ -q -p no:cacheprovider`（`kernel`）⇒ **151 passed / 0 failed / 0 skipped**，exit 0（填掉 R3 自述的「全量未重跑」GAP） | **PASS** |
| D-12 冻结面口径 | PM 亲算双向比对：实算改动 **46** 条，**零未声明漂移**；声明面 11 条「未实现」经核对**全部是新增文件**（不在 `V0_M2.sha256` 内），非漏做 | **PASS** |
| 交付面卫生 | `02_source` 文件 **150**；生成残渣 **0** | **PASS** |

**汇总**：`overall_status = has_medium_low_risk`（**0 CRITICAL**）。

## 18. 判据层 CRITICAL 的收敛轨迹（本轮最硬的一段）

`R3-C1` 是 M3 唯一的 CRITICAL，且**连续两轮未收敛**，PM 亲自介入：

| 轮 | PM 注入（只作用于 `underneath` 一态） | 实测 | 性质 |
|---|---|---|---|
| R3 前 | 基线 | `PASS=27 FAIL=0` exit 0 | 绿 |
| R3 前 | `mesh.scale.set(3,3,3)` | `PASS=27 FAIL=0` exit 0 | **逃逸** |
| R3 前 | `mesh.rotation.y = π/2` | `PASS=27 FAIL=0` exit 0 | **逃逸** |
| R3 前 | `camera.position.set(40,40,40)`（D-7 明文禁止） | `PASS=27 FAIL=0` exit 0 | **逃逸（零判据）** |
| R5 后 | 上列 3 条 + 12 条同类（共 **15 把几何/对象刀**） | **15/15 `FAIL=1` `two_reads_share_scene_structure`** | 判据有牙 |
| R5 后 | **8 把相机刀**（`position` / `fov` / `zoom` / 手改 `projectionMatrix` / `setViewOffset` / `near` / `lookAt` / `up`） | **8/8 `FAIL=1` `two_reads_use_same_render_camera`** | 判据有牙 |
| R5 后 | 对照（不动相机/世界） | `PASS=31 FAIL=0` 绿 | **无假红** |

**根因（PM 定性）**：断言名为 `two_reads_share_rendered_geometry`（「渲染后几何」），实现只覆盖
`geometry.parameters` + `position` attribute + 装配后 `mesh.position` ⇒ **名字过度声称**。
实现本身干净（两态确共用同一几何），**被绕的是判据覆盖面**。按 PM 口径「可被绕过的判据 = 假绿 = CRITICAL」，
**不得**以「实现没问题」放行。

**PM 给出的闭式口径**（不再补字段，而是把结构性场景状态**闭式枚举**）：几何（`index` 摘要 + `groups` +
`position`/`normal`/`uv` attribute）、对象（**`matrixWorld`** + `visible` + `layers.mask` + `renderOrder` +
根子树身份/父子链）、相机（`matrixWorld` + `projectionMatrix` + `zoom` + `viewOffset` + `fov/near/far` +
**实际渲染相机身份**）。该闭式集合**按构造**覆盖 Raven 报出的全部剩余类。

**去过度声称已落地**：断言改名为 `two_reads_share_scene_structure`，新增 `two_reads_use_same_render_camera`；
旧名仅存于注释里的改名说明；`06` 补 **13 条不覆盖清单**（逐条给理由）；沿用 **G9 口径**声明「一致性判据 ≠ 防篡改」。

**分级裁定（R5 上抛项 1）**：Raven 判 CRITICAL / architect 降 MEDIUM ⇒ **PM 确认 MEDIUM**。
理由：该 5 类（钉摘要常量 / 缓存 `cameraReport` / 伪造渲染入参记录 / 判据体自比）**全部要求改写判据自身的取数点或判据体**
= **判据侧改写**；而 `R3-C1`/`R4-C1`/`R4-C2` 的 CRITICAL 口径针对**场景侧注入**（不动判据即逃逸），两者**不同类**。
且判据源码在冻结面内（`02_source` 150/150 OK）⇒ 判据侧改写**由清单这一独立机制可发现**。

## 19. M3 落盘口径与 P-9 跨面迁移（审计要点）

1. **落盘范围 = `V0_M3.sha256` 冻结面（202 条）**：`02_source/**` 150 + `spikes/**` 50（s12-session 38 + s13-render 12）
   + `03_artisan_self_test.log` + `06_v0_m3_self_test.md`。
   工作区 `spikes/s12-session/**`（398 文件）/ `spikes/s13-render/**`（1275 文件）的**运行产物与 scratch 不落仓库**
   —— 这是 `R4-M4` 冻结面口径修正的结果（可重生成的运行产物移出哈希面），使「任意次数真浏览器复跑后 `shasum -c` 仍全 OK」成立。
2. **P-9 跨面迁移（已声明）**：`spikes/s5-latency-calibration/calibration.registry.json` 是派生缓存，
   M3 的 P-9 把三处 `path` 由**绝对路径改为相对路径**（M3 门禁新断言要求 `absolute=0`）。
   该文件**不在**任何里程碑冻结面内 ⇒ 落盘时在仓库内**就地 `registry --force-rewrite` 迁移**。
   迁移后 `shasum -c V0_M3.sha256` 仍 **202 OK / 0 FAILED**；幂等复验：再跑 `registry`（不带 flag）⇒ `rewritten=false`、**逐字节不变**。
3. **落盘执行与 PM 独立复验（落盘后实测，命令级）**：

   | 判据 | 落盘后 PM 实测 |
   |---|---|
   | `shasum -a 256 -c V0_M3.sha256`（`v0/`） | **202 OK / 0 FAILED**（其中 `02_source` **150/150 OK**） |
   | `bash verify_specs.sh --quiet`（`02_source`） | `verify_specs: OK (130 checks passed, 0 skipped)`，exit 0 |
   | `npm test`（`session`） | **16 pass / 0 fail** |
   | `npm test`（`web`） | **4 pass / 0 fail** |
   | 端到端基线 300 tick | `925` 事件 / `6` 检查点 / `chain_tail=baecca92…` / `state_hash=9a4ae3da…` —— 逐位等于 M1 |
   | registry 幂等 | 迁移后复跑 ⇒ **逐字节不变**（`5078be30…`） |

4. **早前里程碑清单在本仓库的失配是预期行为**（冻结时刻证据 + 同树生长）：`V0_M2.sha256` 现为 192 OK / 46 FAILED
   （45 条 `02_source` 被 M3 演进 + 自测日志追加）；`V0_M1.sha256` 为 95 OK / 181 FAILED / 128 缺失（含未随仓库提供的负控沙箱）。
   **不是**交付面被改。

## 20. M4 结转清单（禁止静默）

1. **判据层非覆盖 13 条**中的：相机自身 `Object3D` 层状态；渲染相关状态（`fog`/`background`/`sortObjects`/`frustumCulled`）；
   材质层属性；量化边界 `1e-6`；判据取数点自命中。
2. **冻结面**：非 f4 驱动（f5/f6/f1）产物是否一并出哈希面；`runtime*` 前缀过宽（可误排 `02_source/runtime-*`）；
   排除仅按名字模式 ⇒ **被排除路径不得承载判据结论**。
3. **声明一致性**：`06` 的 R3 段（第 437 行）残留绝对措辞；`04`/`05` 既有轮次内容无哈希锚 ⇒ 不可核验。
4. **链外锚**：AC-M3-8③⑤ 的**原始运行读数**外置后无独立锚。
5. **`R3-RAV-M1` 桥权限自述**：**一旦接网络监听即升 CRITICAL**（升级条件见 `06` R3-H）。
6. **Sentinel 遗留 MEDIUM**：`delta` 位移在**读法切换**时被 `rebuild(latestState)` 吃掉（R3 引入，非 R4/R5）。

## 21. 诚实边界（不得在总结里弱化）

- 本轮交付 = **双模式会话层（W7）+ 渲染层与 UI（W8）+ 世界观落地**，**不是**完整产品：
  观测层（W9）、集成验收（W10）属 **M4**。
- **一致性判据 ≠ 防篡改**：`scene_assert` 证明的是场景结构一致性；判据侧改写不被判据捕获，
  只由**清单**这一独立机制发现。**禁止**把 `scene_assert` 读作「未被篡改」的证据。
- **本仓库不含真浏览器截图证据**：运行产物按冻结面口径移出哈希面且未随仓库提供；
  复现需按 `spikes/s13-render/browser-accept.mjs` 自行真跑（脚本与负控脚本**在**冻结面内）。
- 「`verify` exit 0」**不等于**「日志未被篡改」——抗改写必须传 `--expected-hash`。
- 残留 **MEDIUM/LOW/GAP 若干**（0 CRITICAL）已逐条登记 M4（见 §20），**不作「已关闭」处理**。
