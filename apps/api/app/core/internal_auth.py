"""Authentication shared by bounded scheduler entrypoints."""

from hmac import compare_digest

from fastapi import HTTPException


def require_worker_token(authorization: str | None, token: str | None) -> None:
    if not token:
        raise HTTPException(status_code=404, detail="Introuvable.")
    if not compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="Non autorisé.")
