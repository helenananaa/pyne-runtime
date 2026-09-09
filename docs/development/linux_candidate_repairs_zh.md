# Linux 候选验收发现与修复

基线 `14b4535` 的 Windows 完整门禁通过：1148 passed，性能/稳定性、捕获对照、
wheel/sdist、Twine 和安装流程均成功。随后在普通 Ubuntu-22.04 WSL 的 Linux
原生临时目录浅克隆同一提交，使用既有 CPython 3.12.13 创建独立 venv。
没有使用 Android 构建发行版，也没有改系统 Python。

## 首轮失败如实保留

Linux 同样 1148 passed，但 WMA 增长比 8.086 超过既有 3.000 上限，完整门禁停止。
默认环境下再次确认仍失败（5.722）。后续独立安装检查另发现离线嵌套 venv 无法
导入 NumPy。二者均不是“Linux 已通过”；原始日志位于本地
`build/stable-delivery/linux-performance-confirmation.json`、Linux 临时目录的
`check.log` 及工具输出。Linux 外层启动脚本还曾因末尾 CRLF 报 exit 参数错误，
实际门禁的 `exit-code.txt=1` 和性能 FAIL 独立保留，不能把它误当作纯启动问题。

## 加权初始归约

`_rolling_weighted_sums` 的种子使用 `np.dot`。当前 Linux NumPy 2.5.3 的 OpenBLAS
默认 32 线程，小向量跨线程派发造成尺寸相关开销。九对交替大小测量及单线程诊断
保存在 [BLAS 剖析](evidence/wma_blas_profile_20260909.json)；单线程仅用于定位，
没有写入运行时或修改宿主线程设置。

最终代码仅将初始种子换成 `np.einsum("i,i->", ..., optimize=False)`，保留 centering、
滚动递推、缺失/无穷处理和精确溢出回退。默认 32 线程环境下，原增长门禁变为
2.070，3.000 上限未变，其他性能项也通过。
[修复前报告](evidence/linux_performance_before_20260909.json)与
[修复后报告](evidence/linux_performance_after_20260909.json)均保留。

15 组数值比较（不同长度、周期和 0/1e9/1e12 偏移）发现 31492 个浮点末位变化，
最大绝对差异 7.416e-17，八位舍入变化为 0；见
[数值差异](evidence/wma_seed_numerics_20260909.json)。不能因此声称逐位相同。
共享内核也被线性回归使用；测试验证两条路径不再派发 `np.dot`，并与独立窗口
参考比较，已有测试和外部标准输出未删除或放宽。

数学公式未变，但未舍入值可能进入 request 表达式和脚本状态，因此保守推进
`INCREMENTAL_SEMANTICS_VERSION` 至 3。源自真实 `14b4535` 的版本 2 快照存于
`tests/golden/snapshot_semantics_v2/`，验证升级拒绝；当前版本恢复与延续保持通过。
包版本和 wire-format 不因此替代该身份。版本 2 及更早的会话从权威 OHLCV 重建，
不重新标记旧 payload。此前容量批次仍是原版本 2 的记录；本次改变的 WMA/linreg
内核不在那三类测量负载的计算路径中，不能重写旧报告的提交或语义身份。

## 离线安装依赖目录

`--system-site-packages` 继承基础解释器的目录，不能单独保证调用方 venv 的 NumPy
可见。Windows Anaconda 环境掩盖了这个缺口。修复后查询实际 `--python` 解释器的
purelib/platlib，将这些目录追加到新 venv；不递归处理父环境 `.pth`/editable hooks。
子环境安装的 wheel 保持优先，来源检查在优化模式下也生效。实际子解释器测试同时
验证依赖可用、冲突的父包不覆盖子包、父 hook 未执行，以及越界/换行路径拒绝。

Linux 针对该机制的真实离线复测通过，5 类流程/5074 点，包来源位于新 venv。
这次机制复测使用原语义 2 wheel；合并后的语义 3 候选仍须完整重新构建验收。

## 当前状态

维护者定向检查：加权算法、快照边界、离线安装测试合计 101 passed，Ruff 通过；
发行入口补齐现有性能/稳定性检查，67 项相关检查通过。没有降低任何性能预算。
语义 3 下另运行同三种负载的 1/4/8 会话、各 96 根冒烟，全部完成且无不变量失败；
[结果](evidence/capacity_semantics3_smoke_20260909.json)单独保留，不替换旧长测。
合并后的 Windows/Linux 完整门禁尚待执行，不能沿用修复前的 1148 passed 代替它。
