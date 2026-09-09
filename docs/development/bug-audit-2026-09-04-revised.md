# pyne-runtime 缺陷审查修订稿

> 后续状态（2026-09-07）：B1 EMA/MACD 与 B2 RSI 已取得新的 TradingView Pine v6
> 外部证据并修复，见[指标边界验收](ta_boundary_acceptance_zh.md)。下面保留原审查
> 的历史发现与当时的待确认结论，不应把 B1/B2 继续视为未处理项。

> 第三批补充：B3 的首根 Supertrend=0 已由原生 Pine 确认，保留行为并关闭疑点；
> B4 的 VWMA 缺失窗口已修复。C2 实测确认市价 `strategy.order` 不施加这里的
> pending OCA 效果，批量路径正确，修复的是增量误取消/减量及已成交 sibling
> 被追溯修改的问题。详见[第三批验收](trend_volume_oca_acceptance_zh.md)。

审查基线：`main@9ce0a4d`（2026-09-04）  
验证结果：完整测试 `881 passed, 1 warning`；工作树在验证前为干净状态。

## 结论

当前代码库不能宣称“无 bug”，也不应把 `process` 或 `unsafe` 模式描述成经过强化的敌对代码沙箱。核心路径上仍有若干已经能够复现的状态隔离、错误分类、配置校验和缺失值处理问题。

不过，原审查不能原样作为修复清单：

- “部分平仓佣金重复计算”与仓库保存的 TradingView 捕获相冲突；直接删除现有扣减会破坏已经验证的 Pine accessor 兼容行为。
- “同 tick 市价单必须互相触发 OCA”缺少依据，而且可能与 TradingView 的同 tick 成交语义相反。
- EMA、RSI、Supertrend、VWMA 的异常输入行为确实可疑，但准确目标值尚缺少专门的 TradingView 捕获，不宜凭直觉直接统一实现。
- 强制 `fork`、实时 `builtins` 和巨型文件属于有条件的安全风险或结构债，不能和默认路径上的确定性错误混成同一个严重级别。

因此，本报告把发现分成四类：

1. 已确认、可以直接修复的正确性或事务性缺陷；
2. 已确认存在差异，但修复目标需要外部语义捕获的指标问题；
3. 当前证据不足或原结论不成立的项目；
4. 安全强化与结构性债务。

## A. 已确认、可以直接修复

### A1. Preview 可以污染已提交的 cache

位置：`src/pyne_runtime/incremental/session.py`

Preview deepcopy 把绑定方法按 identity 放入 memo，导致 preview namespace 中的 `cache` / `cache_clear` 仍绑定到已提交的 `PyneCache`。在 preview 中执行 `cache("k").append(999)` 后，下一次正式回调能观察到该元素。

这是明确的隔离契约破坏。修复时应克隆 cache namespace 及其底层状态，或重新绑定 preview 专用方法；同时增加 `cache_clear()` 和嵌套可变值两类回归测试。

优先级：P1。

### A2. 普通增量回调异常不会 poison session

位置：`src/pyne_runtime/incremental/session.py::_run_bar`

`begin_bar()` 后用户回调已经可能改写 series、strategy 和 drawing 状态，但当前只有安全异常和资源限制异常会 poison。普通 `ValueError`、`TypeError` 或超时异常逃出后，session 仍可处理下一根 bar。

最小复现中，第二根回调先写状态再抛 `ValueError`，第三根仍继续运行，最终保留了失败 bar 的写入。

应选择并冻结一个事务契约：

- 任意逃出 bar 回调的异常都 poison session；或
- 在回调失败时完整回滚至上一份 committed state。

在没有可靠事务回滚前，fail-closed poison 是更小、更安全的修复。

优先级：P1。

### A3. `restore_state()` 非原子，且不能恢复空 session 快照

位置：`src/pyne_runtime/incremental/session.py::restore_state`

函数在完成全部反序列化和函数状态恢复前就开始替换 `_ctx`、globals 和 cache。后续 deepcopy 或 `_restore_function_states` 失败，会留下混合新旧状态，而且 session 不会自动 poison。

此外，`seed()` 前生成的合法快照中 `context is None`，restore 后无条件读取 `self._ctx.trace` 会触发 `AttributeError`。

修复应在局部临时对象中完成全部验证和构建，成功后一次性 swap。空上下文快照应明确支持；若产品决定拒绝，也应在任何状态变更前返回稳定的领域错误。

优先级：P1。

### A4. `barssince` / `valuewhen` 把 `NaN` 条件当成真

位置：`src/pyne_runtime/utils.py`

当前实现对条件数组直接调用 `.astype(bool)`；NumPy 中 `NaN` 会变成 `True`。复现结果：

- 条件 `[NaN, 0, 1]` 的 `barssince` 返回 `[0, 1, 0]`；
- 同一条件下，`valuewhen` 在首根错误捕获了源值。

这与仓库已有的 `_truthy` 缺失值规则不一致。TradingView 也规定 `ta.barssince()` 在条件首次成立前返回 `na`。

应统一使用一个明确的条件归一化函数：missing 为 false、有限非零值为 true；`barssince` 在首次 true 前保持 `na`。

优先级：P1。

### A5. 非法配置值被静默接受

位置：

- `src/pyne_runtime/strategy/costs.py`
- `src/pyne_runtime/settings.py`

已复现：

- `commission_type="per_trade"` 最终得到零手续费；
- `executor_mode="typo"` 被静默归一化为 `process`。

这两项都会让调用方误以为配置已经生效。未知枚举应在初始化阶段抛出稳定、可定位的配置错误，而不是猜测或回退。

优先级：P1。

### A6. 非法 OHLCV 被错误分类成脚本运行错误

位置：`src/pyne_runtime/runtime.py`

缺少 `volume` 或时间不递增时，当前返回 `PYNE_RUNTIME_ERROR`，尽管错误码契约已经提供 `PYNE_INVALID_OHLCV`。这会让 host 错误地把输入问题归因于用户脚本。

应把输入解析和验证放在脚本执行错误边界之外，并对所有 OHLCV 结构错误统一返回 `PYNE_INVALID_OHLCV`。

优先级：P1。

### A7. Batch `params` 不是深层只读

位置：

- `src/pyne_runtime/namespace.py`
- `src/pyne_runtime/input.py`

顶层 `MappingProxyType` 只阻止键赋值，嵌套 list/dict 仍引用 host 对象。脚本执行 `params["nested"].append(9)` 后，调用方原始参数也发生变化。

增量路径已有 freeze 语义；batch 应复用同一深层冻结/复制入口，并覆盖嵌套 list、dict、set 和自定义可变对象边界。

优先级：P1。

### A8. Timeframe 可以形成自相矛盾的状态

位置：

- `src/pyne_runtime/metadata.py`
- `src/pyne_runtime/context.py`
- `src/pyne_runtime/request.py`

当前秒数换算有多份实现。mapping 输入可以构造 `{"period": "1h", "multiplier": 1}`：`TimeframeInfo.in_seconds()` 从 period 得到 3600 秒，context 却按 multiplier 得到 60 秒，导致最后一根 `time_close` 错误。

`"1h30"`、`"15min"` 等无法完整解析的字符串还会保留 raw period、使用 multiplier 1，并在部分调用点表现成一分钟周期。

应只保留 `TimeframeInfo` 的单一规范化和换算入口；period 与显式 multiplier 冲突时拒绝输入，畸形文本必须返回配置错误。先前报告的合法 `m` 后缀缺失已经修复，不应重复计入。

优先级：P1。

### A9. 负 period 没有在 API 边界拒绝

位置：`src/pyne_runtime/utils.py::change`、`roc`

`period=-1` 会落到底层切片/广播并产生非领域化异常。所有要求非负或正整数周期的 API 应复用统一验证器，并在计算前返回一致错误。

优先级：P2。

### A10. 增量脚本检测会接受嵌套 `on_bar`

位置：`src/pyne_runtime/incremental/detection.py`

`ast.walk` 会把任意层级的 `def on_bar` 当作模块入口，使本应按 batch 执行的脚本被静默改道。检测应只检查模块顶层函数定义，并明确处理重复定义、async 定义和条件定义。

优先级：P2。

### A11. Plot 颜色序列化可输出非法值

位置：

- `src/pyne_runtime/plot/value_helpers.py`
- `src/pyne_runtime/plot/functions.py`

已确认的复现是：

- ndarray 颜色中的 `np.nan` 被序列化成字符串 `"nan"`；
- 顶层传入颜色 list 时，整个 list 被 `str(...)` 成一个颜色值。

原报告给出的 `color.when(close > 10, color.green, na)` 不是稳定复现，不应继续引用。颜色输入应先分类为 scalar 或 series，再逐点用统一的 `is_na_value` 处理。

优先级：P2。

### A12. Manager 在 factory 成功前淘汰有效 session

位置：`src/pyne_runtime/incremental/manager.py`

容量为 1 时，创建新 session 会先驱逐现有 idle session；若 factory 随后失败，旧 session 已丢失且新 session 也不存在。

应先成功构造候选 session，再在锁内重新检查容量并完成原子替换；同时覆盖 factory 抛错和并发 acquire 的测试。

优先级：P2。

## B. 行为可疑，但修复目标需要 Pine 捕获

这些项目都能证明“当前不同实现之间不一致”或“结果反直觉”，但仅凭仓库现状还不能证明原报告给出的目标值就是 TradingView 语义。

### B1. EMA 在残缺种子窗上使用 `nanmean`

位置：

- `src/pyne_runtime/ta.py::ema`
- `src/pyne_runtime/incremental/ta.py::_StepEMA`
- `src/pyne_runtime/ta.py::_ema_skip_leading_na`

输入 `[1, NaN, 3, 4, 5]`、period 3 时，batch 和 incremental 当前都得到 `[NaN, NaN, 2, 3, 4]`，即在固定的第三根用两个有限值播种。这与函数自身“Seed with SMA”说明以及 `_ema_skip_leading_na` 的规则不一致。

原建议“全部改走 `_ema_skip_leading_na`”仍缺少依据：Pine 对 leading `na` 和中间 `na` 的处理必须分别捕获。先增加以下外部 fixture，再抽取共享规则：

- 开头连续 `na`；
- 种子窗口中间出现 `na`；
- EMA 已建立后再次出现 `na`；
- MACD signal 在同样输入上的行为。

状态：确认实现漂移；目标语义待捕获。建议 P1 调查，捕获后修复。

### B2. 横盘 RSI 返回 0

位置：batch RSI 与 incremental `_rsi_from_avgs`

连续平盘使 `avg_gain == avg_loss == 0`，当前后一个 `where` 覆盖前一个分支，最终返回 0。batch 与 incremental 一致，但结果会把无涨跌误解成极度超卖。

应显式拆分“双零、仅 loss 为零、仅 gain 为零”，但双零究竟返回 50 还是 `na` 应由 TradingView 捕获或产品契约决定。

状态：确认边界处理不明确；目标值待捕获。

### B3. Supertrend 第一根固定为 0

位置：batch 与 incremental Supertrend

ATR 尚未建立时，当前把第一根 Supertrend 写为 `0.0`；现有测试也明确锁定了该结果。它会在常规价格图上产生到零点的异常值，但改变它属于兼容行为变更。

应先捕获 TradingView warmup 区间的 line 和 direction，再决定第一根保持 `na` 还是采用其它值，并同步更新已有 golden/test。

状态：确认反直觉且被测试固化；目标值待捕获。

### B4. VWMA 对 price `NaN` 和 volume 的配对处理不一致

位置：`src/pyne_runtime/ta.py::vwma`

输入 price `[10, NaN, 30]`、volume `[1, 1, 1]`、period 3 时，当前结果是 `13.333...`：分子跳过缺失价格，分母仍计入对应 volume。现有性能测试明确依赖 `nansum` 规则，因此这不是无意中未覆盖的行为。

从加权平均定义看，该结果可疑，但应先捕获 Pine 在 price/volume 分别缺失时的行为，再决定是整窗 `na`，还是同时排除对应的 price 与 volume。

状态：确认算术口径可疑；目标语义待捕获。

## C. 原结论不成立或证据不足

### C1. 不应直接“修复”部分平仓手续费

位置：`src/pyne_runtime/strategy/ledger.py`

原报告正确观察到字段之间不满足直觉上的恒等式。例如最小场景中：

- summary：gross profit 1、commission 4、net profit -3；
- closed trade：profit -1、commission 3、net profit -4；
- 剩余持仓仍携带 1 的入场佣金。

但是，仓库的 `tests/golden/strategy_pine_equivalent_cost_allocation.json` 保存了真实 TradingView 捕获，`docs/reference/pine_like_api_matrix.md` 也明确说明部分平仓的 trade-profit 报告遵循该捕获。捕获结果表明 Pine 的 `closedtrades.profit`、`closedtrades.commission` 和再次相减后的派生值本来就具有这种反直觉关系。

因此不能按原建议删除 `reported_profit -= entry_commission`。若产品还需要满足标准账务恒等式，应另增命名清楚的 `raw_pnl`、`allocated_commission`、`net_pnl` 字段，同时保留 Pine 兼容 accessor。

判定：原“重复计算 bug”结论撤回；可另立 API 清晰度改进项。

### C2. 同 tick 市价 OCA 不能仅凭路径不对称判为 bug

位置：`src/pyne_runtime/strategy/replay.py`

复现可以证明：同一 cancel OCA 组中的两个市价 `strategy.order` 能在同一 bar/tick 都成交；pending fill 路径则会在每次成交后调用 OCA。

但 TradingView 的策略说明指出，如果同组订单在同一 tick 执行，策略可能无法在执行前取消或缩减兄弟订单。两个同 tick 市价单都成交因而可能是正确兼容行为。代码路径不对称本身不足以推导语义错误。

应先增加两类 TradingView 捕获：

- 两个同 tick 市价兄弟订单；
- 市价订单成交后，对下一 tick 才满足条件的 pending 兄弟订单的影响。

只有第二种情况下兄弟订单仍错误存活，才应修改成交管线。即便后续重构为共享 fill primitive，也必须把“何时应用 OCA”作为显式时序参数，而不是无条件在每个 fill 后调用。

判定：当前不列为 bug；外部语义待验证。

## D. 安全强化与结构债

### D1. Unix 强制使用 `fork`

位置：`src/pyne_runtime/executor.py::_multiprocessing_context`

在支持 `fork` 的平台上强制选择它，会继承文件描述符和父进程地址空间，并可能与多线程 host 产生死锁风险。当前 Windows 验证环境会回退到默认 `spawn`，所以这里没有本机动态复现。

改为 `spawn` 或经过设计的 `forkserver` 是合理的可靠性强化。但项目文档目前把 safe/research 描述为策略限制而非 hardened sandbox，因此不能把这一点单独表述为“默认隔离边界已被攻破”。若未来承诺执行敌对代码，这一项应升级为发布阻断条件。

### D2. `unsafe + inline` 暴露实时 `builtins.__dict__`

位置：`src/pyne_runtime/security.py::build_builtins`

该组合下脚本能覆盖 host 进程中的 `builtins.abs` 等对象，动态复现成立。`return dict(builtins.__dict__)` 可以消除这种直接全局污染，且不改变 unsafe 模式允许调用危险 builtin 的定位。

这是值得修复的宿主可靠性问题，但危险边界是调用方显式选择的 `unsafe + inline`，不能描述成默认 safe 模式逃逸。

### D3. Inline timeout 契约不清晰

显式 `timeout_seconds` 在 inline 路径没有直接生效；Windows 和非主线程环境也无法依靠当前机制获得硬超时。应把“软检查”“平台受限超时”和“process 硬终止”分别写入 API 契约，并拒绝无法兑现的 hard-timeout 配置。

### D4. 重复实现已经形成维护风险

当前确有五个文件超过 1000 行，但原报告中的具体行数已过时：

| 文件 | 当前约行数 |
| --- | ---: |
| `incremental/session.py` | 1558 |
| `plot/functions.py` | 1481 |
| `ta.py` | 1437 |
| `incremental/ta.py` | 1366 |
| `incremental/strategy.py` | 1348 |

更重要的问题不是行数本身，而是同一语义被多处实现：

- EMA/RSI/Supertrend 同时存在 batch 和 step 版本；
- timeframe 秒数在 metadata、context、request 中分别推导；
- 市价 entry、市价 order、pending order 分别执行相似的成交步骤；
- plot 的不同 style 重复组装 points 和颜色。

重构应在语义 fixture 冻结后进行。否则“大一统”只会把尚未验证的规则扩散到所有路径。

## 修订后的门槛判断

### 对当前公开定位

仓库当前定位是 alpha、host-embedded runtime，并非 production brokerage 或 hardened hostile-code sandbox。完整测试通过说明已有契约没有普遍崩坏，但不能证明缺失值、失败事务和隔离边界正确。

### 对发布/集成决策

- 作为受控输入下的 alpha/研究运行时：可以继续开发和验证，但应公开上述限制。
- 作为需要长寿命增量 session 的稳定基线：A1-A3 未修前不能通过。
- 作为严格 Pine 兼容实现：B1-B4 和 OCA 捕获完成前不能宣称完整兼容。
- 作为执行不可信脚本的安全边界：当前不能通过；即使修复 `fork` 和 builtins，也仍需独立威胁模型与逃逸测试。
- 作为生产交易账本：当前项目本身没有这一承诺，也不应从 Pine 展示 accessor 推导标准会计账本。

## 建议实施顺序

1. 修复 preview cache 隔离、callback fail-closed、原子 restore，并建立失败事务测试。
2. 对 commission type、executor mode、OHLCV、timeframe 和 period 统一做入口校验。
3. 修复深层 params 隔离、`barssince/valuewhen`、manager 原子替换和颜色序列化。
4. 建立 EMA、RSI、Supertrend、VWMA 以及两个 OCA 时序场景的 TradingView 捕获。
5. 根据捕获结果统一 batch/step 指标内核；保留 Pine accessor，同时按需增加标准账务字段。
6. 最后拆分 session、plot 和 strategy fill 管线，并以 golden fixture 防止重构改变语义。

## 最小验收清单

修复完成后，除完整测试外至少应新增这些回归门槛：

- preview 对 cache 的 clear、append 和嵌套修改不会进入 committed state；
- 任意用户回调异常后，session 要么完整回滚，要么拒绝后续 bar；
- restore 任意阶段失败都不改变原 session；空 session 快照可确定地恢复或拒绝；
- 所有未知 enum 都在执行前失败，且不发生静默回退；
- 所有非法 OHLCV 都返回 `PYNE_INVALID_OHLCV`；
- batch 脚本不能通过嵌套 params 修改 host 对象；
- missing 条件不会触发 `barssince/valuewhen`；
- timeframe 的 parse、multiplier、seconds 和 `time_close` 使用同一规范值；
- factory 失败不会淘汰现有 manager session；
- plot 输出中不存在颜色字符串 `"nan"` 或 list 的整体字符串；
- Pine 捕获覆盖指标 `na` 边界和 OCA 同 tick/跨 tick 时序；
- Pine 兼容 trade accessor 与新增的标准账务字段分别有清楚的恒等式测试。

## 参考

- TradingView functions FAQ：<https://www.tradingview.com/pine-script-docs/faq/functions/>
- TradingView strategy/OCA semantics：<https://www.tradingview.com/pine-script-docs/concepts/strategies/>
- 本仓库 Pine 成本分配捕获：`tests/golden/strategy_pine_equivalent_cost_allocation.json`
- 本仓库兼容性矩阵：`docs/reference/pine_like_api_matrix.md`
- 本仓库安全模式说明：`docs/concepts/security_modes.md`
