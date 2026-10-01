# 部署说明

## 本地

1. 安装 Python 3.10。
2. 安装 `requirements.txt`。测试再安装 `requirements-test.txt`。
3. 设置 `JWT_SECRET`。
4. 运行 `python -m app.cli serve --once` 做一次启动检查，或用进程管理器运行：

```bash
python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

健康检查：`http://127.0.0.1:8000/api/v1/health`。

导入宽表：

```bash
python -m app.cli import-csv --directory data1
```

## 容器

`docker compose up --build` 启动服务 `platform`。卷 `platform-db`、`platform-models`、`platform-exports` 分别保存数据库、模型和导出文件。镜像以 uid 10001 的非 root 用户运行，并安装 Noto CJK。

不要把口令写进镜像。通道凭据只用 `ALERT_EMAIL_CREDENTIAL_REF` 和 `ALERT_WEBHOOK_CREDENTIAL_REF` 这类引用，秘密放在部署环境里。

## 服务器

1. 安装 Docker Engine 与 Compose。
2. 在部署目录设置 `JWT_SECRET` 和调度周期 `COLLECTION_INTERVAL_SECONDS`。
3. 执行 `docker compose up --build -d`。
4. 用 `/api/v1/health` 确认数据库状态。
5. 升级应用时先备份数据库卷，再重新构建镜像。应用启动时会执行 Alembic `upgrade head`。

CNEMC 采集默认关闭。配置合法端点后才会请求外部接口。自动测试不访问该端点。
