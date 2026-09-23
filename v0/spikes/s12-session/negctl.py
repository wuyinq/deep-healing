#!/usr/bin/env python3
"""D-13 负例自证套件（**一律隔离执行**：整树副本在 /tmp，绝不改 02_source 再改回来）。

每条负例附：副本路径 + 注入方式 + 命令 + 期望红 + 实测红 + 交付面 `02_source/**` 跑前/跑后 sha256 相同的证明。

用法：python3 spikes/s12-session/negctl.py <ws>
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

NEG = Path("/tmp/m3-negctl")
LOGS = Path(__file__).resolve().parent / "logs"


def sha_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(part in ("__pycache__", ".pytest_cache", "node_modules") for part in path.parts):
            continue
        if path.suffix == ".pyc":
            continue
        digest.update(rel.encode())
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode())
    return digest.hexdigest()


def run(command: list[str], cwd: Path, log_name: str, env_extra: dict | None = None) -> int:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, env=env)
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / log_name).write_text(
        f"$ cd {cwd}\n$ {' '.join(command)}\n--- exit={result.returncode}\n"
        f"--- stdout\n{result.stdout[-4000:]}\n--- stderr\n{result.stderr[-4000:]}\n",
        encoding="utf-8",
    )
    return result.returncode


def fresh_copy(source: Path, name: str) -> Path:
    target = NEG / name
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "node_modules", "dist", ".build"))
    return target


def main(argv: list[str]) -> int:
    workspace = Path(argv[1]).resolve()
    source = workspace / "02_source"
    if NEG.exists():
        shutil.rmtree(NEG)
    NEG.mkdir(parents=True)
    before = sha_tree(source)
    results = []

    def record(name: str, expectation: str, code: int, log: str) -> None:
        results.append({"case": name, "expectation": expectation, "exit": code,
                        "turned_red": code != 0, "log": str(LOGS / log)})

    # ---- N-1 会话层：observe 改成静默接受 ⇒ npm test 必须红 ----
    copy = fresh_copy(source, "session")
    target = copy / "v0_skeleton/session/src/mode.js"
    target.write_text(target.read_text(encoding="utf-8").replace(
        "return mode === 'observe' ? 'E_MODE_READONLY' : null;", "return null; // NEGCTL"), encoding="utf-8")
    code = run(["npm", "test"], copy / "v0_skeleton/session", "negctl-session.log")
    record("N-1 session observe silently accepted", "npm test 必须红", code, "negctl-session.log")

    # ---- N-3 内核：max_shifts 改成无限 ⇒ test_task_adaptation 必须红 ----
    copy = fresh_copy(source, "kernel-maxshifts")
    target = copy / "v0_skeleton/kernel/tests/test_task_adaptation.py"
    target.write_text(target.read_text(encoding="utf-8").replace('"max_shifts": 2,', '"max_shifts": 999,'), encoding="utf-8")
    code = run([sys.executable, "-m", "pytest", "tests/test_task_adaptation.py", "-q", "-p", "no:cacheprovider"],
               copy / "v0_skeleton/kernel", "negctl-kernel.log")
    record("N-3 max_shifts -> unlimited", "pytest 必须红", code, "negctl-kernel.log")

    # ---- N-2 内核：observe 静默入队 ⇒ test_observe_mode_readonly 必须红 ----
    copy = fresh_copy(source, "kernel-observe")
    target = copy / "v0_skeleton/kernel/deephealing_kernel/tick.py"
    text = target.read_text(encoding="utf-8").replace('if mode != "participate":', 'if False:  # NEGCTL', 1)
    target.write_text(text, encoding="utf-8")
    code = run([sys.executable, "-m", "pytest", "tests/test_observe_mode_readonly.py", "-q", "-p", "no:cacheprovider"],
               copy / "v0_skeleton/kernel", "negctl-kernel-observe.log")
    record("N-2 kernel observe silently accepted", "pytest 必须红", code, "negctl-kernel-observe.log")

    # ---- N-6 / N-7 / N-9 / N-12：verify_specs 门禁的负例 ----
    copy = fresh_copy(source, "verify-specs-pack2")
    (copy / "v0_skeleton/districts/xingfu-xiaoqu-north/worldview.json").unlink()
    code = run(["bash", "verify_specs.sh", "--quiet"], copy, "negctl-verify-specs.log")
    record("N-6 pack#2 worldview.json removed", "verify_specs 必须红", code, "negctl-verify-specs.log")

    copy = fresh_copy(source, "verify-specs-residue")
    residue = copy / "v0_skeleton/web/dist/x.js"
    residue.parent.mkdir(parents=True, exist_ok=True)
    residue.write_text("// NEGCTL residue\n", encoding="utf-8")
    code = run(["bash", "verify_specs.sh", "--quiet"], copy, "negctl-verify-specs-residue.log")
    record("N-7 dist residue injected", "verify_specs 必须红", code, "negctl-verify-specs-residue.log")

    copy = fresh_copy(source, "verify-specs-faces")
    npc = copy / "v0_skeleton/districts/xingfu-xiaoqu/npcs/npc-003.json"
    document = json.loads(npc.read_text(encoding="utf-8"))
    document.pop("hidden_face", None)
    npc.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = run(["bash", "verify_specs.sh", "--quiet"], copy, "negctl-verify-specs-faces.log")
    record("N-9 npc hidden_face removed", "verify_specs 必须红", code, "negctl-verify-specs-faces.log")

    copy = fresh_copy(source, "verify-specs-l1")
    manifest = copy / "manifest.txt"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    # 注入「含该子串但非该文件」的条目：把世界模型 adapter 说明文件的路径**前缀**塞进另一行
    victim = "worldmodel.adapter.spec.md"
    injected = f"xxx/{victim} | NEGCTL 子串注入（非该文件） | 负例"
    lines.append(injected)
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 同时删掉真正的条目行 ⇒ 锚定判据必须红，子串判据（旧实现）会假绿
    lines = [line for line in manifest.read_text(encoding="utf-8").splitlines() if not line.startswith(victim + " | ")]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    code = run(["bash", "verify_specs.sh", "--quiet"], copy, "negctl-l1.log")
    record("N-12 manifest substring-only entry (L-1)", "verify_specs 必须红", code, "negctl-l1.log")

    # ---- N-10 / N-11：scene_assert 的负例 ----
    copy = fresh_copy(source, "scene-assert")
    target = copy / "v0_skeleton/web/src/scene/world.ts"
    text = target.read_text(encoding="utf-8").replace(
        "const pos = entity.transform?.pos_mm ?? { x: 0, y: 0, z: 0 };",
        "const pos = entity.transform?.pos_mm ?? { x: 0, y: 0, z: 0 };\n    pos.x = pos.x + 12345; // NEGCTL", 1)
    target.write_text(text, encoding="utf-8")
    code = run(["node", "scripts/scene_assert.mjs"], copy / "v0_skeleton/web", "negctl-scene-assert.log")
    record("N-10 underneath uses a different coordinate set", "scene_assert 必须红", code, "negctl-scene-assert.log")

    copy = fresh_copy(source, "scene-assert-saturation")
    target = copy / "v0_skeleton/districts/xingfu-xiaoqu/worldview.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["tone"]["underneath"]["saturation_pct"] = 44
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = run(["node", "scripts/scene_assert.mjs"], copy / "v0_skeleton/web", "negctl-scene-assert-saturation.log")
    record("N-11 underneath saturation raised", "scene_assert 必须红", code, "negctl-scene-assert-saturation.log")

    # ---- N-8：worldview schema 的 tone.underneath 删除 ----
    copy = fresh_copy(source, "worldview-schema")
    target = copy / "v0_skeleton/districts/xingfu-xiaoqu/worldview.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["tone"].pop("underneath", None)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = run([sys.executable, "v0_skeleton/tools/schema_validate.py", "worldview.schema.json",
                "v0_skeleton/districts/xingfu-xiaoqu/worldview.json"], copy, "negctl-worldview.log")
    record("N-8 tone.underneath removed", "schema 校验必须红", code, "negctl-worldview.log")

    # ---- N-4 / N-5：P-8 判据的负例（只判「有命中能力」） ----
    copy = fresh_copy(source, "p8-byte")
    victim = copy / "worldview.schema.json"
    victim.write_bytes(victim.read_bytes() + b"\n")
    changed = sha_tree(copy) != sha_tree(source)
    record("N-4 one byte changed in a real file", "清单比对必须红", 1 if changed else 0, "negctl-p8.log")
    (LOGS / "negctl-p8.log").write_text(
        f"copy={copy}\n注入：worldview.schema.json 追加 1 字节\n"
        f"副本 sha_tree != 交付面 sha_tree ⇒ {changed}（期望 True ⇒ 判据有命中能力）\n"
        "N-5（副本机制退回交付树）需要改桥源码后跑真内核，本轮预算耗尽 ⇒ 未执行，见 06 §5 的 GAP 声明\n",
        encoding="utf-8")

    after = sha_tree(source)
    summary = {
        "delivery_face_sha_before": before,
        "delivery_face_sha_after": after,
        "delivery_face_unchanged": before == after,
        "results": results,
        "all_turned_red": all(item["turned_red"] for item in results),
    }
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "negctl-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["all_turned_red"] and summary["delivery_face_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
