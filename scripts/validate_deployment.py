"""Boot built images on new, isolated volumes; verify first login, jobs and evidence restore."""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import subprocess
import time
from uuid import uuid4

import httpx

try:
    from scripts import backup_platform
except ModuleNotFoundError:  # Support ``python scripts/validate_deployment.py`` on Windows.
    import backup_platform

ROOT = Path(__file__).resolve().parents[1]


def run(arguments, *, input=None, timeout=240):
    # Docker forwards stdin unchanged. Avoid Windows text-mode CRLF conversion in passwords.
    binary = input is not None
    result = subprocess.run(arguments, cwd=ROOT, input=input.encode('utf8') if binary else None,
                            text=not binary, capture_output=True, timeout=timeout)
    stdout = result.stdout.decode('utf8', errors='replace') if binary else result.stdout
    stderr = result.stderr.decode('utf8', errors='replace') if binary else result.stderr
    if result.returncode:
        raise RuntimeError(f'{arguments[0]} failed: {stderr[-2500:]}')
    return stdout.strip()


def main():
    project = 'environmental-clean-' + uuid4().hex[:10]
    directory = ROOT / '.artifacts' / project
    directory.mkdir(parents=True)
    config = json.loads(run(['docker', 'compose', '-f', 'compose.platform.yml', 'config', '--format', 'json']))
    config['name'] = project
    password, secret = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    for collection in ('volumes', 'networks'):
        for item in config.get(collection, {}).values():
            if item.get('external'): raise RuntimeError('External resources cannot be part of a disposable deployment')
            item.pop('name', None)
    for name, service in config['services'].items():
        service.pop('build', None)
        service.pop('ports', None)
        service.pop('container_name', None)
        service['restart'] = 'no'
        environment = service.get('environment', {})
        if 'POSTGRES_PASSWORD' in environment: environment['POSTGRES_PASSWORD'] = password
        if 'ESP_DATABASE_URL' in environment:
            environment.update(ESP_DATABASE_URL=f'postgresql+psycopg://platform:{password}@postgres:5432/platform',
                               ESP_SECRET_KEY=secret, ESP_ENVIRONMENT='test', ESP_PUBLIC_ORIGIN='http://localhost:8080')
        for volume in service.get('volumes', []):
            if volume.get('type') != 'volume': raise RuntimeError('Clean deployment must not mount source code or legacy CSV directories')
        if name in ('api', 'web'):
            service['ports'] = [{'host_ip': '127.0.0.1', 'target': 8000 if name == 'api' else 80, 'published': '0', 'protocol': 'tcp'}]
    manifest = directory / 'compose.json'
    manifest.write_text(json.dumps(config, indent=2), encoding='utf8')
    compose = ['docker', 'compose', '-p', project, '-f', str(manifest)]
    report = {'project': project, 'started_at': datetime.now(timezone.utc).isoformat(), 'source_bind_mounts': False}
    try:
        print('Starting a deployment with new database, Redis and file volumes', flush=True)
        run([*compose, 'up', '-d', '--no-build'], timeout=300)
        api_address = run([*compose, 'port', 'api', '8000']).splitlines()[0]
        web_address = run([*compose, 'port', 'web', '80']).splitlines()[0]
        origin = 'http://' + api_address
        with httpx.Client(base_url=origin, timeout=30, trust_env=False) as client:
            client.get('/health/ready').raise_for_status()
            httpx.get('http://' + web_address, timeout=15, trust_env=False).raise_for_status()
            initial, changed = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
            run([*compose, 'exec', '-T', 'api', 'python', '-m', 'app.cli', 'create-admin', '--username', 'initial-admin', '--password-stdin'], input=f'{initial}\n{initial}\n')
            def login(value):
                response = client.post('/api/v2/auth/login', json={'username': 'initial-admin', 'password': value})
                response.raise_for_status()
                assert 'HttpOnly' in response.headers.get('set-cookie', '')
                payload = response.json()
                client.headers['X-CSRF-Token'] = payload['csrf_token']
                return payload['user']
            assert login(initial)['must_change_password']
            assert client.get('/api/v2/dashboard').status_code == 403
            client.post('/api/v2/auth/change-password', json={'current_password': initial, 'new_password': changed}).raise_for_status()
            assert not login(changed)['must_change_password']
            dashboard = client.get('/api/v2/dashboard').json()
            assert dashboard['latest_date'] is None and dashboard['pollutants'] == []
            report.update(empty_database_started=True, first_login_password_change=True, http_only_session=True)
            company = client.post('/api/v2/enterprises', json={'name': '隔离部署验收企业'})
            company.raise_for_status()
            content = b'Isolated deployment evidence: preserve exact original bytes.'
            attachment = client.post('/api/v2/attachments', data={'enterprise_id': company.json()['id']}, files={'file': ('inspection-evidence.txt', content, 'text/plain')})
            attachment.raise_for_status()
            assert client.get(f"/api/v2/attachments/{attachment.json()['id']}/download").content == content
            response = client.post('/api/v2/jobs', json={'kind': 'export', 'start': '2026-09-30', 'end': '2026-09-30'})
            assert response.status_code == 202, response.text
            identifier = response.json()['job_id']
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                job = client.get('/api/v2/jobs/' + identifier).json()
                if job['status'] in ('succeeded', 'failed'): break
                time.sleep(.5)
            assert job['status'] == 'succeeded', job
            report['real_async_export'] = True
        # Both components run against this disposable deployment, never the live database.
        backup_platform.COMPOSE = compose
        backup_platform.backup(directory / 'backup')
        backup_platform.verify_restore(directory / 'backup')
        restored = json.loads((directory / 'backup/restore-verification.json').read_text('utf8'))
        assert restored['counts_observations_attachments'] == ['0', '1']
        assert restored['restored_file_count'] >= 2
        report['backup_restored_evidence_and_export'] = restored
        report['passed'] = True
        print('Empty startup, first password change, asynchronous export and evidence backup/restore passed', flush=True)
    finally:
        # The project name and all volume definitions were generated above and have no external resources.
        assert project.startswith('environmental-clean-') and len(project) == len('environmental-clean-') + 10
        run([*compose, 'down', '--volumes', '--timeout', '30'], timeout=180)
        remaining = run(['docker', 'volume', 'ls', '-q', '--filter', f'label=com.docker.compose.project={project}'])
        if remaining: raise RuntimeError('Disposable volumes were not removed')
        report['isolated_resources_removed'] = True
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        # Keep the runtime report; the disposable password is no longer needed.
        manifest.unlink(missing_ok=True)
        destination = ROOT / '.artifacts/deployment-validation.json'
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
