"""内核 CLI（V0 骨架，接口冻结、实现待做）。

冻结的命令面（01 设计 §4.3）：

    python -m deephealing_kernel run --pack <dir> --seed <int> --tick-rate 10 \\
        --events <path> --snapshot-every 50 --ws-port <int>
    python -m deephealing_kernel replay --events <path> --pack <dir> --until <tick> \\
        --checkpoint-every 50 --out <path> [--dump-divergence]
    python -m deephealing_kernel verify --events <path> --pack <dir> --expected-hash <hex>
    python -m deephealing_kernel validate --pack <dir>
    python -m deephealing_kernel pack sign <dir>

退出码约定：
    0 成功；1 校验失败（E_PACK_INVALID / 哈希分歧 / cassette miss）；2 用法错误。
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deephealing-kernel")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="启动世界（唯一权威进程）")
    run.add_argument("--pack", required=True)
    run.add_argument("--seed", type=int, default=None, help="缺省则用 pack 内 world.seed.json 的 seed")
    run.add_argument("--tick-rate", type=int, default=10)
    run.add_argument("--events", required=True)
    run.add_argument("--snapshot-every", type=int, default=50)
    run.add_argument("--ws-port", type=int, default=8787)
    run.add_argument("--replay", action="store_true", help="回放模式：能力强制走 cassette_replay 且 fail-closed")

    replay = sub.add_parser("replay", help="从 genesis 重放事件日志")
    replay.add_argument("--events", required=True)
    replay.add_argument("--pack", required=True)
    replay.add_argument("--until", type=int, default=None)
    replay.add_argument("--checkpoint-every", type=int, default=50)
    replay.add_argument("--out", required=True)
    replay.add_argument("--dump-divergence", action="store_true")

    verify = sub.add_parser("verify", help="重放并逐检查点比对 state_hash")
    verify.add_argument("--events", required=True)
    verify.add_argument("--pack", required=True)
    verify.add_argument("--expected-hash", default=None)

    validate = sub.add_parser("validate", help="校验内容包（pack.sig + 数据 schema）")
    validate.add_argument("--pack", required=True)

    pack = sub.add_parser("pack", help="内容包工具")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    sign = pack_sub.add_parser("sign", help="重新生成 pack.sig")
    sign.add_argument("dir")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # V0 骨架：命令面已冻结，实现见 08_v0_plan.md 的文件级任务清单。
    print(f"E_NOT_IMPLEMENTED: kernel command '{args.command}' is an interface stub (V0 plan not yet built)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
