# 离线内容生产管线规范（`content-pipeline.spec.md`）

对应：REQ **D-0.8 / AC-15**（与 D-0.7 第 2 项**共用同一条管线**，不得另建）、ADR-011。
**权威校验器（authoritative validator，F9 / RR3-13 收口）**：`02_source/v0_skeleton/tools/verify_asset_pack.py`
（**可运行**，非将来时承诺）。本规范内凡涉及资产 / manifest / 许可 / `review_status` / 元数据剥离 /
工作流受管 / 运行时零生成的校验，**一律**以它为准（见 §7）。

## 1. 唯一一条管线（四步，顺序不可交换）

```
① 生成（离线） → ② 校验（许可检查 + 内容寻址 + schema 校验） → ③ 人工过审 → ④ 收编进 district pack
```

### ① 生成（离线，允许云 / API；运行时禁止）

- 命令（V0 程序化占位资产，真跑过）：
  `python3 tools/make_placeholder_asset.py assets-sample/placeholder-001.png`
  workdir：`<ws>/02_source/v0_skeleton`　期望 exit：**0**
- 生成式模型（图像 / 音频）在本机可用时同样在此步；3D / 视频必须离线云或 API。
- **失败处置**：生成失败即中止，不产出半成品；不得把「重试到出图」当成资产来源。

### ② 校验（**必须有执行体**）

- 命令（正例，真跑）：
  `python3 v0_skeleton/tools/verify_asset_pack.py --pack v0_skeleton/assets-sample --manifest v0_skeleton/assets-sample/asset.manifest.sample.json --license-table asset.license.table.data.json --runtime-tree v0_skeleton`
  workdir：`<ws>/02_source`　期望 exit：**0**
- 校验器**至少拒收 6 类**（每类都有真跑负例，见 `spikes/s6-asset-pipeline/`）：

  | 类 | reason code | 负例 |
  |---|---|---|
  | ① 资产无 manifest 条目（含「合法图片改名 `.txt` 放进 pack」） | `A1_UNMANIFESTED_ASSET` | `logs/n1_unmanifested.log`、`logs/n5_renamed_txt.log` |
  | ② `license` 与 `source_model` 不一致 / 非白名单（default-deny） | `A3_LICENSE_MODEL_MISMATCH`、`A3_UNKNOWN_MODEL_DEFAULT_DENY`、`A3_NON_COMMERCIAL_SOURCE` | `logs/n2_license_selfdeclared.log` |
  | ③ `content_hash` 缺失 / 格式非法 | `A4_BAD_CONTENT_HASH` | `logs/n3_hash_missing.log`、`logs/n3b_hash_malformed.log` |
  | ④ `review_status != adopted` | `A5_NOT_ADOPTED` | `logs/n4_not_adopted.log` |
  | ⑤ 衍生来源传递闭包命中非白名单 / 父资产不在库 | `A6_DERIVED_FROM_DENIED_SOURCE`、`A6_PARENT_NOT_IN_LIBRARY` | `logs/n6_derived_denied.log`、`logs/n6b_parent_missing.log` |
  | ⑥ PNG 未剥离生成器元数据 | `A7_GENERATOR_METADATA_PRESENT` | `logs/n7_metadata_present.log` |

  另有 `A2_DANGLING_MANIFEST_ENTRY`（悬空条目）、`A8_*`（工作流受管登记）、`A9_RUNTIME_GENERATION_PATH`（运行时零生成）。
- **失败处置**：拒收 + 记录 reason code + 资产不进 pack；**不得**「先收编后补 manifest」。
- `asset.manifest.schema.json` 层同样强制：未剥离生成器元数据（`generator_metadata_stripped=false`）的分支
  在 schema 层**不可满足**（负例 `logs/n9_schema_negative.log`）。

### ③ 人工过审

- 命令（结构断言）：
  `jq -e '.assets[] | select(.review_status=="adopted" and (.review.reviewer|length>0) and (.review.reviewed_at|length>0))' <manifest>`
  workdir：`<ws>/02_source`　期望 exit：**0**
- 失败处置：退回 `reviewed`，不得把未过审资产标 `adopted`。

### ④ 收编进 district pack

- 命令（签名 + 逐文件比对，真跑）：
  `python3 v0_skeleton/tools/pack_sign.py v0_skeleton/districts/xingfu-xiaoqu` 然后
  `python3 v0_skeleton/tools/verify_pack.py v0_skeleton/districts/xingfu-xiaoqu`
  workdir：`<ws>/02_source`　期望 exit：**0**
- 失败处置：pack 校验非 0 即不得发布；不得手改 `pack.sig` 迁就文件。

## 2. 运行时零生成（强制约束 + 可检查判据）

- **约束**：运行时（内核 / 会话层 / 渲染层）**不得存在任何生成调用路径**；运行时只加载**已收编**资产。
- **可检查判据（静态扫描，真跑）**：
  `python3 v0_skeleton/tools/verify_asset_pack.py --zero-generation-scan v0_skeleton`
  workdir：`<ws>/02_source`　期望 exit：**0**（命中 `import mflux` / `import diffusers` / `import torch` / `stable_diffusion` / `txt2img` 等即非 0）。
  - 扫描面：**代码文件**（`.py/.js/.ts/.mjs`）；JSON 是数据，其模型引用由工作流校验（A8）负责。
  - **精确排除项（逐条列明，禁止宽泛通配）**：仅排除 `verify_asset_pack.py`（校验器自身按构造包含模式字面量）。
  - 反例自证：注入 `from diffusers import ...` 后必须非 0（`logs/n10_zero_gen_negative.log`）。
- 该扫描**不**覆盖内容层数据文件（district pack 的 JSON 是**离线**产物，不属于运行时调用路径）。

## 3. 许可与来源（与 ADR-011 / `06` L14 一致）

- `license` 白名单枚举 + `(source_model, model_version)` **查表绑定**，未知模型 **default-deny**。
- 云 / API 产出必须 `provenance.self_reported=true` 且 `verification_status=self_reported`（**不得**标「已核验」）——
  按 RA-2 先例登记为**已声明边界**。
- 不可商用权重（FLUX.1-**dev**、MusicGen 权重 CC-BY-NC 等）**禁止出现在任何交付产物中**（含 manifest / 示例 / 截图）。

## 4. ComfyUI 工作流受管登记

- 工作流 JSON 是**受管产物**：必须登记 sha256（`workflow.sha256`），且其 `referenced_models` 必须过许可表。
- 命令：
  `python3 v0_skeleton/tools/verify_asset_pack.py --pack <pack> --manifest <manifest> --license-table asset.license.table.data.json`
  —— A8 会校验 sha256 一致与非白名单 checkpoint 拒收（负例 `logs/n8_workflow_nonwhitelist.log`）。
- ComfyUI 为 **GPL-3.0**：V0 只允许「**独立进程 + 产物文件**」，不得链接进产品（`asset.license.table.json` 的
  `comfyui_workflow_policy.link_policy = separate_process_only`）。

## 5. 内容寻址口径

- `content_hash = sha256:<hex64>`；`content_hash_basis` 必须写明取「**解码后像素 + 规范化规则**」还是「**文件字节**」。
- **推荐**解码后像素（换 EXIF / 重编码不产生新哈希）；V0 示例取 `file_bytes`，**该口径记 GAP**（未实现像素解码器），
  见 `09_risks_open_questions.md` 未决项。
- 入库前**必须**剥离 PNG `tEXt` / `iTXt` / `zTXt` 生成器元数据（或只保留白名单 chunk），并由 A7 扫描门禁兜底。

## 6. 与 AC 的对应

- **AC-15**：本文件 = 管线规范；`asset.manifest.schema.json` + `asset.license.table.*` = 契约；
  `art-bible.md` = 风格约束；`spikes/s6-asset-pipeline/` = 真跑证据。
- **AC-6 / AC-12**：收编进 pack 走既有 `pack_sign.py`（签名）→ `verify_pack.py`（**pack.sig 完整性**）
  校验路径；资产/manifest 面的校验由 `verify_asset_pack.py` 承担（§7）。

## 7. 权威校验器与「非权威」脚本的边界（F9 / RR3-13 收口，必读）

| 脚本 | 角色 | 权威面 | 不权威面（不得据此宣称已校验） |
|---|---|---|---|
| `v0_skeleton/tools/verify_asset_pack.py` | **资产管线权威校验器** | 资产/manifest 覆盖、许可查表 default-deny、`content_hash` 格式、`review_status`、`derived_from` 闭包、PNG 生成器元数据、工作流受管登记、运行时零生成扫描 | —— |
| `v0_skeleton/tools/verify_pack.py` | **`pack.sig` 完整性校验器（非资产权威）** | `pack.sig` 与盘上文件逐条 sha256/字节数一致；**可执行文件双判据**（后缀名 + 内容魔数） | **不是**资产许可 / `review_status` / `content_hash` 语义的校验者；本规范**不**把它当作资产管线校验器引用 |
| `v0_skeleton/tools/aesthetic_check.py` | 美学数值约束校验器 | 色板 / 光照 / 材质 / 镜头 / 音频 / UI 的取值区间 | 不判「氛围达成」（AC-11 仍 GAP） |

- **RM-13 的两半处置（逐条）**：
  1. 「`verify_pack.py` **只按后缀名拦**」→ **已修掉**（round 3 · 修复迭代 1）：判据升级为
     **后缀名 + 内容魔数**（ELF / PE / Mach-O / shebang / Python 字节码），改后缀名不再能绕过。
     证据：`spikes/s6-asset-pipeline/logs/` 的 RM-13 自证负例（改名 `.png` 的 ELF → 非 0）。
  2. 「`pack.sig` **不是签名**」→ 沿用**已声明边界**（`district.pack.spec.md` §2；V0 无外部锚定），
     **不得**写成「pack 内容已保证未被篡改」。
- 规范引用纪律：新增校验步骤时，若属资产/manifest 面 → 引用 `verify_asset_pack.py`；
  仅当属 `pack.sig` 完整性面才引用 `verify_pack.py`。两者**不得**互相替代。
