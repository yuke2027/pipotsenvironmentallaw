from alembic import context
from sqlalchemy import create_engine
from app.v2.shared.persistence import Base
from app.v2.config import Settings

config = context.config
config.set_main_option("sqlalchemy.url", Settings().database_url.replace("%", "%%"))
if context.is_offline_mode():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=Base.metadata, literal_binds=True, version_table="v2_alembic_version")
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(str(config.get_main_option("sqlalchemy.url")))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, version_table="v2_alembic_version")
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
