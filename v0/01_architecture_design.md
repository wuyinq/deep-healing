# 01 · 架构设计 — REQ-20260924-002 DeepHealing N2：徐琴人物形象落地（原著 1:1）

- 作者：architect（航行架构官）· 2026-09-24
- 输入（只读）：`pm_business/REQ-20260924-002-deephealing-xuqin-appearance.md`、`refs/DESIGN-20260924-001-xuqin-appearance.md`、
  `refs/AUDIT-20260924-001-ultimate-goal-gap-inventory.md`、`refs/appearance/*.png`（5 张，只读）
- 起点仓库：`/Users/wooyinq/personal/deep-healing` @ `develop` `18f9fac`（工作树干净，见 F-1）
- 迭代预算：`max_iteration = 3`；`pre_review_raven = true`
- 本文档为**唯一权威实现依据**；与 REQ 冲突处**不自行决断**，逐条登记 §9（上抛 PM）。

---

## 1. 目标 / 非目标 / 边界

### 1.1 目标（本轮交付）

1. 人物**不再是一律的方盒**：`kind === 'npc'` 的实体由**数据驱动的人形装配器**产出 ≥6 个可辨识部件（头 / 发 / 躯干 / 上肢 / 下肢 / 外衣）。
2. **徐琴（npc-006）符合原著锚点**：猩红瞳 / 艳红唇 / 苍白皮肤 / 艳红外衣（+ 黑长发、面具态），每条外形项**逐条挂原著依据**，设计补全项显式标 `design_fill`。
3. 外形数据**有契约、有校验器、有负例**（`npc.appearance.schema.json` + `verify_npc_appearance.py`）。
4. **两态可区分**：`日常态` / `面具态`（半张猪脸面具，面具数据含编号 `8`）。
5. 解决**硬冲突**：`art-bible.md` 的 `S ≤ 45` 不得再拒掉原著角色锚点色（角色豁免条款，环境色板**不**开天窗）。
6. 架构文档 R6 条文与「原著是核心依据」的现行口径**同步**。

### 1.2 非目标（本轮**不**宣称）

- **不**宣称「写实美术目标达成」。本轮是从「方盒」到「可辨识的程序化低模人形」的一步；无贴图、无骨骼动画、无 PBR 皮肤。
- **不**做贴图 / 骨骼 / 动画 / 体型差异系统 / 光照重做。
- **不**新增 NPC（用户明文：人物闭环跑通前不批量生成新居民）。
- **不**改内核语义、不改既有判据的期望值、不改冻结门限、不删测试、不放宽阈值。
- **不**解决「外形如何经内核 state 下发」的**契约变更**（见 §3.2，需 ADR，本轮明确排除）。

### 1.3 边界（硬）

- 写集 = REQ §2 表内文件 + **本文档 §10 显式追加的隐含写集**（须 PM 确认，见 §9-B2）。
- `git commit` / `push` / 改远端：**禁止**（落盘由 PM 执行）。
- 参考图 `refs/appearance/*.png`：**只读**，不得改写。
- 密钥 / 原始请求体 / prompt / 子代理对话原文：不得进入任何报告、日志、进度文件。

---

## 2. 起点事实表（**编号化，worker 逐条可复核**）

> 全部为 architect 在 `18f9fac` 上**实测**读数；命令与输出见 `.architect-facts-n2.md`。worker **不得**盲信本表，须按编号自跑一遍。

| # | 事实 | 实测命令（workdir） | 读数 |
|---|---|---|---|
| F-1 | 仓库起点 | `git -C <repo> rev-parse HEAD; git -C <repo> status --porcelain` | `18f9facfc11281f622a6ff7be455a02d5b92ecea`；porcelain **空**；`origin/develop` 同 SHA；0/0 |
| F-2 | 人物 = 方盒 | `web/src/scene/world.ts` `sizeFor(kind)` | `case 'npc': return [0.8, 1.7, 0.8]` —— 唯一尺寸来源，无外形字段 |
| F-3 | 几何唯一装配点 | 同上 `buildEntityBoxes()` | 每实体 **1 个** `BoxGeometry`；形状指纹 = `size` + `scale` + `quaternion` + `geometry.parameters` + `position` attribute 摘要 |
| F-4 | 内容包无外形字段 | `grep -rn 'appearance\|skin\|hair\|clothes' 02_source/v0_skeleton/districts/` | **0 命中** |
| F-5 | **state 契约封闭** | `world.schema.json` `$defs/entity` | `additionalProperties: false`，字段白名单 = `id/kind/transform/needs/emotion/schedule/relations/memory_ref/trauma_flags/tags` ⇒ **外形不能随内核 state 下发**（须契约变更才可） |
| F-6 | 渲染层**已有**读内容包人物档案的先例 | `web/src/main.ts` `npcProfileUrlFor()` | `/packs/<district_pack_id>/npcs/<npcId>.json`，只读 GET，失败退回 id（不伪造） |
| F-7 | `world.seed.json` 是**几何输入** | `web/scripts/scene_assert.mjs:151` | `const state = { entities: worldSeed.entities }` ⇒ scene_assert 的「下发 state」= 主包 seed 实体 |
| F-8 | NPC JSON 在冻结契约里**无 schema** | `kernel/deephealing_kernel/pack.py:8` | 只做 JSON 可解析性检查 ⇒ 新增 `appearance` 块**不会**被内核拒收（也不被校验） |
| F-9 | 内核只投影 NPC 两字段 | `kernel/deephealing_kernel/tick.py:121` `build_pack_profiles()` | `npc_id -> {need_weights, home_entity}` ⇒ 加 `appearance` **不影响**内核行为 / 决策 / state_hash |
| F-10 | **主包 pack.sig 被冻结锚钉死** | `check_npc_admission_gate.py:42` + `shasum -a 256 districts/xingfu-xiaoqu/pack.sig` | 锚 = `844f7606…cb87b`，与当前文件**一致**；主包 `pack.sig` 含 `npcs/npc-001..005.json` 逐文件 sha256 ⇒ **改主包 NPC 必须重签 ⇒ 锚必失配**（§9-B1） |
| F-11 | 提案包 pack.sig 可重签且不撞锚 | `manifest.txt` 末条 + `verify_specs.sh:758` | `districts/xingfu-xiaoqu-xuqin/pack.sig`（8 文件）重签后 `verify_pack.py` 仍绿；冻结锚只钉主包 |
| F-12 | `manifest.txt` 覆盖**全树** | `verify_specs.sh:267-283` | `02_source/**` 下任何**非生成**新文件若不在 `manifest.txt` ⇒ `bad "manifest.txt does not cover file"` ⇒ 新文件必须登记（§9-B2） |
| F-13 | scene_assert 被门禁按**文本**检查 | `verify_specs.sh:580-591` | 必须仍含 `createScene` / `geometryFor` / `setReading` / `assemblyReport` 各 ≥1 次 |
| F-14 | `art-bible.md` 现条文 | `02_source/art-bible.md` §1 | 「高饱和色 **禁用**（S > 45 不得出现在任何主色板）」；`aesthetic_check.py` 只校验 `assets/manifest.json` 的 `assets[].palette` |
| F-15 | R6 条文位置 | `grep -rn '未使用任何原著人物姓名' docs/` | `docs/architecture/05-risks-and-open-questions.md:18`（含「未使用任何原著人物姓名/台词/情节」）与 `docs/architecture/01-architecture-design.md:456`（「只用结构设定」） |
| F-16 | 徐琴日程使面具态**自然可达** | `districts/xingfu-xiaoqu-xuqin/schedules/weekday.json` | `target_entity = kitchen-01`（120–480、600–1080 tick）⇒ 无需注入即可进入「屠夫之家厨房」⇒ 面具态 |
| F-17 | 确定性契约面 | `web/scripts/scene_assert.mjs` | 两读法（surface/underneath）必须**逐项相同**：ids / shape_digests / mesh_positions / mesh_scales / mesh_rotations / geometry_digest / structureReport（几何 index/groups/attributes + 对象 matrixWorld/visible/layers/renderOrder + 父子关系） |
| F-18 | 无 WebGL 时装配路径不变 | `world.ts` `createRenderer()` | Node 下退化为空渲染器，**几何与场景图照常装配** ⇒ scene_assert 跑的是与浏览器同一条装配路径 |
| F-19 | 依赖位置 | `find <repo> -maxdepth 4 -name node_modules` | **不存在**；历史轮次在工作区建 `node_modules` **软链**（指向 `REQ-20260921-005-…-m3/node_modules`）⇒ 本轮沿用（§10 环境准备） |
| F-20 | 桌面端实机脚手架先例 | `REQ-20260923-002/spikes/m52-live/{serve.mjs,browser-accept.mjs}` | 真内核 + 真会话层 + `vite build` 交付面 web + Playwright 截图（1440×900 / 390×844） |

### 2bis. 事实更正（architect 自纠；**保留原句，改在明处**）

| 原编号 | 原句（**已被更正，不再作为依据**） | 更正后 | 为什么错 |
|---|---|---|---|
| F-4 | 「内容包无外形字段 ⇒ **0 命中**」 | **2 命中**：`districts/xingfu-xiaoqu-xuqin/npcs/npc-006.json:86-87` 的**顶层** `source_fact_map` 键名 `"appearance.red_coat"` / `"appearance.scarlet_eyes"`（值 `["CHR-05"]` / `["CHR-22"]`）。**仍成立的部分**：包内**没有任何外形数据字段**（这 2 条只是 provenance 键名） | 首次 grep 的 root 取窄了（`districts/` 子集），漏掉这两行 ⇒ 见 §12 R-18：这两个**旧键与新嵌套 `appearance` 同族**，是命名冲突陷阱 |
| F-15 | 「R6 旧条文位于 `docs/architecture/05-…:18` 与 `01-…:456`」 | **交付树（`{ws}/docs`）里 0 命中**：`01:456` 与 `05:18` 已是「**核心依据**（保真度方向）」新条文。旧字符串只存活在 **`<repo>/docs/**`**（仓库根 docs，**不在交付镜像树**） | 我当时的 grep 用了 `../../docs/...`（解析到仓库根），把**仓库根**读成了交付树 ⇒ 见 §12 R-03：AC-8 在交付树里**起点即满足**（零鉴别力） |
| F-21 | 「`scene_assert` 当前 exit=1 `ERR_MODULE_NOT_FOUND`」 | 软链建好后**已消除**：`exit=0`，`PASS=31 FAIL=0` | 该读数采集于 §10 环境准备**之前** ⇒ 已过期，保留作历史读数 |

- 口径：更正后的读数为准；**被更正的句子不得被任何 worker 当依据引用**（引用即缺陷）。

---

## 3. 关键决策

### D1（**核心**）外形数据通路：`内容包 → 装配配置 → 渲染`，**不经内核 state**

- 依据 F-5：内核 state 契约 `additionalProperties:false` ⇒ 外形**不可能**随 state 下发；把它塞进去属**契约变更**（本轮非目标）。
- 依据 F-6：渲染层**已有**读 `/packs/<pack>/npcs/<id>.json` 的合法先例（`loadNpcDisplayName`）⇒ 沿用同一 URL 约定，**不新增数据通道类型**。
- 决策：
  - 外形**权威来源 = 内容包 `npcs/*.json` 的 `appearance` 块**（W1b/W1c）。
  - `character.ts` 提供**纯函数**装配器 + **只读**解析器；`world.ts` 接收**已解析的装配配置**（`appearance` 表）并装配。
  - `world.ts` 的模块边界**显式改写**（原文「不得直读内容包文件」）：新边界 =「世界**状态**只消费 snapshot/delta；人物**外形**来自内容包只读 GET（装配配置），失败退回**确定性通用人形**，**不伪造**具体人物特征」。
  - 实机（浏览器）自动接线：`world.ts` 在 `apply(snapshot)` 后按实体 id **惰性**解析一次（缓存），packId 取 `location.search` 的 `?pack=`（与 `main.ts` 同一约定），缺省 `xingfu-xiaoqu`。**无需改 `main.ts`**（不在写集）。
  - 判据侧（scene_assert / spike）可**显式注入**装配配置（确定性、无网络）⇒ 判据不依赖 IO。

### D2 面具态由**下发 state 的纯谓词**驱动（不新增状态字段）

- `appearance.states[]` 每项：`{id, label, when, mask?}`；`when` 只允许读**既有 state 字段**：`schedule.target_entity` / `schedule.state` / `transform.room_id` / `tags`。
- 徐琴：`daily`（默认，无 `when`）+ `masked`（`when.target_entity_in = ["kitchen-01"]`，依据 F-16 ⇒ 实机自然可达）。
- 判定是**纯函数、确定性、无时间源**；两读法下逐项相同（读法只改光照）。

### D3 装配结构：**根 mesh 仍是躯干**，部件为其子对象（保既有判据取数路径）

- 人物实体：`THREE.Mesh`（躯干 BoxGeometry，`name = 实体 id`）作为 `root` 子节点，**其余部件挂为该 mesh 的子 mesh**（`name = "<实体 id>/<部件名>"`）。
- 为什么这样切：`assemblyReport()` / `structureReport()` / `scene_handle_structure_report_is_live` 的既有取数路径（`meshes` map → 根 mesh 的 `geometry.parameters` / `position` / `scale` / `quaternion`）**零改动**仍然成立 ⇒ 不产生「为了让新判据过而放宽旧判据」的形态（skill #24）。
- 新增 `characterReport()`（从**部件 mesh 层读回**）：逐部件 `{entity_id, part, parameters, position_attribute_digest, vertex_count, local_offset, color_hex}`，其中 `color_hex` 从 `mesh.material.color.getHexString()` **读回** ⇒ 证明「包内 hex → 渲染」这条链真的通（AC-5）。
- 部件形状指纹复用既有口径（`shapeOf` + `digestPositions`），**不新增第二套指纹算法**。

**R-06 / R-09 钉死（预审后追加，实现必须逐字遵守）**：

1. **`buildEntityBoxes()` 仍保持「每实体 1 个 box」**（人物实体的那 1 个 box = **根 mesh = 躯干**）；
   部件**只**经**新增**的 `characterReport()` 暴露。**不得**把部件塞进 `buildEntityBoxes` / `geometryReport().entity_count`
   —— 否则 `geometry_covers_every_seeded_entity`（`entity_count === worldSeed.entities.length`）必红，修它就是放宽旧判据。
2. **部件命名 = 数据驱动、禁下标**：`"<实体 id>/<部件名>"`，部件名取自 `appearance` 的固定字段名表
   （`head/hair/torso/arm_l/arm_r/leg_l/leg_r/coat/eyes/lips/mask`）。**禁止** `part-3` / 数组下标 / 遍历序号。
3. **AC-3 的读数点 = `characterReport()`**（REQ AC-3 字面说的「几何报告」在交付里注明对应读数点）。

**R-01 / R-08 钉死（颜色读数的两字段拆分）**：

- `characterReport()` 每部件给**两个**颜色字段：
  - `source_hex`：来自**装配配置**（包内 hex），**读法无关** ⇒ **进**两读法比较面（新增判据 `two_reads_share_character_parts`）；
  - `material_hex`：从 `mesh.material.color.getHexString()` **读回**，**随读法变**（`luminanceScale`）⇒ **仅信息性**，**不得**进任何相等断言。
- AC-5 的「链真的通」= **两条断言**：① `source_hex === 包内 hex`；② `material_hex === source_hex × luminanceScale(currentReading)`
  （判据**自行按 `lighting.ts` 的公式复算**，可复跑）。
- **实测依据（architect 独立复现）**：`healingMaterial('#8b1919', 主包 tone.surface)` ⇒ `material_hex = 791414`；
  `underneath` ⇒ `580c0c`。**均 ≠** `8b1919`，且**随读法变** ⇒ 「读回值直接等于包内 hex」不可达。

### D4 部件清单（≥6，数据驱动）

| 部件 | 来源 | 备注 |
|---|---|---|
| `head` | `appearance.skin.color` | 头（含面部体块） |
| `hair` | `appearance.hair.color` | 设计补全项（`design_fill: true`） |
| `torso` | `appearance.garment.color` | **根 mesh**（F-3 取数路径不变） |
| `arm_l` / `arm_r` | `appearance.garment.color`（袖） | 上肢，≥2 |
| `leg_l` / `leg_r` | `appearance.garment.color` | 下肢，≥2 |
| `coat` | `appearance.garment.color` | 外衣（长款） |
| `mask` | `appearance.mask.color` | **仅面具态存在**；数据含 `number: "8"` + `number_label: "八号"` |
| `eyes` | `appearance.eyes.color` | 猩红瞳（两个薄片或一个条带，仍为 BoxGeometry） |
| `lips` | `appearance.lips.color` | 艳红唇 |

⇒ 日常态部件数 = 10；面具态 = 11。**均 ≥ 6**（AC-3）。

### D5 颜色锚点：包内 hex 为**唯一来源**

- hex 只写在 `npcs/npc-006.json`（`eyes/lips/skin/garment/mask.color`）；TS 内**不得**出现猩红/艳红 hex 字面量（判据：`grep -nE '#(8|9|a|b|c)[0-9a-f]{5}' character.ts` 对**角色锚点色**零命中；TS 只许**中性色默认人形**色值）。
- 材质：复用既有 `healingMaterial(hex, tone)`（`lighting.ts`），**不新增材质路径、不改光照**。

### D6 契约校验器（AC-1 / AC-2）

- `npc.appearance.schema.json`（`v0/02_source/` 根，新增）：`additionalProperties:false`；每个外形字段为 `{value, source_facts?: [CHR-xx], design_fill?: true}` 形态，`source_facts` 与 `design_fill` **互斥且必居其一**。
- `verify_npc_appearance.py --root .`：① JSON Schema 合法；② 每条 `source_facts` 编号在 `fidelity/05-character-dossiers.md` 中**存在且非 `UNVERIFIED`**（复用 `check_chr_provenance.py` 口径）；③ `design_fill` 显式；④ 徐琴必填项齐全；⑤ 面具数据含 `8`。
- 负例（必判红）：删 `eyes.color` ⇒ 非 0；去掉 `hair` 的 `design_fill` ⇒ 非 0；伪造 `CHR-99` ⇒ 非 0。

### D7 art-bible 角色识别色豁免（AC-7）

- 新增条款（`docs/specs/art-bible.md` §1bis）：环境主色板**仍**受 `S ≤ 45` 约束、`aesthetic_check.py` 与 `assets/manifest.json` **一字不改**；**角色锚点色**（原著指定的瞳/唇/衣色）**豁免**，条件三条：① 必须在**内容包内**以 hex 显式声明；② 必须登记原著依据（`source_facts`）；③ 只作用于**角色部件材质**，**不得**进入 `assets/manifest.json` 的 palette。
- 负例（必判红）：把 `assets/manifest.json` 的环境主色板改成 `S > 45` ⇒ `aesthetic_check.py` 仍非 0 ⇒ 证明豁免**只**给角色锚点色。

### D8 文档同步（AC-8）

- `docs/architecture/01-architecture-design.md:456` R6 行 + `docs/architecture/05-risks-and-open-questions.md:18` R6 行：删「未使用任何原著人物姓名/台词/情节」「只用结构设定」，改为「原著人物/名称/情节/世界规则**是核心依据**；只禁**逐字搬运正文段落**（判据见 `scan_ip_boundary.py`）」。
- 判据：`grep -rn '未使用任何原著人物姓名' docs/` → **0 命中**；`grep -rn '核心依据' docs/architecture/*.md` → 命中新条文。

### D9 参考图登记（AC-10）

- 5 张 PNG **只读**位于工作区 `refs/appearance/`；登记进 **xuqin 提案包**的 `assets/manifest.json`（F-11：该包可重签且不撞冻结锚），资产实体文件落 `v0/02_source/v0_skeleton/assets-sample/character-refs/`（W4a 允许「或既有资产目录」）。
- `derived_from` 指向 `character-refs/xuqin-*`；徐琴角色参考表 **≥3 张**（art-bible §7）。
- **待 Artisan 实测核对（不得假设）**：`asset.manifest.schema.json` / `verify_asset_pack.py` 对 `derived_from` 的**解析规则**（包内 / 包外 / 相对路径）与许可字段要求。两条候选路径（① 资产放 `assets-sample/` 并登记为 sample 资产；② 复制进 pack `assets/` 并重签）由 Artisan 按 schema 实测择一，**在自测日志写明依据与读数**；若两条都被既有校验器拒 ⇒ 记录为 GAP 上抛，**不得**放宽校验器。

---

## 4. 模块拆分与写集映射

| 模块 | 文件 | REQ 编号 | 职责 |
|---|---|---|---|
| 外形契约 | `v0/02_source/npc.appearance.schema.json`（新增） | W1a | `eyes/lips/skin/hair/garment/height_cm/build/states[]`，字段级 `source_facts` / `design_fill` |
| 契约校验器 | `v0/02_source/v0_skeleton/tools/verify_npc_appearance.py`（新增） | W1d | 上 §D6 |
| 徐琴数据 | `.../districts/xingfu-xiaoqu-xuqin/npcs/npc-006.json` | W1b | `appearance` 块（原著锚点 + 设计补全逐条标注）+ `states[]` |
| 提案包签名 | `.../xingfu-xiaoqu-xuqin/pack.sig` | 隐含 | 改包内文件后**必须重签**（F-11；`manifest.txt` 明文纪律） |
| 住户数据 | `.../xingfu-xiaoqu-north/npcs/npc-001..005.json` | W1c(北区) | 基础 `appearance`（`design_fill`） |
| 北区签名 | `.../xingfu-xiaoqu-north/pack.sig` | 隐含 | 同上 |
| ~~住户数据（主包）~~ | ~~`.../xingfu-xiaoqu/npcs/npc-001..005.json`~~ | W1c(主包) | **本轮不执行**（§9-B1 硬冲突，待 PM 裁决）；改用 §D1 的**确定性通用人形**兜底 ⇒ AC-3 仍成立 |
| 人形装配器 | `.../web/src/scene/character.ts`（新增） | W2a | 纯函数 `buildCharacterParts()` + 只读 `resolveAppearanceTable()` + `characterReport()` |
| 场景装配 | `.../web/src/scene/world.ts` | W2b | `kind==='npc'` 走人形；`shapeOf`/`geometryReport`/`assemblyReport` 扩展覆盖部件；两读法逐项相同 |
| 判据 | `.../web/scripts/scene_assert.mjs` | W2c | 部件数 ≥6、指纹可复算、面具态、hex 读回、两读法仍逐项相同 |
| 美术圣经 | `docs/specs/art-bible.md` | W3a | §D7 豁免条款 |
| 架构文档 | `docs/architecture/01-architecture-design.md`、`05-risks-and-open-questions.md` | W3b | §D8 同步 |
| 资产登记 | `v0/02_source/v0_skeleton/assets-sample/character-refs/*.png` + 提案包 `assets/manifest.json` | W4a | §D9 |
| 清单 | `v0/02_source/manifest.txt` | 隐含 | F-12：新增文件必须登记（§9-B2） |

---

## 5. 接口要点

```ts
// character.ts（新增；纯函数 + 只读解析器）
export interface AppearanceField<T> { value: T; source_facts?: string[]; design_fill?: boolean }
export interface CharacterAppearance {
  eyes: { color: string }; lips: { color: string }; skin: { color: string };
  hair: { color: string; length?: string }; garment: { color: string };
  height_cm: number; build: string;
  mask?: { color: string; number: string; number_label: string };
  states: Array<{ id: string; label: string; when?: StatePredicate; mask?: boolean }>;
}
export interface StatePredicate { target_entity_in?: string[]; schedule_state_in?: string[]; room_id_in?: string[]; tags_include?: string[] }

/** 纯函数：无 IO / 无时间 / 无随机；同输入 ⇒ 同输出。 */
export function buildCharacterParts(
  appearance: CharacterAppearance | null,
  context: { entityId: string; state: { transform?: {room_id?: string|null}; schedule?: {state?: string; target_entity?: string}; tags?: string[] } },
): CharacterPart[];           // 部件含 {part, size, local_offset, color_hex, ...}

export function resolveStateId(appearance: CharacterAppearance, state: unknown): string;  // 'daily' | 'masked'
export function defaultAppearanceFor(entityId: string): CharacterAppearance;               // 确定性通用人形（design_fill）
export async function resolveAppearanceTable(input: { packId: string; npcIds: string[]; fetchImpl?: typeof fetch }): Promise<Map<string, CharacterAppearance>>;
```

```ts
// world.ts（扩展，向后兼容）
export interface EntityShape { /* 既有字段不变 */ part?: string; part_of?: string }
export interface SceneHandle {
  /* 既有方法全部保留 */
  setAppearance(table: Map<string, CharacterAppearance> | null): void;
  appearanceReport(): { entity_id: string; state_id: string; parts: CharacterPartReport[] }[];
  characterReport(): CharacterPartReport[];   // 从部件 mesh 层读回（含 color_hex）
}
export function createScene(canvas, options: { worldview: Tone; appearance?: Map<string, CharacterAppearance> }): SceneHandle;  // appearance 可选 ⇒ main.ts 不传也编译通过
```

**指纹复算口径（AC-3 的「可复算」）**：部件指纹 = `part 名 + size(6 位小数) + 装配变换(scale/quaternion) + geometry.parameters + position attribute FNV-1a64 摘要`；判据必须**从下发 state + 装配配置重算一遍**并与 `characterReport()` 的读数**逐项比对**，不得只读一次输出。

---

## 6. 风险登记（architect 自评，Raven 预审后增补）

| # | 风险 | 级别 | 处置 |
|---|---|---|---|
| R1 | **W1c 主包半 × AC-7 冻结锚硬冲突**（F-10） | **CRITICAL（需求冲突）** | **不自行决断**：本轮不执行主包半，改用通用人形兜底；逐条上抛 §9-B1 |
| R2 | 新增文件未登记 `manifest.txt` ⇒ 既有判据打红（F-12） | **CRITICAL（门禁）** | 隐含写集显式登记（§10）+ 上抛 §9-B2 |
| R3 | 改 `pack.sig` 属「生成物重签」，可能被读成越界 | MEDIUM | 依据 F-11 + `manifest.txt` 明文重签纪律；在日志写明依据 |
| R4 | 部件化后既有确定性判据被「放宽以求绿」 | **CRITICAL（判据诚信）** | §D3 结构选择使旧取数路径零改动；Sentinel 必须做**负对照**：注入读法相关差异 ⇒ 两读法判据**必须红** |
| R5 | `world.ts` 边界改写被读成「渲染层直读内容包」越界 | MEDIUM | §D1 显式改写模块 docstring 并说明理由；只读 GET、失败不伪造 |
| R6 | 依赖缺失（F-19：repo 无 `node_modules`） | MEDIUM | 沿用工作区软链（§10 环境准备）；Artisan 记录 `node -v` / `three` 版本 |
| R7 | AC-9 实机截图依赖 spike 脚手架 + 宿主静态服务 | MEDIUM | 沿用 F-20 先例；如实声明「实机接线由脚手架按包数据注入装配配置」；上抛 §9-B4 |
| R8 | 面具态判据若只测「数据里有 8」而无**命中能力**自证 | MEDIUM | 负例：把 `mask.number` 改为 `"9"` ⇒ 判据必红 |
| R9 | `verify_npc_appearance.py` 未接入 `verify_specs.sh`（写集未授权） | MEDIUM | 登记 §9-B3；本轮以自测日志 + scene_assert 承载 |
| R10 | 5 张参考图登记路径受 `verify_asset_pack.py` 约束未知（§D9） | MEDIUM | Artisan 实测择一；两条都被拒 ⇒ GAP 上抛，**不放宽校验器** |

---

## 7. 验证计划

### 7.1 Artisan 自测面（写 `03_artisan_self_test.log`）

1. **V0**：`node --test test/render-client.test.ts`（既有 4 用例）+ `node scripts/scene_assert.mjs`（**基线 31 条** + 本轮新增）+ `python3 tools/verify_npc_appearance.py --root .`。
   > 核对「既有断言未被删/弱化」**必须用断言名集合 diff，不是条数**（条数漂移会掩盖删除，见 §12 R-07）。
2. **负例组**（每条都要「退回修复前 ⇒ 必红」的读数）：AC-1（删 `eyes.color`）、AC-2（去 `design_fill` / 伪造 CHR-99）、AC-4（`mask.number` 改 `9`）、AC-7（环境色板 S>45 ⇒ `aesthetic_check.py` 非 0）、R4（读法相关注入 ⇒ 两读法判据必红）。
   > **R-04 钉死（操作纪律）**：**所有注入型负例一律在 `/tmp` 隔离副本上执行**（整树副本 + `node_modules` 软链），
   > `aesthetic_check.py` 直接指向**副本**的 manifest 路径。**禁止**就地修改主包 `districts/xingfu-xiaoqu/**`：
   > 就地改会（a）打红冻结锚 `844f7606…`（不可逆，须 PM 授权改判据期望值）、（b）使 §9-B1 的推迟策略同时失效。
3. **确定性**：`scene_assert` 两读法逐项相同；`git status --porcelain` 只含授权写集。
4. **AC-9 实机**：桌面 1440×900 + 390px 窄屏 + 面具态各 ≥1 张真实截图（`file -b` 读 PNG 头核尺寸），JS 错误计数 = 0。
   > **L-16 钉死**：提案包 seed 的 `tick = 0` 时 `npc-006.schedule.target_entity = room-1052`（`resting`）⇒ **不在面具态**。
   > 面具态截图必须**驱动 ≥120 tick**（`kitchen-01` 窗口 = 120–480 / 600–1080）或**等价地注入该 state**，并在 `03` 写明用的是哪一种。
5. **门禁读数**：`verify_specs.sh` 全文读数（**预期**：本轮新增文件若已登记 `manifest.txt`、`pack.sig` 已重签，则**仅** AC-7 冻结锚一项**预先存在的冲突**需在 §9-B1 裁决；其余不得新增 FAIL —— 若出现其它 FAIL，按 CRITICAL 处理）。
6. 逐 AC `PASS|FAIL|GAP + evidence + command + exit` 回填。

### 7.2 Sentinel 测试面（写 `04_sentinel_test_report.md`）

- 功能正确性：AC-1~AC-10 逐条**独立复现**（不复用 Artisan 读数，重跑命令）。
- 边界：缺 `appearance` 的 NPC（通用人形兜底）、`states[]` 为空、`when` 谓词无命中、`height_cm` 越界、`build` 非法值。
- 静态检查：TS 内**无**角色锚点 hex 字面量（D5）；无 `Math.random` / `Date.now` 进入装配路径（确定性）。
- **负对照（必做）**：注入「只作用于 underneath 读法」的差异 ⇒ 两读法判据**必须红**（防 R4）。
- 既有回归：`node --test`、`scene_assert`、`verify_specs.sh`、`pytest`（内核全量，含 AC-10 度量）。
- **已知负载敏感项**：`test_live_observation::test_pace_is_identical_with_zero_and_two_observers` 为**墙钟容差**判据，CPU 争用下**假红**（M5.2 实测 3 次 1 次）。若红：**如实记读数**、标注「已知假红 + 串行复跑读数」，**不得**重跑直到绿、**不得**记成全绿。

### 7.3 Raven 审计面（写 `05_raven_risk_report.md`）

- 隐性假设：外形数据通路（D1）是否会在「内核 state 封闭」下产生**静默不一致**（实机 = 脚手架注入 vs 交付路径）？
- 架构缺陷：部件化是否使**确定性契约**出现新的逃逸面（scale/rotation/父子层级/材质色）？
- 安全 / IP：`appearance` 是否可能被用来**逐字搬运正文段落**（`scan_ip_boundary.py` 两条模式）？`source_facts` 是否可能被伪造（`check_chr_provenance.py` 口径）？
- 判据诚信：**新判据是否真的能红**（逐条负例），以及**旧判据是否被放宽**（diff 审：`scene_assert.mjs` 的既有断言是否被改写/删除）。
- 分级 CRITICAL / MEDIUM / LOW + GAP。

---

## 8. 逐 AC 判据表（Artisan 必须逐条回填）

| AC | 判据命令（workdir） | 期望 | 负例（必红） |
|---|---|---|---|
| AC-1 | `python3 v0_skeleton/tools/verify_npc_appearance.py --root .`（`02_source`） | exit 0 | 删 `appearance.eyes.color` ⇒ 非 0 |
| AC-2 | 同上 + `grep` dossiers 命中 | 每条原著项挂 `source_facts` 且命中；补全项带 `design_fill` | 去掉 `hair.design_fill` ⇒ 非 0；伪造 `CHR-99` ⇒ 非 0 |
| AC-3 | `node scripts/scene_assert.mjs`（`02_source/v0_skeleton/web`）→ 全绿；读数点 = **`characterReport()`**（§12 R-06）：`npc-*` 部件数 ≥6；指纹**复算一致**（`geometryReport().shapes` 装配函数产物 vs `characterReport()` **mesh 层读回**，逐项相同） | 改任一部件 size ⇒ 指纹必变（给前后读数） |
| AC-4 | 同上 + `characterReport()`：`daily`/`masked` 两态；`masked` 含 `mask` 部件且数据含 `8`。**判据用合成 state 驱动**（含 `npc-006` + `schedule.target_entity = kitchen-01`；主包 seed 里**没有** `npc-006`，见 §12 R-12），并在报告里声明它与实机（提案包 tick∈120–480/600–1080）的关系 | `mask.number` 改 `9` ⇒ 必红 |
| AC-5 | `grep -n '"color"' .../xuqin/npcs/npc-006.json` + `characterReport()` 的 **`source_hex`**（读法无关）与 **`material_hex`**（信息性）：① `source_hex === 包内 hex`；② `material_hex === source_hex × luminanceScale(reading)`（**按 `lighting.ts` 公式复算**） | TS 里写死锚点 hex ⇒ 静态判据必红 |
| AC-6 | `node --test test/render-client.test.ts` + `node scripts/scene_assert.mjs` | 全绿、**两读法逐项相同** | 读法相关注入 ⇒ 必红 |
| AC-7 | `grep -n '角色识别色豁免' **02_source/art-bible.md**（canonical，`scene_assert` 实际读的那份）**与** `docs/specs/art-bible.md`（两份 sha256 必须相同，见 §12 R-11）；`python3 tools/aesthetic_check.py <manifest>` | 条款命中；环境色板仍 `S ≤ 45` | 环境色板 `S>45` ⇒ 非 0（**在 `/tmp` 副本上做**） |
| AC-8 | `grep -rn '未使用任何原著人物姓名' <ws>/docs/ <ws>/02_source/` = 0；`grep -rn '核心依据' <ws>/docs/architecture/*.md`。**口径（§12 R-03）**：交付树**起点即满足** ⇒ 本条**零鉴别力**，只如实记读数，**不得**声称「本轮完成了同步」；旧条文存活在 `<repo>/docs/**`（仓库根，非交付镜像）⇒ 上抛 §9-B6 | 0 命中 / 命中新条文 | — |
| AC-9 | Playwright 截图（1440×900、390px、面具态）+ JS 错误计数 | 徐琴可辨识（性别/发色/瞳色/衣着）+ 面具态可见；JS 错误 = 0 | 不注入 appearance ⇒ 通用人形（对照图） |
| AC-10 | `assets/manifest.json` 中徐琴参考表 ≥3 张 + `derived_from` 可解析 | ≥3 且可解析 | 去掉一张 ⇒ 判据必红 |

---

## 9. 上抛 PM 的事项（**不自行决断**）

### B1（CRITICAL · 需求冲突）W1c 主包半 × AC-7 冻结锚

- 事实（F-10）：`check_npc_admission_gate.py:42` 硬编码主包 `pack.sig` 的 sha256 冻结锚，且主包 `pack.sig` 含 `npcs/npc-001..005.json` 的逐文件 sha256。
- 冲突：REQ W1c 要求改主包 `npcs/npc-001..005.json`；改包内文件 ⇒ 必须重签 `pack.sig`（`manifest.txt` 明文纪律）⇒ 锚失配 ⇒ `gate_ok=false` ⇒ `verify_specs.sh` §17 打红。而 REQ §2 明文「不得改任何既有判据的期望值」。
- ⇒ **W1c 主包半与「既有判据不变红」不可兼得**。
- 本轮默认处置：**不执行主包半**；`kind==='npc'` 一律走**确定性通用人形兜底** ⇒ AC-3（≥6 部件）仍成立；住户「可辨识化」推迟。
- 请 PM 三选一：① 授权更新冻结锚（须同步登记「既有判据期望值被更新」，并重跑全门禁）；② 维持本轮默认（主包半推迟到下一轮，附「改主包 + 重签 + 更新锚」的独立任务）；③ 改 AC-7 判据口径（须 PM 签字，不属小队权限）。
- **选项④（Raven 预审提出，architect 采纳为推荐项）**：**住户外形改由 web 交付树承载** —— 新增
  `v0/02_source/v0_skeleton/web/src/scene/appearance.residents.json`（登记进 `manifest.txt`），**不碰任何 pack** ⇒
  冻结锚 / `verify_pack` / manifest 覆盖判据**全绿**，AC-3 完整达成。**代价**：与 W1c 的字面（改 `npcs/npc-00X.json`）不符，
  但满足其**意图**（住户可辨识）。**须 PM 明确「W1c = 住户外形数据落地（载体不限）」**。
  > 若 PM 选 ④，architect 另起一轮补差（不重做已完成部分）；本轮仍按默认（不执行主包半）。

### B2（写集确认）`manifest.txt` 与 `pack.sig` 的隐含写集

- 事实（F-12 / F-11）：`02_source/**` 下新增任何非生成文件若不在 `manifest.txt` ⇒ 既有判据打红；改包内文件若不重签 `pack.sig` ⇒ `verify_pack.py` 打红。
- REQ §2 未列这两个文件 ⇒ 按字面「越界即停」会**必然**打红既有门禁。
- 本轮按**隐含写集**处理（§10），请 PM 确认；若不确认，则 AC-1/AC-3/AC-10 无法在不打红既有门禁的前提下交付。

### B3（授权）新校验器是否接入 `verify_specs.sh`

- `verify_specs.sh` 不在写集，而 skill 要求「判据要接进仓库既有 verify 脚本」。本轮**不接**，以自测日志 + `scene_assert` 承载；请 PM 决定是否授权新增一条检查项（属既有脚本的**加法**，不改既有检查项语义）。

### B4（口径）AC-9 实机证据的接线方式

- 因 F-5（state 契约封闭），实机渲染的人物外形由**脚手架按包数据注入装配配置**（沿用 F-20 先例），非内核下发。
- 请 PM 确认该口径可接受；若要求「纯交付面（内核 → state → 浏览器）」链路，则需授权改 `main.ts` + **契约变更（ADR）**，超出本轮范围。

### B5（CRITICAL · 保真缺口）面具的「原著依据」在事实册里**不存在**（§12 R-02）

- 事实（architect 独立复现）：`grep -c '面具' fidelity/05-character-dossiers.md` → **0**；`grep -c '猪脸'` → **0**。
  事实册里只有 **CHR-16**（第 240 章**标题**层面「八号」并列，L1 元数据）与 **CHR-17**（八号 = 蜘蛛副人格女厨师）——**只锚「编号 8」，不锚面具的形状/材质**。
- 冲突：DESIGN-20260924-001 把「半张猪脸面具」列为 **A9 原著事实**；而 AC-2 要求每条原著项都能在事实册中**命中**。
- 本轮默认处置（**不新增写集、不伪造**）：`mask.number` / `mask.number_label` 挂 `source_facts: ["CHR-16","CHR-17"]`；
  `mask.color` 按 REQ AC-2 明文标 `design_fill`；面具**形状/材质（半张、猪脸）**标 `design_fill: true` 并加
  `design_note` 引用 DESIGN A9 的锚点章（ch14221/ch240）+ 写明「事实册内无对应 CHR 条目」⇒ 交付里如实记为 **GAP**。
- 请 PM 二选一：① 授权在 `fidelity/05-character-dossiers.md` **新增一条 CHR**（面具/半张/猪脸，锚 ch14221+ch240）并同步
  `manifest.txt` 描述与 `check_chr_provenance.py` 口径（**属新增写集**）；② 维持本轮默认（面具本体记 design_fill + GAP）。

### B6（口径）R6 旧条文只存活在**仓库根** `docs/**`，不在交付镜像树（§12 R-03）

- 事实：`<ws>/docs/**`（交付镜像）**0 命中**旧条文，`01:456` / `05:18` 已是「核心依据」新条文；旧字符串只在 `<repo>/docs/**`（1 处）。
- ⇒ AC-8 在交付树里**起点即满足**（零鉴别力），W3b 在交付树里**没有编辑对象**。
- 请 PM 决定：是否授权把**仓库根 `docs/**`** 也同步（**不在本轮写集**；且 `<repo>` 对本轮只读，须 PM 落盘时一并处理）。

### B7（授权，architect 已按技术判断执行）新校验器接入 `verify_specs.sh`

- 事实：`appearance.*.source_facts` 是**嵌套**字段，既有 `check_chr_provenance.py` 只读**顶层** `source_facts`/`source_fact_map`
  ⇒ 若不接入，AC-1/AC-2 本轮**没有任何门禁级判据**（只剩自测日志）。
- REQ §2 明文禁止的是「`verify_specs.sh` 的**既有检查项语义**」被改 ⇒ **新增**一条检查项属**加法**，不在禁令字面内。
- architect 判断：本轮**新增**一条检查项（跑 `verify_npc_appearance.py`），**逐字不动**任何既有检查项；并登记在 `03`。
  请 PM 确认；若认为越界 ⇒ 回退该项，并把 AC-1/AC-2 显式标为「本轮无门禁级判据（GAP）」。

---

## 10. 隐含写集（须 PM 确认，见 §9-B2）

```
v0/02_source/manifest.txt                                  # 新增文件登记（F-12）
v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/pack.sig   # 重签（F-11）
v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/assets/manifest.json  # W4a 改它 ⇒ 必须重签（§12 B2 补项②）
v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-north/pack.sig   # 重签（F-11）
v0/02_source/v0_skeleton/assets-sample/character-refs/*.png       # W4a 资产实体
v0/02_source/verify_specs.sh                               # **仅新增**一条检查项（§9-B7 / §12 R-10）；既有检查项逐字不动
v0/02_source/art-bible.md                                  # AC-7 的 canonical（`scene_assert` 实际读的那份，§12 R-11）
```
**镜像范围澄清（§12 R-11）**：`{ws}` **整棵**镜像 `<repo>/v0`（含 `02_source/`、`docs/`、`spikes/`、`fidelity/`、`refs/`、根级 `0*.md` 与 `V0_*.sha256`）——
`docs/**` 的改动**同样**属交付面，**不是**「只落 02_source」。
**环境准备（非交付面，落工作区）**：`{workspace}/node_modules` 软链 → `REQ-20260921-005-deephealing-v0-m3/node_modules`（F-19）；`{workspace}/02_source` 为交付镜像（收尾复制）。

**禁止**：主包 `districts/xingfu-xiaoqu/**`（B1 未决前）、`kernel/**` 语义、`tools/aesthetic_check.py`、`tools/check_npc_admission_gate.py`、`scan_ip_boundary.py` 两条模式、既有判据期望值、`main.ts`、`lighting.ts`、**既有检查项的语义（`verify_specs.sh` 只许新增、不许改既有）**。

---

## 11. 流水线执行顺序（本任务的派单锁）

1. 本文档 v1 定稿 → **Raven 方案预审**（durable 进程）→ architect 逐条处置（写入 §12）。
2. **Artisan r1**（durable 进程；W1a/W1b/W1d/W2a/W2b/W2c/W3a/W3b/W4a + 北区半 + 隐含写集）。
3. architect 读盘核验 → **fan-out 并行** Sentinel（04）+ Raven（05，对最终树）。
4. 读盘裁决 → CRITICAL 修复迭代（≤ `max_iteration`）→ 汇总 JSON 上抛。

**单写者**：一个 task 同时只有一个 writer；`{workspace}/.task-<role>.pid` 为 canonical。gateway 侧被 @ 唤醒的同角色会话**只许只读/建议，不得写任何产物**。

---

## 12. Raven 方案预审处置（**v2 修订节；与 §1~§11 冲突时以本节为准**）

- 预审对象：本文件 `sha256 8a0aec3191fbd91ba516fade6581a73fbb5a97fbdd03f3ea32452896bad8b999`（mtime 08:28:27）
- 预审报告：`<ws>/.raven_prereview-n2.md`（35,458 B；4 CRITICAL / 10 MEDIUM / 4 LOW）
- 处置原则：**每条先由 architect 独立复现**（不采信自述），再定采纳/驳回；**采纳即改写本文件相应节**。
- **独立复现结果**（architect 亲跑）：R-01 ✔ 复现、R-02 ✔、R-03 ✔、R-04 ✔（机制）、R-07 ✔、R-11 ✔、R-12 ✔、R-18 ✔（F-4 更正）；R-05/R-06/R-08/R-09/R-10/R-13/L-15/L-16 为设计缺陷，直接采纳。

### 12.1 逐条处置

| 编号 | 级别 | 判定 | 处置（落到哪一节） |
|---|---|---|---|
| **R-01** | CRITICAL | **采纳** | 材质读回值 = 包内 hex × `luminanceScale(reading)`，**随读法变**（architect 实测：`#8b1919` → surface `791414` / underneath `580c0c`）⇒ 拆 `source_hex`（读法无关，进两读法比较面）+ `material_hex`（信息性）；AC-5 = 两条断言（① 相等 ② 按 `lighting.ts` 公式复算）。落 §3-D3「R-01/R-08 钉死」+ §8-AC-5 |
| **R-02** | CRITICAL | **采纳（并上抛）** | 面具形状/材质在事实册**无 CHR 条目**（`grep -c 面具` = 0，architect 复现）⇒ `mask.number` 挂 `CHR-16/CHR-17`；`mask.color` 按 REQ 明文标 `design_fill`；形状/材质标 `design_fill` + `design_note` ⇒ 交付记 **GAP**。落 §9-**B5**（请 PM 裁决是否新增 CHR） |
| **R-03** | CRITICAL | **采纳（并上抛）** | 交付镜像树 `<ws>/docs/**` 里旧条文 **0 命中**、`01:456`/`05:18` 已是新条文；旧串只在 `<repo>/docs/**`（architect 复现）⇒ AC-8 **起点即满足（零鉴别力）**，W3b **无编辑对象**；**不得**声称本轮完成同步。落 §2bis（F-15 更正）+ §8-AC-8 + §9-**B6** |
| **R-04** | CRITICAL | **采纳** | 所有注入型负例**一律在 `/tmp` 整树副本**执行；**禁止**就地改主包（会不可逆打红冻结锚）。落 §7.1-2 钉死条 + §10 禁止清单 |
| **R-05** | MEDIUM | **采纳** | `world.ts` 的 packId **优先取会话值**（`createScene` 的 `appearance` 选项 / `setAppearance()` 由宿主传入），`?pack=` **仅兜底**；`appearanceReport()` 增加 `source: 'pack' \| 'fallback'`，判据断言徐琴的 `source === 'pack'`（否则「可辨识」可能是「通用人形可辨识」）；AC-9 证据里显式标注 packId 来源 |
| **R-06** | MEDIUM | **采纳** | `buildEntityBoxes()` **仍每实体 1 个 box**（人物 = 根 mesh = 躯干）；部件**只**经新增 `characterReport()` 暴露。落 §3-D3 钉死条 1 |
| **R-07** | MEDIUM | **采纳** | 基线 `scene_assert` **31 条**（非 27）；核对「既有断言未被删/弱化」用**断言名集合 diff**。落 §7.1-1 |
| **R-08** | MEDIUM | **采纳** | 逐部件材质是**新盲区** ⇒ 把 `source_hex`（读法无关）纳入两读法比较面（新判据 `two_reads_share_character_parts`）；`material_hex` 只作信息性。落 §3-D3 钉死条 |
| **R-09** | MEDIUM | **采纳** | 部件名 = `<实体 id>/<部件名>`，**来自数据**，**禁下标/遍历序号**。落 §3-D3 钉死条 2 |
| **R-10** | MEDIUM | **采纳（部分升级为 §9-B7）** | ① 嵌套 `appearance` 的 provenance **只读嵌套字段**；② **不得**触碰顶层 `source_facts`/`source_fact_map`（判据④会红）；③ 新校验器**接入 `verify_specs.sh`（仅新增一条检查项）**——见 §9-**B7**（architect 判读 REQ §2 只禁改既有语义，新增属加法） |
| **R-11** | MEDIUM | **采纳** | canonical = **`02_source/art-bible.md`**（`scene_assert` / `manifest.txt` / `verify_specs.sh` 实际读的那份），`docs/specs/art-bible.md` **同步**，两份 sha256 必须相同（实测起点同值 `e733dc9f…`）。落 §8-AC-7 + §10 |
| **R-12** | MEDIUM | **采纳** | AC-4 判据用**合成 state**（含 `npc-006` + `schedule.target_entity = kitchen-01`）驱动 —— 主包 seed 里**没有** `npc-006`（architect 复现 `grep -c` = 0）。落 §8-AC-4 |
| **R-13** | MEDIUM | **采纳** | `schedule.target_entity` 类型 = **`string \| null`**；`null` / 缺 `schedule` / `states: []` ⇒ **`daily`**，写成显式断言 |
| **R-18** | MEDIUM | **采纳** | 顶层 `source_fact_map` **已占用** `"appearance.red_coat"` / `"appearance.scarlet_eyes"`（architect 复现）⇒ 命名冲突陷阱：`verify_npc_appearance.py` **禁止**按 `appearance.` 前缀去解析**顶层** map（会被旧键假绿）；外观项**只**留嵌套字段。落 §3-D6 + §2bis（F-4 更正） |
| **L-14** | LOW | **记录，不改** | `manifest.txt:32` 的「13 个文件」文本漂移（实测 14）；判据不读该文本 ⇒ 不改（避免顺手改无关文本），登记 `non_block_issues` |
| **L-15** | LOW | **采纳** | `appearance` 内**不得**出现引号包起来的原著句子（需要引文一律走 `source_facts` 编号）；加注入探针证明 `scan_ip_boundary.py` 有牙 |
| **L-16** | LOW | **采纳** | 面具态截图需**驱动 ≥120 tick** 或等价注入 state。落 §7.1-4 |
| **L-17** | LOW | **采纳** | F-21 已过期 ⇒ 落 §2bis 更正 |

### 12.2 Raven 对 §9 上抛项的独立判断（architect 采纳情况）

- **B1 成立**（Raven 自跑复现）：改主包 NPC ⇒ 必须重签 ⇒ 冻结锚必失配；「往主包加文件」被 `verify_pack.py` 的 `undeclared_file` 挡住。
  **新增第三条路（Raven 提出，architect 采纳为 B1 选项④）**：住户外形改由 **web 交付树**承载
  （如 `02_source/v0_skeleton/web/src/scene/appearance.residents.json`，登记进 `manifest.txt`）⇒ 不碰任何 pack ⇒ 冻结锚/`verify_pack`/manifest 全绿。
  **代价**：与 W1c 的**字面**（改 `npcs/npc-00X.json`）不符，但满足其**意图**（住户可辨识）与 AC-3。**须 PM 明确「W1c = 住户外形数据落地（载体不限）」**。
  ⇒ 本轮**默认仍不执行**（等 PM 选），但把它作为**推荐选项**写入 §9-B1。
- **B2 成立**，Raven 补 3 项漏项 ⇒ **已全部补进 §10**。
- **B3** ⇒ 升级为 §9-**B7**（architect 判读：属加法、非改既有语义；已按此执行，请 PM 确认或回退）。
- **B4 成立**，并须连同 R-05 的 packId 口径一起写清 ⇒ 已并入 §9-B4 与 R-05 处置。

### 12.3 本节新增/改写的判据（Artisan 必做）

1. `two_reads_share_character_parts`：两读法下**逐部件** `part` / `parameters` / `position_attribute_digest` / `local_offset` / **`source_hex`** 逐项相同（`material_hex` **不进**）。
2. `character_parts_fingerprints_recomputable`：`geometryReport().shapes`（装配函数产物）与 `characterReport()`（**mesh 层读回**）逐项相同。
3. `character_appearance_source_is_pack`：徐琴的 `appearanceReport().source === 'pack'`（**不得**静默落到 `fallback`）。
4. `appearance_provenance_is_nested`：`verify_npc_appearance.py` 只读嵌套字段；**顶层** `source_facts` / `source_fact_map` **逐字节未改**（给前后 sha256 或 diff 读数）。
5. `appearance_has_no_verbatim_paragraph`：把一段正文段落注入 `appearance` 的自由文本字段 ⇒ `scan_ip_boundary.py` **必须命中**（有牙自证）。
