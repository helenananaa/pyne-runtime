# 首个稳定发行交付台账

本轮目标：交付独立、可嵌入、行为可信的 Pine 风格 Python 运行时。用户能够编写或
迁移代表性指标与策略，在批量、实时增量、重启恢复路径获得符合声明语义的结果，
并取得可安装、可升级、可诊断的发行包。直接运行 `.pine` 源码不在范围内。

本页是当前工作的验收台账，不替代 [当前能力状态](../reference/current_status.md)。
稳定是交付目标，不是当前候选已取得的认证；版本号在发行候选收口时确定。

## 支持承诺

- 支持 Python 3.11/3.12/3.13，Windows/Linux/macOS；实际发行提交必须取得相应
  源码检查和独立 wheel 安装证据。配置存在不等于平台已通过。
- 支持受信 Python 脚本、host-supplied OHLCV、公开包 API、已声明的 batch 与
  incremental 能力。具体成员以版本化 capability contract 为准，不承诺两模式全量等价。
- 覆盖指标组合、多周期请求、显式状态、绘图输出、持续策略交易、诊断与重启恢复。
  策略遵循已声明的 OHLCV 回放模型，不承诺真实逐笔成交或完整 Pine 兼容。
- host -> adapter -> runtime 的依赖方向不变。宿主提供数据、渲染、账户、交易连接、
  进程隔离和持久化；包提供通用契约及中立测试夹具。
- 兼容政策沿用独立 schema 版本与公开 API 规则。修复计算语义也必须披露结果变化；
  不兼容的已提交状态/回放变更更新 `INCREMENTAL_SEMANTICS_VERSION`，拒绝旧快照并
  提供从权威 OHLCV 重建路径，不改旧快照标签绕过检查。
- replay-v1 无法还原历史 preview 访问；依赖 intrabar 访问的 committed state 使用
  state-v2/local 快照。所有格式均不承诺恢复尚未提交的 preview。
- 高偏移滚动离散度保留稳定算术，与部分 Pine 捕获的差异必须明确；外部标准输出不
  得由本运行时重新生成，不通过放宽阈值掩盖差异。

## 代表性流程与退出标准

| ID | 用户流程 | 必须具备的证据 |
| --- | --- | --- |
| U1 | 编写/迁移 TA 组合指标 | 可运行脚本、输入身份、batch/incremental 对照、独立标准或明确差异、warmup/缺失值检查 |
| U2 | HTF/LTF 过滤指标 | 中立 provider、时间对齐、无未来输入污染、preview 隔离、已确认历史不变性、provider 失败后恢复 |
| U3 | 状态和绘图实时更新 | 重复 preview、提交、retention、对象事件与状态的独立预期，不能只比较自身两次输出 |
| U4 | 持续策略交易 | 持续 entry/exit、成本与账本独立算术、已声明 OCA 行为、恢复后继续成交 |
| U5 | 重启及版本升级 | 新进程 state-v2 恢复并继续、同语义版本延续、真实旧快照拒绝、从 OHLCV 重建的可执行示例 |
| U6 | 保存脚本前诊断并安装使用 | 真实迁移任务的失败/修正记录、Inspector 与实际执行一致、wheel 内 CLI/API/示例运行 |

现有 `tests/workloads/` 与完整脚本测试是起点。真实迁移脚本必须说明来源及使用权限，
输入片段必须保留身份；合成数据及第一方脚本可以验证契约，但不能代称真实用户采用。
新增 API 仅在上述流程被具体脚本阻塞时立项。

## 差距与状态（2026-09-09）

| 项目 | 当前证据 | 状态及剩余工作 |
| --- | --- | --- |
| A 支持范围 | 本页；现有 compatibility/schema 文档 | 已建立交付基线；最终检查包、文档、已知差异一致性 |
| B 代表性正确性 | `test_semantic_workloads.py`，外部 TA/OCA 捕获与快照测试 | 部分完成；按 U1–U6 核对逐项覆盖，补真实迁移与输入证据，不能以 58 个捕获代表全部流程 |
| C 长期容量 | 六负载 64/256/1024 年龄基线、请求索引配对报告 | 部分完成；尚缺长期 RSS、多会话混合负载、缓存预算达到/淘汰、频繁 preview 的容量包络 |
| D 迁移体验 | Inspector v2、cookbook、能力需求榜 | 部分完成；真实任务的诊断到修正到执行闭环待验证 |
| E 发行包 | 同一 wheel 的九平台安装配置已整合；Windows 3.12 本地安装通过 | 部分完成；选定提交的远端运行与完整门禁未验证 |

初始核对 HEAD `3e0c5fd`，工作区干净。2026-09-09 已执行状态生成检查和
`test_semantic_workloads.py`、`test_incremental_request_index.py`、
`test_capability_demand_backlog.py`：57 passed。这是定向证据，不是完整发行验收。
此前 1111 passed 为仓库历史验收记录，本轮不据此声称当前发行提交已过门禁。

支持范围切片提交 `187e01c`：文档入口与宿主指南检查 7 passed。其后同一运行时代码
的 TA 边界、trend/volume、OCA、滚动统计、snapshot semantics 和 portable snapshot
六个测试文件合计 132 passed（10.61s），本地日志
`build/stable-delivery/semantic-audit-check.log`。该补充检查未覆盖长期容量或真实迁移。

## 执行与证据规则

每个切片记录基线、修改范围、检查命令/退出码、原始证据位置与剩余问题。
Grok 修改任务使用独立工作树，有界轮数；维护者审核 diff、运行必要检查后才整合。
长测记录配置、脚本/数据/源码身份、环境、原始样本和失败，不把 tracemalloc 当作 RSS，
不把单机短窗口当作 SLA。先测稳定趋势与热点，再决定优化。

当前切片：安装包矩阵（`codex/stable-package-matrix`），只涉及发行验证与文档，
不修改运行时语义，已审核整合为 `e6fdead`；详见
[安装包矩阵验收](package_matrix_acceptance_zh.md)。

U5 补充切片：新进程恢复事件敏感状态、replay-v1 的明确数值差异，以及真实旧快照
拒绝后 OHLCV 重建/继续，已由 `tests/test_recovery_workflows.py` 验证。
连同 snapshot semantics 与文档入口检查合计 38 passed，Ruff 通过。重建测试初稿曾
误用 first-close EMA seed（2 failed）；核对现有外部捕获的三样本均值种子规则后
修正独立算术预期，未修改运行时或捕获。使用方法见
[Session Recovery](../tutorials/session_recovery.md)。

Grok 的 U1–U6 只读审计已完成，维护者复核后选择 U2 provider failure/confirmed
prefix 的直接验收作为下一切片，位于独立工作树 `codex/request-recovery-acceptance`。
长期容量与真实迁移流程仍待完成；不将候选缺口审计当作完整性证明。

本地修改、审核提交和验证已获授权；远端推送、合并、发布须另有明确授权。
所有 U1–U6、容量证据、迁移/重建说明、选定发行提交门禁都完成，才可判定可交付。
若仅剩发布授权或必需外部输入，列明该依赖，不以无限扩充功能延长任务。
