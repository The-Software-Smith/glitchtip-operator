import pytest

from glitchtip_operator.reconcile import ConflictError, sync_alert

PAYLOAD = {
    "name": "errors",
    "timespanMinutes": 1,
    "quantity": 1,
    "uptime": False,
    "alertRecipients": [{"recipientType": "webhook", "url": "https://h/x", "tagsToAdd": []}],
}


def stored(alert_id, name="errors", quantity=1):
    return {
        "id": alert_id,
        "name": name,
        "timespanMinutes": 1,
        "quantity": quantity,
        "uptime": False,
        "alertRecipients": [
            {
                "id": 1,
                "recipientType": "webhook",
                "url": "https://h/x",
                "config": {},
                "tagsToAdd": [],
            }
        ],
    }


class FakeClient:
    def __init__(self, alerts):
        self.alerts = alerts
        self.calls = []

    async def list_alerts(self, organization, project):
        return self.alerts

    async def create_alert(self, organization, project, payload):
        self.calls.append(("create", payload))
        return {"id": 99}

    async def update_alert(self, organization, project, alert_id, payload):
        self.calls.append(("update", alert_id))
        return {"id": alert_id}


async def sync(client, known_id=None):
    return await sync_alert(
        client, organization="acme", project="api", payload=PAYLOAD, known_id=known_id
    )


async def test_creates_when_missing():
    client = FakeClient([stored(1, name="other")])
    result = await sync(client)
    assert (result.action, result.alert_id) == ("created", 99)


async def test_adopts_by_name():
    client = FakeClient([stored(4)])
    result = await sync(client)
    assert (result.action, result.alert_id) == ("unchanged", 4)
    assert client.calls == []


async def test_updates_known_alert_even_if_renamed_in_ui():
    client = FakeClient([stored(4, name="renamed", quantity=3)])
    result = await sync(client, known_id=4)
    assert (result.action, result.alert_id) == ("updated", 4)
    assert client.calls == [("update", 4)]


async def test_recreates_when_known_alert_was_deleted():
    client = FakeClient([])
    result = await sync(client, known_id=4)
    assert result.action == "created"


async def test_refuses_to_guess_between_duplicates():
    client = FakeClient([stored(4), stored(5)])
    with pytest.raises(ConflictError, match="ids 4, 5"):
        await sync(client)
