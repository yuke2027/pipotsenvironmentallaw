"""Crash an isolated real Celery worker during a controlled source download, then recover."""
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from celery import Celery
from sqlalchemy import func, select
from platform_tests.support import DatabaseTest, daily_csv
from app.v2.jobs import enqueue
from app.v2.domains.jobs.models import Job
from app.v2.domains.monitoring.models import Observation
from app.v2.shared.persistence import now
from app.v2.scheduler import publish_outbox, recover_stalled


def main():
    fixture=DatabaseTest()
    fixture.setUp()
    entered=threading.Event()
    release=threading.Event()
    source=None
    worker=None
    queue='recovery-'+uuid4().hex
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            if not entered.is_set():
                entered.set()
                release.wait(30)
            body=daily_csv(kinds=('SO2','NO2','O3','CO')) if 'extra' in self.path else daily_csv()
            self.send_response(200)
            self.end_headers()
            try: self.wfile.write(body)
            except BrokenPipeError: pass
    log_path=Path('.artifacts/worker-recovery.log')
    log_path.parent.mkdir(parents=True,exist_ok=True)
    try:
        source=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=source.serve_forever,daemon=True).start()
        broker=fixture.settings.redis_url.rsplit('/',1)[0]+'/2'
        env={**os.environ,'ESP_DATABASE_URL':fixture.settings.database_url,'ESP_REDIS_URL':broker,
             'ESP_STORAGE_ROOT':str(fixture.settings.storage_root),'ESP_ENVIRONMENT':'test',
             'ESP_SOURCE_BASE_URL':f'http://127.0.0.1:{source.server_port}','ESP_SOURCE_INTERVAL_SECONDS':'0'}
        producer=Celery('isolated-recovery',broker=broker)
        def send(identifier,_queue): producer.send_task('platform.run_job',args=[identifier],queue=queue)
        def start():
            return subprocess.Popen([sys.executable,'-m','celery','-A','app.v2.tasks:celery_app','worker','-Q',queue,
                '--concurrency=1','--loglevel=INFO','--without-gossip','--without-mingle'],env=env,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        with log_path.open('w') as log:
            worker=start()
            with fixture.db.transaction() as session: identifier=enqueue(session,'collect',{'start':'2026-09-30','end':'2026-09-30'}).id
            publish_outbox(fixture.db,send)
            if not entered.wait(45): raise RuntimeError('Isolated worker did not start the real collection task')
            os.killpg(worker.pid,signal.SIGKILL)
            worker.wait(10)
            release.set()
            with fixture.db.transaction() as session:
                job=session.get(Job,identifier)
                assert job.status=='running'
                job.heartbeat_at=now()-timedelta(minutes=20)
            recover_stalled(fixture.db)
            worker=start()
            publish_outbox(fixture.db,send)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                with fixture.db.sessions() as session:
                    job=session.get(Job,identifier)
                    if job.status in {'succeeded','failed','partial'}: break
                time.sleep(.25)
            assert job.status=='succeeded',(job.status,job.error)
            assert job.attempts==2,job.attempts
            # An explicit duplicate delivery also leaves the one persistent result intact.
            send(identifier,'io')
            time.sleep(1)
            with fixture.db.sessions() as session:
                count=session.scalar(select(func.count()).select_from(Observation))
                assert count==24*7*2,count
                assert session.get(Job,identifier).attempts==2
            report={'real_celery_worker_killed':True,'scheduler_recovered':True,'attempts':2,'observations':count,
                'duplicate_delivery_did_not_recompute':True,'source':'isolated local HTTP fixture; no external notification'}
            Path('.artifacts/worker-recovery.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report))
    finally:
        release.set()
        if worker and worker.poll() is None:
            os.killpg(worker.pid,signal.SIGTERM)
            try: worker.wait(10)
            except subprocess.TimeoutExpired:
                os.killpg(worker.pid,signal.SIGKILL)
                worker.wait(5)
        if source: source.shutdown()
        fixture.tearDown()

if __name__=='__main__': main()
