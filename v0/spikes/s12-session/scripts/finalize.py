#!/usr/bin/env python3
"""收尾三件套：追加 03 的 M3 段 + 生成 V0_M3.sha256 + 追加改动面声明的修订记录。

用法：python3 spikes/s12-session/scripts/finalize.py <ws>
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

M3_SECTION = """

================================================================================
M3 段（REQ-20260921-005-deephealing-v0-m3 · artisan R1）
================================================================================
开工快照：repo /Users/wooyinq/personal/deep-healing = develop @ 98c781f4040d9b17757d67ba8e76fed1b95bfa12
          git status --porcelain | wc -l = 0；无并发写者（.task-raven-prereview.pid 已退出）
写集：<ws>/**（02_source/** + spikes/s12-session/** + spikes/s13-render/** + 根级 03/06/V0_M3.sha256）
      + ~/.hermes/team-tasks/** + <ws>/.artisan.progress.json

--------------------------------------------------------------------------------
逐 AC 判定（命令 + workdir + exit + 证据 + 负例自证读数）
--------------------------------------------------------------------------------
AC-M3-1   PASS
  命令：cd <ws>/02_source && bash verify_specs.sh --quiet
  实测：verify_specs: OK (125 checks passed, 0 skipped)   exit=0
  基线：cd <ws>/02_source/v0_skeleton/kernel && python3 -m deephealing_kernel run \\
        --pack districts/xingfu-xiaoqu --seed 20260921 --events /tmp/m3baseline/e.jsonl --snapshot-every 50
        实测 chain_tail=baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786
             event_count=925 / ticks=300 / 6 checkpoints
             checkpoints/000300.json state_hash=9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f
        exit=0（逐位不变）
  manifest：147 行 vs 盘上 148 文件（差 1 = manifest.txt 自身，自排除为既有约定）；缺失/幻影/重复 = 0/0/0
  AC-M3-1b（D-12）：差集 37 条 vs 声明 42 条 ⇒ **部分 FAIL**（5 条声明项本轮未实现：registry.py /
        test_calibrate_latency.py / calibrate_latency.py / pack_sign.py / verify_pack.py）。
        差集里未声明的行 = 0。接受该红，处置见 06 §4.1 与 §7，**不事后删除声明行**。
  AC-M3-1c（P-1）：run --help 默认值已改为引用 tick.DEFAULT_PLAN_TICKS；
        `= 300` 赋值全树恰好 1 处（tick.py:58）；不传 --ticks 真跑 300 tick / 6 检查点  exit=0
  AC-M3-1d：pack#1/pack#2 各自 `kernel validate` exit=0；verify_specs.sh §7b 已含 pack#2 两道调用
        负例 N-6（删 pack#2 worldview.json）⇒ verify_specs exit=1 **红** ✓
  AC-M3-1e：/usr/bin/find 02_source \\( -name node_modules -o -name dist -o -name .build \\) | wc -l = 0
        两次 npm run build 后 .build/web/assets 只有一套哈希产物
        负例 N-7（造 web/dist/x.js）⇒ verify_specs exit=1 **红** ✓

AC-M3-2   PASS
  命令：cd <ws>/02_source/v0_skeleton/session && npm test
  实测：9 passed / 0 failed / 0 skipped  exit=0
        4 条 AC 命名用例逐字存在且真跑（observe 拒写 / tick 边界 / 限流冷却 / 预算耗尽降级）
  内核侧：cd kernel && python3 -m pytest tests/test_observe_mode_readonly.py -q -p no:cacheprovider
        4 passed  exit=0（桩已全部变成真断言）
  事件流：spikes/s12-session/runtime/logs/kernel-events.jsonl
        grep -c intent.rejected = 3（reason_code=E_MODE_READONLY）；intent.applied = 2；task.state_changed = 2
  负例：N-1（会话层 observe 静默接受）⇒ npm test exit=1 **红** ✓
        N-2（内核 submit_intent 静默接受）⇒ pytest exit=1 **红** ✓

AC-M3-3   GAP（预算耗尽，真浏览器交互验收未执行）
  已做：cd web && npm run build ⇒ exit=0；node --test test/render-client.test.ts ⇒ 4 passed 0 skipped exit=0
  未做：真浏览器打开 + 桌面/≥390px 两档 + 真交互 + reload 回读 + 截图 + console 输出
  替代证据（**不构成替代判据**）：spikes/s12-session/run-session.mjs 已实现 HTTP+WS+静态服务三合一

AC-M3-4   GAP（半）：node web/scripts/scene_assert.mjs ⇒ scene_assert: PASS=15 FAIL=0 exit=0
  观察模式无写入口：panel.ts::listWriteControls() 已实现（选择器枚举），**未在真浏览器执行**
  负例：N-10（深层态换坐标）⇒ exit=1 **红** ✓；N-11（深层态饱和调高）⇒ exit=1 **红** ✓

AC-M3-5   PASS
  命令：cd kernel && python3 -m pytest tests/test_task_adaptation.py -q -p no:cacheprovider
  实测：6 passed  exit=0
  真跑：事件流里 task.state_changed 的 payload = {task_id, from_state=dormant, to_state=offered,
        rule_id=rule-001-warmth, shift_index=1, caused_by=p8-part, decision=shift, impact_cost=3.0}
  防刷（D-14 机器判据）：同目标连续两次 delegate_instruction ⇒ 审计流水 [shift, guard_no_op]，
        第二次**不产生** task.state_changed
  max_shifts 上限：数据驱动合成场景 ⇒ 第三次命中 decision=max_shifts_reached，迁移次数恰好 2
  负例：N-3（max_shifts 改成 999）⇒ pytest exit=1 **红** ✓
  无 intent 基线：test_default_run_without_intents_is_bit_identical ⇒ 逐位不变  ✓

AC-M3-6   PASS
  300 tick 基线逐位一致（见 AC-M3-1 的 state_hash / chain_tail / 检查点集合）
  会话层两遍同序列：spikes/s12-session/logs/p8-zero-residue.json（桥运行产物）

AC-M3-7   PASS
  git rev-parse --abbrev-ref HEAD ⇒ develop；git status --porcelain | wc -l ⇒ 0
  shasum -a 256 SEED.sha256 ⇒ 34fa7f6d252bc4bf966c8dbc4d639a1f08788ed71b9cfa04a0896ca7ba8f7676（未变）

AC-M3-8   ①②⑤ PASS；③ 数值 PASS / 真浏览器 GAP；④ PASS
  ① 两个 pack 各带 worldview.json 且过 worldview.schema.json（jsonschema 4.26.0）；
     pack.entrypoints.worldview 登记 + 进 required；district.pack.spec.md §7/§8；verify_specs 仍 OK/0 skipped
     负例 N-8（删 tone.underneath）⇒ schema 校验 exit=1 **红** ✓
  ② 10/10 NPC 具备 narrative_hooks + healing_face + hidden_face
     负例 N-9（删某 NPC 的 hidden_face）⇒ verify_specs exit=1 **红** ✓
  ③ 两态共用几何：entities=12 / vertices=288 / 实体 id 集合与坐标逐项相同（scene_assert 绿）
  ④ two_reads_share_geometry + underneath_does_not_raise_saturation 真跑通过
  ⑤ anom-01 表层读法/深层读法两段齐备，reveal_at_tick=55
  IP 边界：关键词扫描命中 1 文件 = worldview.schema.json 的 $comment（**自命中**，白名单化）；
     命中能力探针 /tmp/m3-ip-probe.txt ⇒ grep 命中 1（有命中能力）；
     xingfu-xiaoqu-north 在 world.ts/main.ts 命中 0（深层态不是第二个 pack/第二张地图）

--------------------------------------------------------------------------------
P-8（O-M2-1）零残渣 —— 逐字节
--------------------------------------------------------------------------------
命令：cd <ws> && node spikes/s12-session/zero-residue.mjs      exit=0
判据①：02_source/** 全量 sha256 清单跑前/跑后逐字节相同
        前 spikes/s12-session/logs/m3-source-manifest-before.txt（148 文件）
        后 spikes/s12-session/logs/m3-source-manifest-after.txt（148 文件）
        changed=[] added=[] removed=[] ⇒ byte_identical=true
        排除集逐条列明：__pycache__ / *.pyc / .pytest_cache / .DS_Store / node_modules / .venv / dist / attic-*
判据②：deephealing_kernel.__file__ = …/spikes/s12-session/runtime/02_source/v0_skeleton/kernel/deephealing_kernel/__init__.py
        ⇒ kernel_inside_copy=true（位于副本路径下，不是交付树）
负例：N-4（隔离副本改 1 字节）⇒ 清单比对**红** ✓；N-5（退回 sys.path.insert 交付树）**未执行**（预算耗尽，GAP）
architect 侧清理登记：02_source 下 14 个 __pycache__/*.pyc（153→139 文件）由 architect 删除
        （removed_files=14 removed_dirs=3）；属解释器副作用，被所有门禁排除，**在此声明**

--------------------------------------------------------------------------------
负例自证（D-13 隔离执行）总读数
--------------------------------------------------------------------------------
命令：cd <ws> && python3 spikes/s12-session/negctl.py .      exit=0
副本根：/tmp/m3-negctl/**（整树副本；**未**改 02_source 再改回来）
交付面 sha 跑前 == 跑后 ⇒ delivery_face_unchanged=true
10 条负例全部 turned_red=true：N-1 N-2 N-3 N-4 N-6 N-7 N-8 N-9 N-10 N-11 N-12
汇总：spikes/s12-session/logs/negctl-summary.json；逐条日志 spikes/s12-session/logs/negctl-*.log

--------------------------------------------------------------------------------
内核全量套件
--------------------------------------------------------------------------------
命令：cd <ws>/02_source/v0_skeleton/kernel && python3 -m pytest tests/ -q -p no:cacheprovider
读数：spikes/s12-session/logs/m3-kernel-pytest.txt（长套件；未在 7200s 内等到终值 ⇒ **不得标 PASS**）

--------------------------------------------------------------------------------
结论
--------------------------------------------------------------------------------
PASS：AC-M3-1（含 1c/1d/1e）、AC-M3-2、AC-M3-5、AC-M3-6、AC-M3-7、AC-M3-8①②④⑤
FAIL：AC-M3-1b（差集 vs 声明的双向比对，5 条声明项未实现 —— 如实报红）
GAP ：AC-M3-3（真浏览器交互）、AC-M3-4 半（真浏览器无写入口枚举）、AC-M3-8③（真浏览器两态截图）、
      P-9 / R-M2-1 / R-M2-3 / R-M2-4（预算耗尽，处方已定，归属 M4）、N-5、内核全量套件终值
"""

AMENDMENT = """

--------------------------------------------------------------------------------
SECTION E — POST-HOC AMENDMENT (written AFTER coding; disclosed as post-hoc)
--------------------------------------------------------------------------------
Execution result: 37 of the 42 SECTION A lines actually changed; the 5 that did NOT change are
  the carry-over items that were NOT implemented this round (budget exhausted):
    registry.py, kernel/tests/test_calibrate_latency.py, kernel/tools/calibrate_latency.py,
    tools/pack_sign.py, tools/verify_pack.py
This amendment is recorded for transparency ONLY. The declaration is NOT retro-edited to match
the diff (that would be the circular "generate the declaration from shasum -c" move forbidden by
3A-M6). The bidirectional criterion therefore reports: declared-not-in-diff = 5 (RED, accepted),
diff-not-declared = 0. Verdict: AC-M3-1b = FAIL(partial). See 06_v0_m3_self_test.md §4.1.
"""


def collect(workspace: Path) -> list[tuple[str, str]]:
    roots = ["02_source", "spikes/s12-session", "spikes/s13-render"]
    files = ["03_artisan_self_test.log", "06_v0_m3_self_test.md"]
    # `V0_M3.sha256` **自排除**（无法自证自身哈希；与 `manifest.txt` 的自排除同一约定，显式声明）
    entries: list[tuple[str, str]] = []
    for root in roots:
        base = workspace / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(workspace).as_posix()
            if any(part in ("__pycache__", ".pytest_cache", "node_modules", ".build", "dist") for part in path.parts):
                continue
            if path.suffix == ".pyc":
                continue
            if rel.startswith("spikes/s12-session/runtime/"):
                continue  # 运行期副本（生成物，非交付面）
            entries.append((rel, hashlib.sha256(path.read_bytes()).hexdigest()))
    for name in files:
        path = workspace / name
        if path.is_file():
            entries.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))
    return sorted(entries)


def main(argv: list[str]) -> int:
    workspace = Path(argv[1]).resolve()

    log = workspace / "03_artisan_self_test.log"
    text = log.read_text(encoding="utf-8")
    if "M3 段（REQ-20260921-005-deephealing-v0-m3" not in text:
        log.write_text(text + M3_SECTION, encoding="utf-8")
        print("03: M3 section appended")
    else:
        print("03: M3 section already present")

    change_face = workspace / "spikes/s12-session/m3-change-face.txt"
    text = change_face.read_text(encoding="utf-8")
    if "SECTION E" not in text:
        change_face.write_text(text + AMENDMENT, encoding="utf-8")
        print("change-face: amendment appended")

    entries = collect(workspace)
    lines = ["# V0_M3.sha256 — M3 冻结面自校验（采集面与排除项**显式声明**）",
             "#",
             "# 采集面：02_source/**（除生成残渣与运行期副本）+ spikes/s12-session/** + spikes/s13-render/**",
             "#         + 根级 03_artisan_self_test.log / 06_v0_m3_self_test.md / V0_M3.sha256（自身）",
             "# 排除项：__pycache__ / *.pyc / .pytest_cache / .DS_Store / node_modules / .venv / dist / .build / attic-*",
             "#         + spikes/s12-session/runtime/**（运行期副本，生成物）",
             "# 语义：本清单是 M3 **时点快照**（与 V0_M2.sha256 同口径）；M4 增删文件后 `shasum -c` 按设计会红，",
             "#       届时按「重取登记」规则（理由 + 变更清单 + 前后哈希）重取，**不得**静默改写。",
             f"# 条目数：{len(entries)}",
             ""]
    lines += [f"{digest}  {rel}" for rel, digest in entries]
    (workspace / "V0_M3.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"V0_M3.sha256: {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
