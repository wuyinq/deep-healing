# district pack 规范（内容层冻结）

配套 schema：`district.pack.schema.json`（`$defs/packManifest`、`$defs/packSig`、`$defs/worldSeed`）。
目标：**小区 = 数据驱动可加载单元**；新增第二街区（甚至第三街区）**不改内核代码**（AC-6）。

## 1. 目录结构（冻结）

```
districts/<pack_id>/
  pack.json              # 清单：id/version/engine_range/bounds/author/license/entrypoints/portals
  world.seed.json        # 初始世界：seed / constants / entities / weather（须过 world.schema.json）
  buildings/*.json       # 楼栋、房间、可交互物（含导航节点）
  npcs/*.json            # 住户档案：需求权重、日程引用、关系种子、创伤/暗面标记
  tasks/*.json           # 分级任务定义（状态机 + adaptation_rules）
  schedules/*.json       # 日程表（数据驱动，非代码）
  assets/manifest.json   # 资产位（占位/程序化/可替换）+ 治愈系美学数值约束
  pack.sig               # 完整性清单（sha256 列表，不含自身）
```

- 目录名必须等于 `pack.json.id`。
- 所有路径相对 pack 根目录，POSIX 分隔符，**禁止** `..` 或绝对路径（防越界读取）。
- pack 目录内不得出现可执行代码（`.py`/`.js`/`.sh` 一律拒绝加载）——内容层只有数据。

## 2. 校验顺序（冻结，失败即 `E_PACK_INVALID` 且非 0 退出）

1. `pack.json` 过 `$defs/packManifest`；
2. `engine_range` 与内核契约版本比对（不满足 → 拒绝，防新数据配旧内核静默出错）；
3. 每个 `entrypoints` glob 至少命中 1 个文件（空 glob = 失败，不许静默跳过）；
4. 每个数据文件过对应 schema（`world.seed.json` → `world.schema.json`；`assets/manifest.json` → 美学数值约束）；
5. `pack.sig` 逐文件 sha256 比对（多文件/少文件/哈希不符 任一即失败）。

复跑命令（第三方可照抄）：

```bash
cd <workspace>/02_source
jq . v0_skeleton/districts/xingfu-xiaoqu/pack.json            # exit 0
bash verify_specs.sh                                           # exit 0（含 pack.sig 比对）
```

## 3. 新增第二街区（不改内核代码）迁移路径

1. 复制 `districts/xingfu-xiaoqu/` → `districts/<new-id>/`；
2. 改 `pack.json.id` / `version` / `display_name` / `bounds_mm`；
3. 填 `world.seed.json`、`buildings/*.json`、`npcs/*.json`、`tasks/*.json`、`schedules/*.json`；
4. 重新生成签名：`kernel pack sign districts/<new-id>`（只改 `pack.sig`）；
5. `kernel validate --pack districts/<new-id>` → exit 0；
6. `kernel run --pack districts/<new-id>` 启动；
7. 跨区连接**只在 `pack.json.portals[]` 声明**：内核按 portals 数据建边（`to_pack_id` + `to_entity`），**不新增代码分支**。

**判据（AC-6）**：改动清单里只有 `districts/**`（新增 pack 目录）+ 可选 `capabilities/**` 数据文件；内核源码目录（`kernel/`）零改动。证据形式：`git status --porcelain`（workspace 内）/ 文件 mtime 对比 / `pack.sig` 重签记录。

## 4. 跨区连接的数据契约

`portals[]` 每条声明 `{id, from_entity, to_pack_id, to_entity, bidirectional, traversal_cost_ticks}`。

- 内核加载时把 portals 转成世界内的边（实体 `kind=portal`），移动与寻路只读该数据。
- `to_pack_id` 指向的 pack 未加载时：边保留但标记 `inactive`（不报错、不崩），加载后自动激活 —— 这样「先做第一街区、后加第二街区」不需要改代码。
- 跨区不共享 RNG：跨区移动不消耗对方 stream，避免新增街区扰动既有 `state_hash`（AC-2 的确定性要求）。

## 5. assets/manifest.json 与治愈系美学约束（AC-11）

每个资产位声明：

| 字段 | 约束 | 说明 |
|---|---|---|
| `id` / `kind` | 必填 | 资产位标识与类型（prop/material/audio/texture） |
| `source` | `placeholder` \| `procedural` \| `authored` | V0 以占位/程序化为主，可替换 |
| `palette` | HSL：`saturation ≤ 45%`；色相落在 20°–60° 或 180°–210° | 夜间场景高饱和点缀色 ≤ 2 |
| `roughness_range` | `[min, max]` 且 `min ≥ 0.6` | 材质粗糙度偏高，镜面弱 |
| `audio_bed` | `ambient_lowfreq` \| `none` | 无突发高频刺耳音效 |
| `license` | 枚举（同 pack license） | **禁止** GPL 系资产进运行时 |

数值超界即校验失败（工具化判据，不依赖主观评价）。

## 6. 版本与回滚

- 内容包独立版本号；`engine_range` 声明兼容的内核契约区间。
- 内容变更只需重签 `pack.sig`；回滚 = 切回旧 pack 目录版本（内核代码不动）。
- 一个内核实例同时只加载一个主 pack（跨区经 portals），避免「多 pack 状态合并」的确定性复杂度（V0 冻结）。

## 7. `worldview.json`（M3 新增，ADR-016）

- **落点**：`districts/<pack_id>/worldview.json`（pack 根），经 `pack.json.entrypoints.worldview` 登记；
  `entrypoints` 因此由 6 键扩为 **7 键**，`district.pack.schema.json` 的该键已进 `required`
  （**两个 pack 都必须有**，否则第二街区 load 失败）。
- **契约**：`02_source/worldview.schema.json`（draft 2020-12，与 `district.pack.schema.json` 同级）。
  字段：`schema_version` / `pack_id` / `tone.{surface,underneath}.{light_k,ambient_ratio,saturation_pct}` /
  `anomalies[]`（`id` / `at_entity` / `kind` / `surface_read` / `underneath_read` / `reveal_at_tick`）/
  `fault_lines[]`（`id` / `about` / `kind` / `repair_via` / `repaired_state`）。
- **禁止形容词**：每个对象 `additionalProperties:false`，任何形容词键（如 `mood` / `feeling`）都会被拒。
- **数值边界**（在 `art-bible.md` 之内，不推翻）：`light_k` 3200–5200；`ambient_ratio` 0–0.6（表层 ≥0.25）；
  `saturation_pct` ≤ 45。深层态 = **同一色板降明度**：`saturation_pct(underneath) ≤ saturation_pct(surface)`。
- **同一几何两态**：两态**共用同一份几何数据**（顶点数 / 实体 id 集合逐项相同）；禁止第二张地图、第二个 pack、换相机。
- **校验**：`verify_specs.sh` 对**两个** pack 的 `worldview.json` 真跑 `worldview.schema.json` 校验
  （`v0_skeleton/tools/schema_validate.py`，引擎 jsonschema）。
- **变更即重签**：改数据后两个 pack 都要 `kernel pack sign <dir>`。

## 8. `narrative_hooks` → `healing_face` / `hidden_face`（M3 兼容/迁移说明，ADR-016）

- **加字段、不删字段**：`npcs/*.json` 保留既有 `narrative_hooks: [string]`，**新增**
  `healing_face: [string]`（表层读法：这个人在做的好事）与 `hidden_face: [string]`（深层读法：没人注意到的那一面）。
- **旧消费方零改动**：M3 复核的 `narrative_hooks` 消费点是**内容包数据文件自身**；
  内核 / 会话层 / 渲染层 **0 命中消费**（`grep -rn narrative_hooks 02_source` 的命中全在 `districts/**/npcs/*.json`）。
  因此兼容风险面只有「内容包校验 + 未来消费者」。
- **校验**：`verify_specs.sh` 断言**每个** NPC 同时具备非空 `healing_face` 与 `hidden_face`，且 `narrative_hooks` 仍在。
  负例：删掉任一 NPC 的 `hidden_face` ⇒ 该断言**必须红**（隔离副本实测）。
- **渲染语义**：表层态显示 `healing_face`，深层态显示 `hidden_face`；两者**不是**两个 pack、也不是两份数据。
