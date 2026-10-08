# 工作台操作与开发入门

先按 README 启动平台并创建管理员。首次改密后由系统管理建立主管、执法人员与研究者账号，每个新账号首次登录都需要修改初始密码。

## 监测与分析

1. 管理员在报告与下载中补采当前日期，或使用 `python -m app.cli collect --backfill-months 24` 回填历史数据。
2. 打开任务抽屉查看真实进度。下载缺档会显示部分完成及失败日期，可以重试。
3. 监测分析支持六项污染物及来源 AQI、最多五站对比、小时与日粒度、图表缩放和当日明细联动。筛选保存在 URL。
4. 标准评价使用原始小时观测，按观测日期匹配标准；数据不足不输出达标结论。插补属于单独标记的辅助数据。
5. 导出生成后台任务，完成后从报告列表下载。研究者仅可下载自己的授权环境数据导出。

CSV 使用 UTF-8：监测日文件表头为 `date,hour,type,站点…`，日期为 `YYYYMMDD`，小时为 0 到 23；颗粒物选 `all`，气体选 `extra`。企业表头为 `企业名称,统一社会信用代码,行业,地址,联系人`；批量导入的信用代码要求 18 位大写字母或数字。解析错误不会部分写入企业档案。

## 核查闭环

主管人工建立或从超限评价创建线索，确认关联企业，分派负责人、协作人和期限。执法人员开始现场核查，保存事实、手动选择法规和具体条款，上传证据后添加整改要求。

进入整改跟踪后填写每项完成情况，提交复查并逐项记录事实、核实结果，再交主管审核。主管可退回或审核归档；归档禁止修改，重新开启需要说明理由。无需整改的事项也必须保存事实和审核说明。

附件追加版本保留原文件和 SHA-256，不覆盖旧证据。表单未保存时阻止直接切换页面，并在刷新或关闭时提示。

## 模型

默认 API 镜像仅包含核心业务和数值基线。先构建 API，再构建专用模型镜像：

```powershell
docker compose -f compose.platform.yml build api
docker compose -f compose.platform.yml -f compose.models.yml build model-worker
docker compose -f compose.platform.yml -f compose.models.yml up -d --no-deps model-worker
```

管理员选择足够长的数据范围，在模型中心创建季节预测、LightGBM、插值、SAITS 或 BRITS 训练任务。任务保存快照、代码哈希、环境、指标和制品。候选未超过基线保留实验状态；已验证模型需要管理员激活，切换失败保留上一版本。

24 小时预测首版仅包含 PM2.5 和 PM10。区间为验证残差校准后的名义 90% 区间，页面同时提供实测覆盖率；不显示未经验证的可靠概率。

## 本地开发

后端使用 Python 3.12 和 `requirements-platform.lock`。`compose.dev.yml` 仅为开发时挂载后端源码，Python 代码变化需要重启对应服务。训练、采集不能放进 API 进程。

```powershell
cd frontend
npm ci
npm run dev
```

Vite 代理指向本机 58000 端口。使用 Vite 开发时，将后端 `ESP_PUBLIC_ORIGIN` 设置为 `http://localhost:5173` 并重启 API；生产和验收仍使用各自的同源入口。修改契约后执行后端 `python -m app.cli openapi --output frontend/openapi.json`，再执行前端 `npm run generate:api`。默认认证使用 HttpOnly 会话 Cookie 和 CSRF 请求头；不要在 LocalStorage 保存登录令牌。
