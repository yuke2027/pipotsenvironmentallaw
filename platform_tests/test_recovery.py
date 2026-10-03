from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json

import httpx
from sqlalchemy import func, select

from platform_tests.support import DatabaseTest, daily_csv
from app.v2.collection import collect_range, import_file
from app.v2.evaluation import evaluate_range
from app.v2.jobs import enqueue
from app.v2.models import Channel, Delivery, Job, ModelActivation, ModelArtifact, Notification, Observation, Outbox, SourceAttempt, SourceFile, now
from app.v2.notifications import deliver_pending
from app.v2.scheduler import recover_stalled
from app.v2.tasks import run_job


class RecoveryTests(DatabaseTest):
    def test_concurrent_enqueue_and_stale_delivery_recovery(self):
        def submit(_):
            with self.db.transaction() as session:
                return enqueue(session,'export',{'start':'2026-09-30','end':'2026-09-30'},self.users['researcher']).id
        with ThreadPoolExecutor(max_workers=6) as pool: identifiers = list(pool.map(submit,range(12)))
        self.assertEqual(len(set(identifiers)),1)
        with self.db.transaction() as session:
            message=session.scalar(select(Outbox))
            message.sent_at=now()-timedelta(minutes=20)
            session.get(Job,identifiers[0]).status='running'
        recover_stalled(self.db)
        with self.db.sessions() as session: self.assertIsNone(session.scalar(select(Outbox)).sent_at)
        self.assertEqual(run_job(identifiers[0],self.settings)['status'],'completed')
        self.assertEqual(run_job(identifiers[0],self.settings)['status'],'already_finished')

    def test_collection_resumes_only_this_job_and_keeps_reverted_source(self):
        calls=[]
        def response(request):
            calls.append(str(request.url))
            return httpx.Response(200,content=daily_csv(kinds=('SO2','NO2','O3','CO')) if 'extra' in str(request.url) else daily_csv())
        client=httpx.Client(transport=httpx.MockTransport(response))
        for identifier in ['delivery-a','delivery-a','delivery-b']:
            collect_range(self.db,self.store,self.settings,date(2026,9,30),date(2026,9,30),identifier,lambda _:None,client)
        self.assertEqual(len(calls),4)
        original=daily_csv()
        import_file(self.db,self.store,daily_csv(value=23),'all')
        import_file(self.db,self.store,original,'all')
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(SourceFile).where(SourceFile.is_current.is_(True))),2)
            self.assertEqual(session.scalar(select(Observation.value).join(SourceFile).where(SourceFile.is_current.is_(True),Observation.pollutant=='PM2.5').limit(1)),80)

    def test_notifications_progress_past_first_batch_and_retry_is_bounded(self):
        with self.db.transaction() as session:
            channel=Channel(name='测试通道',kind='webhook',enabled=True,config={'url':'https://example.invalid/hook'},created_at=now()-timedelta(days=1))
            session.add(channel)
            for n in range(503): session.add(Notification(user_id=self.users['officer'],title='隔离通知',body='核查提醒',href='/inspections',dedupe_key=str(n)))
        sent=[]
        def send(channel,notification): sent.append(notification.id)
        for _ in range(3): deliver_pending(self.db,self.settings,send)
        self.assertEqual(len(sent),503)
        self.assertEqual(len(set(sent)),503)
        with self.db.transaction() as session: session.add(Notification(user_id=self.users['officer'],title='重试测试',body='提醒',href='/inspections',dedupe_key='failed'))
        attempts=[]
        def failure(*args):
            attempts.append(1)
            raise RuntimeError('private token not exposed')
        for _ in range(5): deliver_pending(self.db,self.settings,failure)
        self.assertEqual(len(attempts),3)
        with self.db.sessions() as session: self.assertNotIn('token',session.scalar(select(Delivery.error).where(Delivery.status=='failed')))

    def test_missing_whole_hour_is_explicit_and_unknown_city_empty(self):
        import_file(self.db,self.store,daily_csv(hours=23),'all')
        client=self.client('researcher')
        response=client.get('/api/v2/timeseries?start=2026-09-30&end=2026-09-30').json()
        self.assertEqual(len(response['items']),24)
        self.assertIsNone(response['items'][-1]['value'])
        response=client.get('/api/v2/dashboard?city_id=unknown&start=2026-09-30&end=2026-09-30').json()
        self.assertEqual(response['stations'],0)
        self.assertEqual(response['pollutants'],[])

    def test_corrupt_model_activation_and_rollback_preserve_pointer(self):
        admin=self.client()
        with self.db.transaction() as session:
            job=enqueue(session,'train',{},self.users['admin'])
            key,hashed=self.store.put(b'{"algorithm":"seasonal"}','models','.json')
            good=ModelArtifact(task='forecast',algorithm='seasonal',status='validated',storage_key=key,sha256=hashed,manifest={},metrics={},job_id=job.id)
            session.add(good)
            session.flush()
            good_id=good.id
            bad_key,bad_hash=self.store.put(b'{"algorithm":"broken"}','models','.json')
            bad=ModelArtifact(task='forecast',algorithm='seasonal',status='validated',storage_key=bad_key,sha256=bad_hash,manifest={},metrics={},job_id=job.id)
            session.add(bad)
            session.flush()
            bad_id=bad.id
        self.assertEqual(admin.post(f'/api/v2/models/{good_id}/activate').status_code,200)
        self.store.path(bad_key).write_bytes(b'corrupted')
        self.assertEqual(admin.post(f'/api/v2/models/{bad_id}/activate').status_code,422)
        with self.db.transaction() as session: session.get(ModelActivation,'forecast').previous_id=bad_id
        self.assertEqual(admin.post('/api/v2/models/forecast/rollback').status_code,422)
        with self.db.sessions() as session: self.assertEqual(session.get(ModelActivation,'forecast').model_id,good_id)
