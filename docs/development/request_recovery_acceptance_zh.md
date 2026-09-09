# 增量 request 瞬时故障恢复验收

日期：2026-09-09。范围：独立 `pyne-runtime`，不修改运行时、既有测试、捕获或包元数据。

既有 `tests/test_semantic_workloads.py::test_failed_workload_recovers_from_last_committed_state`
覆盖的是回调抛出异常后的 poisoned 恢复，不是宿主 provider 的瞬时取数故障。
`tests/test_incremental_request.py` 覆盖 typed 缺 provider / 非法返回，以及覆盖区间不重复取数，
不是「提交前缀 → 新取数区间失败 → poisoned → typed-state 恢复 → 续算」的完整路径。

本批只新增验收测试与本文档。

## 覆盖

`tests/test_incremental_request_recovery.py` 两个验收函数，按 `request.security` 与
`request.security_lower_tf` 参数化，共 **4** 项：

| 检查 | 数量 |
| --- | ---: |
| 瞬时 provider 故障、typed 错误、poisoned 拒绝后续提交、typed-state 恢复后前缀与续算 | 2 |
| 恢复后 confirmed/preview 保留旧时间戳绘图点；更换后的 provider 只影响新 bar | 2 |

宿主中立、不可变 OHLCV。图表周期 `10S`。`request.security("TEST:ASSET", "10S", "close")`
的当前值等于独立算术 `1000 + t`。`request.security_lower_tf(..., "5S", "close")`
在每个图表桶 `[t, t+10)` 内固定两根 5 秒 bar，`size() == 2`，`last()` 等于
`2000 + t + 5`。脚本在调用 request 之前推进 `ctx.state("count")`。

故障路径：至少 2 次成功提交后，provider 在**新的取数区间**上抛出公开
`PyneProviderDataError`。断言：

- 失败为 `PyneRequestError`，`category="providerFailure"`，`code="PYNE_RUNTIME_ERROR"`；
- poisoned 会话拒绝下一次 `on_bar_closed`（`PyneSecurityError`）；
- 失败前 `snapshot_portable_state()` 用恢复后的 provider 重建会话；
- 旧提交前缀与后续数值同时等于独立算术和从未失败的对照会话。

第二项不把 provider 改写历史当作受支持的数据更新。typed-state 快照不含 provider
缓存。恢复时换用会对同一历史时间戳给出不同 close 的 provider，仅用于证明：后续
preview/confirmed 步仍保留快照前已提交的时间戳绘图点；新 bar 才使用新算术。
`cache_max_items=1` 只作为已声明的请求区间缓存上限，必要时允许逐出后再向新
provider 取数，不收紧 `max_output_points`，以免裁掉绘图点。

比较公开 `result.lines` 与 `output`。增量事件结果只携带当前 bar 的点；保留窗口
以 `snapshot_result()` 为准。排除 `meta["requestDiagnostics"]`、
`meta["requestDiagnosticsInfo"]`（冷恢复后的 cacheHit / 自适应 start-end /
dropped 不是计算身份），以及可能被 preview 访问改写的 `meta["barstate"]["isnew"]`。
保留 `retentionBars` / `retainedBars` / `totalCommittedBars` 等会话记账字段。

## 规模与限制

- 图表 8 根 10 秒 bar；会话 `retention_bars=8`。
- 故障项默认 `cache_max_items`（32）与默认 `max_output_points`。
- 保留项 `cache_max_items=1`；`max_output_points` 保持默认，避免与绘图保留混淆。
- 不构成吞吐、内存上限或「provider 修订历史」协议承诺。

## 复现

在本工作树执行（解释器为仓库外的维护者 venv，不安装、不联网）：

```powershell
H:\program\pyne-runtime\.venv\Scripts\python.exe -m pytest -q tests/test_incremental_request_recovery.py
H:\program\pyne-runtime\.venv\Scripts\python.exe -m ruff check tests/test_incremental_request_recovery.py
```

本批不运行完整 `scripts/check.ps1`，不提交、不推送。

## 本轮验证结果

2026-09-09，工作树 `E:\Disk0Merged\H\program\pyne-runtime-request-recovery`：

| 检查 | 结果 |
| --- | --- |
| 上列 pytest | **4 passed**（0.62s） |
| 上列 ruff | All checks passed |

未改运行时。若后续失败暴露真实缺陷，应保留失败测试，由维护者决定是否改运行时。

维护者审核后在该独立工作树复跑：4 passed（0.46s），Ruff 通过。整合时将同周期
请求输出名称从 `HTF` 改为 `Requested`，避免把 10S→10S 宣称为高周期验收，并移除
一个只检查固定切片长度的冗余断言。本切片覆盖两类 request 的故障路径；已有 HTF
时间对齐测试继续保留，不由本切片替代。
