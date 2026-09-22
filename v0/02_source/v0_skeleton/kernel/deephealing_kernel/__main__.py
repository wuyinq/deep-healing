"""`python3 -m deephealing_kernel` 入口（V0-M1 新增）。

冻结命令面（设计 §4.6）全部以 `python -m deephealing_kernel <subcommand>` 形式调用，
因此包内必须有 `__main__.py`；它只做一件事：把控制权交给 `cli.main`。
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
