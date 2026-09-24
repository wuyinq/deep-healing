# N2 实机脚手架说明（`spikes/n2-appearance/**`，**非交付面**）

本目录是 **AC-9 实机取证**的脚手架与产物。**交付面在 `<ws>/02_source/**` 与 `<ws>/docs/**`**；
本目录的任何文件都**不是**交付物，也不参与 `verify_specs.sh` / `scene_assert.mjs` 的判据。

## 1. 装配（沿用 F-20 先例，零重写）

| 层 | 实现 | 说明 |
|---|---|---|
| 真内核 + 真内容包 | `spikes/m52-live/tools/live_driver.py`（**沿用，未重写**） | 与 `session/bridge/kernel_bridge.py` 同形的 stdin/stdout 驱动 |
| 真会话层 | `02_source/v0_skeleton/session/src/server.js`（原样 import） | `serve.mjs` 只做「把驱动记录喂给会话层」的搬运 |
| 真渲染层 | `spikes/n2-appearance/build/web` | 由**交付面** `02_source/v0_skeleton/web/**` 经 `vite build` 产出 |
| 浏览器 | Playwright + Chromium 1234（swiftshader） | 1440×900 / 390×844 |

`serve.mjs` = `spikes/m52-live/serve.mjs` 的副本，**只改 4 个路径常量**（WEB / OUT / RUNTIME / DRIVER）
+ 读数文件名 + 头部说明 + 一处回填开关（见 §3）。

## 2. 复跑命令

```bash
# 0) 构建交付面 web（产物落本目录，**不进 02_source**）
cd <ws>/02_source/v0_skeleton/web
node ../../../node_modules/vite/bin/vite.js build --outDir ../../../spikes/n2-appearance/build/web

# 1) 起服务（世界**先不推进**：起步闸门默认 paused）
cd <ws>/spikes/n2-appearance
node serve.mjs --port 8801 --pack xingfu-xiaoqu-xuqin --tag n2 --run-seconds 300 \
     --tick-ms 200 --backlog-cap 0

# 2) 实机验收（日常态 + 390px + 面具态 + 对照；含 JS 错误计数）
cd <ws>
node spikes/n2-appearance/browser-accept.mjs --url http://127.0.0.1:8801 --out spikes/n2-appearance

# 3) 面具态**驱动路线**单独取证（≥120 tick）
node serve.mjs --port 8806 --pack xingfu-xiaoqu-xuqin --tag driven --run-seconds 240 \
     --tick-ms 200 --backlog-cap 0            # 另起一个终端
node spikes/n2-appearance/tools-drive-mask.mjs --url http://127.0.0.1:8806 --out spikes/n2-appearance
```

## 3. 两处必须知道的口径（**实测发现**）

1. **世界必须停在 tick 0 等页面就绪，再 `POST /control/resume`。**
   起步闸门只控制「是否继续给驱动发 step 命令」，**不写世界状态**。
   顺序错了（先推进、后连页面）会让「事件回填」与首帧 snapshot 互相踩踏。
2. **`--backlog-cap 0` = 关闭事件回填。**
   M5.2 脚手架在 WS 升级时把 `eventBacklog` 直接发给新连接；这些事件带**当前 tick**，
   会把渲染客户端的 `(tick, seq)` 水位推到最新 ⇒ 随后 `primeSession` 的 snapshot 因 seq 更小
   被当乱序丢弃，页面永远拿不到初始实体（实测：`entityIds() == []` 而 SSE 投影有 5 实体）。
   N2 的 AC-9 不需要事件回放 ⇒ 关闭回填，读数更干净。**交付面未受影响**（这是脚手架行为）。

## 4. 产物

| 路径 | 内容 |
|---|---|
| `shots/n2-desktop-1440x900-daily.png` | 桌面 1440×900 · 日常态（外形来自内容包） |
| `shots/n2-narrow-390x844-daily.png` | 390×844 窄屏 · 日常态 |
| `shots/n2-desktop-1440x900-masked-driven.png` | 桌面 · **面具态（驱动 ≥120 tick，实测 tick 137）** |
| `shots/n2-desktop-1440x900-masked.png` | 桌面 · 面具态（等价注入该 state 的第二条读数） |
| `shots/n2-control-1440x900-generic-humanoid.png` | **对照**：`setAppearance(null)` ⇒ 通用人形（**非达标证据**） |
| `readback/n2-browser-accept.json` | 逐读数（`appearanceReport` / `characterReport` / JS 错误 / 截图清单） |
| `readback/n2-driven-mask.json` | 驱动路线读数（tick / state_id / 部件名 / 消息计数 / snapshot 目标） |
| `readback/events-*.jsonl`、`tick-series-*.json`、`n2-run-*.json`、`serve-summary-*.json` | 过程日志（非判据性） |
| `runtime/**` | 驱动运行期目录（内核事件日志 / 状态） |

> **读数按 mtime 分轮，跨轮读数不可混用**（Raven BUG-6）：`readback/` 内 r2 与 r4 的读数**并存**
> （如 `n2-browser-accept.json` 与 `n2-r4-*`），文件名**不含轮次** ⇒ 取数时**必须**按 `mtime`
> 判定所属轮次，**不得**把不同轮次的读数拼成一条证据链。

## 5. 诊断脚本（保留，便于复核）

- `tools-diag-page.mjs`：页面装配读数（句柄 / 实体 / 投影 / canvas）。
- `tools-diag-mask.mjs`：世界推进过程中 `schedule.target_entity` 与 `state_id` 的逐点采样。
- `tools-diag-messages.mjs`：**场景实际收到**的消息类型与 snapshot 的 `target_entity` 集合
  —— 「面具态到底由哪条路径驱动」的判定依据。
