"""修复轮 5 · **R4-C1（CRITICAL）**：`--replay` 命中被篡改的 cassette ⇒ 降级路径**不得回填** replay 源。

缺陷（architect 裁决 `.squad_tools/architect-ruling-r4c1.md`，三方独立复现）：
`--replay` 命中被篡改记录 ⇒ `CassetteTampered` ⇒ `on_error` 降级 ⇒ `registry.py::_fallback()`
（原 L494）**无条件** `record()`，把降级输出写回 `--cassette-dir` 指向的 replay 源目录
（5→6→7 条、追加记录分叉哈希链、`verify_chain()` 零告警）。违反：
① 本轮关闭判据 ⑤「篡改时零回填」；② `cassette.format.md` §5（`record_if_allowed` **禁止**用于回放跑）；
③ `_fallback()` 自身 docstring「禁止静默回填」；④ `--replay` 是审计路径，却改写它正在验证的产物。

关闭判据（任务书 §2 / 裁决 §4.2）：
  ① replay 命中篡改 ⇒ 源目录**跑前/跑后全量 sha256 逐字节相同**（且仍 exit ≠ 0 + `E_CASSETTE_TAMPERED`）；
  ② 同一 key 重复出现 ⇒ `verify_chain()` 判红（冻结条文 §4.1.2 / §6 / §5.1）；
  ③ 负例自证：退回 F-1 守卫（`if False and …` 形态，锚点命中数断言 = 1）⇒ ① 变红（回填复现）；
  ④ 回归：齐全未篡改 ⇒ exit 0；miss ⇒ exit ≠ 0 + `E_CASSETTE_MISS`。

判据纪律（裁决 §4.3）：凡「零写入 / 零回填」必须落到**目标目录前后哈希比对**，
不接受任何 summary 字段作为替代证据 —— 本文件 ① 只认 `_digests()` 的前后对照。

运行：
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_cassette_no_backfill_r5.py -q -p no:cacheprovider
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
SKELETON_ROOT = KERNEL_ROOT.parent                      # 02_source/v0_skeleton
PACK = "districts/xingfu-xiaoqu"
RELATION_FILE = "relation.infer__deterministic_rule.jsonl"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
E_TAMPERED = re.compile(r"(?m)^E_CASSETTE_TAMPERED\b")
E_MISS = re.compile(r"(?m)^E_CASSETTE_MISS\b")

# F-1 守卫锚点（`_fallback()` 内，唯一）；退回形态 = 还原「无条件 record」
F1_GUARD = ('        if provider_class == "deterministic_rule" and self._cassette is not None '
            'and not replay_mode:\n')
F1_REVERTED = ('        if provider_class == "deterministic_rule" and self._cassette is not None '
               'and not (False and replay_mode):\n')


# --------------------------------------------------------------------------- 工具
def _cli(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "deephealing_kernel", *args],
                          capture_output=True, text=True, cwd=str(cwd or KERNEL_ROOT), env=env or ENV)


def _digests(root: Path) -> dict[str, str]:
    """目录内全部 `*.jsonl` 的 sha256（**逐字节**判定用，不看任何自报字段）。"""
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.glob("*.jsonl"))}


def _line_count(root: Path, name: str = RELATION_FILE) -> int:
    return len([line for line in (root / name).read_text(encoding="utf-8").splitlines() if line.strip()])


def _record_into(cassettes: Path, tmp: Path, *, cwd: Path | None = None) -> Path:
    """**同 seed 先录一遍**（关键前提：不同 seed ⇒ 全 miss ⇒ 看不到回填）。"""
    cassettes.mkdir(parents=True, exist_ok=True)
    proc = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--ticks", "100", "--cognition",
                "--events", str(tmp / "rec" / "events.jsonl"), "--cassette-dir", str(cassettes), cwd=cwd)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return cassettes


def _tamper_last_relation(cassettes: Path) -> Path:
    """同 PM 配方 ②：改 `relation.infer` 末条记录的 `output.confidence`（不断链、不重签）。"""
    path = cassettes / RELATION_FILE
    lines = path.read_text(encoding="utf-8").splitlines()
    last = json.loads(lines[-1])
    last["output"]["confidence"] = 99999
    lines[-1] = json.dumps(last, ensure_ascii=False, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _append_duplicate_key(cassettes: Path) -> Path:
    """自洽追加一条**同 key** 记录 —— 正是回填产生的签名（链上合法、此前零告警）。"""
    from deephealing_kernel.snapshot import chained_hash

    path = cassettes / RELATION_FILE
    lines = path.read_text(encoding="utf-8").splitlines()
    last = json.loads(lines[-1])
    duplicate = dict(last)
    duplicate["prev_hash"] = last["key"]
    body = {name: value for name, value in duplicate.items() if name != "hash"}
    duplicate["hash"] = chained_hash(duplicate["prev_hash"], body)
    lines.append(json.dumps(duplicate, ensure_ascii=False, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _replay(cassettes: Path, tmp: Path, *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--ticks", "100", "--replay",
                "--cassette-dir", str(cassettes), "--cognition",
                "--events", str(tmp / "rep" / "events.jsonl"), cwd=cwd)


def _rewrite_records(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records) + "\n",
                    encoding="utf-8")


# --------------------------------------------------------------------------- ① 零回填（核心）
def test_replay_on_tampered_cassette_does_not_write_back(tmp_path):
    """① `--replay` 命中篡改 ⇒ 源目录前后**逐字节相同**（且仍 fail-closed）。"""
    cassettes = tmp_path / "cas"
    _record_into(cassettes, tmp_path)
    _tamper_last_relation(cassettes)
    before = _digests(cassettes)
    lines_before = _line_count(cassettes)

    proc = _replay(cassettes, tmp_path)
    combined = proc.stdout + proc.stderr
    # 可见性不得回退：仍然 exit ≠ 0 + 结构化诊断、无 traceback
    assert proc.returncode != 0, f"篡改仍必须 fail-closed，got exit {proc.returncode}"
    assert E_TAMPERED.search(combined), combined[-400:]
    assert "Traceback" not in combined, combined[-800:]

    after = _digests(cassettes)
    assert after == before, (
        "R4-C1：replay 源被回填（目录逐字节比对）\n"
        f"  before={before}\n  after ={after}"
    )
    assert _line_count(cassettes) == lines_before, "记录条数不得增长（5→6 即回填）"

    # 反零命中：确认降级**确实发生**（否则这条是「什么都没跑」的假绿）
    summary = json.loads((tmp_path / "rep" / "cognition" / "summary.json").read_text(encoding="utf-8"))
    assert summary["fallback_counts"].get("on_error", 0) >= 1, summary["fallback_counts"]
    assert summary["cassette_tampered_events"] >= 1
    # 回填被抑制这件事必须留痕（零回填 ≠ 零痕迹）
    suppressed = [entry for entry in summary["registry_journal"]
                  if entry.get("event") == "cassette.record_suppressed"]
    assert suppressed, "回放模式下被抑制的回填必须落 journal"


# --------------------------------------------------------------------------- ② 重复 key 判据
def test_verify_chain_reports_duplicate_key(tmp_path):
    """② 同一文件内同一 key 出现两次 ⇒ `verify_chain()` 判红（冻结 §4.1.2 / §6 / §5.1）。"""
    from deephealing_kernel.providers.cassette import CassetteStore

    root = tmp_path / "dup"
    store = CassetteStore(root)
    capability = {"id": "relation.infer", "version": "1.0.0"}
    payload = {"npc_id": "npc-1", "tick": 0}
    output = {"relations": [], "top_partner": None, "confidence": 0.0}
    meta = {"schema_version": "1.0.0", "recorded_at": "2026-09-22T00:00:00Z"}

    store.record(capability, "deterministic_rule", payload, output, meta)
    assert CassetteStore(root).verify_chain() == [], "单条记录必须完好（判据不得误伤）"

    store.record(capability, "deterministic_rule", payload, output, meta)   # 同 key 第二条（链自洽）
    problems = CassetteStore(root).verify_chain()
    assert problems, "同一 key 重复出现必须判红（此前零告警）"
    assert len(problems) == 1, problems
    assert "duplicate key" in problems[0], problems[0]


def test_prev_hash_only_tamper_forms_are_rejected(tmp_path):
    """F-3b：`prev_hash`-only 的两种形态都必须在 `verify_chain()` 与命令层判红。

    Raven r3 曾报「仅改 `prev_hash` ⇒ exit 0」；r4 实测 exit 1 并判其不可复现。本轮独立复跑
    （形态矩阵读数见 `03` §修复轮 5）：**两种形态都判红** ⇒ `verify_chain()` 无需结构性改动，
    由本用例钉住（形态 B 是更严的一格：改 `prev_hash` **并自洽重签**自身 `hash`，
    只剩「`prev_hash` 必须等于前一条的 `key`」这一条判据可抓它）。
    """
    from deephealing_kernel.providers.cassette import CassetteStore
    from deephealing_kernel.snapshot import chained_hash

    cassettes = tmp_path / "cas-prevhash"
    _record_into(cassettes, tmp_path)
    path = cassettes / RELATION_FILE
    base = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    form_a = [dict(record) for record in base]
    form_a[-1]["prev_hash"] = "ff" * 32                       # 形态 A：不重签
    _rewrite_records(path, form_a)
    assert CassetteStore(cassettes).verify_chain(), "形态 A（只改 prev_hash、不重签）必须判红"

    changed = {**base[-1], "prev_hash": "ff" * 32}
    body = {name: value for name, value in changed.items() if name != "hash"}
    form_b = [dict(record) for record in base]
    form_b[-1] = dict(body, hash=chained_hash("ff" * 32, body))   # 形态 B：自洽重签
    _rewrite_records(path, form_b)
    problems_b = CassetteStore(cassettes).verify_chain()
    assert problems_b, "形态 B（改 prev_hash 且自洽重签）必须判红"
    assert any("prev_hash mismatch" in problem for problem in problems_b), problems_b

    proc = _replay(cassettes, tmp_path)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0 and E_TAMPERED.search(combined), combined[-400:]


def test_duplicate_key_cassette_is_visible_at_command_layer(tmp_path):
    """②-命令层：重复 key（= 回填签名）⇒ exit ≠ 0 + `E_CASSETTE_TAMPERED`（修复前 exit 0）。"""
    cassettes = tmp_path / "cas-dup"
    _record_into(cassettes, tmp_path)
    _append_duplicate_key(cassettes)

    proc = _replay(cassettes, tmp_path)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, f"重复 key 必须 fail-closed，got exit {proc.returncode}"
    assert E_TAMPERED.search(combined), combined[-400:]
    summary = json.loads((tmp_path / "rep" / "cognition" / "summary.json").read_text(encoding="utf-8"))
    assert any("duplicate key" in problem for problem in summary["cassette_chain_errors"]), \
        summary["cassette_chain_errors"]


# --------------------------------------------------------------------------- ③ 负例自证
def test_negative_control_reverting_f1_guard_reproduces_backfill(tmp_path):
    """③ 退回 F-1 守卫 ⇒ ① 变红（回填复现）⇒ 判据有牙齿。

    变异**只发生在 `tmp_path` 的整树副本**上（交付树零改动，末尾逐字节复核）。
    """
    live_source = (KERNEL_ROOT / "deephealing_kernel" / "registry.py").read_text(encoding="utf-8")
    assert live_source.count(F1_GUARD) == 1, (
        f"F-1 守卫锚点命中数必须 = 1，实测 {live_source.count(F1_GUARD)}（锚点漂移 ⇒ 负例无效）"
    )

    copy_root = tmp_path / "patched" / "02_source"
    shutil.copytree(SKELETON_ROOT.parent, copy_root, ignore=shutil.ignore_patterns("__pycache__"))
    patched_kernel = copy_root / "v0_skeleton" / "kernel"
    target = patched_kernel / "deephealing_kernel" / "registry.py"
    patched_text = target.read_text(encoding="utf-8")
    assert patched_text.count(F1_GUARD) == 1
    target.write_text(patched_text.replace(F1_GUARD, F1_REVERTED), encoding="utf-8")
    assert target.read_text(encoding="utf-8").count(F1_REVERTED) == 1, "退回形态必须恰好生效 1 处"

    cassettes = tmp_path / "cas-neg"
    _record_into(cassettes, tmp_path, cwd=patched_kernel)
    _tamper_last_relation(cassettes)
    before = _digests(cassettes)
    lines_before = _line_count(cassettes)

    proc = _replay(cassettes, tmp_path, cwd=patched_kernel)
    after = _digests(cassettes)
    lines_after = _line_count(cassettes)

    assert after != before, (
        "负例无效：退回「无条件 record」后回填仍不复现 ⇒ 判据 ① 没有牙齿\n"
        f"  before={before}\n  after ={after}\n  exit={proc.returncode}"
    )
    assert lines_after == lines_before + 1, f"回填复现应恰好 +1 条，实测 {lines_before} → {lines_after}"

    # 交付树源码必须逐字节未变（本测试只在副本上变异）
    assert (KERNEL_ROOT / "deephealing_kernel" / "registry.py").read_text(encoding="utf-8") == live_source


# --------------------------------------------------------------------------- ③b 生效 replay_mode 传参
def test_effective_replay_mode_is_passed_into_fallback(tmp_path):
    """F-1 实现要求：生效 `replay_mode` 必须**显式传入** `_fallback()`。

    构造参数 `replay_mode=False` + 调用参数 `replay_mode=True`（不一致）⇒ 仍不得回填；
    只读 `self.default_replay_mode` 的实现会在这一格漏判。
    """
    from deephealing_kernel.providers.cassette import CassetteStore
    from deephealing_kernel.providers.deterministic_rule import DeterministicRuleProvider
    from deephealing_kernel.registry import CapabilityRegistry

    root = tmp_path / "cas-effective"
    root.mkdir(parents=True, exist_ok=True)
    registry = CapabilityRegistry(SKELETON_ROOT / "capabilities",
                                  SKELETON_ROOT / "capabilities" / "pins.json",
                                  cassette_store=CassetteStore(root), clock=None, replay_mode=False)
    registry.discover()
    registry.validate()
    registry.register_adapter("deterministic_rule", DeterministicRuleProvider())
    assert registry.default_replay_mode is False

    class _ExhaustedBudget:
        """强制走 `fallback.on_budget_exhausted`（确定性降级路径）。"""

        def allow_call(self, tick, npc_id):
            return False, "test_exhausted"

        def record(self, *args, **kwargs):  # pragma: no cover - 降级路径不记账
            return None

    result = registry.invoke("relation.infer",
                             {"npc_id": "npc-1", "tick": 0, "observations": [], "existing_relations": {}},
                             replay_mode=True, budget=_ExhaustedBudget())
    assert result.fallback_reason == "on_budget_exhausted"
    assert not list(root.glob("*.jsonl")), "生效 replay_mode=True ⇒ 降级不得写回 cassette 目录"


# --------------------------------------------------------------------------- ④ 回归
def test_regressions_clean_replay_green_and_miss_red(tmp_path):
    """④ 回归：齐全未篡改 ⇒ exit 0；miss ⇒ exit ≠ 0 + `E_CASSETTE_MISS`。"""
    cassettes = tmp_path / "cas-clean"
    _record_into(cassettes, tmp_path)
    before = _digests(cassettes)
    clean = _replay(cassettes, tmp_path)
    combined = clean.stdout + clean.stderr
    assert clean.returncode == 0, f"干净回放必须 exit 0：{combined[-400:]}"
    assert not E_TAMPERED.search(combined)
    assert _digests(cassettes) == before, "干净回放同样不得改动源目录"

    empty = tmp_path / "cas-empty"
    empty.mkdir(parents=True, exist_ok=True)
    miss = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--ticks", "100", "--replay",
                "--cassette-dir", str(empty), "--cognition",
                "--events", str(tmp_path / "miss" / "events.jsonl"))
    combined = miss.stdout + miss.stderr
    assert miss.returncode != 0, "miss 必须 fail-closed"
    assert E_MISS.search(combined), combined[-400:]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(__import__("pytest").main([__file__, "-q", "-p", "no:cacheprovider"]))
