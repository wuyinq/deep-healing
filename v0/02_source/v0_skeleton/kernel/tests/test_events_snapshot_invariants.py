"""事件链 / 检查点集合 / 脱敏 / 检查点自洽（设计 §6 R17、R18、R24、R25）。

每条判据都带**反向对照**（退回错误形态 ⇒ 断言必红）。

冻结运行形态：cd <ws>/02_source/v0_skeleton/kernel && \
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_events_snapshot_invariants.py -q -p no:cacheprovider
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_REL = "districts/xingfu-xiaoqu"
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921

from deephealing_kernel import snapshot as snapshot_mod  # noqa: E402
from deephealing_kernel import tick as tick_mod  # noqa: E402
from deephealing_kernel import cli as cli_mod  # noqa: E402
from deephealing_kernel.events import (  # noqa: E402
    AUTHORIZATION_VALUE,
    REDACTED_VALUE,
    EventLog,
    check_ech_invariants,
    redact,
)
from deephealing_kernel.pack import load_pack  # noqa: E402

_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def _run(out_dir: Path, ticks: int = 40, snapshot_every: int = 20) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    kernel = tick_mod.WorldKernel(
        pack=load_pack(PACK_DIR), seed=SEED, log=EventLog(out_dir / "e.jsonl"),
        snapshot_every=snapshot_every, checkpoint_dir=out_dir / "checkpoints",
    )
    kernel.run(ticks)
    return out_dir


def _checkpoint_doc(tick: int, state: dict, state_hash: str, chain: str = "a" * 64, rng: str = "b" * 64) -> dict:
    return {"tick": tick, "state": state, "state_hash": state_hash,
            "event_chain_hash": chain, "rng_state_digest": rng}


def _write(directory: Path, name: str, document: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- R17
def test_event_chain_invariants(tmp_path):
    """INVARIANT-ECH-1/2/3 逐条断言；含 ECH-2 / ECH-1 的反向对照。"""
    out = _run(tmp_path)
    parsed = list(EventLog(out / "e.jsonl").read_all())
    checkpoint_dir = out / "checkpoints"

    assert check_ech_invariants(parsed, checkpoint_dir) == []

    snapshot_events = [event for event in parsed if event.type == "snapshot.taken"]
    assert snapshot_events, "本用例需要至少一个 snapshot.taken 事件"

    # ECH-2：事件 payload 的 event_chain_hash == 该事件的 prev_hash
    for event in snapshot_events:
        assert event.payload["event_chain_hash"] == event.prev_hash

    # ECH-1：检查点字段的 event_chain_hash == hash(snapshot.taken 事件, tick == checkpoint.tick)
    for path in sorted(checkpoint_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        event = next(item for item in snapshot_events if item.tick == document["tick"])
        assert document["event_chain_hash"] == event.hash

    # ECH-3：hash_object(payload.rng_digests) == payload.rng_state_digest
    for event in snapshot_events:
        assert snapshot_mod.hash_object(event.payload["rng_digests"]) == event.payload["rng_state_digest"]
        assert event.payload["rng_digests"] == {
            name: event.payload["rng_digests"][name] for name in sorted(event.payload["rng_digests"])
        }

    # 反向对照 ①：把 payload 的 event_chain_hash 改成自身 hash（ECH-2 的经典 off-by-one）⇒ 必红
    mutated = []
    for event in parsed:
        if event.type == "snapshot.taken":
            payload = dict(event.payload)
            payload["event_chain_hash"] = event.hash
            mutated.append(dataclasses.replace(event, payload=payload))
        else:
            mutated.append(event)
    problems = check_ech_invariants(mutated, None)
    assert any("INVARIANT-ECH-2" in problem for problem in problems), problems

    # 反向对照 ②：把检查点里的 event_chain_hash 改一个字符 ⇒ ECH-1 必红
    broken_dir = tmp_path / "broken_checkpoints"
    shutil.copytree(checkpoint_dir, broken_dir)
    target = sorted(broken_dir.glob("*.json"))[0]
    document = json.loads(target.read_text(encoding="utf-8"))
    document["event_chain_hash"] = "0" * 64
    target.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    problems = check_ech_invariants(parsed, broken_dir)
    assert any("INVARIANT-ECH-1" in problem for problem in problems), problems


# --------------------------------------------------------------------------- R18
def test_verify_checkpoint_set_canonical(tmp_path):
    """非规范文件名 / 同 tick 重复文件 ⇒ `checkpoint_set_error`；规范命名 ⇒ 一致。"""
    state = {"schema_version": "1.0.0", "seed": 1, "tick": 20, "constants": {}, "entities": []}
    digest = snapshot_mod.hash_object(state)

    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left, "000020.json", _checkpoint_doc(20, state, digest))
    _write(right, "000020.json", _checkpoint_doc(20, state, digest))
    assert snapshot_mod.compare_checkpoints(left, right) == []

    # ① 非规范文件名 `25.json`
    _write(left, "25.json", _checkpoint_doc(25, state, digest))
    problems = snapshot_mod.compare_checkpoints(left, right)
    assert any(problem.startswith("checkpoint_set_error:non_canonical_filename:25.json") for problem in problems), problems
    (left / "25.json").unlink()

    # ② 同一 tick 两份文件（`000025.json` + `25.json`）⇒ duplicate_tick
    _write(left, "000025.json", _checkpoint_doc(25, state, digest))
    _write(left, "25.json", _checkpoint_doc(25, state, digest))
    problems = snapshot_mod.compare_checkpoints(left, right)
    assert any(problem.startswith("checkpoint_set_error:duplicate_tick:25") for problem in problems), problems
    assert any(problem.startswith("checkpoint_set_error:non_canonical_filename:25.json") for problem in problems), problems
    (left / "25.json").unlink()
    (left / "000025.json").unlink()

    # ③ tick 集合不同：必须逐个列出缺失，不得取交集当通过
    _write(right, "000040.json", _checkpoint_doc(40, state, digest))
    problems = snapshot_mod.compare_checkpoints(left, right)
    assert problems == ["missing_in_left:tick=40"], problems

    # ④ 字段缺失 / null 一律算 divergent（禁止 .get() 静默放过）
    broken = _checkpoint_doc(20, state, digest)
    del broken["rng_state_digest"]
    _write(left, "000020.json", broken)
    problems = snapshot_mod.compare_checkpoints(left, right)
    assert "missing_field:tick=20 field=rng_state_digest side=left" in problems, problems
    _write(left, "000020.json", _checkpoint_doc(20, state, digest))

    # ⑤ 字段差异必须带 tick + 逐字段 left/right
    _write(left, "000020.json", _checkpoint_doc(20, state, digest, chain="c" * 64))
    problems = snapshot_mod.compare_checkpoints(left, right)
    assert any(problem.startswith("field_diff:tick=20 field=event_chain_hash left=") for problem in problems), problems


# --------------------------------------------------------------------------- R24
def test_redact_fields_path_and_glob():
    """预审 M2：`redact_fields` 是主判据（点分路径 + glob），键名匹配只作补充。"""
    payload = {
        "headers": {"Authorization": "Bearer FIXTURE-NOT-A-CREDENTIAL-1", "X-Trace": "abc"},
        "raw_headers": {"Authorization": "Bearer FIXTURE-NOT-A-CREDENTIAL-2"},
        "env": {"FOO_API_KEY": "secret-value", "BAR": "keep-me"},
        "nested": [{"api_key": "nested-secret"}],
        "note": "keep",
    }
    out = redact(payload, ["headers.Authorization", "env.*_API_KEY"])

    assert out["headers"]["Authorization"] == AUTHORIZATION_VALUE
    assert out["env"]["FOO_API_KEY"] == REDACTED_VALUE          # glob 命中（硬编码键名表会漏这一条）
    assert out["note"] == "keep"
    assert out["headers"]["X-Trace"] == "abc"
    assert out["env"]["BAR"] == "keep-me"
    assert out["nested"][0]["api_key"] == REDACTED_VALUE         # 补充判据（键名匹配）
    # 原 payload 绝不被就地修改
    assert payload["env"]["FOO_API_KEY"] == "secret-value"
    assert payload["headers"]["Authorization"] == "Bearer FIXTURE-NOT-A-CREDENTIAL-1"

    # `payload.` 前缀形态（imagine.predict 的 redact_fields）也必须命中
    out_prefixed = redact(payload, ["payload.raw_headers.Authorization"])
    assert out_prefixed["raw_headers"]["Authorization"] == AUTHORIZATION_VALUE

    # 反向对照：只按硬编码键名匹配的实现会漏掉 env.FOO_API_KEY
    def naive_redact(document: dict) -> dict:
        result = {}
        for key, value in document.items():
            if key.lower() in {"authorization", "token"}:
                result[key] = AUTHORIZATION_VALUE
            elif isinstance(value, dict):
                result[key] = naive_redact(value)
            else:
                result[key] = value
        return result

    naive = naive_redact(payload)
    assert naive["env"]["FOO_API_KEY"] == "secret-value"
    assert naive["env"]["FOO_API_KEY"] != out["env"]["FOO_API_KEY"]


def test_event_log_applies_redaction_on_append(tmp_path):
    """追加前必须脱敏（Authorization 只允许 `Bearer ***REDACTED***` 形态落盘）。"""
    path = tmp_path / "e.jsonl"
    log = EventLog(path)
    log.append(1, "capability.invoked", "kernel", {
        "capability": {"id": "memory.reflect", "version": "1.0.0"},
        "provider": "remote_api", "ms": 12.5, "ok": True, "input_hash": "0" * 64,
        "headers": {"Authorization": "Bearer FIXTURE-NOT-A-CREDENTIAL-1"},
        "env": {"FOO_API_KEY": "secret-value"},
    })
    text = path.read_text(encoding="utf-8")
    assert "FIXTURE-NOT-A-CREDENTIAL-1" not in text
    assert "secret-value" not in text
    assert AUTHORIZATION_VALUE in text
    assert REDACTED_VALUE in text
    # 链仍然自洽
    assert len(list(EventLog(path).read_all())) == 1


# --------------------------------------------------------------------------- R25
def test_checkpoint_state_hash_selfconsistent(tmp_path):
    """预审 M3：逐检查点独立复算 `sha256(canonical_json(checkpoint["state"]))` 并与文件值比对。"""
    out = _run(tmp_path)
    checkpoint_dir = out / "checkpoints"
    assert snapshot_mod.check_checkpoint_integrity(checkpoint_dir) == []

    for path in sorted(checkpoint_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert snapshot_mod.state_hash(document["state"]) == document["state_hash"]

    # 反向对照：手改检查点 state_hash 一个字符 ⇒ 完整性断言必红
    broken_dir = tmp_path / "broken"
    shutil.copytree(checkpoint_dir, broken_dir)
    target = sorted(broken_dir.glob("*.json"))[0]
    document = json.loads(target.read_text(encoding="utf-8"))
    first = document["state_hash"][0]
    document["state_hash"] = ("1" if first != "1" else "2") + document["state_hash"][1:]
    target.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    problems = snapshot_mod.check_checkpoint_integrity(broken_dir)
    assert any("state_hash_mismatch" in problem for problem in problems), problems

    # 端到端：手改检查点的 state_hash 后 verify 必须非 0
    verify_dir = tmp_path / "verify_input"
    verify_dir.mkdir()
    shutil.copy(out / "e.jsonl", verify_dir / "e.jsonl")
    shutil.copytree(broken_dir, verify_dir / "checkpoints")
    proc = subprocess.run(
        [sys.executable, "-m", "deephealing_kernel", "verify",
         "--events", str(verify_dir / "e.jsonl"), "--pack", PACK_REL],
        capture_output=True, text=True, cwd=str(KERNEL_ROOT), env=_ENV,
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "state_hash_mismatch" in (proc.stdout + proc.stderr)


def test_dump_divergence_reports_component_level_diff(tmp_path):
    """`--dump-divergence` 的辅助函数必须给出组件级 diff。"""
    out = _run(tmp_path)
    left = out / "checkpoints"
    right = tmp_path / "mutated"
    shutil.copytree(left, right)
    target = sorted(right.glob("*.json"))[0]
    document = json.loads(target.read_text(encoding="utf-8"))
    document["state"]["entities"][0]["transform"]["pos_mm"]["x"] += 1
    document["state_hash"] = snapshot_mod.state_hash(document["state"])
    target.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    report = snapshot_mod.dump_divergence(left, right, int(target.stem))
    assert report["tick"] == int(target.stem)
    assert any("pos_mm" in key for key in report["component_diff"]), report


# --------------------------------------------------------------------------- B1（修复轮）
def _trauma_state(healed_pair):
    """同一逻辑状态、仅 `healed_tick` 不同、其余字段全同的两条 trauma_flag，按给定顺序放入。"""
    world = tick_mod.World(seed=SEED, constants={})
    world.spawn(tick_mod.Entity(id="npc-001", kind="npc"))
    world.set_component("npc-001", "trauma_flags", [
        {"id": "t-001", "severity": 2, "since_tick": 10, "healed_tick": healed_pair[0]},
        {"id": "t-001", "severity": 2, "since_tick": 10, "healed_tick": healed_pair[1]},
    ])
    return world.to_state()


def test_trauma_flags_total_order_is_input_order_independent():
    """修复轮 B1 / 预审 R3：`trauma_flags` 的排序键必须**全序**，否则同一逻辑状态两种 state_hash。

    原键 `(id, since_tick, severity)` 在「三者相同、仅 healed_tick 不同」时**平局**，而 `sorted`
    稳定 ⇒ 平局顺序由**输入顺序**决定 ⇒ 状态哈希随输入顺序漂移（跨进程 / 跨快照不可比）。
    """
    healed_first = _trauma_state((200, None))
    healed_last = _trauma_state((None, 200))

    assert healed_first["entities"][0]["trauma_flags"] == healed_last["entities"][0]["trauma_flags"]
    assert snapshot_mod.hash_object(healed_first) == snapshot_mod.hash_object(healed_last)

    # 反向对照：在**原始输入**上退回「三字段元组」键 ⇒ 同一对输入给出两种顺序（判据非零命中）；
    # 而全序键（契约序列化）对同一对输入给出**同一**顺序。
    def old_key(item):
        return (str(item.get("id", "")), int(item.get("since_tick", 0)), int(item.get("severity", 0)))

    def flag(healed_tick):
        return {"id": "t-001", "severity": 2, "since_tick": 10, "healed_tick": healed_tick}

    raw_first = [flag(200), flag(None)]
    raw_last = [flag(None), flag(200)]

    old_first = [item["healed_tick"] for item in sorted(raw_first, key=old_key)]
    old_last = [item["healed_tick"] for item in sorted(raw_last, key=old_key)]
    assert old_first == [200, None] and old_last == [None, 200]
    assert old_first != old_last, "旧键必须复现顺序漂移，否则本用例不是有效对照"

    new_first = [item["healed_tick"] for item in sorted(raw_first, key=snapshot_mod.canonical_json)]
    new_last = [item["healed_tick"] for item in sorted(raw_last, key=snapshot_mod.canonical_json)]
    assert new_first == new_last, "全序键必须让两种输入顺序收敛到同一结果"


# --------------------------------------------------------------------------- B2（修复轮）
def test_supplementary_redaction_uses_key_equivalence_not_substring():
    """修复轮 B2 / 预审 R8：补充判据必须是**键名整词等价族**，不是子串包含。

    子串包含会把 `world.schema.json` 允许的合法键名（`token_budget` / `authorization_level` /
    `api_keys_count` / `token-holder`）误判成密钥字段并整体脱敏 ⇒ 事件语义被静默破坏。
    """
    from deephealing_kernel import events as events_mod

    expectations = {
        "token": True, "authorization": True, "secret": True,
        "api_key": True, "apikey": True, "access_token": True,
        "Authorization": True, "TOKEN": True, "access-token": True,
        "token_budget": False, "authorization_level": False,
        "api_keys_count": False, "token-holder": False,
        "tokens_used": False, "secret_santa": False,
    }
    for key, expected in expectations.items():
        assert events_mod._should_redact(key, ["payload", key], []) is expected, key

    # 反向对照：退回**子串包含** ⇒ 四个合法键名必须被误判（证明上面的 False 不是恒 False）
    def substring(key):
        lowered = key.lower()
        return any(part in lowered for part in ("authorization", "api_key", "token"))

    for key in ("token_budget", "authorization_level", "api_keys_count", "token-holder"):
        assert substring(key) is True, key

    # 端到端：合法键名原样保留，真密钥字段脱敏（`redact_fields=[]` ⇒ 只走补充判据，不靠 glob）
    redacted = redact({
        "token_budget": 4096, "authorization_level": "public", "api_keys_count": 0,
        "token-holder": "npc-001", "token": "sk-real-secret", "api_key": "k-2",
    }, [])
    assert redacted["token_budget"] == 4096
    assert redacted["authorization_level"] == "public"
    assert redacted["api_keys_count"] == 0
    assert redacted["token-holder"] == "npc-001"
    assert redacted["token"] == REDACTED_VALUE
    assert redacted["api_key"] == REDACTED_VALUE


# --------------------------------------------------------------------------- C9（修复轮）
def test_checkpoint_path_points_at_real_file_relative_to_log_dir(tmp_path):
    """修复轮 C9 / 预审 R13：`snapshot.taken.payload.checkpoint_path` 必须指向**真实存在**的文件。

    语义（本轮钉死）：以**事件日志所在目录**为基准的相对路径；`run` 与 `replay` 都把检查点写在
    各自日志目录下的 `checkpoints/` ⇒ 两侧产物里该字段都指向真实文件，且**不含目录前缀**
    ⇒ run/replay/verify 三条路径的链尾逐 tick 一致（A1 的事件流比对依赖这一点）。
    """
    out_dir = tmp_path / "run"
    _run(out_dir, ticks=40, snapshot_every=20)

    snapshots = [obj for obj in (json.loads(line) for line in
                                 (out_dir / "e.jsonl").read_text(encoding="utf-8").splitlines())
                 if obj["type"] == "snapshot.taken"]
    assert [obj["payload"]["snapshot_tick"] for obj in snapshots] == [20, 40]
    for obj in snapshots:
        recorded = obj["payload"]["checkpoint_path"]
        assert recorded == f"checkpoints/{obj['payload']['snapshot_tick']:06d}.json"
        assert (out_dir / recorded).is_file(), recorded

    replay_dir = tmp_path / "replay"
    replay_dir.mkdir()
    assert cli_mod.main(["replay", "--events", str(out_dir / "e.jsonl"), "--pack", str(PACK_DIR),
                         "--checkpoint-every", "20", "--out", str(replay_dir)]) == 0
    replay_snapshots = [obj for obj in (json.loads(line) for line in
                                        (replay_dir / "replay.jsonl").read_text(encoding="utf-8").splitlines())
                        if obj["type"] == "snapshot.taken"]
    assert replay_snapshots
    for obj in replay_snapshots:
        recorded = obj["payload"]["checkpoint_path"]
        assert (replay_dir / recorded).is_file(), f"{recorded} 在 replay 产物里不存在"


def test_checkpoint_integrity_guards_json_roundtrip_premise(tmp_path):
    """C9 守卫断言：`check_checkpoint_integrity` 的前提（JSON 写读往返不改 canonical 形式）
    必须被**显式**检查并写进 docstring，而不是默默假设。"""
    out_dir = tmp_path / "run"
    _run(out_dir, ticks=40, snapshot_every=20)
    assert snapshot_mod.check_checkpoint_integrity(out_dir / "checkpoints") == []

    doc = snapshot_mod.check_checkpoint_integrity.__doc__ or ""
    assert "json_roundtrip_premise_violated" in doc
    assert "往返" in doc
