from alembic import context
from app.persistence import Database, metadata

db = Database()
with db.engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(4710000)")
        context.run_migrations()
