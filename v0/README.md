# v0 —— DeepHealing V0 垂直切片（里程碑 M1：确定性内核）

本目录是 V0 的**可验证交付单元**。M2 及后续里程碑在**同一棵树上继续生长**（不另起目录）。

## 这里有什么

```
v0/
  02_source/                      产品源（规格 + 骨架代码，111 文件）
    *.schema.json / *.spec.md     18 份冻结契约（与 docs/specs/ 逐字节相同）
    verify_specs.sh               契约与交付面自校验（自定位，可在任意路径运行）
    manifest.txt                  02_source 下每个文件的清单（覆盖检查的判据）
    v0_skeleton/
      kernel/                     确定性内核（tick / ECS / RNG / 事件 / 快照 / CLI / 注册表）
      districts/xingfu-xiaoqu/    幸福小区内容包（数据驱动）
      capabilities/               原子能力声明
      tools/                      校验与标定工具
      web/ session/ assets-sample/   后续里程碑的占位
  spikes/                         内核测试套件依赖的产物（必须随交付包一并提供）
    kernel-baseline/              内核源码指纹基线
    s5-latency-calibration/       时间预算标定产物 + 三份冻结物
  06_v0_m1_self_test.md           逐 AC 判定书（测试会读取其中的真实调用计数）
  V0_M1.sha256                    冻结时刻的交付面清单（**证据**，见下）
  SEED.sha256                     起点溯源（从上一里程碑播种时的聚合哈希）
```

## 怎么验证

```bash
# 1) 契约与交付面自校验
cd v0/02_source && bash verify_specs.sh --quiet
#    期望：verify_specs: OK (95 checks passed, 0 skipped)

# 2) 内核测试套件
cd v0/02_source/v0_skeleton/kernel
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
#    期望：71 passed, 10 skipped
#    （10 条 skip 属后续里程碑 W3/W7 的范围，带明确理由跳过，不是掩盖失败）

# 3) 端到端：跑一次世界 → 校验日志 → 回放比对
mkdir -p /tmp/dh
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel run \
    --pack districts/xingfu-xiaoqu --seed 20260921 \
    --events /tmp/dh/e.jsonl --snapshot-every 50 --ticks 300
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel verify \
    --events /tmp/dh/e.jsonl --pack districts/xingfu-xiaoqu \
    --expected-hash "$(tail -1 /tmp/dh/e.jsonl | python3 -c 'import json,sys; print(json.load(sys.stdin)["hash"])')"
#    期望：exit 0
```

> ⚠️ **`verify` 必须带 `--expected-hash`（链外锚点）。**
> 不带锚点时 `exit 0` 只证明「确定性一致」（链自洽 + 检查点与重放一致 + 事件流与重放一致），
> **不证明「日志未被篡改」**：无密钥哈希链不是真实性保证。已实测：截断日志 + 改写 `plan_ticks` +
> 重算整链 ⇒ 产出真日志的**自洽前缀**，无锚点时 `verify` 仍 `exit 0`。
> 该强度边界是**已声明**的（见 `02_source/cassette.format.md` 的 `FROZEN-CASSETTE-INTEGRITY-1`），
> 不是未知缺陷——但任何把「`verify` exit 0」读成「未被篡改」的下游结论都是错的。

## 已知限制（如实记录，未粉饰）

1. **标定缓存与位置耦合**：`spikes/s5-latency-calibration/calibration.registry.json` 是**派生缓存**，
   记录了三个冻结文件的**绝对路径 + mtime**。因此把它复制/克隆到新路径后，
   `tests/test_calibrate_latency.py::test_registry_is_idempotent` **首次运行会失败**（缓存过期，首跑重写）。
   **补救**：在该位置跑一次 `python3 tools/calibrate_latency.py registry` 重新同步，套件即恢复 71 passed。
   内容锚（三个冻结文件的 sha256）不随位置变化，完整性未受影响（工具会与硬编码常量比对，不一致即 `exit 1`）。
   *已登记为待修缺陷：把缓存改为位置/时间无关（只存内容哈希）——需要连同 `V0_M1.sha256` 一起重新快照。*

2. **`V0_M1.sha256` 是冻结时刻的证据，不是本仓库内的完整性检查**。它覆盖当时工作区里的**全部**交付面
   （276 条），包含仅用于 A/B 证据、**未随本目录提供**的沙箱（`spikes/red/**` 等 87 条）。
   故在本仓库里对它跑 `shasum -c` 会报缺失；这是预期行为。本目录内的完整性检查是第 1 条里的 `verify_specs.sh` 与内核测试套件。

3. **时间预算标定判据 ③ 不可重复**（AC-M1-6 记为 GAP）：同一份数据、同一批声明值、同为 `--runs 10`，
   相邻三次测量给出 adopted 降级率 `0.50`（越界）/ `0.20` / `0.10`；根因是环境抖动 **叠加** 冻结区间的口径塌缩
   （`ceil_to(50,p95) == ceil_to(100,p95) == 1300`，七个能力全部塌缩，「松一档」的前提不成立）。
   **未重采样、未调参、未改任何声明值。**

4. **`local_model` provider 未真跑**：本机无本地模型服务，只有槽位设计。不冒充已跑。

5. **范围**：本轮交付 = **确定性内核可运行**（`run` → 事件日志 → `replay` → `verify` → `validate` → `pack sign`）。
   能力注册表运行时、规则层与预算、记忆层、双模式会话、渲染层、观测层属后续里程碑。

## 溯源

| 项 | 值 |
|---|---|
| 需求书 | `REQ-20260921-003-deephealing-v0-m1`（上游 `REQ-20260921-002` 架构冻结） |
| 验收 | **有条件通过**：8 条 AC 中 6 PASS / 1 GAP / 1 分列两判据均 PASS；**CRITICAL 全程为 0**；无 FAIL |
| 冻结计划 | `docs/architecture/04-v0-plan.md`（13 工作包 / 4 里程碑 M1~M4） |
| 契约副本 | `docs/specs/` 是这 18 份契约的**发布视图**；本目录 `02_source/` 是**可自校验的源**（两者逐字节相同，已核） |
