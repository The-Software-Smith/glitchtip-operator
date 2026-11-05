from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

RECIPIENT_TYPES = frozenset(
    {"email", "webhook", "discord", "googlechat", "ntfy", "teams", "zulip", "feishu"}
)
DEFAULT_ZULIP_TOPIC = "GlitchTip Alerts"

SecretReader = Callable[[str, str, str], Awaitable[str]]


class SpecError(ValueError):
    pass


async def _resolve(
    source: dict[str, Any], field: str, namespace: str, read_secret: SecretReader
) -> str | None:
    value = source.get(field)
    ref = (source.get(f"{field}From") or {}).get("secretKeyRef")
    if value and ref:
        raise SpecError(f"set only one of {field} and {field}From")
    if ref:
        return await read_secret(namespace, ref["name"], ref["key"])
    return value


async def build_recipient(
    recipient: dict[str, Any], namespace: str, read_secret: SecretReader
) -> dict[str, Any]:
    kind = recipient.get("type")
    if kind not in RECIPIENT_TYPES:
        raise SpecError(f"unknown recipient type {kind!r}")
    url = await _resolve(recipient, "url", namespace, read_secret)
    if kind != "email" and not url:
        raise SpecError(f"recipient of type {kind!r} needs url or urlFrom")

    payload: dict[str, Any] = {
        "recipientType": kind,
        "url": (url or "").strip(),
        "tagsToAdd": list(recipient.get("tagsToAdd") or []),
    }
    if kind == "zulip":
        zulip = recipient.get("zulip") or {}
        api_key = await _resolve(zulip, "apiKey", namespace, read_secret)
        if not (zulip.get("botEmail") and api_key and zulip.get("channel")):
            raise SpecError(
                "zulip recipient needs zulip.botEmail, zulip.apiKeyFrom and zulip.channel"
            )
        payload |= {
            "botEmail": zulip["botEmail"],
            "apiKey": api_key.strip(),
            "channel": zulip["channel"],
            "topic": zulip.get("topic") or DEFAULT_ZULIP_TOPIC,
        }
    return payload


async def build_payload(
    spec: dict[str, Any], *, name: str, namespace: str, read_secret: SecretReader
) -> dict[str, Any]:
    errors = spec.get("errors")
    uptime = bool(spec.get("uptime", False))
    if not errors and not uptime:
        raise SpecError("set errors, uptime: true, or both")
    recipients = [
        await build_recipient(r, namespace, read_secret) for r in spec.get("recipients") or []
    ]
    keys = [(r["recipientType"], r["url"]) for r in recipients]
    if len(keys) != len(set(keys)):
        raise SpecError("recipients must have unique (type, url) pairs")
    return {
        "name": spec.get("name") or name,
        "timespanMinutes": errors["timespanMinutes"] if errors else None,
        "quantity": errors["quantity"] if errors else None,
        "uptime": uptime,
        "alertRecipients": recipients,
    }


_ZULIP_CONFIG_KEYS = {
    "botEmail": "bot_email",
    "apiKey": "api_key",
    "channel": "channel",
    "topic": "topic",
}


def _recipient_key(recipient: dict[str, Any]) -> tuple:
    config = dict(recipient.get("config") or {})
    for camel, snake in _ZULIP_CONFIG_KEYS.items():
        if camel in recipient:
            config[snake] = recipient[camel]
    return (
        recipient.get("recipientType"),
        (recipient.get("url") or "").rstrip("/"),
        tuple(recipient.get("tagsToAdd") or ()),
        tuple(sorted(config.items())),
    )


def normalize(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": alert.get("name") or "",
        "timespanMinutes": alert.get("timespanMinutes"),
        "quantity": alert.get("quantity"),
        "uptime": bool(alert.get("uptime")),
        "alertRecipients": sorted(_recipient_key(r) for r in alert.get("alertRecipients") or []),
    }
