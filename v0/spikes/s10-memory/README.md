# spikes/s10-memory —— W5 记忆层真跑证据（AC-M2-5）

生成脚本：`.squad_tools/artisan-s10-memory-evidence.py`（可重复执行，逐字节可复算）。

| 文件 | 判据 |
|---|---|
| `logs/memory-layers.json` | 三层（working/episodes/facts）真跑条数与样本；两个独立库一致 |
| `logs/write-point.json` | 唯一写入点：默认 flag 关闭 ⇒ 零写入；打开 ⇒ 真写 |
| `logs/retrieval-digest-compare.json` | 同 seed 同输入 ⇒ 检索摘要**逐字节一致**（比对器 CONSISTENT） |
| `logs/retrieval-digest-negative.json` | **负例**：改 tie-break / 依赖容器迭代序 ⇒ 比对器 INCONSISTENT |
| `logs/prune-soft-delete.json` | `prune` 软删（行仍在库）+ 容量上限生效 |
| `logs/supersede-history.json` | 事实覆盖保留历史（`superseded_by` 指向新 ref） |
| `logs/cognition-memory-run.json` | 经 CLI `run --cognition --memory` 真跑一次认知循环（写入计数/检索摘要/退出码） |
| `logs/world-state-boundary.json` | 带/不带认知层的 `chain_tail` 逐位相同（记忆不写世界状态） |

对照用例：`02_source/v0_skeleton/kernel/tests/test_memory_layers.py`（8 条，含逐条自证反例）。
