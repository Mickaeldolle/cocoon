from sqlalchemy.pool import NullPool

from app.core.database import engine_options


def test_vercel_does_not_keep_session_pooler_connections_open() -> None:
    options = engine_options(
        "postgresql+psycopg://user:password@aws-1-eu-west-1.pooler.supabase.com:5432/postgres",
        serverless=True,
    )
    assert options["poolclass"] is NullPool
    assert "connect_args" not in options


def test_transaction_pooler_disables_prepared_statements() -> None:
    options = engine_options(
        "postgresql+psycopg://user:password@aws-1-eu-west-1.pooler.supabase.com:6543/postgres",
        serverless=False,
    )
    assert options["poolclass"] is NullPool
    assert options["connect_args"] == {"prepare_threshold": None}


def test_regular_local_database_keeps_existing_pool_behavior() -> None:
    assert engine_options("sqlite:///./cocoon.db", serverless=False) == {"pool_pre_ping": True}
