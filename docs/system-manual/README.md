# 系统说明书再生流程

本目录是《蓝穹云眼·系统架构及功能说明书》的源文件与产物目录。

| 文件 | 用途 |
| --- | --- |
| `manual.md` | 说明书正文（Markdown，图片引用 `assets/`） |
| `figures.html` | 五张架构图的 HTML/CSS 源（架构/部署/数据流/状态机/许可门禁） |
| `capture.mjs` | 正式系统页面截图脚本（Playwright） |
| `assets/` | 嵌入图片：fig-* 架构图 + m* 系统截图 + proto-* 原型示意 |
| `蓝穹云眼-系统架构及功能说明书-v2.0.docx` | 生成的 Word 交付物 |

## 再生步骤

```bash
# 1. 架构图：Playwright 容器截 HTML 源
docker run --rm -v <repo>:/workspace mcr.microsoft.com/playwright:v1.63.0-noble \
  node -e '…对每个 #fig-* 元素截图到 assets/…'

# 2. 系统截图：需要运行中的 web/API 与账号（见 capture.mjs 内常量）
docker run --rm --network environmental-platform_default -v <repo>:/workspace \
  -w /workspace/docs/system-manual mcr.microsoft.com/playwright:v1.63.0-noble \
  node capture.mjs

# 3. 生成 Word
pandoc manual.md -o 蓝穹云眼-系统架构及功能说明书-v2.0.docx \
  --toc --toc-depth=2 --resource-path=. --standalone
```

注意：截图账号与对象 ID（站点/企业/核查）写在 `capture.mjs` 常量里，换库后需同步更新；大屏图为原型示意，正式大屏实施后重截。
