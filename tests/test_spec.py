import pytest

from glitchtip_operator.spec import SpecError, build_payload, normalize

SECRETS = {("apps", "slack", "url"): "https://hooks.slack.com/services/T0/B0/x\n"}


async def read_secret(namespace, name, key):
    return SECRETS[(namespace, name, key)]


async def build(spec, name="my-alert"):
    return await build_payload(spec, name=name, namespace="apps", read_secret=read_secret)


async def test_builds_payload_from_secret_ref():
    payload = await build(
        {
            "organization": "acme",
            "project": "api",
            "errors": {"quantity": 1, "timespanMinutes": 1},
            "recipients": [
                {
                    "type": "webhook",
                    "urlFrom": {"secretKeyRef": {"name": "slack", "key": "url"}},
                    "tagsToAdd": ["service"],
                }
            ],
        }
    )
    assert payload == {
        "name": "my-alert",
        "timespanMinutes": 1,
        "quantity": 1,
        "uptime": False,
        "alertRecipients": [
            {
                "recipientType": "webhook",
                "url": "https://hooks.slack.com/services/T0/B0/x",
                "tagsToAdd": ["service"],
            }
        ],
    }


async def test_spec_name_overrides_metadata_name():
    payload = await build({"name": "Errors", "uptime": True})
    assert payload["name"] == "Errors"
    assert payload["quantity"] is None


async def test_email_recipient_needs_no_url():
    payload = await build({"uptime": True, "recipients": [{"type": "email"}]})
    assert payload["alertRecipients"] == [{"recipientType": "email", "url": "", "tagsToAdd": []}]


@pytest.mark.parametrize(
    "spec",
    [
        {},
        {"uptime": True, "recipients": [{"type": "slack", "url": "https://x"}]},
        {"uptime": True, "recipients": [{"type": "webhook"}]},
        {
            "uptime": True,
            "recipients": [
                {
                    "type": "webhook",
                    "url": "https://x",
                    "urlFrom": {"secretKeyRef": {"name": "slack", "key": "url"}},
                }
            ],
        },
        {
            "uptime": True,
            "recipients": [
                {"type": "webhook", "url": "https://x"},
                {"type": "webhook", "url": "https://x"},
            ],
        },
        {"uptime": True, "recipients": [{"type": "zulip", "url": "https://z", "zulip": {}}]},
    ],
)
async def test_rejects_invalid_spec(spec):
    with pytest.raises(SpecError):
        await build(spec)


async def test_zulip_payload_matches_stored_config():
    payload = await build(
        {
            "uptime": True,
            "recipients": [
                {
                    "type": "zulip",
                    "url": "https://zulip.example.com",
                    "zulip": {
                        "botEmail": "bot@example.com",
                        "apiKeyFrom": {"secretKeyRef": {"name": "slack", "key": "url"}},
                        "channel": "alerts",
                    },
                }
            ],
        }
    )
    stored = {
        "id": 3,
        "name": "my-alert",
        "timespanMinutes": None,
        "quantity": None,
        "uptime": True,
        "alertRecipients": [
            {
                "id": 9,
                "recipientType": "zulip",
                "url": "https://zulip.example.com/",
                "config": {
                    "bot_email": "bot@example.com",
                    "api_key": "https://hooks.slack.com/services/T0/B0/x",
                    "channel": "alerts",
                    "topic": "GlitchTip Alerts",
                },
                "tagsToAdd": None,
            }
        ],
    }
    assert normalize(payload) == normalize(stored)


async def test_normalize_detects_changes_and_ignores_order():
    payload = await build(
        {
            "errors": {"quantity": 5, "timespanMinutes": 10},
            "recipients": [
                {"type": "webhook", "url": "https://a.example.com/hook"},
                {"type": "discord", "url": "https://b.example.com/hook"},
            ],
        }
    )
    stored = {
        "id": 1,
        "name": "my-alert",
        "timespanMinutes": 10,
        "quantity": 5,
        "uptime": False,
        "alertRecipients": [
            {
                "id": 2,
                "recipientType": "discord",
                "url": "https://b.example.com/hook",
                "config": {},
                "tagsToAdd": [],
            },
            {
                "id": 1,
                "recipientType": "webhook",
                "url": "https://a.example.com/hook",
                "config": {},
                "tagsToAdd": [],
            },
        ],
    }
    assert normalize(payload) == normalize(stored)
    stored["quantity"] = 6
    assert normalize(payload) != normalize(stored)
