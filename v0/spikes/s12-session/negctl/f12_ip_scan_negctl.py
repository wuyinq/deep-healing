#!/usr/bin/env python3
"""F12 判据与负例（R2）：IP 边界扫描必须有**判据载体**且**有命中能力**。

判据（真跑，整树副本）：
  ① 阳性：副本上 `scan_ip_boundary.py --root .` ⇒ exit 0、`unwhitelisted_hits == 0`；
  ② **负例 A**：向副本注入一个含探针文本的文件 ⇒ 必须 exit 1（`E_IP_BOUNDARY` 行）；
  ③ **负例 B**：把副本里扫描器的白名单清空 ⇒ 必须 exit 1（证明白名单是承重的：schema `$comment`
     的「自命中」需要**逐条理由**才被允许，否则就是红）。

用法：python3 -B spikes/s12-session/negctl/f12_ip_scan_negctl.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

SCANNER_REL = "v0_skeleton/tools/scan_ip_boundary.py"
PROBE_NAME = "injected-ip-probe.txt"
PROBE_TEXT = "IP 探针：第 3 章 《某某传》 怪物 血腥 Jump Scare\n"
WHITELIST_ANCHOR = "DECLARATION_SITES: dict[str, str] = {"
ART_BIBLE_REL = "art-bible.md"
# R3 / G4 负例：**真越界**内容（不含任何禁令词 ⇒ 行级豁免不适用）
ART_BIBLE_OUT_OF_BOUNDS = "场景参考：第 3 章，主角被怪物肢解，血腥特写，配合 Jump Scare。\n"


def inject_probe(root: Path) -> str:
    target = root / "02_source" / PROBE_NAME
    target.write_text(PROBE_TEXT, encoding="utf-8")
    return f"向副本注入 {PROBE_NAME}（含 4 类探针形态）"


def inject_out_of_bounds_into_art_bible(root: Path) -> str:
    """R3 / G4：往 `art-bible.md`（**声明站点**）追加一句真越界 ⇒ 必须红。

    修复前这里是 `exit 0`（整份文件被白名单豁免）；现在只有「同一行含禁令词」的行才豁免。
    """
    target = root / "02_source" / ART_BIBLE_REL
    with target.open("a", encoding="utf-8") as handle:
        handle.write(ART_BIBLE_OUT_OF_BOUNDS)
    return f"向副本 {ART_BIBLE_REL} 追加一句真越界（含 gore/monster/jump scare，无禁令词）"


def disable_whitelist(root: Path) -> str:
    path = root / "02_source" / SCANNER_REL
    text = path.read_text(encoding="utf-8")
    assert WHITELIST_ANCHOR in text, "anchor miss"
    # 把声明站点整体改成空（保留类型注解形态）⇒ 所有命中都算未豁免
    start = text.index(WHITELIST_ANCHOR)
    end = text.index("\n}", start) + 2
    path.write_text(text[:start] + "DECLARATION_SITES: dict[str, str] = {}\n" + text[end:], encoding="utf-8")
    return "清空扫描器声明站点（schema $comment 的自命中不再被豁免）"


CASES = [
    {"case": "f12_pristine", "expect_exit": 0, "mutate": None},
    {"case": "f12_neg_injected_probe", "expect_exit": 1, "mutate": inject_probe},
    {"case": "f12_neg_whitelist_disabled", "expect_exit": 1, "mutate": disable_whitelist},
    {"case": "f12_neg_art_bible_out_of_bounds", "expect_exit": 1, "mutate": inject_out_of_bounds_into_art_bible},
]


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []
    for spec in CASES:
        root = lib.fresh_copy(spec["case"])
        detail = spec["mutate"](root) if spec["mutate"] else "no mutation"
        exit_code, stdout, stderr, secs = lib.run(
            [sys.executable, "-B", str(root / "02_source" / SCANNER_REL),
             "--root", str(root / "02_source")], root, timeout=600)
        report = None
        try:
            report = json.loads([line for line in stdout.splitlines() if line.startswith("{")][0])
        except Exception:  # noqa: BLE001
            pass
        ok = exit_code == spec["expect_exit"]
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}\n# copy {root}\n# mutation: {detail}\n"
                            f"# cmd: python3 -B {root}/02_source/{SCANNER_REL} --root {root}/02_source\n"
                            f"# exit={exit_code} seconds={secs}\n# stderr:\n{stderr}\n"
                            f"# report:\n{json.dumps(report, ensure_ascii=False, indent=2)[:4000]}\n")
        results.append({"case": spec["case"], "mutation": detail, "copy": str(root), "log": str(log),
                        "exit": exit_code, "expect_exit": spec["expect_exit"], "ok": ok,
                        "unwhitelisted_hits": (report or {}).get("unwhitelisted_hits"),
                        "verdict": "judged_red" if exit_code else "judged_green"})
        print(f"[{spec['case']}] exit={exit_code} unwhitelisted={(report or {}).get('unwhitelisted_hits')} ok={ok}")
    after = lib.sha_tree(lib.SRC)
    summary = {"round": "R2", "item": "F12 IP boundary scan criterion carrier", "cases": results,
               "delivery_face_unchanged": before == after, "delivery_face_sha_tree": before,
               "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("f12-ip-scan-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
