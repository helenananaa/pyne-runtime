# CMO / Stochastic 官方边界对照

日期：2026-09-30。第一轮开发候选为 0.4.1rc1，计算语义 6；未发布。
后续公共极值修正将语义升至 7，见[极值验收](extrema_boundaries_acceptance_zh.md)。

通过 Chrome 在 TradingView COINBASE:BTCUSD 1D 图表运行四份探针，每份
32 行合成输入。`oscillator_flat`、`oscillator_formula` 和
`stoch_transitions` 使用 Pine v6；另以 Pine v5 重跑相同 Stochastic
过渡输入。源码、原始 Pine Logs、哈希、采集信息和解析数值保存在
`tests/workloads` 对应文件中，不能由 Pyne 结果重写。

CMO 原生输出与独立的 `ta.change`、条件分支和 `math.sum` 公式逐行相同。
缺失动量分别进入上涨/下跌分支，各分支独立累计非缺失观察；不能将两个
窗口强制合并为完整成对动量。零分母输出缺失，不能制造零值。修正仅涉及
已有批量 CMO，没有宣称新增增量 CMO。

Stochastic 的 high/low 缺失会分别重置对应极值窗口。source 缺失、暂时没有
可计算的极值或区间宽度为零时，保留最近一次有效 Stochastic 输出；从未
有有效输出时保持缺失。覆盖单独 source/high/low 缺失、连续缺失、平坦
末段和先平坦后变化的输入。Pine v5 与 v6 的这份过渡输出逐行一致。
批量与增量实现均修正；同版本 local/replay/state 恢复和预览隔离已有回归。

两项差异明确保留：

- Pyne Stochastic 使用已有的短历史窗口启动。此次原生数据集起点探针
  在周期 3 的前两根 bar 输出缺失，Pyne 提前有值。对照只从第三根开始
  声明一致；平坦起点案例全程检查。单独测试明确断言前两根的差异。
  原有截取图表窗口的 58 个 capture-family 对照仍保持，不修改原始值。
- Pyne correlation 保持完整成对窗口、常数序列未定义和稳定 Pearson
  算法。此次原生缺失输入输出出现大于 1 的相关系数，常数输入原生为零。
  原始列保留为 reference-only，测试明确断言差异；不宣称这两列对齐。

`tests/test_oscillator_boundaries_external.py` 有 52 项测试，检查证据身份、
多个历史前缀、两种执行模式、恢复、预览隔离及上述保留边界。与 WMA 的
两份探针合计六份、192 行。这些证据属于 pytest workload，不混入既有
58 个 capture-family 的统计，也不证明实时 tick 或任意 Pine 脚本一致。

计算语义与 WMA 修正一并升至 6。旧版本快照必须从权威 OHLCV 重建。
最终完整检查结果记录在 WMA/HMA 验收文档中。

2026-10-02更新：上述correlation完整成对窗口/常量未定义约束是语义6
的历史验收。语义30改用独立有效观测窗口并返回已就绪的常量零值，
原始两列现在进入batch与完整Python callback的严格原生对照；旧差异
断言已替换为原生全列断言。更大的相关性探针仍保留数值差异，未
宣称一般条件下完全一致。详见official alignment Goal最新验收记录。
