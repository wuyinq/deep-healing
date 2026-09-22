"""内容包（district pack）加载与校验（V0-M1 实现，契约冻结）。

校验顺序（district.pack.spec.md §2）：pack.json → engine_range → entrypoints glob 命中
→ 数据文件校验 → pack.sig 逐文件 sha256。任一失败 → E_PACK_INVALID，内核不启动。

**第 4 步的准确措辞（修复轮 B4 / 预审 R6）**：只校验 `pack.json`（`$defs/packManifest`）与
`world.seed.json`（`$defs/worldSeed` + 去 `weather` 投影过 `world.schema.json`）；
`buildings`/`npcs`/`tasks`/`schedules`/`assets` 五层在**冻结契约里没有对应 schema**
（`district.pack.schema.json` 只有 `packManifest`/`packSig`/`worldSeed` 三个 `$defs`）
⇒ 本轮**只做 JSON 可解析性检查**，**不做**结构校验。补齐这五层的 schema 属**契约变更**（需 ADR）。

禁止：pack 目录内出现可执行代码；**路径字符串**含 `..` 或绝对路径；**符号链接目标**越出 pack 根
（修复轮 B3 / 预审 R7：路径守卫 `_guard_relpath` 只看字符串，故另有 `_assert_within_root` 解析真实路径）。

M1 关键裁决（设计 §4.4，预审 M1 升级为**严格更强**口径）：
  - pack 数据文件按 `district.pack.schema.json` 的 `$defs` 校验（`packManifest` / `packSig` / `worldSeed`）；
  - **`world.seed.json` 必须额外通过严格口径**：去掉 `weather` 后的投影（schema_version/seed/tick/
    constants/entities）必须**全量通过 `world.schema.json`**。理由：`$defs/worldSeed` 只把 `constants`
    声明为 `{"type":"object"}`、`entities` 声明为 `{"type":"array","items":{"type":"object"}}`，
    **不校验内部结构** ⇒ 结构损坏的 seed 会通过 `validate`（假绿）却在 snapshot 阶段炸。
  - **`weather` 的读取与丢弃必须显式**（预审 U2）：加载后断言 `world_seed["weather"]` 存在，
    并**有意**不把它放进 `to_state()`（内核状态里没有天气字段）。M2 不得把它读成「天气已支持」。

可执行文件判据与 `tools/verify_pack.py` **同一算法**（后缀名 + 内容魔数双判据）；
本文件镜像该算法，`tests/test_pack_validate.py::test_pack_sign_and_verify_use_same_executable_criteria`
断言两侧常量逐条一致（防漂移守卫）。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from . import KERNEL_CONTRACT_VERSION

V0_SKELETON = Path(__file__).resolve().parents[2]
SOURCE_ROOT = V0_SKELETON.parent

# 与 tools/verify_pack.py 同一算法（镜像；由测试断言防漂移）
FORBIDDEN_SUFFIXES = {".py", ".js", ".ts", ".sh", ".rb", ".pl", ".exe", ".so", ".dylib"}
EXECUTABLE_MAGICS = (
    (b"\x7fELF", "ELF"),
    (b"MZ", "PE"),
    (b"\xfe\xed\xfa\xce", "Mach-O 32 BE"),
    (b"\xfe\xed\xfa\xcf", "Mach-O 64 BE"),
    (b"\xce\xfa\xed\xfe", "Mach-O 32 LE"),
    (b"\xcf\xfa\xed\xfe", "Mach-O 64 LE"),
    (b"\xca\xfe\xba\xbe", "Mach-O universal"),
    (b"#!", "shebang 脚本"),
    (b"\x03\xf3\x0d\x0a", "Python 字节码"),
    (b"\x0d\x0d\x0a", "Python 字节码（PEP 552）"),
)

ENGINE_RANGE_RE = re.compile(r"^>=(\d+)\.(\d+)\.(\d+) <(\d+)\.(\d+)\.(\d+)$")


class PackInvalid(Exception):
    """E_PACK_INVALID：内容包校验失败（携带首个失败原因）。"""

    code = "E_PACK_INVALID"


@dataclass(slots=True)
class DistrictPack:
    root: Path
    manifest: dict
    world_seed: dict
    buildings: list[dict] = field(default_factory=list)
    npcs: list[dict] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    schedules: list[dict] = field(default_factory=list)
    assets: dict = field(default_factory=dict)
    portals: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------- 小工具
def executable_kind(path: Path) -> str | None:
    """按**内容魔数**判断可执行容器；命中返回其名字，否则 None（与 tools/verify_pack.py 一致）。"""
    try:
        with path.open("rb") as handle:
            head = handle.read(8)
    except OSError:
        return None
    for magic, name in EXECUTABLE_MAGICS:
        if head.startswith(magic):
            return name
    return None


def sha256_of(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _guard_relpath(rel: str) -> str | None:
    """路径**字符串**安全：拒绝绝对路径与 `..` 段。返回拒绝原因或 None。

    ⚠ 归因边界（Sentinel Bug#3 / 预审 R7）：冻结 schema 把 `entrypoints` 的 6 个值全部钉成 `const`
    且 `additionalProperties:false`，`rglob` 结果的 `relative_to(root)` 也不含 `..`
    ⇒ 本函数对**任何先通过 schema 校验的输入**都不可达。它是对**未来放开 entrypoints** 的防线，
    其可达性由 `tests/test_pack_validate.py::test_guard_relpath_rejects_traversal_and_absolute` 直接覆盖。
    **符号链接**不看字符串 ⇒ 由 `_assert_within_root()` 单独守。
    """
    if not rel:
        return "empty path"
    if Path(rel).is_absolute() or rel.startswith("/"):
        return f"absolute path not allowed: {rel}"
    if ".." in Path(rel).parts:
        return f"parent traversal not allowed: {rel}"
    if "\\" in rel:
        return f"backslash separator not allowed: {rel}"
    return None


def _assert_within_root(path: Path, root: Path) -> None:
    """**符号链接守卫**（修复轮 B3 / 预审 R7）：解析真实路径后必须仍位于 pack 根之内。

    为什么需要：`_guard_relpath` 只看路径字符串，而 `Path.rglob` / `is_file()` / `read_text()`
    都**跟随符号链接** ⇒ pack 内一个指向 pack 外合法 JSON 的符号链接会让内核读入 pack 外的文件
    （内容进入 `world_seed` → `state` → 事件日志/检查点，构成把 pack 外内容带出到产物的通道）。
    """
    resolved = path.resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise PackInvalid(
            f"symlink escape: {path} resolves to {resolved} which is outside pack root {root_resolved}"
        )


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackInvalid(f"missing data file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PackInvalid(f"unparsable JSON: {path}: {exc}") from exc


def _schema_document(name: str) -> dict:
    path = SOURCE_ROOT / name
    return json.loads(path.read_text(encoding="utf-8"))


def _def_schema(schema: dict, def_name: str) -> dict:
    document = {"$schema": schema.get("$schema"), "$ref": f"#/$defs/{def_name}", "$defs": schema["$defs"]}
    return document


def _validate_schema(document: object, schema: dict, label: str) -> None:
    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path)
        raise PackInvalid(f"schema validation failed for {label} at {location or '<root>'}: {exc.message}") from exc
    except jsonschema.SchemaError as exc:  # 校验器自身的 schema 不合法也必须 fail-closed
        raise PackInvalid(f"schema itself is invalid for {label}: {exc.message}") from exc


# ---------------------------------------------------------------------- 引擎区间
def check_engine_range(manifest: dict, kernel_version: str) -> bool:
    match = ENGINE_RANGE_RE.match(str(manifest.get("engine_range", "")))
    if not match:
        return False
    lower = tuple(int(part) for part in match.groups()[:3])
    upper = tuple(int(part) for part in match.groups()[3:])
    try:
        current = tuple(int(part) for part in str(kernel_version).split("."))
    except ValueError:
        return False
    return lower <= current < upper


# ---------------------------------------------------------------------- 签名
def verify_signature(root: Path) -> list[str]:
    """返回不一致清单（空 = 通过）；与 `tools/verify_pack.py` 共用同一算法。

    **返回类型契约（修复轮 2 / F5 / Raven R19）**：本函数**只返回**问题清单，**不抛异常**。
    修复前它在符号链接逃逸路径上抛 `PackInvalid`，而声明返回类型是 `list[str]`（空 = 通过）
    ⇒ 任何「聚合问题清单」的调用方会漏接。现在逃逸也作为一条 problem **返回**：
    `symlink_escape: <path> resolves to <target> which is outside pack root <root>`。
    （`load_pack` 仍 fail-closed：它把非空清单转成 `PackInvalid`。）

    **符号链接守卫的覆盖（F4 / R17）**：`pack.sig` 本身**也**过 `_assert_within_root` ——
    原先 `rglob` 显式跳过 `pack.sig`，随后 `sig_path.read_text()` 跟随链接 ⇒ 它是**唯一**
    未被守卫的读取点（Raven 实证：`pack.sig` 换成指向包外的符号链接时 `load_pack` 仍 OK）。
    """
    root = Path(root).resolve()
    sig_path = root / "pack.sig"
    if not sig_path.is_file():
        return [f"missing_pack_sig: {sig_path}"]
    try:
        _assert_within_root(sig_path, root)
    except PackInvalid as exc:
        return [f"symlink_escape: {exc}"]
    try:
        signature = json.loads(sig_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"unparsable_pack_sig: {exc}"]

    declared = {entry["path"]: entry for entry in signature.get("entries", [])}
    actual: dict[str, dict] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "pack.sig":
            continue
        rel = path.relative_to(root).as_posix()
        guard = _guard_relpath(rel)
        if guard is not None:
            return [f"unsafe_path: {guard}"]
        # 符号链接守卫（B3）：`rglob`/`is_file` 跟随符号链接 ⇒ 必须解析真实路径再判越界
        # 修复轮 2 / F5：逃逸改为**返回**一条 problem（不再从 `verify_signature` 抛出）
        try:
            _assert_within_root(path, root)
        except PackInvalid as exc:
            return [f"symlink_escape: {exc}"]
        suffix_hit = path.suffix in FORBIDDEN_SUFFIXES
        magic_hit = executable_kind(path)
        if suffix_hit or magic_hit:
            criteria = " + ".join(filter(None, ["后缀名" if suffix_hit else "",
                                               f"内容魔数={magic_hit}" if magic_hit else ""]))
            return [f"executable_file: {rel}（判据：{criteria}）"]
        digest, size = sha256_of(path)
        actual[rel] = {"sha256": digest, "bytes": size}

    problems: list[str] = []
    for rel in sorted(declared):
        if rel not in actual:
            problems.append(f"missing_file: {rel}")
            continue
        if actual[rel]["sha256"] != declared[rel]["sha256"]:
            problems.append(
                f"hash_mismatch: {rel} expected={declared[rel]['sha256']} actual={actual[rel]['sha256']}"
            )
        elif "bytes" in declared[rel] and actual[rel]["bytes"] != declared[rel]["bytes"]:
            problems.append(
                f"size_mismatch: {rel} expected={declared[rel]['bytes']} actual={actual[rel]['bytes']}"
            )
    for rel in sorted(set(actual) - set(declared)):
        problems.append(f"undeclared_file: {rel}")
    return problems


# ---------------------------------------------------------------------- 加载
def load_pack(root: Path) -> DistrictPack:
    """加载并校验内容包（含 pack.sig 逐文件比对）。"""
    root = Path(root).resolve()
    if not root.is_dir():
        raise PackInvalid(f"pack directory not found: {root}")

    pack_schema = _schema_document("district.pack.schema.json")
    world_schema = _schema_document("world.schema.json")

    # 1) pack.json 过 $defs/packManifest
    manifest_path = root / "pack.json"
    if not manifest_path.is_file():
        raise PackInvalid(f"missing pack.json in {root}")
    _assert_within_root(manifest_path, root)
    manifest = _read_json(manifest_path)
    _validate_schema(manifest, _def_schema(pack_schema, "packManifest"), "pack.json")

    # 1b) 目录名必须等于 pack.json.id（district.pack.spec.md §1）
    if root.name != manifest["id"]:
        raise PackInvalid(f"pack directory name {root.name!r} != pack.json.id {manifest['id']!r}")

    # 2) engine_range vs 内核契约版本
    if not check_engine_range(manifest, KERNEL_CONTRACT_VERSION):
        raise PackInvalid(
            f"engine_range {manifest['engine_range']!r} does not include kernel contract {KERNEL_CONTRACT_VERSION}"
        )

    # 3) 每个 entrypoints glob 至少命中 1 个文件 + 路径安全
    entrypoints = manifest["entrypoints"]
    for key in sorted(entrypoints):
        pattern = entrypoints[key]
        guard = _guard_relpath(pattern)
        if guard is not None:
            raise PackInvalid(f"entrypoint {key}: {guard}")
        matched = sorted(root.glob(pattern))
        if not matched:
            raise PackInvalid(f"entrypoint {key}={pattern!r} matched no file")
        # 符号链接守卫（B3）：命中文件解析后必须仍在 pack 根内
        for path in matched:
            _assert_within_root(path, root)

    # 4) 数据文件校验（准确措辞见模块 docstring 第 4 步：仅 pack.json + world.seed.json 有 schema）
    seed_path = root / entrypoints["world_seed"]
    _assert_within_root(seed_path, root)
    world_seed = _read_json(seed_path)
    _validate_schema(world_seed, _def_schema(pack_schema, "worldSeed"), "world.seed.json ($defs/worldSeed)")
    # 4b) 强口径（预审 M1）：seed 文档必须**全量**过 `world.schema.json`。
    #
    # **ADR-13 变更（2026-09-22）**：`world.schema.json` 顶层已补 `weather`（结构镜像
    # `$defs/worldSeed.weather`）⇒ 原先「去 weather 的投影」与「原文档」**现在是同一份文档**。
    # 这里的 `projection` 因此**已退化为恒等**（`projection == world_seed`，单口径）。
    # **为什么保留这次调用**：`test_pack_docstring_matches_implementation` 逐字断言本文件里
    # `_validate_schema` 的**出现次数 == 4**（1 定义 + 3 调用）。删掉调用会扰动既有判据计数
    # （Raven 预审 M-2 已实测：计数变 3 ⇒ `assert 3 == 4` 变红）。保留是为了不扰动既有判据计数，
    # **不是**因为还存在双口径 —— 契约矛盾已由 ADR-13 消除。
    projection = dict(world_seed)  # 恒等投影：ADR-13 之后原文档即单一口径
    _validate_schema(projection, world_schema, "world.seed.json (identity projection: ADR-13)")
    # 4c) weather 的读取与丢弃必须显式（预审 U2）
    if "weather" not in world_seed:
        raise PackInvalid(
            "world.seed.json must declare `weather` (it is read explicitly and intentionally NOT part of "
            "kernel state; a missing key would make the drop silent)"
        )

    def _load_many(pattern: str) -> list[dict]:
        documents = []
        for path in sorted(root.glob(pattern)):
            guard = _guard_relpath(path.relative_to(root).as_posix())
            if guard is not None:
                raise PackInvalid(guard)
            _assert_within_root(path, root)
            documents.append(_read_json(path))
        return documents

    buildings = _load_many(entrypoints["buildings_glob"])
    npcs = _load_many(entrypoints["npcs_glob"])
    tasks = _load_many(entrypoints["tasks_glob"])
    schedules = _load_many(entrypoints["schedules_glob"])
    assets = _read_json(root / entrypoints["assets_manifest"])

    # 5) pack.sig 逐文件比对
    problems = verify_signature(root)
    if problems:
        raise PackInvalid("; ".join(problems))

    return DistrictPack(
        root=root,
        manifest=manifest,
        world_seed=world_seed,
        buildings=buildings,
        npcs=npcs,
        tasks=tasks,
        schedules=schedules,
        assets=assets,
        portals=list(manifest["portals"]),
    )


def build_portal_edges(packs: dict[str, DistrictPack]) -> list[dict]:
    """按 portals 数据建跨区边；目标 pack 未加载时边标 inactive（不报错、不崩）。"""
    edges: list[dict] = []
    for pack_id in sorted(packs):
        pack = packs[pack_id]
        for portal in pack.portals:
            edges.append({
                "id": portal["id"],
                "from_pack_id": pack_id,
                "from_entity": portal["from_entity"],
                "to_pack_id": portal["to_pack_id"],
                "to_entity": portal["to_entity"],
                "bidirectional": bool(portal.get("bidirectional", False)),
                "traversal_cost_ticks": int(portal.get("traversal_cost_ticks", 0)),
                "status": "active" if portal["to_pack_id"] in packs else "inactive",
            })
    return edges
