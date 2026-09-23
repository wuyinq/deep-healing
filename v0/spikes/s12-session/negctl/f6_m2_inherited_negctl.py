#!/usr/bin/env python3
"""F6 判据与负例（R2 / D-11 · R-M2-1 + R-M2-3）：两条「必须本轮关闭」的 M2 继承项。

判据（全部真跑，**整树副本**隔离执行）：
  **R-M2-1（pin 内容摘要绑定）**
    ① 阳性：副本上 `pytest tests/test_pins_resolution.py -q` 全绿（含 3 条 R2 新增摘要判据）；
    ② 负例：在副本里**取消摘要校验**（`_digest_problem` 恒返回 None）⇒ 摘要判据**必须变红**；
  **R-M2-3（目录符号链接 fail-closed）**
    ③ 阳性：副本工具对「含目录符号链接的 pack」`verify_pack` 必须 exit 1（报告 `symlinked directory`）；
    ④ 负例：在副本里**去掉目录链接守卫** ⇒ 同一 pack 必须被判绿（证明红是由该守卫造成的，判据有牙齿）。

用法：python3 -B spikes/s12-session/negctl/f6_m2_inherited_negctl.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

REGISTRY_REL = "v0_skeleton/kernel/deephealing_kernel/registry.py"
VERIFY_PACK_REL = "v0_skeleton/tools/verify_pack.py"
PACK_REL = "v0_skeleton/districts/xingfu-xiaoqu"

DISABLE_DIGEST_ANCHOR = (
    "        item = self._file_for(capability_id, version)\n"
    "        if item is None:\n"
    "            return None\n"
)
DISABLE_DIRLINK_ANCHOR = (
    "    dir_links = symlinked_directories(pack_dir)\n"
    "    if dir_links:\n"
)


def make_pack_with_dir_symlink(copy_root: Path) -> Path:
    """在副本里造一个「含目录符号链接（子树含文件）」的 pack。"""
    pack = copy_root / "dirsym-pack"
    shutil.copytree(copy_root / "02_source" / PACK_REL, pack)
    outside = copy_root / "outside-subtree"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "smuggled.json").write_text('{"smuggled": true}\n', encoding="utf-8")
    link = pack / "smuggled-dir"
    link.symlink_to(outside, target_is_directory=True)
    assert link.is_symlink() and link.resolve().is_dir()
    return pack


def pytest_run(copy_root: Path, target: str):
    return lib.run([sys.executable, "-B", "-m", "pytest", target, "-q", "-p", "no:cacheprovider"],
                   copy_root / "02_source" / "v0_skeleton" / "kernel", timeout=900)


CASES = [
    {"case": "f6_pristine", "expect_digest_red": False, "expect_verify_red": True, "inject": []},
    {"case": "f6_neg_pin_digest_disabled", "expect_digest_red": True, "expect_verify_red": True,
     "why": "取消摘要校验（R-M2-1 修复前形态）",
     "inject": [(REGISTRY_REL, DISABLE_DIGEST_ANCHOR, "        return None\n" + DISABLE_DIGEST_ANCHOR)]},
    {"case": "f6_neg_dir_symlink_guard_removed", "expect_digest_red": False, "expect_verify_red": False,
     "why": "去掉目录符号链接守卫（R-M2-3 修复前形态）",
     "inject": [(VERIFY_PACK_REL, DISABLE_DIRLINK_ANCHOR, "    dir_links = []\n    if dir_links:\n")]},
]


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []
    for spec in CASES:
        root = lib.fresh_copy(spec["case"])
        injections = [lib.inject(root / "02_source" / rel, old, new) for rel, old, new in spec["inject"]]

        digest_exit, digest_out, digest_err, digest_secs = pytest_run(root, "tests/test_pins_resolution.py")
        digest_red = digest_exit != 0

        pack = make_pack_with_dir_symlink(root)
        verify_exit, verify_out, verify_err, verify_secs = lib.run(
            [sys.executable, "-B", str(root / "02_source" / VERIFY_PACK_REL), str(pack)],
            root, timeout=300)
        verify_red = verify_exit == 1 and "symlinked directory in content pack" in (verify_out + verify_err)
        verify_ok_line = "verify_pack: OK" in verify_out

        ok = (digest_red == spec["expect_digest_red"]) and (verify_red == spec["expect_verify_red"])
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}\n# copy {root}\n# why {spec.get('why', '阳性对照')}\n"
                            f"# injections {injections}\n"
                            f"# pytest tests/test_pins_resolution.py exit={digest_exit} seconds={digest_secs}\n"
                            f"#   tail:\n" + "\n".join(digest_out.splitlines()[-6:]) + "\n"
                            f"# verify_pack <dirsym-pack> exit={verify_exit} seconds={verify_secs}\n"
                            f"#   stderr:\n{verify_err}\n#   stdout:\n{verify_out}\n")
        results.append({
            "case": spec["case"], "copy": str(root), "why": spec.get("why", "阳性对照"),
            "injections": injections, "log": str(log),
            "pin_digest_pytest_exit": digest_exit, "pin_digest_criterion_red": digest_red,
            "expect_pin_digest_red": spec["expect_digest_red"],
            "verify_pack_exit": verify_exit, "dir_symlink_reported": verify_red,
            "verify_pack_ok_line": verify_ok_line,
            "expect_dir_symlink_red": spec["expect_verify_red"], "ok": ok,
            "verdict": "judged_red" if (digest_red or verify_red) else "judged_green",
        })
        print(f"[{spec['case']}] pin_digest_red={digest_red} dir_symlink_red={verify_red} ok={ok}")
    after = lib.sha_tree(lib.SRC)
    summary = {"round": "R2", "item": "F6 R-M2-1 + R-M2-3 inherited items", "cases": results,
               "delivery_face_unchanged": before == after, "delivery_face_sha_tree": before,
               "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("f6-m2-inherited-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
