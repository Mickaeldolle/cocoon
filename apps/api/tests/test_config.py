import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_blank_optional_vercel_settings_do_not_prevent_startup() -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret="test-only-secret-with-at-least-thirty-two-characters",
        assistant_runtime="",
        metrics_token="",
    )

    assert settings.assistant_runtime == "local"
    assert settings.metrics_token is None


def test_plain_supabase_url_uses_installed_psycopg_driver() -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret="test-only-secret-with-at-least-thirty-two-characters",
        database_url="postgresql://user:password@localhost:5432/cocoon",
    )

    assert settings.database_url == "postgresql+psycopg://user:password@localhost:5432/cocoon"


@pytest.mark.parametrize(
    "field,value", [("assistant_runtime", "remote"), ("metrics_token", "short")]
)
def test_invalid_nonblank_settings_still_fail(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            jwt_secret="test-only-secret-with-at-least-thirty-two-characters",
            **{field: value},
        )
