from collections.abc import Generator
from os import environ

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def engine_options(database_url: str, *, serverless: bool) -> dict[str, object]:
    """Avoid retaining one database session per warm serverless instance."""
    url = make_url(database_url)
    is_postgres = url.get_backend_name() == "postgresql"
    host = (url.host or "").lower()
    is_transaction_pooler = (
        is_postgres
        and (
            host.endswith(".pooler.supabase.com")
            or (host.startswith("db.") and host.endswith(".supabase.co"))
        )
        and url.port == 6543
    )
    if is_postgres and (serverless or is_transaction_pooler):
        options: dict[str, object] = {"poolclass": NullPool}
    else:
        options = {"pool_pre_ping": True}
    if is_transaction_pooler:
        options["connect_args"] = {"prepare_threshold": None}
    return options


settings = get_settings()
engine = create_engine(
    settings.database_url,
    **engine_options(settings.database_url, serverless=environ.get("VERCEL") == "1"),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
