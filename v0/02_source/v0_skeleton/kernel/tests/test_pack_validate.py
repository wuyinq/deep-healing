"""RED 用例：内容包校验与「新增第二街区不改内核代码」（AC-M1-4）。

覆盖设计 §6 的 R8/R9/R10/R11/R23。所有用例一律在 `tmp_path` 副本上操作，
**禁止**原地篡改 `districts/**`（否则 `pack.sig` 失配连带 AC-M1-1 变红）。

冻结运行形态（两种形态都必须能跑，预审 C2）：
    cd <workspace>/02_source/v0_skeleton/kernel && pytest tests/test_pack_validate.py -q
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_pack_validate.py -q -p no:cacheprovider
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
WS_ROOT = KERNEL_ROOT.parents[2]

from deephealing_kernel.pack import PackInvalid, load_pack, verify_signature  # noqa: E402

_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "deephealing_kernel", *args],
        capture_output=True, text=True, cwd=str(KERNEL_ROOT), env=_ENV,
    )


def _validate(pack: Path) -> subprocess.CompletedProcess:
    return _cli("validate", "--pack", str(pack))


def _sign(pack: Path) -> subprocess.CompletedProcess:
    return _cli("pack", "sign", str(pack))


def _copy_pack(dest: Path) -> Path:
    shutil.copytree(PACK_DIR, dest)
    return dest


def _kernel_digest(root: Path) -> dict:
    tool = _load_module("kernel_digest_for_pack_test", KERNEL_ROOT / "tools" / "kernel_digest.py")
    return tool.kernel_digest(root)


def _world_schema() -> dict:
    return json.loads((WS_ROOT / "02_source" / "world.schema.json").read_text(encoding="utf-8"))


def _pack_schema() -> dict:
    return json.loads((WS_ROOT / "02_source" / "district.pack.schema.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- R8
def test_pack_validates_and_signature_matches(tmp_path):
    """样例 pack 校验通过，pack.sig 逐文件比对通过；portal 边在目标未加载时标 inactive。"""
    pack = load_pack(PACK_DIR)
    assert pack.manifest["id"] == "xingfu-xiaoqu"
    assert len(pack.npcs) == 5
    assert len(pack.buildings) == 2
    assert pack.world_seed["seed"] == 20260921
    # U2：weather 被**显式读取**（内容包声明了它），但不进内核 state
    assert "weather" in pack.world_seed

    assert verify_signature(PACK_DIR) == []
    assert _validate(PACK_DIR).returncode == 0

    from deephealing_kernel.pack import build_portal_edges

    edges = build_portal_edges({pack.manifest["id"]: pack})
    assert len(edges) == 1
    assert edges[0]["to_pack_id"] == "xingfu-xiaoqu-north"
    assert edges[0]["status"] == "inactive", "目标 pack 未加载时边必须保留并标 inactive"


# --------------------------------------------------------------------------- R9
def test_tampered_pack_fails_closed(tmp_path):
    """篡改任一数据文件后校验必须失败（E_PACK_INVALID，非 0 退出）。"""
    tampered = _copy_pack(tmp_path / "tampered")
    target = tampered / "npcs" / "npc-001.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["display_name"] = payload["display_name"] + "（被篡改）"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PackInvalid):
        load_pack(tampered)
    problems = verify_signature(tampered)
    assert any(p.startswith("hash_mismatch: npcs/npc-001.json") for p in problems), problems
    assert _validate(tampered).returncode != 0

    # 反向对照：原样 pack 必须 exit 0（证明上面不是恒红）
    assert _validate(PACK_DIR).returncode == 0


# --------------------------------------------------------------------------- R10
def test_second_district_requires_no_kernel_change(tmp_path):
    """复制 pack → 改 id/version → 重签 → validate 通过；`kernel/` 源码零改动。"""
    before = _kernel_digest(KERNEL_ROOT)["digest"]

    second = _copy_pack(tmp_path / "xingfu-xiaoqu-north")
    manifest_path = second / "pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["id"] = "xingfu-xiaoqu-north"
    manifest["version"] = "0.2.0"
    manifest["display_name"] = "幸福小区北区（第二街区，零内核改动）"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 未重签 ⇒ 必须失败
    assert _validate(second).returncode != 0

    signed = _sign(second)
    assert signed.returncode == 0, signed.stdout + signed.stderr
    assert _validate(second).returncode == 0

    after = _kernel_digest(KERNEL_ROOT)["digest"]
    assert before == after, "新增第二街区不得改动 kernel/ 源码"

    # 反向对照：把 pack.sig 里的一个 sha256 改错 ⇒ 必须非 0
    sig_path = second / "pack.sig"
    signature = json.loads(sig_path.read_text(encoding="utf-8"))
    signature["entries"][0]["sha256"] = "0" * 64
    sig_path.write_text(json.dumps(signature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _validate(second).returncode != 0


# --------------------------------------------------------------------------- R11
def test_executable_file_in_pack_is_rejected(tmp_path):
    """内容包里出现 `.py`（含改名后内容魔数）必须被拒绝（内容层只有数据）。

    **T-2 判据口径改写（ADR-13 同批；M2 / P-5）**：
      改前断言：`_sign(by_magic).returncode == 0`（编码的是 docstring 自称的「L3 已知缺陷：
      写侧只按后缀名」）。改后断言：**必须非 0** —— P-5 正是来关掉该缺陷。
      为什么不是放松判据：不是把负例改正例。改名 shebang 内容仍然**必须被拒**，
      只是拒的位置从「只读侧」变成「读写两侧」；判据由 1 处变 2 处，强度只增不减。
      自证反例：把 `pack_sign.py` 退回「只按后缀名」⇒ 本用例第一段（`returncode != 0`）必红；
      独立反例脚本 `.squad_tools/artisan-p5-revert-negative-control.py` 用仓库 HEAD 的
      修复前工具实测 exit 0（判据确实有牙齿）。
    """
    # ① 后缀名判据：pack_sign 与 validate 都必须拒绝
    by_suffix = _copy_pack(tmp_path / "evil_suffix")
    (by_suffix / "payload.py").write_text("print('nope')\n", encoding="utf-8")
    assert _sign(by_suffix).returncode != 0, "pack sign 必须拒绝含 .py 的内容包"
    assert _validate(by_suffix).returncode != 0, "含 .py 的 pack 必须被拒收"

    # ② 内容魔数判据（改名绕过后缀名）：**写侧与读侧都必须拒收**（P-5 关闭 L3 已知缺陷）
    by_magic = _copy_pack(tmp_path / "evil_magic")
    (by_magic / "assets" / "notes.txt").write_bytes(b"#!/bin/sh\necho nope\n")
    signed = _sign(by_magic)
    assert signed.returncode != 0, "P-5 之后 pack sign 必须按内容魔数拒收改名后的 shebang 内容"
    assert "E_PACK_INVALID" in (signed.stdout + signed.stderr), signed.stdout + signed.stderr
    assert _validate(by_magic).returncode != 0, "改名后的 shebang 内容必须被魔数判据拒收"

    # 判据归因（证明拒收来自**内容魔数**而不是后缀名，即 P-5 的加固面真的可达）
    sign_tool = _load_module("pack_sign_reference", WS_ROOT / "02_source" / "v0_skeleton" / "tools" / "pack_sign.py")
    assert Path("notes.txt").suffix not in sign_tool.FORBIDDEN_SUFFIXES
    assert sign_tool.executable_kind(by_magic / "assets" / "notes.txt") == "shebang 脚本"

    # 反向对照：干净 pack 必须 exit 0
    assert _validate(PACK_DIR).returncode == 0


# --------------------------------------------------------------------------- R23
def test_seed_projection_passes_world_schema(tmp_path):
    """**T-1 判据口径改写（ADR-13）**：`world.seed.json` **原样**必须过 `world.schema.json`（单口径）。

    改前断言：`projection`（去 weather）过 schema，且**原样（含 weather）必红** ——
      那是契约矛盾（K1）的机器可读证据，前提是「矛盾存在」。
    改后断言：**原样**过 schema（`world.schema.json` 顶层已补 `weather`，ADR-13），
      双口径消失；并补 `additionalProperties:false` 的牙齿（未声明字段 `humidity` ⇒ 必红）。
    为什么不是放松判据：判据没有变空 —— 它从「schema 拒收 weather」换成
      「schema **接受** weather（与 `$defs/worldSeed` 同构）但**仍然拒收未声明字段**」，
      牙齿由 `humidity` 负例承担；原样的两条结构负例（缺 `transform` / `kind` 非法）**逐字保留**。
    自证反例：把 `world.schema.json` 顶层的 `weather` 去掉（= 退回改前形态）⇒
      本用例的「原样过 schema」必红（脚本内即时构造该退化 schema 验证，见下 `degraded`）。

    负例自证：缺 `transform` / `kind` 非法的 seed 副本 **重签之后** 仍必须被 `validate` 拒收
    （证明拦截来自 schema 强口径，而不是签名失配）；同时断言弱口径 `$defs/worldSeed`
    对同一份损坏 seed **是绿的**（证明若只用弱口径就是假绿）。
    """
    import jsonschema

    world_schema = _world_schema()
    pack_schema = _pack_schema()
    world_seed_def = {"$schema": pack_schema["$schema"], "$ref": "#/$defs/worldSeed",
                      "$defs": pack_schema["$defs"]}

    raw_seed = json.loads((PACK_DIR / "world.seed.json").read_text(encoding="utf-8"))
    assert "weather" in raw_seed
    # 单口径：**原样**即通过 world.schema.json（改后断言）
    jsonschema.validate(raw_seed, world_schema)
    # 投影退化为恒等（pack.py 的补偿路径保留调用、语义已是恒等）
    projection = {k: v for k, v in raw_seed.items() if k != "weather"}
    assert set(projection) == {"schema_version", "seed", "tick", "constants", "entities"}
    jsonschema.validate(projection, world_schema)
    # 原样对 $defs/worldSeed 仍然绿（weather 声明合法）
    jsonschema.validate(raw_seed, world_seed_def)

    # ---- 负例 0（自证反例）：退回「schema 无 weather」形态 ⇒ 上面那条正向断言必红 ----
    degraded = json.loads(json.dumps(world_schema))
    del degraded["properties"]["weather"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw_seed, degraded)

    # ---- 负例 1：`additionalProperties:false` 未被放松（未声明字段 humidity ⇒ 必红）----
    with_humidity = json.loads(json.dumps(raw_seed))
    with_humidity["humidity"] = 0.5
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(with_humidity, world_schema)
    # 顶层 weather 自身也是 additionalProperties:false（未声明的子字段 ⇒ 必红）
    bad_weather = json.loads(json.dumps(raw_seed))
    bad_weather["weather"]["pressure_hpa"] = 1013
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_weather, world_schema)

    # ---- 负例 A：缺 transform ----
    broken = _copy_pack(tmp_path / "broken_transform")
    seed_path = broken / "world.seed.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    del seed["entities"][7]["transform"]
    seed_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _sign(broken).returncode == 0, "重签必须先成功，才能证明拦截来自 schema 口径"
    assert _validate(broken).returncode != 0, "缺 transform 的 seed 必须在重签后仍被拒收"
    # 弱口径对同一份损坏 seed 是**绿**的 ⇒ 只用 $defs/worldSeed 就是假绿
    jsonschema.validate(seed, world_seed_def)

    # ---- 负例 B：kind 非法 ----
    broken_kind = _copy_pack(tmp_path / "broken_kind")
    seed_path = broken_kind / "world.seed.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    seed["entities"][7]["kind"] = "wizard"
    seed_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _sign(broken_kind).returncode == 0
    assert _validate(broken_kind).returncode != 0, "kind 非法的 seed 必须在重签后仍被拒收"
    jsonschema.validate(seed, world_seed_def)


# --------------------------------------------------------------------------- 路径安全
def test_pack_rejects_path_escape(tmp_path):
    """`pack.json` 的 entrypoints 出现 `..` / 绝对路径 → 必须拒收（防越界读取）。

    **归因声明（修复轮 C2）**：冻结 schema 把 `entrypoints` 的 6 个值钉成 `const`
    ⇒ 该输入在**schema 层**就被拦下（Sentinel Bug#3），**不会**走到路径守卫。
    所以本用例的断言分两段，且**不得**把「任意非 0」当作守卫生效的证据：
      (a) 端到端拒绝**归因到具体字段**（`entrypoints/assets_manifest`）；
      (b) 对**同一恶意值**直接调用路径守卫，断言原因字符串（守卫本身可达且判据非空）。
    """
    escaped = _copy_pack(tmp_path / "escape")
    manifest_path = escaped / "pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entrypoints"]["assets_manifest"] = "../../../etc/passwd"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _sign(escaped).returncode == 0

    proc = _validate(escaped)
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    # (a) 归因到具体字段，而不是「任意非 0 就算过」
    assert "entrypoints/assets_manifest" in combined, combined

    # (b) 同一恶意值直达守卫：原因字符串必须逐字命中
    from deephealing_kernel import pack as pack_mod

    assert pack_mod._guard_relpath("../../../etc/passwd") == "parent traversal not allowed: ../../../etc/passwd"
    assert pack_mod._guard_relpath("/etc/passwd") == "absolute path not allowed: /etc/passwd"
    assert pack_mod._guard_relpath("assets/manifest.json") is None


def _assert_guard_rejects(guard):
    """把「守卫必须拒绝」的判据抽成可复用函数，供反向对照使用。"""
    assert guard("../../../etc/passwd") == "parent traversal not allowed: ../../../etc/passwd"
    assert guard("/etc/passwd") == "absolute path not allowed: /etc/passwd"


def test_guard_relpath_negative_control(monkeypatch):
    """反向对照（C2）：把守卫换成恒 `None` ⇒ 上面的判据必须**失败**（证明判据不是恒绿）。"""
    from deephealing_kernel import pack as pack_mod

    _assert_guard_rejects(pack_mod._guard_relpath)          # 真实现 ⇒ 判据成立
    monkeypatch.setattr(pack_mod, "_guard_relpath", lambda rel: None)
    with pytest.raises(AssertionError):
        _assert_guard_rejects(pack_mod._guard_relpath)      # 恒 None ⇒ 判据必须炸


def test_pack_rejects_symlink_escape(tmp_path):
    """修复轮 B3 / 预审 R7：包内文件**符号链接指向包外** ⇒ 必须 fail-closed。

    原先 `rglob` + `read_bytes` 会静默跟随符号链接，把包外文件读进来当包内容
    （`pack.sig` 也按解析后的内容核对 ⇒ 签名挡不住）。
    """
    escaped = _copy_pack(tmp_path / "symlink" / "xingfu-xiaoqu")
    outside = tmp_path / "symlink" / "outside-world.seed.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text((escaped / "world.seed.json").read_text(encoding="utf-8"), encoding="utf-8")

    link = escaped / "world.seed.json"
    link.unlink()
    link.symlink_to(outside)
    assert link.is_symlink() and link.resolve() == outside.resolve()

    proc = _validate(escaped)
    assert proc.returncode != 0, "包内符号链接指向包外必须被拒收"
    assert "symlink escape" in (proc.stdout + proc.stderr), proc.stdout + proc.stderr

    # 反向对照：把符号链接换成**包内**目标的真文件 ⇒ 必须仍然 exit 0（不是「有链接就红」）
    inside_target = escaped / "world.seed.copy.json"
    inside_target.write_text(outside.read_text(encoding="utf-8"), encoding="utf-8")
    link.unlink()
    link.write_text(inside_target.read_text(encoding="utf-8"), encoding="utf-8")
    inside_target.unlink()
    assert _sign(escaped).returncode == 0
    assert _validate(escaped).returncode == 0


def test_pack_rejects_symlink_pack_sig(tmp_path):
    """F4 / R17：`pack.sig` 读点也必须过符号链接守卫（它原先是**唯一**未守卫的读取点）。"""
    from deephealing_kernel import pack as pack_mod

    escaped = _copy_pack(tmp_path / "sigsym" / "xingfu-xiaoqu")
    outside = tmp_path / "sigsym" / "outside.pack.sig"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text((escaped / "pack.sig").read_text(encoding="utf-8"), encoding="utf-8")

    link = escaped / "pack.sig"
    link.unlink()
    link.symlink_to(outside)
    assert link.is_symlink()

    proc = _validate(escaped)
    assert proc.returncode != 0, "pack.sig 指向包外必须被拒收"
    assert "symlink_escape" in (proc.stdout + proc.stderr), proc.stdout + proc.stderr

    # F5：`verify_signature()` 必须**返回**问题清单（不抛异常），保持 `-> list[str]` 契约
    problems = pack_mod.verify_signature(escaped)
    assert isinstance(problems, list) and problems, problems
    assert any(item.startswith("symlink_escape:") for item in problems), problems

    # 反向对照：换回包内的真文件 ⇒ 必须 exit 0（不是「有链接就红」）
    link.unlink()
    link.write_text(outside.read_text(encoding="utf-8"), encoding="utf-8")
    assert _validate(escaped).returncode == 0
    assert pack_mod.verify_signature(escaped) == []


def test_verify_signature_returns_list_never_raises(tmp_path):
    """F5 / R19：逃逸路径下 `verify_signature()` 返回非空 list（**不抛** `PackInvalid`）。"""
    from deephealing_kernel import pack as pack_mod

    escaped = _copy_pack(tmp_path / "sigret" / "xingfu-xiaoqu")
    outside = tmp_path / "sigret" / "outside-world.seed.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text((escaped / "world.seed.json").read_text(encoding="utf-8"), encoding="utf-8")

    link = escaped / "world.seed.json"
    link.unlink()
    link.symlink_to(outside)

    problems = pack_mod.verify_signature(escaped)          # 不得抛
    assert isinstance(problems, list) and problems, problems
    assert any("symlink_escape" in item for item in problems), problems
    # `load_pack` 仍 fail-closed：它把非空清单转成 `PackInvalid`
    with pytest.raises(pack_mod.PackInvalid):
        pack_mod.load_pack(escaped)
    # 正常 pack 的列表语义仍成立（既有断言 `verify_signature(PACK_DIR) == []`）
    assert pack_mod.verify_signature(PACK_DIR) == []


def test_pack_docstring_matches_implementation():
    """修复轮 B4：`pack.py` 的校验顺序 docstring 必须与实现一致（不再谎报「各数据文件 schema」）。"""
    from deephealing_kernel import pack as pack_mod

    doc = pack_mod.__doc__ or ""
    assert "只做 JSON 可解析性检查" in doc
    assert "各数据文件 schema" not in doc
    assert "五层" in doc

    # 判据非空：`district.pack.schema.json` **只有**三个 $defs ⇒ 五层数据面确实没有 schema 可用
    pack_schema = json.loads((WS_ROOT / "02_source" / "district.pack.schema.json").read_text(encoding="utf-8"))
    assert set(pack_schema["$defs"]) == {"packManifest", "packSig", "worldSeed"}
    # 实现只对 pack.json 与 world.seed.json 调 schema（+ world.seed 投影过一次 world.schema.json）
    source = (KERNEL_ROOT / "deephealing_kernel" / "pack.py").read_text(encoding="utf-8")
    assert source.count("_validate_schema(") == 4, source.count("_validate_schema(")  # 定义 1 + 调用 3


def test_pack_rejects_symlinked_directory(tmp_path):
    """**R2 / R-M2-3 收口（F6）**：pack 内的**目录**符号链接必须被显式报告 / 拒收，不得静默跳过。

    修复前（继承 M1 R16/R18）：`rglob('*')` 不递归进目录链接、`is_file()` 对目录链接为 `False`
    ⇒ 该子树**既不被 hash、也不报 undeclared_file** ⇒ 工具侧 `verify_pack: OK`（假绿）。
    """
    pack = _copy_pack(tmp_path / "dirsym" / "xingfu-xiaoqu")
    outside = tmp_path / "dirsym" / "outside-subtree"
    outside.mkdir(parents=True)
    (outside / "smuggled.json").write_text('{"smuggled": true}\n', encoding="utf-8")
    link = pack / "smuggled-dir"
    link.symlink_to(outside, target_is_directory=True)
    assert link.is_symlink() and link.resolve().is_dir()

    verify_tool = _load_module("verify_pack_reference", WS_ROOT / "02_source" / "v0_skeleton" / "tools" / "verify_pack.py")
    sign_tool = _load_module("pack_sign_dir_reference", WS_ROOT / "02_source" / "v0_skeleton" / "tools" / "pack_sign.py")

    # ① 读侧工具必须拒收（且不得输出 OK）
    proc = subprocess.run([sys.executable, str(verify_tool.__file__), str(pack)],
                          capture_output=True, text=True, env=_ENV)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "symlinked directory in content pack" in (proc.stdout + proc.stderr), proc.stdout + proc.stderr
    assert "verify_pack: OK" not in proc.stdout

    # ② 写侧工具必须拒绝对它签名（否则 `pack.sig` 会漏掉整棵被跳过的子树）
    with pytest.raises(SystemExit) as caught:
        sign_tool.build_signature(pack)
    assert "symlinked directory" in str(caught.value), str(caught.value)

    # ③ 漂移守卫：两侧的目录链接枚举必须逐项一致
    assert ([str(item) for item in verify_tool.symlinked_directories(pack)]
            == [str(item) for item in sign_tool.symlinked_directories(pack)]
            == [str(link)])

    # ④ 阳性对照：移除目录链接 ⇒ 必须恢复 OK（证明该判据不是「恒红」）
    link.unlink()
    proc2 = subprocess.run([sys.executable, str(verify_tool.__file__), str(pack)],
                           capture_output=True, text=True, env=_ENV)
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr
    assert "verify_pack: OK" in proc2.stdout
    sign_tool.build_signature(pack)  # 不得抛


def test_pack_sign_and_verify_use_same_executable_criteria(tmp_path):
    """漂移守卫：三处可执行判据常量必须逐条一致 —— `pack.py` / `tools/verify_pack.py` /
    `tools/pack_sign.py`（**M2 / P-5 扩展**：写侧原先只按后缀名，判据漂移面从 2 处变 3 处）。

    自证反例：把 `pack_sign.py` 的 `EXECUTABLE_MAGICS` 去掉一条（或退回只按后缀名）⇒
    本用例第一条 `tuple(...) == tuple(...)` 必红。
    """
    from deephealing_kernel import pack as pack_mod

    reference = _load_module("verify_pack_reference", WS_ROOT / "02_source" / "v0_skeleton" / "tools" / "verify_pack.py")
    sign_tool = _load_module("pack_sign_reference", WS_ROOT / "02_source" / "v0_skeleton" / "tools" / "pack_sign.py")
    assert pack_mod.FORBIDDEN_SUFFIXES == reference.FORBIDDEN_SUFFIXES
    assert tuple(pack_mod.EXECUTABLE_MAGICS) == tuple(reference.EXECUTABLE_MAGICS)
    # P-5 扩展：写侧（pack_sign.py）必须与读侧逐条同判据（后缀 + 内容魔数）
    assert sign_tool.FORBIDDEN_SUFFIXES == reference.FORBIDDEN_SUFFIXES
    assert tuple(sign_tool.EXECUTABLE_MAGICS) == tuple(reference.EXECUTABLE_MAGICS)
    # 判据本身必须真的能命中（不是空表）
    probe = tmp_path / "probe.bin"
    probe.write_bytes(b"\x7fELF\x02\x01\x01\x00")
    assert reference.executable_kind(probe) is not None
    assert pack_mod.executable_kind(probe) is not None
    assert sign_tool.executable_kind(probe) is not None
    # 写侧判据的**独立**负例：shebang 内容 + 合法后缀名 ⇒ 只有魔数判据能拦下
    shebang = tmp_path / "notes.txt"
    shebang.write_bytes(b"#!/bin/sh\necho nope\n")
    assert shebang.suffix not in sign_tool.FORBIDDEN_SUFFIXES
    assert sign_tool.executable_kind(shebang) == "shebang 脚本"
    assert reference.executable_kind(shebang) == "shebang 脚本"
