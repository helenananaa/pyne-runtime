# 0.3.0 正式发行验收

日期：2026-09-09。完整本地门禁对应代码提交
`eabb9a2a8489590f24439374fe049bf789e38c4f`，版本 0.3.0，计算语义 3。

**结论：声明范围内的独立稳定包已正式交付。** 用户明确授权后，
[PR #3](https://github.com/helenananaa/pyne-runtime/pull/3) 已保留历史合并，
`v0.3.0` 指向 `8379d6bf05f7d1abe04d2c61ff0b786878cd875a`；
[正式 Release](https://github.com/helenananaa/pyne-runtime/releases/tag/v0.3.0)
于 2026-09-09 10:28:03 UTC 发布，非草稿、非预发行。公开资产已下载核验。

## 对目标逐项核对

| 项目 | 当前证据 | 判断 |
| --- | --- | --- |
| A 支持范围与升级政策 | compatibility、schema migrations、session recovery，包与计算身份分离 | 已冻结 |
| U1 指标迁移与语义 | 真实 ADX/DI 的 80 根输入/外部日志、前缀比较及原 TA 捕获 | 本地通过 |
| U2 多周期与失败恢复 | 完整请求负载、未来输入隔离、provider 故障/恢复与旧绘图点保留 | 本地通过 |
| U3 状态/绘图实时更新 | 独立状态/事件预期，重复 preview、retention、恢复 | 本地通过 |
| U4 持续策略 | OCA 外部捕获、成本独立算术、循环交易长测 | 本地通过 |
| U5 重启/升级 | 新进程恢复、真实语义 2 快照拒绝、语义 3 延续、OHLCV 重建 | 本地通过 |
| U6 诊断/安装 | 初译失败→建议→修正成功；已安装 wheel 执行五类代表性流程 | 本地通过 |
| C 容量 | 1/4/8 会话各 4096 根；266240 原始事件归档并独立复算；另有语义 3 功能冒烟 | 固定负载范围通过，不是任意脚本 SLA |
| D 真实迁移体验 | ADX/DI 递推、参数、阈值保留与显式 renderer 差异；Inspector 建议不强制阻塞 | 本地通过 |
| E 正式发行 | PR/main 的 19 项检查通过；发布流程 11 项通过；公开资产校验和及下载 wheel 安装通过 | 已完成 |

## 实际执行的检查

- Windows CPython 3.12.7 / NumPy 2.4.6：完整门禁退出 0，1164 passed。
- Ubuntu-22.04 WSL 的 Linux 原生目录，CPython 3.12.13 / NumPy 2.5.3：
  同一提交的完整门禁退出 0，1164 passed。
- Linux 独立 NumPy 1.26.0 环境：1164 passed，覆盖声明的 NumPy 最低版本。
- 同一候选 wheel 在 Windows 3.12、Windows 3.13.9、Linux 3.12、Linux 3.12 +
  NumPy 1.26.0 中完成安装验收：每次五类流程、5074 个比较点，语义身份均为 3。
- 构建、Twine、版本/日期校验和 SHA256SUMS 生成通过。旧 Linux WMA 与离线依赖
  失败及修复证据单独保留，没有放宽预算或覆盖旧捕获。
- 两个平台完整门禁都保留一个既有的大模块架构提示，不存在失败测试。

候选 wheel 名称为 `pyne_runtime-0.3.0-py3-none-any.whl`，本地已验证字节的 SHA-256：
`fd40aa1aa6389efb1c0bbdac2c2608b36bc3464f433a96a610446336cc18febc`。
候选工作树 `build/release-0.3.0/` 保留制品、release notes、candidate-manifest.json；
主工作树 `build/stable-delivery/` 保留完整本地日志。后续正式发布只接受其自身发布
工作流实际验证的制品，不假设另一次构建的哈希相同。

## 远端与公开制品验收

- [PR CI](https://github.com/helenananaa/pyne-runtime/actions/runs/34339410311)：
  19/19 成功。Windows/Linux/macOS × Python 3.11/3.12/3.13 各自 1164 passed，
  九组合独立安装同一构建 wheel，各完成五类流程、5074 个比较点、语义身份 3。
- [合并后 CI](https://github.com/helenananaa/pyne-runtime/actions/runs/34339718707)：
  最终 19/19 成功。macOS Python 3.11 首次滚动顺序统计增长比为 3.360，
  超过 3.250；同代码 PR 为 2.176。仅重跑失败环境，结果为 2.213；
  未修改代码、阈值或 runner 配置。此结果与机器计时波动一致，但单次重跑不能
  证明所有性能波动的根因；保留首次失败与重跑证据，不声称首次全绿。
- [Release 工作流](https://github.com/helenananaa/pyne-runtime/actions/runs/34340235873)：
  11/11 成功，包含一次构建、九组合安装及一次发布，发布使用经过验证的同一制品。
- 三个公开资产下载后，大小、GitHub digest 与 SHA256SUMS 均一致。
  下载的 wheel 又在本机 Windows Python 3.12 临时环境通过五类流程、5074 个比较点。

| 公开资产 | 字节数 | SHA-256 |
| --- | ---: | --- |
| pyne_runtime-0.3.0-py3-none-any.whl | 240074 | `36f2ba901154c6907f3e18768f9df379d1b7b8ba4fbc5abc34f9eebc346f8189` |
| pyne_runtime-0.3.0.tar.gz | 3747305 | `828a36ce07ee8001fbf5dc3fcddc6e13d6e08788535599d68fe694d261347039` |
| SHA256SUMS | 194 | `09098ab409a3750edafa122badcb66975817ed0b29fd59bf0a89dad91cee8837` |

可追溯机器记录见 [正式发行清单](evidence/release_0.3.0_20260909.json)。
完整下载日志及 CI 回执保存在本地主工作树 `build/stable-delivery/`。
上述公开 wheel 是 Linux 发布工作流构建，不能与前述 Windows 本地候选字节混为一谈。
发布后同步 `published-version`、README 安装链接和当前状态；标签与已发布制品保持不变。

## 保留边界

完整 Pine 源码解释、任意脚本 SLA、恶意多租户隔离和宿主行情/图表/交易集成不在本次
独立包交付范围。长期容量记录属于其原始测量提交和固定负载，不重标为任意生产保证。
源码门禁保留一个既有的大模块架构提示，后续维护可继续拆分，但没有失败测试。

## 发布后计时门禁维护

[发布记录 PR #4](https://github.com/helenananaa/pyne-runtime/pull/4) 的首次 CI
在 macOS Python 3.11 测得 WMA 增长 3.365（上限 3.000）；不改代码重跑后仍为
3.289，另有恢复增长 3.630（上限 3.500）。因此停止继续重跑取绿，保留两次失败。
WMA/顺序统计原先先测全部小负载，再测全部大负载；发布后维护改为已有的交错配对
计时方法，默认重复从 3 次增加到 9 次，并在 CI 输出 JSON 原始配对样本。
原负载规模、所有性能上限和运行时代码保持不变，另用合成时钟验证共同变慢时仍能
检出 4 倍增长回归。该维护不改写 v0.3.0 标签、公开制品或其历史验收。
托管性能验收的稳定性仍以新 CI 的实际结果为准，不能仅凭计时方法改动宣称解决。
