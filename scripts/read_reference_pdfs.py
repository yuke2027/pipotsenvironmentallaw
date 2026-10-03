"""Developer reference extraction (not an API runtime dependency)."""
import io
from pathlib import Path
import httpx
from pypdf import PdfReader

urls = {
    "HJ633-2026": "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/jcffbz/202602/W020260225366493492011.pdf",
    "HJ663-2026": "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/jcffbz/202602/W020260225383639187925.pdf",
    "GB3095-2026": "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202602/W020260224700452407278.pdf",
}
target = Path(".artifacts/references")
target.mkdir(parents=True, exist_ok=True)
for name, url in urls.items():
    response = httpx.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    (target / f"{name}.pdf").write_bytes(response.content)
    content = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    (target / f"{name}.txt").write_text(content, encoding="utf-8")
    print(name, len(content))
