
---

# 06 — M5.2 **r2** 自测报告（AC-5 实机呈现 + W11 追溯链）

- 角色：artisan（舰载工程官）· 本任务**唯一派单写入者**（`.task-artisan.pid` = 99008 = 本派单进程）
- 段：**M5.2 r2**（主写集 `02_source/v0_skeleton/web/**` + `spikes/m52-live/**`；本轮**最后写入者**）
- 模型自证：`model: deepseek-v4.1-flash | 来源: 本派单进程 hermes -p artisan chat --query-file …r2.pointer.txt --oneshot --run-budget 7200`（本段无换模型）
- 逐条命令 / workdir / exit / 读数见 `03_artisan_self_test.log` 的 **§M5.2-r2** 段；本文件给**呈现层分层声明 /
  追溯链 / 工具链来源与替代路径 / 遗留与建议 / 冻结面终版**。

## 1. 呈现层分层声明（REQ §4 AC-5 明文，**逐项**）

| # | 层 | 本轮的**事实**（含读数/文件） |
|---|---|---|
| ① | **真内核 + 真内容包（行为面 = 真实）** | 世界由交付面 `kernel/deephealing_kernel` 的 `WorldKernel.step()` 推进；内容包 = `districts/xingfu-xiaoqu-xuqin`（独立 `pack_id`、`pack.sig` 已验，npc-006 = 徐琴）。页面上的 `tick` / 世界钟 / `state_hash` / 事件流**全部**来自该内核（内核自带 `LiveWorld` 的只读投影 + 会话层转发）；**无**前端自算、**无**回放。读数：`state_hash c7ed9f1d…`、`event_chain_hash 3db65b3b…`、`world_clock 07:31`（`readback/before-with.json`） |
| ② | **呈现层仍是低多边形占位** | 场景几何 = `THREE.BoxGeometry`（`web/src/scene/world.ts`）；资产 = `assets-sample/workflows/procedural-placeholder.json` 的**程序化占位**（64×64、无贴图）。⇒ **盒体占位画面不得作为「写实美术已达成」的证据**；本段任何读数都**不**声称画质 / 氛围达成（`art-bible.md`：「**不**宣称『治愈系氛围已达成』」同口径） |
| ③ | **与 PM 的 `/tmp/dh-demo` 演示件的区别** | `/tmp/dh-demo/**` 是 **PM 手搓参考件**（自带 `viewer/`、`serve_live.py`、`#left` 面板及其 `#left{max-height:66vh}` 溢出形态），**不是**交付客户端。本轮的落点是**交付面** `02_source/v0_skeleton/web/**`（构建产物 `<ws>/.build/web`），面板元素 = `#hud` / `#event-stream` / `#causal-trace`（**没有** `#left`）；AC-5 **未**依赖 `/tmp/dh-demo` 的 node_modules 存活 |

## 2. 徐琴闭环的可追溯呈现（W11）

**交付面实现**：`web/src/ui/observe/trace.ts`（新增；`#causal-trace` 是**纯文本块**，零控件 ⇒ M3 的
`write_controls == []` 判据未回退）。链的四节点**全部**取自会话通道下发的 `event` 消息（内核真实事件日志原样转发）：

```
① 事件      seq 62  t16  npc.action(npc-006, rest → room-1052)
② 记忆      seq 63  t16  memory.written(layer=episodic, ref=16, kind=rest, importance=0.144619)
③ 决策      seq 122 t31  npc.decision(memory_influence.signals=["episode:rest@ref=16"], utility_delta=0.19, chosen=rest)
④ 可观察行动 seq 123 t31  npc.action(rest → room-1052)
```

- **连边可核**：②→③ 靠 `@ref=` 与 `memory.written.payload.ref` **逐字相等**；①→② 靠「同 tick + kind 一致」
  （内核 [5] 段的顺序钉死：先 `npc.action`、后 `memory.written`）；③→④ 是同 tick 的 `npc.action`。
- **命令**：`python3 spikes/m52-live/tools/extract_chain.py --npc npc-006` ⇒ exit 0 / `all_pass=true`
  （读数 `readback/chain-verdict.json`）。抽取器**从客户端实际收到的事件重新抽链**（不采信客户端自报）。
- **反例（把该经历从注入里去掉 ⇒ 链断）**：`without` 臂（同 seed / 同 pack / 同 tick 数，唯一变量 = 未注入）
  ⇒ `decisions_with_signals = 0`（**记忆节点缺失**、链不完整）+ 两臂首个分叉 **tick 22**：
  注入臂 `rest` vs 无注入臂 **`work`**（**决策改变**）。⇒ 断链同时命中「节点缺失」与「决策改变」，
  且落点是**可观察行动**（`npc.action` 的 action / target_entity），**不是**「认知日志里多了结论」。
- **注入形态（如实披露）**：库级**提升一条内核自产经历的权重**（0.144619 → 0.95；AC-4「预置关键经历」的
  等价形态），选择规则 = 取该 tick `utility_ranking` 的**第二名**动作（runner-up）再回找最近一条该动作的经历。
  **有意留下的痕迹**：该 `memory.written` 事件里的 `importance` 是写入时刻的值 ⇒ 与库内当前值不同，
  这正是「权重是注入抬起来的」的可核验标记（`ac5-run-with.json` → `injection.store_before/after`）。
- **诚实边界（GAP）**：交付面 `session/bridge/kernel_bridge.py` **无** `event` emit 点 ⇒ 浏览器侧**没有**
  内核事件源。r2 写集不含 `session/**` / `kernel/**` ⇒ 该通道由 AC-5 脚手架（`spikes/m52-live/serve.mjs`
  + `tools/live_driver.py`）**只读转发**内核事件日志补齐，**不改写、不新增**事件。**下一轮建议**见 §4。

## 3. 工具链来源与替代路径（Raven L-6）

- **来源**：`vite` / `playwright`（**1.63.0**）来自 **M3 工作区**的持久依赖
  `…/REQ-20260921-005-deephealing-v0-m3/node_modules`，以 `<ws>/node_modules` 符号链接接入
  （**D-9 既有口径**：「依赖提升到 `<workspace>/node_modules`」；该目录被三份清单按名排除，不是交付物）；
  浏览器 / 编码器来自 `~/Library/Caches/ms-playwright`（`chromium-1234` / `ffmpeg-1011`，持久缓存）；
  node **v26.3.1**。
- **AC-5 不依赖 `/tmp` 存活**：截图 / 录屏 / 回读 JSON / 断言日志**全部**落 `spikes/m52-live/**`；
  构建产物落 `<ws>/.build/web`（`vite.config.ts` 既有口径，在 `02_source` 之外、生成器按名排除）。
- **缺件时的替代路径（本遍实测三条）**：
  ① `vite build` 需要 `<ws>/node_modules`（否则 `vite.config.ts` 解析 `vite` 失败，实测
     `ERR_MODULE_NOT_FOUND`）——缺件时的替代 = 用 M3 依赖目录建符号链接（本遍做法）；
  ② Playwright 的 `ffmpeg-mac` **没有** `null` muxer 与 `select` 滤镜 ⇒ 时长改用容器元数据、帧数改用
     **全帧解码计数**（`-s 160x100` 落盘数文件）、抽帧改用 `-ss`（`tools/check_artifacts.py` 已按此实现）；
  ③ 仓库 `web/package.json` **无** playwright ⇒ 实机验收**必须**由 `spikes/**` 脚手架提供驱动，
     **不得**把 playwright 写进交付面依赖。

## 4. 遗留与建议

1. **交付面缺事件通道（最高优先）**：`kernel_bridge.py` 无 `event` emit ⇒ 交付客户端拿不到内核事件，
   「从事件记录追溯原因」在交付形态下**无数据源**。建议下一轮在桥的 `step` 分支补 event 转发
   （形态照 `spikes/m52-live/tools/live_driver.py`），并加判据「下发事件条数 == 内核事件日志行数」。
2. **`KNOWN_PACKS` 硬编码**（`session/src/server.js:37`）⇒ 新内容包被会话层拒（`E_PACK_INVALID`）。
   建议把 pack 白名单数据化（来自 `districts/` 目录扫描 + `manifest.txt`），与 r1 的 M-6 一并处置。
3. **回读判据的口径**：本遍用脚手架步进闸门把世界冻结后对照（并给「放行推进 ⇒ diff ≠ 0」的负对照）。
   若要求「世界不停转时的 reload 一致性」，需新增逐 tick 对齐判据。
4. **F7 残留 GAP**：M4 的 `fd_total_peak 4089` 仍未复现（放大到 4090 条目标并发只压到 1785 条）；
   需要 M4 当时的客户端负载脚本或原始 fd 采样。
5. **AC-8 MEDIUM（cognition 退化）**：C1 让需求压力长期 ~0.06 ⇒ 只调 `emotion.appraise`（能力调用 15 → 5）。
   改门限 = 改冻结的 `COGNITION_TREE_SPEC` 语义 ⇒ 待 PM / architect 裁决。
6. **实机验收发现并修复的交付面缺陷 2 条**（D1 双会话 / D2 pack id 默认值），已在 `web/**` 落地并复跑验证
   （修后 console error **0**、面板 tick 与世界 tick 一致）。
7. **`memory.written` 的 `working` 层与 `episodes` 层 ref 各自编号**（实测同 tick 都是 16）⇒ 任何按 ref
   关联的判据**必须**同时按 `layer` 过滤（本轮客户端与抽取器都已加；建议写进后续判据模板）。

## 5. 冻结面终版登记（W12 · r1 版 SUPERSEDED）

- 三份清单 = `V0_M52.sha256`（**M5.2 权威面**）/ `V0_M4.sha256` / `V0_M5.sha256`（各自沿用原口径**重取**）；
  生成器 `V0_M52.gen.py` 与 `spikes/m52-frozen/retake_m4_m5.py` **均不入清单**。
- `shasum -a 256 -c` 三份 ⇒ **0 非 OK**；读数 = `spikes/m52-live/evidence/frozen-verify.txt`（含 mtime 对照表：
  清单 mtime **晚于**交付面最后一次写入；最终清单由**最后一次生成**产出，其自校验在生成后立即复跑）。
- **r1 版已被 r2 取代**：r2 改了 `web/**`（在三份清单的采集面内）⇒ 根级 `03`/`06` 与三份清单的 **r1 版本
  不得再当终版引用**。
