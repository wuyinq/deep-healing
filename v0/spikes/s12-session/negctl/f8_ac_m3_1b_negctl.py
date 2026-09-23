#!/usr/bin/env python3
"""F8 判据与负例（R2）：AC-M3-1b 双向口径 + M2 继承偏差登记 + 时间锚。

判据（真跑）：
  ① 阳性：`ac-m3-1b-check.py --ws .` ⇒ 双向成立（`declared - nonOK == ∅` 且 `nonOK - declared ⊆ 继承偏差`）；
  ② **负例 A（虚报）**：声明里塞一条**没变**的路径 ⇒ 必须红；
  ③ **负例 B（漏报）**：从声明里删掉一条**真变了**的路径 ⇒ 必须红；
  ④ **负例 C（继承偏差未登记）**：删掉 `inherited_m2_deviations` 且同时删掉该条的声明 ⇒ 必须红
     （证明「继承偏差登记」是承重的，不是装饰）；
  ⑤ **负例 D（V0_M2 被改）**：把某文件的记录哈希改错（模拟「采集面被篡改」）⇒ 该文件变 FAILED 而未声明 ⇒ 必须红。
  ⑥ 时间锚在场：声明 JSON 含 `declared_at_epoch` + 当时的 `shasum -c` 原始输出。

用法：python3 -B spikes/s12-session/negctl/f8_ac_m3_1b_negctl.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

CHECK = WS / "spikes" / "s12-session" / "scripts" / "ac-m3-1b-check.py"
V0M2 = WS / "V0_M2.sha256"
DECLARATION = WS / "spikes" / "s12-session" / "m3-change-face.json"
INHERITED_PATH = "02_source/v0_skeleton/kernel/tools/calibrate_latency.py"


def stage(case: str) -> Path:
    root = lib.NEG_ROOT / case
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    shutil.copy2(V0M2, root / "V0_M2.sha256")
    shutil.copy2(DECLARATION, root / "declaration.json")
    return root


def mutate_phantom(root: Path) -> str:
    document = json.loads((root / "declaration.json").read_text(encoding="utf-8"))
    document["modified"] = sorted(set(document["modified"]) | {"02_source/this_file_did_not_change.json"})
    document["modified_count"] = len(document["modified"])
    (root / "declaration.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return "声明里塞入一条**没变**的路径（虚报）"


def mutate_drop_declared(root: Path) -> str:
    """漏报：从声明里删掉一条**真变了**的路径（且它不在继承偏差登记里）⇒ 必须红。"""
    target = "02_source/verify_specs.sh"
    document = json.loads((root / "declaration.json").read_text(encoding="utf-8"))
    document["modified"] = [path for path in document["modified"] if path != target]
    document["modified_count"] = len(document["modified"])
    (root / "declaration.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"从声明里删掉真变了的 {target}（漏报）"


def mutate_drop_inheritance(root: Path) -> str:
    """删掉继承偏差登记**并**删掉它的声明条目 ⇒ 差集无法被解释 ⇒ 必须红（证明登记是承重的）。"""
    document = json.loads((root / "declaration.json").read_text(encoding="utf-8"))
    document["inherited_m2_deviations"] = []
    document["modified"] = [path for path in document["modified"] if path != INHERITED_PATH]
    document["modified_count"] = len(document["modified"])
    (root / "declaration.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return "同时删掉继承偏差登记与它的声明条目 ⇒ 差集无法被解释"


def mutate_v0m2(root: Path) -> str:
    """采集面被篡改：把一条**未声明**文件的记录哈希改错 ⇒ 它变 FAILED 但没声明 ⇒ 必须红。"""
    target_suffix = "  02_source/art-bible.md"
    lines = (root / "V0_M2.sha256").read_text(encoding="utf-8").splitlines()
    out = []
    hit = False
    for line in lines:
        if line.endswith(target_suffix):
            out.append("0" * 64 + target_suffix)
            hit = True
        else:
            out.append(line)
    if not hit:
        raise SystemExit("fixture miss: art-bible.md not found in V0_M2.sha256")
    (root / "V0_M2.sha256").write_text("\n".join(out) + "\n", encoding="utf-8")
    return "把 02_source/art-bible.md 的记录哈希改错（该文件未在声明清单里 ⇒ 变 FAILED 即漏报）"


CASES = [
    {"case": "f8_pristine", "expect_ok": True, "mutate": None},
    {"case": "f8_neg_phantom_declaration", "expect_ok": False, "mutate": mutate_phantom},
    {"case": "f8_neg_dropped_declaration", "expect_ok": False, "mutate": mutate_drop_declared},
    {"case": "f8_neg_inheritance_unregistered", "expect_ok": False, "mutate": mutate_drop_inheritance},
    {"case": "f8_neg_v0m2_tampered", "expect_ok": False, "mutate": mutate_v0m2},
]


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []
    for spec in CASES:
        root = stage(spec["case"])
        detail = spec["mutate"](root) if spec["mutate"] else "no mutation"
        exit_code, stdout, stderr, secs = lib.run(
            [sys.executable, "-B", str(CHECK), "--ws", str(WS),
             "--v0m2", str(root / "V0_M2.sha256"), "--declaration", str(root / "declaration.json")],
            WS, timeout=900)
        report = None
        try:
            report = json.loads([line for line in stdout.splitlines() if line.startswith("{")][0])
        except Exception:  # noqa: BLE001
            pass
        ok = (exit_code == 0) == spec["expect_ok"]
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}\n# mutation: {detail}\n"
                            f"# cmd: {sys.executable} -B {CHECK} --ws {WS} "
                            f"--v0m2 {root}/V0_M2.sha256 --declaration {root}/declaration.json\n"
                            f"# exit={exit_code} seconds={secs}\n# stderr:\n{stderr}\n"
                            f"# report:\n{json.dumps(report, ensure_ascii=False, indent=2)}\n")
        results.append({"case": spec["case"], "mutation": detail, "log": str(log),
                        "exit": exit_code, "expect_ok": spec["expect_ok"], "ok": ok,
                        "declared_but_unchanged": (report or {}).get("declared_but_unchanged"),
                        "changed_but_undeclared": (report or {}).get("changed_but_undeclared"),
                        "bidirectional_ok": (report or {}).get("bidirectional_ok"),
                        "verdict": "judged_green" if exit_code == 0 else "judged_red"})
        print(f"[{spec['case']}] exit={exit_code} ok={ok} undeclared={(report or {}).get('changed_but_undeclared')}")
    after = lib.sha_tree(lib.SRC)
    declaration = json.loads(DECLARATION.read_text(encoding="utf-8"))
    summary = {"round": "R2", "item": "F8 AC-M3-1b bidirectional criterion", "cases": results,
               "declared_at_epoch": declaration.get("declared_at_epoch"),
               "time_anchor_present": bool(declaration.get("declared_at_epoch")
                                           and declaration.get("shasum_check_raw")),
               "inherited_m2_deviations": declaration.get("inherited_m2_deviations"),
               "delivery_face_unchanged": before == after, "delivery_face_sha_tree": before,
               "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("f8-ac-m3-1b-summary.json", summary)
    print(f"summary={path} all_ok={summary['all_ok']} time_anchor={summary['time_anchor_present']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
