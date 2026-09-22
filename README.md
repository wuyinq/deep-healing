# deep-healing

自我演进的赛博世界 —— 3D 世界沙盒，从「幸福小区」起步，人物可自主进化、自主交互；
人类可选**观察模式**（只读订阅）或**参与模式**（经权威端写入，影响任务迭代演进）。

## 目录

```
docs/            设计与契约（发布视图）
  architecture/    架构设计、开源选型矩阵、ADR、V0 计划、风险、验收记录
  specs/           18 份冻结契约（schema / spec）
v0/              V0 垂直切片的可验证交付单元（里程碑 M1：确定性内核）
  README.md        怎么验证、已知限制、溯源
```

## 快速验证

```bash
cd v0/02_source && bash verify_specs.sh --quiet          # 期望 OK (95 checks, 0 skipped)
cd v0/02_source/v0_skeleton/kernel && \
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider   # 期望 71 passed, 10 skipped
```

已知限制与注意事项见 `v0/README.md`（含「`verify` 必须带链外锚点」这条硬规矩）。

## 技术底盘

- 渲染：Web 前端（3D）；仿真内核：本地进程（Python 骨架，架构上预留 Rust 加速位）
- 认知：混合——LLM 只做高层意图 / 记忆反思 / 叙事；规则层（需求·效用·行为树）负责执行与物理
- 内核是**唯一权威写入点**：确定性 tick + 哈希链；异步结果跨 tick 边界直接丢弃，绝不回填
- 模型能力经 **API 作为原子能力**补充（能力注册表 + 四类 provider：远程 API / 本地模型 / 确定性规则 / 录制回放）
- 素材：AIGC **离线生产**、运行时零生成；资产一等公民（内容寻址哈希 + 版本 + 许可 + 生成来源）
