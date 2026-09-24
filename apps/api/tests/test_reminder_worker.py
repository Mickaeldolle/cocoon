import json
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.commands import run_reminder_worker as worker
from app.modules.assistant.models import AssistantPreference, NotificationOutbox, RecurringReminder
from app.modules.auth.models import Device, User


def _user(client: TestClient):
    client.post(
        "/api/auth/register",
        json={
            "email": "reminders@example.com",
            "password": "A-strong-password-123",
            "display_name": "Reminder user",
            "installation_id": "reminder-device",
            "name": "Reminder device",
            "platform": "ios",
        },
    )
    session = client.app.state.test_session_factory()
    try:
        return session.query(User).one().id
    finally:
        session.close()


def test_recurring_reminder_catches_up_and_is_idempotent(
    client: TestClient, monkeypatch
) -> None:
    user_id = _user(client)
    session_factory = client.app.state.test_session_factory
    session = session_factory()
    session.add(
        RecurringReminder(
            user_id=user_id,
            title="Contrôle",
            anchor_date=date(2024, 1, 31),
            recurrence_months=1,
            lead_days=0,
            next_due_date=date(2024, 1, 31),
            next_reminder_at=datetime(2024, 1, 31, 9, tzinfo=UTC),
            timezone="Europe/Paris",
        )
    )
    session.commit()
    session.close()
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    now = datetime(2024, 4, 1, tzinfo=UTC)
    assert worker.queue_pending_notifications(now) == 3
    assert worker.queue_pending_notifications(now) == 0

    session = session_factory()
    try:
        keys = [item.dedupe_key for item in session.query(NotificationOutbox).all()]
        reminder = session.query(RecurringReminder).one()
        assert keys == [
            "recurring-reminder:" + keys[0].split(":")[1] + ":2024-01-31",
            "recurring-reminder:" + keys[0].split(":")[1] + ":2024-02-29",
            "recurring-reminder:" + keys[0].split(":")[1] + ":2024-03-29",
        ]
        assert reminder.next_due_date == date(2024, 4, 29)
    finally:
        session.close()


def test_month_end_calculation_is_deterministic() -> None:
    assert worker.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert worker.add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)


def test_outbox_lease_prevents_second_claim_until_expired(client: TestClient) -> None:
    user_id = _user(client)
    session_factory = client.app.state.test_session_factory
    session = session_factory()
    item = NotificationOutbox(
        user_id=user_id,
        dedupe_key="lease-test",
        title="Cocoon",
        body="Rappel",
        data={"kind": "reminder"},
    )
    session.add(item)
    session.commit()
    now = datetime(2026, 9, 22, tzinfo=UTC)
    assert worker._claim_one(session, "worker-a", now) is not None
    assert worker._claim_one(session, "worker-b", now) is None
    session.close()


def test_notification_without_device_is_terminal_and_remains_consultable(
    client: TestClient, monkeypatch
) -> None:
    user_id = _user(client)
    session_factory = client.app.state.test_session_factory
    session = session_factory()
    item = NotificationOutbox(
        user_id=user_id,
        dedupe_key="no-device-test",
        title="Cocoon",
        body="Rappel",
        data={"kind": "reminder"},
    )
    session.add(item)
    session.commit()
    item_id = item.id
    session.close()
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    assert worker.send_pending_notifications(datetime(2026, 9, 22, tzinfo=UTC)) == 0

    session = session_factory()
    try:
        stored = session.get(NotificationOutbox, item_id)
        assert stored is not None
        assert stored.failed_at is not None
        assert stored.provider_status == "failed"
        assert stored.last_error_code == "no_device"
        assert stored.attempts == 1
    finally:
        session.close()


def test_recurring_reminder_can_be_modified_and_cancelled(client: TestClient, monkeypatch) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "controls@example.com",
            "password": "A-strong-password-123",
            "display_name": "Controls user",
            "installation_id": "controls-device",
            "name": "Controls device",
            "platform": "ios",
        },
    )
    auth = {"Authorization": f"Bearer {response.json()['access_token']}"}
    session_factory = client.app.state.test_session_factory
    session = session_factory()
    user_id = session.query(User).filter(User.email == "controls@example.com").one().id
    reminder = RecurringReminder(
        user_id=user_id,
        title="Vidange",
        anchor_date=date(2026, 1, 10),
        recurrence_months=12,
        lead_days=7,
        next_due_date=date(2027, 1, 10),
        next_reminder_at=datetime(2027, 1, 3, 8, tzinfo=UTC),
        timezone="Europe/Paris",
    )
    session.add(reminder)
    session.add(AssistantPreference(user_id=user_id, daily_notification_quota=1))
    session.commit()
    reminder_id = str(reminder.id)
    session.close()

    updated = client.patch(
        f"/api/assistant/reminders/{reminder_id}",
        headers=auth,
        json={"lead_days": 2, "timezone": "UTC"},
    )
    assert updated.status_code == 200
    assert updated.json()["next_reminder_at"].startswith("2027-01-08")

    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    assert worker.queue_pending_notifications(datetime(2027, 1, 9, tzinfo=UTC)) == 1
    assert client.delete(f"/api/assistant/reminders/{reminder_id}", headers=auth).status_code == 204
    session = session_factory()
    try:
        item = session.query(NotificationOutbox).one()
        assert item.cancelled_at is not None
        assert item.data["target_type"] == "recurring_reminder"
        assert item.data["target_id"] == reminder_id
    finally:
        session.close()


def test_recurring_reminder_stays_pending_when_quota_is_exhausted(
    client: TestClient, monkeypatch
) -> None:
    user_id = _user(client)
    session_factory = client.app.state.test_session_factory
    session = session_factory()
    reminder = RecurringReminder(
        user_id=user_id,
        title="Contrôle quota",
        anchor_date=date(2026, 1, 1),
        recurrence_months=1,
        lead_days=0,
        next_due_date=date(2026, 9, 22),
        next_reminder_at=datetime(2026, 9, 22, 9, tzinfo=UTC),
        timezone="UTC",
    )
    session.add(reminder)
    session.add(AssistantPreference(user_id=user_id, daily_notification_quota=0))
    session.commit()
    session.close()
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    now = datetime(2026, 9, 22, 12, tzinfo=UTC)

    assert worker.queue_pending_notifications(now) == 0
    session = session_factory()
    try:
        stored = session.query(RecurringReminder).one()
        assert stored.next_due_date == date(2026, 9, 22)
        session.query(AssistantPreference).filter(
            AssistantPreference.user_id == user_id
        ).one().daily_notification_quota = 1
        session.commit()
    finally:
        session.close()

    assert worker.queue_pending_notifications(now) == 1


def test_provider_receipt_and_user_read_are_distinct(client: TestClient, monkeypatch) -> None:
    user_id = _user(client)
    session_factory = client.app.state.test_session_factory
    session = session_factory()
    item = NotificationOutbox(
        user_id=user_id,
        dedupe_key="receipt-test",
        title="Cocoon",
        body="Rappel",
        data={"kind": "reminder"},
        provider_status="accepted",
        provider_ticket={"data": [{"id": "ticket-1"}]},
        sent_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    session.add(item)
    session.commit()
    item_id = item.id
    session.close()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"data": {"ticket-1": {"status": "ok"}}}).encode()

    monkeypatch.setattr(worker, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    assert worker.refresh_provider_receipts(datetime(2026, 9, 22, tzinfo=UTC)) == 1

    session = session_factory()
    try:
        stored = session.get(NotificationOutbox, item_id)
        assert stored is not None
        assert stored.provider_status == "delivered"
        assert stored.read_at is None
    finally:
        session.close()


def test_provider_receipt_disables_device_not_registered_token(
    client: TestClient, monkeypatch
) -> None:
    user_id = _user(client)
    session_factory = client.app.state.test_session_factory
    session = session_factory()
    device = Device(
        user_id=user_id,
        installation_id="receipt-invalid-device",
        name="Receipt invalid device",
        platform="ios",
        push_token="ExponentPushToken[receipt-invalid]",
    )
    session.add(device)
    session.flush()
    item = NotificationOutbox(
        user_id=user_id,
        dedupe_key="receipt-invalid-test",
        title="Cocoon",
        body="Rappel",
        data={"kind": "reminder"},
        provider_status="accepted",
        provider_ticket={"data": [{"id": "ticket-invalid", "device_id": str(device.id)}]},
        sent_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    session.add(item)
    session.commit()
    item_id = item.id
    device_id = device.id
    session.close()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": {
                        "ticket-invalid": {
                            "status": "error",
                            "details": {"error": "DeviceNotRegistered"},
                        }
                    }
                }
            ).encode()

    monkeypatch.setattr(worker, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    assert worker.refresh_provider_receipts(datetime(2026, 9, 22, tzinfo=UTC)) == 1

    session = session_factory()
    try:
        stored_device = session.get(Device, device_id)
        stored_item = session.get(NotificationOutbox, item_id)
        assert stored_device is not None
        assert stored_device.push_token is None
        assert stored_item is not None
        assert stored_item.provider_status == "receipt_failed"
    finally:
        session.close()


def test_invalid_device_token_is_disabled_without_blocking_other_devices(
    client: TestClient, monkeypatch
) -> None:
    user_id = _user(client)
    session_factory = client.app.state.test_session_factory
    session = session_factory()
    session.add_all(
        [
            Device(
                user_id=user_id,
                installation_id="invalid-installation",
                name="Invalid device",
                platform="ios",
                push_token="ExponentPushToken[invalid]",
            ),
            Device(
                user_id=user_id,
                installation_id="valid-installation",
                name="Valid device",
                platform="android",
                push_token="ExponentPushToken[valid]",
            ),
        ]
    )
    item = NotificationOutbox(
        user_id=user_id,
        dedupe_key="multi-device-test",
        title="Cocoon",
        body="Rappel",
        data={"kind": "reminder"},
    )
    session.add(item)
    session.commit()
    item_id = item.id
    session.close()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": [
                        {
                            "status": "error",
                            "details": {"error": "DeviceNotRegistered"},
                        },
                        {"status": "ok", "id": "ticket-valid"},
                    ]
                }
            ).encode()

    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(worker, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    assert worker.send_pending_notifications(datetime(2026, 9, 22, tzinfo=UTC)) == 1

    session = session_factory()
    try:
        devices = {
            device.installation_id: device.push_token
            for device in session.query(Device).filter(Device.user_id == user_id)
        }
        stored = session.get(NotificationOutbox, item_id)
        assert devices["invalid-installation"] is None
        assert devices["valid-installation"] == "ExponentPushToken[valid]"
        assert stored is not None
        assert stored.provider_status == "accepted"
    finally:
        session.close()
