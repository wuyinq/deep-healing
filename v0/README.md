# v0 —— DeepHealing V0 垂直切片（里程碑 M1 + M2）

本目录是 V0 的**可验证交付单元**。里程碑在**同一棵树上继续生长**（不另起目录）。

## 这里有什么

```
v0/
  02_source/                      产品源（规格 + 骨架代码，139 文件）
    *.schema.json / *.spec.md     18 份冻结契约（与 docs/specs/ 逐字节相同）
    07_adr.md                     架构决策记录：冻结 12 条 ADR 逐字 + ADR-13/14/15（M2 新增）
    verify_specs.sh               契约与交付面自校验（自定位，可在任意路径运行）
    manifest.txt                  02_source 下每个文件的清单（覆盖检查的判据，138 条）
    v0_skeleton/
      kernel/                     确定性内核 + 能力注册表 + 四类 provider + 规则层 + 预算 + 记忆层
      districts/xingfu-xiaoqu/    幸福小区内容包
      districts/xingfu-xiaoqu-north/   第二街区（M2 新增：纯数据驱动，零内核改动）
      capabilities/               原子能力声明（含 relation.infer@1.0.0）
      tools/                      校验与标定工具
      web/ session/ assets-sample/   后续里程碑的占位
  spikes/                         内核测试套件依赖的产物 + 里程碑真跑证据
    kernel-baseline/              内核源码指纹基线（实现前快照）
    s5-latency-calibration/       时间预算标定产物 + 三份冻结物
    s8-registry/ s9-rules/ s10-memory/ s11-pack2/   M2 真跑 spike（仅 V0_M2 冻结面条目）
  06_v0_m1_self_test.md           M1 逐 AC 判定书（内核测试会读取其中的真实调用计数）
  06_v0_m2_self_test.md           M2 逐 AC 判定书
  03_artisan_self_test.log        M1 + M2 实现自测日志
  V0_M1.sha256 / V0_M2.sha256     各里程碑冻结时刻的交付面清单（**证据**，见下）
  SEED.sha256                     起点溯源（从上一里程碑播种时的聚合哈希）
```

## 怎么验证

```bash
# 1) 契约与交付面自校验
cd v0/02_source && bash verify_specs.sh --quiet
#    期望：verify_specs: OK (110 checks passed, 0 skipped)

# 2) 内核测试套件
cd v0/02_source/v0_skeleton/kernel
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider
#    期望：132 passed, 4 skipped
#    （4 条 skip 属后续里程碑 W7/W9 范围，带明确理由跳过，不是掩盖失败）

# 3) 端到端：跑一次世界 → 校验日志 → 回放比对
mkdir -p /tmp/dh
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel run \
    --pack districts/xingfu-xiaoqu --seed 20260921 \
    --events /tmp/dh/e.jsonl --snapshot-every 50 --ticks 300
PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel verify \
    --events /tmp/dh/e.jsonl --pack districts/xingfu-xiaoqu \
    --expected-hash "$(tail -1 /tmp/dh/e.jsonl | python3 -c 'import json,sys; print(json.load(sys.stdin)["hash"])')"
#    期望：exit 0；925 事件 / 6 检查点 / chain_tail baecca92… / state_hash 9a4ae3da…
```

> ⚠️ **`verify` 必须带 `--expected-hash`（链外锚点）。**
> 不带锚点时 `exit 0` 只证明「确定性一致」（链自洽 + 检查点与重放一致 + 事件流与重放一致），
> **不证明「日志未被篡改」**：无密钥哈希链不是真实性保证。已实测：截断日志 + 改写 `plan_ticks` +
> 重算整链 ⇒ 产出真日志的**自洽前缀**，无锚点时 `verify` 仍 `exit 0`。
> 该强度边界是**已声明**的（见 `02_source/cassette.format.md` 的 `FROZEN-CASSETTE-INTEGRITY-1`），
> 不是未知缺陷——但任何把「`verify` exit 0」读成「未被篡改」的下游结论都是错的。

## M2 落盘口径（重要，审计用）

1. **落盘范围 = `V0_M2.sha256` 冻结面**（238 条：`02_source/**` 139 + `spikes/**` 97 +
   `03_artisan_self_test.log` + `06_v0_m2_self_test.md`）。
   工作区里 `spikes/**` 的 **scratch 目录**（`smoke-out-*` / `*-scratch` / `digest-scratch` /
   `u11-legacy-tools` / `p4-scratch/revert-*` 等，约 500 文件）**不在冻结面内，未随本仓库提供**：
   它们是过程性中间产物，且 `u11-legacy-tools` 携带**修复前**的 `verify_pack`/`pack_sign` 副本
   （已登记为存在符号链接逃逸缺口），不宜进交付仓库。
2. **`V0_M2.sha256` 原样落盘（保持冻结真相）**：其 `02_source/v0_skeleton/kernel/tools/calibrate_latency.py`
   一条记录的是 **M2 拿到的输入** `e30be65b…`，而本仓库该文件是 **M1 后置修复版** `23fed40d…`
   （内容锚定，修掉位置耦合）。⇒ 在本仓库里对 `V0_M2.sha256` 跑 `shasum -c` 是
   **237 OK / 1 FAILED**，**那 1 条 FAILED 是预期行为、不是 M2 缺陷**（沿用 M1 先例：
   清单保持冻结真相，divergence 文档化）。
3. `spikes/s5-latency-calibration/calibration.registry.json` 是**派生缓存**，内嵌**绝对路径**与 mtime，
   跨 workspace 不可移植 ⇒ 按约束文件结论**就地重生成**后随仓库提供（幂等：跑测试前后逐字节不变）。

## 已知限制（如实记录，未粉饰）

1. **标定缓存与位置耦合 —— 已修（M1 后置修复，已随本仓库生效）**：
   `spikes/s5-latency-calibration/calibration.registry.json` 是**派生缓存**，记录三个冻结文件的路径/mtime/sha256。
   原实现把「路径 + mtime」也纳入**是否重写**的判定 ⇒ 复制或克隆到新路径后首跑必改写该文件，
   `tests/test_calibrate_latency.py::test_registry_is_idempotent` **在克隆里首跑即红**（已在全新克隆中实测复现）。
   **修法**：幂等判定改为**内容锚定** —— 只比对各冻结物的 `sha256`；内容未变则**不写盘、逐字节保留**既有文件。
   修复后全新克隆 **71 passed / 10 skipped**（M1 口径），无需任何人工补救。
   *冻结清单增量（如实记录）*：`calibrate_latency.py` `e30be65b…` → `23fed40d…`。
   **残留边界**：该缓存仍**内嵌绝对路径与 mtime**（跨 workspace 的可移植性未解决）。
   本轮 PM 实测（把仓库树 `cp -R` 到 `/private/tmp` 后跑全量套件）：registry **逐字节不变**
   （`f1da3742…`，跑前 = 跑后）、套件 `132 passed / 4 skipped` ⇒ **内容锚定在副本上同样成立**。
   但 sentinel 在它自己的工作区副本上曾观察到 1 例 `test_registry_is_idempotent` 红（`mtime`/`path` 字段不等），
   PM 未能复现 ⇒ **登记为待收敛项（M3 开口项）**，不作「已关闭」处理。
2. **`V0_M1.sha256` / `V0_M2.sha256` 是冻结时刻的证据，不是本仓库内的完整性检查**。
   它们覆盖当时工作区里的**全部**交付面（M1 276 条 / M2 238 条），其中一部分未随本目录提供
   （M1 的 `spikes/red/**` 负控沙箱等；M2 的 scratch 目录）。
   故在本仓库里对它们跑 `shasum -c` 会报缺失/不一致——**这是预期行为**（见上一节第 2 条）。
   本目录内的完整性检查是 `verify_specs.sh` 与内核测试套件。
3. **时间预算标定判据 ③ 不可重复**（AC-M1-6 记为 GAP，M2 未变）：同一份数据、同一批声明值、同为 `--runs 10`，
   相邻三次测量给出 adopted 降级率 `0.50`（越界）/ `0.20` / `0.10`；根因是环境抖动 **叠加** 冻结区间的口径塌缩
   （`ceil_to(50,p95) == ceil_to(100,p95) == 1300`，七个能力全部塌缩）。**未重采样、未调参、未改任何声明值。**
4. **`local_model` provider 未真跑**：本机无本地模型服务，只有槽位设计。不冒充已跑。
5. **`embed.text` 远端结构性不可用（GAP-E1，M2 登记）**：该能力在所用通道上 `/v1/embeddings` 端点与
   目标嵌入模型均不存在（通道 19 个模型中含 embed 的 0 个）⇒ 录制态每次触发都发一次注定 404 的请求，
   `local_model` 本机无服务 ⇒ 该能力实际只剩 `deterministic_rule`。ADR-014 已把契约优先级收敛
   （`remote_api` 10→90、`cassette_replay` 20→50），`06` 已如实登记。
6. **M2 结转 M3 的开口项 7 条**（`06_v0_m2_self_test.md` / `docs/architecture/06-acceptance-record.md` 有逐条依据）：
   raven H2/H3/H4/H8/H9、B-9a/b/c 锚定族、A-7 `_fallback` 默认值、`test_calibrate_latency` 绝对路径绑定。
   另有 M2 门禁登记的 MEDIUM/LOW 残留（`pin` 只做存在性校验 ⇒ 回滚语义可被旁路；`verify_pack`/`pack_sign`
   用 `rglob` 不跟随**目录**符号链接 ⇒ U11 的缺口；`--cognition` 默认 provider 随环境凭据漂移；
   `verify_specs.sh` 的 manifest 覆盖判据是**子串**非锚定）。
7. **范围**：M1 = 确定性内核可运行；M2 = 能力注册表 + 四类 provider + 规则层与预算 + 记忆层 + 第二街区内容包。
   双模式会话（W7）、渲染层与 UI（W8）、观测层（W9）、集成验收（W10）属后续里程碑（M3/M4）。

## 溯源

| 项 | 值 |
|---|---|
| 需求书 | `REQ-20260921-003`（M1）、`REQ-20260921-004`（M2）；上游 `REQ-20260921-002` 架构冻结 |
| 验收 | **M1**：有条件通过（6 PASS / 1 GAP / 1 分列均 PASS，CRITICAL 0）；**M2**：通过（8/8 AC PASS，CRITICAL 0，残留 FAIL 0） |
| 冻结计划 | `docs/architecture/04-v0-plan.md`（13 工作包 / 4 里程碑 M1~M4） |
| 契约副本 | `docs/specs/` 是这 18 份契约的**发布视图**；本目录 `02_source/` 是**可自校验的源** |
| M2 落盘提交 | 见本目录所在仓库的提交历史（M2 单笔提交） |
