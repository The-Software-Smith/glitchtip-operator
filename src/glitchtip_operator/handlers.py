from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import kopf

from . import GROUP, PLURAL, VERSION
from .client import GlitchTipClient, GlitchTipError
from .reconcile import ConflictError, sync_alert
from .secrets import SecretNotFound, SecretReader
from .spec import SpecError, build_payload

RESYNC_SECONDS = float(os.environ.get("GLITCHTIP_RESYNC_SECONDS", "300"))
RETRY_SECONDS = float(os.environ.get("GLITCHTIP_RETRY_SECONDS", "60"))

_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _token() -> str:
    path = os.environ.get("GLITCHTIP_TOKEN_FILE")
    token = Path(path).read_text() if path else os.environ.get("GLITCHTIP_TOKEN", "")
    if not token.strip():
        raise RuntimeError("set GLITCHTIP_TOKEN or GLITCHTIP_TOKEN_FILE")
    return token.strip()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ready_condition(status: dict[str, Any]) -> dict[str, Any]:
    return next((c for c in status.get("conditions") or [] if c.get("type") == "Ready"), {})


def _ready(status: dict[str, Any], ok: bool, reason: str, message: str) -> list[dict[str, Any]]:
    state = "True" if ok else "False"
    previous = _ready_condition(status)
    since = previous.get("lastTransitionTime") if previous.get("status") == state else None
    return [
        {
            "type": "Ready",
            "status": state,
            "reason": reason,
            "message": message,
            "lastTransitionTime": since or _now(),
        }
    ]


def _fail(body: kopf.Body, status: dict[str, Any], patch: kopf.Patch, reason: str, exc: Exception):
    message = str(exc)
    patch.status["conditions"] = _ready(status, False, reason, message)
    previous = _ready_condition(status)
    if (previous.get("reason"), previous.get("message")) != (reason, message):
        kopf.warn(body, reason=reason, message=message)


@kopf.on.startup()
async def startup(settings: kopf.OperatorSettings, memo: kopf.Memo, **_: Any) -> None:
    url = os.environ.get("GLITCHTIP_URL")
    if not url:
        raise RuntimeError("set GLITCHTIP_URL")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    memo.glitchtip = GlitchTipClient(url, _token())
    memo.read_secret = SecretReader()
    settings.persistence.finalizer = f"{GROUP}/finalizer"
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage(prefix=GROUP)
    settings.persistence.diffbase_storage = kopf.AnnotationsDiffBaseStorage(
        prefix=GROUP, key="last-handled-configuration"
    )


@kopf.on.cleanup()
async def cleanup(memo: kopf.Memo, **_: Any) -> None:
    await memo.glitchtip.aclose()


async def _reconcile(
    body: kopf.Body,
    spec: kopf.Spec,
    meta: kopf.Meta,
    status: kopf.Status,
    patch: kopf.Patch,
    memo: kopf.Memo,
    logger: kopf.Logger,
) -> None:
    status = dict(status or {})
    organization, project = spec["organization"], spec["project"]
    known_id = status.get("alertId")
    try:
        if known_id and (status.get("organization"), status.get("project")) != (
            organization,
            project,
        ):
            if spec.get("deletionPolicy", "Delete") == "Delete":
                await memo.glitchtip.delete_alert(
                    status["organization"], status["project"], known_id
                )
                logger.info(f"Deleted alert {known_id} from the previous target")
            known_id = None
        payload = await build_payload(
            dict(spec), name=meta["name"], namespace=meta["namespace"], read_secret=memo.read_secret
        )
        result = await sync_alert(
            memo.glitchtip,
            organization=organization,
            project=project,
            payload=payload,
            known_id=known_id,
        )
    except SpecError as exc:
        _fail(body, status, patch, "InvalidSpec", exc)
        raise kopf.PermanentError(str(exc)) from exc
    except ConflictError as exc:
        _fail(body, status, patch, "Conflict", exc)
        raise kopf.PermanentError(str(exc)) from exc
    except SecretNotFound as exc:
        _fail(body, status, patch, "SecretNotFound", exc)
        raise kopf.TemporaryError(str(exc), delay=RETRY_SECONDS) from exc
    except GlitchTipError as exc:
        _fail(body, status, patch, "GlitchTipError", exc)
        if exc.retryable:
            raise kopf.TemporaryError(str(exc), delay=RETRY_SECONDS) from exc
        raise kopf.PermanentError(str(exc)) from exc

    message = f"Alert {result.alert_id} {result.action} in {organization}/{project}"
    if result.action != "unchanged":
        logger.info(message)
        kopf.info(body, reason=result.action.capitalize(), message=message)
    patch.status.update(
        alertId=result.alert_id,
        organization=organization,
        project=project,
        observedGeneration=meta.get("generation"),
        lastSyncTime=_now(),
        conditions=_ready(status, True, "Synced", f"in sync with alert {result.alert_id}"),
    )


@kopf.on.resume(GROUP, VERSION, PLURAL)
@kopf.on.create(GROUP, VERSION, PLURAL)
@kopf.on.update(GROUP, VERSION, PLURAL, field="spec")
async def apply(body, spec, meta, status, patch, memo, logger, uid, **_: Any) -> None:
    async with _locks[uid]:
        await _reconcile(body, spec, meta, status, patch, memo, logger)


@kopf.timer(GROUP, VERSION, PLURAL, interval=RESYNC_SECONDS, initial_delay=RESYNC_SECONDS)
async def resync(body, spec, meta, status, patch, memo, logger, uid, **_: Any) -> None:
    async with _locks[uid]:
        await _reconcile(body, spec, meta, status, patch, memo, logger)


@kopf.on.delete(GROUP, VERSION, PLURAL)
async def delete(spec, status, memo, logger, uid, **_: Any) -> None:
    _locks.pop(uid, None)
    alert_id = (status or {}).get("alertId")
    if not alert_id or spec.get("deletionPolicy", "Delete") == "Orphan":
        return
    organization, project = status["organization"], status["project"]
    try:
        deleted = await memo.glitchtip.delete_alert(organization, project, alert_id)
    except GlitchTipError as exc:
        if exc.retryable:
            raise kopf.TemporaryError(str(exc), delay=RETRY_SECONDS) from exc
        raise kopf.PermanentError(
            f"could not delete alert {alert_id}, leaving it in GlitchTip: {exc}"
        ) from exc
    if deleted:
        logger.info(f"Deleted alert {alert_id} from {organization}/{project}")
