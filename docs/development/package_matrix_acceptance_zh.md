# 同一安装包的跨平台验收

2026-09-09，基线 `3e0c5fd`。Grok 在独立工作树
`codex/stable-package-matrix` 修改 CI/release 工作流和相关文档；维护者审阅四个文件
的 diff、构建/安装原始日志后整合，补充 changelog 并明确发布任务名称。
运行时源码、包版本和快照语义未修改。

CI 构建一次 wheel/sdist，上传命名制品 `pyne-runtime-dist`；三个系统乘三个 Python
版本的九个任务下载并安装这一制品。原有源码测试矩阵保持独立。标签工作流采用相同
结构，发布任务依赖全部安装任务，下载被验收的同一制品；不重新构建后发布。

传输使用官方文档的 [upload-artifact v7](https://github.com/actions/upload-artifact)
和 [download-artifact v8](https://github.com/actions/download-artifact)，2026-09-09
经维护者联网核对。现有 checkout/setup-python 版本不变。

## 本地证据

- Windows CPython 3.12.7，在独立工作树执行 isolated build、Twine、在线独立 venv
  安装 smoke，全部退出 0。安装检查包含 wheel import 路径、类型标记、CLI、schema、
  inspect 和示例执行。未使用源码安装冒充 wheel 验证。
- 维护者读取 Grok session `01a08455-6e40-78e2-9c73-d5b78e138efb` 的终端原始输出，
  确认 20 项现有 package/release contract 测试通过；整合后再次运行同样两个文件，
  20 passed（0.45s）。
- 本地制品 `pyne_runtime-0.3.0rc2-py3-none-any.whl`，241463 bytes，SHA-256
  `a21fba95becd812447520a04da01b285dbcbd87df59d109a02b6ebcda89fc74d`。
  它属于本切片工作树构建，不是最终发行提交的安装包。

原始本机证据保存在独立工作树 `build/stable-delivery/` 的
`package-matrix-report.md`、`local-windows-validation.log` 和 `dist/`，以及上述 Grok
会话终端日志。该工作树不包含主线后续新增测试/文档。

## 尚未验证

没有推送、触发远端 CI 或发布。九平台制品传输/安装、标签工作流与最终发行提交
完整门禁均未运行。通过本地检查证明配置与本地包路径可用，不证明全部平台已通过。
远端执行及最终制品校验属于发行候选验收。
