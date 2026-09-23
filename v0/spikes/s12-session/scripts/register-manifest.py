#!/usr/bin/env python3
"""M3：把本轮**新增**的 02_source 文件登记进 manifest.txt（幂等；不删除既有行）。

用法：python3 spikes/s12-session/scripts/register-manifest.py <02_source>
"""
from __future__ import annotations

import sys
from pathlib import Path

NEW_ENTRIES = [
    ("worldview.schema.json",
     "世界观契约 schema（draft 2020-12）：tone.{surface,underneath} 可检查数值 / anomalies[] / fault_lines[]；禁止形容词字段",
     "手工编写（M3 / ADR-016）"),
    ("v0_skeleton/districts/xingfu-xiaoqu/worldview.json",
     "pack 世界观数据：两态基调（同一色板降明度）+ 异常锚点（表层读法/深层读法）+ 系统性故障线",
     "手工编写（M3 内容层，经 pack.entrypoints.worldview 登记）"),
    ("v0_skeleton/districts/xingfu-xiaoqu-north/worldview.json",
     "第二街区世界观数据（同契约；否则 required 会让 pack#2 load 失败）",
     "手工编写（M3 内容层）"),
    ("v0_skeleton/kernel/deephealing_kernel/rules/adaptation.py",
     "任务演进规则层：adaptation_rules 数据驱动、守卫先求值并短路（D-14）、max_shifts 硬上限、审计记录",
     "手工编写（M3 内核侧最小改动面）"),
    ("v0_skeleton/kernel/tests/test_task_adaptation.py",
     "AC-M3-5 判据：数据驱动迁移 / tick 边界 / 防刷短路 / max_shifts 上限 / 无 intent 基线逐位不变",
     "手工编写（M3 内核侧）"),
    ("v0_skeleton/session/src/protocol.js",
     "会话协议运行时：出入消息逐字段校验（additionalProperties:false / 枚举 / 条件必填）+ 冻结错误码",
     "手工编写（M3 会话层）"),
    ("v0_skeleton/session/bridge/kernel_bridge.py",
     "Python 驱动桥：复制 02_source 到运行目录后导入**副本**内核，stdin 读命令 / stdout 写 per-tick JSONL（D-2/D-8）",
     "手工编写（M3 会话层）"),
    ("v0_skeleton/web/test/render-client.test.ts",
     "渲染客户端判据：乱序 delta 丢弃 / observe 本地即拒 / apply 幂等",
     "手工编写（M3 渲染层）"),
    ("v0_skeleton/web/scripts/scene_assert.mjs",
     "治愈系数值断言 + 两态机器判据（two_reads_share_geometry / underneath_does_not_raise_saturation）",
     "手工编写（M3 渲染层）"),
    ("v0_skeleton/kernel/tests/test_budget_downgrade_void.py",
     "R2/M3-03 判据：预算耗尽降级时内核侧待应用队列**逐条作废**（intent.rejected{E_BUDGET_EXHAUSTED}）+ pending 归零 + 会话维度隔离 + 空队列零副作用",
     "手工编写（M3 修复轮 R2）"),
    ("v0_skeleton/tools/scan_ip_boundary.py",
     "R2/F12 判据载体：IP 边界扫描器（模式表 + 逐条理由白名单 + `--probe` 自证命中能力），进 verify_specs.sh",
     "手工编写（M3 修复轮 R2）"),
]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: register-manifest.py <02_source_dir>", file=sys.stderr)
        return 2
    manifest = Path(argv[1]).resolve() / "manifest.txt"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    existing = {line.split(" | ", 1)[0] for line in lines if line.strip()}
    added = 0
    for rel, purpose, how in NEW_ENTRIES:
        if rel in existing:
            print(f"SAME  {rel}")
            continue
        lines.append(f"{rel} | {purpose} | {how}")
        added += 1
        print(f"ADD   {rel}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"manifest lines={len(lines)} added={added}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
