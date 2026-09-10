# 0.4.0 发行验收

日期：2026-09-10。包版本 0.4.0，计算语义 5。

## 当前状态

**0.4.0 已正式发布，公开 wheel 与源码包 SHA-256 核验通过。**
[PR #5](https://github.com/helenananaa/pyne-runtime/pull/5) 已合并；
`v0.4.0` 指向 `b1f55c8817a05509ca8a06ea8fbc809f86239fda`。
[正式 Release](https://github.com/helenananaa/pyne-runtime/releases/tag/v0.4.0)
发布于 2026-09-10 00:24:46 UTC，非草稿、非预发行。

- [PR CI](https://github.com/helenananaa/pyne-runtime/actions/runs/34420623160)：19/19 通过。
- [main CI](https://github.com/helenananaa/pyne-runtime/actions/runs/34420853342)：19/19 通过。
- [发布流程](https://github.com/helenananaa/pyne-runtime/actions/runs/34421059454)：11/11 通过。
- 三系统 × Python 3.11/3.12/3.13 的源码和已安装 wheel 检查通过。
- 发布流程对同一构建产物独立完成九组合安装验证，发布时没有重新构建。

## 交付范围

- 独立执行默认完整 Python、当前进程、无默认截止时间或计算配额。
- 宿主显式设置权限和资源策略；输入、结果保留、回放记录独立配置。
- 快照恢复检查计算身份与状态容量，重新绑定所选预算；旧语义快照拒绝并从 OHLCV 重建。
- 三类安装包模板、CSV 映射与导出、历史/实时共用回调、诊断与静态预检。
- README 去除中间示意图，安装入口与说明已统一为 0.4.0 正式版。

## 本地验证

- Windows 完整 `scripts/check.ps1` 退出 0：1,236 passed，1 项既有大模块提示。
- 性能与五项会话稳定性门禁通过，原阈值未放宽。
- Strategy 27、TA 10、Request 21 外部捕获全部零差异、零运行错误。
- wheel/sdist 构建、Twine 元数据检查通过。
- 独立安装 wheel：三模板生成/检查/CSV 导出；9 类工作流、55,075 比较点通过。
- 公开下载的 wheel 再次隔离安装通过：9 类工作流、55,075 比较点；日志 `build/release-0.4.0/published-smoke.log`。
- 正式 README 示例输出正确，28 个本地链接有效，23 项文档测试通过。
- 完整日志保存在 `build/release-0.4.0/windows-gate.log`。

机器可读记录与日志摘要见 [发行证据](evidence/release_0.4.0_20260910.json)。
验证仅覆盖文档声明的运行时能力与固定工作负载，不代表任意脚本或市场场景。
