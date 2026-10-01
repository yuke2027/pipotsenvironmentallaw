# 环境监督平台

FastAPI 环境监督平台。本地、容器和服务器使用同一套应用。自动测试不访问外网。

## 本地启动

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-test.txt
set JWT_SECRET=replace-with-a-long-secret
python -m app.cli --help
python -m app.cli import-csv --help
python -m app.cli serve --once
```

仪表盘地址是 `http://127.0.0.1:8000/`，健康检查地址是 `http://127.0.0.1:8000/api/v1/health`。

## 容器启动

```bash
docker compose up --build
```

Compose 服务名是 `platform`。数据库、模型和导出目录使用命名卷。`JWT_SECRET` 必须由环境变量提供。

## 服务器部署

见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 测试

```bash
python -m pytest
python -m mypy app
python -m compileall app
```

测试使用临时 SQLite 和 `httpx.MockTransport`，不依赖外网，也不读取生产数据库。
