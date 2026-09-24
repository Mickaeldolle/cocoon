from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.database import Base
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.conversations import models as conversation_models  # noqa: F401
from app.modules.family_spaces import models as family_space_models  # noqa: F401
from app.modules.personal import models as personal_models  # noqa: F401
from app.modules.assistant import models as assistant_models  # noqa: F401
from app.modules.neural import models as neural_models  # noqa: F401

config = context.config
# Alembic stores this value in ConfigParser, where '%' begins an interpolation.
# Preserve URL-encoded password characters such as '%3F'.
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
