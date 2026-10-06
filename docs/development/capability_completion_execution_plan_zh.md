# Pyne Runtime 功能补全与候选发布执行计划

> [!IMPORTANT]
> **状态：历史执行计划。** 本文保留 `0.3.x` 功能补全的设计和验收方法，
> 不再作为当前任务清单；唯一近期里程碑见 [0.4.1 发布收尾](release_0.4.1_zh.md)。
> 本文原范围只面向 `pyne-runtime` 仓库内的 `0.3.x` 功能补全、
> 独立安装和候选发布。具体产品的 bridge、workbench、版本锁和宿主验收由各自的适配
> 仓库负责，不是本仓库的 release gate。当前已经实现的能力、明确边界与证据，始终以
> [Current Project Status](../reference/current_status.md) 和
> [Runtime Capabilities](../api/capabilities.md) 为准；本文负责规定下一步如何选题、
> 实现、验收和停止，不用未来计划覆盖当前事实。

本文把“Pyne 还有哪些功能缺失”转成可以逐步执行的工程手册。执行原则不是追求
Pine API 名称数量，而是优先关闭冻结语料和独立 Runtime 工作流中的阻塞项，并让每一项
新增能力都有可重复的语义、性能、恢复和包级证据。

## 0. 最终目标

本计划完成后，应得到以下结果：

1. 当前 `0.3.x` Runtime 能以候选 wheel 形式通过干净环境独立安装和包级验收。
2. 真实指标/策略语料有固定版本、校验和与机器可读需求报告，不再凭印象选功能。
3. 高频 Batch-only TA 按需求进入 Incremental，并具备 preview、confirmed、snapshot、
   restore、资源限制和性能证据。
4. 外部 Pine 库只按固定 owner/library/version/member 增加适配器，未知成员继续
   fail closed。
5. 新 `request.*` 只有在存在明确数据提供方契约时才进入 Runtime，并同步完成 provider、
   schema、diagnostics 和 capture；具体数据源映射留给适配仓库。
6. 策略层继续定位为 deterministic bar replay；新增 accessor 或订单语义有
   TradingView/golden 证据，不虚构 OHLCV 无法证明的逐 Tick 行为。
7. Pine-to-Pyne 迁移报告可以在执行脚本前准确列出语法改写、宿主需求、外部库、
   Incremental 不支持项和不确定动态调用。
8. 任何能力进入“已支持”列表前，都必须经过源码路径、测试、文档、构建 wheel 和干净
   安装路径五层验收。

## 1. 2026-09-04 执行基线

本计划编写时，本地候选基线为：

| 项目 | 当前状态 |
| --- | --- |
| 源码版本 | `0.3.0rc2` |
| 发布版本 | `0.2.0rc1` |
| Batch TA | 55 个声明能力 |
| Incremental TA | 39 个声明能力 |
| Request capture | 21/21，0 diff |
| Strategy capture | 27/27，0 diff |
| TA capture | 10/10，0 diff |
| 本地全门禁 | 881 tests passed；性能、稳定性、build、Twine、installed-wheel smoke 通过 |

测试数量会增长，后续验收不得把 `881` 写成必须相等的硬编码条件。
正确判据是命令退出码为 0、没有 skipped critical gate，并保存当次实际计数。

本计划的 Phase 1 已把能力计数和公开契约的漂移变成自动门禁。后续切片仍须保持文档、
`runtime_capabilities()` 和真实测试证据同步。

## 2. 边界与非目标

### 2.1 归 Pyne Runtime 负责

- Pine-like Python 语义、series、state、TA、strategy deterministic replay。
- Batch/Incremental 执行、preview/confirmed 隔离和 portable snapshot。
- `request.*` 的参数、对齐、表达式、错误、结果和 provider contract。
- 输入、输出、strategy report、runtime capabilities 和 diagnostics schema。
- 固定外部 Pine 库的 Python adapter。
- 静态 inspect/validate、迁移诊断、资源估算和有界 trace。

### 2.2 归适配仓库负责

- 产品 SDK 映射、版本锁、chart context 和协议转换。
- Runtime 输出到 Host Render IR/chart layer 的显式投影。
- malformed/unsupported output 的 fail-closed 校验。
- 产品自己的兼容层、workbench、安装包和端到端验收。

### 2.3 归具体 Host 负责

- 行情、历史数据、metadata、公司行动、经济/财务数据的数据源。
- 数据库、网络、进程生命周期、容量、重启、分布式协调和权限。
- 参数面板、图表最终渲染、alert 调度、账户和交易执行。
- 不可信脚本的进程、容器或操作系统级隔离。

### 2.4 本计划明确不做

- 不直接解析或执行 `.pine` 源码。
- 不下载或执行任意 Pine library。
- 不把 core package 变成行情/财务数据客户端。
- 不根据 OHLCV 虚构 tick path、订单簿队列、真实部分成交或券商强平。
- 不把 `safe` / `research` 宣称成多租户强沙箱。
- 不在本仓库实现或修改具体产品的 bridge、workbench、release lock 和 Host 业务模块。
- 不为了凑“全量兼容率”实现真实工作负载没有使用的冷门 API。

## 3. 总体执行顺序

阶段必须按以下依赖推进：

```text
Phase 0 保护工作区并冻结基线
   ↓
Phase 1 修复能力真相与文档漂移
   ↓
Phase 2 冻结代表性工作负载并生成需求榜
   ↓
Phase 3 验收当前 0.3 候选的独立安装与包契约
   ↓
Phase 4 按需求补 Incremental TA
   ↓
Phase 5 改善 Pine 迁移与固定外部库
   ↓
Phase 6 条件式扩展 request family
   ↓
Phase 7 条件式扩展 strategy/report
   ↓
Phase 8 条件式补强安全与运行编排
   ↓
Phase 9 候选冻结、全门禁、发布或继续开发决策
```

允许在 Phase 4 内连续完成多个独立 TA 切片，但不得在 Phase 2 的需求榜和 Phase 3 的
独立候选包验收完成前，直接进入大规模 API 扩张。

## 4. 通用工作约定

### 4.1 PowerShell 环境变量

所有命令从 `pyne-runtime` 根目录执行：

```powershell
$PyneRoot = (Resolve-Path '.').Path
$PynePython = Join-Path $PyneRoot '.venv\Scripts\python.exe'
$PyneEvidenceRoot = Join-Path $PyneRoot 'build\capability-completion'

if (-not (Test-Path -LiteralPath $PynePython)) {
    throw "Missing repository virtualenv: $PynePython"
}

New-Item -ItemType Directory -Force -Path $PyneEvidenceRoot | Out-Null
```

`build/` 已被 `.gitignore` 忽略，适合保存本地报告、构建产物和临时验收证据。需要进入
版本控制的结论应人工整理到 `docs/development/`，不要直接提交临时目录。

### 4.2 每个切片的 Git 边界

开始切片前：

```powershell
git status --short --branch
git diff --check
```

执行要求：

1. 记录开始时已经存在的 modified/untracked 文件。
2. 只编辑本切片列出的文件。
3. 不使用 `git add -A`；提交前列出并逐个确认目标文件。
4. 不在功能提交中顺带处理 URL、格式化或其他工作区修改。
5. 不自动 tag、push 或发布；这些是 Phase 9 的独立决定。

每个切片结束前：

```powershell
git diff --check
git diff --stat
git status --short
```

### 4.3 单切片完成定义

一个切片只有同时满足下列条件才算完成：

- public capability/schema 已声明或明确保持不变；
- 正常路径、缺失值、边界值和错误路径有测试；
- Batch/Incremental 相关能力有 parity 测试；
- preview、confirmed、snapshot/restore 相关状态没有串扰；
- 性能复杂度可解释，必要时加入 growth gate；
- 对外文档、API matrix 和 changelog 同步；
- focused tests 通过；
- `scripts/check.ps1` 通过；
- 如果改变 host-facing contract，schema/conformance fixture 已更新，并在变更说明中通知
  适配仓库维护者；适配仓库的实现和验收不在本提交中完成。

## 5. Phase 0：保护工作区并冻结基线

### 5.1 目标

确认后续失败来自新切片，而不是现有脏工作区、环境或过期状态。

### 5.2 执行步骤

1. 保存当前 Git 状态，不修改已有文件：

```powershell
git status --short --branch |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase0-git-status.txt')
git log -12 --date=iso-strict --pretty=format:'%H %ad %s' |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase0-git-log.txt')
```

2. 校验状态页没有生成漂移：

```powershell
& $PynePython scripts\project_status.py --check
```

3. 导出机器可读 runtime capability：

```powershell
& $PynePython -c `
  "import json, pyne_runtime as pn; print(json.dumps(pn.runtime_capabilities(), indent=2, sort_keys=True))" |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase0-runtime-capabilities.json')
```

4. 记录三类 capture 状态：

```powershell
& $PynePython scripts\request_capture_status.py --json |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase0-request-status.json')
& $PynePython scripts\strategy_capture_status.py --json |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase0-strategy-status.json')
& $PynePython scripts\ta_capture_status.py --json |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase0-ta-status.json')
```

5. 跑完整门禁：

```powershell
& .\scripts\check.ps1
if ($LASTEXITCODE -ne 0) {
    throw 'Phase 0 baseline gate failed.'
}
```

### 5.3 验收标准

- `project_status.py --check` 成功。
- Request、Strategy、TA capture 没有 missing、runtime error 或 parity diff。
- 全量 pytest、性能、稳定性、build、Twine、installed-wheel smoke 全部通过。
- 初始脏文件清单已保存，且未被本阶段改写。

### 5.4 停止条件

任一基线门失败时停止新增能力。先将失败归类为：环境问题、已有回归、证据漂移或现有
工作区修改；不得把修复混入第一个功能切片。

## 6. Phase 1：建立单一能力真相并消除文档漂移

### 6.1 目标

让 `runtime_capabilities()` 成为 Batch/Incremental 能力列表的单一机器真相，并让关键
文档从该真相校验，而不是手写数量长期漂移。

### 6.2 代码与文档落点

- `src/pyne_runtime/capabilities.py`
- `docs/api/capabilities.md`
- `docs/concepts/incremental_runtime.md`
- `docs/reference/current_status.md`
- `docs/reference/pine_like_api_matrix.md`
- 新增 `tests/test_runtime_capability_docs.py`

### 6.3 执行步骤

1. 读取 `pn.runtime_capabilities()`，确认 Batch/Incremental TA、request、strategy、drawing、
   external library 和 security 字段。
2. 修正 Incremental 文档中的旧 helper 列表和旧数量。
3. 修正 API matrix 中落后的 TA capture 数量。
4. 新增文档契约测试，至少校验：
   - 当前状态页中的 source version 与 `pyproject.toml` 一致；
   - API matrix 的 Incremental TA 数量与能力契约一致；
   - Incremental 指南不得保留固定的旧列表；
   - external library 的 identifier、成员和 mode 与能力契约一致。
5. 如果完整 helper 列表直接嵌在文档中，优先让测试解析并逐项比较；不要只比较数量。
6. 更新 `CHANGELOG.md` 的 Unreleased 文档修复项。

### 6.4 验收命令

```powershell
& $PynePython -m pytest tests\test_runtime_capability_docs.py `
  tests\test_runtime_capabilities.py `
  tests\test_docs_index.py `
  tests\test_project_status.py -q
& $PynePython scripts\project_status.py --check
& $PynePython -m ruff check .
```

随后运行：

```powershell
& .\scripts\check.ps1
```

### 6.5 提交边界

建议单独提交：

```text
docs: align capability references with runtime contract
```

不得把仓库 URL 迁移、TA 实现或 Host 改动放进该提交。

## 7. Phase 2：冻结代表性工作负载并生成需求榜

### 7.1 目标

把“应该补哪个函数”变成由真实脚本决定的排序问题。没有冻结语料、文件级需求和宿主
场景的功能项，不进入 P0/P1 实现。

### 7.2 输入

需要明确 Pine 语料路径；Pyne 语料默认使用仓库内可发布的 `examples/`：

- `$PineCorpusRoot`：原始 Pine 指标/策略语料，只用于静态审计，不执行、不复制源码。
- `$PyneScriptRoot`：本仓库 `examples/`，用于 `pyne inspect` 和 installed-wheel smoke。
- 如另有已获授权的迁移脚本目录，把它作为额外语料单独冻结；不得把某个产品适配仓库
  设为本仓库的必需输入。

执行者必须把 Pine 占位符换成真实路径：

```powershell
$PineCorpusRoot = (Resolve-Path '<ABSOLUTE-PINE-CORPUS-DIRECTORY>').Path
$PyneScriptRoot = (Resolve-Path (Join-Path $PyneRoot 'examples')).Path

if (-not (Test-Path -LiteralPath $PineCorpusRoot -PathType Container)) {
    throw "Missing Pine corpus: $PineCorpusRoot"
}
if (-not (Test-Path -LiteralPath $PyneScriptRoot -PathType Container)) {
    throw "Missing packaged Pyne examples: $PyneScriptRoot"
}
```

### 7.3 冻结语料身份

```powershell
Get-ChildItem -LiteralPath $PineCorpusRoot -Recurse -File |
    Sort-Object FullName |
    Get-FileHash -Algorithm SHA256 |
    Select-Object Path, Hash |
    ConvertTo-Json -Depth 3 |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase2-pine-corpus-sha256.json')

Get-ChildItem -LiteralPath $PyneScriptRoot -Recurse -File |
    Sort-Object FullName |
    Get-FileHash -Algorithm SHA256 |
    Select-Object Path, Hash |
    ConvertTo-Json -Depth 3 |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase2-pyne-scripts-sha256.json')
```

语料更新必须生成新的 manifest，不允许覆盖旧结论后继续沿用旧需求榜。

### 7.4 生成两份审计报告

```powershell
& $PynePython scripts\pine_corpus_audit.py $PineCorpusRoot `
  --format json `
  --output (Join-Path $PyneEvidenceRoot 'phase2-pine-corpus-report.json')

& $PynePython -m pyne_runtime inspect $PyneScriptRoot `
  --recursive `
  --pattern '*.py' `
  --runtime-mode incremental |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase2-pyne-inspect.json')
```

如果额外授权语料使用 `.pyne` 扩展名，再对该额外目录独立执行一次
`--pattern '*.pyne'`，不要把多个扩展名假设成一个 glob。

### 7.5 建立可跟踪需求表

从报告人工审核后新增：

```text
docs/development/capability_demand_backlog_zh.md
```

每一行至少包含：

| 字段 | 要求 |
| --- | --- |
| capability | 规范化 API，例如 `ctx.ta.linreg` |
| kind | incremental-ta / external-library / request / strategy / host / syntax |
| blocking workload | 被阻塞的代表性脚本或用户流程 |
| files touched | 命中脚本数量 |
| modes | batch / incremental / both |
| owner | runtime / bridge / workbench / host |
| evidence plan | semantic test / TV capture / provider fixture / host probe |
| risk | state / lookahead / performance / schema / host-data |
| decision | implement / document / host-first / reject |

排序使用以下稳定的字典序，不使用伪精确打分：

1. 是否阻塞冻结的代表性用户流程；
2. 命中文件数；
3. 是否是 realtime/Incremental 必需；
4. 宿主依赖是否已经准备好；
5. 是否能建立可信外部或确定性证据；
6. 实现风险和后续维护成本。

### 7.6 验收标准

- 每个 P0/P1 项都有真实文件和工作流证据。
- `host-gap`、`syntax-rewrite`、`external-library` 不再错误归类成 core TA gap。
- 需求榜明确列出 owner 和 evidence plan。
- 语料报告不包含或复制 Pine 源码正文。

### 7.7 停止条件

如果 Pine 语料路径、授权或冻结版本无法确认，Phase 2 标记阻塞；不得凭当前 17 个
Batch-only 名称直接决定全部实现顺序。没有额外产品迁移语料不阻塞独立 Runtime；此时
必须明确写出需求结论只覆盖冻结 Pine 语料和仓库内 packaged examples。

## 8. Phase 3：验收当前 0.3 候选的独立安装与包契约

### 8.1 目标

在添加更多能力前，证明现有 `0.3.0rc2` 能从源码构建为 wheel，并在不暴露仓库
`src/` 的干净 Python 环境中完成 CLI、schema、example 和 import 验收。该阶段的失败
优先作为打包或公开契约缺口修复，而不是用新增 Runtime API 掩盖。

### 8.2 边界

- 只验收 `pyne-runtime` 自己的源码、构建产物和公开包契约。
- 不读取或修改任何产品适配仓库、candidate lock 或 Host 私有模块。
- Host-facing schema/conformance fixture 必须自洽，但具体 adapter 映射不属于本阶段。
- Runtime 候选版本为 `0.3.0rc2`；published version 仍保持 `0.2.0rc1`，直到显式发布。

### 8.3 Source-focused 验收

先运行公开入口、schema、capability、inspect 和 package smoke 的 focused tests：

```powershell
& $PynePython -m pytest `
  tests\test_api.py `
  tests\test_cli.py `
  tests\test_cli_contracts.py `
  tests\test_runtime_capabilities.py `
  tests\test_script_inspection.py `
  tests\test_schema.py `
  tests\test_package_smoke.py -q
if ($LASTEXITCODE -ne 0) {
    throw 'Runtime source-focused package contract acceptance failed.'
}
```

该步骤验证源码真相，不代替下面的 installed-wheel 验收。

### 8.4 候选 wheel 验收

Source-focused 通过后，再保存真实候选 artifacts：

```powershell
$CandidateDist = Join-Path $PyneEvidenceRoot 'phase3-pyne-dist'
New-Item -ItemType Directory -Force -Path $CandidateDist | Out-Null

& $PynePython -m build --no-isolation --outdir $CandidateDist
if ($LASTEXITCODE -ne 0) {
    throw 'Pyne candidate build failed.'
}

$CandidateArtifacts = Get-ChildItem -LiteralPath $CandidateDist -File |
    Where-Object { $_.Extension -in '.whl', '.gz' }
& $PynePython -m twine check @($CandidateArtifacts.FullName)
if ($LASTEXITCODE -ne 0) {
    throw 'Pyne candidate metadata check failed.'
}

Get-FileHash -Algorithm SHA256 -LiteralPath @($CandidateArtifacts.FullName) |
    ConvertTo-Json -Depth 3 |
    Set-Content -Encoding utf8 (Join-Path $PyneEvidenceRoot 'phase3-pyne-artifact-sha256.json')

& $PynePython scripts\package_smoke.py --dist-dir $CandidateDist --offline
if ($LASTEXITCODE -ne 0) {
    throw 'Installed-wheel smoke failed.'
}
```

`package_smoke.py` 必须创建独立 venv、移除继承的 `PYTHONPATH`，并确认
`pyne_runtime.__file__` 位于该 venv 内。这样可以阻止仓库 `src/` 或 editable install
冒充候选 wheel。产品适配仓库如需 pin SHA，应消费这里保存的 artifact identity；本仓库
不修改它的 lock。

### 8.5 必须覆盖的独立包场景

至少形成以下场景矩阵：

| 场景 | 必须证明 |
| --- | --- |
| Import origin | `pyne_runtime` 从新 venv 的 `site-packages` 导入，不来自仓库源码 |
| CLI | `pyne --version`、`pyne schema`、`pyne validate` 和 `pyne inspect` 可执行 |
| Packaged examples | wheel 外的已冻结 examples 可由安装包运行并产生版本化输出 |
| Batch contract | 代表性 indicator/strategy 输出和 schema 与源码测试一致 |
| Incremental contract | seed/preview/confirmed/snapshot/restore 测试通过 |
| Request contract | provider conformance、错误分类和 capture parity 通过 |
| Artifact metadata | wheel/sdist 名称、版本、依赖和 Twine 检查正确 |
| Source isolation | 清除 `PYTHONPATH` 后 smoke 仍通过；错误安装不得回退到源码 |

### 8.6 验收标准

- source-focused、build、Twine 和 installed-wheel smoke 全部通过。
- artifact 文件名、字节数、SHA-256、source commit 和 Python 版本已保存。
- 失败能归因到 Runtime source、packaging、dependency 或 public contract 中唯一 owner。
- 当前候选包独立可用后，才允许把新 P0 API 加入候选。

## 9. Phase 4：按需求补 Incremental TA

### 9.1 当前差集

当前 Batch 已声明但 Incremental 尚未声明的能力为：

```text
cmo
correlation
donchian
falling
keltner
linreg
mom
nz
obv
percentile_linear_interpolation
percentile_nearest_rank
rising
roc
shift
tsi
volume_sma
wpr
```

这 17 项是候选池，不是必须按列表顺序全部实现的 backlog。Phase 2 需求榜决定顺序；
未使用的成员可以明确记录为 `document` 或 `defer`。

### 9.2 建议切片分组

只有需求榜无法区分优先级时，才使用以下默认分组：

1. 简单单值/方向类：`mom`、`roc`、`rising`、`falling`、`nz`、`volume_sma`。
2. 有状态趋势/统计类：`cmo`、`correlation`、`linreg`、`obv`、`wpr`、`tsi`。
3. 多输出/窗口类：`donchian`、`keltner`、两个 percentile。
4. `shift` 单独处理；先冻结正向 bars-back、retention 和 lookahead 边界，不与其他 helper
   合并。

每个提交最多包含一个独立 helper，或一组共享同一状态内核和返回形状的紧密相关 helper。

### 9.3 单个 helper 的标准执行步骤

以下步骤对每个候选重复执行。

#### Step 1：读取 Batch 真相

- 找到 `src/pyne_runtime/ta.py` 或 `utils.py` 的 Batch 实现。
- 找到现有 Batch semantic/golden/performance tests。
- 记录函数签名、默认参数、warm-up、`na`、动态 period、返回 tuple 和异常行为。
- 不直接在 Incremental 中复制向量实现；先写出逐 Bar 状态模型。

#### Step 2：写失败测试

在下列文件中按职责添加测试：

- `tests/test_incremental_ta_demand.py`：目标 helper 的逐 Bar 基本语义。
- `tests/test_incremental_ta_expansion.py`：Batch/Incremental parity 和边界组合。
- `tests/test_incremental_portable_snapshot.py`：replay-v1 restore。
- `tests/test_incremental_state_codec_hardening.py`：typed-state-v2 restore 或 payload 边界。
- `tests/test_runtime_capabilities.py`：能力从 unsupported 变为 supported。
- `tests/test_ta_performance.py` 或 `scripts/performance_smoke.py`：有窗口/排序成本时的增长门。

至少覆盖：

1. 首个可用值之前的 warm-up；
2. 输入含 `na`；
3. preview 重复更新；
4. preview 后 confirmed；
5. 跨多个 confirmed bar；
6. replay-v1 snapshot/restore；
7. typed-state-v2 snapshot/restore；
8. 达到 retention 边界；
9. 非法参数 fail closed；
10. 与 Batch 对照的完整结果。

#### Step 3：实现状态内核

主要落点：

- `src/pyne_runtime/incremental/ta.py`
- 必要时使用现有 rolling state/helper，不新增无界 list。
- 只有 Batch 与 Incremental 真正共享无状态数值核时，才抽到 `ta_kernels.py`。

实现必须：

- 状态大小与 period/retention 有明确上界；
- preview 在 clone 上运行；
- confirmed 才推进持久状态；
- snapshot 中只出现 allowlist 类型；
- 错误使用稳定 `PYNE_*` code，而不是靠异常字符串分类。

#### Step 4：公开并自描述

同步更新：

- `INCREMENTAL_TA_CAPABILITIES`；
- Incremental namespace 装配；
- `pn.inspect_script()` 所需 capability/资源提示；
- API matrix 和 Incremental 文档；
- `CHANGELOG.md`。

#### Step 5：focused 验收

```powershell
& $PynePython -m pytest `
  tests\test_incremental_ta_demand.py `
  tests\test_incremental_ta_expansion.py `
  tests\test_incremental_portable_snapshot.py `
  tests\test_incremental_state_codec_hardening.py `
  tests\test_runtime_capabilities.py -q

& $PynePython scripts\performance_smoke.py --check
& $PynePython scripts\incremental_stability_smoke.py --check
```

#### Step 6：代表性脚本验收

重新运行 Phase 2 的 `pyne inspect` 和目标脚本。验收不是“capability list 多了一个名字”，
而是原先被该 helper 阻塞的冻结脚本可以进入下一阶段，且没有新增 host/syntax gap。

#### Step 7：完整门禁

```powershell
& .\scripts\check.ps1
```

### 9.4 TA capture 决策

满足任一条件时必须新增 TradingView capture：

- warm-up/seeding 容易与 Pine 不同；
- tuple 顺序或锚点确认时机容易不同；
- 动态长度或 `na` 传播不明确；
- 代表性脚本的业务判断依赖精确边界；
- 现有 deterministic test 只能证明自洽，不能证明 Pine parity。

查看当前状态与 diff：

```powershell
& $PynePython scripts\ta_capture_status.py --json
& $PynePython scripts\ta_capture_diff.py --assertion all --summary
```

新 capture 先作为 `reference`，只有 diff 归零且语义结论完成评审后才提升为 `parity`。

### 9.5 Phase 4 完成标准

- 冻结代表性 Incremental 工作负载不再被高优先级 Batch-only TA 阻塞。
- 每个新增 helper 都能自描述、早失败、恢复并通过性能门。
- 仍未实现的 helper 在需求榜中有明确 `defer/reject` 理由。

## 10. Phase 5：Pine 迁移诊断与固定外部库

### 10.1 Phase 5A：文件级迁移报告

目标是让用户知道“这份 Pine 思路为什么不能直接运行、应该改哪里”，而不是实现 Pine
parser/compiler。

执行步骤：

1. 用 `pine_corpus_audit.py` 保留 aggregate feature inventory。
2. 用 `pyne inspect --recursive` 生成每个已迁移脚本的 declaration、mode、TA、request、
   strategy、drawing、library、host data 和 resource requirements。
3. 扩展 Inspector v2，使目录报告对每个文件输出：
   - `supported`；
   - `unsupportedMembers`；
   - `syntaxRewrites`；
   - `hostRequirements`；
   - `externalLibraries`；
   - `dynamicAccessUncertainty`；
   - `estimatedHistory`；
   - `migrationReadiness`。
4. 对 `if series`、Python ternary、`and/or/not`、`:=` 对应状态、裸表达式 request、
   `array.from`、负 history 和 `alert()` 给出稳定 error code、源码位置和 Pyne 写法提示。
5. 不在 report 中回显完整脚本；使用 source hash、路径和紧凑诊断。
6. 只有诊断覆盖稳定后，才评估生成 Python 骨架；骨架不得声称自动语义等价。

主要落点：

- `src/pyne_runtime/inspection.py`
- `src/pyne_runtime/migration_diagnostics.py`
- `src/pyne_runtime/cli.py`
- `tests/test_script_inspection.py`
- `tests/test_cli.py`
- `docs/tutorials/pine_to_pyne_cookbook.md`

验收：

```powershell
& $PynePython -m pytest tests\test_script_inspection.py tests\test_cli.py tests\test_api.py -q
& $PynePython -m pyne_runtime inspect $PyneScriptRoot --recursive --pattern '*.py'
```

### 10.2 Phase 5B：外部 Pine library

当前只允许 `TradingView/ta/10` 的 9 个 Batch 成员。新增成员或库时，一个切片只处理一个
固定 identifier 或一组紧密相关成员。

执行步骤：

1. 从 `capabilityDemand.externalLibraryCandidates` 取最高优先项。
2. 记录完整 `owner/library/version/member` 和命中脚本。
3. 决定：已有 core 等价、需要 adapter、需要 host data，还是拒绝。
4. 在 `pine_libraries.py` 注册固定 allowlist；不接受模糊版本或运行时下载。
5. 为每个成员声明 `dataRequirements`；只有确实需要 lower-TF 的成员才申请该能力。
6. 先实现 Batch；只有真实 realtime 脚本需要时才单独实现 Incremental。
7. 增加 semantic tests、inspect tests、unknown-member fail-closed tests。
8. 对数值边界新增 TradingView capture；先 reference，归零后 parity。
9. 更新 runtime capability、API docs、matrix 和 changelog。

验收：

```powershell
& $PynePython -m pytest `
  tests\test_render_ir_v2.py `
  tests\test_runtime_capabilities.py `
  tests\test_script_inspection.py `
  tests\test_golden_ta.py -q
& $PynePython scripts\ta_capture_diff.py --assertion all --summary
& .\scripts\check.ps1
```

### 10.3 停止条件

- library 没有固定版本；
- 无法确认版权/允许的实现来源；
- 依赖宿主没有的数据；
- 只有 API 名称，没有目标脚本或证据计划；
- 实现需要执行或下载任意 Pine 源码。

## 11. Phase 6：条件式扩展 `request.*`

### 11.1 启动条件

只有同时满足以下条件，某个新 request family 才能启动：

1. Phase 2 证明真实工作流需要它；
2. 已有明确的数据提供方需求，且适配仓库愿意实现对应数据源；
3. 能定义 provider capability、请求坐标、返回形状和错误类别；
4. 有合法稳定的 reference/golden 数据；
5. 不要求 core 直接联网。

候选包括：

```text
request.currency_rate
request.financial
request.economic
request.dividends
request.splits
request.earnings
generic request.data
```

建议先做宿主最容易提供、时间对齐语义最明确的一类。`generic request.data` 最后评估，
避免过早形成无法约束的万能接口。

### 11.2 单 request family 执行步骤

1. 写一页 contract decision：输入坐标、时间单位、时区、修订值、缺失值、重复值、排序、
   缓存和 ignore 行为。
2. 扩展 `DataProvider` 或新增窄协议；不得用一个无类型 `dict` 吞掉所有 family。
3. 更新 provider capability schema 和 conformance kit。
4. 在 Runtime 实现确定性 alignment，不让 provider 决定 lookahead/gaps 语义。
5. 定义 typed exception category 和 `errorDetail.requestProviderRequest`。
6. 更新 `runtime_capabilities()` 和 `inspect_script()` 的 host requirements。
7. 增加 Batch tests；有 realtime 需求时再实现 Incremental callback/cache/snapshot 行为。
8. 新增 reference capture 或独立的权威 fixture。
9. 发布 host-facing contract 变更说明，供独立适配仓库实现数据 broker 映射。
10. 跑 Runtime full gate；适配仓库验收作为其自己的采用条件，不阻塞本仓库开发提交。

主要落点：

- `src/pyne_runtime/request/provider.py`
- `src/pyne_runtime/request/module.py`
- `src/pyne_runtime/request/errors.py`
- `src/pyne_runtime/request/conformance.py`
- `src/pyne_runtime/schema.py`
- `src/pyne_runtime/capabilities.py`
- `src/pyne_runtime/inspection.py`
- `tests/test_request_provider_conformance.py`
- `tests/test_request_errors.py`
- `tests/test_request_security.py`
- `tests/` 内的 provider conformance/golden fixtures

### 11.3 验收命令

```powershell
& $PynePython -m pytest `
  tests\test_request_provider_typing.py `
  tests\test_request_provider_conformance.py `
  tests\test_request_errors.py `
  tests\test_request_security.py `
  tests\test_incremental_request.py `
  tests\test_schema.py `
  tests\test_runtime_capabilities.py `
  tests\test_script_inspection.py -q

& $PynePython scripts\request_capture_diff.py --assertion all --summary
& .\scripts\check.ps1
```

### 11.4 明确不补的项

- nested request 默认继续 unsupported；只有能证明递归深度、缓存、错误归属和资源预算后
  才单独立项。
- direct capture of an already evaluated Python expression 不可能自然获得 requested context；
  继续使用 `lambda ctx: ...`，不增加会产生错误语义的便利 API。

## 12. Phase 7：条件式扩展 strategy/report

### 12.1 启动条件

新 strategy 工作只能来自以下证据之一：

- 冻结代表性策略无法表达；
- 缺少高频 `closedtrades.*` / `opentrades.*` accessor；
- Batch/Incremental 对同一已承诺语义不一致；
- 新 TradingView capture 证明现有 fill/report 语义错误；
- Host 的 strategy-provider contract 缺少必要但可确定表达的字段。

### 12.2 单 strategy 切片步骤

1. 新增最小 Pine-equivalent fixture 或扩展现有 fixture。
2. 运行 scaffold，确保存在 external capture contract：

```powershell
& $PynePython scripts\strategy_capture_scaffold.py --check
```

3. 导入外部证据前，先将 assertion 保持为 `reference`。
4. 用 summary 定位差异：

```powershell
& $PynePython scripts\strategy_capture_diff.py --assertion all --summary
```

5. 一次只修改 accessor、fill、cost、risk、lot 或 lifecycle 中一个语义域。
6. 同时验证 long/short、reversal、partial close、commission allocation 和 missing trade
   访问的回归面。
7. 如果 Incremental 受影响，验证 preview 不持久化，confirmed 才更新 ledger。
8. diff 归零、语义评审完成后，才将 fixture 提升为 `parity`。
9. 更新 strategy report/schema 时执行 schema migration 规则；破坏性变化必须新版本。

主要落点：

- `src/pyne_runtime/strategy/`
- `src/pyne_runtime/incremental/strategy.py`
- `src/pyne_runtime/schema.py`
- `tests/test_strategy_runtime.py`
- `tests/test_strategy_shared_helpers.py`
- `tests/test_golden_strategy.py`
- `tests/test_incremental.py`

验收：

```powershell
& $PynePython -m pytest `
  tests\test_strategy_runtime.py `
  tests\test_strategy_shared_helpers.py `
  tests\test_golden_strategy.py `
  tests\test_incremental.py `
  tests\test_strategy_performance.py -q

& $PynePython scripts\strategy_capture_diff.py --assertion parity --summary
& .\scripts\check.ps1
```

### 12.3 永久边界

以下能力不得仅凭 OHLCV 加入当前 strategy replay：

- 真实 tick 顺序；
- order-book queue position；
- 无输入证据的 partial fill；
- broker margin call / forced liquidation；
- 利息、借券、结算和交易所私有撮合规则。

如果产品确实需要，应建立独立的 trade-tape/order-book simulation kernel，并把可用输入、
确定性、校准和不确定性写成新合同；不要让 `pyne-runtime` 静默猜测。

## 13. Phase 8：条件式安全与运行编排

### 13.1 不可信脚本

`safe` / `research` 是语言和执行策略限制，不是多租户强沙箱。只有产品允许非信任用户
上传脚本时，才启动该工作流：

1. 保持 Pyne 内的 import/builtin/resource/timeout fail-closed 门。
2. 由调用方或独立适配层提供进程身份、文件系统、网络和系统调用边界。
3. 明确 CPU、内存、进程数、磁盘、网络和 wall-clock 配额。
4. 复用 Host attack matrix，验证超时后进程终止和干净重启。
5. 不在文档或 UI 中把 Python 级 restriction 描述为 sandbox。

### 13.2 分布式会话

当前 manager 是进程内 TTL/LRU；portable snapshot 可以跨进程，但不携带 provider，也不
替代分布式协调。如果产品需要多实例或容灾：

1. Host 定义 session key、generation、lease 和 fencing token。
2. snapshot 存储、加密、TTL 和一致性由 Host 负责。
3. restore 必须重新注入兼容 provider/settings。
4. stale generation 的 preview/confirmed 事件必须被拒绝。
5. 不把 Redis/数据库客户端引入 `pyne-runtime` core。

### 13.3 启动条件

没有明确威胁模型或多实例部署需求时，本阶段保持 deferred，避免增加无意义门槛。

## 14. Phase 9：候选冻结与最终验收

### 14.1 冻结条件

- Phase 2 的 P0 阻塞项全部为 implemented、external-owner 或明确 reject。
- 代表性 Batch、Incremental、request、strategy 和 renderer 场景全部通过。
- 没有未分类的 unsupported runtime error。
- 没有使用旧 source tree 冒充 installed wheel 的测试。

### 14.2 Runtime 全门禁

```powershell
& .\scripts\check.ps1
if ($LASTEXITCODE -ne 0) {
    throw 'Final Pyne Runtime gate failed.'
}
```

必须保存：

- commit SHA；
- source version 和 published version；
- runtime capabilities JSON；
- capture counts/diffs；
- pytest count；
- performance/stability raw summary；
- wheel/sdist filename、size、SHA-256；
- installed-wheel CLI/schema/example smoke。

### 14.3 干净安装复验

从冻结 commit 重新构建候选 artifact，并重复 Phase 3 的 installed-wheel smoke。最终报告
必须明确：

- wheel/sdist 的文件名、字节数和 SHA-256；
- wheel 内版本、依赖和包文件清单；
- `pyne_runtime.__file__` 确实位于临时 venv，不来自仓库 `src/`；
- CLI version/schema/validate/inspect 和 packaged-example smoke 结果；
- source 与 installed wheel 的 `runtime_capabilities()` / schema identity 一致；
- 不兼容版本和损坏 artifact 能 fail closed。

具体产品的 adapter、lock、UI、data broker 和端到端路径由独立适配仓库复验，不写入本
仓库的完成条件。

### 14.4 远端 CI

候选分支推送后，必须通过 Linux、Windows、macOS × Python 3.11、3.12、3.13，以及 build
job。远端 CI 未通过时，本地候选只能称为 locally accepted，不能称为 release-ready。

### 14.5 发布决策

只有用户明确批准后才执行 tag/release。发布前：

1. 确认候选提交已进入 `main`。
2. 确认 `pyproject.toml`、`CHANGELOG.md`、status 和 docs 同步。
3. 按 `release.yml` 的 tag/version 规则生成 wheel、sdist、SHA256SUMS 和 notes。
4. RC 保持 prerelease；不得自动提升 stable。
5. 发布后通过公开 HTTPS URL 再做 install/import/version/schema smoke。

### 14.6 回滚

- 保留已发布 `0.2.0rc1` artifact，不覆盖旧 tag 或 Release asset。
- 候选失败时撤销候选提交或继续保持 unpublished，不修改外部适配仓库的 lock。
- Runtime schema/version 不兼容必须 fail closed，不做猜测性降级。
- 回滚演练和发布演练分开记录。

## 15. 每个切片的执行记录模板

每次实现复制以下模板到 issue、任务说明或执行记录：

```markdown
## Slice: <capability>

- Owner: runtime / packaging / external-adapter
- Workload blocked: <script or user flow>
- Baseline commit: <sha>
- Corpus manifest: <sha256 report>
- Current behavior: <supported / unsupported / wrong>
- Target behavior: <precise semantic contract>
- Non-goals: <explicit exclusions>
- Files allowed to change: <list>
- Evidence required: <tests/capture/installed-wheel probe>
- Performance risk: <none/window/sort/memory/provider>
- Schema impact: <none/additive/breaking>
- Rollback: <revert or keep candidate unpublished>

### Red test
<command and observed failure>

### Implementation
<short design>

### Focused validation
<commands and results>

### Full validation
<scripts/check result>

### Adapter impact
<host-facing contract change notice or not applicable; implementation stays out of repo>

### Decision
implemented / deferred / rejected / host-blocked
```

## 16. 全局停止条件

出现任一情况时停止当前切片并回到设计/证据阶段：

- 需要改变 public schema 但没有 migration/version 方案；
- 无法区分 Runtime 与外部适配层 owner；
- 只有函数名，没有可验证语义；
- 需要未知或未授权数据源；
- Pine/TradingView 结果无法合法、稳定地获取或重放；
- 性能从有界状态变成随全历史无界增长；
- preview 状态污染 confirmed session；
- snapshot/restore 不能保持等价或需要序列化任意 Python 类型；
- 新功能迫使 core 联网或导入具体产品的私有模块；
- 为通过测试而放宽 fail-closed 校验；
- 工作区出现无法归属的新修改。

## 17. 推荐的前四个实际切片

在没有新的产品优先级输入时，按以下顺序开始：

1. **能力文档真相切片**：修正 39-helper/10-capture 漂移并增加自动测试。
2. **代表性工作负载切片**：冻结 Pine/Pyne 语料并提交经审核的需求榜。
3. **当前候选包验收切片**：保存 build/Twine/installed-wheel/capability identity 证据，
   不读取或修改任何产品适配仓库。
4. **第一个 Incremental TA 切片**：从需求榜最高项中选择一个 helper，按 Phase 4 完成
   red test、实现、restore、performance、docs、full gate 和 packaged-script 验收。

完成这四步后再重新排序后续工作。若代表性脚本已经全部可运行，不应为了清空 17 项差集
继续机械扩张；应转向迁移体验、独立包可用性和候选发布闭环。

## 18. 计划完成判定

本计划不是要求实现“全部 Pine”。满足以下条件即可宣告本轮功能补全完成：

- 冻结代表性工作负载全部进入 supported、documented rewrite 或明确 host-owned 状态；
- 没有未解释的 core/runtime gap；
- P0 Incremental workload 有 batch parity、preview isolation 和 restore 证据；
- 需要的外部库和 request family 均有固定契约，未需要的保持 fail closed；
- strategy 没有超出输入证据的虚构行为；
- candidate wheel 在无仓库源码路径的干净环境中通过独立安装与包契约验收；
- full local gate 和 remote matrix CI 通过；
- remaining gaps 在 API matrix 和需求榜中可见，而不是运行时才暴露。

达到这些条件后，下一步应是发布/采用决策，而不是继续无边界地扩大 API 数量。
