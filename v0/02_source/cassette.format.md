# cassette 录制 / 回放格式（冻结）

配套 schema：`cassette.schema.json`（每条记录必须通过）。载体：JSONL，一行一条记录，UTF-8，无 BOM，`\n` 结尾。

## 1. 目的与适用面

cassette 是**原子能力**（`capability.schema.json`）的确定性回放层。它解决两件事：

1. **可确定性回放**：`determinism.mode = replayable` 的能力在回放模式下强制走 `cassette_replay`，世界重放不引入新的随机性。
2. **离线降级**：远端 API 不可用时，仍能用已录制结果推进同一决策循环（认知降质但世界不断线）。

cassette 只服务能力调用，**不**记录世界状态（世界状态由 `events.jsonl` + `snapshot.schema.json` 负责）。

## 2. 记录格式（逐字段）

| 字段 | 类型 | 语义 | 约束 |
|---|---|---|---|
| `key` | string(hex64) | 记录主键 | 见 §3；只由确定性字段派生 |
| `capability_id` | string | 能力 id | 与 `capability.schema.json.id` 一致 |
| `capability_version` | string | 能力版本 | 参与 key；版本升级即旧记录失效 |
| `provider` | enum | **录制源** provider | 四类之一；回放 provider 不参与 key |
| `canonical_input_hash` | string(hex64) | 规范化输入的 sha256 | 规范化规则同 `snapshot.normalization` |
| `output` | object | 录制到的结构化输出 | 录制前必须已通过能力 `output_schema` |
| `meta` | object | 模型/token/延迟/时间/schema 版本/脱敏字段 | `recorded_at` **不参与**任何 hash |
| `prev_hash` | string(hex64) | 文件内前一条的 `key` | genesis = 64 个 `0` |
| `hash` | string(hex64) | 记录自校验 hash | **必填**。`sha256(prev_hash ‖ canonical_json(记录去掉 hash 字段))`，小写十六进制；定义与 `cassette.schema.json` 的 `hash` 字段逐字一致。参与完整性校验，见 §4.3。**强度边界见 §4.3 的 `FROZEN-CASSETTE-INTEGRITY-1`**：无密钥哈希链只检损坏 / 篡改，**不是真实性保证** |

## 3. key 构成（冻结）

```
key = sha256( canonical_json( {
  "capability_id":       <string>,
  "capability_version":  <string>,
  "canonical_input_hash":<hex64>,
  "provider":            <录制源 provider 类>
} ) )
```

- `canonical_json` 规则与快照一致：键按字典序、分隔符 `,`/`:`、UTF-8、无空格、整数不带小数点、浮点 6 位小数。
- 必须进 key 的：`capability_id` + `capability_version` + `canonical_input_hash` + `provider`（对应 `determinism.cassette_key_fields` 的最小集合）。
- **禁止**进 key 的：wall-clock、进程 id、主机名、会话 id、请求头、凭据、任何 provider 侧随机量。理由：一旦进入，回放必然 miss 或产生假命中。

## 4. 查找与命中规则

### 4.1 查找顺序

1. 调用发生在回放模式（会话/内核 `--replay`，或能力 `providers[]` 被强制为 `cassette_replay`）时，按 §3 计算 key；key 用**录制源 provider**计算，而不是 `cassette_replay`（回放 provider 自身不录制，`cassette_replay.cassette.jsonl` 不会存在）。
2. 录制源 provider **必须先确定**（见 §4.2），再在 `<capability_id>@<version>/<provider>.cassette.jsonl` 内查找 key 相同的记录。
   - **禁止**「枚举目录下全部 `*.cassette.jsonl`，取文件名字典序首个命中」。同一输入在不同录制源下 key 不同；取首个会让命中结果随目录内容漂移（多录一次就换一个答案），回放等价性就成了步骤顺序的侥幸。
   - 同一文件内同一 key 出现多次视为**文件损坏** → `E_CASSETTE_TAMPERED`（见 §6 的幂等录制要求）。
3. 命中：直接返回 `output`，**逐字节等价**（不做二次采样、不做风格重写）。
4. 命中后仍必须过 `output_schema` 校验；不通过按 `invalid_schema` 走 fallback（防止 cassette 文件被手工篡改成非法结构）。schema 合法**不等于**内容可信：完整性由 §4.3 负责，二者不可互相顶替。

### 4.2 回放时如何得知历史 provider（冻结）

录制源 provider **不是猜出来的，是读出来的**：`capability.invoked` 事件必须携带 `provider`（该次调用实际产出输出的 provider 类），回放以**历史事件日志**为唯一依据。

1. 回放跑必须由历史事件日志驱动（`run --mode replay --journal <历史事件日志/result.json>`）。
2. 对每次能力调用，以 `(capability_id@version, canonical_input_hash)` 为键在历史日志中查 `capability.invoked` 事件，取该事件的 `provider` 作为本次查找的录制源。
3. 历史日志中**没有**该输入的调用记录（例如换了输入上下文）→ 不得猜：按 `E_CASSETTE_MISS` fail-closed。
4. 没有历史日志可用时（例如只拿到一个 cassette 目录做审计），目录内录制源**必须唯一**；出现 ≥2 个录制源即 `E_CASSETTE_AMBIGUOUS_SOURCE`，不得取首个、不得按新旧挑一个。

> 理由：目录枚举顺序是**环境事实**，只有事件日志记的是**历史事实**（当时到底用了谁）。「同一个输入换一个 provider 重录」后，回放必须仍能命中历史那一条，而不是命中目录里恰好排在前面的那一条。

### 4.3 完整性校验的调用时机（冻结）

`hash` 与 `prev_hash` 链不是可选装饰。下列**三个时机都必须校验**，任一不符即 `E_CASSETTE_TAMPERED`（fail-closed，不得降级为「schema 合法就放行」）：

| # | 时机 | 说明 |
|---|---|---|
| ① | **命中即校验**（强制） | 每次查找命中记录之前，先校验该文件的 `hash`（按 §2 定义重算）与文件内 `prev_hash` 链（genesis = 64 个 `0`，下一环 = 前一条记录的 `key`） |
| ② | **回放前置**（强制） | `replay` 跑开始之前对整库做一次完整性校验；任何文件不符即整体拒绝启动 |
| ③ | **validate 前置**（强制） | `validate` / `verify-cassettes` 类命令必须先做整库完整性校验，再报 schema 结果 |

- 只校验 `output_schema` 是不够的：攻击者把 `valence 0.08 → -0.9`、`mood_label tired → irritated` 这类**合法取值**改掉，schema 照样通过；`hash` + `prev_hash` 链能检出**非重算式**的改动（改一条记录却没重算其后全部 `hash`）。
- **`FROZEN-CASSETTE-INTEGRITY-1`（冻结条文 · 强度边界，不可被后续轮次放宽或反向解读）**：
  cassette 的哈希链**无密钥**，因此它**只能**检出**损坏与篡改**（内容被改、链断裂、同一 key 重复出现），
  **不是真实性（authenticity）保证**。任何能改写文件的人都可以连同 `hash` 与 `prev_hash` 一起**重算整条链**，
  链依然自洽 —— 因此「链自洽」**不构成**「未被第三方重写」的证据。
  真实性需要**外部锚定**：把链头（末条 `hash`）纳入**快照链头签名**或其它可信签名 / 时间戳载体，
  由内核侧锚定之后才具备真实性证据力。
  **V0 现状：无外部锚定实现 → 记 GAP**（不得写成「已实现链头签名」或「已保证未被篡改」）。
- 校验对象是**文件内容**，与 provider 是否确定性无关：`hash` 覆盖「记录去掉 `hash` 字段后的全部字段」。

## 5. miss 策略（默认 fail-closed）

| 策略 | 行为 | 使用场景 |
|---|---|---|
| `fail_closed`（**默认**） | 抛 `E_CASSETTE_MISS`，能力调用失败并落 `capability.fallback{reason:"on_cassette_miss"}`；**不得**静默切到远端 | 回放/审计/验收（AC-2、AC-13） |
| `fallback_chain` | 按 `providers[].priority` 回退到 `deterministic_rule`，并落 `capability.fallback` 事件 | 允许降质的离线演示 |
| `record_if_allowed` | 仅当显式开启 `--allow-record` 且当前 provider 为远端/本地模型时才录制新记录 | 首次采集，**禁止**用于回放跑 |

- 回放跑（`kernel replay` / `verify`）**必须**是 `fail_closed`：任何 miss 都意味着该次回放引入了历史中不存在的新决策，哈希必然分歧，应立刻失败而非掩盖。
- miss 事件必须可观测：`capability.fallback{capability, from_provider, to_provider, reason: on_cassette_miss}`。

### 5.1 错误码（冻结）

| 错误码 | 触发条件 | 行为 |
|---|---|---|
| `E_CASSETTE_MISS` | 历史日志中无该输入的调用记录；或该 provider 的录制文件/记录不存在 | fail-closed；落 `capability.fallback{reason: on_cassette_miss}` |
| `E_CASSETTE_AMBIGUOUS_SOURCE` | 无历史日志可依，且目录内录制源 ≥2 | 拒绝查找（不得取首个）；落 `capability.fallback{reason: on_cassette_ambiguous_source}` |
| `E_CASSETTE_TAMPERED` | `hash` 重算不符、`prev_hash` 链断裂、或同一 key 在文件内重复出现 | 拒绝命中；落 `capability.fallback{reason: on_cassette_tampered}` |

## 6. 存储与生命周期

- 位置：`cassettes/<capability_id>@<version>/<provider>.cassette.jsonl`（每个能力×provider 一个文件，便于按能力灰度与回滚）。
- 只追加（append-only）；重录 = 新文件 + 版本升级，禁止原地改历史记录。
- **同一 key 只保留首条（幂等录制）**：重复录制不得追加出重复记录。首条是录制当时的历史事实，后续重录不得改写它；若追加，文件内即出现重复 key，按 §4.1 视为文件损坏（`E_CASSETTE_TAMPERED`）。想换答案只能升级 `capability_version`（key 随之改变）。
- 新鲜度：`meta.recorded_at` 只作提示；**判据是 key 命中**，不看时间。
- 容量：单文件超过 32 MB 或记录数超过 50,000 时滚动（`*.cassette.1.jsonl`），滚动规则属实现细节，不影响 key。

## 7. 安全（硬性）

- **禁止**在 cassette 任何字段写入 token / api key / 凭据 / 完整请求头；`meta.redacted_fields` 必须列出被脱敏字段路径。
- 玩家可控文本进入能力输入时（prompt injection 面），cassette 只记录 `canonical_input_hash` 与结构化输出，**不**记录原始 prompt 文本；需要人读时另存脱敏摘要。
- cassette 属于交付物，同样受「产物中不得出现 secrets」的扫描约束。

## 8. 与 AC 的对应

- AC-2（确定性回放）：回放跑强制 `cassette_replay` + `fail_closed`，保证同日志重放哈希一致。
- AC-3 / AC-13：provider 切换（`remote_api` → `cassette_replay` → `deterministic_rule`）三类真跑，且切换只改数据声明。
- AC-13（完整性）：`hash` + `prev_hash` 链在「命中即校验 / 回放前置 / validate 前置」三个时机强制校验（§4.3）；`output_schema` 合法**不**免除完整性校验。
- R3（cassette 陈旧）：key 含 `capability_version` → 升级即 miss，不静默复用。
