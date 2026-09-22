# 声明值推导规则（**先冻结**，再测量）
#
# 冻结时间：见本文件 mtime。本文件的 mtime 必须**早于** `logs/latency.distribution.json`
# 与 `logs/degradation.*.json` 的 mtime（D-0.9 防自证第 1 条）。sha256 登记在 `calibration.registry.json`。
#
# 为什么必须冻结：如果先看分布、再挑一条让降级率好看的规则，标定就退化成自证（预审 Q2）。

## 规则（分布的单调非减函数，带下界）

记实测远端延迟分布为 D（单位 ms），`p_k(D)` 为**最近秩法**分位（nearest-rank：`k = ceil(q * N)`，取排序后第 k 个样本）。

```
ceil_to(m, x)        = m * ceil(x / m)                    # 向上取整到 m 的整数倍
p90(D)               = nearest_rank(D, 0.90)
p95(D)               = nearest_rank(D, 0.95)
p99(D)               = nearest_rank(D, 0.99)

strict_candidate(D)  = ceil_to(50,  p95(D))
adopted(D, cap)      = ceil_to(100, p95(D)) + offset_ms(cap)      # 盘上采用值
loose_candidate(D,cap)= ceil_to(500, p99(D) + 1000) + offset_ms(cap)
latency_budget(D,cap)= ceil_to(50,  p90(D)) + offset_ms(cap)
```

`offset_ms(cap)` 是**每个能力自己的**固定偏移（本轮冻结值，理由：单次调用的输出 token 量与上下文长度不同）：

| 能力 | offset_ms | 理由 |
|---|---|---|
| `emotion.appraise` | 0 | 输出最短（结构化情绪评分） |
| `intent.plan` | 500 | 输出中等（动作 + 理由码） |
| `memory.reflect` | 1000 | 输出最长（反思摘要字段最多） |
| `relation.infer` | 0 | 本地确定性规则，不调远端（offset 仅用于对称） |
| `embed.text` | 250 | 批量嵌入，输出固定长度 |
| `imagine.predict` | 500 | 世界模型结构化预测（输出含预测列表，长度与 `horizon_ticks` 相关） |
| `imagine.rollout` | 750 | 世界模型推演（输出含多候选 rollout，字段最多） |

## 单调性与下界（为什么这条规则不能被「按绿灯挑」）

- 单调性：`p95` 与 `p99` 对分布单调非减，`ceil_to` 与加法保持单调 ⇒ 声明值随分布单调非减；
  实测分布变差时，声明值只会变大，不会变小。
- 下界：`ceil_to(100, p95) ≥ p95`，故 `声明值 ≥ p95`。
- **禁止**的规则（本文件冻结时即排除）：取 `p50`、取 `min`、取 `max`、取「刚好让降级率为 0 的最小值」。

## 硬约束（校验器会断言）

1. `timeout_ms ≥ p95_ms`（向上取整）。
2. `timeout_ms ≠ max_ms`（声明值不得等于当次实测最大值）。
3. `latency_ms_budget ≥ p90_ms`。
4. 声明值必须出现在 `02_source` 的能力清单里，且与报告值**脚本断言一致**（防 override 路径绕过）。
5. 等价性 / 降级证据必须在**声明值**下取得，**禁止** `--timeout-ms-override`（合成负例例外见 `capability.time-budget.spec.md`）。
