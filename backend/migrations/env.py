from alembic import context

from auditor.config import Settings
from auditor.history import HistoryStore
from auditor.history_schema import metadata


def run(connection):
    context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
elif context.is_offline_mode():
    raise RuntimeError("Use scripts/setup-history.py for this local SQLite migration environment.")
else:
    store = HistoryStore(Settings())
    try:
        if not store.path.is_file():
            raise RuntimeError("Initialize the runtime using scripts/setup-history.py first.")
        with store.engine.begin() as connection:
            run(connection)
    finally:
        store.close()
