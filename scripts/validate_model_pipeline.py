"""Actual preserved CSV -> PostgreSQL -> queued training -> activation -> inference."""
import csv
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select
from platform_tests.support import DatabaseTest
from app.v2.collection import import_file
from app.v2.domains.jobs.models import Job
from app.v2.domains.ml.models import DerivedValue, ModelArtifact
from app.v2.tasks import run_job


def main():
    fixture=DatabaseTest()
    fixture.setUp()
    fixture.settings.model_window=24
    report={'isolated_postgresql':True,'source':'preserved January 2025 CSV, first 3 actual stations; no synthetic observations'}
    try:
        count=0
        for path in sorted(Path('data1').glob('beijing_*_202501*.csv')):
            rows=list(csv.reader(io.StringIO(path.read_text('utf-8-sig'))))
            content=io.StringIO(newline='')
            writer=csv.writer(content)
            for row in rows: writer.writerow(row[:6])
            import_file(fixture.db,fixture.store,content.getvalue().encode(),'extra' if 'extra' in path.name else 'all','REAL_VALIDATION')
            count+=1
        if count != 62: raise RuntimeError('Expected all 62 preserved daily files')
        admin=fixture.client()
        report['files']=count
        for task,algorithm in [('forecast','seasonal'),('imputation','interpolation')]:
            response=admin.post('/api/v2/jobs',json={'kind':'train','task':task,'algorithm':algorithm,'start':'2025-01-01','end':'2025-01-31'})
            assert response.status_code==202,response.text
            identifier=response.json()['job_id']
            assert run_job(identifier,fixture.settings)['status']=='completed'
            with fixture.db.sessions() as session:
                job=session.get(Job,identifier)
                model=session.get(ModelArtifact,job.result['model_id'])
                assert model.status=='validated',model.metrics
                model_id=model.id
                contract=job.result['_contract']
                artifacts=[item for item in contract['artifacts'] if item['kind']=='model']
                assert len(artifacts)==1,contract
                fixture.store.verify(artifacts[0]['key'],artifacts[0]['sha256'])
                report[algorithm]={'status':model.status,'metrics':model.metrics,'snapshot':model.manifest['snapshot']['sha256'],
                    'training_artifact':artifacts[0]}
            response=admin.post(f'/api/v2/models/{model_id}/activate')
            assert response.status_code==200,response.text
            response=admin.post('/api/v2/jobs',json={'kind':'forecast' if task=='forecast' else 'impute','start':'2025-01-01','end':'2025-01-31'})
            identifier=response.json()['job_id']
            result=run_job(identifier,fixture.settings)
            with fixture.db.sessions() as session:
                job=session.get(Job,identifier)
                assert result['status']=='completed',(result,job.error)
                assert job.result['rows']>0
                contract=job.result['_contract']
                artifacts=[item for item in contract['artifacts'] if item['kind']==('forecast' if task=='forecast' else 'imputation')]
                assert len(artifacts)==1,contract
                fixture.store.verify(artifacts[0]['key'],artifacts[0]['sha256'])
                report[algorithm]['inference_artifact']=artifacts[0]
                report[algorithm]['inference_rows']=job.result['rows']
            assert run_job(identifier,fixture.settings)['status']=='already_finished'
        target=Path('.artifacts/model-pipeline.json')
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({key: value['inference_rows'] for key,value in report.items() if isinstance(value,dict)}))
    finally: fixture.tearDown()

if __name__=='__main__': main()
