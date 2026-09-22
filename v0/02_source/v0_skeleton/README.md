# V0 目录骨架（`02_source/v0_skeleton/`）

本目录是**架构冻结轮的目录骨架**：真实目录树 + 非空 stub 文件（接口签名与不变量已冻结，
实现属于 V0 实施范围，见 `08_v0_plan.md` 的文件级任务清单）。它**不是**可运行产品。

## 目录与分层对应

| 目录 | 层 | 说明 |
|---|---|---|
| `web/` | L1 渲染层 | three.js + TS + vite；只消费 snapshot/delta/event，零业务逻辑 |
| `session/` | L2 会话传输层 | Node 进程，**非权威**；只搬运与鉴权，不持世界状态真值 |
| `kernel/` | L3 世界内核 + L4 认知 + L6 记忆 | Python 3.13 包 `deephealing_kernel`；唯一权威 |
| `capabilities/` | L4 数据面 | 原子能力声明（`*.capability.json`）+ `pins.json`；**数据驱动发现** |
| `districts/xingfu-xiaoqu/` | L5 内容层 | 样例 content pack（含 `pack.sig`） |
| `tools/` | 离线工具 | canonical JSON、pack 签名/校验、美学数值校验、duckdb 查询 |

> `session/` 在 01 设计 §5 列举的五个目录之外新增，用于承载 L2 层；01 用「含」表述，非封闭列表。

## 三条硬边界（骨架阶段即生效）

1. **模型调用只允许出现在 `kernel/deephealing_kernel/providers/`**：业务模块一律经
   `CapabilityRegistry.invoke(slot, ...)`；Sentinel 会扫描业务模块中的 HTTP/SDK 调用。
2. **权威写入只在 `kernel` 的 tick 执行阶段**：`web/` 与 `session/` 均无世界状态写路径。
3. **内容层只有数据**：`districts/**` 内出现 `.py/.js/.sh` 等可执行文件即 `E_PACK_INVALID`。

## 本地自检（骨架阶段即可跑，无需装依赖）

```bash
cd <workspace>/02_source
bash verify_specs.sh          # jq 全量解析 + pack.sig 逐文件比对 + 骨架完整性
```

## 已冻结的 RED 用例（实现完成后应转 GREEN）

- `kernel/tests/test_determinism_replay.py`（AC-2：双跑哈希一致 + 两个非确定性负例）
- `kernel/tests/test_capability_registry.py`（AC-13：数据驱动发现 / provider 切换 / cassette fail-closed）
- `kernel/tests/test_pack_validate.py`（AC-6：第二街区不改内核代码）
- `kernel/tests/test_observe_mode_readonly.py`（AC-4：observe 上行被拒）
- `session/test/session.test.js`（AC-4：双模式权限，`node --test test/session.test.js` 可跑的部分已可执行）
