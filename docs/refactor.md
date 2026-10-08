# 渐进式重构指南

平台采用模块化单体和垂直业务切片。公开接口只使用 `/api/v2`。SQLite 旧应用、`/api/v1` 和 `legacy_algorithms` 已从运行树移除。

## 后端边界

`app/v2/domains/*` 是领域入口，统一遵循：

```text
router -> application service -> repository / adapter -> database or external system
```

路由负责参数校验、权限依赖和响应映射；服务层不依赖 FastAPI 或 ORM 实现；仓储负责持久化。共享事务、分页、HTTP 错误、日志脱敏、UTC 时间、审计、权限上下文、存储和任务契约位于 `app/v2/shared`。

领域切片包括 `auth`、`monitoring`、`collection`、`enforcement`、`jobs`、`ml` 和 `admin`。`app/v2/models.py` 保留为兼容门面，内部委托到领域服务。

## 任务和数据管道

`app/v2/shared/job_contracts.py` 定义 `JobKind`、`JobSpec`、`JobState`、`JobProgress`、`JobResult` 和 `ArtifactRef`。采集、导入、评价、训练、插补、预测和导出都通过统一任务生命周期提交、更新和登记制品。制品和来源哈希要求为小写 64 位 SHA-256；原始来源文件不可变，派生结果不会覆盖观测数据。

## 前端边界

`frontend/src/domains/*` 按业务域组织页面和 hooks；`frontend/src/shared` 负责 API transport、React Query、分页、错误、权限、布局和状态组件。页面不直接调用底层 `fetch` 或拼接请求。OpenAPI 生成类型由 `frontend/openapi.json` 作为快照输入。

## 数据库和部署

首期保留现有表名和字段含义。增量结构变更使用 Alembic；`v2_0004` 增加任务进度字段，`v2_0005` 增加幂等、心跳、模型状态和采集证据索引。主栈和验收栈继续使用 PostgreSQL、Redis、Celery、scheduler、API 和前端容器。

## 当前验证快照（2026-10-03）

- 后端完整回归：239 passed，0 skipped；CJK 导出集成和属性测试、采集覆盖门禁、备份/许可门禁、JobKind 契约、用户提示编码、API 代理动态解析和只读验收执行器检查均在 Linux 容器中实际执行。
- 重构契约、领域模型和 Schema：33 passed；前端依赖边界 smoke：4 passed。
- Docker 平台验收：25/25 passed；主 API、验收 API、主 Web 和验收 Web 均返回 HTTP 200，并验证生产采集授权保护。
- 前端 Vitest：5/5 passed；TypeScript/Vite production build passed；Playwright 桌面和 tablet：8/8 passed。
- 运行时 OpenAPI 与 `frontend/openapi.json` 对全部 55 条路径及其 schema、参数和响应做完整对象相等校验。
- 部署、备份恢复、真实 Celery worker 恢复和模型管道均有 `.artifacts/` 证据。
- 62 个保留 CSV 已完成真实模型验证；seasonal 和 interpolation 通过发布门禁，LightGBM、SAITS、BRITS 因基线门禁未通过而保持未激活。

## 生产签署条件

当前替换窗口从 `2026-10-01T14:00:00+00:00` 开始，最早可在 `2026-10-08T14:00:00+00:00` 审核。在线报告仍显示七天窗口未完成、采集覆盖率未通过，且 Quotsoft 连续使用许可尚未确认。不得用测试数据、时间跳跃或环境变量伪造这些门禁。

在线报告位于 `.artifacts/online-acceptance-current-window.json`，操作步骤见 [`docs/online-acceptance-runbook.md`](online-acceptance-runbook.md)。
