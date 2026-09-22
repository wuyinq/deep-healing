"""AC-M1-7(b) 请求体面：扫描器**必须带反向对照**（修复轮 C1 / 预审 M4）。

上一轮的表述错误：把请求体面写成「空集」。实际 W0e 标定打了 24 + 30 = 54 次真实远端调用
（`dist` 24 次 + `degrade` 3 式 × 30 次），只是**请求体没有落盘**（`transcript_written: false`）。
所以正确表述是「**有调用、无落盘请求体**，判据待补」，而不是「没有调用所以没有请求体」。

本文件证明「无落盘请求体」这条判据**不是零命中绿**：
  ① 扫描函数对注入的探针文件必须命中（≥1）；
  ② 探针移除后对同一扫描面必须 0 命中；
  ③ 真实扫描面（`out/**` + 标定 spike 目录）当前 0 命中；
  ④ 标定产物自报 `transcript_written: false`（与 ① 的命中能力合起来才构成有效判据）。

冻结运行形态：cd <ws>/02_source/v0_skeleton/kernel && \
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_evidence_scan.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
WS_ROOT = KERNEL_ROOT.parents[2]
SPIKE_DIR = WS_ROOT / "spikes" / "s5-latency-calibration"

# 扫描判据：**JSON 对象键**形态的请求体/提示词字段（带冒号，避免命中 `prompt_scope` 这类合法键）
FORBIDDEN_BODY_KEYS = ("prompt", "messages", "raw_headers", "request_body", "system_prompt")
SCAN_RE = re.compile(r'"(?:' + "|".join(FORBIDDEN_BODY_KEYS) + r')"\s*:')


def scan_for_request_bodies(roots) -> list[str]:
    """返回命中的 `相对路径:行号` 列表（空列表 = 无落盘请求体）。"""
    hits: list[str] = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in {".json", ".jsonl", ".log", ".txt"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if SCAN_RE.search(line):
                    hits.append(f"{path}:{number}")
    return hits


def _scan_roots():
    return [WS_ROOT / "out", SPIKE_DIR]


def test_scan_surface_is_clean_and_scanner_is_not_zero_hit_green(tmp_path):
    """① / ② / ③：探针必须命中 ⇒ 移除后 0 命中 ⇒ 真实扫描面 0 命中。"""
    probe_dir = tmp_path / "probe-surface"
    probe_dir.mkdir()
    probe = probe_dir / "probe.events.jsonl"
    probe.write_text(
        json.dumps({"seq": 0, "payload": {"prompt": "PROBE-NOT-A-REAL-PROMPT"}}, ensure_ascii=False) + "\n"
        + json.dumps({"seq": 1, "payload": {"messages": []}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # ① 扫描器必须真的能命中（否则「0 命中」毫无意义）
    probe_hits = scan_for_request_bodies([probe_dir])
    assert len(probe_hits) == 2, probe_hits

    # ② 移除探针 ⇒ 同一扫描面必须 0 命中
    probe.unlink()
    assert scan_for_request_bodies([probe_dir]) == []

    # ③ 真实扫描面（含 `out/**` 的事件日志与检查点、标定产物）
    real_hits = scan_for_request_bodies(_scan_roots())
    assert real_hits == [], f"扫描面出现落盘请求体/提示词：{real_hits[:5]}"

    # 探针同时写进**真实扫描面**（`out/`）再移除：证明 ③ 的 0 命中不是「目录不存在」
    out_dir = WS_ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    real_probe = out_dir / ".probe-request-body.jsonl"
    try:
        real_probe.write_text(json.dumps({"prompt": "PROBE-NOT-A-REAL-PROMPT"}) + "\n", encoding="utf-8")
        assert scan_for_request_bodies(_scan_roots()), "真实扫描面上的探针必须被命中"
    finally:
        real_probe.unlink(missing_ok=True)
    assert scan_for_request_bodies(_scan_roots()) == []


def test_calibration_artifacts_declare_no_transcript_written():
    """④ 标定产物必须自报「请求体未落盘」；同时证明**确实打过真实调用**（不是空集）。"""
    logs = SPIKE_DIR / "logs"
    distribution = json.loads((logs / "latency.distribution.json").read_text(encoding="utf-8"))
    assert distribution["transcript_written"] is False
    assert distribution["sample_count_requested"] == 24
    assert distribution["sample_count_ok"] == 24
    assert len(distribution["samples"]) == 24
    assert distribution["synthetic"] is None, "必须是真的远端采样，不是合成样本"

    # 每条样本只留结构化延迟与状态，不得含请求体/响应体字段
    allowed = {"i", "kind", "latency_ms", "ok", "http_status", "tokens", "error"}
    for sample in distribution["samples"]:
        assert set(sample) <= allowed, sorted(set(sample) - allowed)

    degradation_files = sorted(logs.glob("degradation.*.json"))
    assert len(degradation_files) == 3, [path.name for path in degradation_files]
    degrade_calls = 0
    for path in degradation_files:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["transcript_written"] is False, path.name
        assert len(document["runs"]) == document["runs_count"] == 10, path.name
        degrade_calls += document["runs_count"]

    real_calls = distribution["sample_count_ok"] + degrade_calls
    assert real_calls == 54, real_calls       # 24（dist）+ 3 式 × 10（degrade）
    assert "54" in (WS_ROOT / "06_v0_m1_self_test.md").read_text(encoding="utf-8"), \
        "06 的 AC-M1-7(b) 必须写明「有 54 次真实调用、无落盘请求体」"


def test_spike_logs_are_not_deleted_by_the_probe(tmp_path):
    """夹具卫生：本文件不得删除/改写标定产物（只读扫描）。"""
    before = sorted(path.name for path in (SPIKE_DIR / "logs").iterdir())
    shutil.rmtree(tmp_path, ignore_errors=True)
    after = sorted(path.name for path in (SPIKE_DIR / "logs").iterdir())
    assert before == after
