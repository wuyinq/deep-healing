# PM 落盘说明（N2 · REQ-20260924-002）

本文件由 **PM（lanova）** 在把 N2 产物从工作区落盘到交付仓库时写入，
记录**落盘变换**，保证证据可追溯。它**不是** N2 小队的产物，也不参与任何判据。

## 1. 被排除的目录（运行期/构建产物，非证据）

| 目录 | 体积 | 排除理由 |
|---|---|---|
| `spikes/n2-appearance/runtime/**` | 89 MB | 脚手架运行期副本（内含多份 `02_source` 全树 + sqlite + checkpoint），可由 §notes README 的复跑命令重建 |
| `spikes/n2-appearance/build/**` | 3.2 MB | `vite build` 产物，由交付面 `02_source/v0_skeleton/web/**` 重建 |

## 2. 被压缩的原始事件流（`readback/events-*.jsonl`）

原始事件流体积过大（最大单文件 49 MB，超出仓库既有惯例与托管方单文件上限）。
按仓库既有惯例（`v0/spikes/m52-f7/pre-r5-stderr/*.err.gz` 同法）**gzip 存储**，
文件名加 `.gz` 后缀，**内容零改动**。

解压：`gunzip -k <file>.jsonl.gz`（得到与原文件字节一致的 `.jsonl`）

| 原始文件 | 原始 | 压缩后 |
|---|---|---|
| `readback/events-n2.jsonl` | 49.14 MB | 6.43 MB |
| `readback/events-r2obs.jsonl` | 17.67 MB | 2.61 MB |
| `readback/events-r3obs.jsonl` | 6.80 MB | 1.01 MB |
| `readback/events-r4obs4.jsonl` | 2.67 MB | 0.40 MB |
| `readback/events-r4obs3.jsonl` | 1.92 MB | 0.29 MB |
| `readback/events-driven.jsonl` | 1.90 MB | 0.28 MB |
| `readback/events-diag.jsonl` | 1.41 MB | 0.21 MB |
| `readback/events-diag2.jsonl` | 1.40 MB | 0.21 MB |
| `readback/events-r4obs2.jsonl` | 0.74 MB | 0.11 MB |
| `readback/events-r4obs.jsonl` | 0.40 MB | 0.06 MB |

## 3. 未被改动的内容

除上表两类外，其余文件**逐字节原样落盘**（含 `shots/*.png`、`readback/*.json`、
各分析日志、`serve.mjs`、`browser-accept.mjs` 等脚手架）。
