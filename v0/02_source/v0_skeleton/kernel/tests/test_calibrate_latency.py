"""AC-M1-6：W0e 标定工具链（设计 §6 R19）—— 合成样本自证 + 冻结物绑定 + 漂移守卫。

自证结构（全部离线、不联网、不消耗凭据）：
  ① 干净合成样本 ⇒ `dist` 判 usable、`derive` 产出声明值、`degrade` 落在声明区间、`check` exit 0；
  ② 污染合成样本（重尾）⇒ `dist` 判 degraded、`derive` **fail-closed** 拒绝产出任何声明值；
  ③ 陈旧声明值（把 adopted 压低）⇒ `degrade` 的区间判据必须变红（证明该闸不是零命中绿）；
  ④ 分布日志早于规则文件 ⇒ `derive` 必须拒绝（防自证第 1 条）；
  ⑤ 冻结物 sha256 必须与 round-3（002 工作区）逐字节一致（预审 C3 关闭判据）。

冻结运行形态：cd <ws>/02_source/v0_skeleton/kernel && \
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_calibrate_latency.py -q -p no:cacheprovider
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
WS_ROOT = KERNEL_ROOT.parents[2]
SPIKE_DIR = WS_ROOT / "spikes" / "s5-latency-calibration"
RULE_FILE = SPIKE_DIR / "DERIVATION-RULE.frozen.md"
RANGE_FILE = SPIKE_DIR / "ACCEPTED-DEGRADATION-RANGE.frozen.md"

FROZEN_RULE_SHA256 = "7590eab4b765671860eaa50b68de807606581bfdd439cb3aa6fe2d953edb0feb"
FROZEN_RANGE_SHA256 = "713dba90df07f63e685fc98dcf276769ba37f2617f9c8a4b38319d8c174bddb4"


def _load_tool():
    path = KERNEL_ROOT / "tools" / "calibrate_latency.py"
    spec = importlib.util.spec_from_file_location("calibrate_latency_under_test", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_offset_table(text: str) -> dict[str, int]:
    table: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"^\|\s*`([a-z.]+)`\s*\|\s*(\d+)\s*\|", line.strip())
        if match:
            table[match.group(1)] = int(match.group(2))
    return table


def _parse_accepted_range(text: str) -> dict[str, tuple[float, float]]:
    table: dict[str, tuple[float, float]] = {}
    for line in text.splitlines():
        name = re.search(r"`(strict|adopted|loose)`", line)
        window = re.search(r"\*\*(\d+\.\d+)\s*[–-]\s*(\d+\.\d+)\*\*", line)
        if name and window:
            table[name.group(1)] = (float(window.group(1)), float(window.group(2)))
    return table


# --------------------------------------------------------------------------- ⑤ 冻结物绑定
def test_frozen_artifacts_are_byte_identical_to_round3():
    """预审 C3：两份冻结物必须是 round-3（002 工作区）同名文件的逐字节副本。"""
    assert _sha256(RULE_FILE) == FROZEN_RULE_SHA256
    assert _sha256(RANGE_FILE) == FROZEN_RANGE_SHA256
    assert TOOL.FROZEN_RULE_SHA256 == FROZEN_RULE_SHA256
    assert TOOL.FROZEN_RANGE_SHA256 == FROZEN_RANGE_SHA256


def test_mirrored_constants_match_frozen_files():
    """漂移守卫：工具里的 offset 表与区间表必须与冻结文件逐条一致。"""
    assert TOOL.CAP_OFFSET_MS == _parse_offset_table(RULE_FILE.read_text(encoding="utf-8"))
    assert TOOL.ACCEPTED_RANGE == _parse_accepted_range(RANGE_FILE.read_text(encoding="utf-8"))
    assert TOOL.CAP_OFFSET_MS, "offset 表解析为空（冻结文件格式变化会静默让守卫失效）"
    assert TOOL.ACCEPTED_RANGE, "区间表解析为空"


# --------------------------------------------------------------------------- ① 干净链
def test_synthetic_clean_chain_is_green(tmp_path):
    dist_path = tmp_path / "clean.distribution.json"
    calibration_path = tmp_path / "clean.calibration.json"
    degrade_path = tmp_path / "clean.degradation.json"

    assert TOOL.main(["dist", "--synthetic", "clean", "--out", str(dist_path)]) == 0
    dist = json.loads(dist_path.read_text(encoding="utf-8"))
    assert dist["environment_class"] == "usable"
    assert dist["synthetic"] == "clean"
    assert dist["sample_count_ok"] == 24
    assert dist["transcript_written"] is False

    assert TOOL.main(["derive", "--dist", str(dist_path), "--out", str(calibration_path)]) == 0
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    assert calibration["refuses_to_declare"] is False
    assert calibration["rule_frozen_before_measurement"] is True
    assert calibration["adopted_differs_from_max"] is True
    table = calibration["four_value_table"]
    assert table["adopted_ms"] >= table["p95_ms"]
    assert table["adopted_ms"] != table["max_ms"]
    assert calibration["per_capability"]["emotion.appraise"]["adopted_ms"] == table["adopted_ms"]

    assert TOOL.main(["degrade", "--formula", "adopted", "--runs", "24",
                      "--calibration", str(calibration_path), "--synthetic", "clean",
                      "--out", str(degrade_path)]) == 0
    degrade = json.loads(degrade_path.read_text(encoding="utf-8"))
    assert degrade["within_accepted_range"] is True
    assert 0.0 <= degrade["degradation_rate"] <= 0.30

    for formula in ("strict", "adopted", "loose"):
        out = tmp_path / f"clean.{formula}.json"
        assert TOOL.main(["degrade", "--formula", formula, "--runs", "24",
                          "--calibration", str(calibration_path), "--synthetic", "clean",
                          "--out", str(out)]) == 0
    args = ["check", "--calibration", str(calibration_path), "--dist", str(dist_path)]
    for formula in ("strict", "adopted", "loose"):
        args += ["--degrade", f"{formula}={tmp_path / f'clean.{formula}.json'}"]
    assert TOOL.main(args) == 0


# --------------------------------------------------------------------------- ② 污染样本
def test_synthetic_polluted_fails_closed(tmp_path):
    """污染（重尾）样本 ⇒ dist 判 degraded、derive fail-closed 不产出任何声明值。"""
    dist_path = tmp_path / "polluted.distribution.json"
    calibration_path = tmp_path / "polluted.calibration.json"

    assert TOOL.main(["dist", "--synthetic", "polluted", "--out", str(dist_path)]) == 1
    dist = json.loads(dist_path.read_text(encoding="utf-8"))
    assert dist["environment_class"] == "degraded"
    assert dist["environment_class_reasons"]
    # 原始分布必须落盘（不得只留结论）
    assert len(dist["samples"]) == 24
    assert dist["p90_ms"] > 20000

    assert TOOL.main(["derive", "--dist", str(dist_path), "--out", str(calibration_path)]) == 1
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    assert calibration["refuses_to_declare"] is True
    assert calibration["per_capability"] == {}, "degraded 环境必须**不产出**任何声明值"
    assert calibration["four_value_table"]["p90_ms"] == dist["p90_ms"]

    # 没有声明值 ⇒ degrade 必须 fail-closed（不得凭空测降级率）
    assert TOOL.main(["degrade", "--formula", "adopted", "--runs", "5",
                      "--calibration", str(calibration_path), "--synthetic", "clean",
                      "--out", str(tmp_path / "x.json")]) == 1
    # check 也必须非 0（判据 ②③④ 无从成立）
    assert TOOL.main(["check", "--calibration", str(calibration_path), "--dist", str(dist_path)]) == 1


# --------------------------------------------------------------------------- ③ 陈旧声明值
def test_stale_declared_value_breaks_accepted_range(tmp_path):
    """把 adopted 压低到远低于 p95 ⇒ 降级率越界 ⇒ `degrade` 必须变红（区间闸不是零命中绿）。"""
    dist_path = tmp_path / "clean.distribution.json"
    calibration_path = tmp_path / "clean.calibration.json"
    assert TOOL.main(["dist", "--synthetic", "clean", "--out", str(dist_path)]) == 0
    assert TOOL.main(["derive", "--dist", str(dist_path), "--out", str(calibration_path)]) == 0

    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    for values in calibration["per_capability"].values():
        values["adopted_ms"] = 900
    stale_path = tmp_path / "stale.calibration.json"
    stale_path.write_text(json.dumps(calibration, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")

    out = tmp_path / "stale.degradation.json"
    assert TOOL.main(["degrade", "--formula", "adopted", "--runs", "24",
                      "--calibration", str(stale_path), "--synthetic", "clean", "--out", str(out)]) == 1
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["within_accepted_range"] is False
    assert report["degradation_rate"] > report["accepted_range"][1]


# --------------------------------------------------------------------------- ④ 时间戳顺序
def test_derive_refuses_when_distribution_predates_rule(tmp_path):
    """防自证第 1 条：分布日志早于规则文件 ⇒ `derive` 必须拒绝。"""
    dist_path = tmp_path / "clean.distribution.json"
    assert TOOL.main(["dist", "--synthetic", "clean", "--out", str(dist_path)]) == 0
    early = RULE_FILE.stat().st_mtime - 3600
    os.utime(dist_path, (early, early))  # 只改**测试夹具**的 mtime；冻结文件一律不动

    calibration_path = tmp_path / "backdated.calibration.json"
    assert TOOL.main(["derive", "--dist", str(dist_path), "--out", str(calibration_path)]) == 1
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    assert calibration["rule_frozen_before_measurement"] is False


def test_registry_is_idempotent(tmp_path, capsys):
    """F1（修复轮 2 / Sentinel Bug#9）：连跑两次 `registry` ⇒ `calibration.registry.json` 逐字节不变。

    修复前 `cmd_registry` 每次写入 `registry_written_at: time.strftime(...)` ⇒ 每跑一次就改写该文件，
    使 `V0_M1.sha256` 的自校验由「642 OK / 0 非 OK」变成「641 OK / 1 FAILED」。

    **夹具卫生**：本用例先留存原始字节，断言失败时在 `finally` 里逐字节复原并再断言复原成功
    （绝不把交付面/测量产物留在被改写的状态）。
    """
    registry_path = SPIKE_DIR / "calibration.registry.json"
    original = registry_path.read_bytes()
    try:
        first = capsys.readouterr()
        assert TOOL.main(["registry"]) == 0
        after_first = registry_path.read_bytes()
        assert TOOL.main(["registry"]) == 0
        after_second = registry_path.read_bytes()

        assert after_first == original, "幂等：第一次执行不得改写既有 registry（内容字段未变）"
        assert after_second == original, "幂等：连跑两次后 registry 必须逐字节不变"
        assert _sha256(registry_path) == hashlib.sha256(original).hexdigest()

        report = json.loads([line for line in capsys.readouterr().out.splitlines() if line.startswith("{")][0])
        assert report["unchanged"] is True
        assert report["sha256"] == hashlib.sha256(original).hexdigest()
        del first
    finally:
        if registry_path.read_bytes() != original:
            registry_path.write_bytes(original)
        assert registry_path.read_bytes() == original, "夹具必须逐字节复原 registry"


def test_registry_still_rewrites_when_content_changes(tmp_path):
    """F1 反向对照：内容字段真的变了 ⇒ 必须**写盘**（幂等不等于「永不更新」）。"""
    registry_path = SPIKE_DIR / "calibration.registry.json"
    original = registry_path.read_bytes()
    try:
        document = json.loads(original.decode("utf-8"))
        document["frozen_rule"]["sha256"] = "0" * 64          # 伪造一处内容字段（仅在夹具副本上）
        registry_path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        assert TOOL.main(["registry"]) == 0
        restored = json.loads(registry_path.read_text(encoding="utf-8"))
        assert restored["frozen_rule"]["sha256"] == FROZEN_RULE_SHA256, "内容不一致时必须重写"
    finally:
        registry_path.write_bytes(original)
        assert registry_path.read_bytes() == original, "夹具必须逐字节复原 registry"


def test_registry_registers_three_frozen_artifacts():
    """`registry` 必须登记三份冻结物（规则 / 区间 / 环境判定）的 sha256 与 mtime。"""
    registry_path = SPIKE_DIR / "calibration.registry.json"
    assert registry_path.is_file(), "registry 必须先于采样落盘（防自证第 1/3/4 条）"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["frozen_rule"]["sha256"] == FROZEN_RULE_SHA256
    assert registry["accepted_degradation_range"]["sha256"] == FROZEN_RANGE_SHA256
    assert registry["environment_class_rule"]["sha256"] == _sha256(SPIKE_DIR / "ENVIRONMENT-CLASS.frozen.md")
    # R2 / P-9：`path` 是**相对 registry 目录**的路径 ⇒ 必须用工具的运行时解析器解析（不是相对 cwd）
    assert TOOL.resolve_registry_path(registry["frozen_rule"]["path"]).stat().st_mtime < registry_path.stat().st_mtime
    assert TOOL.resolve_registry_path(registry["environment_class_rule"]["path"]).stat().st_mtime < registry_path.stat().st_mtime


def test_registry_paths_are_relative_to_registry_dir():
    """R2 / P-9 / 3A-C3：registry 内**零绝对路径**，且每条 `path` 都能在运行时解析到真实文件。"""
    registry_path = SPIKE_DIR / "calibration.registry.json"
    text = registry_path.read_text(encoding="utf-8")
    registry = json.loads(text)
    assert "/Users/" not in text, "registry 不得含任何绝对路径（换机/克隆后失效，且泄漏本地目录结构）"
    for key in ("frozen_rule", "accepted_degradation_range", "environment_class_rule"):
        value = registry[key]["path"]
        assert not value.startswith("/"), f"{key}.path 必须是相对路径：{value}"
        assert ".." not in Path(value).parts, f"{key}.path 不得逃出 registry 目录：{value}"
        assert TOOL.resolve_registry_path(value).is_file(), f"{key}.path 解析不到文件：{value}"


def test_registry_force_rewrite_migrates_absolute_paths():
    """R2 / P-9 迁移机制：盘上残留绝对路径 ⇒ `registry` 必须真的把它们迁移成相对路径。

    两条迁移路径都要真跑：
      ① 默认口径：检测到**格式漂移**（绝对路径）⇒ 自动重写迁移（并如实报告迁移了哪些键）；
      ② `--force-rewrite`：显式强制重写，同样必须迁移。
    **负例**：迁移后盘上若仍含绝对路径，本用例的断言必须红。
    """
    registry_path = SPIKE_DIR / "calibration.registry.json"
    original = registry_path.read_bytes()
    keys = ("frozen_rule", "accepted_degradation_range", "environment_class_rule")

    def inject_absolute_paths() -> None:
        document = json.loads(registry_path.read_text(encoding="utf-8"))
        for key in keys:
            document[key]["path"] = str(SPIKE_DIR / Path(document[key]["path"]).name)  # 注回**绝对**路径
        registry_path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        assert "/Users/" in registry_path.read_text(encoding="utf-8"), "夹具未注入绝对路径"

    try:
        # ① 默认口径必须自动迁移
        inject_absolute_paths()
        assert TOOL.main(["registry"]) == 0
        migrated_text = registry_path.read_text(encoding="utf-8")
        assert "/Users/" not in migrated_text, "默认口径下格式漂移必须被自动迁移"
        migrated = json.loads(migrated_text)
        for key in keys:
            assert not migrated[key]["path"].startswith("/"), f"{key}.path 未迁移：{migrated[key]['path']}"
            assert TOOL.resolve_registry_path(migrated[key]["path"]).is_file()
            assert migrated[key]["sha256"] == TOOL.sha256_file(SPIKE_DIR / Path(migrated[key]["path"]).name)

        # ② `--force-rewrite` 同样必须迁移（显式强制路径）
        inject_absolute_paths()
        assert TOOL.main(["registry", "--force-rewrite"]) == 0
        forced_text = registry_path.read_text(encoding="utf-8")
        assert "/Users/" not in forced_text
        assert json.loads(forced_text)["frozen_rule"]["sha256"] == FROZEN_RULE_SHA256

        # ③ 迁移后回到幂等：再跑两次（含 force）逐字节不变
        assert TOOL.main(["registry"]) == 0
        assert registry_path.read_text(encoding="utf-8") == forced_text
        assert TOOL.main(["registry", "--force-rewrite"]) == 0
        assert registry_path.read_text(encoding="utf-8") == forced_text
    finally:
        registry_path.write_bytes(original)
        assert registry_path.read_bytes() == original, "夹具必须逐字节复原 registry"


# --------------------------------------------------------------------------- C5（修复轮）
def test_check_recomputes_all_five_quantiles(tmp_path, capsys):
    """修复轮 C5 / 预审 R12：`check` 必须**独立重算** p50/p90/p95/p99/max 五个量，逐个比对。

    只比 p90 时，把 p95 / max 改掉仍能 exit 0（判据零命中）；这里逐量反证。
    """
    dist_path = tmp_path / "clean.distribution.json"
    calibration_path = tmp_path / "clean.calibration.json"
    assert TOOL.main(["dist", "--synthetic", "clean", "--out", str(dist_path)]) == 0
    assert TOOL.main(["derive", "--dist", str(dist_path), "--out", str(calibration_path)]) == 0

    base_args = ["check", "--calibration", str(calibration_path), "--dist", str(dist_path)]
    assert TOOL.main(base_args) == 0
    capsys.readouterr()

    original = json.loads(calibration_path.read_text(encoding="utf-8"))
    samples = [sample["latency_ms"] for sample in json.loads(dist_path.read_text(encoding="utf-8"))["samples"]]
    recomputed = {
        "p50_ms": TOOL.nearest_rank(samples, 0.50), "p90_ms": TOOL.nearest_rank(samples, 0.90),
        "p95_ms": TOOL.nearest_rank(samples, 0.95), "p99_ms": TOOL.nearest_rank(samples, 0.99),
        "max_ms": max(samples),
    }
    for name, value in recomputed.items():
        assert original["four_value_table"][name] == value, name

    for name in ("p50_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms"):
        tampered = json.loads(json.dumps(original))
        tampered["four_value_table"][name] = recomputed[name] + 1
        path = tmp_path / f"tampered.{name}.json"
        path.write_text(json.dumps(tampered, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        assert TOOL.main(["check", "--calibration", str(path), "--dist", str(dist_path)]) == 1, name
        assert name in capsys.readouterr().err, f"{name} 的篡改未被 check 归因"


# --------------------------------------------------------------------------- C4（修复轮）
def test_check_reports_adopted_equals_strict_collapse(tmp_path, capsys):
    """修复轮 C4 / 预审 R11：`adopted_ms == strict_candidate_ms` 的**结构塌缩**必须与普通区间越界
    **分开**报告（它是判据③「松一档」前提不成立的证据，而不是又一个数值越界）。"""
    dist_path = tmp_path / "clean.distribution.json"
    calibration_path = tmp_path / "clean.calibration.json"
    assert TOOL.main(["dist", "--synthetic", "clean", "--out", str(dist_path)]) == 0
    assert TOOL.main(["derive", "--dist", str(dist_path), "--out", str(calibration_path)]) == 0
    capsys.readouterr()

    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    # 先造出**塌缩**：把 adopted 压到与 strict 候选完全相同
    for values in calibration["per_capability"].values():
        values["adopted_ms"] = values["strict_candidate_ms"]
    collapsed_path = tmp_path / "collapsed.calibration.json"
    collapsed_path.write_text(json.dumps(calibration, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")

    assert TOOL.main(["check", "--calibration", str(collapsed_path), "--dist", str(dist_path)]) == 1
    captured = capsys.readouterr()
    report = json.loads([line for line in captured.out.splitlines() if line.startswith("{")][0])
    assert report["structural_collapse"]["adopted_equals_strict"] is True
    assert sorted(report["structural_collapse"]["capabilities"]) == sorted(calibration["per_capability"])
    assert "E_CALIBRATION_STRUCTURAL" in captured.err
    # 「分开报告」：塌缩条目不得混进 problems 列表
    assert all("structural" not in problem for problem in report["problems"])

    # 反向对照：把 adopted 抬到严格不同（且仍 >= p95）⇒ 塌缩条目必须消失
    distinct = json.loads(json.dumps(calibration))
    for values in distinct["per_capability"].values():
        values["adopted_ms"] = values["strict_candidate_ms"] + 1
    distinct_path = tmp_path / "distinct.calibration.json"
    distinct_path.write_text(json.dumps(distinct, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    TOOL.main(["check", "--calibration", str(distinct_path), "--dist", str(dist_path)])
    captured = capsys.readouterr()
    report = json.loads([line for line in captured.out.splitlines() if line.startswith("{")][0])
    assert report["structural_collapse"]["adopted_equals_strict"] is False
    assert report["structural_collapse"]["capabilities"] == []

