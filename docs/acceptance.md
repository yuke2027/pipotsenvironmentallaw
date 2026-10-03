# 重构验收记录

本记录只引用当前工作区和 Docker 验证产物。生产签署所需的自然时间窗口与许可证确认单独列出，不以一次测试运行代替。

## 已完成并有证据的检查

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 后端完整回归 | 通过 | Docker test image：239 passed，0 skipped；包含 Linux CJK 导出、采集覆盖门禁、备份/许可门禁、JobKind 契约、编码伪影和只读验收执行器检查 |
| 重构契约和领域模型 Schema | 通过 | 33 passed；包含服务、路由依赖方向、用户提示编码和表结构兼容性 |
| Docker 平台验收 | 通过 | `platform_tests`：25/25 passed；包含生产采集授权保护 |
| 前端单元测试 | 通过 | Vitest：5/5 passed |
| 前端构建 | 通过 | TypeScript/Vite production build |
| 浏览器验收 | 通过 | Playwright 桌面和 tablet：8/8 passed |
| OpenAPI 兼容 | 通过 | 运行时 OpenAPI 与 `frontend/openapi.json` 完整对象相等 |
| 空库部署和恢复 | 通过 | [deployment-validation.json](../.artifacts/deployment-validation.json) |
| Worker 恢复和幂等 | 通过 | [worker-recovery.json](../.artifacts/worker-recovery.json) |
| 模型制品管道 | 通过 | [model-pipeline.json](../.artifacts/model-pipeline.json) |
| 真实模型验证 | 部分通过 | [model-validation/report.json](../.artifacts/model-validation/report.json)；seasonal、interpolation 已通过，其他候选保持未激活 |
| 性能基线 | 通过 | 10M 行隔离 PostgreSQL：list P95 657.01ms，dashboard P95 686.15ms |

## 数据和追溯

原始观测、来源文件和源 SHA-256 保持不可变；采集和导出任务将来源哈希写入任务结果。模型、预测、插补和导出文件通过 `ArtifactRef` 登记，备份恢复会重新校验文件和制品引用。

## 仍需完成的生产前条件

- 七天在线采集窗口仍在进行，必须每日记录任务状态、重试、缺失文件、源文件修订、通知和备份证据；正式签署还要求 `backup_gate_passed=true`。
- 当前窗口最早审核时间为 `2026-10-08T14:00:00+00:00`。
- Quotsoft 连续存储和业务使用许可仍需由部署方书面确认，并保存符合 runbook 格式的审计记录；确认文件有效且 `ESP_SOURCE_LICENSE_CONFIRMED=true` 后，许可门禁才会通过。
- GPU 配置、概率预测校准和目标生产规模的恢复演练仍需在目标环境复核。

最新只读报告：[online-acceptance-current-window.json](../.artifacts/online-acceptance-current-window.json)。操作流程见 [`online-acceptance-runbook.md`](online-acceptance-runbook.md)。

## 部署边界

当前部署保持单组 Compose 拓扑。行政处罚办理、电子签章、正式送达和自动归责不属于首期平台流程；生产入口必须通过受控 HTTPS 反向代理，数据库、原始文件、附件和模型制品必须一起备份。
