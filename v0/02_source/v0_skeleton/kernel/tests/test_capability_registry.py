"""RED 用例：能力注册表数据驱动发现 / provider 切换 / 新增能力不改内核代码（AC-13）。

运行（实现完成后）：
    cd <workspace>/02_source/v0_skeleton/kernel && python3 -m pytest tests/test_capability_registry.py -q
"""

from __future__ import annotations

import pytest


def test_registry_discovers_capability_files(tmp_path):
    """丢入一个 *.capability.json 即被发现（无需改任何源码）。"""
    pytest.skip("V0 skeleton: pending kernel implementation (see 08_v0_plan.md)")


def test_new_capability_requires_no_kernel_source_change(tmp_path):
    """新增 relation.infer@1.0.0 后，kernel/ 源码哈希必须不变（AC-13 判据）。"""
    pytest.skip("V0 skeleton: pending kernel implementation (see 08_v0_plan.md)")


def test_provider_switch_remote_to_cassette_to_rule(tmp_path):
    """remote_api → cassette_replay → deterministic_rule 三类均产出通过 output_schema 的结果。"""
    pytest.skip("V0 skeleton: pending kernel implementation (see 08_v0_plan.md)")


def test_invalid_capability_file_is_rejected(tmp_path):
    """非法能力文件（缺 safety / secrets_in_context=true）必须被拒绝加载且不静默。"""
    pytest.skip("V0 skeleton: pending kernel implementation (see 08_v0_plan.md)")


def test_cassette_miss_is_fail_closed(tmp_path):
    """回放模式下 cassette miss 必须抛 E_CASSETTE_MISS，不得静默切远端。"""
    pytest.skip("V0 skeleton: pending kernel implementation (see 08_v0_plan.md)")


def test_invalid_model_output_falls_back(tmp_path):
    """模型输出不合 schema → fallback 链降级且落 capability.fallback 事件。"""
    pytest.skip("V0 skeleton: pending kernel implementation (see 08_v0_plan.md)")
