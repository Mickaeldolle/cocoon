"""The additive migration preserves sources and its downgrade is executable."""

import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, MetaData, String, Table, Uuid, create_engine, inspect, select


def test_memory_migration_preserves_existing_sources_and_can_downgrade():
    path = Path(__file__).parents[1] / "migrations/versions/20261006_39_personal_memory.py"
    spec = importlib.util.spec_from_file_location("memory_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for name in ("users", "assistant_threads", "assistant_messages"):
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    memory = Table(
        "memory_items",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("summary", String(240)),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        memory_id = uuid4()
        connection.execute(memory.insert().values(id=memory_id, summary="Source conservée"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert "memory_exclusions" in inspect(connection).get_table_names()
            assert "context_dependencies" in inspect(connection).get_table_names()
            assert connection.scalar(select(memory.c.summary)) == "Source conservée"
            migration.downgrade()
            assert "memory_exclusions" not in inspect(connection).get_table_names()
            assert connection.scalar(select(memory.c.summary)) == "Source conservée"
    engine.dispose()
