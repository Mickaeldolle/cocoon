"""Run the private reminder outbox worker; schedule it as a separate service."""

import calendar
import json
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.modules.assistant.models import AssistantPreference, NotificationOutbox, RecurringReminder
from app.modules.auth.models import Device
from app.modules.personal.models import PersonalTask

MAX_CATCH_UP_OCCURRENCES = 12
LEASE_SECONDS = 600
RETRY_BASE_SECONDS = 30


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def reminder_at(due_date: date, lead_days: int, timezone: str) -> datetime:
    local = datetime.combine(
        due_date - timedelta(days=lead_days), clock_time(9, 0), tzinfo=ZoneInfo(timezone)
    )
    return local.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _quota_available(session, user_id, now: datetime) -> bool:
    preference = session.get(AssistantPreference, user_id)
    quota = preference.daily_notification_quota if preference is not None else 20
    timezone = ZoneInfo(preference.timezone) if preference is not None else UTC
    local_day = now.astimezone(timezone).date()
    start = datetime.combine(local_day, clock_time.min, timezone).astimezone(UTC)
    end = datetime.combine(local_day + timedelta(days=1), clock_time.min, timezone).astimezone(UTC)
    count = session.scalar(
        select(func.count(NotificationOutbox.id)).where(
            NotificationOutbox.user_id == user_id,
            NotificationOutbox.created_at >= start,
            NotificationOutbox.created_at < end,
            NotificationOutbox.cancelled_at.is_(None),
        )
    )
    return int(count or 0) < quota


def _add_outbox(
    session,
    *,
    user_id,
    key: str,
    kind: str,
    now: datetime,
    target_type: str | None = None,
    target_id: str | None = None,
) -> bool:
    if session.scalar(select(NotificationOutbox.id).where(NotificationOutbox.dedupe_key == key)):
        return False
    if not _quota_available(session, user_id, now):
        return False
    data: dict[str, object] = {"kind": kind}
    if target_type is not None and target_id is not None:
        data.update({"target_type": target_type, "target_id": target_id})
    session.add(
        NotificationOutbox(
            user_id=user_id,
            dedupe_key=key,
            title="Cocoon",
            body="Vous avez un rappel à consulter.",
            data=data,
        )
    )
    return True


def queue_pending_notifications(now: datetime) -> int:
    """Persist due occurrences before attempting delivery; safe to rerun after downtime."""
    queued = 0
    with SessionLocal() as session:
        tasks = session.scalars(
            select(PersonalTask).where(
                PersonalTask.completed.is_(False),
                PersonalTask.reminder_at.is_not(None),
                PersonalTask.reminder_at <= now,
            )
        )
        for task in tasks:
            queued += _add_outbox(
                session,
                user_id=task.user_id,
                key=f"reminder:{task.id}",
                kind="reminder",
                now=now,
                target_type="personal_task",
                target_id=str(task.id),
            )

        recurring = session.scalars(
            select(RecurringReminder).where(
                RecurringReminder.active.is_(True), RecurringReminder.next_reminder_at <= now
            )
        )
        for reminder in recurring:
            occurrences = 0
            while (
                _as_utc(reminder.next_reminder_at) <= now
                and occurrences < MAX_CATCH_UP_OCCURRENCES
            ):
                key = f"recurring-reminder:{reminder.id}:{reminder.next_due_date.isoformat()}"
                already_queued = session.scalar(
                    select(NotificationOutbox.id).where(NotificationOutbox.dedupe_key == key)
                )
                if already_queued is None:
                    # Keep the occurrence pending when quota is exhausted. Advancing it
                    # here would lose the reminder without an outbox row to consult.
                    if not _quota_available(session, reminder.user_id, now):
                        break
                    queued += _add_outbox(
                        session,
                        user_id=reminder.user_id,
                        key=key,
                        kind="recurring_reminder",
                        now=now,
                        target_type="recurring_reminder",
                        target_id=str(reminder.id),
                    )
                reminder.next_due_date = add_months(
                    reminder.next_due_date, reminder.recurrence_months
                )
                reminder.next_reminder_at = reminder_at(
                    reminder.next_due_date, reminder.lead_days, reminder.timezone
                )
                occurrences += 1

        preferences = session.scalars(
            select(AssistantPreference).where(AssistantPreference.enabled.is_(True))
        )
        for preference in preferences:
            local_now = now.astimezone(ZoneInfo(preference.timezone))
            if local_now.strftime("%H:%M") == preference.delivery_time:
                key = f"brief:{preference.user_id}:{local_now.date().isoformat()}"
                queued += _add_outbox(
                    session, user_id=preference.user_id, key=key, kind="daily_brief", now=now
                )
        session.commit()
    return queued


def _claim_one(session, worker_id: str, now: datetime) -> NotificationOutbox | None:
    item = session.scalar(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.sent_at.is_(None),
            NotificationOutbox.failed_at.is_(None),
            NotificationOutbox.cancelled_at.is_(None),
            or_(
                NotificationOutbox.next_attempt_at.is_(None),
                NotificationOutbox.next_attempt_at <= now,
            ),
            or_(NotificationOutbox.lease_until.is_(None), NotificationOutbox.lease_until <= now),
        )
        .order_by(NotificationOutbox.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if item is None:
        return None
    item.lease_owner = worker_id
    item.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    item.attempts += 1
    session.commit()
    return item


def _finish(
    session, item_id, worker_id: str, now: datetime, *, error: str | None = None, ticket=None
) -> bool:
    item = session.scalar(select(NotificationOutbox).where(NotificationOutbox.id == item_id))
    if item is None or item.lease_owner != worker_id:
        return False
    item.lease_owner = None
    item.lease_until = None
    if error is None:
        item.sent_at = now
        item.provider_ticket = ticket
        item.provider_status = "accepted"
    elif error == "no_device" or item.attempts >= item.max_attempts:
        item.failed_at = now
        item.last_error_code = error
        item.provider_status = "failed"
    else:
        item.last_error_code = error
        item.provider_status = "retrying"
        item.next_attempt_at = now + timedelta(
            seconds=RETRY_BASE_SECONDS * (2 ** (item.attempts - 1))
        )
    session.commit()
    return True


def _disable_invalid_tokens(session, tokens: list[str | None], ticket: object) -> None:
    if not isinstance(ticket, dict) or not isinstance(ticket.get("data"), list):
        return
    for token, result in zip(tokens, ticket["data"], strict=False):
        if (
            token
            and isinstance(result, dict)
            and result.get("status") == "error"
            and isinstance(result.get("details"), dict)
            and result["details"].get("error") == "DeviceNotRegistered"
        ):
            device = session.scalar(select(Device).where(Device.push_token == token))
            if device is not None:
                device.push_token = None


def _attach_ticket_devices(ticket: object, devices: list[Device]) -> object:
    """Keep a non-secret device reference for asynchronous receipt handling."""
    if not isinstance(ticket, dict) or not isinstance(ticket.get("data"), list):
        return ticket
    data: list[object] = []
    for device, result in zip(devices, ticket["data"], strict=False):
        if isinstance(result, dict):
            data.append({**result, "device_id": str(device.id)})
        else:
            data.append(result)
    return {**ticket, "data": data}


def send_pending_notifications(now: datetime) -> int:
    settings = get_settings()
    worker_id = f"reminder-worker-{uuid4()}"
    sent = 0
    while True:
        with SessionLocal() as session:
            item = _claim_one(session, worker_id, now)
            if item is None:
                break
            devices = list(
                session.scalars(
                    select(Device).where(
                        Device.user_id == item.user_id, Device.push_token.is_not(None)
                    )
                )
            )
            tokens = [device.push_token for device in devices]
            if not tokens:
                _finish(session, item.id, worker_id, now, error="no_device")
                continue
            payload = [
                {"to": token, "title": item.title, "body": item.body, "data": item.data}
                for token in tokens
            ]
            request = Request(
                settings.expo_push_endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=10) as response:  # noqa: S310
                    if not 200 <= response.status < 300:
                        raise HTTPError(
                            settings.expo_push_endpoint,
                            response.status,
                            "push failed",
                            {},
                            None,
                        )
                    raw = response.read()
                    ticket = json.loads(raw.decode("utf-8")) if raw else None
            except (HTTPError, URLError, TimeoutError, ValueError):
                _finish(session, item.id, worker_id, now, error="provider_unavailable")
                continue
            _disable_invalid_tokens(session, tokens, ticket)
            ticket = _attach_ticket_devices(ticket, devices)
            if _finish(session, item.id, worker_id, now, ticket=ticket):
                sent += 1
    return sent


def refresh_provider_receipts(now: datetime) -> int:
    """Poll Expo receipts without confusing provider delivery with user reading."""
    settings = get_settings()
    receipt_endpoint = settings.expo_push_endpoint.rsplit("/", maxsplit=1)[0] + "/getReceipts"
    updated = 0
    with SessionLocal() as session:
        items = list(
            session.scalars(
                select(NotificationOutbox).where(
                    NotificationOutbox.provider_status == "accepted",
                    NotificationOutbox.provider_ticket.is_not(None),
                    NotificationOutbox.cancelled_at.is_(None),
                ).limit(100)
            )
        )
        ticket_items: dict[str, NotificationOutbox] = {}
        ticket_devices: dict[str, str] = {}
        for item in items:
            ticket = item.provider_ticket
            if not isinstance(ticket, dict) or not isinstance(ticket.get("data"), list):
                continue
            for result in ticket["data"]:
                if isinstance(result, dict) and isinstance(result.get("id"), str):
                    ticket_items[result["id"]] = item
                    if isinstance(result.get("device_id"), str):
                        ticket_devices[result["id"]] = result["device_id"]
        if not ticket_items:
            return 0
        request = Request(
            receipt_endpoint,
            data=json.dumps({"ids": list(ticket_items)}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310
                if not 200 <= response.status < 300:
                    return 0
                body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError):
            return 0
        receipts = body.get("data") if isinstance(body, dict) else None
        if not isinstance(receipts, dict):
            return 0
        for ticket_id, receipt in receipts.items():
            item = ticket_items.get(ticket_id)
            if item is None or not isinstance(receipt, dict):
                continue
            status_value = receipt.get("status")
            if status_value not in {"ok", "error"}:
                continue
            if (
                status_value == "error"
                and isinstance(receipt.get("details"), dict)
                and receipt["details"].get("error") == "DeviceNotRegistered"
            ):
                device_id = ticket_devices.get(ticket_id)
                if isinstance(device_id, str):
                    try:
                        device = session.scalar(select(Device).where(Device.id == UUID(device_id)))
                    except ValueError:
                        device = None
                    if device is not None:
                        device.push_token = None
            item.provider_receipt = {"id": ticket_id, **receipt}
            item.provider_status = "delivered" if status_value == "ok" else "receipt_failed"
            item.updated_at = now
            updated += 1
        session.commit()
    return updated


def process_once() -> tuple[int, int]:
    now = datetime.now(UTC)
    queued = queue_pending_notifications(now)
    refresh_provider_receipts(now)
    return queued, send_pending_notifications(now)


def main() -> None:
    settings = get_settings()
    while True:
        queued, sent = process_once()
        print(f"reminder-worker queued={queued} sent={sent}", flush=True)
        time.sleep(settings.worker_interval_seconds)


if __name__ == "__main__":
    main()
