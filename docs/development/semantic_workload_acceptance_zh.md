# 完整脚本语义验收：第一批

日期：2026-09-07。基线提交：`64eb354`。范围：独立 `pyne-runtime`。

本轮建立五类第一方完整脚本的组合验收，发现并修复单根高周期数据的提前披露问题。
脚本、原始外部证据及执行说明位于 [tests/workloads](../../tests/workloads/README.md)，
测试入口为 `tests/test_semantic_workloads.py`。

## 验收内容

| 类别 | 检查 |
| --- | --- |
| TA 组合 | SMA → crossover → valuewhen；批量/增量及 TradingView 对照 |
| 多周期 | HTF、稀疏 LTF 分组、平滑后的价差；按时间点对照；扰动未来数据 |
| 状态与缓存 | 嵌套可变对象、全局 cache 别名、计数、滚动均值；独立算术预期 |
| 绘图 | line/label 反复创建、更新、删除；事件顺序、时间与 confirmed 标志 |
| 策略 | 撤销未成交 stop、入场、减仓、平仓、手续费；完整报告及独立盈亏预期 |

45 个参数化测试实例覆盖：

- 三类批量/增量对照及三类未来数据扰动；
- 五类脚本 × local/replay/state 三种恢复方式，每根确认前重复三次 preview；
- 五类脚本各运行 256 根 bar，在 32/64/128/192 根后执行 typed-state 恢复；
- 五类脚本在回调修改状态后抛异常，验证 poisoned 行为及从失败前快照恢复；
- 单根请求下 batch/incremental × gaps on/off × lookahead on/off；
- TA 的两种执行模式与外部日志对照，以及状态、绘图、策略的独立预期；
- 对 `barstate.isnew` 敏感的已提交状态使用 typed-state 恢复。

每条数据流都保留时间坐标；预热时无输出不能通过丢弃时间戳而被误判为对齐。
这些规模用于确定性恢复与保留窗口验收，不构成生产吞吐量或内存上限承诺。

## 本轮修复

`request/alignment.py` 原先完全根据相邻时间戳推断周期。当请求结果或 chart context
只有一根 bar 时，无法推断间隔，`lookahead="off"` 会退化为按开盘时间披露 HTF
最终值。例如 10 秒图请求 30 秒数据，t=0 的 HTF 最终 close 会错误地出现在 t=0。

修复从 `RequestModule` 传入 chart/request 周期长度，仅在间隔不能推断时作为补充。
该例现在到 chart t=20（收盘边界 t=30）才披露。标量、tuple 和显式 lookahead_on
均有覆盖；已有多根数据对齐路径保持原有规则。该修复不声称解决交易时段、月历周期、
任意稀疏数据的完整日历对齐。

三个 diff 工具单元测试使用的临时合成 fixture 原先依赖这个错误，假设一个 4 小时
最终值在第 1 秒就可读。它们现在显式声明 `lookahead="on"`，保留原来的比较工具
测试目的。真实 TradingView 捕获未被改写。

## 外部证据与边界

通过用户授权的 Chrome，在 TradingView Pine v6 运行第一方合成序列脚本，取得
完整 40 根日志。保留 Pine 源码、原始日志、结构化数值和摘要。按输出协议的 8 位
小数比较两种执行模式；原日志的 10 位小数不被修改。这一组合捕获单独由 pytest
验收，不计入原来的 58 个外部 capture 案例总数。

replay-v1 不记录 preview 访问，因而不能承诺复现依赖 `isnew`/intrabar 历史的脚本。
本批 replay 工作负载不依赖该历史，只排除 `isnew` 元数据比较；数值、绘图事件、
策略报告及其余元数据仍检查。对该历史敏感的已提交状态使用 local/state-v2 快照。
这是已明确的适用范围，不是对任意脚本恢复等价的证明。

旧审查的 EMA/RSI/Supertrend/VWMA/OCA 外部语义问题不在本批修复声明中。
下一批应围绕这些具体边界扩充外部捕获，避免按 API 名称数量继续扩展。

## 复现

```powershell
.venv\Scripts\python.exe -m pytest tests/test_semantic_workloads.py -q
.\scripts\check.ps1
```

完整门禁包含 pytest、现有 capture diff、性能/稳定性 smoke、wheel/sdist 构建、
Twine 及离线隔离安装检查。发布、提交和推送均不由本验收文档隐含授权。

## 本轮验证结果

2026-09-07，Windows / 仓库 `.venv` 执行 `scripts/check.ps1`，退出码 **0**：

| 检查 | 结果 |
| --- | --- |
| 完整 pytest | 966 passed（含本轮 45 项） |
| Request / Strategy / TA 捕获 | 21 / 27 / 10，全部 0 diff、0 runtime error |
| 本轮 TA 组合外部捕获 | 40 根完整日志，两种执行模式均通过 |
| 性能与多会话稳定性 smoke | 全部通过 |
| wheel / sdist、Twine | 通过 |
| 离线隔离安装、CLI、schema/能力检查及包示例 | 通过 |

本地完整日志：`build/semantic-workloads/check.log`（生成产物，不纳入版本控制）。
pytest 另有既存的 `incremental/session.py` 模块体积提示；本轮未重构该模块。
