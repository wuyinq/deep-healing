#!/usr/bin/env python3
"""AC-10 判据的**负对照探针**（M5.2 r1 · 判据必须有牙）。

做什么：把 `02_source/` 整树复制到临时目录，在**副本**上把「让世界活起来」的改动**逐条退回修复前**，
再跑 `measure_behaviour_diversity.py` ⇒ 判据**必须变红**。交付树**零改动**（副本隔离）。

探针用例（两例，逐条对应三处内核改动）：
  - `c1_reverted`：`ACTION_EXTRA_NEEDS` 清空（= `rest` 不再缓解 `safety`，回到修复前）
    ⇒ **必须** `10a_pass=false` **且** `10b_pass=false`（单分支/单需求支配复现）。
  - `c2c3_reverted`：`explore` 候选重新塞回 `home` + `_next_block` 退回 `>`（跳过边界块）
    ⇒ **必须** `10d1_pass=false` **且** `10d2_pass=false`（室外判据复现）。

输出（末行一个 JSON，供 `verify_specs.sh` 的 `selfproof` 判据读取）：
  `{"probe_ok": bool, "probe": [{"case":..., "fired": bool, "detail": {...}}, ...],
    "back_to_baseline": bool, "delivery_face_sha256_before": "...", "delivery_face_sha256_after": "..."}`

退出码：**0** = 全部探针按预期变红且交付树未变；**1** = 有探针**没**变红（判据无牙）；
        **3** = 注入锚点缺失 / 注入后复核失败（**注入失败与判据无牙必须分开**）。

注入纪律（skill）：锚点必须是**只可能出现在代码里**的行；写入后**回读复核**注入真的落地，
否则以独立退出码（3）失败 —— 绝不让「注入落成空操作」冒充「判据无牙」。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve()
SOURCE_ROOT = HERE.parents[2]                     # 02_source/
KERNEL_REL = Path("v0_skeleton/kernel")
PACK_REL = Path("v0_skeleton/districts/xingfu-xiaoqu")
TOOL_REL = Path("v0_skeleton/tools/measure_behaviour_diversity.py")
DECISION_REL = Path("v0_skeleton/kernel/deephealing_kernel/rules/decision.py")

C1_ANCHOR = 'ACTION_EXTRA_NEEDS: dict[str, tuple[str, ...]] = {\n    "rest": ("safety",),\n}'
C1_INJECTED = "ACTION_EXTRA_NEEDS: dict[str, tuple[str, ...]] = {}"
C2_ANCHOR = ('        # C2（M5.2 r1）：**不再**把 home 放进 explore 的候选集\n'
             '        # （原实现 append(home) ⇒「探索」= 待在家；见函数 docstring）\n')
C2_INJECTED = ('        # probe: C2 reverted\n'
               '        if isinstance(home, str) and home:\n'
               '            candidates.append(home)\n')
C3_ANCHOR = 'int(block.get("start_tick", 0)) >= current_until_tick]'
C3_INJECTED = 'int(block.get("start_tick", 0)) > current_until_tick]'

EXIT_OK = 0
EXIT_NO_TEETH = 1
EXIT_BAD_INJECTION = 3


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inject(text: str, anchor: str, replacement: str, label: str) -> str:
    """精确替换；锚点必须**恰好出现一次**，替换后必须真的变了（fail-closed）。"""
    if text.count(anchor) != 1:
        raise _BadInjection(f"{label}: anchor occurrences = {text.count(anchor)} (expected exactly 1)")
    return text.replace(anchor, replacement, 1)


class _BadInjection(Exception):
    pass


def _run_measure(copy_root: Path, out_json: Path) -> dict:
    command = [
        sys.executable, str(copy_root / TOOL_REL),
        "--kernel-root", str(copy_root / KERNEL_REL),
        "--pack", str(copy_root / PACK_REL),
        "--seed", "20260921", "--ticks", "1440",
        "--json", str(out_json),
    ]
    env = {"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    completed = subprocess.run(command, capture_output=True, text=True, env=env, timeout=1800)
    if not out_json.is_file():
        raise RuntimeError(f"measure tool produced no JSON (rc={completed.returncode}): "
                           f"{completed.stdout[-400:]}{completed.stderr[-400:]}")
    return json.loads(out_json.read_text(encoding="utf-8"))


def _probe_case(workdir: Path, name: str, edits: list[tuple[str, str, str]],
                expectations: list[tuple[str, bool]]) -> dict:
    """复制交付树 ⇒ 注入 ⇒ 跑判据 ⇒ 比对期望。返回一条探针读数。"""
    copy_root = workdir / name / "02_source"
    shutil.copytree(SOURCE_ROOT, copy_root)
    target = copy_root / DECISION_REL
    text = target.read_text(encoding="utf-8")
    for anchor, replacement, label in edits:
        text = _inject(text, anchor, replacement, label)
    target.write_text(text, encoding="utf-8")

    # 回读复核：注入必须真的落地（否则以独立退出码失败，而不是判成「判据无牙」）
    reread = target.read_text(encoding="utf-8")
    for anchor, replacement, label in edits:
        if anchor in reread or replacement not in reread:
            raise _BadInjection(f"{label}: injection did not land on re-read")

    document = _run_measure(copy_root, workdir / f"{name}-ac10.json")
    detail = {key: document.get(key) for key in
              ("10a_pass", "10b_pass", "10c_pass", "10d1_pass", "10d2_pass",
               "10a_share", "10b_share", "10d1_outdoor_share", "10d2_npcs_at_or_above_20pct")}
    fired = all(bool(document.get(key)) is bool(expected) for key, expected in expectations)
    return {"case": name, "fired": fired, "expected": dict(expectations), "detail": detail}


def main() -> int:
    delivery_decision = SOURCE_ROOT / DECISION_REL
    before = _sha256(delivery_decision)
    workdir = Path(tempfile.mkdtemp(prefix="m52-ac10-probe-"))
    probe: list[dict] = []
    try:
        probe.append(_probe_case(
            workdir, "c1_reverted",
            [(C1_ANCHOR, C1_INJECTED, "c1:ACTION_EXTRA_NEEDS")],
            [("10a_pass", False), ("10b_pass", False)],
        ))
        probe.append(_probe_case(
            workdir, "c2c3_reverted",
            [(C2_ANCHOR, C2_INJECTED, "c2:explore_home_candidate"),
             (C3_ANCHOR, C3_INJECTED, "c3:boundary_block")],
            [("10d1_pass", False), ("10d2_pass", False)],
        ))
    except _BadInjection as exc:
        print(json.dumps({"probe_ok": False, "probe": probe, "back_to_baseline": None,
                          "reason": f"injection_anchor_missing: {exc}"}, ensure_ascii=False))
        return EXIT_BAD_INJECTION
    after = _sha256(delivery_decision)
    document = {
        "probe_ok": all(item["fired"] for item in probe) and len(probe) == 2,
        "probe": probe,
        "back_to_baseline": before == after,
        "delivery_face_sha256_before": before,
        "delivery_face_sha256_after": after,
        "copy_root": str(workdir),
    }
    print(json.dumps(document, ensure_ascii=False))
    return EXIT_OK if document["probe_ok"] and document["back_to_baseline"] else EXIT_NO_TEETH


if __name__ == "__main__":
    raise SystemExit(main())
