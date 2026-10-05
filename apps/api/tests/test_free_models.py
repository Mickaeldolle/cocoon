import pytest

from app.core.config import Settings
from app.modules.assistant import free_models as catalog


def settings(base_url: str = "https://openrouter.ai/api/v1") -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret="test-secret-that-is-long-enough-for-validation",
        llm_provider="openai_compatible",
        llm_base_url=base_url,
        llm_api_key="test-key",
        llm_model="openrouter/free",
    )


def model(model_id: str, prompt: str = "0", completion: str = "0") -> dict:
    return {
        "id": model_id,
        "name": model_id,
        "pricing": {"prompt": prompt, "completion": completion},
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
    }


def test_catalog_excludes_paid_non_chat_and_unpriced_models() -> None:
    paid = model("vendor/paid:free", completion="0.001")
    image = model("vendor/image:free")
    image["architecture"]["output_modalities"] = ["image"]
    missing_price = model("vendor/unknown:free")
    missing_price.pop("pricing")
    result = catalog._parse_catalog(
        {"data": [model("openrouter/free"), model("vendor/chat:free"), paid, image,
                  missing_price, model("vendor/zero-without-free-suffix")]}
    )
    assert [item.id for item in result] == ["openrouter/free", "vendor/chat:free"]


def test_selected_model_must_be_listed_free_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        catalog, "free_models", lambda _settings: (catalog.FreeModel("vendor/chat:free", "Chat"),)
    )
    assert catalog.select_free_model(settings(), "vendor/chat:free") == "vendor/chat:free"
    with pytest.raises(ValueError, match="plus disponible"):
        catalog.select_free_model(settings(), "vendor/paid")


def test_catalog_only_applies_to_exact_openrouter_api_root() -> None:
    assert catalog.uses_openrouter(settings())
    assert not catalog.uses_openrouter(settings("https://openrouter.ai/api/v1/chat/completions"))
    assert not catalog.uses_openrouter(settings("https://example.com/api/v1"))
