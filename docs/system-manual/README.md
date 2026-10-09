# 系统说明书再生流程

本目录是《蓝穹云眼·系统架构及功能说明书》的源文件与产物目录，产出为两册 Word：

| 文件 | 用途 |
| --- | --- |
| `manual.md` | 主册正文（业务+架构+运维，约 67 页） |
| `appendix.md` | 附录册正文（接口/数据字典/权限/枚举，约 38 页，脚本生成） |
| `gen_appendix.py` | 从 `openapi.json` + `schema.txt` + 路由鉴权声明生成 `appendix.md` |
| `figures.html` | 8 张架构图的 HTML/CSS 源（架构/部署/数据流/状态机/许可门禁/ER/鉴权/任务生命周期） |
| `assets/` | 嵌入图片：fig-* 架构图 + m* 系统截图 + proto-* 原型示意 |
| `make_reference.py` | 由 pandoc 默认 reference.docx 生成中文公文样式（黑体标题/宋体正文/1.5 倍行距/表格网格线/居中图题） |
| `build.py` | 注入分节分页符并调用 pandoc 生成两册 docx |
| `reference.docx` | 生成产物中的样式模板 |
| `openapi.json` / `schema.txt` | 生成附录的输入快照（运行系统契约与库结构） |
| `count_pages.ps1` | 用本机 Word COM 统计页数（须先把 docx 复制为 ASCII 名） |
| `nginx.manual.conf` | 截图用临时 web 容器的反代配置 |

## 再生步骤

```bash
# 1. 架构图：Playwright 容器对每个 #fig-* 元素截图到 assets/
# 2. 系统截图：脚本在 frontend/.proto-check/（依赖该目录 node_modules）：
#    manual-shots.mjs（整页）、manual-more.mjs（Tab/弹窗）、
#    manual-lead.mjs、manual-forecast.mjs（写入型操作，慎用）
docker run --rm --network environmental-platform_default -v <repo>:/workspace \
  -w /workspace/frontend/.proto-check -e BASE=http://manual-web \
  mcr.microsoft.com/playwright:v1.63.0-noble node manual-shots.mjs

# 3. 刷新契约与 schema 快照
curl -s http://localhost:58000/api/v2/openapi.json -o openapi.json
docker exec environmental-platform-postgres-1 psql -U platform -d platform -A -F'|' \
  -c "SELECT table_name,column_name,data_type,is_nullable,character_maximum_length,column_default \
      FROM information_schema.columns WHERE table_schema='public' AND table_name LIKE 'v2_%' \
      ORDER BY table_name, ordinal_position" > schema.txt

# 4. 生成
python gen_appendix.py
pandoc --print-default-data-file reference.docx > ref-src.docx && python make_reference.py
python build.py
```

注意：截图账号与对象 ID（站点/企业/核查）写在脚本常量里，换库后需同步更新；大屏图为原型示意，正式大屏实施后重截。临时验证容器 manual-api/manual-web 的启动方式见 git 历史说明。
