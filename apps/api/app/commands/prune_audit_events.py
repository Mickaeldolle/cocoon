"""Remove audit metadata beyond its configured retention period."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.modules.audit.models import AuditEvent


def main() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=get_settings().audit_retention_days)
    with SessionLocal.begin() as session:
        result = session.execute(delete(AuditEvent).where(AuditEvent.occurred_at < cutoff))
    print(f"audit_events_pruned={result.rowcount}")


if __name__ == "__main__":
    main()
