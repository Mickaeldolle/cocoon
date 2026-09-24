from fastapi import APIRouter, Depends

from app.modules.auth.dependencies import require_superadmin
from app.modules.auth.models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/status")
def status(current_user: User = Depends(require_superadmin)) -> dict[str, str]:
    """Minimal protected probe for the future administration interface."""
    return {"status": "ok", "email": current_user.email}
