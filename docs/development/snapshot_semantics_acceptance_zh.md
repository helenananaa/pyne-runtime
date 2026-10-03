# 快照升级与四批语义修复收敛

日期：2026-09-08。独立运行时，本地基线 `64eb354`。

此前四批修复改变了 EMA/RSI、VWMA、SMA/方差/BB、OCA 和单根 HTF 披露语义，
但快照只有格式版本。字段可以解码不代表旧状态可按新规则继续执行；replay-v1
重新计算旧历史也不能声称恢复了旧结果。

本批引入独立整数语义版本 `1`。local 状态和两种 portable envelope 均携带标识；
缺失、不匹配、布尔值、字符串和浮点值均拒绝。异常仍属于已有
`PynePortableSnapshotError`，增加可机读 `code=PYNE_SNAPSHOT_SEMANTICS_MISMATCH`，
消息说明从权威 OHLCV 重建，禁止修改版本标识强行导入。格式版本和包版本不变。

没有可靠的旧语义身份，因此所有未标记快照均拒绝，未按指标名称猜测是否安全。
这不是自动检测代码变化；后续不兼容语义或状态变更必须由维护者提升语义版本。

## 证据

`tests/golden/snapshot_semantics` 的 replay/state JSON 由真实历史提交
`64eb354` 的源代码在独立目录加载后生成，包含四根 bar 和 EMA 状态。
保留脚本、完整提交号、输入说明和 LF 规范化 SHA-256；测试不联网、不运行旧代码。
新增测试同时检查：

- 旧 artifact 在 session 构造前拒绝；
- 只修改旧 state envelope 的标识不能升级内部旧状态；
- local 恢复拒绝后 committed 快照不变，preview 后续确认与独立对照一致；
- 当前 local/replay/state 恢复后继续多根 preview/confirmed 输出一致。

既有五类完整脚本继续覆盖数值、绘图、策略生命周期、恢复与失败隔离；既有
portable 测试继续覆盖跨进程恢复。高偏移方差的两列仍为 reference-only，未改外部预期。

## 复现

```powershell
.venv\Scripts\python.exe -m pytest tests/test_snapshot_semantics.py tests/test_incremental_portable_snapshot.py -q
.\scripts\check.ps1
```

## 完整门禁结果

2026-09-08，Windows / 仓库 `.venv` 执行 `scripts/check.ps1`，退出码 **0**：

| 检查 | 结果 |
| --- | --- |
| 完整 pytest | 1084 passed，含本批 25 项 |
| Strategy / TA / Request 捕获 | 27 / 10 / 21，全部 0 diff、0 runtime error |
| 性能、多会话稳定性与恢复 smoke | 全部通过 |
| wheel / sdist、Twine | 通过 |
| 离线隔离安装、CLI、schema/能力与包示例 | 通过 |

完整日志：`build/snapshot-semantics/check.log`（本地生成产物）。唯一 pytest warning
仍是 `incremental/session.py` 体积提示；本批只添加兼容性校验，没有拆分会话实现。
提交属于本地收敛，不代表推送、发布或远端多平台验收。


## 2026-10-03 开发计算语义36

RMA在缺失输入位置输出缺失，并保留平滑状态，不增加种子计数或重置累加器。
这是输出和历史续算契约变化，因此INCREMENTAL_SEMANTICS_VERSION从34升至36，
候选版本为0.4.1rc31。旧身份不能重新标记以绕过检查。由真实独立安装rc29 /
语义34生成的`tests/golden/snapshot_semantics_v34`和
`tests/golden/rma_missing_semantics_v34`保存state/replay、已提交结果、输入和
wheel哈希。两种portable模式均在会话构造之前拒绝；请用权威调用方OHLCV重建。
新版本local/state/replay继续运行在原生holdout种子准备、缺失块和数值区间切换
期间，preview不改变已提交状态。该语义变化不涉及宿主资源策略。

中间候选rc30 /语义35曾真实构建和安装，其DMI缺失处理出现连带变化。
最终rc31 /语义36显式保留ATR、DMI原有组合策略，因此还保存真实中间版本的
`tests/golden/snapshot_semantics_v35`与`tests/golden/dmi_composition_semantics_v35`，
升级拒绝发生在构造前。中间版本身份保持不变；其4,307项回归不能作为最终版本
验证。组合策略控制样本只证明旧行为保留，不是TradingView DMI官方对齐证据。

最终rc31 /36完整回归4,315项通过，源码和独立wheel各439项定向测试通过；
同版本local/state/replay续算与preview隔离、真实旧34/35拒绝均纳入验证。
本轮官方RMA修复308处差异，不构成完整Pine API、宿主接入或发布资格。


## 2026-10-03 开发计算语义37

DMI分母RMA的首根种子改为严格前收盘真实波幅，公开TR/ATR首根回退不变。
候选rc32 /37拒绝由真实独立安装rc31 /36生成的
`tests/golden/snapshot_semantics_v36`与`tests/golden/dmi_initial_tr_semantics_v36`。
保留原wheel哈希、输入、已提交DI值、state/replay与原始身份，构造前拒绝升级，
权威OHLCV重建。新版本local/state/replay、preview跨越DI/ADX初始化并续算。
该计算变化不涉及宿主策略或资源预算；两组原生完整OHLCV并非缺失场景全集资格。

最终rc32 /37完整回归4,381项通过，源码和真实独立wheel各518项定向测试通过。
真实旧36升级拒绝、同版本local/state/replay续算及preview隔离均纳入最终检查；
收据为`.tmp/tv-alignment-round55-20261003/dmi-origin-qualification.json`。
