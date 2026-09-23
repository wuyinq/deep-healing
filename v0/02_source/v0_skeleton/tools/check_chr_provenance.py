#!/usr/bin/env python3
"""CHR 出处可复算判据（M5.2 r1 · Raven M-17 硬性；**不修红线判据本身**，只补补偿控制）。

背景：R-17 的失明面直接作用在本轮**新增**的 L0 派生内容上 ⇒ 补一条可复算判据：
`npc-006.json` 的每条设定都能指到 **CHR 编号**，且该编号在
`02_source/fidelity/05-character-dossiers.md` 内**存在**（且**不是** `UNVERIFIED` 条目）。

判据：
  ① `source_facts` **非空**；
  ② `source_fact_map` **非空**，每个键（= 一条设定）的值是**非空** CHR 编号列表；
  ③ 所有被引用的编号都出现在事实册的**已核实**集合内（`[CHR-nn]` 且该行不含 `UNVERIFIED`）；
  ④ `source_facts` 与 `source_fact_map` 的编号集合**一致**（不得一处声明、一处漏标）；
  ⑤ 事实册标 `UNVERIFIED` 的编号（如年龄 / 生前身份）**不得**被引用。

负对照（`--probe-only`，临时副本，交付树零改动）：
  - `forged_id`：把 `CHR-01` 换成不存在的 `CHR-99` ⇒ ③ **必红**；
  - `unverified_id`：把一条设定指到事实册标 `UNVERIFIED` 的编号 ⇒ ⑤ **必红**（若事实册无 UNVERIFIED 条目，该例记 `not_applicable` 并如实登记）。

输出末行 JSON：`{"provenance_ok": bool, "checks": {...}, "probe_ok": bool, "probe": [...]}`
退出码：**0** 全绿；**1** 有判据为假；**2** 前置输入缺失；**3** 注入锚点失效。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

CHR_LINE_RE = re.compile(r"\[(CHR-\d+)\]")
EXIT_OK, EXIT_RED, EXIT_SKIP, EXIT_BAD_INJECTION = 0, 1, 2, 3


class _BadInjection(Exception):
    pass


def _dossier_sets(dossiers: Path) -> tuple[set[str], set[str]]:
    verified: set[str] = set()
    unverified: set[str] = set()
    for line in dossiers.read_text(encoding="utf-8").splitlines():
        for match in CHR_LINE_RE.finditer(line):
            identifier = match.group(1)
            if "UNVERIFIED" in line:
                unverified.add(identifier)
            else:
                verified.add(identifier)
    return verified, unverified


def _evaluate(dossiers: Path, npc: Path) -> dict:
    verified, unverified = _dossier_sets(dossiers)
    document = json.loads(npc.read_text(encoding="utf-8"))
    facts = [str(item) for item in (document.get("source_facts") or [])]
    fact_map = document.get("source_fact_map")
    fact_map = fact_map if isinstance(fact_map, dict) else {}

    map_ids: set[str] = set()
    empty_entries: list[str] = []
    for key, value in sorted(fact_map.items()):
        items = [str(item) for item in value] if isinstance(value, list) else []
        items = [item for item in items if item.strip()]
        if not items:
            empty_entries.append(key)
        map_ids.update(items)

    referenced = set(facts) | map_ids
    unknown = sorted(item for item in referenced if item not in verified and item not in unverified)
    unverified_hits = sorted(item for item in referenced if item in unverified)

    checks = {
        "source_facts_non_empty": {"value": facts, "pass": bool(facts)},
        "source_fact_map_non_empty": {"entries": sorted(fact_map), "pass": bool(fact_map) and not empty_entries,
                                      "empty_entries": empty_entries},
        "all_ids_exist_in_dossiers": {"unknown": unknown, "verified_count": len(verified),
                                      "pass": not unknown},
        "declared_and_mapped_agree": {"only_in_source_facts": sorted(set(facts) - map_ids),
                                      "only_in_map": sorted(map_ids - set(facts)),
                                      "pass": set(facts) == map_ids and bool(facts)},
        "no_unverified_ids_used": {"unverified_hits": unverified_hits,
                                   "unverified_in_dossiers": sorted(unverified),
                                   "pass": not unverified_hits},
    }
    return {"provenance_ok": all(item["pass"] for item in checks.values()), "checks": checks}


def _probe(dossiers: Path, npc: Path, workdir: Path) -> list[dict]:
    verified, unverified = _dossier_sets(dossiers)
    cases: list[dict] = []

    forged = workdir / "forged" / npc.name
    forged.parent.mkdir(parents=True, exist_ok=True)
    source = npc.read_text(encoding="utf-8")
    anchor = '"relations.hanfei.first_meeting": ["CHR-01"]'
    if source.count(anchor) != 1:
        raise _BadInjection(f"forged_id: anchor occurrences = {source.count(anchor)} (expected exactly 1)")
    forged.write_text(source.replace(anchor, '"relations.hanfei.first_meeting": ["CHR-99"]', 1),
                      encoding="utf-8")
    if '"CHR-99"' not in forged.read_text(encoding="utf-8"):
        raise _BadInjection("forged_id: injection did not land")
    result = _evaluate(dossiers, forged)
    cases.append({"case": "forged_id", "fired": result["checks"]["all_ids_exist_in_dossiers"]["pass"] is False,
                  "reading": result["checks"]["all_ids_exist_in_dossiers"]["unknown"]})

    if unverified:
        victim = sorted(unverified)[0]
        copy = workdir / "unverified" / npc.name
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(source.replace(anchor, f'"relations.hanfei.first_meeting": ["{victim}"]', 1),
                        encoding="utf-8")
        if f'"{victim}"' not in copy.read_text(encoding="utf-8"):
            raise _BadInjection("unverified_id: injection did not land")
        result = _evaluate(dossiers, copy)
        cases.append({"case": "unverified_id",
                      "fired": result["checks"]["no_unverified_ids_used"]["pass"] is False,
                      "reading": result["checks"]["no_unverified_ids_used"]["unverified_hits"]})
    else:
        cases.append({"case": "unverified_id", "fired": None,
                      "reading": "not_applicable: dossiers contain no UNVERIFIED CHR entry"})
    return cases


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="CHR provenance check")
    parser.add_argument("--dossiers", required=True)
    parser.add_argument("--npc", required=True)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args(argv)

    dossiers = Path(args.dossiers).expanduser()
    npc = Path(args.npc).expanduser()
    missing = [str(path) for path in (dossiers, npc) if not path.is_file()]
    if missing:
        _emit({"status": "skipped_missing_input", "missing": missing}, args.json_path)
        return EXIT_SKIP

    try:
        probe = _probe(dossiers, npc, Path(tempfile.mkdtemp(prefix="m52-chr-probe-")))
    except _BadInjection as exc:
        _emit({"provenance_ok": None, "probe_ok": False, "reason": f"injection_anchor_missing: {exc}"},
              args.json_path)
        return EXIT_BAD_INJECTION

    document = _evaluate(dossiers, npc)
    document["probe"] = probe
    document["probe_ok"] = all(item["fired"] is not False for item in probe) and any(
        item["fired"] is True for item in probe)
    document["status"] = "measured"
    _emit(document, args.json_path)
    if args.probe_only:
        return EXIT_OK if document["probe_ok"] else EXIT_RED
    return EXIT_OK if document["provenance_ok"] and document["probe_ok"] else EXIT_RED


def _emit(document: dict, json_path: str | None) -> None:
    text = json.dumps(document, ensure_ascii=False, sort_keys=True)
    sys.stdout.write(text + "\n")
    if json_path:
        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
