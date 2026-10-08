"""The additive migration preserves sources and its downgrade is executable."""

import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Column, MetaData, String, Table, Uuid, create_engine, inspect, select


def test_memory_migration_preserves_existing_sources_and_can_downgrade():
    path = Path(__file__).parents[1] / "migrations/versions/20261008_40_personal_memory.py"
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


def test_alembic_has_one_head_and_memory_follows_welcome():
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["20261008_40"]
    assert scripts.get_revision("20261008_40").down_revision == "20261006_39"
