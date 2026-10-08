# 环境监测与执法辅助平台

React 中文监管工作台与 FastAPI 业务平台。北京公开空气监测数据、可追溯的模型实验、企业线索与整改核查共用一套真实 API。生产入口统一为 `/api/v2`。原始观测数据和历史制品保留；SQLite 旧应用和 `legacy_algorithms` 已从运行树移除。

## 启动

需要 Docker Compose。容器使用 Python 3.12、Node 24、PostgreSQL 16 和 Redis 7；宿主机只需 Python 运行初始化脚本。

```powershell
python scripts/configure_platform.py
docker compose -f compose.platform.yml up -d --build
docker compose -f compose.platform.yml exec api python -m app.cli create-admin --username admin
```

打开 [工作台](http://localhost:8080)。初始化命令交互读取口令，不提供固定管理员密码；首次登录必须改密。空数据库没有示例图表或虚构企业。导入、采集、训练和导出通过持久化后台任务执行。

```powershell
docker compose -f compose.platform.yml exec api python -m app.cli collect --backfill-months 24
```

页面显示最新观测日期、入库时间和数据延迟。公开源持续存储与业务使用许可须在正式上线前核实；生产模式在许可未确认时停止在线采集。

## 工作区

工作台、监测分析、站点详情、标准评价、趋势预测、线索中心、核查与整改、企业档案、模型中心、报告与下载、系统管理。

四类角色分别为管理员、监管主管、执法人员、研究者。核查流程包含线索认领、分派、现场事实、证据版本、整改期限、复查、主管审核、退回和重新开启。研究者不能读取企业证据，执法人员不能处理未授权任务。

不建设完整行政处罚办理、电子签章或正式送达；空气异常不能自动归责企业，旧罚款估算不进入新版流程。

## 文档

- [操作与开发入门](QUICKSTART.md)
- [部署、升级与备份恢复](DEPLOYMENT.md)
- [架构和接口约定](docs/architecture.md)
- [数据口径、标准及模型差异](docs/data-and-models.md)
- [迁移与验收记录](docs/acceptance.md)
- [重构与目录约定](docs/refactor.md)

## 验证

集成测试只使用真实 PostgreSQL 的隔离 schema，不访问在线来源。真实模型验证与轻量算法测试分开。

```powershell
docker compose -f compose.platform.yml -f compose.dev.yml run --rm --no-deps -v ./platform_tests:/workspace/platform_tests:ro api python -m unittest discover -s platform_tests -v
docker build -f Dockerfile.backend-tests -t environmental-platform-backend-tests:local .
docker run --rm -v "${PWD}:/workspace" -w /workspace environmental-platform-backend-tests:local
cd frontend
npm ci
npm test
npm run build
npm run test:e2e
```

前端开发使用 Node 24。浏览器验收需要先启动 `compose.acceptance.yml` 的隔离服务，详见部署文档。七天在线稳定运行属于部署后的验收，不以自动化测试通过代替。
