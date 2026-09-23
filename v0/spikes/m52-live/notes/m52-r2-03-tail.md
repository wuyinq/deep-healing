
--------------------------------------------------------------------------------
[自审（必要自审，**不替代** Sentinel / Raven 独立门禁）]
--------------------------------------------------------------------------------
  - **正确性**：因果链的连边是**字符串逐字相等**（`signals` 里的 `@ref=<R>` == `memory.written.payload.ref`），
    且只认 `layer=episodic`（与 `rules/decision.py::memory_influence` 的 `fetch_episodes()` 同源 —— `working`
    层 ref 与 episodes **各自独立编号**，实测同 tick 两条都是 16，不按层过滤会张冠李戴）。
    抽取器**不看客户端自报的 `traceFor()`**，而是从客户端**实际收到**的原始事件重新抽链；两者结果一致
    （面板文本与 `chain-verdict.json` 的四节点逐字段相同）。链不完整时面板**显示「（无）」**并列出
    未连上的 ref（`unlinked_signal_refs`），**不补造**节点。
  - **兼容性**：`web/**` 的改动是**追加式**（新文件 `trace.ts` + `index.html` 新增只读块 + `main.ts` 接线）；
    `?pack=` 缺省时行为与改前一致（仍用默认包）；删掉的第二次 `client.connect()` 经实机对照确认是**缺陷**
    （双会话 ⇒ 消息按 (tick,seq) 交错被丢），修后 `apply()` 语义不变。M3 的「观察模式零写控件」判据
    **未回退**：实机 `write_controls == []`（desktop + narrow 两档都有读数）。
  - **安全**：追溯面板只渲染事件 payload 的既有字段（`npc_id` / `layer` / `ref` / `kind` / `importance` /
    `signals` / `target_entity`）——**不含**原著正文；脚手架只绑 `127.0.0.1`，**不**接管参与模式写通道
    （`submitIntent` 如实返回 `E_KERNEL_UNAVAILABLE`）；注入只写**运行副本**的 SQLite（`spikes/m52-live/runtime/**`），
    交付树与真实仓库零写入；无凭据、无 prompt、无原始请求体进入任何产物。
  - **错误路径**：内容包/NPC 档案取不到 ⇒ 退化为显示 id（**不**伪造名字，且非人物 actor **不**入索引 ⇒ 无 404）；
    实时通道断 ⇒ 面板显示 `offline`（**不**伪造读数）；事件流为空 ⇒ 面板显示 `waiting for events`；
    注入找不到可提升的 runner-up 经历 ⇒ 如实报 `skipped_no_target`（不伪造注入）。
  - **并发 / 资源边界**：一页面**一个会话**（D1 修复）；脚手架下行箱**每 100ms 出队**（缺它则消息堆在下行箱、
    页面停在最初几 tick —— 这是本遍实测到的脚手架缺陷，已修）；SSE 订阅集合在收尾显式关闭；
    F7 侧读数未因本轮改动变化（`fd_total_peak` 72，与 r1 的 73 同量级）。
  - **已知未覆盖**（详见「未闭合项」）：① 浏览器侧事件通道由脚手架补齐；② `KNOWN_PACKS` 硬编码；
    ③ 回读判据依赖脚手架的步进闸门（交付树无暂停控制）；④ F7 的 4089 仍未复现；⑤ cognition 退化未改。

--------------------------------------------------------------------------------
[未闭合项（交班时如实登记）]
--------------------------------------------------------------------------------
  1. **`kernel_bridge.py` 无 `event` emit 点 ⇒ 交付面客户端没有内核事件数据源**（GAP，不包装成已解决）。
     事实：`session/bridge/kernel_bridge.py` 的 docstring 声明 `kind` 含 `event`，但 `grep -n '"kind": "event"'`
     零命中、`emit({...})` 无一处带 `event` ⇒ 会话层从未下发过内核事件。r2 写集**不含** `session/**` / `kernel/**`
     ⇒ AC-5 的实机由脚手架**只读转发**内核事件日志补齐（不改写、不新增事件）。**下一轮建议**：在
     `kernel_bridge.py` 的 `step` 分支里补 event 转发（与 `spikes/m52-live/tools/live_driver.py` 同形），
     并配一条「事件条数 == 内核事件日志行数」的判据。
  2. **`KNOWN_PACKS` 硬编码**（`session/src/server.js:37` = `{xingfu-xiaoqu, xingfu-xiaoqu-north}`）⇒ 交付会话层
     对徐琴提案包返回 `E_PACK_INVALID`；脚手架显式传入白名单绕过（`knownPacks: new Set([PACK, …])`）。
     与 r1 的 M-6（`verify_specs.sh` 的 `PACK_DIR` 硬编码）同一类问题。
  3. **F7 残留 GAP**：M4 的 `fd_total_peak 4089` 仍未复现（本轮把 `hold` regime 放大到 4090 条目标并发，
     客户端只压到 1785 条）⇒ 缺 M4 当时客户端的并发/连接保持形态或原始 fd 采样。判据仍**有牙**
     （放大负载：pre-fix 1785 红 vs 交付 72 绿）。
  4. **AC-8 新增 MEDIUM（cognition 退化）**：C1 让需求压力长期 ~0.06 ⇒ `cognition` 树只走 `emotion.appraise`
     （能力调用 15 → 5、cassette 4 → 1）。**改门限 = 改冻结的 `COGNITION_TREE_SPEC` 语义** ⇒ 本轮不改，
     交 PM / architect 裁决。
  5. **徐琴包 10-d-1 / 10-d-2 结构不可达**（单 NPC 包，r1 已登记）⇒ 待 PM 决策 B-1。
  6. **AC-5 的「同一世界状态」口径**：交付树**没有**「暂停世界」的控制面；本遍的 reload 回读用脚手架
     `/control/pause|resume`（只控制是否继续发 step 命令、**不写世界状态**）把世界冻结后再对照，
     并给「放行推进 ⇒ diff ≠ 0」的负对照。若 PM 要求「世界不停转时的 reload 一致性」，
     需要新增一条**逐 tick 对齐**的判据（例如「reload 后首帧 tick == 重连时刻的内核 tick」）。

--------------------------------------------------------------------------------
[冻结面终版登记（W12 · 最后写入者 = r2）]
--------------------------------------------------------------------------------
  三份清单（生成器**均不入清单**；时序：快照是收尾**最后一个动作**，取之前 03 已停写）：
  | 清单 | 采集面 | 生成器 | 登记 |
  |---|---|---|---|
  | `V0_M52.sha256` | `02_source/**` + `docs/**` + `spikes/m52-*/**` + 根级 `03_artisan_self_test.log` /
    `06_v0_m52_self_test.md` / `fidelity/POINTER.md` | `V0_M52.gen.py`（**不入清单**） | **M5.2 权威面**
    （PM 落盘按此核验）；**r1 版 = 中间版，已被 r2 取代（SUPERSEDED）** |
  | `V0_M4.sha256` | M4 原口径（`02_source/**` + `spikes/s14..s16/**` + 根级 `03` / `06_v0_m4_self_test.md` /
    `V0_SELF_TEST.md`） | `spikes/m52-frozen/retake_m4_m5.py` | **重取**（r2 改动落在其采集根内） |
  | `V0_M5.sha256` | M5 原口径（`02_source/**` + `docs/**` + `fidelity/POINTER.md` + 根级 `03`） | 同上 | **重取** |
  cmd（workdir `<ws>`）：
    `python3 V0_M52.gen.py`；`python3 spikes/m52-frozen/retake_m4_m5.py`；
    `shasum -a 256 -c V0_M52.sha256 V0_M4.sha256 V0_M5.sha256`
  读数：见 `spikes/m52-live/evidence/frozen-verify.txt`（**三份清单 0 非 OK**；该文件在**最终**清单生成之前
  写入 ⇒ 它本身也在 `V0_M52.sha256` 的采集面内；清单 mtime 晚于交付面最后一次写入，见 06 的 mtime 对照表）。
  **r1 版已被 r2 取代**：r2 改了 `web/**`（在三份清单的采集面内）⇒ 清单与根级 `03`/`06` 的 r1 版本
  **不得**再当终版引用。
