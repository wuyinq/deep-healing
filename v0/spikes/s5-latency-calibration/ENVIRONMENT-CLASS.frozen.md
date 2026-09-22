# 环境可用性判定（**测量前**声明，D-0.9 防自证第 4 条）

冻结时间：见本文件 mtime。本文件必须在**任何采样之前**落盘，且其 mtime 必须早于
`logs/latency.distribution.json` 的 mtime。sha256 登记在 `calibration.registry.json`。

## 为什么需要它

`DERIVATION-RULE.frozen.md` 的规则是分布的单调非减函数 ⇒ 一份**被网络拥塞污染**的分布
照样能算出一组「看起来合规」的声明值（`timeout_ms ≥ p95`、`≠ max` 都能满足）。
因此仅有推导规则不足以防自证：还需要一条**先声明**的判据，用来判定「这份分布是否代表模型真实延迟」，
从而决定 `derive` 是**产出声明值**还是 **fail-closed 拒绝产出**。

## 判定（两条判据，任一命中即判 `degraded`）

记实测分布为 D，`p50(D)` / `p90(D)` 为最近秩分位（口径同 `DERIVATION-RULE.frozen.md`）。

| 类 | 条件 |
|---|---|
| `usable` | `sample_count_ok ≥ 20` **且** `sample_count_failed == 0` **且** `p90(D) ≤ 20000 ms` **且** `p90(D) / p50(D) ≤ 3.0` |
| `degraded` | 上述任一条不成立（含样本不足 / 有失败样本 / `p90 > 20000 ms` / `p90/p50 > 3.0`） |

## 阈值理由（不是为凑结论挑的数）

1. `p90 > 20000 ms`：REQ §7 已把「p90 ~43 s」定性为**网络拥塞污染**而非模型真实延迟；
   本判据把该定性变成可执行断言。20000 ms 明显高于本机历史健康窗口（`p50` 2.3–7.4 s 量级），
   落在健康与拥塞之间，不依赖任何一次具体测量结果。
2. `p90/p50 > 3.0`：拥塞的特征是**重尾**（少数请求被排队拖长），而非整体抬升。
   002 工作区实测 `p90/p50 = 42110.951 / 7443.408 = 5.66` —— 正是重尾形态。
   比值判据与绝对阈值互补：一个挡住「整体变慢但均匀」，一个挡住「少数被拖长」。
3. `sample_count_ok ≥ 20` / `sample_count_failed == 0`：与 `capability.schema.json` 的
   `calibration.sample_count >= 20` 断言口径一致；失败样本必须如实记入 `errors`，不得静默丢弃。

## 处置

- `derive` 在 `degraded` 下 **fail-closed**：`exit 1`，**不产出**任何声明值，
  只在输出里写 `refuses_to_declare: true` 与 `environment_class: "degraded"`，并保留原始分布四值。
- **禁止**把未标定值写成声明值；**禁止**用 `--timeout-ms-override` 类开关绕过；
  **禁止**事后调整本文件的阈值或 `ACCEPTED-DEGRADATION-RANGE.frozen.md` 的区间。
- 原始分布（逐样本延迟 + 四值 + 失败样本）无论类别如何都必须落盘，不得只留结论。
