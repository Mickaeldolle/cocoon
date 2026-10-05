"""OpenRouter's currently listed, text-capable free chat models."""

import threading
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from time import monotonic
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings

CATALOG_TTL_SECONDS = 300
_catalog_lock = threading.Lock()
_catalog_key: tuple[str, str] | None = None
_catalog_until = 0.0
_catalog_models: tuple["FreeModel", ...] = ()


@dataclass(frozen=True)
class FreeModel:
    id: str
    name: str


class FreeModelCatalogError(Exception):
    """The free catalog cannot be checked safely right now."""


def uses_openrouter(settings: Settings) -> bool:
    base_url = settings.llm_base_url or settings.llm_api_url or ""
    parsed = urlsplit(base_url.rstrip("/"))
    return (
        settings.llm_provider == "openai_compatible"
        and parsed.scheme == "https"
        and parsed.hostname == "openrouter.ai"
        and parsed.port is None
        and parsed.path == "/api/v1"
        and not parsed.query
        and not parsed.fragment
    )


def _is_zero_priced(pricing: object) -> bool:
    if not isinstance(pricing, dict) or not pricing:
        return False
    try:
        return all(Decimal(str(value)) == 0 for value in pricing.values())
    except (InvalidOperation, TypeError, ValueError):
        return False


def _parse_catalog(body: object) -> tuple[FreeModel, ...]:
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise FreeModelCatalogError
    models: dict[str, FreeModel] = {}
    for item in body["data"]:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        architecture = item.get("architecture")
        inputs = architecture.get("input_modalities") if isinstance(architecture, dict) else None
        outputs = architecture.get("output_modalities") if isinstance(architecture, dict) else None
        if (
            not isinstance(model_id, str)
            or (not model_id.endswith(":free") and model_id != "openrouter/free")
            or not _is_zero_priced(item.get("pricing"))
            or not isinstance(inputs, list)
            or "text" not in inputs
            or not isinstance(outputs, list)
            or "text" not in outputs
        ):
            continue
        name = item.get("name")
        models[model_id] = FreeModel(
            id=model_id,
            name=name.strip()[:120] if isinstance(name, str) and name.strip() else model_id,
        )
    return tuple(
        sorted(models.values(), key=lambda item: (item.id != "openrouter/free", item.name.lower()))
    )


def free_models(settings: Settings) -> tuple[FreeModel, ...]:
    if not uses_openrouter(settings) or not settings.llm_api_key:
        raise FreeModelCatalogError
    global _catalog_key, _catalog_until, _catalog_models
    key = (settings.llm_base_url or settings.llm_api_url or "", settings.llm_api_key)
    with _catalog_lock:
        if _catalog_key == key and monotonic() < _catalog_until:
            return _catalog_models
        try:
            with httpx.Client(timeout=8, trust_env=False) as client:
                response = client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                )
                response.raise_for_status()
                models = _parse_catalog(response.json())
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise FreeModelCatalogError from error
        if not models:
            raise FreeModelCatalogError
        _catalog_key = key
        _catalog_models = models
        _catalog_until = monotonic() + CATALOG_TTL_SECONDS
        return models


def select_free_model(settings: Settings, requested: str) -> str:
    if requested not in {model.id for model in free_models(settings)}:
        raise ValueError("Ce modèle gratuit n'est plus disponible.")
    return requested
