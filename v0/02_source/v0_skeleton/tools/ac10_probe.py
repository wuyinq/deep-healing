#!/usr/bin/env python3
"""AC-10 判据的**负对照探针**（M5.2 r1 建立 · iter2 r2 判据重基线）。

做什么：把 `02_source/` 整树复制到临时目录，在**副本**上把「让世界活起来」的改动**逐条退回修复前**，
再跑 `measure_behaviour_diversity.py` ⇒ 判据**必须变红**。交付树**零改动**（副本隔离）。

探针用例（**`len(probe) == 2`**，逐条对应内核改动）：
  - `c1_reverted`：`ACTION_EXTRA_NEEDS` 清空（= `rest` 不再缓解 `safety`，回到修复前）
    ⇒ **必须** `10a_pass=false` **且** `10b_pass=false`（单分支/单需求支配复现）。
  - `w1_c2c3_reverted`（**iter2 r2 新臂**）：`W1 目的地承诺层`（`decision.py` 的块目标接管去向）
    **联合** `C2`（`explore` 候选重新塞回 `home`）+ `C3`（`_next_block` 退回 `>` 跳过边界块）
    ⇒ **必须** `10d1_pass=false` **且** `10d2_pass=false`（室外判据复现）。

  **归因（红线：不得改写成「新机理撑起室外多样性」）** —— iter2 r2 实测：
    · **单回退 W1 ⇒ 打不响**：`10d1_outdoor_share 0.3306 → 0.3208`、`10d2` 达标 NPC 数 `4 → 2`，
      `10d1_pass` / `10d2_pass` **两项仍为 true**；
    · **单回退 C2+C3 ⇒ 也打不响**：`0.3528` / 3 人（旧失牙臂复现）；
    · **只有 W1+C2+C3 联合回退 ⇒ 塌陷**：`0.0181` / **0 人** ⇒ 打响。
  ⇒ 塌陷由 **C2/C3 的回退**造成；**W1 的缺席是「解除遮蔽」的使能条件**
    （W1 在场时块目标接管去向 ⇒ C2 改的候选集不再被用到 ⇒ 旧负对照失牙）。
    读数原始件：`evidence/artisan/r2/arm_matrix_artisan.json` / `arm_matrix_artisan.stdout.txt`；
    归因说明：`03_artisan_self_test.log` §1/§6。

  - **归因补登记（iter2 r2.1 · Raven M-3）**：`w1_c2c3_reverted` **不是**最小注入集、**判别粒度粗**（但**无伪牙**）：
    `{W1+C2}` = `0.0222` / 达标 NPC `0`、`{W1+C3}` = `0.1174` / `1` —— **两者各自即已打响**
    ⇒ **「W1 缺席」是必要条件**（单回退 W1 不打响）；**C2 与 C3 互为冗余替代**（任一即可）。
    两侧单独均不打响（`w1_only` = 0.3208 / `c2c3_only` = 0.3528）⇒ 仍**无伪牙**，只是本臂不区分
    C2 / C3 各自的贡献（要定位到具体机理需把臂拆成 `w1_c2` / `w1_c3`，见 `03` §11-F3 登记）。
    读数**只读引用（未改写他人文件）**：Sentinel `evidence/sentinel/r2/arm_matrix_subset.my.txt`、
    Raven `evidence/raven/r2/delivery/arm_matrix_raven.json`（含 `w1_c2.json` / `w1_c3.json`）。

  - **空注入负对照**（**不占 `probe` 条目**）：向副本注入一个「文本必变、语义为空」的操作
    （常量行重排空格 + 尾随注释 ⇒ 解析结果不变）⇒ 期望判据**不打响**
    （`10d1_pass` / `10d2_pass` 仍为 true）⇒ `null_injection_fired=false`，并入 `probe_ok` 合取项
    —— 用以证伪「本探针是『任何改动都会变红』的伪牙」。

输出（末行一个 JSON，供 `verify_specs.sh` 的 `selfproof` 判据读取）：
  `{"probe_ok": bool, "probe": [{"case":..., "fired": bool, "detail": {...}}, ...],
    "null_injection_fired": bool, "null_injection": {...}, "arms_meta": {...},
    "back_to_baseline": bool, "delivery_face_sha256_before": "...", "delivery_face_sha256_after": "..."}`

  **iter2 r2 新增字段（纯加法；既有字段名、退出码语义、`len(probe)`、`_inject` fail-closed、
  副本隔离逐字未动）**：
    - `null_injection_fired`：空注入负对照的**打响**读数（期望 `false`），并入 `probe_ok` 合取项；
    - `null_injection`：空注入臂的完整读数（**不占 `probe` 条目** ⇒ `len(probe)` 仍为 2）；
    - `arms_meta`：锚点 ↔ 指标的责任绑定；每臂一串 `{file, line, anchor_sha256, replacement_sha256}`
      （联合臂有 3 处注入 ⇒ 该臂是 3 条记录的列表）。`line` = **纯净正本**里的锚点起始行
      （先于任何注入计算 ⇒ 不受注入顺序影响，可复核）。
  **`back_to_baseline` / `delivery_face_sha256_before|after` 已整树化**（iter2 r2 / Raven M-2）：
  指纹覆盖 `SOURCE_ROOT` **全树**（排除 `__pycache__` / `*.pyc` / `node_modules`），字段名不变
  —— 原实现只指纹 `decision.py` 一个文件，注入 `tick.py` 一类变体时「交付树零改动」没有机械担保。

  **iter2 r2.1 修复（Raven M-5）：负期望臂不得对「读数缺失」fail-open**。原实现
  `fired = all(bool(document.get(k)) is bool(expected) …)` 在 `detail` 全 `null` 时
  `bool(None) is bool(False)` ⇒ `fired=true` —— **零证据也算打响**。现在每条臂先过
  **判据键齐备性前置**（`measure_status == "measured"` **且** 5 个判据键
  `10a/10b/10c/10d1/10d2_pass` **全部非 `null`**）；不齐备 ⇒ 该臂 `status="degraded"`、`fired=false`
  （**不判打响**），且 `probe_ok` 必为假（`probe_ok` 额外要求全部臂 —— 含空注入臂 —— 同为
  `status="measured"`，且 `null_injection_fired is False`，此时该字段在退化下为 `null` ⇒ 合取必假）。
  退化构造读数落盘：`03_artisan_self_test.log` §11-F2、`evidence/artisan/r2/degraded_probe.{json,stdout.txt}`。

  **iter2 r2.1 登记（Raven M-1；**architect 决定不修**，只登记）**：门禁层（`verify_specs.sh` 的
  `selfproof` → `probe_json` 分支）**只消费 `probe_ok`**，既不消费 `back_to_baseline`（仅被打印进
  OK 文案），**也不消费本工具退出码** ⇒ 「注入泄漏进交付树（`back_to_baseline=false`）」这条路径
  **在门禁层不可见**（工具自身是 fail-closed 的：退出码里含 `back_to_baseline`）。**本轮实测未触发**
  （交付态两指纹相同 ⇒ `back_to_baseline=true`）。
  **不把 `back_to_baseline` 并入 `probe_ok` 的理由**：判据自证必须与被测树**解耦** —— 一旦并入，
  **树侧异常**会以「自证失败」的形式出现，正好丢掉 `verify_specs` 自己在 r2.6 建立起来的
  **维度归因**能力（「自证失效」vs「树红」分开报）。**两条候选修法**（均需 PM 授权改**禁改面**）：
  ① 门禁侧把 `back_to_baseline` 列为**独立维度**（单独一行 PASS/FAIL）；② 门禁侧消费被调工具的**退出码**。

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
# W1（iter2 r2）：`commit_destination()` 末行 —— 关掉「块目标接管去向」，去向回落到 `_resolve_target()`。
# 锚点在 `decision.py` 全树**恰好出现 1 次**（决策层唯一）；单独回退它**打不响**（见上方归因）。
W1_ANCHOR = '    return block, "schedule_block"'
W1_INJECTED = '    return resolved, source'
# 空注入负对照：**文本必变、语义为空**（未动常量值 / 未被解析进任何表达式的空格重排 + 尾随注释）
# ⇒ 期望判据**不打响**。锚点须满足 `_inject` 的 fail-closed 复核（替换后锚点文本不再出现）。
NULL_ANCHOR = 'ARRIVE_TOLERANCE_MM = 1000'
NULL_INJECTED = ('ARRIVE_TOLERANCE_MM  =  1000  '
                 '# probe: null injection (whitespace + comment only; value/semantics unchanged)')

#: 判据键齐备性前置（iter2 r2.1 / Raven M-5）：这 5 个键是 `measure_behaviour_diversity.py` 的判定面，
#: 任一为 `null`（或 `measure_status != "measured"`）⇒ 该臂读数**不齐备**，不得据此判「打响」。
CRITERIA_KEYS = ("10a_pass", "10b_pass", "10c_pass", "10d1_pass", "10d2_pass")

EXIT_OK = 0
EXIT_NO_TEETH = 1
EXIT_BAD_INJECTION = 3

#: 整树指纹的排除集（每项都写明：解释器产物 / 依赖目录；**不含**任何承载判据的路径）
EXCLUDED_TREE_PARTS = ("__pycache__", "node_modules")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path) -> str:
    """`SOURCE_ROOT` 全树指纹（整树化的 `back_to_baseline` / `delivery_face_sha256_*`）。

    排除 `__pycache__` 目录、`*.pyc` 与 `node_modules`（解释器产物 / 依赖目录，非判据面）。
    """
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.endswith(".pyc") or any(part in EXCLUDED_TREE_PARTS for part in rel.split("/")):
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _line_of(text: str, anchor: str) -> int:
    """锚点在**纯净正本**文本中的起始行号（1-based）。"""
    return text[: text.index(anchor)].count("\n") + 1


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
                expectations: list[tuple[str, bool]]) -> tuple[dict, list[dict]]:
    """复制交付树 ⇒ 注入 ⇒ 跑判据 ⇒ 比对期望。

    返回 `(探针读数, 锚点责任绑定元数据)`；元数据的 `line` 取自**纯净正本**（注入前）。
    """
    copy_root = workdir / name / "02_source"
    shutil.copytree(SOURCE_ROOT, copy_root)
    target = copy_root / DECISION_REL
    original = target.read_text(encoding="utf-8")
    text = original
    meta: list[dict] = []
    for anchor, replacement, label in edits:
        if original.count(anchor) != 1:
            raise _BadInjection(f"{label}: anchor occurrences = {original.count(anchor)} (expected exactly 1)")
        line = _line_of(original, anchor)
        text = _inject(text, anchor, replacement, label)
        meta.append({"file": DECISION_REL.as_posix(), "line": line,
                     "anchor_sha256": hashlib.sha256(anchor.encode("utf-8")).hexdigest(),
                     "replacement_sha256": hashlib.sha256(replacement.encode("utf-8")).hexdigest(),
                     "label": label})
    target.write_text(text, encoding="utf-8")

    # 回读复核：注入必须真的落地（否则以独立退出码失败，而不是判成「判据无牙」）
    reread = target.read_text(encoding="utf-8")
    if reread == original:
        raise _BadInjection(f"{name}: text unchanged after injection (empty edit)")
    for anchor, replacement, label in edits:
        if anchor in reread or replacement not in reread:
            raise _BadInjection(f"{label}: injection did not land on re-read")

    document = _run_measure(copy_root, workdir / f"{name}-ac10.json")
    detail = {key: document.get(key) for key in
              (*(CRITERIA_KEYS),
               "10a_share", "10b_share", "10d1_outdoor_share", "10d2_npcs_at_or_above_20pct")}
    # **判据键齐备性前置（iter2 r2.1 / Raven M-5）**：读数缺失 ⇒ 该臂**不得**判「打响」。
    # 原实现在 `detail` 全 `null` 时 `bool(None) is bool(False)` ⇒ `fired=true`（零证据也算打响）。
    missing_keys = [key for key in CRITERIA_KEYS if document.get(key) is None]
    measured = document.get("status") == "measured" and not missing_keys
    fired = bool(measured) and all(bool(document.get(key)) is bool(expected)
                                   for key, expected in expectations)
    return {"case": name, "fired": fired,
            "status": "measured" if measured else "degraded",
            "measure_status": document.get("status"),
            "missing_criteria_keys": missing_keys,
            "expected": dict(expectations), "detail": detail}, meta


def main() -> int:
    before = _tree_sha256(SOURCE_ROOT)
    workdir = Path(tempfile.mkdtemp(prefix="m52-ac10-probe-"))
    probe: list[dict] = []
    arms_meta: dict[str, list[dict]] = {}
    try:
        record, meta = _probe_case(
            workdir, "c1_reverted",
            [(C1_ANCHOR, C1_INJECTED, "c1:ACTION_EXTRA_NEEDS")],
            [("10a_pass", False), ("10b_pass", False)],
        )
        probe.append(record)
        arms_meta["c1_reverted"] = meta
        record, meta = _probe_case(
            workdir, "w1_c2c3_reverted",
            [(W1_ANCHOR, W1_INJECTED, "w1:destination_commitment"),
             (C2_ANCHOR, C2_INJECTED, "c2:explore_home_candidate"),
             (C3_ANCHOR, C3_INJECTED, "c3:boundary_block")],
            [("10d1_pass", False), ("10d2_pass", False)],
        )
        probe.append(record)
        arms_meta["w1_c2c3_reverted"] = meta
        # 空注入负对照：**不占 probe 条目**（`len(probe)` 保持 2）
        null_record, null_meta = _probe_case(
            workdir, "null_injection",
            [(NULL_ANCHOR, NULL_INJECTED, "null:comment_and_whitespace_only")],
            [("10d1_pass", True), ("10d2_pass", True)],
        )
        arms_meta["null_injection"] = null_meta
    except _BadInjection as exc:
        print(json.dumps({"probe_ok": False, "probe": probe, "null_injection_fired": None,
                          "null_injection": None, "arms_meta": arms_meta, "back_to_baseline": None,
                          "reason": f"injection_anchor_missing: {exc}"}, ensure_ascii=False))
        return EXIT_BAD_INJECTION
    after = _tree_sha256(SOURCE_ROOT)
    null_detail = null_record["detail"]
    # 「打响」= 注入后室外判据变红；空注入**必须不打响** ⇒ 期望 false。
    # **iter2 r2.1 / Raven M-5**：读数缺失（`status="degraded"`）时**不得**判成 `false`（那会 fail-open
    # 成「空注入没打响 ⇒ 通过」）⇒ 该情形记 `null`，并让下面 `null_injection_fired is False` 的合取必假。
    if null_record["status"] == "measured":
        null_injection_fired: bool | None = not (bool(null_detail.get("10d1_pass"))
                                                and bool(null_detail.get("10d2_pass")))
    else:
        null_injection_fired = None
    probe_ok = (all(item["fired"] for item in probe) and len(probe) == 2
                and all(item["status"] == "measured" for item in probe)
                and null_record["status"] == "measured"
                and null_injection_fired is False)
    document = {
        "probe_ok": probe_ok,
        "probe": probe,
        "null_injection_fired": null_injection_fired,
        "null_injection": null_record,
        "arms_meta": arms_meta,
        "back_to_baseline": before == after,
        "delivery_face_sha256_before": before,
        "delivery_face_sha256_after": after,
        "copy_root": str(workdir),
    }
    print(json.dumps(document, ensure_ascii=False))
    return EXIT_OK if document["probe_ok"] and document["back_to_baseline"] else EXIT_NO_TEETH


if __name__ == "__main__":
    raise SystemExit(main())
