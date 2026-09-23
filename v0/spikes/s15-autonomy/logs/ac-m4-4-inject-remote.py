#!/usr/bin/env python3
"""把「项目自身模型出口」注入隔离镜像的决策模块（AC-M4-4 反例 A）。

用法：python3 m4r2_inject_remote.py <decision.py 的绝对路径>

**锚点纪律**：`decision.py` 的 **docstring 里就有** `from . import behaviour_tree as bt` 这句话
（命名遮蔽说明）⇒ 用 `str.replace(..., 1)` 打这句话会把注入**打进 docstring**，
AST 代码面判据看不见它，反例就变成了假反例。故：
  ① 锚点取**真正的代码行**（`import copy`）；
  ② 写完用 AST **回验**：必须存在一个 `ImportFrom(module=~providers)` 节点，否则 exit 2。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ANCHOR = "\nimport copy\n"
INJECTED = "\nfrom ..providers import remote_api\nimport copy\n"
PROBE = "\n\n#: 反例探针：经项目自身 provider 出口引用模型调用面\nMODEL_EGRESS_PROBE = remote_api\n"


def main() -> int:
    target = Path(sys.argv[1])
    src = target.read_text(encoding="utf-8")
    if src.count(ANCHOR) != 1:
        print(f"E_ANCHOR_AMBIGUOUS: {ANCHOR!r} occurs {src.count(ANCHOR)} times", file=sys.stderr)
        return 2
    target.write_text(src.replace(ANCHOR, INJECTED, 1) + PROBE, encoding="utf-8")

    # ② AST 回验：注入必须落在**代码面**（不是 docstring / 不是字符串常量）
    tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    imports = [(node.lineno, node.module)
               for node in ast.walk(tree)
               if isinstance(node, ast.ImportFrom) and node.module and "providers" in node.module]
    names = [(node.lineno, node.id)
             for node in ast.walk(tree)
             if isinstance(node, ast.Name) and node.id == "remote_api"]
    if not imports or not names:
        print(f"E_INJECTION_NOT_ON_CODE_FACE: imports={imports} names={names}", file=sys.stderr)
        return 2
    print(f"injected into {target}")
    print(f"  ImportFrom(module contains 'providers') at lines {[line for line, _ in imports]}")
    print(f"  Name('remote_api') reference at lines {[line for line, _ in names]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
