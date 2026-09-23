# DeepHealing · 文档

赛博世界沙盒（3D 世界 / 自主进化 NPC / 参与·观察双模式）的架构与契约文档。

## 状态：架构冻结（有条件通过）

- 冻结轮：`REQ-20260921-002`（契约 rev5）
- 验收判定：**有条件通过（PASS with findings）**；**CRITICAL = 0**
- 验收记录：`architecture/06-acceptance-record.md`（含 PM 独立复验清单与逐 AC 判定）
- **本目录是「架构冻结 + 接口骨架」，不是可运行产品**（见下方诚实边界）

## 目录

    architecture/
      01-architecture-design.md          七层架构、冻结契约表、验证计划
      02-open-source-matrix.md           12 层开源选型矩阵（每层「先调研后裁决」）
      03-adr.md                          12 条 ADR（架构决策记录）
      04-v0-plan.md                      V0 实施计划（文件级任务 + RED 用例 + 工时）
      05-risks-and-open-questions.md     风险登记与未决问题
      06-acceptance-record.md            PM 逐 AC 终验记录（含 PM 独立取证与诚实边界）
    specs/                               冻结契约：JSON Schema + 规格说明
      capability.schema.json             原子能力注册表（D-0.6 能力槽位四类 provider）
      capability.time-budget.spec.md     时间预算语义（D-0.9）
      cassette.format.md / .schema.json  模型调用录制/回放格式与完整性边界
      district.pack.schema.json / .spec  街区内容包（数据驱动扩展，不改内核）
      events / snapshot / world.schema   事件链、检查点、世界模型契约
      session.protocol.schema.json       双模式会话协议与错误码
      intervention.policy.schema.json    参与模式介入护栏（预算/冷却/审计）
      asset.manifest.schema.json         资产一等公民（内容寻址 + 许可 + 生成来源）
      asset.license.table.json           许可白名单（机器可判，default-deny）
      art-bible.md / content-pipeline.spec.md / worldmodel.adapter.spec.md
                                         美学规范、离线内容管线、世界模型接入

## 三条核心裁决（用户明示要求）

1. **不造轮子（D-0.5）**：每层先做开源调研与选型裁决；自研仅限开源无法覆盖的差异化内核。
2. **模型能力经 API 作为原子能力补充（D-0.6）**：能力槽位由四类 provider（远程模型 API / 本地模型 /
   确定性规则 / 录制回放）填充；**新增能力不改内核代码**（已由 PM 以「纯数据加能力、内核指纹逐字节不变」独立验证）。
3. **世界模型接入但不做权威（D-0.7）** / **AIGC 素材离线生产 + 许可白名单（D-0.8）** /
   **时间预算只钉语义不钉毫秒数（D-0.9）**。

## 诚实边界（不得被读成已达成）

- **本轮交付 = 架构冻结 + 接口骨架**。`kernel run/replay/validate`、`pack sign` 仍是**接口桩**
  （`NotImplementedError` / `E_NOT_IMPLEMENTED`），**不是可运行产品**。
- **`local_model` provider 未真跑**（本机无本地模型服务）——只设计槽位。
- **GAP（未做/未实测，逐项登记于 `architecture/05-risks-and-open-questions.md`）**：
  1. **AC-13 remote 类等价性**：远端 `memory.reflect` 输出不符 `output_schema` ⇒ 每次
     `on_invalid_schema` 降级。**未改契约迁就远端输出**，如实记 GAP；V0 需先修远端结构化输出后重取证据。
  2. **AC-11「治愈系氛围达成」未证实**：渲染真跑通过（77 帧 / WebGL2），但画面为极简占位
     （无天空、无可见雾、无可见投影）——配置为真 ≠ 效果为真。
  3. **AC-14/AC-15 的实现面**：本机无生成式世界模型可跑；素材生成 spike 未做；成本未实测；像素口径未实现。
  4. **AC-6**：`kernel validate` 未实现；第二街区真跑未做。
  5. **AC-4**：限流 / 冷却 / 影响预算未实现（权限判定与协议已冻结）。
- **不得宣称「回归 17 项全 0」**：一键回归脚本当前 **exit 1**（唯一失配为计数口径缺陷，非产品缺陷）。
- **D-0.9 声明值量级为受污染窗口下的临时值**（实测 p95 ≈ 43s 系网络拥塞所致），
  **不是产品运行值**，V0 需在干净窗口重标。

## 开放项（需需求侧/产品决策，不阻断架构冻结）

| # | 开放项 | 归属 |
|---|---|---|
| 1 | V1 实验门禁 G4 单位成本阈值（每 1000 次 imagine 调用 / 每生成分钟视频） | 需求侧给值 |
| 2 | 门禁 provider 数量上界（单能力清单可声明 N 个 provider ⇒ N 次 spawn，有硬超时） | 产品决策 |
| 3 | 远端结构化输出修复（AC-13 remote 面重取等价性证据） | V0 实施 |
| 4 | `imagine.predict` 的 `remote_api` impl 指针悬空 | V0 实施 |
| 5 | `R3F3-1`：内嵌 `output_schema` 的 `$ref` 悬挂/成环 ⇒ 崩溃被压成不透明兜底记录（fail-closed，无绕过） | 下一轮收口 |

## 证据与复现

架构冻结轮的全部真跑证据（spike 源码、日志、门禁脚本、冻结快照）位于开发工作区，
不在本仓库内。复现方式：

- **PM 独立验收器**（`pm_verify_ac2.py` / `pm_verify_ac13.py` / `check_bash_multibyte.py`）
  与冻结快照校验器（`make_freeze_snapshot.py --verify`）用于对交付态做第三方复算。
- 各 spike 门禁脚本支持 **隔离复跑**（`--out <dir>` / `DEEPHEALING_SPIKE_OUT`），
  **审阅方复跑一律写隔离目录**，不覆盖被冻结的交付证据。
