# 部署升级与恢复

平台按单组织部署。`compose.platform.yml` 分别运行 PostgreSQL、Redis、迁移进程、API、普通 Worker、模型 Worker、调度器和 Nginx。默认 `docker-compose.yml` 引用这套配置。

## 初始化与配置

运行 `python scripts/configure_platform.py` 创建随机 `.env`；已有配置不会被覆盖。不要提交 `.env`。`POSTGRES_PASSWORD` 和 `ESP_SECRET_KEY` 必须长期保存，数据库、原始文件和附件位于持久化命名卷。

开发地址为 `http://localhost:8080`，API 就绪探针为 `http://localhost:58000/health/ready`。仅监听本机端口。生产通过受控的 HTTPS 反向代理入口访问，设置 `ESP_PUBLIC_ORIGIN` 为准确的公开 Origin、`ESP_ENVIRONMENT=production`、`ESP_COOKIE_SECURE=true`。TLS 在部署网关终止；不要直接把开发 HTTP 端口发布到公网。

在线来源许可确认后设置 `ESP_SOURCE_LICENSE_CONFIRMED=true`，保存许可确认依据。定时任务按北京时间每日 03:30 重查前七天。03:30 前重启不会提前触发当天计划。

```powershell
docker compose -f compose.platform.yml up -d --build
docker compose -f compose.platform.yml exec api python -m app.cli create-admin --username admin
docker compose -f compose.platform.yml logs --tail 100 api worker scheduler
```

普通任务和模型任务分队列。训练并发固定为 1。专用 CPU 模型配置为 `compose.models.yml`；CUDA 配置为 `compose.gpu.yml`，需要 NVIDIA 容器支持。GPU 配置不等于 GPU 已完成验收，CPU 验证见验收记录。API 镜像不安装 TensorFlow、PyTorch 或 PyPOTS；平台镜像包含 WQY/Noto CJK 字体，保证 Linux PDF 和图表导出可重复渲染。

## 导入旧资产

资产清单 `docs/legacy-inventory.json` 包含旧文件 SHA-256 和基线提交。CSV 明确挂载后通过真实任务导入，不依赖启动目录：

```powershell
docker compose -f compose.platform.yml run --rm -v ./data1:/imports:ro api python -m app.cli import-folder /imports
```

原始内容按日文件逻辑键和哈希去重；修订保留所有原始版本。旧 SQLite、旧 LSTM 和结果目录不自动删除，也不当成新平台已审核的业务档案。当前不存在自动迁移旧 JWT 会话的兼容层，账号通过新版初始化与管理建立。

## 备份与恢复演练

数据库和附件必须一起备份。文件为不可变内容寻址制品，脚本先做 PostgreSQL 一致性转储，再归集全部引用文件、模型权重和数据快照。

```powershell
python scripts/backup_platform.py backup .artifacts/backups/20261002
python scripts/backup_platform.py verify-restore .artifacts/backups/20261002
```

`verify-restore` 只创建新的 `platform_restore_*` 数据库和 `restored-files-*` 目录，绝不覆盖运行库。它重新导入数据库、解包文件、逐项验证 SHA-256，并确认恢复库引用的源文件、证据和模型均存在。恢复演练目录与数据库保留供核验，可由运维按名称清理。

真实灾备切换时先停止本平台写入及调度，验证备份，在新卷或目录中恢复文件，将数据库连接与存储根切换到已核验目标，再启动 API、Worker、调度器；最后验证登录、受保护下载、模型制品和任务恢复。不要删除原卷来尝试恢复。

## 升级与回退

先完成备份恢复演练，再构建新镜像并运行迁移服务。Alembic 版本表为 `v2_alembic_version`，首版 DDL 已冻结，后续修订使用独立迁移。HTTP 进程不执行建库与自动管理员创建。迁移失败应停止切换。

回退使用旧镜像及经过验证的升级前备份，保留升级后数据以便核对；禁止用强制降级或删除模型文件处理失败。模型切换另有指针回滚，制品损坏时拒绝激活与回滚。

调度器依靠数据库锁保证单实例，任务提交与发件箱同事务。Worker 中断后连接锁释放，调度器在心跳超过十分钟时重发；同一任务恢复已下载文件清单。重投不保证消息只送一次，业务端保证同任务副作用幂等。

## 通知

站内通知持久保存。管理员可显式添加并启用 SMTP 或 HTTPS Webhook 通道，发送结果及重试次数可查询。秘密存放在 `ESP_NOTIFY_*` 环境变量中，网页只填写变量名。通道参数不会接受明文 password、token 或 secret。外部发送需要组织自己的收件地址和通道配置；测试仅模拟外部响应。

## 隔离验收

```powershell
docker compose -f compose.platform.yml -f compose.acceptance.yml up -d
docker compose -f compose.platform.yml -f compose.acceptance.yml exec acceptance-api python -m scripts.prepare_acceptance
docker compose -f compose.platform.yml -f compose.acceptance.yml exec acceptance-api python -m app.cli migrate
cd frontend
npm run test:e2e
```

在 Docker 测试容器中运行浏览器验收时，使用宿主可达地址并显式设置来源：

```powershell
$env:ACCEPTANCE_PUBLIC_ORIGIN='http://host.docker.internal:8081'
docker compose -f compose.platform.yml -f compose.acceptance.yml up -d --force-recreate acceptance-api acceptance-web
Remove-Item Env:ACCEPTANCE_PUBLIC_ORIGIN
docker run --rm --add-host host.docker.internal:host-gateway `
  -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:8081 `
  environmental-platform-frontend-tests:local npm run test:e2e
```

验收网页仅在 `http://localhost:8081`，使用 PostgreSQL `acceptance` schema、Redis DB 1 和独立附件目录。固定账号 admin、supervisor、officer、researcher 的口令为 `Acceptance-only-2026!`，仅用于隔离测试，初始化程序拒绝在正式库运行。监测图表来自已经下载的真实来源文件；标记为验收测试的企业不属于生产数据。

`scripts/benchmark_platform.py` 创建临时 `test_*` schema 和合成观测做 50 并发、千万行验证，不写生产库。应在有足够磁盘及内存的独立验收环境运行，避免共享宿主机其他项目影响结果。`scripts/validate_worker_recovery.py` 在独立队列及 Redis DB 2 杀掉并重启真实 Celery Worker，外部来源使用本地 HTTP 测试服务。

七天在线验收应每天核对计划任务、两类源文件、缺档、补采、版本修订、通知结果和备份；记录起止时间及实际故障，禁止把一次启动成功当作七天验收完成。
