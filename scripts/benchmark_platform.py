"""Destructive only inside a fresh test_* schema; never inserts synthetic production data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
from pathlib import Path
import threading
import time
import re
import tempfile
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
import numpy as np
from sqlalchemy import select, text
import uvicorn

from platform_tests.support import DatabaseTest, PASSWORD
from app.v2.domains.auth.models import User
from app.v2.domains.collection.models import SourceFile
from app.v2.domains.monitoring.models import City, Station
from app.v2.config import Settings
from app.v2.main import create_app
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, default=10_000_000)
    parser.add_argument('--users', type=int, default=50)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/performance.json'))
    parser.add_argument('--resume-schema', help='Only a previously created isolated test_<uuid> schema')
    parser.add_argument('--keep-schema', action='store_true', help='Retain the isolated dataset for comparison after query changes')
    parser.add_argument('--min-free-gib', type=int, default=30, help='Minimum free space on the mounted host output volume')
    args = parser.parse_args()
    if not 10000 <= args.rows <= 10_000_000 or not 1 <= args.users <= 50: raise SystemExit('Invalid test size')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def check_space():
        free = shutil.disk_usage(args.output.parent).free / 1024**3
        if free < args.min_free_gib: raise RuntimeError(f'Host output volume has only {free:.1f} GiB free; benchmark stopped')
        return round(free, 2)
    initial_free = check_space()
    fixture = DatabaseTest()
    if args.resume_schema:
        if not re.fullmatch(r'test_[a-f0-9]{32}',args.resume_schema): raise SystemExit('Refusing a non-test schema')
        base=Settings()
        fixture.schema=args.resume_schema
        fixture.admin_engine=create_engine(base.database_url)
        fixture.temporary=tempfile.TemporaryDirectory()
        url=make_url(base.database_url).update_query_dict({'options':f'-csearch_path={fixture.schema}'})
        fixture.settings=base.model_copy(update={'database_url':url.render_as_string(hide_password=False),'environment':'test','storage_root':Path(fixture.temporary.name)})
        fixture.app=create_app(fixture.settings)
        fixture.db=fixture.app.state.db
        fixture.clients=[]
    else:
        fixture.setUp()
    server, thread, clients = None, None, []
    report = {'synthetic_isolated_data': True, 'rows': args.rows, 'concurrent_users': args.users,
              'schema': fixture.schema, 'initial_host_free_gib': initial_free}
    try:
        last = date(2024, 1, 1) + timedelta(days=(args.rows - 1) // 14400)
        with fixture.db.transaction() as session:
            city = session.scalar(select(City))
            source=session.scalar(select(SourceFile).where(SourceFile.source_key=='isolated-performance'))
            if args.resume_schema and source is None: raise RuntimeError('Not a benchmark schema')
            if not source:
                for n in range(100): session.add(Station(id=f'benchmark-station-{n}',city_id=city.id,code=str(n),name=f'性能测试站{n}'))
                source = SourceFile(source_key='isolated-performance',local_date=last,kind='test',origin='ISOLATED_TEST',sha256='0'*64,storage_key='never-download',row_count=args.rows)
                session.add(source)
                session.flush()
                hashed = session.get(User, fixture.users['researcher']).password_hash
                for n in range(args.users): session.add(User(username=f'benchmark{n}',display_name='隔离性能测试',password_hash=hashed,role='研究者',must_change_password=False))
            source_id=source.id
            initial_rows=session.scalar(text('SELECT count(*) FROM v2_observations'))
            report['initial_rows']=initial_rows
        began = time.perf_counter()
        for low in range(initial_rows, args.rows, 250000):
            check_space()
            with fixture.db.engine.begin() as connection:
                connection.execute(text("""INSERT INTO v2_observations
                    (id,created_at,source_file_id,station_id,observed_at,local_date,pollutant,basis,value,unit,quality)
                    SELECT md5('benchmark-'||i::text),now(),:source,'benchmark-station-'||((i/6)%100)::text,
                      timestamptz '2024-01-01 00:00:00+08' + (i/600)*interval '1 hour',
                      date '2024-01-01'+(i/14400)::int,
                      (ARRAY['PM2.5','PM10','SO2','NO2','O3','CO'])[(i%6)+1], 'hourly',
                      10+(i%180)::double precision, CASE WHEN i%6=5 THEN 'mg/m³' ELSE 'μg/m³' END,'valid'
                    FROM generate_series(:low, :high) i"""), {'source':source_id,'low':low,'high':min(low+249999,args.rows-1)})
            print(json.dumps({'inserted': min(low+250000,args.rows),'seconds':round(time.perf_counter()-began,1)}),flush=True)
        with fixture.db.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('ANALYZE v2_observations'))
        report['prepare_seconds'] = round(time.perf_counter()-began, 2)
        config = uvicorn.Config(fixture.app,host='127.0.0.1',port=19009,log_level='error',access_log=False)
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run,daemon=True)
        thread.start()
        for _ in range(100):
            if server.started: break
            time.sleep(.1)
        for n in range(args.users):
            client = httpx.Client(base_url='http://127.0.0.1:19009', timeout=60)
            response = client.post('/api/v2/auth/login',json={'username':f'benchmark{n}','password':PASSWORD})
            response.raise_for_status()
            clients.append(client)
        parameters = {'start':str(last-timedelta(days=6)), 'end':str(last), 'city_id':city.id}
        for name, route, extra, limit in [('list','/api/v2/observations',{'pollutant':'PM2.5','page_size':20},800),('dashboard','/api/v2/dashboard',{},2000)]:
            for c in clients[:5]: c.get(route,params={**parameters,**extra}).raise_for_status()
            barrier = threading.Barrier(args.users)
            def worker(index):
                barrier.wait()
                values=[]
                for iteration in range(4):
                    began = time.perf_counter()
                    result=clients[index].get(route,params={**parameters,**extra,**({'page_number':iteration+1} if name=='list' else {})})
                    result.raise_for_status()
                    values.append((time.perf_counter()-began)*1000)
                return values
            with ThreadPoolExecutor(max_workers=args.users) as pool: values=[v for part in pool.map(worker,range(args.users)) for v in part]
            report[name]={'requests':len(values),'p50_ms':round(float(np.percentile(values,50)),2),'p95_ms':round(float(np.percentile(values,95)),2),'max_ms':round(max(values),2),'target_ms':limit}
            report[name]['passed']=report[name]['p95_ms'] <= limit
            print(json.dumps(report[name]),flush=True)
        report['scope']='Single API process, PostgreSQL 16, real HTTP cookies; shared Docker host. Synthetic rows never reach the application schema.'
        report['final_host_free_gib'] = check_space()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    finally:
        for client in clients: client.close()
        if server: server.should_exit=True
        if thread: thread.join(10)
        if args.keep_schema:
            for client in fixture.clients: client.close()
            fixture.db.engine.dispose()
            fixture.admin_engine.dispose()
            fixture.temporary.cleanup()
            print(json.dumps({'retained_isolated_schema': fixture.schema}), flush=True)
        else:
            fixture.tearDown()

if __name__=='__main__': main()
