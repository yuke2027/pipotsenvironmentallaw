"""Create local configuration once without emitting generated credentials."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env already exists; preserved")
else:
    target.write_text(f"ESP_SECRET_KEY={secrets.token_urlsafe(48)}\nPOSTGRES_PASSWORD={secrets.token_urlsafe(32)}\nESP_PUBLIC_ORIGIN=http://localhost:8080\nESP_SOURCE_LICENSE_CONFIRMED=false\n", encoding="utf-8")
    print("Created .env with random local credentials; no administrator was created")
