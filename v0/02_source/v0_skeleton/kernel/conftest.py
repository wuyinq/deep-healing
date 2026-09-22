"""把 `kernel/` 根插入 `sys.path`，使**裸 `pytest`** 与 `python3 -m pytest` 两种形态都能
`import deephealing_kernel`（预审 C2 关闭项）。

为什么需要：REQ §4 的 AC-M1-4 / AC-M1-5 字面写**裸 `pytest`**，而裸 `pytest` 的 `sys.path[0]`
是 console-script 目录，**cwd 不进 `sys.path`**；pytest 的 prepend 导入模式只把测试文件所在目录
（`kernel/tests/`）插进去，而 `kernel/` 下既无 conftest 也无 `[tool.pytest.ini_options] pythonpath`，
包也未安装 ⇒ `ModuleNotFoundError: No module named 'deephealing_kernel'`（architect 探针
`.squad_tools/probe_pytest_import.log` A/B/D 段已实证）。

本文件属 `kernel/**` 写集：**不改**任何冻结文件，也**不**改 REQ/设计里的命令文字。
"""

from __future__ import annotations

import sys
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parent
if str(KERNEL_ROOT) not in sys.path:
    sys.path.insert(0, str(KERNEL_ROOT))
