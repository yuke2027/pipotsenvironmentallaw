"""Build the two docx volumes: main manual + technical appendix.

- injects a page break before each top-level '# 第X部分'/'# 附录'/'# 说明' section
- runs pandoc with reference.docx styling and a 2-level TOC

Usage: python build.py
"""
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
PAGEBREAK = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```\n\n'


def preprocess(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf8")
    out_lines = []
    for line in text.splitlines(keepends=True):
        if re.match(r"^# (第|附录|说明)", line):
            out_lines.append(PAGEBREAK)
        out_lines.append(line)
    dst.write_text("".join(out_lines), encoding="utf8")


def build(src_name: str, out_name: str) -> None:
    tmp = HERE / ("_build_" + src_name)
    preprocess(HERE / src_name, tmp)
    cmd = [
        "pandoc", str(tmp), "-o", str(HERE / out_name),
        "--reference-doc", str(HERE / "reference.docx"),
        "--toc", "--toc-depth=2", "--resource-path", str(HERE),
        "-f", "markdown+smart", "--standalone",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf8")
    for line in (r.stderr or "").splitlines():
        if "translations" not in line and "has no translation" not in line:
            print(" pandoc:", line)
    tmp.unlink()
    print(out_name, "rc=", r.returncode)


if __name__ == "__main__":
    build("manual.md", "蓝穹云眼-系统架构及功能说明书-主册-v2.0.docx")
    build("appendix.md", "蓝穹云眼-系统技术附录册-v2.0.docx")
