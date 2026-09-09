# 已安装 wheel 的代表性流程验收

日期：2026-09-09。运行时代码基线 `c0e93ab`，包候选 `0.3.0rc2`。
本切片只增强包验收工具和稳定发行政策，不改变运行时计算或快照语义。

`scripts/package_smoke.py` 现在在原有 CLI/schema 检查后，用同一个临时 wheel
解释器和清理过的环境执行 `scripts/installed_runtime_acceptance.py`。后者只把
测试目录里的案例文件作为数据读取，不导入测试模块、pytest 或源码基准脚本，
不向 `sys.path` 注入仓库 `src`。包导入必须位于指定 venv 内且不在仓库源码内；
该检查用显式异常，在 `PYTHONOPTIMIZE=1` 下也不能关闭。

## 实际覆盖

1. 批量运行真实 ADX/DI 迁移脚本，对照 80 根捕获的三条曲线和时间坐标。
2. 增量批处理运行同一案例，对照捕获并验证 Threshold 参考线。
3. 初译稿同时具有 Inspector 迁移建议和实际执行失败；修正版无迁移建议且运行成功。
4. 实际增量会话逐根 preview/commit，在第 13 和 40 根后 state-v2 恢复；保留窗口
   持续与外部捕获比较。preview 前保存独立副本，避免别名污染让对照失效。
5. 真实旧 state 快照拒绝后，从 provenance 描述的 OHLCV 新建会话，检查现行 EMA
   种子和下一根独立算术结果；不修改旧快照。

原始 Pine 日志和结构化捕获先做摘要及逐行对应检查，再进行比较；不将实际缺失点
压缩后按数组索引错位比较。合计检查 5074 个数值点（含重复运行/恢复窗口），
这不是 5074 个独立市场案例。

## 本地证据

- 独立工作树 `codex/wheel-runtime-acceptance` 构建 wheel/sdist，构建和 Twine 通过。
- 维护者纠正初稿中与实际公开 API 不符的调用和错误的原始文件摘要映射，随后用
  真实临时安装执行验收，未通过改动标准输出来取得通过。
- 主工作树最新验收 helper 再次使用该 wheel，退出 0：`ok=true`、`cases=5`、
  `pointsChecked=5074`、`semanticsIdentity=2`。导入位于临时
  `venv/Lib/site-packages/pyne_runtime/__init__.py`，完整输出为
  `build/stable-delivery/installed-wheel-check.log`。
- wheel SHA-256：`181f57ddc3d69c26d6bdbc14fd03755ddb306043272fba3a22c90c3f0c3020da`。
  该制品对应本切片基线，最终发行提交需重新构建与验收。
- 包检查、发行文档和文档入口合计 27 passed，相关 Ruff 通过。

此处使用 Windows Python 3.12 的离线依赖复用模式；被测 Pyne 本身从 wheel 安装。

随后用 Windows Python 3.13.9、全新临时环境和在线依赖解析重复相同 wheel 的安装
验收：NumPy 2.5.3（cp313-win_amd64）安装成功，五类流程/5074 点通过，退出 0；
日志 `build/stable-delivery/installed-wheel-python313.log`。这同时覆盖独立依赖解析路径。
其他平台和最终发行提交完整门禁仍须单独验证。本页不声称九平台远端 CI 已执行，
更不代表公开发布。
