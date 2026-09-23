#!/usr/bin/env python3
"""G6 判据与负例（R3 / Raven r2 R2-M2）：三份冻结物的**内容锚覆盖要齐**。

判据（全部在 `/tmp/r3-artisan/**` 的隔离副本上跑，交付面只读）：
  ① 阳性：副本里 `registry` 幂等（`rewritten:false`、exit 0）；
  ② **负例 A**：篡改副本的 `ENVIRONMENT-CLASS.frozen.md` ⇒ 普通 `registry` 必须
     `E_FROZEN_MISMATCH` + exit≠0（修复前是静默 `rewritten:true` / exit 0）；
  ③ 负例 B（对照）：篡改 `ACCEPTED-DEGRADATION-RANGE.frozen.md` ⇒ 同样必须红；
  ④ **负例 C**：只改 registry 里登记的 sha256（冻结物本身没动）⇒ `verify_specs.sh` 的
     「三条冻结物内容锚」判据必须红（证明该门禁有牙齿，不是恒绿）；
  ⑤ **负例 D**：只改工具内的 `FROZEN_ENVCLASS_SHA256` 锚 ⇒ 同一条判据必须红。

用法：python3 -B spikes/s12-session/negctl/g6_frozen_anchor_negctl.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

TOOL_REL = "v0_skeleton/kernel/tools/calibrate_latency.py"
REGISTRY_REL = "calibration.registry.json"
S5_REL = "spikes/s5-latency-calibration"
ANCHOR_FAIL_MARKER = "calibration frozen anchors"


def run_registry(root: Path):
    tool = root / "02_source" / TOOL_REL
    return lib.run([sys.executable, "-B", str(tool), "registry"], root / "02_source" / "v0_skeleton" / "kernel", timeout=300)


def tamper_file(root: Path, rel: str) -> str:
    target = root / S5_REL / rel
    with target.open("a", encoding="utf-8") as handle:
        handle.write("TAMPER\n")
    return f"向副本 {rel} 追加 TAMPER"


def tamper_registry_sha(root: Path) -> str:
    path = root / S5_REL / REGISTRY_REL
    document = json.loads(path.read_text(encoding="utf-8"))
    original = document["environment_class_rule"]["sha256"]
    document["environment_class_rule"]["sha256"] = "0" * 64
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return f"把 registry 的 environment_class_rule.sha256 从 {original[:12]}… 改成 0000…（冻结物本身未动）"


def tamper_tool_anchor(root: Path) -> str:
    path = root / "02_source" / TOOL_REL
    text = path.read_text(encoding="utf-8")
    anchor = 'FROZEN_ENVCLASS_SHA256 = "'
    assert anchor in text, "anchor miss"
    replaced = text.replace(anchor + "962cba08", anchor + "00000000")
    assert replaced != text
    path.write_text(replaced, encoding="utf-8")
    return "把工具内 FROZEN_ENVCLASS_SHA256 的前 8 位改成 00000000"


def verify_specs_anchor_failed(root: Path) -> tuple[bool, str]:
    """跑副本的 `verify_specs.sh`，看「三条冻结物内容锚」判据是否红。"""
    exit_code, stdout, stderr, secs = lib.run(["bash", str(root / "02_source" / "verify_specs.sh")], root / "02_source", timeout=600)
    failed_lines = [line for line in stdout.splitlines() if line.startswith("FAIL") and ANCHOR_FAIL_MARKER in line]
    return bool(failed_lines), f"exit={exit_code} anchor_fail_lines={failed_lines} seconds={secs}"


def build_workspace_copy(case: str) -> Path:
    """副本布局必须**镜像工作区**：`<root>/02_source` + `<root>/spikes/s5-latency-calibration`。"""
    root = lib.NEG_ROOT / case
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    shutil.copytree(lib.SRC, root / "02_source", ignore=shutil.ignore_patterns(*lib.GENERATED))
    shutil.copytree(WS / S5_REL, root / S5_REL,
                    ignore=shutil.ignore_patterns("logs", "__pycache__", "runtime"))
    return root


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []

    # ---- ① 阳性：幂等
    root = build_workspace_copy("g6_pristine")
    exit_code, stdout, stderr, secs = run_registry(root)
    report = {}
    try:
        report = json.loads([line for line in stdout.splitlines() if line.startswith("{")][0])
    except Exception:  # noqa: BLE001
        pass
    ok = exit_code == 0 and report.get("rewritten") is False and report.get("unchanged") is True
    results.append({"case": "g6_pristine", "copy": str(root), "mutation": "none", "exit": exit_code,
                    "report": report, "expect": "exit 0 / rewritten=false", "ok": ok,
                    "verdict": "judged_green" if ok else "judged_red"})
    print(f"[g6_pristine] exit={exit_code} rewritten={report.get('rewritten')} ok={ok}")

    # ---- ②③ 负例 A/B：篡改冻结物 ⇒ 普通 registry 必须红
    for case, rel in (("g6_neg_envclass_tampered", "ENVIRONMENT-CLASS.frozen.md"),
                      ("g6_neg_range_tampered", "ACCEPTED-DEGRADATION-RANGE.frozen.md")):
        root = build_workspace_copy(case)
        mutation = tamper_file(root, rel)
        exit_code, stdout, stderr, secs = run_registry(root)
        judged_red = exit_code != 0 and "E_FROZEN_MISMATCH" in stderr
        log = lib.write_log(f"negctl-{case}.log",
                            f"# case {case}\n# copy {root}\n# mutation {mutation}\n"
                            f"# cmd: python3 -B {root}/02_source/{TOOL_REL} registry\n"
                            f"# exit={exit_code} seconds={secs}\n# stdout:\n{stdout}\n# stderr:\n{stderr}\n")
        results.append({"case": case, "copy": str(root), "mutation": mutation, "exit": exit_code,
                        "stderr_tail": stderr.strip().splitlines()[-1] if stderr.strip() else "",
                        "expect": "E_FROZEN_MISMATCH + exit!=0", "ok": judged_red,
                        "verdict": "judged_red" if judged_red else "judged_green", "log": str(log)})
        print(f"[{case}] exit={exit_code} frozen_mismatch={'E_FROZEN_MISMATCH' in stderr} ok={judged_red}")

    # ---- ④⑤ 负例 C/D：门禁（verify_specs.sh §12b）的命中能力
    for case, mutate in (("g6_neg_registry_sha_tampered", tamper_registry_sha),
                         ("g6_neg_tool_anchor_tampered", tamper_tool_anchor)):
        root = build_workspace_copy(case)
        mutation = mutate(root)
        red, detail = verify_specs_anchor_failed(root)
        log = lib.write_log(f"negctl-{case}.log",
                            f"# case {case}\n# copy {root}\n# mutation {mutation}\n"
                            f"# cmd: bash {root}/02_source/verify_specs.sh\n# {detail}\n")
        results.append({"case": case, "copy": str(root), "mutation": mutation,
                        "expect": f"verify_specs FAIL line containing {ANCHOR_FAIL_MARKER!r}",
                        "detail": detail, "ok": red,
                        "verdict": "judged_red" if red else "judged_green", "log": str(log)})
        print(f"[{case}] anchor_gate_red={red} ok={red}")

    # ---- 对照：未篡改的副本上，同一条门禁必须绿（证明不是恒红）
    root = build_workspace_copy("g6_pristine_gate")
    green = not verify_specs_anchor_failed(root)[0]
    results.append({"case": "g6_pristine_gate", "copy": str(root), "mutation": "none",
                    "expect": "verify_specs 锚判据绿", "ok": green,
                    "verdict": "judged_green" if green else "judged_red"})
    print(f"[g6_pristine_gate] anchor_gate_green={green} ok={green}")

    after = lib.sha_tree(lib.SRC)
    summary = {"round": "R3", "item": "G6 frozen content anchors (3/3)", "neg_root": str(lib.NEG_ROOT),
               "cases": results, "delivery_face_unchanged": before == after,
               "delivery_face_sha_tree": before, "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("g6-frozen-anchor-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
