"""provider 适配器目录（`kernel_digest.py` 的**豁免面**）。

`ADAPTER_DIRS = ("adapters/", "providers/adapters/")`：新增能力的实现体落在本目录时，
「新增能力不改内核代码」的差集判据仍然成立（`changed == []` 且 `added ⊆ adapter 目录并集`）。
"""

from __future__ import annotations
