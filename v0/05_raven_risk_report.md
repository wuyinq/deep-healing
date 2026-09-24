model: deepseek-v4.1-flash | 来源: 派单进程 pid 89451（`--query-file <ws>/.task-raven-n2-gate.pointer.txt`，ppid=1，launchd 直接收养）| 时间: 2026-09-24T04:30:00Z（12:30:00 CST）

# 05 — Raven 红蓝对抗门禁（N2 徐琴人物形象）· 风险报告（**第 2 轮：r4 之后的最终树**）

- task_id：`REQ-20260924-002-deephealing-xuqin-appearance`（**不加**轮次/角色后缀）
- 工作区 `<ws>` = `…/dev_team_workspace/REQ-20260924-002-deephealing-xuqin-appearance`
- 仓库 `<repo>` = `/Users/wooyinq/personal/deep-healing`（**只读**）
- 写集：仅 `<ws>/05_raven_risk_report.md` + `<ws>/.raven.progress.json`；`<ws>/02_source/**`、`<ws>/docs/**`、`<ws>/spikes/**`、`<repo>/**` 全程**只读**
- 本轮与 **Sentinel 并发**（两个门禁并行）。**本报告不引用 Sentinel 的任何读数**；下列每条读数都是我自己跑出来的。
- 本报告**不修改代码、不写修复**；功能性 Bug 只标注并移交 Sentinel 范畴。
- **第 1 轮报告的读数已作废**（绑定在 09:35 那棵树）；本报告只沿用它留下的**探针 / 反例 / 注入配方**，所有读数重新取得。

---

## 0. 开工三件事（读数）

### 0.1 单写者 / 通道自证

```
$ cat <ws>/.task-raven.pid                     → 89451
$ ps -o pid=,ppid=,command= -p 89451
89451     1  …/hermes -p raven chat --query-file <ws>/.task-raven-n2-gate.pointer.txt --oneshot --run-budget 7200
$ ps -eo pid,etime,command | grep 'hermes -p raven' | grep -v grep
（仅 89451 一行）
$ ps -eo pid,etime,command | grep -E 'hermes -p (artisan|sentinel)' | grep -v grep
（artisan：无；sentinel：pid 89428 存活 = 并发门禁，预期）
```

⇒ 我是**派单进程**（ppid=1，command 带本任务 pointer），**不是** gateway 侧会话；**无第二 raven 写入者**；artisan 已退出（无产品 writer）。

### 0.2 开工快照（漂移即停）

```
$ git -C <repo> rev-parse HEAD
18f9facfc11281f622a6ff7be455a02d5b92ecea          # 与设计 F-1 / 第 1 轮一致
$ git -C <repo> status --porcelain | wc -l
0                                                  # 仓库零改动
$ diff -rq <repo>/v0/02_source <ws>/02_source      # 18 行，全部在本轮写集内
  （art-bible.md / manifest.txt / verify_specs.sh / scene_assert.mjs / world.ts 修改；
    npc.appearance.schema.json / tools/verify_npc_appearance.py / web/src/scene/character.ts 新增；
    xuqin 的 npc-006.json / assets/manifest.json / assets/character-refs/** / pack.sig；
    north 的 npc-001..005.json / pack.sig）
$ diff -rq <repo>/…/districts/xingfu-xiaoqu <ws>/…/districts/xingfu-xiaoqu
（无输出，exit 0）                                 # 主包逐字节零改动 ✔
$ shasum -a 256 <ws>/…/xingfu-xiaoqu/pack.sig
844f7606d5b548517a1af3a052bf882b7e38563297a644bcd70e1bd3dafcb87b
$ grep -n MAIN_PACK_SIG_SHA256 <ws>/…/tools/check_npc_admission_gate.py
42:MAIN_PACK_SIG_SHA256 = "844f7606d5b548517a1af3a052bf882b7e38563297a644bcd70e1bd3dafcb87b"   # 冻结锚一致 ✔
$ find <ws>/02_source <ws>/docs -newermt '2026-09-24 12:11:00'   # 我开工之后
（空）                                             # 被审对象在我审计期间未变动 ✔
```

### 0.3 我自己的独立读数（**非**引用 Artisan / Sentinel）

| 面 | 命令（workdir） | 我的读数 |
|---|---|---|
| 场景判据 | `node scripts/scene_assert.mjs`（`02_source/v0_skeleton/web`） | **PASS=65 FAIL=0 / exit 0**（交付树与 `/tmp` 副本各跑一次，读数相同） |
| 外形契约校验器 | `python3 v0_skeleton/tools/verify_npc_appearance.py --root .`（`02_source`） | **exit 0**；`appearance_ok=true`、`probe_ok=true`、**9 条探针全部 `fired=true`** |
| 全量门禁 | `bash verify_specs.sh`（`02_source`） | **PASS=164 FAIL=0 SKIP=0 / exit 0** |
| pack 校验 | `python3 v0_skeleton/tools/verify_pack.py <pack>` | 主包 14 files **OK** / 提案包 13 files **OK** / 北区 14 files **OK** |
| IP 边界（交付树本体） | `python3 v0_skeleton/tools/scan_ip_boundary.py --root .` | **exit 0**；`unwhitelisted_hits=0`（whitelisted 2 = `jump_scare` 白名单） |
| 冻结锚 / 主包 | §0.2 | **一致** ✔ |
| `npc-006.json` | `shasum -a 256` | `6e40368c063eab410930ce9616777cd550c47cf6c870993140632245b994e50d`（== `03` r4 段声称的开工值） |
| 交付面残渣 | `find <ws>/02_source \( -name __pycache__ -o -name .pytest_cache -o -name dist -o -name node_modules -o -name '*.pyc' \)` | **0** |

> **并发争用声明**：本轮与 Sentinel 并发。上述读数**未出现**任何红项；三面判据我这边一次跑绿，**无需**「重跑到绿」的处置。

---

## 0.4 任务书 §0bis / §0ter 逐条结论（先给表，细节见后文）

| # | 任务书要求 | 我的结论 | 证据 |
|---|---|---|---|
| §0bis-1 | 「0 删除 / 0 弱化既有断言」是否属实 | **属实** | `diff -u` HEAD↔当前：398→1159 行，**3 个 hunk、0 条 `-` 行**（纯追加）⇒ 既有区段逐字未动；6 条点名断言全在既有未改区段内 |
| §0bis-2 | 「AC-10 的 `verify_asset_pack.py` 不可达」是否属实 | **属实（GAP 成立）** | 我复现更靠前的阻塞 `KeyError: 'asset_id'`（`verify_asset_pack.py:110`）；`tools/**` 相对 HEAD **零改动**（未放宽校验器）✔ |
| §0bis-3 | 「参考图实为 JPEG」 | **属实** | `file -b` = `JPEG image data, JFIF standard 1.01`；`xxd -l 16` = `ffd8ffe0 0010 4a46 4946`；5 张副本 ↔ 源 `sha256` 逐字相同；源文件 `mtime` 08:15–08:19（早于 Artisan 开工 08:40）未变 |
| §0bis-4 | `mask.*` provenance 是否逐字段如实 | **属实**（1 项残留见 M7） | `color/shape/material` = `design_fill:true`；`number/number_label` = `source_facts:[CHR-16,CHR-17]`；`design_note` 明写「呈现方式属设计补全（事实册内无对应 CHR 条目）」；`grep -c 面具/猪脸` 事实册 = **0/0** |
| §0bis-5 | 实机外形来自 pack 不是 fallback | **成立** | `06` §2 + 我复跑 `character_appearance_source_is_pack`（绿）；对照臂 `setAppearance(null)` ⇒ 全 `fallback`（`character_appearance_null_falls_back` 绿）；spike 未用 `setAppearance(table)` 注入日常臂 |
| §0bis-6 | 新逃逸面（`source_hex` 进比较面 / `material_hex` 排除 / 层级·visible·renderOrder·顺序） | **已逐条实证**（见 §2） | 7 条 reading-scoped 注入各 `64/1`；`material_hex` 注入**不**动两读法相等断言（`65/0`→`63/2` 的第二红是材质复算判据，不是相等断言） |
| §0bis-7 | `verify_specs.sh` 只新增 1 条 | **属实** | `diff -u` HEAD↔当前：**1 个 hunk、0 条 `-` 行、+17 行**（仅 §17b） |
| §0bis-8 | AC-8 零鉴别力口径是否如实 | **属实** | `06` §6-AC-8 写「**PASS（零鉴别力）**」「**不声称**本轮完成了同步」 |
| §0bis-9 | `03`/`06` 与磁盘一致性（抽 5 读数） | **5/5 一致**；另发现 **2 项陈旧文本**（张数 / 探针条数） | 见 §4.5（PASS=164 ✔ / scene_assert 65 ✔ / 9 探针 ✔ / 冻结锚 ✔ / 像素 diff 4/4 复算 ✔；截图张数「11」vs 实得 **12** ⇒ L2；探针条数「6/6·8/8」vs 实得 **9** ⇒ L1） |
| §0ter-1 | R1（I-9 漏项）是否闭合 | **已闭合** | 真渲染路径注入非 `eyes` 部件材质色（两读法一致）⇒ `character_material_hex_recomputable` **红**（`63/2`）；见 §2.1 |
| §0ter-2 | R2（自证项与树状态耦合）是否闭合 | **未闭合**（已登记 N4） | GEOMETRY 注入 ⇒ 主判据 + 自证项**同时**红（`63/2`）；且**新增**的 `character_material_hex_criterion_has_teeth` 也继承了同一耦合 ⇒ M2 |
| §0ter-3 | R4（`mask.number` provenance 粒度）是否闭合 | **已闭合** | `npc-006.json:157,162` 的 `design_note` 明写「编号值/文字锚 CHR-16/CHR-17；呈现方式属设计补全」 |
| §0ter-4 | R6（AC-10 阻塞理由）是否闭合 | **已闭合** | `06-acceptance-record.md` §23 + `06` R2-2 已改成更靠前的 `KeyError: 'asset_id'` 并给可复现命令；我复跑得同一 KeyError |
| §0ter-5 | R9（状态回退三例）是否闭合 | **已闭合且有牙** | 三条独立断言在场；我注入「谓词恒命中」⇒ 其中两条**直接变红**（`60/5`） |
| §0ter-6 | R3 / R5 登记遗留是否在场 | **在场** | `06-acceptance-record.md` §25 含 **R-R3**（packId 默认值不同源）与 **R-R5**（delta 不重算形态），并注明「N4」 |
| §0ter-7 | r4 新增轮廓几何是否引入新盲区 | **是（2 条新盲区）** | `hair` 纵向长度无界（`65/0` 绿）、`arm` 纵向长度无判据（`65/0` 绿）⇒ M3 / M4 |
| §0ter-8① | 机位是真实世界视点（盒内）、未隐藏/删除/改遮挡物 | **成立** | `world.ts:1107-1113` 的 `setObservationCamera` 只 `position.set` + `lookAt` + `updateMatrixWorld`；spike 全树无 `visible=false`/`remove`/改 `room` 属性；两机位均在 `room-1052` AABB 内 |
| §0ter-8② | 默认取景「玩家看到的是盒子不是人」是否如实写明 | **成立** | `06` R4 段：「默认交付取景下玩家仍看不到人（N4）」+ 像素 diff 表「默认交付取景 · daily ↔ masked = **0**（缺陷取证，未美化）」；我实测 `md5(n2-default-wide-daily) == md5(n2-default-wide-masked)` |
| §0ter-8③ | AC-9 判据形态（非实现者视觉核验 + daily/masked 像素可区分） | **像素可区分成立；非实现者核验未落地（GAP，待并发 Sentinel）** | 我实测 diff：近景 81,969 px / 侧向 5,320 px / 默认 0 px；`06` R4 的读图结论署名是**实现者**（"我的读数，不是独立门禁"）⇒ GAP-1 |
| §0ter-9 | `06` 的 F-9 / F-10 措辞 | **F-9 成立；F-10 主措辞成立（1 处分类不准）** | §23 含改口径原因/时间；§24 明写「**跨读法一致性判据**…**不是**完整性机制」；但把 `two_reads_character_criterion_has_teeth` 也列入该清单 ⇒ L4 |

**PM 硬约束 ①②③ 逐条**：①**成立**（见上表 §0ter-8①）；②**成立**（§0ter-8②）；③**部分**（像素可区分 = 实证成立；「非实现者视觉核验逐项回答看到了什么」在**交付树内**只有实现者署名 ⇒ GAP-1，须由并发 Sentinel 的 `04` 补）。

---

## 1. 隐性假设逐条（判定 + 证据 + 证伪方式）

### 1.1 外形数据通路（D1）：宿主**真的**服务 `/packs/<pack>/npcs/<id>.json`

**判定：成立（通路真跑通），但「实机外形来自 pack」的证据强度仍依赖脚手架源码排除法。**

- `world.ts` 惰性接线：`apply(snapshot)` → `maybeAutoLoadAppearance()`（`world.ts:930-943`）→ `resolveAppearanceTable({packId: queryPackId(), npcIds})` → `GET /packs/<packId>/npcs/<id>.json`（`character.ts:396`）。
- 脚手架**真的**服务该路由：`spikes/n2-appearance/serve.mjs:287`
  `/^\/packs\/([A-Za-z0-9_-]{1,64})\/(worldview\.json|npcs\/[A-Za-z0-9_-]{1,64}\.json)$/`。
- 脚手架**没有**在达标臂注入外形：全树 `grep -n setAppearance spikes/n2-appearance/*.mjs` ⇒ 只命中 `browser-accept.mjs:220` 与 `n2-obs-shots.mjs:252` 的**对照臂** `setAppearance(null)`。
- **口径澄清（沿用并复述，第 1 轮已给）**：`browser-accept.mjs:124` 的 `?pack=<pack>` 是**脚手架写进 URL 的** ⇒ 「实机外形来自 pack」隐含 **URL 带 `?pack=`** 这一前提；缺参时 `world.ts:710-719` 的 `queryPackId()` 回退到**字面量** `'xingfu-xiaoqu'`，与 `main.ts` 的**会话值**不同源 ⇒ 已在 §25 登记为 **R-R3（N4）**。
- 证伪方式：`grep -n "packs" <ws>/spikes/n2-appearance/serve.mjs`；`grep -rn setAppearance <ws>/spikes/n2-appearance/*.mjs`；`grep -n "queryPackId" <ws>/…/world.ts`。

### 1.2 通用人形兜底是否夸大了「G2 人物形象」的达成度

**判定：文档已声明住户走通用人形（不属隐瞒）；「主包 5 户两两完全相同」这一读数已在 `06` R2-3 段补充登记 ✔。**

- 我复刻 `stableIdHash`（FNV-1a 32）与 `NEUTRAL_GARMENTS` 独立算得：
  `npc-001 #7a6f63 / npc-002 #6e6455 / npc-003 #5c5548 / npc-004 #7a6f63 / npc-005 #6e6455`
  ⇒ **npc-001 ≡ npc-004、npc-002 ≡ npc-005**（几何相同、衣色同档 ⇒ 视觉不可区分）。
- `06` R2-3 段已补上该读数（F-12 落地），`06-acceptance-record.md §25` 的 R-R8 亦逐条在场 ✔ ⇒ 第 1 轮的 R8（LOW）**已闭合**。
- 证伪方式：`python3 /tmp/raven_n2g/hash_probe.py`（我本轮实跑）。

### 1.3 AC-9 口径：截图的**可复核性**

**判定：第 1 轮的「画面里没有人」缺陷**已按 PM 裁决修复到「取证机位下可见 + 默认取景如实登记」；但**验收记录本身**（`06` §3.1 / §6 的 AC-9 行）仍以 PM 已判为无效的判据声称 PASS ⇒ 见 §6-**C1**。

- 我实测的像素读数（`/tmp/raven_n2g/shot_diff.py` + `pair_diff.py`，PIL 12.2.0 逐像素）：
  ```
  默认交付取景 · daily ↔ masked     0 px（md5 完全相同：50fa2e19…）
  室内宽      · daily ↔ masked 11,186 px  bbox [530,43,657,131]
  室内近景    · daily ↔ masked  81,969 px  bbox [543,196,896,430]
  室内 3/4 侧向 · daily ↔ masked   5,320 px  bbox [589,138,666,213]
  室内宽重拍  · daily ↔ daily-2     0 px（确定性）
  侧向重拍    · daily ↔ daily-2     0 px（确定性）
  对照臂(通用人形) ↔ 室内宽 daily 186,315 px
  ```
  ⇒ 达标臂与对照臂**可区分**、daily/masked **可区分**、重拍**确定性** ✔。
- 第 1 轮那批 r1 图（`n2-desktop-1440x900-*`）我仍复核了一次：全图 13,694 px 差异，但**3D 视口区（x≥440）差异 = 0** ⇒ 与第 1 轮的 CRITICAL 结论一致（那批图确实不含可见人形，已作废为证据）。
- 几何侧：我独立核 `head` 前表面 `z=0.155` > `hair` 前表面 `z=0.135`；`eyes`/`lips` 前伸 20 / 17.5 mm（阈值 15 mm）⇒ 面部不被发覆盖 ✔。
- 证伪方式：`python3 /tmp/raven_n2g/shot_diff.py`；`node scripts/scene_assert.mjs | grep character_face_visible_beyond_hair`。

### 1.4 `source_facts` 的诚实性（逐字段核）

**判定：互斥且必居其一，0 条冒充；`mask.number/number_label` 的粒度说明已补（R4 闭合）。**

| 字段路径 | 值 | provenance | 我的核验 |
|---|---|---|---|
| `eyes.color` | `#8b1919` | `source_facts:[CHR-22]` | CHR-22 = 猩红瞳 ✔ |
| `lips.color` | `#a51c24` | `source_facts:[CHR-06]` | CHR-06 = 鲜红唇 + 苍白下巴 ✔ |
| `skin.color` | `#dfd2c8` | `source_facts:[CHR-06,CHR-22]` | ✔ |
| `garment.color` | `#8f1d1d` | `source_facts:[CHR-05]` | CHR-05 = 红色外衣 ✔ |
| `mask.number` | `"8"` | `source_facts:[CHR-16,CHR-17]` + `design_note` | **粒度已补**：「编号值锚 CHR-16/17；『刻在面具上』属设计补全」✔ |
| `mask.number_label` | `"八号"` | 同上 | ✔ |
| `hair.*` / `garment.cut` / `height_cm` / `age_look` / `build` / `mask.color` / `mask.shape` / `mask.material` | — | `design_fill:true` + `design_note` | 事实册 `grep -c 面具` = **0**、`猪脸` = **0** ⇒ 面具本体标 design_fill **属实** ✔ |
- 校验器读数（我实跑）：`every_field_has_provenance.fields = 65`、`failures = []`；`source_facts_resolve.referenced = [CHR-05,06,16,17,22]`、`unresolved = []`、`unverified_hits = []`。
- **残留（M7）**：`mask.shape` 的 `design_note` 写「锚点**章**见 DESIGN-20260924-001 A9（`ch14221` / ch240）」，而 PM 已自纠 **`ch14221` 是行号不是章节号**（真实章节 ch229/ch230/ch240/ch250）⇒ 交付面与 `01_architecture_design.md:338-339` 都保留了这个已被更正的引用。
- 证伪方式：`grep -c 面具 <ws>/02_source/fidelity/05-character-dossiers.md`；`grep -n ch14221 <ws>/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/npcs/npc-006.json`。

### 1.5 **新增**隐性假设：验收记录与 PM 裁决同步（本轮最重要的一条）

**判定：不成立 —— 见 §6-C1。**

- PM 在 11:20 的追加更正里明确要求：把「① 机制子句 = PASS；② 可辨识视觉子句 = 载体移交 N4；③ 本轮不得再为可辨识开新迭代」写进 `06_v0_n2_self_test.md` **与** `06-acceptance-record.md`，并保留 r3 截图作为「方盒不可辨识」的对照。
- 我读盘：`06_v0_n2_self_test.md`（mtime 12:09）**没有**这三条的措辞（`grep -n '机制子句\|视觉子句'` = 0 命中）；`06-acceptance-record.md`（mtime **10:28**，早于该裁决）**整份没有 N2 的 AC-9 条目**（`grep -n AC-9` 只命中 M1 期的 ADR 条目）。
- 同时 `06` §3.1（第 81 行）与 §6 的 AC-9 行仍把「**部件数 + 颜色 hex**」当作「可辨识」的可复核口径并标 **PASS** —— 这正是 PM 明文否定的证据形态（「只有文件名/部件数/配置读数 = 无效证据（本轮已踩过）」）。
- 证伪方式：`grep -n '机制子句\|视觉子句' <ws>/06_v0_n2_self_test.md <ws>/docs/architecture/06-acceptance-record.md`（0 命中）；`grep -n AC-9 <ws>/docs/architecture/06-acceptance-record.md`。

### 1.6 **新增**隐性假设：「两条独立取数路径」依赖 `torso.offset == 0`

**判定：不成立（是巧合，不是结构保证）—— 见 §6-M5。**

- `characterReport()`（mesh 层读回，`world.ts:864-901`）对**根部件**恒报 `local_offset = [0,0,0]`（注释明写「相对人物放置点 ⇒ 根部件恒为 [0,0,0]」）；而 `geometryFor().character_shapes`（装配函数产物）报的是 `PART_TABLE` 里的 `offset`。
- 二者当前相等，**只因**交付表的 `torso` 恰为 `{ offset: [0,0,0] }`。我注入 `torso` offset = `[0, 0.20, 0]`（合法几何调整）后：`character_parts_fingerprints_recomputable` **变红**，`first_diff index 9`，两个条目的 `local_offset` 分别是 `[0,0,0]` 与 `[0,0.2,0]`，**其余字段逐字相同**。
- ⇒ 该断言不是「两条路径互相独立校验」，而是「两条路径在当前几何下偶然重合」；它会对合法的 torso 位移**假红**，同时在口径上并不能证明根部件 offset 一致。
- 证伪方式：`bash /tmp/raven_n2g/probe_fp.sh`（`first_diff index 9` 一行）。

### 1.7 **新增**隐性假设：`room` 盒 = 房间**体量**（而非实心体）

**判定：成立（PM 已明文允许「房间内部视角」），但它是「盒内机位」合法性的唯一支点。**

- 两个取证机位 `[5, 0.35, 17.4]` 与 `[6.9, 0.35, 16.8]` 都落在 `room-1052` 的 AABB `x∈[2.3,7.3] y∈[-1.5,1.5] z∈[12.5,17.5]` **内部**；而该 room 在渲染里是 `sizeFor('room')=[5,3,5]` 的**不透明盒**（`lighting.ts` 的 `healingMaterial` 无 `transparent`/`opacity`）。
- 若不把 room 盒理解为「房间体量」而理解为「实心几何体」，则「盒内机位」等价于**相机位于实心体内部**。相机**没有穿过**任何几何体（近平面在盒内、朝向角色，盒远面在角色之后），因此不违反 PM「不是把相机塞进盒子里穿过几何体看」的字面禁令。
- 这条假设若在 N4 的建筑几何重做时被改变（例如 room 变成带厚度的墙体 / 剖切面），取证机位的合法性需要重新论证。
- 证伪方式：`grep -n 'INDOOR_WIDE\|INDOOR_SIDE' <ws>/spikes/n2-appearance/n2-obs-shots.mjs`；`grep -n 'transparent\|opacity' <ws>/…/lighting.ts`。

---

## 2. 架构缺陷 / 确定性逃逸面（含注入配方与读数）

**方法**：全部注入在 **`/tmp` 整树副本**上做（`mktemp -d` + `rsync` + `node_modules` 软链重建），跑的是**交付树原样的 `scene_assert.mjs`**（不是我的复刻判据），交付树零改动（§0.2 的 `find -newermt` = 0 自证）。
驱动器：`/tmp/raven_n2g/run_injections.sh`（world.ts 锚点注入）、`/tmp/raven_n2g/part_tamper.py`（改 `PART_TABLE` 尺寸/偏移）、`/tmp/raven_n2g/replace_pair.py`（定点替换）。

### 2.1 R1（第 1 轮 I-9 漏项）—— **已闭合，实证**

| # | 注入（配方） | 注入前 | 注入后 | 抓到它的判据 |
|---|---|---|---|---|
| MATOTHER | `world.ts` 的 `mesh.add(partMesh)` 后插 `if (part.part === 'arm_l') { partMesh.material.color.set('#00ff00'); }`（**两读法同时生效**） | `65/0` | **`63/2` exit 1** | `character_material_hex_recomputable`（detail 实测 `arm_l=#00ff00/#00ff00`） |
| MATHAIR | 同上，部件换 `hair` | `65/0` | **`63/2` exit 1** | `character_material_hex_recomputable`（`hair=#00ff00/#00ff00`） |

⇒ 第 1 轮「非 `eyes` 部件材质色零判据覆盖」的漏项**已闭合**：判据从「只 `eyes`」扩到 **10 个日常着色部件 + 面具态 `mask`**（`scene_assert.mjs:333-374`），且我用**真渲染路径**（不是它自带的内存级负对照）验证了它有牙。

### 2.2 逃逸面总表（每条给注入配方与读数）

| # | 注入（只作用于 `underneath` 读法，除注明外） | 结果 | 被哪条判据抓到 |
|---|---|---|---|
| I-1 | `partMesh.visible = false` | **`64/1` exit 1** | `two_reads_share_scene_structure`（`objects_first_diff=#6:npc-001/head/visible`） |
| I-2 | `partMesh.renderOrder = 7` | **`64/1`** | 同上（`…/render_order`） |
| I-3 | `partMesh.scale.set(3,3,3)` | **`64/1`** | 同上（`…/matrix_world`） |
| I-4 | `partMesh.rotation.y = Math.PI/2` | **`64/1`** | 同上（`…/matrix_world`） |
| I-5 | `partMesh.layers.set(2)` | **`64/1`** | 同上（`…/layers_mask`） |
| I-6 | `root.add(partMesh)`（改父子层级） | **`64/1`** | 同上（`…/parent_id`） |
| I-7 | `partMesh.name += '-x'` | **`64/1`** | 同上（`…/id`） |
| I-8 | `partMesh.geometry = new THREE.BoxGeometry(0.1,0.1,0.1)` | **`63/2`** | `two_reads_share_character_parts`（`first_diff=#0`）+ `two_reads_character_criterion_has_teeth`（见 §4.3） |
| I-9 | 非 `eyes` 部件材质色（两读法一致） | **`63/2`（已红）** | `character_material_hex_recomputable`（**R1 闭合**） |
| I-10 | 颠倒 `CHARACTER_PART_ORDER`（两读法一致） | **`65/0`（仍绿）** | **无** ⇒ 已知边界（`06-acceptance-record §24` 已登记） |
| **N-1** | `hair` 高 0.72 → **2.20 m**（垂到脚面以下） | **`65/0`（漏）** | **无** ⇒ §6-**M3** |
| **N-2** | `arm_l/arm_r` 高 0.40 → **0.06 m**（小短桩） | **`65/0`（漏）** | **无** ⇒ §6-**M4** |
| N-3 | `coat` 宽 0.38 → 0.52（判据允许的上限） | **`65/0`** | 无（在 `COAT_NARROWER_THAN_HAIR_MIN_M` 允许范围内） |
| N-4 | `hair` 前表面推到 `z=+0.20`（r2 缺陷复现） | **`63/2`** | `character_face_visible_beyond_hair` + `character_eyes_lips_protrude_from_face` |
| N-5 | `torso` 0.66 → 1.30 m 且 offset `[0,0.20,0]` | **`63/2`** | `character_parts_fingerprints_recomputable`（**假红**，见 M5）+ `character_hair_reads_long` |
| N-6 | `mask` 前表面退到 `z=0.10`（不再盖住瞳） | **`64/1`** | `character_mask_reads_half_face` |
| N-7 | 把 `matchesStatePredicate` 的 `target_entity_in` 改成**恒命中** | **`60/5`** | `character_state_falls_back_to_daily_with_schedule_null` + `…_without_schedule_key`（R9 有牙）+ 3 条连带红 |

**判定**：
- 结论①（**正面**）：`visible` / `renderOrder` / `scale` / `rotation` / `layers` / **父子层级** / 对象名 / 几何替换 —— 全部在比较面内，由 `two_reads_share_scene_structure` 的**遍历式**摘要捕获（7 条注入逐条变红，实证）。
- 结论②（**负面**）：比较面是**跨读法一致性**判据，**不是**防篡改判据 —— 两读法**一致**的偏差（I-10 / N-1 / N-2 / N-3）零判据覆盖。该性质 `06-acceptance-record §24` 已如实登记（F-10）✔。
- 结论③（**本轮新增**）：r4 把 `hair` 加宽到 0.58、`torso` 收到 0.38、`arm` 缩到 0.40 之后，**新判据只约束横向关系，不约束纵向尺寸** ⇒ N-1 / N-2 两条「画面明显坏掉但判据全绿」的新盲区（M3 / M4）。

### 2.3 `characterReport()` 与 `geometryReport()` 是否「同一入参算两遍」

**判定：不是恒真式（取数路径确实不同），但「独立」的强度比措辞弱 —— 且根部件 offset 口径不同（M5）。**

- `character_shapes` = 调 `buildCharacterPartsForState()` **重算**并用 `shapeOf()` 度量；`characterReport()` = 从**真的挂进场景图**的 mesh 读回 `geometry.parameters` / position 属性 / `mesh.position` / `userData`。
- 二者**共享**装配函数 ⇒ 抓不到「装配函数本身算错」；**抓得到**「装配之后被改写」（I-8 实证）。
- **新增读数（M5）**：根部件 `local_offset` 在两侧口径不同（mesh 侧恒 `[0,0,0]`，函数侧 = `PART_TABLE.offset`）⇒ 当前绿是巧合。
- 随机性/时间源封堵仍成立：`grep -n 'Math.random|Date.now|new Date' web/src/scene/**` 只命中注释；且装配若引入随机，`setReading()` 触发的 rebuild 会让两读法分叉 ⇒ `two_reads_share_character_parts` 必红。

### 2.4 装配路径的非确定性 / 状态泄漏

**判定：无随机、无时间源；状态更新缺口与第 1 轮相同（均已登记 N4）。**

- `setAppearance()` / `setReading()` → `rebuild()`：先 `root.remove(mesh)` 逐个、再 `meshes.clear()` + `partMeshes.clear()` ⇒ 旧部件不残留 ✔
- **缺口①（delta 不重算形态）**：`apply(delta)` 只处理 `transform.pos_mm` ⇒ 若内核以 delta 下发日程变化，面具态要等下一次 snapshot 才切换 ⇒ 已登记 **R-R5（N4）** ✔
- **缺口②（自动接线一次性）**：`maybeAutoLoadAppearance()`（`world.ts:930-943`）在**第一次** snapshot 就置 `appearanceAutoLoadAttempted = true`，**早于** `npcIds.length === 0` 的提前返回 ⇒ 若首个 snapshot 不含 `kind==='npc'` 实体，自动接线**永久失效**（此后出现的 NPC 一律通用人形，且**无**提示）。**这条在本轮仍未见登记**（`06-acceptance-record §25` 无对应条目）⇒ §6-**M9**。
- **缺口③（资源不回收）**：`rebuild()` 从不 `geometry.dispose()` / `material.dispose()`；本轮每次 rebuild 新建 12 根 + 50 部件资源 ⇒ 已登记 **R-R5b（N4）** ✔
- 证伪方式：读 `world.ts:805-815, 930-943, 1060-1075`；`grep -n dispose web/src/scene/world.ts`（只命中 renderer）。

### 2.5 既有确定性契约是否被破坏

**判定：未破坏（实证）。** `two_reads_share_geometry` / `geometry_positions_match_seeded_state` / `two_reads_share_geometry_object_identity` / `two_reads_share_scene_structure` / `two_reads_share_camera` / `assembly_report_stable_after_reading_round_trip` / `geometry_covers_every_seeded_entity` 全部在场且全绿；`structureReport().objects` 从起点 12 个扩到 **62 个**（含 50 个部件 mesh）仍在同一比较面内（I-1~I-7 实证有牙）。

### 2.6 r4 轮廓几何的**独立遮挡核验**（我自己的 AABB 光线测试）

工具：`/tmp/raven_n2g/occlusion.py`（部件盒按实测 `size` + `local_offset` + 放置点 `(5,0,15)` 还原为世界 AABB，逐面 486 采样点、slab 求交；被其它盒**包住**的采样点计为不可见）。

| 目标部件 | 默认宽机位 | 室内宽 | 室内近景 | 室内 3/4 侧向 | 遮挡者 |
|---|---|---|---|---|---|
| `eyes` | 0% | 0% | 0% | 0% | **`head`（背面嵌入）+ `mask`** —— **`hair` 不在遮挡者列表** ⇒ r4 加宽**没有**遮住瞳 |
| `lips` | 41% | 54% | 54% | 54% | `head`（背面嵌入）+ `mask`（默认机位）—— **`hair` 不在列表** |
| `arm_l` | 0.2% | 40% | 25% | 5.8% | **`hair` 57%–87%**、`torso`、`coat` |
| `arm_r` | 35% | 40% | 18% | 44% | **`hair` 56%–75%** |
| `torso` | 14% | 22% | 17% | 21% | **`hair` 54%–68%**、`coat` 33% |
| `mask` | 71% | 72% | 72% | 72% | `head`（背面嵌入） |

⇒ **两条可执行结论**：
1. 「r4 的 `hair` 加宽是否遮住 `eyes`/`lips`」= **否**（`hair` 从未出现在瞳/唇的遮挡者集合里；因为 `hair` 前表面 `z=0.135` 严格在 `head` 前表面 `0.155` 之后）。
2. 「`torso` 收窄后 `arm_*` 是否穿模」= 几何上**没穿模**（内缘缝隙 0–5 mm 在判据容差内），但**画面里手臂被发遮住 56%–87%** ⇒ 判据 `character_silhouette_narrows_at_waist` 读绿**不等于**「臂在画面上可读」（Artisan 已在 `03` R4-8-2 如实登记为造型取舍）⇒ §6-**L5**。

---

## 3. 安全 / IP

### 3.1 `appearance` 是否成为逐字搬运正文的通道 —— **注入探针：判据有牙（我自建）**

- 探针（`/tmp` 副本）：把一段 **75 个 CJK** 的正文式段落用中文引号包起来塞进 `appearance.hair.color.design_note`，再跑交付树原样的扫描器：
  ```
  $ python3 v0_skeleton/tools/scan_ip_boundary.py --root <副本>/02_source
  exit=1   unwhitelisted_hits=1
  E_IP_BOUNDARY: v0_skeleton/districts/xingfu-xiaoqu-xuqin/npcs/npc-006.json:190:verbatim_body_paragraph:75
  ```
  ⇒ **必命中**（独立于 Artisan 的 N-8 读数）。
- 交付树本体：`scan_ip_boundary.py --root <ws>/02_source` = **exit 0 / unwhitelisted_hits=0**（whitelisted 2 条为 `jump_scare` 白名单）✔
- `scene_assert` 侧同口径判据 `appearance_has_no_verbatim_paragraph` 亦在场（含合成 61 字探针的自证）；**我实测它对被我污染的副本变红** ⇒ 它读的是盘上内容，不是常量 ✔

### 3.2 参考图登记的许可合规 —— **GAP（不可达为真），阻塞理由已更正**

- 我复现的**最靠前**阻塞（与 `06-acceptance-record §23.1` 记载一致）：
  ```
  $ cd <ws>/02_source/v0_skeleton && python3 tools/verify_asset_pack.py \
      --pack districts/xingfu-xiaoqu-xuqin \
      --manifest districts/xingfu-xiaoqu-xuqin/assets/manifest.json \
      --license-table ../asset.license.table.data.json
  exit=1；末行 KeyError: 'asset_id'（tools/verify_asset_pack.py:110）
  ```
  根因：工具期望 `assets[].asset_id`，交付 manifest 用 `assets[].id`（`asset.manifest.schema.json` 口径）。
- **未放宽校验器 = 属实**：`diff -rq <repo>/v0/02_source/v0_skeleton/tools <ws>/…/tools` ⇒ 既有工具**零改动**（唯一新增 = `verify_npc_appearance.py`）。
- 参考图本体：`license: "unknown"`、`runtime_usable: false`、`provenance.verification_status: "not_claimed"`、逐条 `gap` 字段 —— **如实**；`asset.license.table.data.json` 的 `default_policy: "deny"` 未把 `unknown` 纳入白名单 ⇒ A3 必拒的机制成立。
- ⇒ **GAP 成立**；PM 裁决 2 已改口径（≥3 张参考表 + `derived_from` 可解析），口径变更已按 F-9 登记进 `06-acceptance-record §23`（含原因 + 时间 + 可复现命令）✔

### 3.3 参考图真实格式与源文件只读性（§0bis-3 复核）

```
$ file -b <ws>/02_source/…/assets/character-refs/xuqin-*.jpg
JPEG image data, JFIF standard 1.01, … , baseline, precision 8, 1440x2880 / 2048x2048 / 1664x2496 / 2880x1440 / 3552x1184
$ xxd -l 16 xuqin-portrait-01.jpg
00000000: ffd8 ffe0 0010 4a46 4946 0001 0100 0001     # JFIF，确为 JPEG
$ shasum -a 256 <ws>/refs/appearance/*.png  vs  <ws>/…/character-refs/*.jpg
68fa7f4c… / 84af6cd6… / 597515ee… / 6d0805c2… / f1ef0701…     # 5/5 逐字相同
$ stat -f '%Sm' <ws>/refs/appearance/*
08:15–08:19（早于 Artisan 开工 08:40，与第 1 轮读数一致）
```
⇒ 源文件扩展名写作 `.png` 实为 JPEG（G3 如实登记）；登记副本按**真实格式**命名 `.jpg` 且**未重编码**；源文件 `mtime` 未变。

### 3.4 密钥 / 绝对路径 / 可执行文件进 pack

- 本轮全部改动/新增文件中 `grep -c '/Users/'` = **0**（逐文件核：schema / 校验器 / `character.ts` / `world.ts` / `scene_assert.mjs` / `npc-006.json` / 北区 `npc-001.json` / `assets/manifest.json` / `manifest.txt`）。
- 密钥模式扫描：上述文件 `grep -c 'Bearer'` = 0、`grep -c 'api_key'` = 0；`grep -c 'sk-'` 在 `assets/manifest.json` = 4、`manifest.txt` = 6，**逐条核对后全部是 `xuqin-mask-01.jpg` 里 `sk-` 的子串**（假阳性），非密钥。
- pack 内文件越界：`verify_pack.py` 三包全绿（含 `undeclared_file` / `hash_mismatch` 判据）⇒ 无可执行文件/未声明文件进包 ✔

---

## 4. 判据诚信

### 4.1 既有断言是否被弱化 / 删除（**逐行 diff**）

- 方法：`git -C <repo> show HEAD:v0/02_source/v0_skeleton/web/scripts/scene_assert.mjs` vs 当前交付版本，`diff -u`。
- 读数：**398 行 → 1159 行；3 个 hunk；`grep -c '^-[^-]'` = 0**（**零删除、零改写**）。3 个 hunk 分别是：
  1. `@@ -40,8 +40,10 @@`：新增 2 行 import（`three`、`appearanceTableFromDocuments`）；
  2. `@@ -322,6 +324,31 @@`：在既有区段之后**插入** 25 行（取证机位加法判据）；
  3. `@@ -388,7 +415,741 @@`：在汇总行之前**追加** N2 全部判据（含 `+// ===== 7) 汇总` 注释行）。
- ⇒ 任务书 §0bis-1 点名的 6 条（`two_reads_share_geometry` / `two_reads_share_scene_structure` / `two_reads_share_camera` / `geometry_positions_match_seeded_state` / `geometry_covers_every_seeded_entity` / `assembly_report_stable_after_reading_round_trip`）**逐字未变**（均落在未改动的既有区段内）。
- **判定：Artisan「0 删除 / 0 弱化既有断言」= 成立。** 未被弱化 = **不构成 CRITICAL**。
- `verify_specs.sh`：`diff -u` = **1 个 hunk、0 条 `-` 行、+17 行**，全部是新增的 §17b（`NA_OUT=…verify_npc_appearance.py…`）；既有检查项**逐字不动** ✔（任务书 §0bis-7 核实）。
- 断言条数轨迹（我核过的三处）：起点 **31** → r1 **51** → r2 **56** → r3 **61** → r4 **65**（我实跑 = 65）。

### 4.2 新判据逐条负对照（**我自己注入**）

见 §2.2 的 I-1~I-10 / N-1~N-7 表（每条给「注入前 / 注入后」读数）。另：
- 契约校验器自证组（我实跑）：`verify_npc_appearance.py --root .` 的 `probe` 数组 **9/9 `fired=true`**（`remove_eyes_color` / `drop_hair_design_fill` / `forged_chr_99` / `mask_number_9` / `top_level_appearance_key` / `drop_referenced_ref` / `build_quadruped` / `mask_missing_while_masked` / `mask_number_string`）。
- ⇒ 新判据**整体有牙**；唯一漏项是 §2.2 的 I-10（部件顺序，已登记）与**本轮新增的 N-1 / N-2 两条纵向尺寸盲区**。

### 4.3 自证项是否与树状态解耦 —— **未解耦（M2），且耦合扩散到了新增判据**

- 实证 ①：I-8（`underneath` 下替换一个部件几何）使 **`two_reads_character_criterion_has_teeth` 与 `two_reads_share_character_parts` 同时变红**（`63/2`）。
- 实证 ②（**本轮新增**）：MATOTHER（两读法一致的材质色偏差）使 **`character_material_hex_criterion_has_teeth` 与 `character_material_hex_recomputable` 同时变红**（`63/2`）⇒ r2 新增的 F-5 自证项**继承了同一写法**（`before.problems.length === 0` 作前置）。
- 机理：自证项把「基线相等」当**前置条件**，树一脏前置先失败 ⇒ 报红的是自证项，**分不出**「自证失效」与「树红」。
- 同类耦合：`character_fingerprint_detects_size_change` 也含 `restored === before` 的树状态前置。
- 处置：已按 PM 裁决 5 / architect F-11 登记为 **R-R2（N4）** ✔ —— 但登记时只点了两条旧自证项，**未包含本轮新增的第三条** ⇒ 建议在 §25 的 R-R2 条目里补上 `character_material_hex_criterion_has_teeth`。
- 证伪方式：`bash /tmp/raven_n2g/run_injections.sh`（MATOTHER 行 `FAIL=2`）。

### 4.4 主包零改动 + 冻结锚 + 残渣

- `diff -rq <repo>/…/xingfu-xiaoqu <ws>/…/xingfu-xiaoqu` = **0 行输出**；`pack.sig` sha256 = `844f7606…cb87b` == `check_npc_admission_gate.py:42` 的常量 ✔
- `git -C <repo> status --porcelain` = **0 行**；`git rev-parse HEAD` = `18f9fac…`
- 交付面残渣：`__pycache__` / `.pytest_cache` / `dist` / `node_modules` / `*.pyc` = **0**
- **我的足迹**：`find <ws>/02_source <ws>/docs -newermt '2026-09-24 12:11:00'` = **0 个文件**；全部临时脚本与整树副本在 `/tmp/raven_n2g/**`

### 4.5 `03` / `06` 与磁盘一致性（抽读数回读盘）

| # | 文档声称（`06` R4 段 / `03` R4 段） | 我回读盘的结果 | 判定 |
|---|---|---|---|
| 1 | `verify_specs.sh` **PASS=164 FAIL=0 SKIP=0** | **164 / 0 / 0 / exit 0** | **一致** ✔ |
| 2 | `scene_assert` **PASS=65 FAIL=0**（r3 = 61） | **65 / 0 / exit 0** | **一致** ✔ |
| 3 | `verify_npc_appearance` exit 0、**9 探针全红** | exit 0、`probe_ok=true`、**9/9 fired** | **一致** ✔ |
| 4 | 冻结锚 `844f7606…cb87b` / `npc-006.json = 6e40368c…4e50d` | 实算 sha256 逐字相同 | **一致** ✔ |
| 5 | 像素 diff：室内宽 **11,186** / 近景 **81,969** / 侧向 **5,320** / 默认 **0** | 我逐像素重算全部四对：**11,186**（bbox `[530,43,657,131]`）/ **81,969**（bbox `[543,196,896,430]`）/ **5,320**（bbox `[589,138,666,213]`）/ **0**，逐项一致 | **一致（4/4 复算）** |
| 6 | 「实机取证 11 张」（`06` R4 段） | r4 批次（mtime ≥ 12:00）实得 **12 个 PNG**（10 个独立机位/态 + 2 张 `-2` 重拍） | **不一致 ⇒ L2** |
| 7 | `06` §3「`probe_ok=true`（**6/6** 负例命中）」、§5 标题「负例组（**8/8** 全部判红）」 | 工具现报 **9** 条探针（9/9 fired） | **不一致（陈旧文本）⇒ L1** |

---

## 5. 预审意见处置核验表（`<ws>/.raven_prereview-n2.md`：4 CRITICAL / 10 MEDIUM / 4 LOW）

| 编号 | 级别 | 处置核验（我在**最终树**上核的） | 判定 |
|---|---|---|---|
| R-01 | CRITICAL | `source_hex`（读法无关，进 `two_reads_share_character_parts`）与 `material_hex`（仅信息性）**已拆**；`character_material_hex_recomputable` 按 `lighting.ts` 公式**逐着色部件**复算 | **已处置**（第 1 轮残留 I-9 本轮亦闭合 ✔） |
| R-02 | CRITICAL | `mask.shape/material` 标 `design_fill` + `design_note` 写「事实册内无对应 CHR 条目」；`mask.number/number_label` 挂 CHR-16/17 + 粒度说明；GAP 上抛 | **已处置（记 GAP）**；残留：锚点引用 `ch14221` 已被 PM 更正为行号 ⇒ M7 |
| R-03 | CRITICAL | 交付树旧条文 0 命中；`06` §6-AC-8 写「**PASS（零鉴别力）**」「**不声称**本轮完成了同步」 | **已处置** ✔ |
| R-04 | CRITICAL | 注入型负例全在 `/tmp` 副本；主包零改动实证；我的足迹自证 = 0 | **已处置** ✔ |
| R-05 | MEDIUM | API 层具备（`createScene({appearance})` / `setAppearance()` 优先于 `?pack=`）；交付面**无调用者**传会话值（`main.ts` 不在写集） | **部分处置** ⇒ 已登记 **R-R3（N4）** ✔ |
| R-06 | MEDIUM | `buildEntityBoxes()` 仍每实体 1 box（`geometry_covers_every_seeded_entity` 12/12 绿）；部件只经 `characterReport()` / `character_shapes` | **已处置** ✔ |
| R-07 | MEDIUM | `03` 用**断言名集合 diff**（非条数）；`REMOVED = 0` | **已处置** ✔ |
| R-08 | MEDIUM | `source_hex` 已进两读法比较面 | **已处置** ✔ |
| R-09 | MEDIUM | 部件名来自 `CHARACTER_PART_NAMES` 固定表、`"<id>/<part>"`、无下标；根 mesh 名 = 实体 id（`06` §1.2 已登记例外） | **已处置** ✔ |
| R-10 | MEDIUM | `verify_npc_appearance.py` 只读**嵌套**字段；顶层冻结锚 sha256 `a0997e45…` 逐字节核；已接入 `verify_specs.sh` §17b（仅新增） | **已处置** ✔ |
| R-11 | MEDIUM | canonical = `02_source/art-bible.md`；两份 sha256 **相同** = `1d271e59…`（我实算） | **已处置** ✔ |
| R-12 | MEDIUM | AC-4 用**合成 state** 驱动；`03`/`06` 声明与实机（tick 120–480）的关系 | **已处置** ✔ |
| R-13 | MEDIUM | 三例（`states: []` / `schedule: null` / 无 `schedule`）**逐条断言在场**，且我注入验证**有牙**（`60/5`） | **已处置** ✔（R9 闭合） |
| R-18 | MEDIUM | `appearance_provenance_is_nested` 断言顶层旧键恰为 `appearance.red_coat`/`appearance.scarlet_eyes`；校验器禁按前缀解析顶层 | **已处置** ✔ |
| L-14 | LOW | `manifest.txt:32` 仍写「13 个文件」（实测 14）—— 按设计「记录不改」，§25 已登记 | **按设计保留** ✔ |
| L-15 | LOW | `appearance` 禁引号正文长段：契约 description + 校验器 + `scene_assert` 判据 + 我的注入探针（75 CJK 必命中） | **已处置** ✔ |
| L-16 | LOW | 面具态**两条路都在场**（`-masked-driven` 驱动 / `-masked` 等价注入），`06` §3.1 已声明用哪一种 | **已处置** ✔ |
| L-17 | LOW | 设计 §2bis 已把 F-21 标为过期读数 | **已处置** ✔ |

---

## 6. 风险清单

| 编号 | 级别 | 问题 | 触发条件 | 影响 | 证伪方式 | 建议 |
|---|---|---|---|---|---|---|
| **C1** | **CRITICAL** | **AC-9 的验收记录与 PM 裁决不一致**：`06` §3.1（第 81 行）与 §6 的 AC-9 行仍以「**部件数 + 颜色 hex**」为「可辨识」的可复核口径并标 **PASS** —— 这正是 PM 11:20 明文判为**无效证据**的形态；且 PM 要求写进 `06` **与** `06-acceptance-record.md` 的三条（① 机制子句 PASS ② 可辨识视觉子句载体移交 N4 ③ 本轮不再为可辨识开新迭代）**两处都不在场**（`06-acceptance-record.md` mtime 10:28，早于该裁决，整份没有 N2 的 AC-9 条目） | PM/评审按 `06` 的 AC 表收口 AC-9 时 | 用户本轮第一诉求（「形象符合原著」）的验收**口径**与 PM 裁决不一致：记录读起来是「AC-9 PASS」，而 PM 的定论是「机制子句 PASS / 视觉子句载体移交 N4」。**不是**「改判 GAP 掩盖没做到」，而是 PM 自己的裁决没有被落进记录 | `grep -n '机制子句\|视觉子句' <ws>/06_v0_n2_self_test.md <ws>/docs/architecture/06-acceptance-record.md`（0 命中）；`grep -n AC-9 <ws>/docs/architecture/06-acceptance-record.md`（只命中 M1 期条目）；`grep -n '可辨识' <ws>/06_v0_n2_self_test.md`（第 81/126 行） | 两处文档各补一节：AC-9 = 机制子句 **PASS**（取证机位加法 + 两态像素可区分）/ 可辨识视觉子句 **载体移交 N4（AC-5）**；并把 §3.1 与 §6 的 AC-9 行改成同一口径（保留 r3/r4 截图作为「方盒不可辨识」的对照，**不得**删） |
| **M1** | MEDIUM | **r4 是 PM 明令「不得再为可辨识开新迭代」之后的第 4 轮修复轮**：PM 11:20 更正写「本轮不得再为「可辨识」开新迭代（第 3 轮已是预算上限）」；r4 于 **11:47** 派发、目标即「让徐琴的**性别**在实机图里可读」（`.task-artisan-n2-r4.md` §0/§2），派单锁 §5.8 与任务书**均未引用任何 PM 授权** | 任何人对本轮的「谁授权了第 4 轮」提问时 | 交付内容本身更好了且**如实标注**（`03` R4-8、`06` R4 都写了「不宣称一眼可辨性别」），但过程上存在**未登记的越权迭代**；若 PM 认为停令有约束力，本轮收口缺少授权依据 | 读 `<ws>/.pm_recovery-constraint-n2.md`（11:20 段）与 `<ws>/.task-artisan-n2-r4.md`（11:47）+ `<ws>/.architect-dispatch-lock.md` §5.8；`grep -n 'PM' <ws>/.task-artisan-n2-r4.md`（无 11:20 裁决引用） | 请 PM **显式追认或推翻**：追认则在 `.architect-dispatch-lock.md` §5.8 与 `06-acceptance-record` 补一句授权来源；推翻则按 PM 的原始口径处理 r4 的几何改动 |
| **M2** | MEDIUM | **自证项与树状态耦合未闭合，且耦合扩散**：`two_reads_character_criterion_has_teeth` / `character_fingerprint_detects_size_change` 把「基线相等」当前置（已登记 R-R2）；**本轮新增**的 `character_material_hex_criterion_has_teeth` 用同一写法（`before.problems.length === 0`） | 树真的坏了时 | 分不出「自证失效」与「树红」；且 `§25` 的 R-R2 条目**未列出第三条** ⇒ 登记不完整 | `bash /tmp/raven_n2g/run_injections.sh`（MATOTHER 行 `FAIL=2`、GEOMETRY 行 `FAIL=2`） | 在 `06-acceptance-record §25` 的 R-R2 条目补上 `character_material_hex_criterion_has_teeth`；根治（N4）仍是「自证项只报注入前后是否分叉」 |
| **M3** | MEDIUM | **r4 新盲区①：`hair` 纵向长度无界**。判据只约束「下缘 ≤ 0.0」「低于肩线 ≥ 0.10 m」「上沿 ≥ 头顶」，对总长与「不得拖到地面」**无任何约束** | 任何人把 `hair.size[1]` 调大（合法调整） | 注入 `hair` 高 **2.20 m**（下缘 −1.20，垂到脚面以下）⇒ **`scene_assert 65/0` 全绿**：画面明显坏掉而零判据报警 | `python3 /tmp/raven_n2g/part_tamper.py <副本>/character.ts HAIRFLOOR && (cd <副本>/web && node scripts/scene_assert.mjs)` ⇒ `65/0` | 给 `hair` 加**上界**判据（如 `hair.bottom_y ≥ leg.bottom_y + 0.05`、或 `hair.height ≤ 1.2×torso.height`），或在 `06` 的「不覆盖」清单里明写 |
| **M4** | MEDIUM | **r4 新盲区②：`arm_*` 纵向长度零判据**。`character_silhouette_narrows_at_waist` 只约束臂的 **x** 关系（内缘缝隙 / 外缘），对臂的**高度**与「不得缩成短桩」无约束 | 任何人改 `arm.size[1]` | 注入 `arm` 高 **0.06 m** ⇒ **`65/0` 全绿**；画面里手臂变成两个小方块而判据不报警 | 同 M3，`ARMSTUB` 用例 ⇒ `65/0` | 加一条「臂长 ≥ 某个下界（如 `arm.height ≥ 0.30 × torso.height`）」的判据，或明写为不覆盖 |
| **M5** | MEDIUM | **「两条独立取数路径」的隐性假设**：`character_parts_fingerprints_recomputable` 比较的 mesh 读回侧对根部件恒报 `local_offset=[0,0,0]`，装配函数侧报 `PART_TABLE.offset` ⇒ 二者相等**仅因**交付表的 `torso.offset` 恰为 `[0,0,0]` | 任何把 `torso.offset` 设为非 0 的**合法**几何调整（例如整体抬高身体） | 断言**假红**（报「指纹不一致」，实际是两侧口径不同）⇒ 会误导下一轮修复方向；同时该断言并不能真正证明根部件 offset 一致 | `bash /tmp/raven_n2g/probe_fp.sh` ⇒ `first_diff index 9`，readback `local_offset [0,0,0]` vs assembly `[0,0.2,0]`，其余字段逐字相同 | 让两侧对根部件的 `local_offset` 采用**同一口径**（都取「相对放置点」= `[0,0,0]`，或都取 `PART_TABLE.offset`）；或在 `06` §1.1 的实现偏离清单里登记这条口径差 |
| **M6** | MEDIUM | **账本读数与真实状态不符**：`role-task` 账本（`~/.hermes/team-tasks/REQ-20260924-002-….json`）`status = done_pending_summary`、`percent = 100`、第 6 步「Sentinel+Raven 双门禁」与第 7 步「修复迭代（预留）」均已在 **01:24:18Z** 标 done（第 6 步的 note 只描述**第 1 轮**门禁） | PM 的推卡器 / 巡检器读账本时 | 本轮 r4 的**最终门禁（04/05）尚未产出**，账本却已显示 100% / 待总结 ⇒ 会把「门禁未回」误读成「已收口」 | `sed -n '1,20p' ~/.hermes/team-tasks/REQ-20260924-002-deephealing-xuqin-appearance.json`（`status`/`percent`）；`grep '"n": 6' -A5 …`（step 6 note） | 请 architect 把第 6/7 步复位为 `pending`（或补一条 note 说明「第 1 轮门禁读数，最终门禁待 04/05」），并让 `percent` 反映真实进度 |
| **M7** | MEDIUM | **已被 PM 更正的错误锚点仍留在交付面**：`npc-006.json:167` 的 `mask.shape.design_note` 写「锚点**章**见 DESIGN-20260924-001 A9（**ch14221** / ch240）」，而 PM 已自纠 `ch14221` 是**行号**、真实章节为 **ch229/ch230/ch240/ch250**（`01_architecture_design.md:338-339` 同样保留旧引用） | 有人按该引用回查原文时 | 引用指向一个不存在的「章节号」⇒ 溯源失败；方向保守（该字段本身标 `design_fill` + GAP，未冒充原著），故不是 CRITICAL | `grep -rn ch14221 <ws>/02_source <ws>/01_architecture_design.md` | 把引用改成 PM 更正后的章节（`ch229/ch230`），或改成「锚点见 DESIGN-20260924-001 A9（L0 行号 14221）」 |
| **M8** | MEDIUM | **`appearance` 自动接线的一次性缺口未登记**：`maybeAutoLoadAppearance()` 在**第一次** snapshot 就置 `appearanceAutoLoadAttempted = true`，**早于** `npcIds.length === 0` 的提前返回 ⇒ 首个 snapshot 不含 NPC 时，后续出现的 NPC 永久走通用人形兜底且**无提示** | 实机首个 snapshot 无 `kind==='npc'` 实体（时序/降级场景） | 与 R-R3 同族但更隐蔽：`source` 记 `fallback`，但**没有**任何告警路径 ⇒ 「可辨识」在真实部署下可能静默不成立 | 读 `world.ts:930-943`（`appearanceAutoLoadAttempted = true` 在 `npcIds.length === 0` 之前）；`grep -n appearanceAutoLoadAttempted <ws>/…/world.ts` | 把 `appearanceAutoLoadAttempted` 的置位移到 `npcIds.length > 0` 之后，或把「取不到 ⇒ fallback」升级为**可见**读数（`appearanceReport()` 已在，缺的是告警）；至少登记进 `§25` 遗留清单（N4） |
| **L1** | LOW | 负例条数文本陈旧：`06` §3 写「6/6 负例命中」、§5 标题写「8/8 全部判红」，工具现报 **9** 条探针；`verify_specs.sh:833` 的标签亦写「6 injected negatives fire」 | 有人按文本核对探针数 | 会把「9 条探针」误读为「6 条」⇒ 低估覆盖率 | `grep -n '6/6\|8/8' <ws>/06_v0_n2_self_test.md`；`grep -n 'injected negatives fire' <ws>/02_source/verify_specs.sh` | §25 已登记 `verify_specs` 标签漂移，建议**一并**把 `06` §3/§5 的条数改成 9（或注明「r1 时为 6/8，r2 起为 9」） |
| **L2** | LOW | 截图张数漂移：`06` R4 段写「11 张」，r4 批次实得 **12** 个 PNG（10 个独立机位/态 + 2 张 `-2` 重拍，全部 1440×900） | 有人按张数核对证据集 | 计数不一致（不影响证据有效性：重拍图是确定性自证，md5 相同） | `cd <ws>/spikes/n2-appearance/shots && find . -name '*.png' -newermt '2026-09-24 12:00' \| wc -l` ⇒ 12 | 把「11 张」改为「12 张（含 2 张确定性重拍）」 |
| **L3** | LOW | `character_gender_cues_present` 与另三条轮廓判据**共用同一组谓词函数**（`hairDrapesOutsideShoulders` / `silhouetteNarrowsAtWaist` / `legsReadBelowCoat`）⇒ 它只是一次 AND 复述，**零独立覆盖** | 有人把「新增 4 条判据」当作证据增量 | 判据条数增长 ≠ 覆盖增长（PM 裁决 3 提醒过「避免把加测试当成果」） | 读 `scene_assert.mjs:767-781`（`cues()` 直接调用那三个函数） | 保留它（作为 AC-9 性别口径的可读入口），但在 `06` 里注明「与上述三条同源，不构成独立覆盖」 |
| **L4** | LOW | `06-acceptance-record.md §24` 把 `two_reads_character_criterion_has_teeth` 列入「跨读法一致性判据」清单 —— 它是**命中能力自证**项，不证明两读法一致 | 有人据该清单理解判据族 | 分类不准（不影响 F-10 的主措辞：该节的「不是防篡改判据」表述**正确且不得弱化**） | 读 `<ws>/docs/architecture/06-acceptance-record.md:537-552` | 从该清单移除该项，或改注为「命中能力自证（不属一致性判据族）」 |
| **L5** | LOW | 判据读绿 ≠ 画面可读：我独立遮挡测试显示 `hair` 遮住 `arm_l/arm_r` 采样面的 **56%–87%**、`torso` 的 **54%–68%**（室内三机位），而 `character_silhouette_narrows_at_waist` 的 detail 文案写「臂贴住躯干侧面…⇒ 收腰」 | 有人据判据绿认为「收腰线索在画面成立」 | 性别线索的**画面**强度弱于判据文案的暗示（Artisan 已在 `03` R4-8-2 如实登记为造型取舍） | `python3 /tmp/raven_n2g/occlusion.py`（`arm_l @ obs_indoor blocked-by hair 57.4%`） | 在判据 detail 里注明「臂在画面中被发遮挡，该判据只保证几何关系」；或在 `06` 的性别线索说明里补该读数 |
| **G1** | GAP | **非实现者视觉核验（PM 硬约束 ③ 的「逐项回答看到了什么」）在交付树内未落地**：`06` R4 段的读图结论署名是**实现者**（原话「我的读数，不是独立门禁」）；r4 图的非实现者核验需由**并发的 Sentinel** 在 `04` 提供 | PM 按 PM 裁决 1 的判据形式核 AC-9 时 | 本轮 AC-9 的**视觉子句**在交付树内目前只有实现者读数 ⇒ 不构成达标证据（**不阻断**：Sentinel 门禁并发在跑，`04` 落地后即补） | `grep -n '我的读数，不是独立门禁' <ws>/06_v0_n2_self_test.md`（R4 段）；`ls -la <ws>/04_sentinel_test_report.md`（mtime 09:47 = 第 1 轮） | 等 `04` 落地后由 architect 把「非实现者逐项看到了什么」并入 `06-acceptance-record`；本报告**不引用** Sentinel 读数 |
| **G2** | GAP | **AC-10 门禁级证据为零**（沿用第 1 轮结论 + 我本轮复现）：参考图登记在**资产美学 manifest** 的 `character_refs` 块，而 `verify_asset_pack.py` 读另一种 manifest 形态 ⇒ 登记处与门禁不在同一张表；且在交付 manifest 上工具**更早**就 `KeyError: 'asset_id'` | 交付评审按 AC-10 括号里的「`verify_asset_pack.py` 通过」核 | 参考图的**许可合规**在门禁层未被证明；`runtime_usable:false` 已如实标注 | §3.2 的 KeyError 复现命令 | 保持 GAP 上抛（**不得**放宽校验器）；PM 裁决 2 已改口径并登记 ✔ |
| **G3** | GAP | **面具本体的原著 CHR 依据在事实册内不存在**（`grep -c 面具` = 0、`猪脸` = 0，我复现）⇒ `mask.shape/material` 记 `design_fill` + GAP | — | 保真缺口，已如实登记 | `grep -c 面具 <ws>/02_source/fidelity/05-character-dossiers.md` | 维持 GAP；PM 裁决 4 已并入 N4 |
| **G4** | GAP（口径） | **AC-8 零鉴别力**：交付镜像树起点即满足（旧条文 0 命中、新条文已在场）；旧条文只存活在 `<repo>/docs/**` | — | 该 AC 本轮**不能**作为「文档已同步」的证据 | `grep -rn '未使用任何原著人物姓名' <ws>/docs/ <ws>/02_source/` = 0 | 维持 `06` G4 口径（**不得**声称本轮完成同步） |

**分级统计**：CRITICAL **1**；MEDIUM **8**；LOW **5**；GAP **4**。
**未发现**（已审计且无风险的面）：既有断言被弱化/删除（0 条）、主包被改动（0 处）、冻结锚失配（无）、密钥/绝对路径进交付面（无）、`appearance` 成为逐字搬运通道（探针必命中）、pack 越界文件（无）、确定性契约被破坏（无）、`Math.random`/`Date.now` 进入装配路径（无）。

---

## 7. 有效性窗口

- 本节全部读数绑定在 **2026-09-24T04:30Z（12:30 CST）的那棵树** 上。**任何写入者落地后本报告即失效**，必须重取。
- 被审对象的 `sha256`（我实算，收尾前复取一致）：
  ```
  c8871c18f43edaaa9abc1551e589282732b7a9b28c13be7363eca60a54c30b5c  02_source/v0_skeleton/web/scripts/scene_assert.mjs
  49d9071ff2d7bccb62837b9fcac6016378033ed7ba6f84086d080a9e82479405  02_source/v0_skeleton/web/src/scene/character.ts
  19e24ec19672dc6917b09aa42df5f156811cf6378bca68e0ddc91b06da3dfa14  02_source/v0_skeleton/web/src/scene/world.ts
  d619065b2834a97fa7884e3a1bd7de356512a7af2c5f303708341172eadf04d6  02_source/v0_skeleton/tools/verify_npc_appearance.py
  8504c393ac1589da109ccb972402fdb214a3e993a6209afd6c4bc2a31fb7010f  02_source/verify_specs.sh
  6e40368c063eab410930ce9616777cd550c47cf6c870993140632245b994e50d  02_source/…/xingfu-xiaoqu-xuqin/npcs/npc-006.json
  1d271e5997ce87618322fe1b33b31481b1d91f238546f0df1786b200f3b83ab0  02_source/art-bible.md  ==  docs/specs/art-bible.md
  844f7606d5b548517a1af3a052bf882b7e38563297a644bcd70e1bd3dafcb87b  02_source/v0_skeleton/districts/xingfu-xiaoqu/pack.sig（冻结锚）
  ```
- 报告所依赖的**非写集**读数：`06_v0_n2_self_test.md`（mtime 12:09:09，42,298 B）、`03_artisan_self_test.log`（12:08:53，103,052 B）、`docs/architecture/06-acceptance-record.md`（**10:28:42**，54,055 B）、`spikes/n2-appearance/**`（最新 12:07）。其中 `06-acceptance-record.md` 的 mtime 早于 PM 11:20 裁决 ⇒ **C1 的结构性原因**。
- 仓库锚：`HEAD = 18f9facfc11281f622a6ff7be455a02d5b92ecea`，`git status --porcelain` = 空（收尾复检仍空）。
- **我的足迹自证**：`find <ws>/02_source <ws>/docs -newermt '2026-09-24 12:11:00'` = **0 个文件**；临时脚本与整树副本全部在 `/tmp/raven_n2g/**`；交付树零改动。

---

## 8. 覆盖范围声明（**不覆盖**什么）

- **不覆盖功能正确性 / 回归 / 常规静态检查**（归 Sentinel）：我没有跑内核 pytest 全量、没有做 AC-1~AC-10 的功能复现、没有做边界值测试（`height_cm` 越界 / `build` 非法值 / schema 组合爆炸）。
- **不覆盖 Sentinel 的读数**：本报告不引用 `04_sentinel_test_report.md`，与它**各自独立取数**（并发运行）。
- **不覆盖**：`spikes/**`（非交付面）的脚手架质量、Playwright/Chromium 版本行为、`vite build` 产物。
- **不覆盖**：内核侧（本轮零改动）的任何语义、记忆链、事件链。
- **不覆盖**：`refs/appearance/*.png` 源文件的**不可改写性**无法逐字节证明 —— 工作区没有第二份可比对基线，我只能给 `mtime`（08:15–08:19，早于 Artisan 开工 08:40）与「登记副本与源文件 sha256 逐字相同」两条间接证据。
- **不覆盖**：截图里人物的**主观观感**是否「好看 / 符合原著气质」—— 需要人眼；我给的只是像素 diff、几何读数与遮挡计算。
- **不覆盖**：`hair`/`arm` 纵向尺寸之外的其它「画面坏掉但判据全绿」形态（我只系统试了 12 类注入；这是一份**不穷尽**的逃逸面清单）。
- **不覆盖**：PM 11:20 裁决之后是否有我不可见的授权渠道（M1 只报告**磁盘上**可核的授权缺失）。
- **我没有**改任何代码、**没有**写修复、**没有**跑任何有副作用的写操作（除我自己的两个写集文件）。

---

## 9. 群播报稿（可直接投递；第一人称、4~8 行）

```
[REQ-20260924-002-deephealing-xuqin-appearance] N2-r4 最终门禁跑完：1 条 CRITICAL，卡在验收记录上。

我独立复跑：scene_assert 65/0、verify_specs 164/0/0、契约校验器 exit 0（9 探针全红）、
主包逐字节零改动、冻结锚一致、既有 31 条断言零删除零弱化、IP 注入探针必命中 —— 这些面我没有异议。
上一轮我提的「逐部件材质色」漏项已经补上：我改非眼睛部件的颜色，判据现在真的会红。

CRITICAL 不是代码，是记录：06 的 AC-9 行仍用「部件数 + 颜色 hex」当可辨识的口径标 PASS，
而 PM 11:20 已经明确说那不是有效证据；PM 要求写进 06 和验收记录的三条（机制子句 PASS /
可辨识交给 N4 / 不再开新迭代）两处都不在场。这条不修，AC-9 的验收口径就和 PM 裁决对不上。

另有 8 条 MEDIUM，最关键的三条：r4 新几何留下两个盲区（头发长度、手臂长度都没有上界，
我把头发拉到脚面、手臂缩成小方块，65 条判据全绿）；「两条独立取数路径」那条断言其实只靠
躯干偏移恰好为 0 才成立；账本已显示 100% 待总结，而我和 Sentinel 的门禁还没回。

建议：C1 由 architect 补两处记录（不涉代码），MEDIUM 带着交付、逐条登记 N4。不需要额外人工介入。
—— raven
```
