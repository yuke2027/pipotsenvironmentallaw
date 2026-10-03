from datetime import date, datetime, timezone
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url

from app.v2.config import Settings
from app.v2.db import Database
from app.v2.models import Base, City, Observation, SourceFile, Station


class MigrationTests(unittest.TestCase):
    def test_empty_install_then_upgrade_preserves_observations(self):
        base = Settings()
        admin = create_engine(base.database_url)
        schema = 'test_' + uuid4().hex
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(base.database_url).update_query_dict({'options': f'-csearch_path={schema}'})
        settings = base.model_copy(update={'database_url': url.render_as_string(hide_password=False)})
        db = Database(settings)
        try:
            with patch.dict(os.environ, {'ESP_DATABASE_URL': settings.database_url}):
                config = Config('alembic-v2.ini')
                command.upgrade(config, 'v2_0001')
                with db.transaction() as session:
                    city = City(code='migration-test', name='杩佺Щ娴嬭瘯')
                    session.add(city)
                    session.flush()
                    station = Station(city_id=city.id, code='one', name='test-station')
                    source = SourceFile(source_key='isolated-migration', local_date=date(2026, 9, 30), kind='extra', origin='TEST', sha256='0'*64, storage_key='test-only')
                    session.add_all([station, source])
                    session.flush()
                    for basis in ('daily_max_1h', 'daily_max_8h'):
                        session.add(Observation(source_file_id=source.id, station_id=station.id, observed_at=datetime(2026, 9, 30, tzinfo=timezone.utc), local_date=date(2026, 9, 30), pollutant='O3', basis=basis, value=108, unit='ug/m3'))
                command.upgrade(config, 'head')
                command.upgrade(config, 'head')
                command.downgrade(config, 'v2_0004')
                with db.engine.connect() as rollback_connection:
                    indexes = {item['name'] for table in ('v2_jobs', 'v2_models', 'v2_source_attempts') for item in inspect(rollback_connection).get_indexes(table)}
                    self.assertTrue({'ix_v2_jobs_target_key', 'ix_v2_jobs_status_heartbeat', 'ix_v2_models_task_status', 'ix_v2_source_attempts_date_kind_status'}.isdisjoint(indexes))
                command.upgrade(config, 'head')
            with db.engine.connect() as connection:
                self.assertEqual(connection.scalar(text('SELECT version_num FROM v2_alembic_version')), 'v2_0005')
                differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
                self.assertEqual([d for d in differences if 'v2_alembic_version' not in str(d)], [])
            with db.sessions() as session:
                observations = session.scalars(select(Observation)).all()
                self.assertEqual({o.basis for o in observations}, {'rolling_max_24h', 'rolling_max_8h_24h'})
                self.assertEqual([o.value for o in observations], [108, 108])
        finally:
            db.engine.dispose()
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()

