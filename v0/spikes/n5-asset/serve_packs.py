#!/usr/bin/env python3
"""取证用静态服务（N5 / 非交付面）：把内容包目录挂到 `/packs/**`。

`vite` 的 dev server 只服务 `web/`，而页面启动时 `loadWorldview()` 会 GET
`/packs/<district_pack_id>/worldview.json`（内容包在 `v0_skeleton/districts/<id>/`）。
本脚本把 `/packs/<id>/<rest>` **重写**为 `districts/<id>/<rest>` 后原样返回，
使真浏览器能完成 bootstrap（**只读**，零写盘）。

运行：`python3 v0/spikes/n5-asset/serve_packs.py --root <districts dir> --port 8791`
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import sys
from pathlib import Path


class RewriteHandler(http.server.SimpleHTTPRequestHandler):
    """把 /packs/<...> 映射到 <root>/<...>；其余路径 404。"""

    def translate_path(self, path: str) -> str:
        p = path.split("?", 1)[0].split("#", 1)[0]
        if not p.startswith("/packs/"):
            return os.path.join(self.directory, "__nonexistent__")
        rel = p[len("/packs/"):]
        rel = rel.replace("..", "")  # 目录穿越防护（取证服务，仅本机）
        return os.path.join(self.directory, rel)

    def log_message(self, fmt, *args):  # 静默，避免污染终端
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--port", type=int, default=8791)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"E_ENV: not a directory: {root}", file=sys.stderr)
        return 2
    handler = functools.partial(RewriteHandler, directory=str(root))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serve_packs: root={root} port={args.port}", flush=True)
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
