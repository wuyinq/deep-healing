#!/usr/bin/env python3
"""读取 JPEG 内嵌 **C2PA 清单**（JUMBF/CBOR）里的生成器事实（N5 / `AC-G-4c` 的外部锚）。

运行：
    python3 v0/spikes/n5-asset/c2pa_scan.py --path <jpg 路径> [--json]

为什么需要它：`AC-G-4c` 要求「生成件的 EXIF/XMP `Software` 与 `generator` 声明**不得矛盾**；
不可得 ⇒ 记 GAP 并进上抛」。本仓库无 `exiftool`，但 `doubao-seedream` 产出的 JPEG 内嵌了
**签发过的 C2PA 清单**（GlobalSign 证书链），其中 `c2pa.actions.v2` 断言携带
`softwareAgent.name` / `version` / `parameters.model_name` 与 IPTC `digitalSourceType`。

本脚本是**只读**取证工具：只用正则从字节流中定位 CBOR 段并抽取可打印键值，**不写任何交付文件**。
输出（默认人类可读；`--json` 给机读）：
    software_agent_name / software_agent_version / model_name / action / when /
    digital_source_type / claim_generator / c2pa_instance_id
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

C2PA_URN = re.compile(rb"urn:c2pa:[0-9a-f-]{36}")
ACTIONS = re.compile(
    rb"factionl?(?P<action>c2pa\.[a-z_.]+?)dwhen\.t(?P<when>[0-9T:\-Z]+)"
    rb"msoftwareAgent\.dnameq(?P<agent>[A-Za-z0-9_.\-]+?)gversione?(?P<agent_version>[0-9.]+)")
MODEL = re.compile(rb"model_names(?P<model>[A-Za-z0-9_.\-]+)")
DST = re.compile(rb"digitalSourceTypexF(?P<dst>http[^\x00-\x20]+)")
CLAIM_GEN = re.compile(rb"claim_generator_info\.dnameg(?P<name>[A-Za-z0-9_.\-]+)gversionf?(?P<ver>[0-9.]+)")
SOFTWARE_ALT = re.compile(rb"Software[\x00-\x20]{0,4}(?P<sw>[A-Za-z0-9_.\- ]{3,40})")

# CBOR 短字符串的「单字母前缀 + 键名」分隔符：抓取到的值尾部可能粘上下一个键，逐个切断
GLUED_KEYS = ["flog_idx", "fhttp", "qdigitalSourceType", "gversione", "gversion",
              "jparameters", "jmodel_name", "dwhen", "msoftwareAgent", "shash", "dtime",
              "twhen", "fdigitalSourceType", "qquality"]


def strip_glued(value: str) -> str:
    for key in GLUED_KEYS:
        if key in value:
            value = value.split(key)[0]
    return value.rstrip(".")


def scan(path: Path) -> dict:
    data = path.read_bytes()
    out: dict = {
        "path": str(path),
        "byte_size": len(data),
        "c2pa_present": b"c2pa" in data,
        "c2pa_instance_ids": sorted({m.decode() for m in C2PA_URN.findall(data)}),
    }
    m = ACTIONS.search(data)
    if m:
        out["action"] = m.group("action").decode()
        out["when"] = m.group("when").decode()
        out["software_agent_name"] = m.group("agent").decode().strip()
        out["software_agent_version"] = m.group("agent_version").decode()
    m = MODEL.search(data)
    if m:
        out["model_name"] = strip_glued(m.group("model").decode())
    m = DST.search(data)
    if m:
        out["digital_source_type"] = strip_glued(m.group("dst").decode())
    m = CLAIM_GEN.search(data)
    if m:
        out["claim_generator"] = f"{m.group('name').decode()} {m.group('ver').decode()}"
    m = SOFTWARE_ALT.search(data)
    if m:
        out["software_alt"] = m.group("sw").decode().strip()
    out["generator_declared_by_file"] = out.get("software_agent_name")
    out["verdict"] = "c2pa_verified" if out.get("model_name") else (
        "c2pa_present_no_model" if out["c2pa_present"] else "no_c2pa")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    p = Path(args.path)
    if not p.is_file():
        print(f"E_ENV: not a file: {p}", file=sys.stderr)
        return 2
    result = scan(p)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for k, v in result.items():
            print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
