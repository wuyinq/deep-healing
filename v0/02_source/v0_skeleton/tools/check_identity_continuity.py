#!/usr/bin/env python3
"""AC-6 人物跨 pack 身份映射判据（M5.2 r1 · **只读 pack 数据、内核零改动**）。

冻结契约（`district.pack.spec.md` §3 / ADR-008 / `test_second_district_requires_no_kernel_change`）：
新增街区的迁移路径 = 复制 → 改 id/version/display_name/bounds → 重签 `pack.sig`，**`kernel/` 零改动**。
⇒ 本判据**只读**两个 pack 的 NPC 档案，**不要求任何内核改动**。

口径（Raven C-3②，硬性）：
  - 身份键 = **`person_id`（人物级声明，落在 pack 数据里）**，`npc_id` 只是 pack 内的**局部名**；
  - **禁止**把身份绑在 pack 上（`<pack_id>:<npc_id>` 这类键）；
  - **红线不是「复制目录」**，而是「**用复制包宣称人物跨区连续**」：
    未声明 `person_id` 对齐的复制包 ⇒ 判据**必须**识别为**不连续**。

判据：`continuous = person_a 非空 and person_a == person_b`。

负对照（`--probe-only`；**三条都是判据，逐条给 `fired` 读数**）：
  - **正例**：提案包 vs「同 `person_id` 的第二 pack」（临时副本，改 `pack_id` 不删 `person_id`）
    ⇒ 判据识别为**同一人物**（`continuous == true`）；
  - **反例 A（Sentinel LOW-2 形态）**：**有该 NPC 但未声明 `person_id`** 的临时副本
    ⇒ **必须**识别为**不连续**（此前内置反例用的是 north + `npc-006`，而 north 下**根本没有**
    `npc-006.json` ⇒ 判「不连续」来自**文件缺失**，不是来自「未声明对齐」）；
  - **反例 B（Raven L-4 形态，强夹具）**：两包**都声明** `person_id` 但**不相等**
    ⇒ 此时 `person_a` / `person_b` **都非空**，「任一为空即 false」的短路**失效**，
    才真正检验比较逻辑 ⇒ **必须**判 `continuous == false`。

另给一条**信息性**读数（**不参与 `probe_ok`**）：主包 NPC vs 既有复制式第二街区
`xingfu-xiaoqu-north` 的**同名文件**（若存在）—— 它是**真实冻结产物**，
但 north 下没有 `npc-006.json` 时该读数只说明「文件缺失」，不作为判据。

输出末行 JSON：`{"continuous": bool, "person_a":..., "person_b":..., "kernel_change_required": false,
                   "probe_ok": bool, "probe": [...], "frozen_negative_reading": {...}}`
退出码：**0** 判据为「连续」且负对照成立；**1** 判据为「不连续」（反例命中，或正例失败）；
        **2** 前置输入缺失；**3** 注入锚点失效。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

EXIT_OK, EXIT_RED, EXIT_SKIP, EXIT_BAD_INJECTION = 0, 1, 2, 3


class _BadInjection(Exception):
    pass


def _person_id(pack_dir: Path, npc_id: str) -> str | None:
    path = pack_dir / "npcs" / f"{npc_id}.json"
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    value = document.get("person_id")
    return str(value) if isinstance(value, str) and value.strip() else None


def _compare(pack_a: Path, npc_a: str, pack_b: Path, npc_b: str) -> dict:
    person_a = _person_id(pack_a, npc_a)
    person_b = _person_id(pack_b, npc_b)
    return {
        "pack_a": str(pack_a), "npc_a": npc_a, "person_a": person_a,
        "pack_b": str(pack_b), "npc_b": npc_b, "person_b": person_b,
        "continuous": bool(person_a and person_b and person_a == person_b),
        "kernel_change_required": False,
    }


def _write_npc(pack_dir: Path, npc_id: str, mutate) -> None:
    """就地改一份 NPC 档案（临时副本专用；`mutate` 收到 dict 并原地改）。"""
    path = pack_dir / "npcs" / f"{npc_id}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clone_pack(source: Path, target: Path, *, pack_id: str) -> None:
    """复制 pack 并改 `pack_id`（保持**只改 id** 这一最小变量）。"""
    shutil.copytree(source, target)
    manifest_path = target / "pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["id"] = pack_id
    manifest["version"] = "0.2.0"
    manifest["display_name"] = f"AC-6 负对照夹具：{pack_id}（仅用于判据自证）"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _probe(positive_pack: Path, positive_npc: str, pack_b: Path, npc_b: str,
           negative_pack: Path, workdir: Path) -> tuple[list[dict], dict]:
    """三条**判据性**负对照 + 一条**信息性**真实产物读数。

    判据性三条（`probe_ok` = 三条都 `fired`）：
      ① 正例：改 `pack_id` **保留** `person_id` ⇒ 必须判「同一人物」；
      ② 反例 A：**有该 NPC 但删掉 `person_id`** ⇒ 必须判「不连续」（Sentinel LOW-2：旧内置反例的
         「不连续」来自 north 下没有 `npc-006.json` 这个**文件缺失**，不是来自「未声明对齐」）；
      ③ 反例 B：两包**都声明** `person_id` 但**不相等** ⇒ 短路失效，必须判「不连续」（Raven L-4）。
    """
    cases: list[dict] = []
    mirror_root = workdir / "mirror"

    # ① 正例：镜像第二 pack（改 pack_id，**保留** person_id）
    mirror = mirror_root / f"{positive_pack.name}-mirror"
    _clone_pack(positive_pack, mirror, pack_id=f"{positive_pack.name}-mirror")
    if _person_id(mirror, positive_npc) is None:
        raise _BadInjection("positive: mirror pack lost person_id")
    positive = _compare(positive_pack, positive_npc, mirror, positive_npc)
    cases.append({"case": "same_person_id_across_packs", "fired": positive["continuous"] is True,
                  "reading": {"person_a": positive["person_a"], "person_b": positive["person_b"]}})

    # ② 反例 A：**有该 NPC 但未声明 person_id**（文件存在 ⇒ 短路不成立）
    stripped = mirror_root / f"{positive_pack.name}-noperson"
    _clone_pack(positive_pack, stripped, pack_id=f"{positive_pack.name}-noperson")
    _write_npc(stripped, positive_npc, lambda doc: doc.pop("person_id", None))
    if _person_id(stripped, positive_npc) is not None:
        raise _BadInjection("negative-a: person_id still present after strip")
    no_person = _compare(positive_pack, positive_npc, stripped, positive_npc)
    cases.append({"case": "same_npc_without_person_id_declaration",
                  "fired": no_person["continuous"] is False,
                  "reading": {"person_a": no_person["person_a"], "person_b": no_person["person_b"],
                              "npc_file_exists": (stripped / "npcs" / f"{positive_npc}.json").is_file()}})

    # ③ 反例 B（强夹具）：两包**都声明** person_id 但**不相等** ⇒ 短路失效，检验比较逻辑本体
    mismatched = mirror_root / f"{positive_pack.name}-mismatch"
    _clone_pack(positive_pack, mismatched, pack_id=f"{positive_pack.name}-mismatch")
    declared = _person_id(positive_pack, positive_npc)
    _write_npc(mismatched, positive_npc,
               lambda doc: doc.__setitem__("person_id", f"{declared}-other"))
    person_b_mismatch = _person_id(mismatched, positive_npc)
    if person_b_mismatch is None or person_b_mismatch == declared:
        raise _BadInjection("negative-b: mismatched person_id not injected")
    mismatch = _compare(positive_pack, positive_npc, mismatched, positive_npc)
    cases.append({"case": "both_packs_declare_person_id_but_unequal",
                  "fired": mismatch["continuous"] is False,
                  "reading": {"person_a": mismatch["person_a"], "person_b": mismatch["person_b"],
                              "short_circuit_inactive": bool(mismatch["person_a"] and mismatch["person_b"])}})

    # 信息性（**不参与 probe_ok**）：真实冻结产物 north —— 缺 npc 文件时只说明「文件缺失」
    frozen: dict = {"pack": str(negative_pack), "judged": False}
    npc_file = negative_pack / "npcs" / f"{npc_b}.json"
    frozen["npc_file_exists"] = npc_file.is_file()
    if negative_pack.is_dir() and npc_file.is_file():
        comparison = _compare(pack_b, npc_b, negative_pack, npc_b)
        frozen.update({"person_a": comparison["person_a"], "person_b": comparison["person_b"],
                       "continuous": comparison["continuous"]})
    return cases, frozen


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AC-6 cross-pack identity continuity")
    parser.add_argument("--pack-a", required=True)
    parser.add_argument("--npc-a", required=True)
    parser.add_argument("--pack-b", required=True)
    parser.add_argument("--npc-b", required=True)
    parser.add_argument("--positive-pack", default=None,
                        help="含 person_id 声明的 pack，用于正例自证（默认 = --pack-a）")
    parser.add_argument("--positive-npc", default="npc-006")
    parser.add_argument("--negative-pack", default=None,
                        help="反例用的既有复制式第二街区（默认 = <pack-b 的父目录>/xingfu-xiaoqu-north）")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args(argv)

    pack_a = Path(args.pack_a).expanduser()
    pack_b = Path(args.pack_b).expanduser()
    positive_pack = Path(args.positive_pack).expanduser() if args.positive_pack else pack_a
    negative_pack = Path(args.negative_pack).expanduser() if args.negative_pack \
        else pack_b.parent / "xingfu-xiaoqu-north"
    missing = [str(path) for path in (pack_a, pack_b, positive_pack) if not path.is_dir()]
    if missing:
        _emit({"status": "skipped_missing_input", "missing": missing}, args.json_path)
        return EXIT_SKIP

    try:
        probe, frozen = _probe(positive_pack, args.positive_npc, pack_b, args.npc_b, negative_pack,
                               Path(tempfile.mkdtemp(prefix="m52-ac6-probe-")))
    except _BadInjection as exc:
        _emit({"continuous": None, "probe_ok": False, "reason": f"injection_anchor_missing: {exc}"},
              args.json_path)
        return EXIT_BAD_INJECTION

    document = _compare(pack_a, args.npc_a, pack_b, args.npc_b)
    document["probe"] = probe
    document["frozen_negative_reading"] = frozen
    document["probe_ok"] = all(item["fired"] for item in probe) and len(probe) == 3
    document["status"] = "measured"
    _emit(document, args.json_path)
    if args.probe_only:
        return EXIT_OK if document["probe_ok"] else EXIT_RED
    return EXIT_OK if document["continuous"] and document["probe_ok"] else EXIT_RED


def _emit(document: dict, json_path: str | None) -> None:
    text = json.dumps(document, ensure_ascii=False, sort_keys=True)
    sys.stdout.write(text + "\n")
    if json_path:
        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
