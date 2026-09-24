# 06 — N2 自测报告（徐琴人物形象落地：契约 / 数据 / 人形装配器 / 判据 / 美术圣经 / 参考图登记）

- 任务：`REQ-20260924-002-deephealing-xuqin-appearance`（设计 `01_architecture_design.md` v2，含 §12 Raven 预审处置）
- 执行：artisan（舰载工程官）· 2026-09-24
- 交付面：`02_source/**`（代码/数据/清单/门禁）+ `docs/specs/art-bible.md`（与 `02_source/art-bible.md` 同步）
- 实机脚手架（**非交付面**）：`spikes/n2-appearance/**`
- 权威自测日志：`03_artisan_self_test.log`（命令 + workdir + exit + 原始读数）

## 0. 边界声明（先说不做什么，防误读）

- 本轮**不**宣称「写实美术目标达成」。当前美术阶段 = **程序化低模人形**（`BoxGeometry` 部件装配，
  无贴图 / 无骨骼 / 无动画 / 无 PBR / 无体型差异系统）。相对起点（`0.8×1.7×0.8` 方盒）的进展是
  「**从方盒到可辨识的程序化低模人形**」。
- 本轮**不**解决「外形如何经内核 state 下发」的契约变更（见 §2）。
- 主包 `districts/xingfu-xiaoqu/**` **逐字节零改动**（冻结锚 `844f7606…` 未动，实测复读一致）。

## 1. 实现说明（W1a / W1b / W1c / W1d / W2a / W2b / W2c / W3a / W4a + 隐含写集）

| 项 | 文件 | 做了什么 |
|---|---|---|
| W1a | `02_source/npc.appearance.schema.json`（新增） | 外形契约：`eyes/lips/skin/hair/garment/height_cm/age_look/build/mask/states`；每字段 `{value, source_facts 或 design_fill}` **互斥且必居其一**；`additionalProperties:false` |
| W1b | `.../xingfu-xiaoqu-xuqin/npcs/npc-006.json` | 新增 `appearance` 块：原著锚点项挂 `source_facts`（CHR-05/06/16/17/22），设计补全项标 `design_fill`（hair / height_cm / age_look / build / garment.cut / mask.color / mask.shape / mask.material）；`states` = `daily` + `masked`（`target_entity_in=["kitchen-01"]`） |
| W1c | `.../xingfu-xiaoqu-north/npcs/npc-001..005.json` | 各加**基础** `appearance`（**全字段 `design_fill`**，不编造原著事实；住户通用人形） |
| W1d | `.../tools/verify_npc_appearance.py`（新增） | 10 条判据 + 6 条 /tmp 隔离负例自证（schema 真跑 jsonschema / 出处编号可解析 / 徐琴必填项 / 两态 / 嵌套出处冻结锚 / 住户 design_fill-only / 主包豁免显式 / 角色参考表登记 / 无引号正文长串） |
| W2a | `.../web/src/scene/character.ts`（新增） | **纯函数**装配器 `buildCharacterParts()` + 确定性通用人形 `defaultAppearanceFor()` + 只读解析 `resolveAppearanceTable()` / `appearanceTableFromDocuments()`；部件名来自固定字段名表（**无下标**）；本文件内**零**角色锚点 hex 字面量 |
| W2b | `.../web/src/scene/world.ts` | 模块 docstring **边界改写**（世界状态只消费 snapshot/delta；人物外形来自内容包**只读 GET**，失败退回通用人形）；`buildEntityBoxes()` 对 `kind==='npc'` 用装配器，**仍每实体 1 个 box**（人物 = 根 mesh = 躯干）；部件为子 mesh；新增 `setAppearance()` / `appearanceReport()` / `characterReport()` / `geometryReport().character_shapes`；`createScene(canvas,{worldview, appearance?})`（`appearance` 可选 ⇒ `main.ts` 不传也编译通过） |
| W2c | `.../web/scripts/scene_assert.mjs` | 新增 20 条判据（既有 31 条**逐字未动**）；新增「合成 state 驱动的两态 / 部件指纹可复算 / 两读法部件逐项相同 / 装配配置来源 = pack / 嵌套出处 / 无引号正文长串」+ 4 条命中能力自证 |
| W3a | `02_source/art-bible.md` **与** `docs/specs/art-bible.md` | 新增 §1bis「角色识别色豁免」（环境色板仍受 `S ≤ 45`；角色锚点色豁免**三条件**）。两份 **sha256 相同**（`1d271e59…`） |
| W4a | `.../xingfu-xiaoqu-xuqin/assets/character-refs/*.jpg` + `.../assets/manifest.json` | 5 张徐琴参考图登记进**提案包** manifest 的 `character_refs` 块（`sheet_min_images=3`，`consumers[].derived_from` 指向 5 张 ref） |
| 隐含 | `02_source/manifest.txt` | 新增 8 个文件逐条登记（否则既有判据 `manifest.txt does not cover file` 必红） |
| 隐含 | `.../xingfu-xiaoqu-xuqin/pack.sig`、`.../xingfu-xiaoqu-north/pack.sig` | 改包内文件后**重签**（`manifest.txt` 明文纪律）；主包 `pack.sig` **未动** |
| 隐含 | `02_source/verify_specs.sh` | **只新增 1 条**检查项（§17b 跑 `verify_npc_appearance.py`），既有检查项**逐字不动** |

### 1.1 一处**有意的实现口径偏离**（如实登记，供 Sentinel / Raven 核）

设计 §12.3-2 的字面是「`geometryReport().shapes` 与 `characterReport()` 逐项相同」。实现里
**`shapes` 保持实体级**（R-06 钉死「每实体 1 个 box」，改动它会动到既有 `shapes` / `shape_digests` /
`geometry_digest` 的语义），部件级读数放在**新增字段** `geometryReport().character_shapes`。
判据 `character_parts_fingerprints_recomputable` 比较的是 **`character_shapes`（装配函数产物）**
与 **`characterReport()`（mesh 层读回）**，逐项一致（含 `part/name/parameters/size/
position_attribute_digest/vertex_count/local_offset/source_hex`）。口径：**同一判据、改的是取数字段名**。

### 1.2 另一处如实登记：根部件的命名

R-09 要求部件名 = `"<实体 id>/<部件名>"`，R-06/D3 要求**根 mesh 的 `name` = 实体 id**（保既有取数路径）。
两者在「躯干」这一部件上冲突 ⇒ 取 R-06/D3：根 mesh `name` = `npc-006`，其 `part` 字段 = `torso`；
其余 9（+面具 = 10）个部件 mesh 名 = `npc-006/<part>`。

### 1.3 第三处如实登记：根部件的 `local_offset` **口径差**（r5 已统一，Raven M5）

`character_parts_fingerprints_recomputable` 比较的 `local_offset` 两侧口径原本**不同**：
mesh 读回侧（`characterReport()`）= `mesh.position − character_placement` ⇒ 根部件**恒** `[0,0,0]`；
装配产物侧（`geometryFor().character_shapes`）直接透传 `PART_TABLE.offset` ⇒ 两侧相等**仅因**
`torso.offset` 恰为 `[0,0,0]`。一旦有人**合法地**把 `torso.offset` 设为非 0，断言会**假红**。
**r5 处置**：在 `world.ts` 的 `character_shapes` 构造处把根部件统一为「相对放置点」= `[0,0,0]`
（与读回侧同一口径）；值**逐字节不变**（`torso.offset` 本就是 `[0,0,0]`），回退版可复现假红
（读数见 `03` r5 段与附录 R5-B3）。

## 2. 接线口径声明（**硬性**：外形不经内核 state 下发）

- 事实（F-5）：`world.schema.json` 的 `$defs/entity` 是 `additionalProperties:false`
  ⇒ 外形**不可能**随内核 state 下发；塞进去属**契约变更**（本轮非目标）。
- 因此：渲染层按 `?pack=` 对内容包做**只读 GET**（`world.ts` 的惰性接线，与 `main.ts` 的
  `loadNpcDisplayName()` **同一条 URL 约定**）取装配配置；取不到 ⇒ 确定性通用人形兜底，**不伪造**。
- **实机读数**（`spikes/n2-appearance/readback/n2-browser-accept.json`）：
  `npc-006.source === 'pack'`（不是 fallback）；对照臂 `setAppearance(null)` ⇒ 全部 `'fallback'`。
- ⇒ 读本报告时**不得**理解为「内核已下发外形」。内核侧本轮**零改动**。

## 3. 判据与读数（摘要；完整命令 + exit 见 `03`）

| 面 | 命令（workdir） | 读数 |
|---|---|---|
| AC-1/AC-2/AC-4/AC-10 契约 | `python3 v0_skeleton/tools/verify_npc_appearance.py --root .`（`02_source`） | exit **0**；10/10 判据通过；`probe_ok=true`（**9/9** 负例命中 —— r1 时 6、r2 起 9；订正见 §5 与附录 R5-B6） |
| AC-3/AC-4/AC-5/AC-6 渲染判据 | `node scripts/scene_assert.mjs`（`02_source/v0_skeleton/web`） | **PASS=51 FAIL=0**（既有 31 条 + 新增 20 条；既有断言名集合**无删除**） |
| AC-6 既有单测 | `node --test test/render-client.test.ts` | **tests 4 / pass 4 / fail 0** |
| AC-7 美术圣经 | `grep -n '角色识别色豁免' 02_source/art-bible.md docs/specs/art-bible.md`；`python3 .../aesthetic_check.py <提案包 manifest>` | 两份**均命中**、**sha256 相同**（`1d271e59…`）；`aesthetic_check: OK (3 assets)` |
| AC-8 文档 | `grep -rn '未使用任何原著人物姓名' <ws>/docs/ <ws>/02_source/` = **0**；`grep -rn '核心依据' docs/architecture/*.md` | 0 命中 / 新条文命中（**起点即满足，零鉴别力**，见 §6-G4） |
| AC-9 实机 | `spikes/n2-appearance/{browser-accept.mjs,tools-drive-mask.mjs}` | 4+1 张真实截图（`file -b` 核尺寸）；**JS 错误 = 0** |
| 全量门禁 | `bash verify_specs.sh`（`02_source`） | 见 `03` 的收尾读数（起点 `PASS=162 FAIL=0 SKIP=0`） |

### 3.1 AC-9 实机证据（`spikes/n2-appearance/shots/`）

| 图 | 尺寸（`file -b`） | 读数 |
|---|---|---|
| `n2-desktop-1440x900-daily.png` | 1440×900 | 徐琴日常态：`source='pack'`、10 部件、`eyes` source `#8b1919` / material `#751313` |
| `n2-narrow-390x844-daily.png` | 390×844 | 窄屏同读数（10 部件） |
| `n2-desktop-1440x900-masked-driven.png` | 1440×900 | **驱动 ≥120 tick**（tick 137）后 `state_id='masked'`、**11 部件（含 `mask`）**；收到的 snapshot 里 `target_entity ∈ {room-1052, kitchen-01}` |
| `n2-desktop-1440x900-masked.png` | 1440×900 | 同一两态的**等价注入**路线（另一份读数，L-16 允许的第二条路） |
| `n2-control-1440x900-generic-humanoid.png` | 1440×900 | **对照**：`setAppearance(null)` ⇒ 全部 `'fallback'`、10 部件、中性色（`#5c5548` / `#4b4239` …）。**不当达标证据** |

- **AC-9 的口径（r5 订正，按 PM 2026-09-24 11:20 裁决）**：
  - **AC-9 的机制子句 = PASS（有证据）**：外形由**外形契约驱动装配**、**部件化**（日常 **10** / 面具 **11** 部件）、
    日常态/面具态**像素可区分**（读数见上表与附录 R4 的像素 diff 表）、取证机位是**加法**且
    **默认取景逐字节未变**。
  - **AC-9 的「可辨识」视觉子句 = 载体移交 N4**：**方盒几何在任何机位都不可辨识** —— 该子句的达成载体是
    **写实人体（N4 的 AC-5）**，不是相机或部件坐标。**这不是「改判 GAP 掩盖没做到」**，而是如实划出
    本轮能力的边界、并指明下一轮承载者。
  - **部件数与颜色 hex 不构成「可辨识」的 PASS 依据**（PM 明文判为**无效证据**的形态）：hex 只证明
    「颜色锚点由数据驱动」（= AC-5），部件数只证明「不是单个方盒」（= AC-3）；二者**都不证明**
    「人能认出徐琴」。性别 / 发色 / 瞳色 / 衣着的**视觉**判定需人工看图（机器判据只给部件与颜色读数）。
  - 本轮**不再为「可辨识」开新迭代**（第 3 轮已是预算上限）。逐条落地见附录 **R5-A2**。
- **面具态用的是哪一种**（L-16 硬性）：`n2-desktop-1440x900-masked-driven.png` = **驱动 ≥120 tick**
  （实机日程把徐琴带到 `kitchen-01`，窗口 120–480）；另一张 = **等价注入该 state**。两条路都在场。

## 4. 美术圣经豁免：**没有**给环境开天窗（负例读数）

| 负例（**在 `/tmp` 整树副本上做**） | 读数 |
|---|---|
| 环境主色板 `assets[0].palette.saturation_pct` 改 **60** ⇒ `aesthetic_check.py <副本 manifest>` | **exit 1**，`E_AESTHETIC_OUT_OF_RANGE: mat-kitchen-wall: saturation 60 > 45` |
| 原样交付树 ⇒ 同一命令 | **exit 0**，`aesthetic_check: OK (3 assets)` |

⇒ 豁免**只**作用于**角色部件材质**（hex 只写在内容包 `npcs/*.json`）；`aesthetic_check.py` 与其校验对象
（`assets[].palette`）**一字未改**。

## 5. 负例组（r1 的 8 条全部判红；**工具现报 9 条探针**（r1 时 6 → r2 起 9）；完整读数见 `03`）

| # | 注入 | 必红判据 | 读数 |
|---|---|---|---|
| N-1 | 删 `appearance.eyes.color` | `schema_valid` | exit 1 |
| N-2 | 去掉 `hair.color.design_fill` | `schema_valid`（互斥/必居其一） | exit 1 |
| N-3 | 伪造 `CHR-99` | `source_facts_resolve` | exit 1 |
| N-4 | `mask.number` 改 `9` | `xuqin_required_fields` | exit 1 |
| N-5 | 往**顶层** `source_fact_map` 塞 `appearance.hair` | `appearance_provenance_is_nested` | exit 1 |
| N-6 | 环境主色板 `S=60` | `aesthetic_check.py` | exit 1 |
| N-7 | TS 里写死 `#8b1919` | 静态判据 `character_ts_has_no_anchor_hex_literal` | `hardcoded=['#8b1919']`、`pass=false` |
| N-8 | 往 `appearance` 自由文本注入引号长段（61 汉字） | `scan_ip_boundary.py`（`verbatim_body_paragraph`） | exit 1，命中 `npc-006.json:190:verbatim_body_paragraph:82` |

另有 **in-tree** 命中能力自证（`scene_assert`）：
`character_fingerprint_detects_size_change`（`height_cm` 168→188 ⇒ 指纹必变，还原回原值）、
`two_reads_character_criterion_has_teeth`（只改 underneath 一个部件的 `source_hex` ⇒ 比较面必红）、
`mask_number_criterion_has_teeth`、`appearance_has_no_verbatim_paragraph` 的合成引号段探针。

## 6. 逐 AC 结论（PASS / FAIL / GAP）

| AC | 结论 | 证据 |
|---|---|---|
| AC-1 契约存在且真校验 | **PASS** | `verify_npc_appearance.py --root .` exit 0；N-1 负例 exit 1 |
| AC-2 原著事实可核验 | **PASS** | 引用集合 `{CHR-05,06,16,17,22}` 全在事实册且非 UNVERIFIED；N-2 / N-3 必红 |
| AC-3 人物不再是方盒 | **PASS** | `character_parts_count_at_least_six`：6 个 npc 实体各 **10** 部件（面具态 11）；`character_parts_fingerprints_recomputable` 装配产物 vs mesh 读回逐项相同 |
| AC-4 两态可区分 | **PASS** | `character_states_daily_and_masked`（daily 10 / masked 11 + `mask` 部件 + `number='8'` + `number_label='八号'`）；**实机驱动 ≥120 tick 达成 masked**；N-4 必红 |
| AC-5 颜色锚点由数据驱动 | **PASS** | ① `source_hex` == 包内 hex（eyes `#8b1919` / lips `#a51c24` / garment `#8f1d1d` / skin `#dfd2c8`）；② `material_hex` == `source_hex × luminanceScale(reading)`（surface `#751313` / underneath `#570c0c`，**均 ≠ 包内 hex**）；静态判据 N-7 必红 |
| AC-6 确定性契约不破 | **PASS** | 既有 31 条断言名集合**零删除/零改写**；新增两读法部件逐项相同；`node --test` 4/4；`two_reads_character_criterion_has_teeth` 负对照必红 |
| AC-7 美术圣经改对方向 | **PASS** | 两份 art-bible 命中新条款且 sha256 相同；环境色板负例（N-6）必红 |
| AC-8 架构文档已同步 | **PASS（零鉴别力）** | 交付树 `docs/` **起点即满足**（旧条文 0 命中、新条文已在 `01:456` / `05:18`）⇒ 本轮**没有**编辑对象，**不声称**「本轮完成了同步」；旧条文只存活在 `<repo>/docs/**`（只读，见 G4） |
| AC-9 实机证据 | **机制子句 PASS /「可辨识」视觉子句载体移交 N4**（PM 11:20 裁决；逐条见附录 R5-A2） | 机制子句：外形契约驱动装配 + 部件化（日常 10 / 面具 11 部件）+ 日常态/面具态像素可区分 + 取证机位是加法且默认取景逐字节未变；视觉子句：**方盒几何在任何机位都不可辨识** ⇒ 达成载体是写实人体（N4 的 AC-5）；**不再以「部件数 + 颜色 hex」充当「可辨识」的 PASS 依据** |
| AC-10 参考图登记 | **PASS（部分口径偏离，见 G1）** | 提案包 `assets/manifest.json` 的 `character_refs`：**5 张**徐琴参考表 + `derived_from` 可解析（5/5）；`drop_referenced_ref` 负例必红 |

## 7. 遗留与 GAP（**如实**，不粉饰）

- **G1（AC-10 口径偏离 · MEDIUM）**：AC-10 括号里的「`verify_asset_pack.py` 通过」**在提案包上不可达**，
  两条**互相独立**的硬阻塞（均已实测，见 `03`）：
  1. **循环依赖**：`verify_asset_pack.py` 的 A1 要求 pack 内**每个**文件都在 manifest 里有条目 ⇒
     必须声明 `pack.sig`；而 `pack.sig` 的内容含 `assets/manifest.json` 的 sha256，manifest 又要写
     `pack.sig` 的 sha256 ⇒ **无不动点**。实测：声明签名前哈希 ⇒ `A4_CONTENT_HASH_MISMATCH`；
     声明签名后哈希 ⇒ `verify_asset_pack` exit 0 但 `verify_pack.py` 报 `hash_mismatch: assets/manifest.json`。
  2. **许可 default-deny**：5 张参考图**只有 JFIF 段、无 EXIF / 模型信息** ⇒ 无法诚实声明
     `(source_model, model_version)`，`verify_asset_pack.py` 的 A3 查表必拒。
  - 处置：**不放宽校验器**（设计 §D9 明文）。登记照做（`character_refs` + `derived_from` 可解析），
    新增的机器判据 `character_refs_registered` 覆盖「≥3 张 + derived_from 可解析」并含必红负例。
  - **需要 PM 决定**：① 在 `asset.license.table.data.json` 登记这 5 张图的产出模型 + 许可（该文件**不在**本轮写集）；
    ② 或接受「参考图仅离线设计参考、不进运行时资产链」的口径。
- **G2（面具本体 · 保真缺口 · CRITICAL 待裁决）**：事实册内**没有**面具（半张 / 猪脸）的 CHR 条目
  （`grep -c 面具` = 0）⇒ `mask.shape` / `mask.material` 标 `design_fill` + `design_note`（引用
  DESIGN A9 锚点章 ch14221 / ch240），**不冒充原著**；`mask.number` / `number_label` 挂 CHR-16 / CHR-17。
  处置同设计 §9-B5（请 PM 二选一）。
- **G3（参考图真实格式 · LOW）**：工作区 `refs/appearance/*.png` 的真实格式是 **JPEG**
  （`file -b`：JFIF baseline；`xxd` 头 `ffd8ffe0`），扩展名写作 `.png`。登记副本按**真实格式**命名 `.jpg`，
  字节与源文件**逐字相同**（未重编码、未剥离）。源文件保持只读。
- **G4（AC-8 零鉴别力 · 口径）**：交付镜像树里旧条文 0 命中、新条文已在场 ⇒ AC-8 **起点即满足**；
  旧条文存活在**仓库根** `<repo>/docs/**`（本轮只读、不得改）。请 PM 决定是否授权把仓库根 `docs/**` 一并同步。
- **G5（住户可辨识化的载体 · 待 PM 明确）**：W1c 的主包半（`districts/xingfu-xiaoqu/npcs/npc-001..005.json`）
  与冻结锚 `844f7606…` 硬冲突 ⇒ **本轮不执行**；主包 5 个住户由**确定性通用人形**兜底
  （AC-3 仍成立，实测 5 户各 10 部件）。北区 5 户已加基础 `appearance`（全 `design_fill`）。
  设计 §9-B1 的选项④（住户外形改由 web 交付树承载）**需 PM 明确**后才可落地。
- **G6（实机脚手架 quirk · LOW，非交付面）**：`spikes/n2-appearance/serve.mjs` 继承了 M5.2 脚手架的
  「事件回填」行为 —— 回填事件带当前 tick，会把渲染客户端的 `(tick, seq)` 水位推到最新，使随后的
  周期 snapshot 被挤掉（实测该轮 `snapshot_count = 0`、`entityIds()` 恒空）。本脚手架以
  `--backlog-cap 0` **关闭回填**、并把 `resume` 放到页面就绪之后 ⇒ 读数干净。**交付面未受影响**。
- **G7（未做）**：写实美术 / 贴图 / 骨骼动画 / 体型差异 / 餐刀等身份道具 / 光照重做 —— 均**未做**
  （REQ §1.2 非目标）。「面具后刻八号」只有**数据**（`mask.number='8'`），**没有**贴图级呈现。

## 8. 必答问题（REQ §6，逐条给事实）

1. **徐琴现在能不能被认出来？** 机器可复核的部分：实机读回 **10 个部件**（头 / 发 / 躯干 / 双臂 / 双腿 /
   外衣 / 双瞳 / 双唇；面具态 +面具），颜色来自包内锚点（瞳 `#8b1919`、唇 `#a51c24`、衣 `#8f1d1d`、
   肤 `#dfd2c8`、发 `#1c1a19`）。图：`spikes/n2-appearance/shots/n2-desktop-1440x900-daily.png`、
   `…-narrow-390x844-daily.png`、`…-masked-driven.png`、对照 `…-control-1440x900-generic-humanoid.png`。
   **性别 / 发色 / 瞳色 / 衣着的视觉判定需人工看图**（机器判据不给主观结论）。
2. **哪些是原著事实、哪些是设计补全？** 原著事实（挂 `source_facts`）：瞳色（CHR-22）、唇色（CHR-06）、
   肤色（CHR-06 + CHR-22）、外衣色（CHR-05）、面具编号 `8` / `八号`（CHR-16 + CHR-17）。
   设计补全（`design_fill: true`）：发色 + 发长、身高 `168`、年龄观感 `25-30`、体型 `slim`、
   外衣剪裁、**面具颜色 / 形状 / 材质**。住户（北区 5 人）**全部** `design_fill`。
3. **面具态与日常态怎么切换？** 由**下发 state 的纯谓词**驱动（不新增状态字段）：
   `appearance.states[]` 的 `masked.when.target_entity_in = ["kitchen-01"]`；`daily` 无 `when`。
   实机可达性：提案包日程 tick∈120–480 / 600–1080 把徐琴带到 `kitchen-01` ⇒ 实测 tick 137 即进入面具态。
   `target_entity` 为 `null` / 缺 `schedule` / `states: []` ⇒ 显式 `daily`（不抛异常）。
4. **确定性契约有没有被破坏？** 没有。两读法部件读数**逐项相同**（`part / name / parameters / size /
   position_attribute_digest / vertex_count / local_offset / source_hex`，`first_diff=none`）；
   既有 31 条断言**零删除、零改写**；装配路径零 `Math.random` / `Date.now`。只有**信息性**的
   `material_hex` 随读法变（`#751313` → `#570c0c`），且**不进任何相等断言**。
5. **美术圣经豁免有没有给环境开天窗？** 没有。负例：环境主色板 `S=60` ⇒ `aesthetic_check.py` **exit 1**；
   原树 **exit 0**。豁免只覆盖「包内显式声明 + 登记原著依据 + 只作用于角色部件材质」三条件。
6. **还没做到什么？** 写实美术（贴图 / PBR / 骨骼动画 / 体型差异）、身份道具（一整套餐刀）、
   面具的贴图级「八号」刻字、主包 5 个住户的原著化形象（G5）、面具本体的原著 CHR 依据（G2）、
   参考图进运行时资产链（G1）。当前美术阶段 = **程序化低模人形**。


---

# 附：N2-r2 修复轮（2026-09-24；关闭门禁第 1 轮的 1 条 CRITICAL + 8 条必修项）

> 本轮**追加**，不改上文 r1 段。命令 + workdir + exit + 原始读数见 `03_artisan_self_test.log` 的 r2 段。

## R2-1. F-1（**CRITICAL**）：徐琴在实机画面里**真的可见**

**根因（两门禁独立复现，architect 采信）**：`npc-006` 位于世界 `(5.0, 0, 15.0)` m，与 `room-1052`
（`sizeFor('room') = [5,3,5]`，AABB `x∈[2.3,7.3] y∈[−1.5,1.5] z∈[12.5,17.5]`）**同点**
⇒ 严格落在**不透明盒体内部**；默认相机 `(18,14,24) lookAt(9,0,6)` 在盒外 ⇒ 人形被完全遮挡。

**取证机位（加法、可选、spike 专用；默认行为一字不变）**

| 项 | 读数 |
|---|---|
| 新增 API | `world.ts` 的 `setObservationCamera(view \| null)`（`null` = 恢复默认取景）；`DEFAULT_CAMERA_POSITION = [18,14,24]` / `DEFAULT_CAMERA_LOOK_AT = [9,0,6]` 为**起点冻结值** |
| 徐琴实测部件 AABB | `x∈[4.635,5.365] y∈[−1.12,0.70] z∈[14.83,15.17]`（高 **1.82 m**，中心 `(5,−0.21,15)`）—— 由交付面自己的 `buildCharacterPartsForState()` 度量，**非猜测** |
| 室内取证机位（宽） | `position [5.0, 0.35, 17.4]` / `look_at [5.0, −0.2, 15.0]`；与角色中心距离 **≈ 2.465 m**；**在 `room-1052` 盒内** |
| 室内近景 | `position [5.0, 0.58, 15.95]` / `look_at [5.0, 0.45, 15.05]`；与头部中心距离 **≈ 0.954 m**；同在盒内 |
| 可见性机制 | 相机在盒**内部** ⇒ 房间内侧背面按 three 默认 `FrontSide` 自然被剔除。**未**改 `room` 的 `visible` / 材质 / 几何（**不是**「临时隐藏遮挡物后拍照」） |
| **默认取景未被改**（自证） | 改 `world.ts` **前 / 后**各跑一次 `n2-obs-camera.mjs --mode baseline` ⇒ 两份 JSON **逐字节相同**（`readback/n2-default-camera-before.json` vs `…-after.json`）；`scene_assert` 新增 `observation_camera_is_additive_and_default_framing_unchanged`（不调用它 ⇒ 机位/朝向与起点一致；调用后**真的变**；`setObservationCamera(null)` 逐项还原） |

**9 张图（`spikes/n2-appearance/shots/`，均 1440×900，`file -b` 核过）**

| 图 | 内容 |
|---|---|
| `n2-obs-indoor-daily.png` | 室内取证机位 · 日常态（世界**冻结** ⇒ 位置与面具态相同） |
| `n2-obs-indoor-masked.png` | 室内取证机位 · 面具态（**唯一变量 = `target_entity`**） |
| `n2-obs-indoor-closeup-daily.png` / `…-masked.png` | 室内近景（瞳 / 唇 / 发可判读） |
| `n2-obs-indoor-daily-2.png` | 同机位**重拍**（确定性自证） |
| `n2-obs-indoor-masked-driven.png` | 世界放行后**驱动到 tick 138** 的真实面具态（实机日程到 `kitchen-01`） |
| `n2-obs-indoor-control-generic.png` | 对照臂：`setAppearance(null)` ⇒ 通用人形（**非达标证据**） |
| `n2-default-wide-daily.png` / `…-masked.png` | **默认交付取景**（缺陷取证） |

**像素可区分读数（`n2-pixel-diff.py`，逐像素；HUD 面板区已排除）**

| 对照 | 差异像素 | 差异 bbox（视口区） |
|---|---|---|
| 室内 · 日常 vs 面具 | **16,359** | `[518, 64, 673, 170]` ← **头部/面具区**，不在 HUD 内 |
| 室内近景 · 日常 vs 面具 | **53,142** | `[402, 250, 596, 525]` ← 面部区 |
| **默认取景** · 日常 vs 面具 | **0** | `None` ⇒ **默认取景下玩家看不到人**（差异只在 HUD） |
| 室内 · 日常 vs 重拍 | **0** | `None` ⇒ 3D 视口确定性 |
| 室内 · 徐琴 vs 通用人形（对照臂） | **192,968** | `[430, 17, 777, 838]` |
| 默认取景 vs 室内机位 | **312,955** | `[35, 17, 1439, 899]` |

**主导色读数（`n2-visibility-readout.py`；渲染是平面着色 ⇒ 主导色 = 画面上真正看到的东西）**
- 日常态：`#3c0a08`/`#3d0b09`（暗红 = 外衣/四肢，83,155 px，bbox `[431,251,772,782]`）、
  `#0d0a08`（近黑 = 发，8,098 px，bbox `[520,47,666,195]`）、`#3b0a08`（瞳/唇暗红条，1,584 px，bbox `[549,95,622,120]`）
- 面具态：`#665d52`（浅色**面具板**，15,886 px，bbox `[519,65,671,169]`）；**其余部件像素数与日常态逐位相同** ⇒ 差异只在头部

**如实声明（PM 三条硬约束）**
1. 取证机位是**世界里真实存在的室内视点**（`room-1052` 体块内部），**不是**「临时隐藏遮挡物」；
   若需要隐藏 `room` 盒，规则要求同时交出「正常视角下玩家看到什么」—— 本轮**没有**隐藏任何东西，
   且默认取景图（`n2-default-wide-*.png`）**已交出**。
2. **交付面缺陷如实写明**：默认广角视角下**玩家看到的是盒子不是人**（`room=[5,3,5]` 不透明盒与 `npc-006` 同点）。
   **不得**用取证机位把它绕过去当成没发生。本轮**只登记 + 取证**（PM 已登记为 N4 的 F8）。
3. 外形数据由渲染层按 `?pack=` **只读 GET** 内容包，**非内核 state 下发**（F-5 契约封闭，与 r1 §2 同）；
   实机读数 `appearanceReport().source === 'pack'`（对照臂 `setAppearance(null)` ⇒ 全部 `'fallback'`）；JS 错误 **0**。

**像素层能认出什么（如实）**：发色（黑）、瞳色（暗红条）、唇色（暗红条）、衣着（暗红/oxblood 长外套）
**可判读**；**性别不可判**（低模人形无性别特征）；**肤色基本不可见**（`hair` 盒 0.30×0.34×0.30 完整包住
`head` 盒 0.26×0.30×0.26 ⇒ 仅底部露出一条约 0.02 m 的窄边）。面具态下 `mask` 盒（0.30×0.20，`y∈[0.41,0.61]`）
位于瞳/唇之前 ⇒ **遮住瞳唇区**，读作「一整块浅色面罩」而非「半张面具」。以上均为**低模保真缺口**，登记交 N4。

## R2-2. F-8（MEDIUM）：AC-10 阻塞理由**更正**（更靠前的那一条）

r1 的 `03` / `06` 把 AC-10 不可达记成「循环 `pack.sig` 依赖 + 许可 default-deny」——
那两条**只能**出自**自建 probe manifest**。在**交付 manifest** 上**更靠前**的阻塞是：

```bash
cd <ws>/02_source/v0_skeleton
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_asset_pack.py \
  --pack districts/xingfu-xiaoqu-xuqin \
  --manifest districts/xingfu-xiaoqu-xuqin/assets/manifest.json \
  --license-table ../asset.license.table.data.json
# exit=1；末行 KeyError: 'asset_id'（tools/verify_asset_pack.py:110）
# 根因：工具期望 assets[].asset_id，交付 manifest 用 assets[].id（实测该 manifest 的 assets[0] 键 = audio_bed,id,kind,license,palette,roughness_range,source）
```
- 复跑得**同一 KeyError**（本轮复跑两次一致）；原始输出留档 `spikes/n2-appearance/readback/n2-f8-verify_asset_pack-keyerror.txt`。
- **probe manifest 的路径与内容一并留档**：生成脚本 `spikes/n2-appearance/n2-ac10-probe.py`，
  产物 `spikes/n2-appearance/readback/n2-ac10-probe-manifest.json`（**仅**把 `assets[].id` 改名为
  `asset_id`，3 条，其余逐字不变），读数 `spikes/n2-appearance/readback/n2-ac10-probe.json`
  （越过①之后仍是结构化拒收：`A3_UNKNOWN_MODEL_DEFAULT_DENY` / `A4_BAD_CONTENT_HASH` / `A5_NOT_ADOPTED`）。
- **口径变更登记**（AC-10 改口径的原因 / 时间 / 不静默替换）：见 `docs/architecture/06-acceptance-record.md` §23。

## R2-3. F-12（LOW）：G5 段补充 —— 主包 5 户雷同读数

**G5 补充（F-12）**：主包 5 户（`districts/xingfu-xiaoqu/npcs/npc-001..005.json`）**几何完全相同** ——
`height_cm = 168`、`build = average`、同一张 `PART_TABLE`；衣色只有 **3 档**中性色（按实体 id 的确定性摘要择一）
⇒ **`npc-001 ≡ npc-004`、`npc-002 ≡ npc-005`**（像素层**视觉不可区分**），`npc-003` 为第三档。
⇒ 「主包 5 户可辨识化」不是「加个通用人形」就能达成的：需要**逐户外形数据**（与 R-B1 主包半同项），
PM 已并入 **N4**。本条只登记读数，**不**声称主包住户已可辨识。

## R2-4. 其余必修项（F-2 ~ F-7）落地读数

| # | 落地 | 关闭读数 |
|---|---|---|
| F-2 | `npc.appearance.schema.json` 新增 `$defs/buildField`（`value` = **enum** `["slim","average","stocky"]`，取自交付数据与兜底人形**实际使用**的三档） | `build="quadruped"` ⇒ 校验器 **exit 1**，`schema_valid.failures = ["…: build/value: 'quadruped' is not one of ['slim','average','stocky']"]`；`build="average"` ⇒ 仍 0 |
| F-3 | ① schema 顶层 `allOf` 的 `if/then`：`states` 含 `mask:true` ⇒ `mask` **条件必填**；② `character.ts` 新增 `resolveMaskDegradation()`，`buildCharacterParts()` / `stateIdFor()` 同走该路径 ⇒ 缺 `mask` 时**显式降级为 `daily`** + 结构化告警 `E_MASK_DATA_MISSING`（经 `appearanceReport().degradations` 暴露），**不抛异常** | 删 `mask` 而 `states` 声明 masked ⇒ 校验器 **exit 3**（`EXIT_BAD_INJECTION`）+ 结构化 JSON 含 `schema_valid.failures = ["…: <root>: 'mask' is a required property"]`；`scene_assert` **不崩**，`mask_data_missing_degrades_explicitly` PASS（生效形态 `daily` / 告警 `E_MASK_DATA_MISSING` / 部件数 10 无 mask 部件 / 还原后 `daily`） |
| F-4 | ① 注入 lambda 的 `KeyError`/`AttributeError`/`TypeError`/`IndexError` 一律转 `BadInjection` ⇒ 该 case 记 `skipped_anchor_missing`、整次运行 `EXIT_BAD_INJECTION`，**但 `evaluate()` 照跑**（结构化读数不丢）；② `appearance`/`mask`/`mask.number`/`mask.number_label` 取值加 `isinstance(dict)` 守卫 | 三处锚点缺失（`eyes.color`/`hair.color.design_fill`/`mask`）⇒ **exit 3** + 结构化 JSON（**含完整 `checks`**）；`mask.number="9"`（字符串）⇒ 结构化拒收（`appearance.mask.number(=None, expected '8')`），**无 traceback** |
| F-5 | `scene_assert` 的 `character_material_hex_recomputable` 从「只 `eyes`」扩到**逐着色部件**（10 日常 + 面具态 `mask`）；新增负对照 `character_material_hex_criterion_has_teeth` | 日常态逐部件读数：`head=#bdb2aa/#8e867f hair=#161413/#0e0c0c torso=#791717/#5a0e0e arm_l=#791717/#5a0e0e … eyes=#751313/#570c0c lips=#8c161d/#680e13`；面具态 `mask=#c6c2bb/#95928c`。注入 `arm_l` 材质色偏差（**两读法一致**）⇒ 判据 **FAIL**（`arm_l source=#8f1d1d expected=#791717/#5a0e0e actual=#000000/#000000`） |
| F-6 | `npc-006.json` 的 `mask.number` / `number_label` 补 `design_note`：「编号**值**锚 CHR-16 / CHR-17；『刻在面具上』这一**呈现方式**属设计补全」 | 字段级 `grep` 命中（`grep -c "刻在面具上" = 1`）；**未新增** CHR 引用（`source_facts_resolve.referenced` 仍为 5 个编号集合） |
| F-7 | `character_state_falls_back_to_daily_without_schedule` 扩成**三例**（各自独立断言）：`states: []` / `schedule: null` / 无 `schedule` 键 | 对照臂 `target_entity=kitchen-01 ⇒ masked`；`states: [] ⇒ daily`；**`schedule: null ⇒ daily`**；无 `schedule` 键 `⇒ daily`。四条读数均绿 |


# 附：N2-r3 小范围修复轮（2026-09-24；面部可见性 + 性别线索 + 取证图重出）

> 本轮**追加**，不改上文 r1 / r2 段。命令 + workdir + exit + 原始读数见 `03_artisan_self_test.log` 的 **R3** 段。
> 交付面改动 = **2 个文件**：`character.ts`（只改 `PART_TABLE` 的 size/offset）+ `scene_assert.mjs`（只**增** 5 条判据）。

## R3-1. 唯一修复项：面部可见 + 性别可辨 + 半张面具（R-3A / R-3B / R-3C）

**根因**（r2 的 `PART_TABLE` 读数）：`hair` 盒 x/y/z 三区间**完整包住** `head` 盒（皮肤 `#dfd2c8` 被整块遮住）；
`eyes`/`lips` 只比 `hair` 前表面凸 **5 mm** ⇒ 画面上是两条细缝；`mask` 与 `hair` 同宽 0.30 且 `y∈[0.41,0.61]`
⇒ 盖住瞳唇、读作「整块浅色面罩」。

**几何表改动（`character.ts`，逐行）**

| 部件 | r2 | r3 | 为什么 |
|---|---|---|---|
| `head` | `[0.26,0.30,0.26] @ [0,0.49,0]` | `@ [0,0.49,0.025]` | 面部前表面推到 `z=0.155` |
| `hair` | `[0.30,0.34,0.30] @ [0,0.53,-0.01]` | `[0.36,0.62,0.30] @ [0,0.37,-0.015]` | 只做顶盖+后脑+两侧（前表面退到 `z=0.135`）；下缘 `y=0.06` 过肩 |
| `coat` | `[0.56,0.86,0.34] @ [0,-0.12,0]` | `[0.56,1.12,0.34] @ [0,-0.25,-0.05]` | 下摆 `y=-0.81`（过膝）；前表面退到 `z=0.12` ⇒ 长发正面可见 |
| `eyes` / `lips` | `@ …z=0.13` | `@ …z=0.16 / 0.1575` | 前伸 **20 mm / 17.5 mm** |
| `mask` | `[0.30,0.20,0.06] @ [0,0.51,0.135]` | `[0.24,0.16,0.05] @ [0,0.565,0.17]` | 收窄 60 mm、只覆盖上半脸 |
| `torso` / `arm_*` / `leg_*` | — | **未动** | 最小改动 |

**机器判据读数（`node scripts/scene_assert.mjs`，`web`）**

| 判据 | 读数 |
|---|---|
| `character_face_visible_beyond_hair` | `head` 前表面 **z=0.155** > `hair` 前表面 **z=0.135**（露 20 mm） |
| `character_eyes_lips_protrude_from_face` | eyes **20 mm**（相对发前表面 40 mm）/ lips **17.5 mm**（37.5 mm），阈值 ≥ 15 mm |
| `character_hair_reads_long` | 发下缘 `y=0.06`，低于肩线（躯干上缘 `y=0.33`）**270 mm**；发长 0.62 m |
| `character_coat_reads_long` | 下摆 `y=-0.81` ≤ 膝线 `y=-0.72`；小腿露出 **310 mm** |
| `character_mask_reads_half_face` | 面具 `y∈[0.485,0.645]` 盖住瞳、下缘高于唇上缘；面具高 0.16 m ≤ 头高×0.7；下半脸皮肤带 **145 mm** |

**RED → GREEN**：5 条判据先在 r2 几何上**全部判红**（`exit=1 PASS=56 FAIL=5`；并用 `/tmp` 整树副本
以**最终判据代码**复证一次），改几何后 **`exit=0 PASS=61 FAIL=0`**。断言名集合 **REMOVED = 0**、ADDED = 5。

## R3-2. 实机取证（**重出**）与像素读数

| 项 | 读数 |
|---|---|
| 5 张图（+ 对照臂 / 重拍 / 驱动路线） | `spikes/n2-appearance/shots/n2-obs-indoor-{daily,masked}.png`、`…-closeup-{daily,masked}.png`、`n2-default-wide-{daily,masked}.png`（11:13~11:14 重出） |
| **像素 diff** 宽 · 日常 ↔ 面具 | **11,186 px**，bbox `[530,43,657,131]`（角色区，不在 HUD 内） |
| **像素 diff** 近景 · 日常 ↔ 面具 | **81,969 px**，bbox `[543,196,896,430]` |
| **像素 diff** 默认交付取景 · 日常 ↔ 面具 | **0**（缺陷取证：默认取景下玩家看不到人，**未**美化） |
| 同机位重拍 / 对照臂 | **0**（确定性）/ **204,891**（徐琴 vs 通用人形） |
| 投影取样（`n2-r3-face-probe.py`，逐部件正面四边形内主导像素色） | 宽 · `head` 面：皮肤 `#61554a` 64.7% + 瞳 `#3b0a08` 15.0% + 唇 `#470b0b` 8.7%；`eyes` 面 `#3b0a08` **97.4%**；`lips` 面 `#470b0b` **100%** |
| 同上 · 面具态 | 近景 `mask` 面 `#665d52` **100%**（平坦色块 80,916 px）；`head` 面 = 面具 56.5% + **下半脸皮肤 32.3%** + 唇 5.7% |
| `source='pack'` / JS 错误 | 9 张图全部 `pack`（对照臂 `fallback`）；`console_error=0 pageerror=0` |
| 视觉核验（读图） | 日常：*「平坦的浅色面部板 + **恰好两条**深红横带（上=眼、下=嘴）；近黑长发**垂到胸前**；深红外衣**下摆在膝下**、下摆以下可见两条小腿」*；面具态：*「较亮平板只盖面部**上半（约 50~60%）**，下半脸与嘴部横条仍可见」* |

**⚠️ 一处如实登记的机位偏离**：r2 的近景机位把相机轴放在 `x=5.0` 而角色在 `x=4.756` ⇒ 头部投到屏幕
`x≈388`，正落在 `rgba(255,255,255,.78)` 的**半透明 HUD 面板**后面（面部被混成 `#dcdad7` = `0.22×#61554a + 0.78×白`
⇒ 失去「可判读」）。本轮**只把近景机位横向平移到角色轴上**（`x=4.756`，距离/俯仰未动）⇒ 面部落在画面中心
`x≈720`。**宽机位一字未动**（与 r2 宽图逐像素可比）。

## R3-3. 逐关闭判据结论

| 关闭判据 | 结论 |
|---|---|
| ① 实机图看到**苍白皮肤 / 猩红瞳 / 艳红唇** | **PASS**（探针 + 读图双路径） |
| ① 几何：`head` 前表面 z > `hair` 前表面 z；`eyes`/`lips` 前伸 ≥ 15 mm | **PASS**（0.155 > 0.135；20 / 17.5 mm） |
| ② 取证图读出**长发 + 长款外衣**；**不改变**任何颜色锚点值 | **PASS**（长发低于肩线 270 mm；下摆过膝；`npc-006.json` sha256 **前后逐字节相同**） |
| ③ 面具态读出「**半张**面具 + 下半脸可见」；与日常态像素可区分 | **PASS**（面具盖上半脸、下半脸皮肤 32.3% + 唇可见；diff 11,186 / 81,969 px） |
| ③ 编号 `8` 数据层不变 / 贴图级数字 | **PASS** / **GAP**（贴图级数字**未做**，不得声称已呈现） |
| 门禁 | `scene_assert` **61/0**（REMOVED=0）；`verify_specs.sh` **164/0/0**；`render-client` **4/4**；`verify_npc_appearance` exit 0（9 探针全红）；内核全量 pytest **216 passed / exit 0**（1502.45s，串行）；`vite build` exit 0；残渣 0；repo 零改动；主包锚 `844f7606…cb87b` |

## R3-4. 遗留（**如实**，交 N4）

1. **苍白皮肤被场景光照压暗**：`+z` 是背光面 ⇒ 锚点 `#dfd2c8` 在画面上呈 `#61554a`（是**角色身上最亮的面**：
   发 `#0b0907` / 外衣 `#3c0908` / 瞳 `#3b0a08` 都更暗，但**不等于**锚点色的「苍白」观感）。根因 = 光照方向，
   改 `world.ts`/`lighting.ts` **超出本轮写集**。
2. **面具与皮肤的渲染色接近**（`#665d52` vs `#61554a`）：两个设计锚点本身就是相近浅色 ⇒ 面具主要靠**边界 +
   盖住瞳**被读出，不靠强色差。
3. **面具态下瞳色不可见**（按「覆盖上半脸」口径）；要「面具态仍可辨瞳色」需改「单侧」覆盖 ⇒ 属需求变更。
4. **性别仍只由两项轮廓线索承载**（长发 + 及膝下外衣），读图为「偏中性/弱女性化」；**不**宣称写实美术目标达成。
5. **默认交付取景下玩家仍看不到人**（`room-1052` 盒与 `npc-006` 同点）：只登记 + 取证，**未**绕过。
6. **自审不替代门禁**：本轮结论只含实现事实与自测读数；**必须**由 Sentinel（功能）+ Raven（风险）独立复跑。

---

## R4. N2-r4 最后一轮修复（2026-09-24）：性别可读（长发过肩 / 收腰 / 露腿）

> 本节**追加**，r1 / r2 / r3 段逐字未改。完整读数与命令见 `03_artisan_self_test.log` 的 R4 段。

**根因（与 r3 不同）**：r3 的 `hair` 宽 **0.36 ＜ `torso` 宽 0.46** ⇒ 头发下部**缩在肩内**（两侧各窄 50 mm）
⇒ 画面上读作「头罩 / 头盔」；`torso` 0.46 + 臂在 ±0.30（合计 **0.73** 宽）+ `coat` 0.56 ⇒ 整体读作
「方肩无性立柱」，PM 的 AC-9「能认出性别」不成立。

**交付面改动 = 2 个文件**（部件清单 / 命名 / 颜色零改动）：
- `web/src/scene/character.ts` 的 `PART_TABLE`（只改 size/offset + 该表口径注释）：
  `hair` `[0.36,0.62,0.30]@[0,0.37,-0.015]` → **`[0.58,0.72,0.30]@[0,0.34,-0.015]`**（宽 0.58 ＞ 躯干 0.38，下缘 −0.02）；
  `torso` **0.46 → 0.38**；`arm_l/r` `[0.13,0.60,0.15]@±0.30` → **`[0.10,0.40,0.14]@±0.24`**（内缘恰好贴住躯干侧面、外缘与发缘齐平）；
  `coat` **0.56 → 0.38**（与躯干同宽，下摆仍 −0.81 过膝）；`head`/`eyes`/`lips`/`mask`/`leg_l`/`leg_r` **逐字节未动**。
- `web/scripts/scene_assert.mjs` **只增 4 条判据**：`character_hair_drapes_outside_shoulders` /
  `character_silhouette_narrows_at_waist` / `character_legs_read_below_coat` / `character_gender_cues_present`
  （全部读 `characterReport()` 实测部件、每条自带负对照）。

**门禁读数（最终交付件）**

| 门禁 | 读数 |
|---|---|
| `scene_assert`（`web`） | exit 0 ⇒ **PASS=65 FAIL=0**（r3 = 61）；断言名 diff **REMOVED = 0**、ADDED = 4 |
| `verify_npc_appearance.py --root .`（`02_source`） | exit 0 ⇒ `appearance_ok=true` `probe_ok=true`（9 探针全红） |
| `node --test test/render-client.test.ts`（`web`） | exit 0 ⇒ 4 pass / 0 fail |
| `bash verify_specs.sh`（`02_source`） | exit 0 ⇒ **PASS=164 FAIL=0 SKIP=0**（与 r3 零差异） |
| `vite build` → `spikes/n2-appearance/build/web` | exit 0（`✓ built in 388ms`）；`02_source` 内残渣 **0** |
| `tsc -p --noEmit`（`web`） | exit 2、15 条 error（`main.ts`/`lighting.ts`/`world.ts`/`ui/observe/trace.ts`），**`character.ts` 0 条**（与 r3 同站点 ⇒ 既有问题） |
| repo / 冻结锚 | `git status --porcelain` = 0 行；主包 `pack.sig = 844f7606…cb87b`；`npc-006.json = 6e40368c…4e50d`（开工值） |
| 内核全量 pytest | 按任务书 §4.6 **不重跑**（只改 web 几何表） |

**实机取证（重出 + 新增 3/4 侧向机位）**：`spikes/n2-appearance/shots/**`（**12 张**（含 2 张确定性重拍），全部 `source='pack'`、
daily 10 部件 / masked 11 部件、JS 错误 0、`PNG 1440x900`）；新增机位 `INDOOR_SIDE`
`[6.9,0.35,16.8]→[4.9,−0.10,15.0]`（**仍在 `room-1052` 盒内**，偏离正面轴 ≈48°）。

| 像素 diff（HUD 区已排除） | 差异像素 | bbox |
|---|---|---|
| 室内宽 · daily ↔ masked | 11,186 | `[530,43,657,131]` |
| 室内近景 · daily ↔ masked | 81,969 | `[543,196,896,430]` |
| **室内 3/4 侧向 · daily ↔ masked** | **5,320** | `[589,138,666,213]` |
| **默认交付取景 · daily ↔ masked** | **0** | `None`（缺陷取证，未美化） |
| 同机位重拍（宽 / 侧向） | 0 / 0 | `None` |

**轮廓读数**（`n2-r4-silhouette-probe.py`，部件盒 8 角按实测相机投影）：宽图 发 295.9 px **＞** 躯干 190.3 px
（**+105.6 px**）、发 **＞** 外衣 190.5 px（**+105.4 px**）、发下缘垂过肩线 **159.8 px**、下摆以下露腿 **125.8 px**；
侧向图 发 242.4 px ＞ 躯干 174.6 px（+67.8 px）、垂过肩线 **136.0 px**、露腿 **97.1 px**。

**读图结论（我的读数，不是独立门禁）**：宽图 *「reads as a long-haired figure with narrow shoulders … rather than
as a featureless rectangular pillar」*；侧向图 *「long-haired figure with a narrow build … rather than as a pure
genderless rectangular pillar（still very abstract, blocky）」*；近景 *「pale skin visible + 两条深红横带（瞳/唇）
+ 近黑发框住面部并延伸出画面下缘」* ⇒ r3 的「squared-shouldered featureless pillar」读数**已改变**。

**未做到（如实）**：仍是程序化低模（**不**宣称写实美术目标达成、也**不**宣称一眼可辨性别）；为让「发以下立刻收窄」
成立，`arm` 由 0.60 m 缩到 0.40 m ⇒ 正面视角手臂大部分被发遮住（造型取舍）；苍白皮肤仍被光照压暗（N4）；
面具编号 `8` 仍只有数据层；默认交付取景下玩家仍看不到人（N4）；内核 pytest 读数属 r3 不属本轮。
**自审不替代门禁**：必须由 Sentinel + Raven 独立复跑。

---

# 附：N2-r5 收口轮（2026-09-24；关 2 条 CRITICAL + 低成本登记）

> 本节**追加**。任务书 = `.task-artisan-n2-r5.md`；完整命令 + workdir + exit + 原始读数见
> `03_artisan_self_test.log` 的 r5 段。
>
> **口径纪律（硬性）**：本轮**不是**「可辨识」迭代 —— PM 11:20 已裁定 AC-9 的**机制子句 = PASS**、
> 「**可辨识**」视觉子句的**载体移交 N4**；本轮**不**再为「可辨识」开新迭代。**未**改任何
> `PART_TABLE` 几何数值、**未**改任何颜色值、**未**改 `mask` 数据。

## R5-A2（**CRITICAL · Raven C1**）AC-9 验收记录与 PM 11:20 裁决**不一致** ⇒ 按裁决逐字落地

**现象**：`06` §3.1 与 §6 的 AC-9 行此前以「**部件数 + 颜色 hex**」作为「可辨识」的可复核口径并标 **PASS**
—— 这正是 PM 11:20 明文判为**无效证据**的形态；且 PM 要求写进 `06` **与**
`docs/architecture/06-acceptance-record.md` 的三条**两处都不在场**（`06-acceptance-record.md` 整份**没有** N2 的 AC-9 条目）。

**处置（PM 11:20 原文口径，逐字落地 —— 两份文件各补一节）**：
1. **AC-9 的机制子句 = PASS（有证据）**：外形**契约驱动装配**、**部件化**（日常 **10** / 面具 **11** 部件）、
   日常态/面具态**像素可区分**（室内宽 11,186 px / 近景 81,969 px / 侧向 5,320 px，见 R4 段像素表）、
   取证机位是**加法**且**默认取景逐字节未变**（同机位重拍 diff = 0，见 R4 段像素表）。
2. **AC-9 的「可辨识」视觉子句 = 载体移交 N4**：理由 —— **方盒几何在任何机位都不可辨识**；
   该子句的达成载体是**写实人体（N4 的 AC-5）**，不是相机或部件坐标。
   **这不是「改判 GAP 掩盖没做到」**，而是如实划出本轮能力的边界并指明下一轮承载者。
3. **本轮不再为「可辨识」开新迭代**（第 3 轮已是预算上限）。

**r1 段被改写的显式登记**：r2 / r3 / r4 段均声明「r1 段逐字未改」；本轮按 PM 裁决**改写**了 §3.1 的
「可辨识」口径行与 §6 的 AC-9 行（**只改这两行**）⇒ 该声明在**这两行**上**不再成立**，
显式登记以免被读成静默改写。

**保留**：**r4 截图 12 张全部保留**（`spikes/n2-appearance/shots/**`，mtime 12:03~12:04）作为「**方盒不可辨识**」的证据 ——
N4 的起点对照，**不得删**。
> **口径订正（Raven 收口 N-1，LOW）**：本节原写「r3 / r4 的截图全部保留」，与磁盘**不符** ——
> r3 期（10:30–12:00）的 PNG 已被 r4 于 12:03 **同名重拍就地覆盖**，全工作区**无** r3 期 PNG。
> r3 的**读数**仍在（`spikes/n2-appearance/readback/n2-r3-face-probe-*.json`，11:12–11:15）。
> ⇒ 准确口径 =「**r4 截图 12 张在 + r3 读数在**」；保留**目的**（方盒不可辨识的对照）**成立**。

**关闭判据读数**：
- `grep -n '机制子句\|视觉子句' <ws>/06_v0_n2_self_test.md <ws>/docs/architecture/06-acceptance-record.md`
  ⇒ **两处均命中**（读数见 `03` r5 段）；
- `grep -n AC-9 <ws>/docs/architecture/06-acceptance-record.md` ⇒ 命中 **§26 的 N2 条目**。

## R5-A1（**CRITICAL · Sentinel BUG-1**）`scene_assert.mjs` 在「声明 masked 但缺 `appearance.mask`」的包上**崩溃**

**根因**：`scene_assert.mjs` 的几何读数块（原 `:970` / `:971`，detail 模板同块）直接解引用
`maskedFace.mask.top_y`；`faceOf()` 在缺 `mask` 时返回 `mask: null` ⇒ 抛未捕获
`TypeError: Cannot read properties of null (reading 'top_y')` ⇒ **没有** `PASS=/FAIL=` 汇总行
⇒ r2 的负例 `N-3b` **不再判红**（r2 日志 `crash=False` ⇒ 属 **r3 引入的回归**）。

**RED（复现；交付树零改动，在 `/tmp/r5_neg/A1-red` 整树副本上做）**：
```
node scripts/scene_assert.mjs            # workdir = 副本/v0_skeleton/web
exit=1  crash=True  汇总行=[]（无 PASS=/FAIL=）
TypeError: Cannot read properties of null (reading 'top_y')
    at .../scripts/scene_assert.mjs:970:44
```

**修复**：加**与 `maskReadsHalfFace()` 一致的守卫** —— 前置量 `maskGeometryMissing` /
`maskGeometryAvailable`；缺 `mask`（或 `eyes`/`lips`/`head`）时把 `maskHeightM` / `lowerFaceBandMm`
降级为 `null`，detail 改走**显式 FAIL 文案**
（`MISSING_PARTS=[…]（appearance 数据缺失）⇒ 几何读数不可用（未解引用…）⇒ 判据显式判红`），
**不解引用**。既有 65 条断言**逐字未动**。

**关闭判据（缺一不可）**：
| # | 判据 | 读数 |
|---|---|---|
| 1 | 交付树 `node scripts/scene_assert.mjs` ⇒ 仍全绿、条数 ≥ 65 | exit **0** ⇒ **PASS=67 FAIL=0**（≥ 65 ✓） |
| 2 | `/tmp` 整树副本删 `npc-006` 的 `appearance.mask` ⇒ exit 非 0 **且**输出含 `PASS=… FAIL=…` 汇总行、`crash=False` | exit **1**、`scene_assert: PASS=63 FAIL=4`、`crash=False`；`character_mask_reads_half_face` **显式判红** |
| 3 | 负例组回到 **16/16 逐条判红**（`not_fired=[]`） | `all_fired=16/16  not_fired=[]`；`N-3b_mask_missing_scene_assert` ⇒ `crash=False \| scene_assert: PASS=63 FAIL=4` |

## R5-B2（Raven M3 / M4）r4 新判据的两个**无界**盲区 ⇒ 加两条纵向界判据

- `hair` **纵向长度无界**：注入 `hair.size[1]=2.20` ⇒ 原 **65/0 全绿**；
- `arm_*` **纵向长度无界**：注入 `arm.size[1]=0.06` ⇒ 原 **65/0 全绿**。

**新增两条**（**纯加法**：既有 65 条逐字未动、期望值不动；读数仍来自 `characterReport()` 实测部件）：
- `character_hair_length_bounded_by_waist`：发下缘**不得低于腰线（躯干下沿）+ 50 mm**；
- `character_arm_height_bounded_by_torso`：臂高 **≥ 躯干高 × 0.30**。

**与任务书示例的口径差异（如实登记）**：任务书示例式 `hair.bottom_y ≥ leg.bottom_y + 0.05`
**对任务书自己的注入不触发** —— 实测注入后 `hair.bottom_y = −0.76` 仍**高于** `leg_l.bottom_y = −1.12`
（差 0.31 m）⇒ 该式恒真。故 hair 侧按**更紧**的口径（腰线式）落地；任务书示例式作为**从属子句**
一并保留（被腰线式蕴含）。

**残留（如实登记，Raven 收口 LOW-1 / `03_artisan_self_test.log:1512`）**：本轮只给 `hair` / `arm_*` 加了
**纵向**（高度）界；其**横向**（宽 / 厚）**仍无独立上下界** ⇒ 把 `hair.size[0]` 或 `arm.size[2]` 调到极端值，
本轮 67 条判据**不会**全红（部分轮廓判据会红，但无专门横向界判据）。**不阻断交付**，留给 N4 与 R-R2 一并处理。

**关闭判据读数（注入前 / 后）**：
| 注入（`/tmp` 整树副本，改 `PART_TABLE`） | 交付树（注入前） | 注入后 |
|---|---|---|
| `hair.size[1] = 2.20`（下缘 y −0.02 → **−0.76**） | `PASS=67 FAIL=0` | exit **1**、`PASS=66 FAIL=1`、`FAILED (character_hair_length_bounded_by_waist)`（读数：高于腰线 **−430 mm** < 阈值 50 mm） |
| `arm.size[1] = 0.06`（臂高 0.40 → **0.06**） | `PASS=67 FAIL=0` | exit **1**、`PASS=66 FAIL=1`、`FAILED (character_arm_height_bounded_by_torso)`（读数：比 0.090909 < 0.30） |

（两条注入**各自只让对应的一条判据变红** ⇒ 判据有**鉴别力**，不是连带噪声。）

## R5-B3（Raven M5）「两条独立取数路径」的隐性假设 ⇒ 口径统一（二选一取「统一」）

见 §1.3。**修复有牙的两树差分**（同一注入：`torso.offset = [0, 0.05, 0]`）：
| 树 | 读数 |
|---|---|
| r5 修复后（交付树代码） | exit **0** ⇒ `PASS=67 FAIL=0`（**不假红**） |
| 回退到 r5 修复前（`/tmp` 副本内把 `character_shapes` 侧改回透传） | exit **1** ⇒ `FAIL character_parts_fingerprints_recomputable (assembly=60 readback=60 first_diff=#54)`（**假红**复现） |

## R5-B1（Raven M2）自证项耦合的登记不完整 ⇒ 已补

`docs/architecture/06-acceptance-record.md` §25 的 **R-R2** 条目原只列 2 条，**漏了**本轮新增的
`character_material_hex_criterion_has_teeth`（同样把「基线相等」当前置）⇒ **已补进该条目**
（**只补登记**，根治留 N4）。

## R5-B4（Raven M7）已被 PM 更正的错误锚点仍留在交付面 ⇒ 已改（`01` 不在写集）

- `npc-006.json` 的 `mask.shape.design_note`：
  `锚点章见 DESIGN-20260924-001 A9（ch14221 / ch240）` →
  **`锚点见 DESIGN-20260924-001 A9（ch229 / ch230 / ch240；此前写作 ch14221 系 L0 行号、非章节，PM 2026-09-24 自纠）`**；
- **颜色值逐字节不变**（`#8b1919` / `#a51c24` / `#dfd2c8` / `#1c1a19` / `#8f1d1d` 五行未动）；
- `pack.sig` **重签**（`v0_skeleton/tools/pack_sign.py`；diff 只有 `npcs/npc-006.json` 一条
  `sha256` / `bytes` 变化，其余 12 条 entry **逐字不变**）；
  `npc-006.json` sha256：`6e40368c…4e50d` → `168ee262…fa24f`。
- **`01_architecture_design.md` 不在本轮写集** ⇒ **设计文档侧同项由 architect 处理**（本行即登记）。

## R5-B5（Raven M8）`appearance` 自动接线的**一次性缺口** ⇒ 已修（置位移位）

`maybeAutoLoadAppearance()` 原在**第一次** snapshot 就置 `appearanceAutoLoadAttempted = true`，
**早于** `npcIds.length === 0` 的提前返回 ⇒ 首个 snapshot 不含 NPC 时，后续 NPC **永久**走通用人形兜底
且**无提示**。**处置**：把置位**移到** `npcIds.length > 0` **之后**（`world.ts`，写集内）。
**未**新增判据（本轮不加新期望值），登记于此 + `docs/architecture/06-acceptance-record.md` §26。

## R5-B6（Raven L1 / L2 / L3 / L4 + Sentinel BUG-4）文档计数与分类订正

| 项 | 订正 |
|---|---|
| §3 的「`probe_ok=true`（6/6 负例命中）」 | → **9/9**（r1 时 6、r2 起 9） |
| §5 标题「8/8 全部判红」 | → 「r1 的 8 条全部判红；**工具现报 9 条探针**（r1 时 6 → r2 起 9）」 |
| R4 段「11 张」 | → **12 张**（含 2 张确定性重拍） |
| `verify_specs.sh` 的 §17b **标签文本** | 「6 injected negatives fire」→「**9** injected negatives fire」（**纯文字**；既有检查项语义**一字未动**；紧邻注释行仍写「覆盖 6 条」—— 按任务书「**只许改这一处文字**」**未动**，登记为遗留文本漂移，判据不读该文本） |
| `character_gender_cues_present` | 与 `character_hair_drapes_outside_shoulders` / `character_silhouette_narrows_at_waist` / `character_legs_read_below_coat` **共用同一组谓词**（`cues()` 只是把三条谓词打包）⇒ **零独立覆盖**，**不构成独立覆盖**（PM 裁决 3：「避免把加测试当成果」） |
| `docs/architecture/06-acceptance-record.md` §24 的 `two_reads_character_criterion_has_teeth` | 从「跨读法一致性判据」清单**移出**，改注「**命中能力自证**（不属一致性判据族）」 |

另记（**未改，登记**）：`02_source/manifest.txt` 中 `verify_npc_appearance.py` 一行的用途文本仍写
「含 6 条 /tmp 隔离负例自证」⇒ 同属**文本漂移**；`manifest.txt` 本轮写集仅限「若新增文件」，
故**未改**（判据只按 `path | 用途 | 生成方式` 做**覆盖**断言，不读该文本）。

## R5-B7（Sentinel BUG-3 / 5 / 6 / 7）**只登记，不修**

| 编号 | 内容 | 处置 |
|---|---|---|
| **BUG-3** | 瞳色与衣着色同色不可分：眼睛簇 `#3b0a08` vs 衣着簇 `#3c0a08`，**差 1/255** ⇒ AC-9 的「瞳色」只有**弱**证据 | **不得改颜色**（颜色锚点是原著事实；拉开明度差属 N4 口径）⇒ 登记为遗留（N4） |
| **BUG-5** | 静态判据 `character_ts_has_no_anchor_hex_literal` 只扫 `character.ts`；`world.ts` **注释内**有锚点 hex | 登记为**覆盖面口径边界**（N4 可扩为「注释外零锚点 hex」） |
| **BUG-6** | `spikes/n2-appearance/readback/` 内 r2 与 r4 读数并存（文件名不含轮次） | 已在 `spikes/n2-appearance/notes/README.md` 补「**按 mtime 分轮，跨轮读数不可混用**」 |
| **BUG-7** | `spikes/n2-appearance/n2-ac10-probe.py` 在 `--out` 指向工作区外时崩（`relative_to`） | 登记即可（**非交付面**） |

## R5-B8（Raven M1）r4 的**授权来源** —— 按 PM 12:40 裁决 **6-A 追认**

> **本节已订正**：原为「r4 是 PM 明令停令之后的一轮（越权 / 待 PM 追认）」的旧措辞，
> 该措辞已被 **PM 12:40 裁决 6-A 明令作废**（6-A：**不许**把 r4 写成「无授权」或「PM 未授权」）。
> 订正执行者 = **architect 派单归属进程**（2026-09-24 13:0x CST）；依据 `docs/architecture/06-acceptance-record.md` §26.2 同步。

**授权来源（PM 6-A 原文口径）**：**PM 12:40 裁决 6-A 追认 r4；PM 承担中途收窄未给中止指令的责任。**

**事实链（保留，供追溯）**：
- PM **10:20** 重启架构官时的授权原文 =「执行你裁决书 §3.1 的 **F-1 ~ F-12** 修复（写集照 §4）」；
  而 **F-1 的字面即「让徐琴在实机画面里真的可见（能看出性别/发色/瞳色/衣着）」** ⇒ r4 的**主体在授权内**；
- PM **11:20** 中途收窄为「不得再为『可辨识』开新迭代」，但**未**下「中止 F-1 子项」的明确指令；
- architect 的流程缺口（r4 派发前未重读 PM 更新过的裁决文件）**已如实登记**，并**按 6-A 的定性记录**。

**硬性确认（PM 6-A）**：**r4 是最后一轮**；此后不再为「可辨识」开任何迭代；
AC-9 的「可辨识」视觉子句按 11:20 裁决**载体移交 N4（AC-5）**。

## R5 门禁读数（最终交付件）

| 门禁 | 命令（workdir） | 读数 |
|---|---|---|
| AC-1/2/4/10 契约 | `python3 v0_skeleton/tools/verify_npc_appearance.py --root .`（`02_source`） | exit **0**；`appearance_ok=true` `probe_ok=true`（**9** 探针全红） |
| AC-3/4/5/6 渲染判据 | `node scripts/scene_assert.mjs`（`web`） | exit **0** ⇒ **PASS=67 FAIL=0**（r4 = 65 ⇒ **只增 2**）；断言名 **REMOVED = 0**、**ADDED = 2** |
| AC-6 既有单测 | `node --test test/render-client.test.ts`（`web`） | exit **0** ⇒ tests 4 / pass 4 / fail 0 |
| 全量门禁 | `bash verify_specs.sh`（`02_source`） | exit **0** ⇒ **PASS=164 FAIL=0 SKIP=0**（与 r4 零差异；唯一文本变化 = §17b 标签 6→9，**逐条归因**） |
| 负例组 | `python3 /tmp/n2_sentinel/n2-negatives-r2.py` | **16/16 逐条判红**（`not_fired=[]`；`N-3b` 回到 `crash=False`） |
| 交付树零改动（负例/注入期间） | `find 02_source -type f \| sort \| xargs shasum -a 256` 前后各一次 | **BYTE-IDENTICAL**（208 个文件） |
| 残渣 | `find 02_source -name __pycache__ -o -name .pytest_cache -o -name dist` | **0** |
| repo / 冻结锚 | `git -C <repo> status --porcelain` / `shasum -a 256 …/xingfu-xiaoqu/pack.sig` | **0** 行 / **844f7606…cb87b**（== 冻结锚，**未动**） |
| 内核 pytest | 本轮不碰内核面 | 按任务书 §5.7 **不重跑** |

## R5 诚实边界（**不得在总结里弱化**）

- 本轮**不**改人物外观：`PART_TABLE` 几何数值 **0 处**改动、颜色值 **0 处**改动、`mask` 数据 **0 处**改动；
- 本轮**不**宣称「可辨识」提升 —— AC-9 的「可辨识」按 PM 裁决**载体移交 N4**（本轮**不**为它开新迭代）；
- 本轮新增的 2 条判据只**收紧**既有盲区（无界长度），**不**新增任何以「更可辨识」为目标的判据；
- `01_architecture_design.md` 侧的同项（R5-B4）**由 architect 处理**，本轮**未**碰（不在写集）；
- 自审**不**替代门禁：本轮结论仍需 Sentinel + Raven 独立复跑。


