from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_frontend_transport_is_owned_by_shared_layer() -> None:
    violations = []
    for source in ROOT.rglob("*"):
        if source.suffix not in {".ts", ".tsx"} or source.name.endswith(".test.ts") or source.name.endswith(".test.tsx"):
            continue
        if re.search(r"\bfetch\s*\(", source.read_text(encoding="utf-8")) and source != ROOT / "shared" / "api.ts":
            violations.append(str(source.relative_to(ROOT)))
    assert not violations, f"direct fetch must stay in shared/api.ts: {violations}"


def test_domain_hooks_import_shared_transport() -> None:
    violations = []
    for source in (ROOT / "domains").glob("*/hooks.ts"):
        if "from '../../api'" in source.read_text(encoding="utf-8"):
            violations.append(str(source.relative_to(ROOT)))
    assert not violations, f"domain hooks must use shared/api: {violations}"


def test_frontend_pages_are_owned_by_domain_slices() -> None:
    expected = {
        ROOT / "domains" / "auth" / "pages.tsx",
        ROOT / "domains" / "monitoring" / "pages.tsx",
        ROOT / "domains" / "enforcement" / "pages.tsx",
        ROOT / "domains" / "operations" / "pages.tsx",
        ROOT / "domains" / "admin" / "pages.tsx",
    }
    assert all(path.is_file() for path in expected)
    forbidden_imports = ("from '../api'", "from '../components'", "from '../context'")
    violations = []
    for source in expected:
        text = source.read_text(encoding="utf-8")
        if any(import_path in text for import_path in forbidden_imports) or re.search(
            r"import .*\b(api|useApi|useAction)\b.*from ['\"]\.\./\.\./shared/api['\"]", text
        ):
            violations.append(str(source.relative_to(ROOT)))
        if re.search(r"\brequest\s*\(", text) or "useAuthRequest" in text or "useAdminRequest" in text or "useEnforcementRequest" in text or "useOperationsRequest" in text:
            violations.append(f"{source.relative_to(ROOT)}: direct request helper")
    assert not violations, f"domain pages must use shared UI and transport layers: {violations}"

    main = (ROOT / "main.tsx").read_text(encoding="utf-8")
    assert "./shared/layout" in main and "./domains/" in main
    assert "./domains/admin/pages" in main
    assert "./domains/operations/pages" in main
    assert "./pages/" not in main


def test_shared_shell_uses_shared_hooks_instead_of_low_level_transport() -> None:
    shell = (ROOT / "shared" / "layout.tsx").read_text(encoding="utf-8")
    assert "from './hooks'" in shell
    assert not re.search(r"\bapi\s*\(", shell)
    assert "useApi" not in shell


def test_nginx_proxy_re_resolves_replaced_api_containers() -> None:
    repo = Path(__file__).resolve().parents[2]
    configs = {
        repo / "deployment" / "nginx.conf": "api:8000",
        repo / "deployment" / "nginx.acceptance.conf": "acceptance-api:8000",
    }
    for config, upstream in configs.items():
        text = config.read_text(encoding="utf-8")
        assert "resolver 127.0.0.11 valid=5s ipv6=off;" in text
        assert "resolver_timeout 3s;" in text
        assert "set $api_backend" in text
        assert "proxy_pass http://$api_backend;" in text
        assert upstream in text
