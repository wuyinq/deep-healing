"""快照与状态哈希（V0-M1 实现，契约冻结）。

    state_hash        = sha256(canonical_json(state))
    event_chain_hash  = 截至该 tick 的事件日志末条 hash
    rng_state_digest  = sha256(canonical_json(rng_state))，rng_state 按 stream 名排序

规范化规则见 snapshot.schema.json 的 normalization 字段；实现必须与
tools/canonical_json.py 共用同一套序列化，禁止各写一份。

**单一来源（设计 §4.1）**：本模块**不实现** canonical JSON，只按**文件路径**加载
`<v0_skeleton>/tools/canonical_json.py` 并转发（`canonical_json` / `canonical_bytes` /
`sha256_hex` / `hash_object` / `chained_hash` / `GENESIS_HASH`）。加载时断言「加载到的文件就是
该路径」——除 `DEEPHEALING_CANONICAL_JSON` 环境变量显式覆盖（测试注入用）外。

**compare_checkpoints 字符串协议（设计 §4.3，冻结签名 `-> list[str]`）**：
    missing_in_left:tick=<T> / missing_in_right:tick=<T>
    field_diff:tick=<T> field=<state_hash|rng_state_digest|event_chain_hash> left=<v> right=<v>
    missing_field:tick=<T> field=<F> side=<left|right>
    null_field:tick=<T> field=<F> side=<left|right>
    checkpoint_set_error:<原因>
空列表 = 一致。**禁止** zip / 索引配对比较（`x-ac2-criterion.forbidden_comparison`）。
（`side=` 是本轮对冻结协议前缀的**加法**扩展，用于定位缺失发生在哪一侧；前缀与字段名逐字未改。）
"""

from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path

COMPARE_FIELDS = ("state_hash", "rng_state_digest", "event_chain_hash")

# <v0_skeleton> = deephealing_kernel/ -> kernel/ -> v0_skeleton/
V0_SKELETON = Path(__file__).resolve().parents[2]
CANONICAL_JSON_PATH = V0_SKELETON / "tools" / "canonical_json.py"
CANONICAL_JSON_ENV = "DEEPHEALING_CANONICAL_JSON"


def _load_canonical_json_module():
    override = os.environ.get(CANONICAL_JSON_ENV)
    path = Path(override) if override else CANONICAL_JSON_PATH
    spec = importlib.util.spec_from_file_location("deephealing_canonical_json", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load canonical JSON module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    loaded = Path(module.__file__).resolve() if getattr(module, "__file__", None) else None
    if not override and loaded != CANONICAL_JSON_PATH.resolve():
        raise ImportError(
            f"canonical JSON single-source violation: loaded {loaded} instead of {CANONICAL_JSON_PATH}"
        )
    return module


_CANONICAL = _load_canonical_json_module()

canonical_json = _CANONICAL.canonical_json
canonical_bytes = _CANONICAL.canonical_bytes
sha256_hex = _CANONICAL.sha256_hex
hash_object = _CANONICAL.hash_object
chained_hash = _CANONICAL.chained_hash
GENESIS_HASH = _CANONICAL.GENESIS_HASH


@dataclass(frozen=True, slots=True)
class Snapshot:
    tick: int
    state: dict
    state_hash: str
    event_chain_hash: str
    rng_state_digest: str

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "state": self.state,
            "state_hash": self.state_hash,
            "event_chain_hash": self.event_chain_hash,
            "rng_state_digest": self.rng_state_digest,
        }


def state_hash(state: dict) -> str:
    return hash_object(state)


def take_snapshot(world: dict, tick: int, event_chain_hash: str, rng_state_digest: str) -> Snapshot:
    """冻结签名收 `dict`；调用方传 `world.to_state()`（预审 L2）。"""
    return Snapshot(
        tick=int(tick),
        state=world,
        state_hash=hash_object(world),
        event_chain_hash=event_chain_hash,
        rng_state_digest=rng_state_digest,
    )


def write_checkpoint(snapshot: Snapshot, out_dir: Path) -> Path:
    """写 `checkpoints/{tick:06d}.json`（设计 §4.3 冻结命名；桩注释的 `<tick>.json` 是旧文）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{snapshot.tick:06d}.json"
    path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _load_checkpoint_dir(directory: Path) -> tuple[dict[int, dict], list[str]]:
    """读检查点目录；返回 (tick -> 文档, 集合级错误)。文件名必须是 `{tick:06d}.json`。"""
    directory = Path(directory)
    errors: list[str] = []
    if not directory.is_dir():
        return {}, [f"checkpoint_set_error:missing_directory:{directory}"]
    by_tick: dict[int, dict] = {}
    seen_names: dict[int, str] = {}
    for path in sorted(directory.glob("*.json")):
        stem = path.stem
        if not stem.isdigit():
            errors.append(f"checkpoint_set_error:non_numeric_filename:{path.name}")
            continue
        tick = int(stem)
        canonical = f"{tick:06d}"
        if stem != canonical:
            # 非规范名（如 25.json）：旧实现用 {int(stem): path} 会静默遮蔽同名 tick 的另一份 → 假绿
            errors.append(f"checkpoint_set_error:non_canonical_filename:{path.name}")
            if tick in seen_names:
                errors.append(
                    f"checkpoint_set_error:duplicate_tick:{tick} ({seen_names[tick]}, {path.name})"
                )
            continue
        if tick in seen_names:
            errors.append(f"checkpoint_set_error:duplicate_tick:{tick} ({seen_names[tick]}, {path.name})")
            continue
        try:
            by_tick[tick] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"checkpoint_set_error:unparsable:{path.name}:{exc}")
            continue
        seen_names[tick] = path.name
    return by_tick, errors


def compare_checkpoints(left_dir: Path, right_dir: Path) -> list[str]:
    """逐检查点比对三字段；返回分歧列表（空 = 一致，AC-M1-2 判据）。

    满足 `snapshot.schema.json` 的 `x-ac2-criterion`：
      (1) tick 集合必须完全相同（逐个列出缺失，不取交集当通过）
      (2) 逐点比 state_hash / rng_state_digest / event_chain_hash
      (3) 检查点集合本身必须规范（`{tick:06d}.json`，同 tick 不得重复）
      (4) 字段缺失或为 null 一律算 divergent
      (5) 强制 run ↔ replay 比对（由调用方保证）
    """
    left, left_errors = _load_checkpoint_dir(left_dir)
    right, right_errors = _load_checkpoint_dir(right_dir)
    if left_errors or right_errors:
        return left_errors + right_errors

    divergences: list[str] = []
    for tick in sorted(set(left) - set(right)):
        divergences.append(f"missing_in_right:tick={tick}")
    for tick in sorted(set(right) - set(left)):
        divergences.append(f"missing_in_left:tick={tick}")

    for tick in sorted(set(left) & set(right)):
        left_doc, right_doc = left[tick], right[tick]
        for field in COMPARE_FIELDS:
            left_missing = field not in left_doc
            right_missing = field not in right_doc
            if left_missing or right_missing:
                if left_missing:
                    divergences.append(f"missing_field:tick={tick} field={field} side=left")
                if right_missing:
                    divergences.append(f"missing_field:tick={tick} field={field} side=right")
                continue
            left_value, right_value = left_doc[field], right_doc[field]
            if left_value is None:
                divergences.append(f"null_field:tick={tick} field={field} side=left")
            if right_value is None:
                divergences.append(f"null_field:tick={tick} field={field} side=right")
            if left_value is not None and right_value is not None and left_value != right_value:
                divergences.append(
                    f"field_diff:tick={tick} field={field} left={left_value} right={right_value}"
                )
    return divergences


def check_checkpoint_integrity(checkpoint_dir: Path) -> list[str]:
    """独立完整性断言（预审 M3）：逐检查点用 `sha256(canonical_json(checkpoint["state"]))`
    复算 `state_hash` 并与文件值逐位比对。

    与 run/replay 无关 ⇒ 能挡住「`state_hash` 被算在错误对象上」这类**两条路径共有**的系统性错误。
    它**挡不住** C1 的链重算伪造（伪造者保留的检查点自身仍然自洽）。

    **前提（修复轮 C10 / 预审 R14，本轮显式声明）**：本函数从**文件**读回 `state` 再复算，而
    `state_hash` 当初是对**内存中**的 `to_state()` 结果算的 ⇒ 两者相等的前提是
    「`canonical_json(state)` 对 **JSON 写读往返不变**」。该前提在当前 state 形状
    （int / str / float / list / dict / None）下成立；一旦被破坏（引入 `Decimal` / `tuple` /
    `datetime` / 超大浮点等），本函数会**显式**报 `json_roundtrip_premise_violated`，而不是静默漂移。

    ⚠ **独立性边界（修复轮 C10 / 预审 R2）**：本断言在 **run↔replay 轴**上独立，但**共用**
    `canonical_json` ⇒ **挡不住序列化实现本身的缺陷**。契约口径的独立序列化判据见
    `tests/test_canonical_contract.py`（内嵌契约要求的最小序列化并与内核实现逐位对照）。
    """
    by_tick, errors = _load_checkpoint_dir(checkpoint_dir)
    problems = list(errors)
    for tick in sorted(by_tick):
        doc = by_tick[tick]
        if "state" not in doc or "state_hash" not in doc:
            problems.append(f"integrity_error:tick={tick} missing state or state_hash")
            continue
        # 守卫：显式校验「canonical_json(state) 对 JSON 写读往返不变」这一前提（C9）
        if hash_object(json.loads(canonical_json(doc["state"]))) != hash_object(doc["state"]):
            problems.append(f"integrity_error:tick={tick} json_roundtrip_premise_violated")
        recomputed = hash_object(doc["state"])
        if recomputed != doc["state_hash"]:
            problems.append(
                f"integrity_error:tick={tick} state_hash_mismatch recomputed={recomputed} recorded={doc['state_hash']}"
            )
    return problems


def _flatten(value: object, prefix: str = "") -> dict[str, object]:
    flat: dict[str, object] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            flat.update(_flatten(value[key], f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            flat.update(_flatten(item, f"{prefix}[{index}]"))
    else:
        flat[prefix] = value
    return flat


def dump_divergence(left_dir: Path, right_dir: Path, tick: int) -> dict:
    """`--dump-divergence`：输出分歧 tick 的组件级 diff（根因定位辅助）。"""
    left, _ = _load_checkpoint_dir(left_dir)
    right, _ = _load_checkpoint_dir(right_dir)
    left_doc = left.get(int(tick))
    right_doc = right.get(int(tick))
    report: dict = {"tick": int(tick), "left_present": left_doc is not None, "right_present": right_doc is not None,
                    "field_diff": {}, "component_diff": {}}
    if left_doc is None or right_doc is None:
        return report
    for field in COMPARE_FIELDS:
        if left_doc.get(field) != right_doc.get(field):
            report["field_diff"][field] = {"left": left_doc.get(field), "right": right_doc.get(field)}
    left_flat = _flatten(left_doc.get("state", {}))
    right_flat = _flatten(right_doc.get("state", {}))
    for key in sorted(set(left_flat) | set(right_flat)):
        if left_flat.get(key) != right_flat.get(key):
            report["component_diff"][key] = {"left": left_flat.get(key), "right": right_flat.get(key)}
    return report
