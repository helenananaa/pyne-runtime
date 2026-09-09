# 首个稳定发行交付台账

本轮目标：交付独立、可嵌入、行为可信的 Pine 风格 Python 运行时。用户能够编写或
迁移代表性指标与策略，在批量、实时增量、重启恢复路径获得符合声明语义的结果，
并取得可安装、可升级、可诊断的发行包。直接运行 `.pine` 源码不在范围内。

本页是当前工作的验收台账，不替代 [当前能力状态](../reference/current_status.md)。
本轮目标版本为 **0.3.0**，目标仍是稳定、独立、可嵌入的正式发行包；当前处于本地
候选验收阶段。远端 CI 与发布尚未完成，不得据此声称已公开发行。稳定是有界兼容
契约，不是完整 Pine 实现声明。

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
| A 支持范围 | 本页；compatibility 中稳定 0.3 发行线承诺与 schema 政策 | 范围已冻结；最终检查包、文档、已知差异一致性 |
| B 代表性正确性 | 完整脚本、外部 TA/OCA、快照与真实 ADX/DI 迁移捕获 | 主要流程已有直接证据；最终选定提交仍需统一验收，不能以 58 个捕获代表全部流程 |
| C 长期容量 | 1/4/8 会话各 4096 根，266240 原始事件，48 个窗口与恢复检查 | 固定负载验收完成；证据已归档并独立复算，不扩张为任意脚本 SLA |
| D 迁移体验 | 真实 ADX/DI 初译失败、迁移提示、修正执行及 80 根外部对照 | 已完成本代表性案例；不声称所有语料可迁移 |
| E 发行包 | 本地 0.3.0 候选已准备；公开 published-version 仍为 0.2.0rc1 | 本地验收继续直接执行；远端 CI 需推送授权，发布需明确授权 |

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
prefix 的直接验收切片，来自独立工作树 `codex/request-recovery-acceptance`。
两类 request 的故障/恢复和旧绘图点保留共 4 项通过维护者复跑；详见
[请求恢复验收](request_recovery_acceptance_zh.md)。
整合后新测试、既有 incremental request 与完整脚本合计 55 passed（21.66s），
Ruff 通过；文档入口与发行文档检查 15 passed。以上不是最终发行完整门禁。
长期容量与真实迁移流程仍待完成；不将候选缺口审计当作完整性证明。

后续真实迁移：BeikabuOyaji ADX/DI，保留 MPL-2.0，80 根实际 BTCUSDT 15 分钟行情的
Chrome 捕获已落盘，迁移与恢复 18 项通过。另修复 Inspector 缺少迁移建议的问题，
保持启发式建议与能力阻塞分开；迁移/Inspector 合计 32 passed、Ruff 通过。详见
[ADX/DI 迁移验收](adx_migration_acceptance_zh.md)。上一段的真实迁移待办由此关闭。

容量工具来自 Grok 独立工作树，经维护者纠正“同一快照恢复两次充当续算对照”、额外
preview 预热及窗口原始数组保留问题后整合为 `5aca520`。5 项工具测试与 96 根冒烟
通过；长测使用独立干净测量提交 `87c06d9`，当前结果保存在容量工作树
`build/runtime-capacity/qualification*.json`。长测未结束，不将部分窗口升级为容量结论。

本地修改、审核提交和验证已获授权；远端推送、合并、发布须另有明确授权。
所有 U1–U6、容量证据、迁移/重建说明、选定发行提交门禁都完成，才可判定可交付。
若仅剩发布授权或必需外部输入，列明该依赖，不以无限扩充功能延长任务。

发行前补充验收：已安装 wheel 的五类迁移/恢复流程通过，5074 个比较点；包/文档
检查 27 passed。详见[已安装流程验收](installed_workflow_acceptance_zh.md)。
2026-09-09 通过 GitHub CLI 只读核对：公开版本仍只有 `v0.2.0rc1`，最新远端 main
CI 通过对应 `9ce0a4d`，不是本地候选。未推送、触发远端任务或发布。

同日对原 EMA/RSI Pine 捕获脚本作独立 Chrome 复核：18 行、15 列全部一致，
包含缺失位置。新证据位于 `evidence/ema_rsi_reverification_20260909.*`，原记录未改。

容量长测随后全部结束，1540 项适用检查通过；1/4/8 会话末窗口 RSS 为
45.98/48.47/51.77 MiB。独立审计重算全部 266240 事件及统计值，归档解包再审计通过。
详见[容量验收](capacity_acceptance_zh.md)。目前剩余主线为最终完整门禁、发行候选
制品和九平台远端资格；不再为保持运行而继续扩充 API 或重复该容量批次。

Linux 原生克隆验收发现 WMA/BLAS 增长失败及离线嵌套 venv 缺 NumPy；已完成定向
修复，保留原失败。归约末位变化使全局计算语义保守升级为 3，真实版本 2 快照
拒绝与版本 3 延续通过。详见[Linux 修复记录](linux_candidate_repairs_zh.md)。
当前唯一实现收口事项是合并后 Windows/Linux 完整复验及最终发行资格，原有
版本 2 通过记录不作为新语义的完整门禁结果。

本地 `0.3.0` 候选已在工作树准备：`project.version=0.3.0`，intended classifier
为 Production/Stable，`published-version` 仍为 `0.2.0rc1`。此前 `0.3.0rc2`
本地验收为历史记录，不替换、不升级为远端 CI 成功。剩余工作仍是完整门禁、
远端 CI 与发布授权；未推送、未打标签、未发布。

代码基线 `dbb8721` 已分别通过 Windows Python 3.12.7 和 Linux 原生 Python 3.12.13
完整门禁，各 1164 passed，包含性能/稳定性、捕获、构建、Twine 和语义 3 的已安装
流程。0.3.0 版本准备只涉及元数据、文档和相应发行契约测试，运行时代码未改。
版本/发行资产/状态检查 22 passed；候选制品独立安装与最终远端矩阵仍继续验收。
