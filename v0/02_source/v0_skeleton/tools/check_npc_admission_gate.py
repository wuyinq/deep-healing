#!/usr/bin/env python3
"""AC-7 闸门：现实事件 → NPC 生成的**准入判据**（M5.2 r1 · Raven M-11 硬性）。

判据（**能红**，不是存在性检查）：
  ① 主读数包 `npcs/*.json` 计数 **== 5**（REQ §4 明文禁止本轮批量生成新居民）；
  ② 主读数包 `pack.sig` 的 sha256 **== 冻结锚**（逐字节不变 ⇒ 主包未被改动，AC-10 基线不被污染）；
  ③ 徐琴提案包 `npcs/*.json` 计数 **== 1**；
  ④ 提案包内**每个** NPC 文档必须带**非空**来源标注字段 `source_facts`（否则不许进内容层）。

负对照（`--probe-only`，全部在**临时副本**上做，交付树零改动）：
  - `extra_npc`：往提案包副本里多加一个 NPC ⇒ ③ **必红**；
  - `npc_without_source`：把副本里 NPC 的 `source_facts` 清空 ⇒ ④ **必红**。

**覆盖范围声明（M5.2 r3 / FIX-12 · Raven L-2，**硬性**）**：
本闸门的两个 pack 路径是**参数**（`--main-pack` / `--proposal-pack`），它**从不扫描** `districts/*`
⇒ **只覆盖「主读数包 + 显式指定的提案包」这一对**。**实证的绕过路径**：把新居民放进**第三个包**
（Raven 造了 `districts/xingfu-xiaoqu-batch/`：3 NPC、`source_facts: []`）后对**主包 + 提案包**跑同一工具
⇒ `gate_ok=true`、exit 0。⇒ 本闸门**不能**在树级执行「本轮不得批量生成新居民」。
**树级兜底（不是本工具，必须一并声明）**：`verify_specs.sh` 的
`manifest.txt does not cover file: $rel` 判据会打红 `02_source/**` 下**任何新增文件**
（`districts/**` 也在其中）⇒ 第三个包**会被**该判据挡住。
⇒ 结论口径：**「AC-7 闸门」= 参数对级判据；树级新增由 manifest 覆盖判据兜底**，不得读成「覆盖全树」。

输出末行 JSON：`{"gate_ok": bool, "checks": {...}, "coverage": {...}, "probe_ok": bool, "probe": [...]}`
退出码：**0** 判据全绿；**1** 有判据为假；**2** 前置输入缺失；**3** 注入锚点失效（与「判据无牙」分开）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

#: 冻结锚（2026-09-23 采集）：仓库 `v0/02_source/v0_skeleton/districts/xingfu-xiaoqu/pack.sig`
#: 与 M5.1 交付面 `/tmp/m52-ref` 的同名文件 sha256 **逐字节相同**（两条独立读数一致）。
MAIN_PACK_SIG_SHA256 = "844f7606d5b548517a1af3a052bf882b7e38563297a644bcd70e1bd3dafcb87b"
MAIN_PACK_NPCS = 5
PROPOSAL_PACK_NPCS = 1
EXIT_OK, EXIT_RED, EXIT_SKIP, EXIT_BAD_INJECTION = 0, 1, 2, 3


class _BadInjection(Exception):
    pass


def _npcs(pack_dir: Path) -> list[Path]:
    return sorted((pack_dir / "npcs").glob("*.json"))


def _evaluate(main_pack: Path, proposal_pack: Path) -> dict:
    main_npcs = _npcs(main_pack)
    proposal_npcs = _npcs(proposal_pack)
    sig_path = main_pack / "pack.sig"
    sig_sha = hashlib.sha256(sig_path.read_bytes()).hexdigest() if sig_path.is_file() else None

    without_source: list[str] = []
    for path in proposal_npcs:
        document = json.loads(path.read_text(encoding="utf-8"))
        facts = document.get("source_facts")
        if not isinstance(facts, list) or not [item for item in facts if str(item).strip()]:
            without_source.append(path.name)

    checks = {
        "main_pack_npc_count": {"value": len(main_npcs), "expected": MAIN_PACK_NPCS,
                                "pass": len(main_npcs) == MAIN_PACK_NPCS},
        "main_pack_sig_byte_identical": {"value": sig_sha, "expected": MAIN_PACK_SIG_SHA256,
                                         "pass": sig_sha == MAIN_PACK_SIG_SHA256},
        "proposal_pack_npc_count": {"value": len(proposal_npcs), "expected": PROPOSAL_PACK_NPCS,
                                    "pass": len(proposal_npcs) == PROPOSAL_PACK_NPCS},
        "proposal_npcs_have_source_facts": {"without_source": without_source,
                                            "pass": not without_source and bool(proposal_npcs)},
    }
    return {"gate_ok": all(item["pass"] for item in checks.values()), "checks": checks}


def _probe(main_pack: Path, proposal_pack: Path, workdir: Path) -> list[dict]:
    cases: list[dict] = []

    copy_a = workdir / "extra_npc" / proposal_pack.name
    shutil.copytree(proposal_pack, copy_a)
    extra = copy_a / "npcs" / "npc-007.json"
    extra.write_text(json.dumps({"id": "npc-007", "display_name": "probe",
                                 "source_facts": ["CHR-01"]}, ensure_ascii=False), encoding="utf-8")
    if not extra.is_file():
        raise _BadInjection("extra_npc: probe file not written")
    result = _evaluate(main_pack, copy_a)
    cases.append({"case": "extra_npc", "fired": result["checks"]["proposal_pack_npc_count"]["pass"] is False,
                  "reading": result["checks"]["proposal_pack_npc_count"]})

    copy_b = workdir / "no_source" / proposal_pack.name
    shutil.copytree(proposal_pack, copy_b)
    target = _npcs(copy_b)[0]
    document = json.loads(target.read_text(encoding="utf-8"))
    document.pop("source_facts", None)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    reread = json.loads(target.read_text(encoding="utf-8"))
    if "source_facts" in reread:
        raise _BadInjection("npc_without_source: injection did not land")
    result = _evaluate(main_pack, copy_b)
    cases.append({"case": "npc_without_source",
                  "fired": result["checks"]["proposal_npcs_have_source_facts"]["pass"] is False,
                  "reading": result["checks"]["proposal_npcs_have_source_facts"]})
    return cases


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="AC-7 NPC admission gate — coverage: ONLY the (--main-pack, --proposal-pack) pair; "
                    "it never scans districts/*. A third pack is NOT covered by this gate; tree-level "
                    "additions are caught by verify_specs.sh's manifest-coverage criterion.")
    parser.add_argument("--main-pack", required=True)
    parser.add_argument("--proposal-pack", required=True)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args(argv)

    main_pack = Path(args.main_pack).expanduser()
    proposal_pack = Path(args.proposal_pack).expanduser()
    missing = [str(path) for path in (main_pack, proposal_pack) if not path.is_dir()]
    if missing:
        _emit({"status": "skipped_missing_input", "missing": missing}, args.json_path)
        return EXIT_SKIP

    try:
        probe = _probe(main_pack, proposal_pack, Path(tempfile.mkdtemp(prefix="m52-ac7-probe-")))
    except _BadInjection as exc:
        _emit({"gate_ok": None, "probe_ok": False, "reason": f"injection_anchor_missing: {exc}"},
              args.json_path)
        return EXIT_BAD_INJECTION

    document = _evaluate(main_pack, proposal_pack)
    document["probe"] = probe
    document["probe_ok"] = all(item["fired"] for item in probe) and len(probe) == 2
    # **覆盖范围（FIX-12 · r3）**：机器可读地声明本闸门**不覆盖**第三个包（Raven L-2 实证绕过路径），
    # 树级兜底是 `verify_specs.sh` 的 manifest 覆盖判据 —— 不留下「看起来覆盖全树」的印象。
    document["coverage"] = {
        "scanned_packs": [str(main_pack), str(proposal_pack)],
        "scans_districts_glob": False,
        "bypass_path": "new npcs placed in a THIRD pack under districts/ are not seen by this gate",
        "tree_level_backstop": "verify_specs.sh: 'manifest.txt does not cover file: <rel>' "
                               "(any new file under 02_source/** turns red)",
        "claim": "parameter-pair level criterion; tree-level additions are covered by the manifest backstop",
    }
    document["status"] = "measured"
    _emit(document, args.json_path)
    if args.probe_only:
        return EXIT_OK if document["probe_ok"] else EXIT_RED
    return EXIT_OK if document["gate_ok"] and document["probe_ok"] else EXIT_RED


def _emit(document: dict, json_path: str | None) -> None:
    text = json.dumps(document, ensure_ascii=False, sort_keys=True)
    sys.stdout.write(text + "\n")
    if json_path:
        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
