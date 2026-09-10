# 最新易用性验收：诊断、验证与执行入口

日期：2026-09-09；当前工作区候选 0.3.1rc1，计算语义身份保持 5。
本轮未提交、未推送、未发布。以下结果均来自本轮 Windows 验证。

| 使用流程 | 修复和验收 |
| --- | --- |
| pandas / CSV / 长任务 | 沿用完整 Python、inline、无默认计算额度；原独立执行回归继续通过 |
| 显式资源预算 | 输入、集合、窗口与状态容量使用资源错误码；提供调整预算或 None 的提示，不建议改变权限 |
| preview / snapshot | 可选 `validate(target=...)` 和 CLI `--target` 提前定位可静态确定的模块 class；不执行代码、不抓取数据 |
| 避免新增误拦 | 已删除/覆盖的 class、动态或导入的回调不因静态猜测被阻止；保留运行时状态检查 |
| API / CLI 政策一致 | validate/run 共用 security-mode、allowed-import、timeout 和 limit 配置；可覆盖环境额度 |
| 结果导出与纠错 | 仅选中曲线要求唯一命名；未知曲线列出可用名称；失败的 JSON/CSV 文件运行保留上次结果 |
| 文档与异常处理 | 直接异常提供 code/hint；新增异常兼容旧基类 catch；错误文档链接补齐显式锚点 |

验证：`scripts/check.ps1` 完整通过；1,236 项测试通过，保留原有大模块提示一项。
性能增长和会话稳定性检查通过，阈值未改。Strategy 27、TA 10、Request 21
外部捕获对照均为零差异、零运行错误。wheel/sdist 构建、Twine 和 Windows
隔离安装通过；安装后 9 类验收、55,075 比较点，并验证新 CLI/诊断流程。
本地完整日志：`.pyne-usability-check.log`。本轮未运行 Linux/macOS 或远端 CI。

静态检查不认证动态闭包、对象图或 provider；这些仍需实际运行验证。
以上是已验证的常见流程，不宣称所有用户程序都能提前静态判定或不存在剩余摩擦。
新操作入口见 [脚本诊断教程](../tutorials/diagnose_script.md)。

---

## 第一轮历史验收记录（以下数字与语义身份不代表当前候选）

### 0.3.1rc1 编写与独立计算体验验收

日期：2026-09-09。基于已发布 0.3.0 后的 main `58243c8`。
本轮是本地开发候选，未推送、未发布；公开安装记录仍为 0.3.0。

## 完成范围

| 原差距 | 交付 | 验证 |
| --- | --- | --- |
| 批量/实时写法分裂 | `pyne new` 随包提供 trend、volatility、state 三种 Python 模板；无需 init，沿用命名 TA 的首次使用初始化；同一 on_bar 源码供历史 pn.run 与实时 session 使用 | 三模板独立 EMA/均值方差/累计变化算术对照；64 根历史、重复 preview、16 根保留窗口、warmup 前后及第 32 根恢复 |
| CSV 与入门入口 | CLI 列映射、秒/毫秒输入、按名称选择并导出 CSV；创建脚本不覆盖现有文件；失败计算保留已有 CSV；补齐安装与操作教程 | 重命名列、毫秒时间戳、含逗号列名、缺失值、选择顺序、无效选项、参数失败等测试；Windows/Linux 安装 wheel 中生成并运行全部模板 |
| 完整编写任务验证 | 初译失败→Inspector 建议→标量 callback 修正；趋势、波动、显式状态三个完整任务；教程包含历史运行、预览确认和恢复代码 | `tests/test_authoring_workflows.py` 10 项；沿用既有真实 ADX/DI 迁移与外部捕获证据，不把新第一方模板称为真实用户采用 |

核心继续执行 Pine 风格 Python。CandleScope 行情、图表、持久化和连接实现不进入本库。
本轮没有修改计算内核或会话状态格式，计算语义身份保持 3。
选择统一 callback 写法可以复用源码；没有自动把任意向量化 batch 脚本转换成增量脚本。

## 实际检查

- Windows Python 3.12：1176 passed，保留既有 session.py 大模块提示一项。
- Ruff、compileall、生成状态和 diff 检查通过。
- 性能门禁 9 次重复通过，会话稳定性五项通过；阈值未改。
- 外部捕获：Strategy 27、TA 10、Request 21，全部零差异、零运行错误。
- wheel/sdist 构建与 Twine 通过。
- 同一 wheel 在 Windows Python 3.12.7、Linux Python 3.12.13 临时环境独立安装通过：
  三个模板从已安装包生成，检查、导出 CSV；原五类工作流各 5074 比较点通过。
- 新候选没有运行远端三系统九组合 CI，不借用 0.3.0 发布记录代称其已通过。

本地构建与日志位于 `build/usability-0.3.1rc1/`、`build/stable-delivery/usability-*`。
新命令完整用法见 [CSV 到实时](../tutorials/csv_to_realtime.md)。
