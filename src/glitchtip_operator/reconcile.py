from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import GlitchTipClient
from .spec import normalize


class ConflictError(Exception):
    pass


@dataclass(frozen=True)
class SyncResult:
    action: str
    alert_id: int


async def sync_alert(
    client: GlitchTipClient,
    *,
    organization: str,
    project: str,
    payload: dict[str, Any],
    known_id: int | None,
) -> SyncResult:
    alerts = await client.list_alerts(organization, project)

    current = next((a for a in alerts if a["id"] == known_id), None) if known_id else None
    if current is None:
        named = [a for a in alerts if a.get("name") == payload["name"]]
        if len(named) > 1:
            ids = ", ".join(str(a["id"]) for a in named)
            raise ConflictError(
                f"{len(named)} alerts named {payload['name']!r} exist in "
                f"{organization}/{project} (ids {ids}); remove the extras or set spec.name"
            )
        current = named[0] if named else None

    if current is None:
        created = await client.create_alert(organization, project, payload)
        return SyncResult("created", created["id"])
    if normalize(current) != normalize(payload):
        await client.update_alert(organization, project, current["id"], payload)
        return SyncResult("updated", current["id"])
    return SyncResult("unchanged", current["id"])
