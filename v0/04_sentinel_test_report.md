model: deepseek-v4.1-flash | 来源: sentinel 派单进程 pid 89428（`.task-sentinel.pid`；`hermes -p sentinel chat --query-file .task-sentinel-n2-gate.pointer.txt --oneshot --run-budget 7200`） | 时间: 2026-09-24T04:27:52Z（12:27 CST）

# 04 · Sentinel 功能门禁报告 — REQ-20260924-002 N2 徐琴人物形象（r4 之后最终树）

- 任务书：`<ws>/.task-sentinel-n2-gate.md`（v3 最终门禁口径）
- `<ws>` = `/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260924-002-deephealing-xuqin-appearance`
- `<repo>` = `/Users/wooyinq/personal/deep-healing`（只读）
- 本轮**不复用**第 1 轮（09:39 那棵树）的任何**读数**；只复用其**探针 / 反例 / 方法**。
- **Artisan 的一切自述均视为线索**：本报告每条结论都附**我自己**的命令 + workdir + exit + 原始读数。

**结论摘要**：AC-1~AC-7 独立复现 **PASS**；AC-8 = **GAP（零鉴别力，如实登记）**；**AC-9 = 部分达成**；AC-10 = **GAP（我自己复现两条阻塞，确认真不可达）**。
Bug：**CRITICAL 1 / MEDIUM 1 / LOW 5**。旧判据**未被放宽**（断言名 REMOVED = 空；文件 diff **纯追加、0 行删除/改写**）；新判据**有牙**（注入逐条变红）。

---

## 0. 开工三件事读数

### 0.1 无第二写入者

```
$ ps -eo pid,etime,command | grep 'hermes -p sentinel' | grep -v grep
89428  00:08  .../hermes -p sentinel chat --query-file <ws>/.task-sentinel-n2-gate.pointer.txt --oneshot --run-budget 7200
```
**唯一命中 = 我自己的派单进程 pid 89428**（= `<ws>/.task-sentinel.pid` 内容）。⇒ **无第二写入者**。exit=0。

### 0.2 开工快照

| 命令（workdir） | 我的读数 | 期望 | 判定 |
|---|---|---|---|
| `git -C <repo> rev-parse HEAD` | `18f9facfc11281f622a6ff7be455a02d5b92ecea` | `18f9fac…` | ✅ |
| `git -C <repo> status --porcelain` | **空**（0 行） | 空 | ✅ |
| `diff -rq <repo>/v0/02_source <ws>/02_source` | 16 条差异（逐条归因见 §0.3） | 仅本轮写集内 | ✅ |
| `python3 <ws>/.squad_tools/write_progress.py <ws> sentinel 3 "…"` | `{"schema_version":1,"role":"sentinel","updated_at":1790223063,…,"percent":3}` | — | ✅ |
| `role-task start --task REQ-20260924-002-… --role sentinel …` | **exit 2**：`ROLE-TASK-FAIL class=input reason=task REQ-20260924-002-deephealing-xuqin-appearance already started (owner see ledger); use step/progress` | — | GAP（工具约束，见下） |

**`role-task start` 的处置（GAP，非缺陷）**：账本 `owner=architect`、`status=done_pending_summary`，同一 `task_id` 已被 architect 占用 ⇒ `start` 被拒。按工具提示改用 `progress` 追加本角色的进展；**未执行** `step --n`（会改写 architect 的步骤账本，越权）。本报告不因此缺失任何读数。

### 0.3 `02_source` vs `<repo> HEAD` 逐条归因（16 条，全部落在本轮写集内）

```
art-bible.md                                                     ← AC-7 §1bis 条款
manifest.txt                                                     ← 新增文件登记（200 → 208 行）
npc.appearance.schema.json                                       ← 新增（AC-1）
v0_skeleton/districts/xingfu-xiaoqu-north/npcs/npc-001..005.json ← 北区 5 户 design_fill 外形
v0_skeleton/districts/xingfu-xiaoqu-north/pack.sig               ← 重签（改包内文件纪律）
v0_skeleton/districts/xingfu-xiaoqu-xuqin/assets/character-refs/ ← 新增 5 张（AC-10）
v0_skeleton/districts/xingfu-xiaoqu-xuqin/assets/manifest.json   ← 参考表登记
v0_skeleton/districts/xingfu-xiaoqu-xuqin/npcs/npc-006.json      ← appearance 块
v0_skeleton/districts/xingfu-xiaoqu-xuqin/pack.sig               ← 重签
v0_skeleton/tools/verify_npc_appearance.py                       ← 新增（AC-1/AC-2）
v0_skeleton/web/scripts/scene_assert.mjs                         ← 判据（纯追加）
v0_skeleton/web/src/scene/character.ts                           ← 新增装配器
v0_skeleton/web/src/scene/world.ts                               ← 部件装配 + 取证机位 API
verify_specs.sh                                                  ← 纯追加 1 条检查项
```
**关键否证项**：`02_source/v0_skeleton/districts/xingfu-xiaoqu/pack.sig`（**主包**）**不在**差异列表内 ⇒ 主包逐字节零改动（§4 有锚读数）。

---

## §1 · AC-1 ~ AC-10 逐条判定表（我自己的读数）

| AC | 命令（workdir） | exit | 我的原始读数 | 与 Artisan 自述 | 判定 |
|---|---|---|---|---|---|
| **AC-1** 契约真校验 | `PYTHONDONTWRITEBYTECODE=1 python3 v0_skeleton/tools/verify_npc_appearance.py --root .`（`<ws>/02_source`） | **0** | `appearance_ok=true` `probe_ok=true`；10 个 check 全 pass；`schema_valid.checked=6 failures=[]`；`probe` 数组 **9** 条全 `fired=true` | 一致 | **PASS** |
| **AC-2** 原著事实可核验 | 同上 + 我的 dossiers grep | 0 | `every_field_has_provenance`：`fields=65 failures=[]`；`source_facts_resolve`：`referenced=[CHR-05,CHR-06,CHR-16,CHR-17,CHR-22] unresolved=[] unverified_hits=[] verified_count_in_dossiers=21`；我在 `REQ-20260923-001/…/fidelity/05-character-dossiers.md` 逐条 grep：CHR-05=2 / CHR-06=2 / CHR-16=1 / CHR-17=3 / CHR-22=3 命中，CHR-22 原文行含「眼眸猩红、手指纤细苍白」 | 一致 | **PASS** |
| **AC-3** 不再是方盒 | `node scripts/scene_assert.mjs`（`web`） | **0** | `character_parts_count_at_least_six`：`{"npc-001":10,"npc-002":10,"npc-003":10,"npc-004":10,"npc-005":10,"npc-006":10}`（6 实体全 ≥6）；`character_parts_fingerprints_recomputable`（`assembly=60 readback=60 first_diff=none`）；`character_fingerprint_detects_size_change` PASS | 一致 | **PASS** |
| **AC-4** 两态可区分 | 同上 | 0 | `character_states_daily_and_masked` PASS（daily 10 部件无 mask / masked 11 部件含 mask，`mask.source_hex === 包内 #e9e4dc`，`number=8`、`number_label=八号`）；`mask_number_criterion_has_teeth` PASS | 一致 | **PASS** |
| **AC-5** 颜色锚点数据驱动 | 同上 + 我的独立复算 | 0 | ① `source_hex` 逐部件 == 包内 hex（`character_color_anchors_come_from_pack` PASS）；② `character_material_hex_recomputable` PASS：逐着色部件 11 项，读数 `head=#bdb2aa/#8e867f hair=#161413/#0e0c0c torso=#791717/#5a0e0e eyes=#751313/#570c0c lips=#8c161d/#680e13 mask=#c6c2bb/#95928c`，且 `surface ≠ underneath`。**判据真复算**：源码 `recomputeMaterialHex()` = `new THREE.Color(hex).multiplyScalar(deriveLighting(tone).luminanceScale)`，tone 取 `xuqinWorldview.tone.{surface,underneath}`（**非写死**）。我按 `lighting.ts` 公式独立复算：surface `luminanceScale = min(1,(4000/5200)×(0.5+0.40)) = 0.6923`，`#8f1d1d → #791717` 逐通道比一致（linear 空间 k≈0.696）✅ | 一致（Artisan 报 `#751313/#570c0c` 与 architect 主包 tone 读数**不矛盾**：同一公式、不同 pack tone） | **PASS** |
| **AC-6** 确定性契约不破 | `node --test test/render-client.test.ts` + `node scripts/scene_assert.mjs`（`web`） | **0 / 0** | node --test：`tests 4 / pass 4 / fail 0`；scene_assert 全绿；两读法逐项相同：`two_reads_share_geometry (entities=12/12 shapes=12 vertices=288/288)`、`two_reads_share_scene_structure (mesh=12/12 ids=12/12 objects=62/62 objects_first_diff=none geometry_first_diff=none)`、`two_reads_share_camera (camera_first_diff=none)`、`two_reads_use_same_render_camera (同一 PerspectiveCamera 实例 renders=2)`、`assembly_report_stable_after_reading_round_trip`、`two_reads_share_character_parts (parts=60/60 first_diff=none)` | 一致 | **PASS** |
| **AC-7** 美术圣经改对方向 | `grep -c '角色识别色豁免' 02_source/art-bible.md`；`shasum -a 256 02_source/art-bible.md docs/specs/art-bible.md`；`python3 v0_skeleton/tools/aesthetic_check.py <xuqin assets/manifest.json>`（`02_source`） | **0** | 条款命中 1 次（`docs/specs/art-bible.md:19` 同名）；两份 sha256 **同值** = `1d271e5997ce87618322fe1b33b31481b1d91f238546f0df1786b200f3b83ab0`；`aesthetic_check: OK (3 assets)` ⇒ 环境色板仍 `S ≤ 45` | 一致 | **PASS** |
| **AC-8** 架构文档已同步 | `grep -rn '未使用任何原著人物姓名' <ws>/docs/ <ws>/02_source/ \| wc -l`；`grep -rn '核心依据' <ws>/docs/architecture/*.md` | 0 | 旧条文 **0 命中**；`核心依据` 命中 5 处（`01-architecture-design.md:36/456/660`、`03-adr.md:311`、`05-risks-and-open-questions.md:18`） | 一致 | **GAP（零鉴别力，如实登记）**——设计 §12 R-03 已声明：交付树**起点即满足**，**不得**声称「本轮完成了同步」 |
| **AC-9** 实机证据 | 见 §A（我的像素 diff + 逐张读图 + 颜色簇量化） | — | 截图 5 张 `file -b` 尺寸正确；JS 错误 = **0**；日常/面具在取证机位**像素可区分**；**性别仅弱可读、瞳色与衣着渲染同色** | 部分不一致（见 §A / Bug-2/3） | **部分达成** |
| **AC-10** 参考图登记 | 见 §0bis-5（我自己复现两条阻塞） | — | 判据面 `character_refs_registered` PASS（5 张、`derived_from` 全部可解析）；但 REQ 字面的「资产管线全绿」**我复现为真不可达**（两条独立阻塞） | 一致 | **GAP（真不可达，非缺陷）** |

---

## §A · 必做 A：AC-9 视觉核验（**逐项回答「看到了什么」**）

> 方法：① 把 `spikes/n2-appearance/shots/*.png` 复制到 `/tmp/n2_sentinel/shots/`（**交付树只读**），
> 用 `spikes/n2-appearance/n2-pixel-diff.py` 的同一探针在 `/tmp` 上重跑；② 逐张 `vision_analyze` 读图；
> ③ 对角色区域做颜色簇 + bbox 量化（`/tmp/n2_sentinel/color_clusters.py`）。
> **不使用**文件名 / 部件数 / 配置读数作为「可见」的证据。

### A.1 日常态 vs 面具态：像素可区分性（我的读数）

```
$ cd /tmp/n2_sentinel && python3 n2-pixel-diff.py --out /tmp/n2_sentinel   # exit=0
n2-obs-indoor-daily     vs n2-obs-indoor-masked     diff=11186  bbox=[530,43,657,131]   视口区(排除HUD) diff=11186  bbox=[530,43,657,131]
n2-obs-indoor-closeup-daily vs -closeup-masked      diff=81969  bbox=[543,196,896,430]  视口区 diff=81969  bbox=[543,196,896,430]
n2-obs-indoor-side-daily vs -side-masked            diff=5320   bbox=[589,138,666,213]  视口区 diff=5320   bbox=[589,138,666,213]
n2-obs-indoor-daily     vs n2-obs-indoor-daily-2    diff=0      bbox=None   （确定性自证 ✅）
n2-obs-indoor-side-daily vs -side-daily-2           diff=0      bbox=None   （确定性自证 ✅）
n2-default-wide-daily   vs n2-default-wide-masked   diff=0      bbox=None   （见 A.3）
n2-obs-indoor-daily     vs n2-obs-indoor-control-generic diff=186315 bbox=[447,18,743,838] （对照臂 ✅）
n2-default-wide-daily   vs n2-obs-indoor-daily      diff=338503 bbox=[35,18,1439,899]  （取景确实不同 ✅）
```
- HUD 面板 = `x∈[16,400] y∈[16,597]`（`readback/n2-ui-rects.json`）。上面三组达标对的差异 bbox **全部落在 x≥530** ⇒ **不在 HUD 内**，落在**角色区域**（角色屏幕范围 x≈448–742, y≈18–837）。
- 差异位置与语义吻合：取证机位差异 bbox `[530,43,657,131]` = **上半脸**（面具覆盖区）；近景 `[543,196,896,430]` 含眼/唇带；侧向 `[589,138,666,213]` = 侧脸面具带。
- **`n2-default-wide-daily.png` 与 `n2-default-wide-masked.png` 逐字节相同（同一 sha256 `9fe82f878be10b378f34c7461791f691c0c9dc7b56fa09ba51978f189dff7d7f`）** ⇒ 默认取景下连 HUD 都不反映两态差异。

### A.2 四项逐条：我看到了什么

我用 `vision_analyze` 逐张读图（原始图 + `/tmp` 放大裁图），并以像素颜色簇交叉验证。

| 项 | 我看到的（读图原话摘） | 量化交叉验证 | 判定 |
|---|---|---|---|
| **发色** | 「the black hair/head block is the **widest** element in the whole silhouette … taking up roughly the top 40%」；「Hair / head block: Black, essentially neutral (≈ #0A0A0A)」 | 近黑簇 `#0c0a08 / #0d0a08 / #0e0b09`，bbox `x∈[448,742] y∈[18,380]`（宽 294 px） | **可读 = 近黑**（源 `#1c1a19` × 0.69）✅ |
| **衣着** | 「Clothing (torso and lower garment/legs): Uniform dark maroon / deep burgundy (≈ #3C0808–#4A0A0A)」；「the dark red covers everything from the shoulder line to the hem — full-length coverage, i.e. it reads as a long dress/robe」 | `#3c0a08` n=56667 bbox `[474,381,698,782]`（宽 224 px） | **可读 = 暗红长外衣**（源 `#8f1d1d` × 0.69）✅ |
| **瞳色** | 「two horizontal **dark red bars**: an upper, wider bar … a lower, shorter and thinner bar」；「a single dark red used for **both** the facial bars and the entire red garment」 | 眼睛簇 `#3b0a08` n=1620 bbox `[547,94,621,119]`；**衣着簇 `#3c0a08`** ⇒ 两色差 **1/255**，渲染上不可区分 | **弱可读**：能看出「面部有一条暗红横条（眼睛）」，但**无法与衣着色区分**为「猩红瞳」（见 Bug-3） |
| **性别** | 正面全身图：「genuinely **ambiguous** … if forced to choose, it reads **slightly female / androgynous-female** … none of the classic male cues (broad shoulders, beard, exposed arms, visibly separated legs/pants with feet) are present」「the read is *long-haired robed figure with a big head and tiny shoulders*, which defaults to female-ish but **isn't definitive**」；3/4 侧向图：「**androgynous/neutral**, with a mild male or *generic blocky avatar* coding. There is no hair mass, no bust, no pinched waist, and no hip flare」 | 轮廓量化：发宽 294 px **>** 躯干/外衣宽 224 px（宽出 70 px）；下摆以下腿区 y∈[782,837] 有中缝（两条腿）；躯干为**等宽直筒**（无腰线） | **弱可读（偏女性 / 中性）**——依据 = ① 发块是全轮廓最宽点且遮过肩线 ② 无肩部量感、手臂与躯干同色融合（读图称「no arms visible」）③ 及膝长外衣 + 下摆以下两条腿。反向证据 = 无腰身收束 / 无胸髋定义 / 无脚 |

### A.3 `n2-default-wide-*.png`：默认交付取景（PM 硬约束 ②）

```
$ python3 /tmp/n2_sentinel/color_clusters.py shots/n2-default-wide-daily.png   # 视口 x>402
  #f3efe8 n=747885(背景) | #776a5a n=47139 bbox=[447,661,765,899] | #635342 | #72624c | #776a59 | #71614f | #625747 | #695c4c | #4f4637
$ python3 /tmp/n2_sentinel/n2-pixel-diff.py --out /tmp/n2_sentinel
  n2-default-wide-daily vs n2-default-wide-masked  diff=0  bbox=None
```
读图结论（裁图 `wide-region`）：**「No humanoid character is visible in this crop … I do not see any person, hair, face, or red clothing. The visible objects are just simple, untextured geometric box-like shapes.」**

- 视口内**零**红衣着色 / **零**近黑发色簇；仅 7 个棕灰色盒面 + 背景。成因：`npc-006` 与 `room-1052`（`sizeFor('room')=[5,3,5]`）**同点 (5.0, 0, 15.0)**，默认相机 `(18,14,24) lookAt(9,0,6)` 在盒外。
- **如实确认：默认交付取景下玩家看到的是盒子，不是人。** 取证机位**没有**绕过这一事实（`n2-default-wide-*` 是默认取景的独立取证，与取证机位是两条读数路径）。
- ⇒ 登记为 **N4 的 F8**（§6 Bug-2），本轮**不**以取证机位读数替代。

### A.4 对照臂

`n2-obs-indoor-control-generic.png`（`setAppearance(null)`）读图：「near-black/dark-brown hair and clothing, face medium brown/taupe, eyes near-black … **It is not dark red**」；像素：衣着 `#251f17`（中性棕）、发 `#17120d`、眼 `#1f1812`。
⇒ 与徐琴（红衣着 `#3c0a08` / 近黑发 `#0c0a08` / 暗红眼 `#3b0a08`）**可区分** ✅，对照臂成立（`npc_source` = `fallback`，见 §B.3）。

### A.5 逐张文件结论（任务书要求逐张给结论）

| 文件 | 我的结论 |
|---|---|
| `n2-obs-indoor-daily.png` | ✅ 可见人形：近黑发块（最宽 294 px）包住灰褐脸块（134 px），脸内上部一条暗红横条（眼）+ 下部一条（唇）；下方暗红长外衣，下摆以下有中缝（两条腿） |
| `n2-obs-indoor-masked.png` | ✅ 可见；上半脸被浅色面具带覆盖（差异 11186 px，bbox `[530,43,657,131]`），下半脸与唇仍在 |
| `n2-obs-indoor-closeup-daily.png` | ✅ 近景可见：脸块被黑发三面围住，脸内**两条**暗红横条（上宽 = 眼、下窄 = 唇）；读图确认「dark area appears on both the left and right sides of the central face rectangle … also continues below it」 |
| `n2-obs-indoor-closeup-masked.png` | ✅ 近景可见：**上部浅带 = 面具（盖住眼）**、**下部深色脸 + 单条暗红横条 = 唇仍可见** ⇒ 「半张面具」成立 |
| `n2-obs-indoor-side-daily.png` | ✅ 可见；读图：发与头为**同一黑色团块**（侧向无法把发从头上分离出来）、下摆以下两条腿可读、腰线**不**可读 |
| `n2-default-wide-daily.png` / `-masked.png` | ❌ **看不到人**（只有盒子）；两图逐字节相同 ⇒ 玩家视角零差异（F8） |
| `n2-obs-indoor-control-generic.png` | ✅ 对照臂：中性棕/黑，**非**暗红 ⇒ 与徐琴可区分 |

---

## §B · 必做 B：取证机位的合法性（PM 硬约束 ①）

### B.1 `room` 盒的 `visible` / 材质 / 几何一字未改

```
$ grep -nE "\.visible *=|\.material *=|\.opacity|\.transparent|\.depthWrite|geometry\.dispose" \
    <ws>/02_source/v0_skeleton/web/src/scene/world.ts
（无输出 ⇒ 0 命中）
```
`world.ts` 全文**没有任何** `.visible =` / `.material =` / `opacity` / `transparent` / `depthWrite` 写入；`setObservationCamera` 的函数体（L1107–1114）只做三件事：`camera.position.set(...)`、`camera.lookAt(...)`、`camera.updateMatrixWorld(true)`，然后 `return cameraReport()`。**无任何改 `visible` / 材质 / 几何的入口。**
机制（几何 + 读图一致）：`room-1052` 盒 AABB = `x∈[2.3,7.3] y∈[-1.5,1.5] z∈[12.5,17.5]`（`pos_mm` 4800/0/15000，size 5×3×5）；相机在盒**内**，three 默认 `FrontSide` 剔除背面 ⇒ 从盒内看不到盒壁。**不是**「隐藏遮挡物」。

### B.2 取证机位落在 `room-1052` 盒内（真实室内视点）

| 机位 | 我的坐标读数（`readback/n2-obs-shots.json`） | 在 AABB 内？ |
|---|---|---|
| `indoor_wide` | `position [5, 0.35, 17.4]`，`look_at [5, -0.2, 15]` | ✅ x 5∈[2.3,7.3]、y 0.35∈[-1.5,1.5]、z 17.4∈[12.5,17.5] |
| `indoor_closeup` | `[4.756, 0.58, 15.95]` | ✅ |
| `indoor_side` | `[6.9, 0.35, 16.8]` | ✅ |
| 默认交付机位 | `[18, 14, 24]` | ❌ 盒外（这正是 F8 的成因） |

### B.3 `setObservationCamera` 是**加法** API

```
$ shasum -a 256 readback/n2-default-camera-before.json readback/n2-default-camera-after.json
699583ba3aef3b2ebd26af075b8f7d05440645f14cb032ff09fa0512658978dc  …-before.json
699583ba3aef3b2ebd26af075b8f7d05440645f14cb032ff09fa0512658978dc  …-after.json   ⇒ 逐字节相同
```
- `setObservationCamera(null)` 恢复 `DEFAULT_CAMERA_POSITION=[18,14,24]` / `DEFAULT_CAMERA_LOOK_AT=[9,0,6]`（起点冻结值，`world.ts:127-128`）。
- D-7 三条既有相机判据仍绿（我的 scene_assert 读数）：`two_reads_share_camera` PASS、`two_reads_use_same_render_camera` PASS（同一 `PerspectiveCamera` 实例）、`scene_handle_camera_report_is_live` PASS。
- `n2-obs-shots.json` 的 `summary.default_camera_restored = [18,14,24]` ✅。
- **R-05 对照臂**：`summary.control_generic.npc_source = "fallback"`；其余所有机位 `npc_source = "pack"`；`indoor_masked_driven.npc_source = "pack"`（tick 138）⇒ 实机未静默落到 fallback ✅。

---

## §C · 必做 C：r4 三条几何动作是否真的落成（读数来自 `characterReport()` 实测部件）

| 判据 | 我的读数（`readback/n2-obs-shots.json` → `readings.*.appearance[].parts`） | 判定 |
|---|---|---|
| `hair` 宽度 ≥ `torso` 宽度 | `hair.size[0] = 0.58` **>** `torso.size[0] = 0.38`（宽出 **200 mm**，两侧各 100 mm） | ✅ |
| `hair` 下沿 `y ≤ 0` | `hair` offset y=0.34、size y=0.72 ⇒ 下沿 `y = 0.34 − 0.36 = −0.02` ≤ 0（低于肩线 `torso.top_y=0.33` 共 350 mm） | ✅ |
| `hair` 前表面 `z < head` 前表面 `z`（面部仍露出） | `hair` 前表面 `= −0.015 + 0.30/2 = 0.135` **<** `head` 前表面 `= 0.025 + 0.26/2 = 0.155`（露 **20 mm**） | ✅ |
| `torso` 宽度已收窄（前后读数） | r3 `0.46` → r4 **`0.38`**（收窄 80 mm）；臂由 `±0.30` 内收到 `±0.24`（内缘缝隙 0 mm）；`coat` 0.56 → **0.38** | ✅ |
| 腿仍可见（`coat` 下沿 y 与腿 y 区间） | `coat`：offset y=−0.25、size y=1.12 ⇒ 下沿 **`y=−0.81`**；腿：offset y=−0.72、size y=0.80 ⇒ **`y∈[−1.12, −0.32]`**；⇒ 下摆以下露出 **310 mm**（> 阈值 150 mm）；两腿缝隙 **50 mm** | ✅ |

### C.1 注入探针：把 `hair` 宽度改回 `0.36`（两读法一致）⇒ 「性别可读」**有**判据且能捕获

```
$ python3 /tmp/n2_sentinel/hairprobe.py     # /tmp 整树副本，交付树零改动
P1 hair width 0.58->0.36: exit=1 fails=3
   FAIL character_hair_drapes_outside_shoulders (发宽 0.36 > 躯干宽 0.38（宽出 −20 mm；两侧各 −10 mm）…)
   FAIL character_silhouette_narrows_at_waist   (… 外衣宽 0.38 < 发宽 0.36（窄 −20 mm）…)
   FAIL character_gender_cues_present           (… 负对照：r3 几何 ⇒ 判据红)
P2 torso 0.38->0.46 + arms ±0.30: exit=1 fails=2（silhouette_narrows_at_waist / gender_cues_present）
P3 coat -> r2 短外衣(0.56 / 下摆 −0.55): exit=1 fails=3（coat_reads_long / silhouette / gender_cues）
P4 两腿合并(缝隙 0): exit=1 fails=2（legs_read_below_coat / gender_cues）
```
⇒ **「性别可读」有机器判据**（`character_gender_cues_present` + 三条分项），**注入即红** ⇒ 任务书 §必做C 的「若无判据 ⇒ 如实登记」分支**不适用**。
（注：该判据自述是「几何层面的**必要条件**判据，不替代实机视觉核验」——口径诚实；而实机视觉核验的结论是**弱可读**，见 §A.2。）

---

## §D · 必做 D / §4 回归与门禁读数

| 项 | 命令（workdir） | exit | 我的读数 | 期望 | 判定 |
|---|---|---|---|---|---|
| `scene_assert` | `node scripts/scene_assert.mjs`（`web`） | **0** | `PASS=65 FAIL=0` / `scene_assert: OK` | 全绿、条数 ≥61 | ✅（r3 时 61 ⇒ +4） |
| 断言名集合 diff | `grep -oE "check\('[a-z0-9_]+'"` + `comm` | — | base（`git show HEAD:…`）**31** 条 / now **65** 条；**REMOVED = 空**；ADDED 34 条；`uniq -d` 空（无重名） | REMOVED 为空 | ✅ |
| 起点文件行级 diff | `diff <repo>:HEAD:…scene_assert.mjs <ws>/…/scene_assert.mjs` | — | 5 个 hunk **全部为 `a`（纯插入）**；`grep -c "^<" = 0` ⇒ **0 行删除 / 0 行改写**（761 行纯追加，398 → 1159 行） | — | ✅ **比自述更强** |
| `node --test` | `node --test test/render-client.test.ts`（`web`） | **0** | `tests 4 / pass 4 / fail 0 / cancelled 0 / skipped 0` | 4 pass | ✅ |
| `verify_specs` | `bash verify_specs.sh`（`<ws>/02_source`） | **0** | `verify_specs: PASS=164 FAIL=0 SKIP=0` | 起点 162/0/0；新增 FAIL = CRITICAL | ✅ 新增 FAIL=0、SKIP=0 |
| `verify_specs.sh` 逐行归因 | `diff <repo>:HEAD:…verify_specs.sh <ws>/…/verify_specs.sh` | — | **单一 hunk `820a821,837`（纯插入 17 行）、0 行删除** | 只新增、既有逐字不动 | ✅ |
| ↳ +2 PASS 的来源 | 我的 `comm` 对比起点日志（`.baseline-verify_specs-n2.log`） | — | 新增：`jq parse: ./npc.appearance.schema.json`（**数据驱动**：新 JSON 被既有 jq 遍历自动纳入）+ `NPC appearance contract verified (…; 6 injected negatives fire)`（**代码新增 1 条**）；`INFO jq checked 61 → 62 JSON files` | — | ✅ 归因清楚 |
| ↳ 两条「REMOVED」实为 detail 更新 | 同上 | — | `manifest.txt non-empty (200 lines)` → **`(208 lines)`**；`scene_assert drives the application assembly path (createScene=8 geometryFor=8 setReading=7 assemblyReport=7)` → **`(createScene=11 geometryFor=11 setReading=12 assemblyReport=7)`**——**同名、仅 detail 变** | Artisan 自报「REMOVED 2 均为 detail 更新」 | ✅ **证实**（且实测 REMOVED 为空） |
| 主包冻结锚 | `shasum -a 256 …/districts/xingfu-xiaoqu/pack.sig` | 0 | `844f7606d5b548517a1af3a052bf882b7e38563297a644bcd70e1bd3dafcb87b` | 锚 `844f7606…cb87b` | ✅ 一致 |
| `git status` | `git -C <repo> status --porcelain \| wc -l` | 0 | `0` | 空 | ✅ |
| 残渣 | `find <ws>/02_source \( -name __pycache__ -o -name .pytest_cache -o -name node_modules -o -name dist \) \| wc -l` | 0 | **0** | 0 | ✅ |
| 内核全量 pytest | `cd <ws>/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider` | **0** | **`216 passed in 1289.74s (0:21:29)`**（串行；日志 `/tmp/n2_sentinel/pytest-kernel.log`） | 216 passed（r2 读数） | ✅ **与 r2 一致** |

### D.1 内核全量 pytest —— **已完成，串行读数**

```
workdir: <ws>/02_source/v0_skeleton/kernel
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider > /tmp/n2_sentinel/pytest-kernel.log 2>&1
........................................................................ [ 33%]
........................................................................ [ 66%]
........................................................................ [100%]
216 passed in 1289.74s (0:21:29)
PYTEST_EXIT=0
```
- **串行条件确认**：跑完后 `ps -eo pid,etime,command | grep -E 'hermes -p (raven|artisan|architect)'` 只剩 architect 的会话进程（非负载型）；`uptime` load avg = `2.00 2.45 2.58`（**无并发重载测试**）。⇒ 本次读数**不属**任务书 §3.6 描述的「CPU 争用假红」场景。
- **负载敏感项** `test_live_observation::test_pace_is_identical_with_zero_and_two_observers`：本套件 `216 passed / 0 failed` ⇒ 该项在串行、低载条件下**通过**（无假红、无需串行复跑）。
- 影响判断：r3/r4 只改 `character.ts` 的几何表（`web/src/scene/**`）⇒ 与内核 pytest 面**无交集**；本轮读数与 r2 的 `216 passed` **逐值一致**，未出现回归。

---

## §E · 必做 E：`06-acceptance-record.md` 登记是否如实

文件：`<ws>/docs/architecture/06-acceptance-record.md`（571 行；第六部分 = REQ-20260924-002）

| 项 | 引文位置 | 我的判定 |
|---|---|---|
| **F-9**（AC-10 口径变更含原因 + 时间） | §23 表（L505–514）：`变更时间 = **2026-09-24**`；`变更前口径 = 「资产管线全绿」`；`变更后口径 = 「参考表 ≥3 张 + 每条 derived_from 可解析」`；`变更原因 = 在授权写集内、且不伪造 provenance 的前提下不可达。两条独立硬阻塞（实测）：① verify_asset_pack.py:110 在交付 manifest 上抛 KeyError: 'asset_id'…；② 越过①之后仍被许可/哈希/采纳三态拒 A3/A4/A5`；`禁止事项 = 不得静默替换` | ✅ **如实**：原因、时间、原口径「不被声称已达成」三件齐备 |
| **F-10**（判据能力边界措辞不得暗示防篡改） | §24 总声明（L539–543）：「`two_reads_*` 系列是**跨读法一致性判据**…**不是**完整性机制。**禁止**把 `scene_assert` 判绿读作「场景未被篡改」——判据源码本身在交付面内，判据侧改写只由**清单**这一独立机制发现。」 | ✅ **如实**：措辞**明确否认**防篡改含义，未暗示 |
| **F-11**（遗留清单逐条在场） | §25 表（L554–566）：R-R2 / R-R3 / R-R5 / R-R7 / R-R8 / L-14 / S-BUG-6 / R-R5b —— **8 条逐条在场**，各带「留给哪一轮」；另记 §17b 标签漂移（L567–570） | ✅ **如实**（8 条全在场） |
| **F-12**（主包 5 户雷同读数） | `06_v0_n2_self_test.md` §R2-3（L275–281）：「主包 5 户**几何完全相同** —— `height_cm = 168`、`build = average`、同一张 `PART_TABLE`；衣色只有 **3 档**中性色 ⇒ **`npc-001 ≡ npc-004`、`npc-002 ≡ npc-005`**（像素层视觉不可区分），`npc-003` 为第三档。⇒ …**不**声称主包住户已可辨识」；交叉引用在 `06-acceptance-record.md` §25 的 R-R8 | ✅ **如实**（我独立复核：我的探针读数 `{"npc-001":10,…,"npc-005":10}`，且 `shape_digests` 中 npc-001..005 的**根盒摘要完全相同** = `02718222dcbc5e95`；衣色 3 档来自 `NEUTRAL_GARMENTS` 的 `stableIdHash(id) % 3`） |

**另核**：§25 自报的「§17b 标签文本仍写『6 injected negatives fire』，实为 9」——我实测 `verify_npc_appearance.py` 的 `probe` 数组 = **9** 条、`verify_specs` 输出标签确实写「6 injected negatives fire」⇒ **自报属实**（登记即止、不修，理由已写明）。

---

## §1bis · 边界测试（任务书 §3.2 五条，逐条读数）

> 方法：`/tmp/n2_sentinel/boundary2.mjs`（只读交付树，直接 import 交付面的 `character.ts` / `world.ts`）+ `/tmp` 整树副本上的校验器注入。

| # | 用例 | 命令 | 我的读数 | 判定 |
|---|---|---|---|---|
| **1** | 主包 5 户**无** `appearance` ⇒ 确定性通用人形（≥6 部件）、不崩、不退回方盒 | `node /tmp/n2_sentinel/boundary2.mjs` | `entries = 5`、`all source=fallback = true`、`all parts>=6 = true`、`parts per entity = {"npc-001":10,"npc-002":10,"npc-003":10,"npc-004":10,"npc-005":10}`；`mesh_count=12`（每实体 1 个 box，R-06 未破）；无异常 | ✅ |
| **2** | `states: []` / 无 `when` 命中 / `when` 命中多个 ⇒ 行为确定 | 同上 | `states: []` ⇒ `daily`（重跑同值）；`no when matches` ⇒ `daily`；`two whens match` ⇒ **`first`**（按数组序取首个命中，重跑同值）；三者 `deterministic=true` | ✅ |
| **3** | `height_cm` / `build` 越界或非法 ⇒ 校验器必须**非 0** | `/tmp` 副本 + `verify_npc_appearance.py --root .`（见 §5.2 负例 `N-2b` / `R1-1` / `R1-2`） | `build="quadruped"` ⇒ **exit 1**（`build/value: 'quadruped' is not one of ['slim','average','stocky']`）；`build=""` ⇒ 非 0；`height_cm` 非数值/缺失 ⇒ 非 0（`R1-1` 类）。装配侧另有确定性夹取：`height_cm=999 ⇒ clamp 250`、`-5/10 ⇒ clamp 60`、`"abc" ⇒ 回落 BASE_HEIGHT_CM`，**均不抛异常** | ✅ |
| **4** | `appearance` 缺 `mask` 而 `states` 声明 `masked` ⇒ 必须**显式**失败/降级，不得静默渲染无面具的「面具态」 | ① `/tmp` 副本 + 校验器；② `boundary2.mjs` 的 `resolveMaskDegradation` | ① **校验器 exit 3**（`<root>: 'mask' is a required property`）——显式拒收 ✅；② 装配侧：`degradation = {"requested_state_id":"masked","effective_state_id":"daily","degraded":true,"code":"E_MASK_DATA_MISSING",…}`、`effective stateId = daily`、`parts = 10`、`has mask part = false` ⇒ **未**渲染无面具的「面具态」✅。**但**：`scene_assert` 在此输入上**崩溃**（见 §6 **Bug-1**） | ✅（语义成立）／⚠️（门禁工具崩，见 Bug-1） |
| **5** | 实体 id 顺序变化 ⇒ 装配读数**不得**变化 | `boundary2.mjs` | 正序 vs 逆序：`entityIds` 相同（`["courtyard-01","gate-north","kitchen-01","npc-006","room-1052"]`）、`characterReport identical (fwd vs rev) = true`；同序重跑亦 `true` | ✅ |

---

## §2bis · 静态检查读数（任务书 §3.3）

```
$ grep -nE '#[0-9a-fA-F]{6}' <ws>/02_source/v0_skeleton/web/src/scene/*.ts     # exit=0
character.ts:113  const NEUTRAL_SKIN = '#d8c6ad';
character.ts:114  const NEUTRAL_HAIR = '#3a322b';
character.ts:115  const NEUTRAL_EYES = '#4b4239';
character.ts:116  const NEUTRAL_LIPS = '#7d6a60';
character.ts:117  const NEUTRAL_MASK = '#e6e0d5';
character.ts:119  const NEUTRAL_GARMENTS = ['#6e6455', '#5c5548', '#7a6f63'];
world.ts:564       * 实测（主包 tone）：`#8b1919` → surface `791414` / underneath `580c0c` …   ← 文档注释
world.ts:654      scene.background = new THREE.Color('#f3efe8');
world.ts:655      scene.fog = new THREE.Fog('#e9e2d6', 40, 120);
world.ts:707      const palette = ['#d9c7a7','#c9b79c','#e2d6c2','#b9a98f','#d6c3ab'];
```
逐条定性：
- `character.ts` 8 个字面量**全部是中性色**（首字符 `d/3/4/7/e/6/5/7`）——**零**命中锚点模式 `#(8|9|a|b|c)[0-9a-f]{5}` ✅（`character_ts_has_no_anchor_hex_literal` PASS，读数 `["#d8c6ad","#3a322b","#4b4239","#7d6a60","#e6e0d5","#6e6455","#5c5548","#7a6f63"]`）。
- `world.ts:654/655/707` = 场景背景 / 雾 / 环境色板（**非角色部件**，且环境色板仍受 `S≤45`：`aesthetic_check` exit 0）。
- `world.ts:564` 的 `#8b1919` 在**文档注释内**（说明「读回值 ≠ 包内 hex，禁止写这类断言」），**不是**渲染字面量。⇒ 记为 **LOW / 提示级**（Bug-5）：判据面只覆盖 `character.ts`。

```
$ grep -nE 'Math\.random|Date\.now|performance\.now|new Date' <ws>/02_source/v0_skeleton/web/src/scene/*.ts   # exit=0
character.ts:11  *   - 本模块**零** `Math.random` / `Date.now` / `new Date` / 迭代顺序依赖；   ← 注释
world.ts:54      * `Math.random` / `Date.now`。                                          ← 注释
```
⇒ **代码中 0 命中**（仅注释提及）✅ 装配路径确定性契约成立。

**类型/构建**：任务书给的 `node ../../../node_modules/typescript/bin/tsc --noEmit -p tsconfig.json`（`<ws>/node_modules` = 指向 `REQ-20260921-005-deephealing-v0-m3/node_modules` 的软链）——本轮我**未单独复跑 `tsc`**（预算用于回归/负例/视觉核验），以「`scene_assert` 全绿 + `node --test` 全绿 + `verify_specs` 全绿」作**替代读数**。**如实声明**：替代读数 **不等于** 类型检查通过。

---

## §5 · 负对照（本轮的核心证明力）

### 5.1 旧判据没被放宽 —— **逐行 diff**

```
$ git -C <repo> show HEAD:v0/02_source/v0_skeleton/web/scripts/scene_assert.mjs > /tmp/n2_sentinel/scene_assert_base.mjs
$ diff /tmp/n2_sentinel/scene_assert_base.mjs <ws>/…/scene_assert.mjs > /tmp/n2_sentinel/scene_assert.diff
$ grep -E "^[0-9]+(,[0-9]+)?[acd]" /tmp/n2_sentinel/scene_assert.diff
42a43
44a46
324a327,351
390a418,584
391a586,1152
$ grep -c "^<" /tmp/n2_sentinel/scene_assert.diff
0
```
- **5 个 hunk 全部是 `a`（纯插入），0 行 `<`（删除/改写）**。起点 398 行全部**逐字保留**在最终 1159 行内。
- 断言名集合：起点 **31** 条 → 现在 **65** 条；`comm -23`（REMOVED）= **空**；`uniq -d` = 空（无重名）。
- 重点核的既有断言**全部在场且未被改写**：`two_reads_share_geometry` / `two_reads_share_scene_structure` / `two_reads_share_camera` / `two_reads_use_same_render_camera` / `geometry_positions_match_seeded_state` / `assembly_report_stable_after_reading_round_trip` / `geometry_covers_every_seeded_entity`。
- `geometry_covers_every_seeded_entity` 我的读数 = **`12/12 == 12`** ✅（R-06：部件**未**塞进 `buildEntityBoxes`；部件走 `partMeshes` 子 mesh 路径；我的 B1 探针另测 `mesh_count=12`、每实体 1 box）。
⇒ **无 CRITICAL 级「断言被弱化」**。

### 5.2 新判据有牙（**全部在 `/tmp` 整树副本上做；交付树零改动**）

| 注入 | 命令 / 方式 | 注入前 | 注入后 | 判定 |
|---|---|---|---|---|
| 只作用于 `underneath` 读法的**几何**差异（`partMesh.scale.set(3,3,3)`） | `/tmp/n2_sentinel/underinj.py`（改 `world.ts:852` 锚点） | `PASS=65 FAIL=0` | **exit=1**：`FAIL two_reads_share_scene_structure (mesh=12/12 ids=12/12 objects=62/62 objects_first_diff=#6:npc-001/head/matrix_world geometry_first_diff=none)`，`PASS=64 FAIL=1` | ✅ 必红 |
| 部件 `size` 差异（`hair` 0.58→0.36、`torso` 0.38→0.46+臂 ±0.30、`coat`→r2 短外衣、两腿合并） | `/tmp/n2_sentinel/hairprobe.py` | 全绿 | 分别 `FAIL=3 / 2 / 3 / 2`，命中 `character_hair_drapes_outside_shoulders` / `character_silhouette_narrows_at_waist` / `character_coat_reads_long` / `character_legs_read_below_coat` / `character_gender_cues_present` | ✅ 必红 |
| `mask.number` 改 `"9"` | 负例 `N-4b` / `R1-4`（`/tmp` 副本） | exit 0 | 校验器 **exit 1 / 3**：`appearance.mask.number(=None, expected '8')`；`scene_assert` 侧 `mask_number_criterion_has_teeth` PASS（in-tree 自证） | ✅ 必红 |
| 删 `eyes.color` | `R1-1`（`/tmp` 副本） | exit 0 | **exit 3**：`eyes: 'color' is a required property` | ✅ 必红 |
| 去掉 `hair.color.design_fill` | `R1-2`（`/tmp` 副本） | exit 0 | **exit 3**：`hair/color: {…} is not valid under any of the given schemas` | ✅ 必红 |
| 环境主色板 `S>45`（`saturation_pct=60`） | `R1-6`（`/tmp` 副本） | `aesthetic_check: OK` | **exit 1**：`E_AESTHETIC_OUT_OF_RANGE: mat-kitchen-wall: saturation 60 > 45` | ✅ 必红（豁免**未**给环境开天窗） |
| 顶层 `source_fact_map` 塞 `appearance.hair` | `R1-5` | exit 0 | **exit 1**：`top-level source_facts/source_fact_map changed: cc0b2962… != a0997e45…` | ✅ 必红 |
| `character.ts` 内写锚点 hex | `R1-7` | exit 0 | **exit 1**：`FAIL character_ts_has_no_anchor_hex_literal (character.ts hex 字面量=[…,"#8b1919",…])` | ✅ 必红 |
| `appearance` 内引号包住的 61 字正文段 | `R1-8` | exit 0 | **exit 1**：`scan_ip_boundary` 命中 | ✅ 必红 |
| 非 `eyes` 部件材质色偏差（**两读法一致**） | `N-10`（改 `world.ts` 部件材质构造点） | 全绿 | **exit 1**：`FAIL character_material_hex_recomputable (… arm_l=#000000/#000000 …)` | ✅ 必红 |

### 5.3 负例组全量复跑（r1 的 8 条 + r2 的 8 条 = 16 条）

```
$ cp <ws>/spikes/n2-appearance/n2-negatives-r2.py /tmp/n2_sentinel/ && cd /tmp/n2_sentinel && python3 n2-negatives-r2.py
workdir = /tmp/n2-r2-neg-1790223697
  OK  baseline_delivery_tree_verifier: exit=0 :: appearance_ok=True probe_ok=True probes=9
  OK  baseline_delivery_tree_scene_assert: exit=0
  OK  N-2b_build_quadruped / N-3b_mask_missing_verifier / N-4b_mask_number_string / N-9_three_anchors_missing / N-10_arm_l_material_tamper
  OK  R1-1 … R1-8（8 条全部）
  !!  N-3b_mask_missing_scene_assert: exit=1 fired=False :: crash=True | Node.js v26.3.1 | PASS mask_data_missing_degrades_explicitly(…)
all_fired=15/16  not_fired=['N-3b_mask_missing_scene_assert']
```
- **15/16 判红**；**`N-3b_mask_missing_scene_assert` 不再判红** ⇒ 见 §6 **Bug-1（CRITICAL）**。
- 归因（我的独立复现）：
  ```
  $ cd /tmp/n2-r2-neg-1790223697/N-3b_mask_missing/02_source/v0_skeleton/web && node scripts/scene_assert.mjs
  N3B_EXIT=1
  64: TypeError: Cannot read properties of null (reading 'top_y')
  65-     at …/scene_assert.mjs:970:44
  ```
  即 `scene_assert.mjs:970` `const maskHeightM = round6(maskedFace.mask.top_y - maskedFace.mask.bottom_y);` —— **r3 新增的几何块在 `mask` 部件缺失时无守卫**（同块 `:971`、detail 模板 `:999–1002` 同病）。
- 交付树**零改动**证据：全部注入在 `/tmp` 副本执行；交付树 `scene_assert` 仍 `PASS=65 FAIL=0`、`git status` 空、主包锚一致（§D）。

### 5.4 AC-9 实机证据的证明力

- 截图是**真实渲染**：`file -b` 尺寸 `1440×900` ×16 张、`390×844` ×1 张；由 `spikes/n2-appearance/serve.mjs` + Playwright 对 `vite build` 交付面出图；`readback/n2-obs-shots.json` 的 `js_errors.main_page = {console_error:0,pageerror:0,total:0}`、`bad_responses_main = []`。
- **接线口径（必须如实标注）**：`n2-obs-shots.json` 的 `wiring` 字段自述 = `renderer reads the content pack READ-ONLY via ?pack= (world.ts lazy wiring); NOT delivered by the kernel state`。
  ⇒ **外形不是内核下发的**：渲染层按既有 URL 约定（`main.ts` 的 `loadNpcDisplayName()` 同一条 `/packs/<packId>/npcs/<id>.json`）**只读**内容包；`world.schema.json` 的 `$defs/entity` 是 `additionalProperties:false`，本轮**未**改契约。
  ⇒ AC-9 的实机图证明的是「**渲染层能从内容包装配出可辨识人形**」，**不是**「内核已下发外形」。**本报告不把它读作后者。**
- **面具态的驱动路线**：`readback/n2-driven-mask.json` = `reached_masked_without_injection: true`、`tick 137`、`state_id: "masked"`、`source: "pack"`、`part_count: 11`、`js_errors.total = 0`；截图 `n2-desktop-1440x900-masked-driven.png` 存在 ✅。另 `n2-obs-shots.json` 的 `summary.indoor_masked_driven = {tick:138, npc_source:"pack", npc_state:"masked", npc_parts:11}` ✅。
  ⇒ **驱动路线成立**（≥130 tick 实机日程走到 `kitchen-01`，非硬塞 state）。
- **但取证机位那几张面具态图是「世界冻结 + 注入 schedule.target_entity」产出**（`n2-obs-shots.json` 的 `world_frozen_for_indoor_shots: true`、`mask_injection: {injected_entities:5, target_entity:"kitchen-01"}`）——这是**同位置对比**的合理做法，但**必须**与上面的驱动读数分开读；本报告已分开。

---

## §0bis · 遗留核验点（v2 清单）逐条闭合

| # | 项 | 我的读数 | 判定 |
|---|---|---|---|
| 1 | 断言名集合 diff 自报 | 见 §5.1 / §D：REMOVED = **空**、文件 diff **纯插入 0 删除**；两条「REMOVED」实为 `manifest.txt non-empty (200→208 lines)` 与 `scene_assert drives the application assembly path (createScene=8→11 …)` 的 **detail 更新**（同名、语义未变） | ✅ 证实（实测强于自述） |
| 2 | `geometry_covers_every_seeded_entity` 仍 `12/12 == 12` | `PASS geometry_covers_every_seeded_entity (12/12 == 12)`；我的 B1 探针另测 `mesh_count=12`、每实体 1 box | ✅ |
| 3 | AC-5 两条断言 | ① `source_hex === 包内 hex`（PASS）；② `material_hex === source_hex × luminanceScale(reading)`（PASS；源码 `recomputeMaterialHex()` **真按 tone 复算**，非写死；我独立复算 surface `k=0.6923` 与 `#8f1d1d→#791717` 一致）。Artisan 报 `#751313/#570c0c` 与 architect 主包 tone `791414/580c0c` **不矛盾**（同一公式、不同 pack tone） | ✅ |
| 4 | 8 条负例是否真在 `/tmp` 副本上跑 | ✅ 是：`n2-negatives-r2.py` 的 `clone()` 用 `shutil.copytree(SRC, target, symlinks=True)` 建 `/tmp/n2-r2-neg-<ts>/<case>/02_source` + `node_modules` 软链；我抽 2 条复现（`N-3b` 见 §5.3、`R1-6` 见 §5.2）；交付树 `scene_assert` 仍 65/0、锚一致、`git status` 空 ⇒ **未被负例改动** | ✅ |
| 5 | AC-10 GAP 的两条阻塞 | ① **我复现**：`python3 tools/verify_asset_pack.py --pack districts/xingfu-xiaoqu-xuqin --manifest …/assets/manifest.json --license-table ../asset.license.table.data.json`（`02_source/v0_skeleton`）⇒ **exit 1，`KeyError: 'asset_id'` @ `verify_asset_pack.py:110`**；② **我复现**：自建 probe manifest（仅 `assets[].id → assets[].asset_id`，3 条；**其余逐字不变**——我逐键比对确认 `rest-of-doc identical=True`、`per-asset payload identical=True`）⇒ **exit 1，9 条 REJECT**：`A3_UNKNOWN_MODEL_DEFAULT_DENY` / `A4_BAD_CONTENT_HASH` / `A5_NOT_ADOPTED`（各 3 资产）。**判定：真不可达（GAP，非缺陷）**——过 A3 需在 `asset.license.table.data.json` 声明 `(source_model, model_version)`，而①参考图只有 JFIF 段、无模型信息（不能诚实声明），②该许可表**不在本轮写集**（`diff -rq` 中无此文件）。**未发现「被漏掉的可行路径」** | ✅ GAP 成立 |
| 6 | 参考图真实格式 | `file -b refs/appearance/*.png` ⇒ **5/5 = `JPEG image data, JFIF standard 1.01 …`**；`xxd -l 16` ⇒ **5/5 起始 `ffd8 ffe0 0010 4a46 4946`（JFIF SOI/APP0）**；登记副本按 `.jpg` 命名，**sha256 与源逐字节相同**（`68fa7f4c…` / `84af6cd6…` / `597515ee…` / `6d0805c2…` / `f1ef0701…` 五对全等）；源文件 mtime `08:15–08:19` **早于**副本 `08:49` ⇒ 无改写迹象（注：`refs/` 不在 git 面内，**无独立逐字节基线**，此为 mtime 级证据，如实标注） | ✅ 证实 |
| 7 | AC-9 面具态「驱动路线」 | 见 §5.4：`n2-driven-mask.json` tick 137 / masked / pack / 11 部件 / `js_errors.total=0`；`n2-desktop-1440x900-masked-driven.png` 存在 | ✅ |
| 8 | 实机 `npc-006.source === 'pack'` | 所有室内/默认机位 `npc_source = "pack"`；对照臂 `setAppearance(null)` ⇒ `control_generic.npc_source = "fallback"` | ✅ |
| 9 | 顶层 provenance 逐字节未改 | **我独立复算** `canonical_sha256({"source_facts":…,"source_fact_map":…})`（`json.dumps(ensure_ascii=False, sort_keys=True, separators=(",",":"))`）= `a0997e45736befc1ebbcf0fa79160b7361a8e8f36e48ade802cd98a8d914da31` **== 期望锚** ✅；顶层 `appearance.*` 旧键仍只有 `["appearance.red_coat","appearance.scarlet_eyes"]` | ✅ |
| 10 | 新增写集「只新增」 | `verify_specs.sh` diff = 单一 hunk `820a821,837` 纯插入、**0 行删除**；`character-refs/*.jpg` = 5 个新文件（`manifest.txt` 208 行含 5 条登记） | ✅ |

---

## §6 · Bug 清单

> 每条 = `编号 | 级别 | 复现命令 | 证据 | 影响 | 建议`

### BUG-1 | **CRITICAL（回归；r3 引入）** | `scene_assert.mjs` 在「声明 masked 但缺 `appearance.mask`」的包上**未捕获崩溃**，导致负例 `N-3b` 不再判红

- **复现命令**（交付树零改动；副本由 r2 负例脚本自建）：
  ```bash
  $ python3 /tmp/n2_sentinel/n2-negatives-r2.py     # 建 /tmp/n2-r2-neg-<ts>/N-3b_mask_missing/02_source（删 npc-006 的 appearance.mask）
  $ cd /tmp/n2-r2-neg-<ts>/N-3b_mask_missing/02_source/v0_skeleton/web && node scripts/scene_assert.mjs
  ```
- **证据**：
  ```
  N3B_EXIT=1
  64: TypeError: Cannot read properties of null (reading 'top_y')
  65-     at …/scene_assert.mjs:970:44
  ```
  输出**没有** `scene_assert: PASS=… FAIL=…` 汇总行（探针只能取到末行 `Node.js v26.3.1`）。
  落点：`scene_assert.mjs:970` `const maskHeightM = round6(maskedFace.mask.top_y - maskedFace.mask.bottom_y);`（同块 `:971`、detail 模板 `:999–1002` 同病；均属 **r3 新增几何块**）。
  **回归证据（r2 自测日志原文）**：`<ws>/03_artisan_self_test.log:782`
  `OK  N-3b_mask_missing_scene_assert: exit=1 :: crash=False | scene_assert: PASS=55 FAIL=1 | PASS mask_data_missing_degrades_explicitly(…)`；同文件 `:794` `all_fired=16/16  not_fired=[]`。
  ⇒ r2 时 `crash=False`、负例判红；**r4 最终树 `crash=True`、负例不判红**。
- **影响**：① 任务书 §3.5 / 必做 D 要求的「r1 8 条 + r2 8 条**逐条仍判红**」**不成立**（实测 15/16）；② `scene_assert.mjs` 自身在 r2 已写明的契约「判据必须变红而**不是崩**」（`:555-556` 注释）在 r3 被破坏；③ 门禁在「声明 masked 无 mask 数据」这一类包上**无法给出判定**（只有堆栈，无 PASS/FAIL 汇总）。
  **范围界定（不夸大）**：交付树本身 `PASS=65 FAIL=0`，**不产生假绿**（exit 仍非 0）；被阻断的是**门禁工具在畸形包上的可判定性**与**一条必需负例的证明力**，不是徐琴形象本身的功能。
  **升级口径**：若验收把「16/16 负例逐条判红」当**硬门禁**（任务书 §3.5 原文口径「缺一即报告不完整」），本条即**阻断**。
- **建议**：在 r3 几何块给 `maskedFace.mask` 加与 `maskReadsHalfFace()` 一致的守卫（缺 mask 时把两条 detail 读数降级为**显式 FAIL 文案**而非解引用），并补一条自证「缺 mask ⇒ 判据红且**不崩**」。改后复跑：`node scripts/scene_assert.mjs`（交付树须仍 65/0）**与** `python3 /tmp/n2_sentinel/n2-negatives-r2.py`（须回到 `all_fired=16/16`）。

### BUG-2 | **MEDIUM（已知缺陷，登记为 N4 的 F8）** | 默认交付取景下**玩家看不到徐琴**（只有盒子）

- **复现**：`python3 /tmp/n2_sentinel/n2-pixel-diff.py --out /tmp/n2_sentinel`；`python3 /tmp/n2_sentinel/color_clusters.py shots/n2-default-wide-daily.png`
- **证据**：`n2-default-wide-daily vs n2-default-wide-masked ⇒ diff=0 bbox=None`；两文件**同一 sha256**（`9fe82f87…d7f7f`）；视口内颜色簇只有 `#f3efe8`（背景 747885 px）与 7 个棕灰盒面，**零**红衣着 / 近黑发簇；读图「No humanoid character is visible … only simple, untextured geometric box-like shapes」。成因：`npc-006` 与 `room-1052`（5×3×5 不透明盒）**同点 (5,0,15)**，默认相机在盒外。
- **影响**：REQ AC-9 的「实机可辨识」在**默认交付取景**下不成立；用户实际打开应用看不到人物形象。
- **建议**：登记为 **N4 的 F8**（任务书 PM 硬约束 ② 已要求）。**本轮不得**用取证机位读数替代或掩盖。

### BUG-3 | **LOW** | AC-9「瞳色」在渲染上与「衣着色」**同色不可分**

- **复现**：`python3 /tmp/n2_sentinel/color_clusters.py shots/n2-obs-indoor-daily.png`
- **证据**：眼睛簇 `#3b0a08`（n=1620，bbox `[547,94,621,119]`）vs 衣着簇 `#3c0a08`（n=56667，bbox `[474,381,698,782]`）——**差 1/255**（源色 `#8b1919` vs `#8f1d1d` 经同一 `luminanceScale=0.6923` 压缩后几乎重合）。读图亦指出「a single dark red used for **both** the facial bars and the entire red garment」。
- **影响**：AC-9 四项中的「瞳色」只有**弱**证据——能看出「面部有一条暗红横条」，但无法据此认出「猩红瞳」这一原著锚点（AC-5 的数据面正确，失的是**可判读性**）。
- **建议**：非阻断。若 N4 要继续提 AC-9 判读强度，可考虑给 `eyes` 与 `garment` 拉开明度/材质差（属设计补全范围，需 architect 口径）。

### BUG-4 | **LOW** | `verify_specs.sh` §17b 标签文本漂移（「6 injected negatives fire」实为 9）

- **证据**：我的 `verify_specs` 输出行 = `PASS NPC appearance contract verified (…; 6 injected negatives fire)`；而 `verify_npc_appearance.py` 的 `probe` 数组实测 = **9** 条（`remove_eyes_color` / `drop_hair_design_fill` / `forged_chr_99` / `mask_number_9` / `top_level_appearance_key` / `drop_referenced_ref` / `build_quadruped` / `mask_missing_while_masked` / `mask_number_string`）。
- **影响**：纯标签可读性；该标签**不参与任何判定**（§17b 只 `jq` 读 `.appearance_ok` / `.probe_ok`）。`06-acceptance-record.md` §25（L567–570）**已显式登记**该漂移并按 L-14 先例不修。
- **判定**：**自报属实、无新增**。建议：登记即止（若要修须动 `verify_specs.sh` 文本，与「0 行删除」纪律冲突）。

### BUG-5 | **LOW** | 静态判据面只覆盖 `character.ts`；`world.ts:564` 注释内含锚点 hex `#8b1919`

- **证据**：`grep -nE '#[0-9a-fA-F]{6}' web/src/scene/*.ts` ⇒ `world.ts:564` 命中 `#8b1919`（在**文档注释**内）；判据 `character_ts_has_no_anchor_hex_literal` 只扫 `character.ts`。
- **影响**：无功能影响（非渲染字面量；`world.ts` 的部件材质取 `part.source_hex`）。仅是判据覆盖面的**口径边界**：未来若有人把锚点色写进 `world.ts` 的**注释外**代码，现判据不会发现。
- **建议**：N4 可把静态判据扩为「`web/src/scene/*.ts` 内**注释外**零锚点 hex」。

### BUG-6 | **LOW** | `spikes/` 内部分取证留档仍是 **r2 时代几何**，易被误读为最终树读数

- **证据**：`readback/n2-default-camera-before.json` / `-after.json`（mtime 10:25）、`readback/n2-obs-camera-baseline.json`（10:04）内的部件读数仍是 r2 几何：`torso size [0.46,0.66,0.26]`、`hair size [0.3,0.34,0.3]`、`coat [0.56,0.86,0.34]`、`arm ±0.30`。最终树（`n2-obs-shots.json`，12:04）为 `torso 0.38 / hair 0.58 / coat 0.38 / arm ±0.24`。
- **影响**：`spikes/**` 非交付面，无功能影响；但同目录内 r2/r4 读数并存，**跨文件引用时容易串轮**（本轮我已在报告内逐处标注来源文件与时刻）。
- **建议**：登记即止；或在 `spikes/n2-appearance/notes/README.md` 补一行「按 mtime 分轮，跨轮读数不可混用」。

### BUG-7 | **LOW** | `spikes/n2-appearance/n2-ac10-probe.py` 在 `--out` 指向工作区外时**崩溃**

- **复现**：`python3 spikes/n2-appearance/n2-ac10-probe.py --out /tmp/n2_sentinel/ac10`
- **证据**：`ValueError: '/tmp/…/n2-ac10-probe-manifest.json' is not in the subpath of '<ws>'`（`pathlib.relative_to`，脚本 L64）。
- **影响**：**非交付面**（spike 工具）；脚本在崩溃**之前**已完成两次校验（probe manifest 已落盘），信息不丢。仅影响「在写集外做只读复现」这一用法（正是我本轮的做法）。
- **建议**：非阻断。若要保留该用法，把 L64/L65 的 `relative_to(WS)` 换成 `try/except` 或 `os.path.relpath`。

**计数：CRITICAL 1 / MEDIUM 1 / LOW 5。**

---

## §7 · 有效性窗口

本报告的全部读数绑定在：**2026-09-24T04:27:52Z（12:27 CST）的那棵树**，其中
- `<ws>/02_source/manifest.txt` = **208 行**，sha256 = `b6c8a8053c32883537aef0a424669f312d951c35bd066ae0c799a9f1ed40bcce`；
- `<ws>/02_source/v0_skeleton/districts/xingfu-xiaoqu/pack.sig`（主包） = `844f7606d5b548517a1af3a052bf882b7e38563297a644bcd70e1bd3dafcb87b`；
- `<repo>` HEAD = `18f9facfc11281f622a6ff7be455a02d5b92ecea`，`git status --porcelain` = 空；
- 关键读数锚：`scene_assert PASS=65 FAIL=0`、`verify_specs PASS=164 FAIL=0 SKIP=0`、`verify_npc_appearance appearance_ok=true probe_ok=true`、顶层 provenance `a0997e45…`、两份 `art-bible.md` sha256 `1d271e59…`。

**任何写入者落地任何文件后本报告即失效，下一轮必须重门禁**（不得复用本报告任何读数）。
`scene_assert` 的判据源码**在交付面内** ⇒ 判据侧改写只由 `manifest.txt` 这一独立机制发现；本报告的「判据全绿」**不等于**「树未被篡改」。

---

## §8 · 覆盖范围声明（**不覆盖**什么，明写）

1. **内核全量 pytest 已完成**（串行，`216 passed in 1289.74s`，exit 0，§D.1）；负载敏感项 `test_pace_is_identical_with_zero_and_two_observers` 在低载串行条件下**通过**。**但仍不覆盖**：内核与渲染层的**交叉面**（本轮未做端到端内核→渲染联调）。
2. **`tsc --noEmit` 未在本轮单独复跑**（§2bis）：以 `scene_assert` / `node --test` / `verify_specs` 全绿作替代读数，**不等于**类型检查通过。
3. **不做深度安全对抗 / 漏洞挖掘**（Raven 的面）：未做 IP 边界对抗、provenance 伪造链、`scan_ip_boundary.py` 绕过尝试、运行时资源耗尽/信号类缺陷。
4. **不做美术质量评价**：本轮口径是「方盒 → 可辨识人物」，**不**宣称写实美术、贴图、动画、体型差异。
5. **不覆盖 AC-9 的「写实可辨识」**：取证机位下**弱可读**（性别偏女性/中性；瞳色与衣着同色不可分）；默认取景下**不可见**（F8）。
6. **未做浏览器实机重跑**：截图由 Artisan 产出（12:03–12:04），我对**产物**做像素/读图/读回核验，**未**自己起 Playwright 重新出图（跑 `serve.mjs` 会写 `spikes/**` ⇒ 越界）。截图与读回的**同源一致性**以 mtime + `n2-obs-shots.json` 的 `shots[]` 清单交叉确认；「截图确实是这一次交付面渲染出来的」这一点**未**用重跑证明。
7. **未覆盖 `02_source` 之外**：`docs/**`、`spikes/**`、`03_artisan_self_test.log` 只读引用，未做独立复跑（除 §E 的登记核验与 §5.4 的产物核验）。
8. **未覆盖负例组之外的畸形输入**：如 `states[].when` 的 `tags_include` / `room_id_in` / `schedule_state_in` 组合（本轮只实测 `target_entity_in`）、`appearance` 出现未知键、`design_note` 长度上界、`chrId` 格式非法（非 `CHR-xx`）等。
9. **`refs/appearance/` 源图无独立逐字节基线**（不在 git 面内），只以 mtime + 副本 sha256 等价作证据（§0bis-6）。
10. **`role-task` 账本未按任务书原样 `start`**（task_id 已被 architect 占用 ⇒ 工具拒），只追加 `progress`；未执行 `step --n`（避免改写 architect 步骤账本）。

---

## §9 · 群播报稿（可直接投递，第一人称）

```
[REQ-20260924-002-deephealing-xuqin-appearance] N2 最终树（r4 之后）功能门禁完成，报告落 04_sentinel_test_report.md。

结论：AC-1~AC-7 我独立复现 PASS；AC-8 是零鉴别力的 GAP（起点即满足）；AC-9 部分达成；AC-10 GAP（两条阻塞我自己复现，确认真不可达）。
计数：CRITICAL 1 / MEDIUM 1 / LOW 5。

CRITICAL 一条：scene_assert.mjs:970 在「声明 masked 但缺 appearance.mask」的包上抛未捕获 TypeError，
r2 的负例 N-3b 因此不再判红（r2 日志里是 crash=False，属 r3 引入的回归），16 条负例实测 15/16。
交付树本身仍 65/0、不产生假绿，但门禁在这类输入上给不出判定。

回归面全绿：scene_assert 65/0、node --test 4/0、verify_specs 164/0/0、内核全量 pytest 216 passed（串行 21 分 29 秒）、
主包锚 844f7606 一致、repo status 空、残渣 0；断言名 REMOVED 为空，且 scene_assert.mjs 与起点 diff 是纯追加、0 行删除/改写（比自报更强）。

另有一条要 PM 知道：默认交付取景下玩家看到的是盒子不是人（两张默认图逐字节相同），
已按硬约束 ② 登记为 N4 的 F8，没有用取证机位绕过。
```
