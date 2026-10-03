# WMA/HMA 缺失窗口官方对齐

日期：2026-09-30。第一轮开发工作区的计算语义为 6；已发布 0.4.0 保持语义 5。

通过 Chrome 在已登录的 TradingView 图表运行两份 Pine v6 探针。输入由
`bar_index` 生成，覆盖首段缺失、孤立缺失、连续缺失、WMA 周期 1/3/5、
HMA 周期 5/7/9 与嵌套 WMA。图表为 COINBASE:BTCUSD 1D；计算不依赖行情。
原始 Pine Logs、源码哈希、日志哈希、采集时间及解析值保存在
`tests/workloads/weighted_boundaries.*` 和 `wma_gap_confirmation.*`。

第一份探针有 32 行、12 个计算输出。修复前批量对照有 35 处差异：WMA holes
7 处、HMA holes 16 处、Nested WMA 12 处。正常输入下的 HMA 周期取整、
SWMA、ALMA、DEV 与空输入对照没有差异。

第二份 32 行探针用每根 bar 无条件计算的 `fixnan` 加 WMA 公式区分规则：

- 预热必须累计足够的真实非缺失输入；填补缺失不能提前结束预热。
- 缺失 bar 输出 `na`，但内部加权 bar 窗口沿用最近输入推进。
- 下一根有效 bar 的窗口包含缺失期间沿用的输入；简单跳过缺失 bar 也不正确。
- 嵌套 WMA 的每层独立应用这套规则。

批量实现保留原有线性复杂度的加权核、非有限值处理与数值稳定路径；
增量实现保存最近输入和预热观察计数。HMA 通过其 WMA 组合自动获得修正。
没有新增宿主策略、市场数据依赖或 Pine 源码执行功能。

`test_weighted_boundaries_external.py` 校验源码/日志哈希、原始日志与 JSON
一致性、完整行列，比较两种执行模式的多个历史前缀，并验证预览不污染提交
状态以及 local/replay/state 恢复后的完整续算。另用独立窗口算术验证不同
周期、末段连续缺失；已有高偏移和非有限值测试仍保留独立计算依据。

状态格式不变，计算语义由 5 升至 6。语义 5 的真实 replay/state 快照由
未修改的 `655fbd86eb7483befb911a35553fb9f8ce057036` 在独立进程生成，
记录于 `tests/golden/snapshot_semantics_v5/provenance.json`。
拒绝旧快照须发生在创建会话之前；兼容版本可以正常恢复续算。
升级须从调用方提供的权威 OHLCV 重建，禁止改版本号冒充兼容。

本证据属于 pytest workload 对照，不计入原有 58 个 capture-family 总数。
它没有证明任意 Pine 脚本兼容性或实时 tick 与 TradingView 一致。

## 本轮最终核验

本节记录第一轮语义 6 的候选验收。后续语义 7 修正与核验见
[极值窗口验收](extrema_boundaries_acceptance_zh.md)。

候选包版本为 `0.4.1rc1`，未发布；历史 `0.4.0` 发布记录保持不变。
在物理工作目录 `E:\Disk0Merged\H\program\pyne-runtime` 运行
`scripts/check.ps1`，整个命令退出码为 0：

- 全量 pytest：1,350 项通过。保留已有的大模块架构提示 warning。
- compileall、全仓 Ruff、生成状态检查、diff 空白检查通过。
- 性能和增量稳定性检查通过，WMA 保持线性窗口算法。
- 既有 TA 10 / Strategy 27 / Request 21 官方 capture 全部零差异。
- sdist、wheel 构建和 Twine 检查通过。
- 独立安装 wheel 的 9 个验收流程、55,075 个比较点通过，导入路径位于
  验收虚拟环境 `site-packages`，计算语义身份为 6。

另建离线验收虚拟环境安装同一 wheel，先断言导入来自其 `site-packages`，
再运行新增 WMA/oscillator 对照及快照语义测试：149 项全部通过。
完整证据覆盖六份官方探针、192 行；原始对照输出未作改写。
Stochastic 起点及 correlation 的保留差异见
[oscillator 验收](oscillator_boundaries_acceptance_zh.md)。

完整门禁开始前，仅展开三处文件中的旧单行语句以修复九项 Ruff 格式错误：
`external.py`、`historical.py`、`test_callback_arity_fastpath.py`。
这些调整没有改变行为。没有加入宿主集成或默认资源限制。
