"""HUB Usage event emission helper.

Mirrors ``POST /api/v1/usage/events`` on the HUB. Designed to be called from
hot paths in leaf products: failures are logged and discarded, never raised.
An optional ``local_buffer`` lets callers persist events for retry from a
background worker.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_INITIAL_DELAY_SECONDS = 0.2
_BACKOFF_FACTOR = 3.0  # 0.2 → 0.6 → 1.8 base
_JITTER_FRACTION = 0.2


class UsageEvent(BaseModel):
    """One usage event in the HUB ingestion batch."""

    model_config = ConfigDict(frozen=True)

    event_type: str = Field(max_length=64)
    quantity: Decimal = Field(max_digits=12, decimal_places=2)
    unit: str = Field(max_length=32)
    occurred_at: AwareDatetime
    tenant_id: UUID
    user_id: UUID | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


async def emit_usage_event(
    client: httpx.AsyncClient,
    *,
    hub_url: str,
    service_token: str,
    events: list[UsageEvent],
    local_buffer: Callable[[list[UsageEvent]], Awaitable[None]] | None = None,
) -> None:
    """POST a batch of ``UsageEvent`` to the HUB ingestion endpoint.

    Retries up to 3 times with exponential backoff and jitter on transient
    failures (network errors and 5xx responses). 4xx responses are not retried.
    On terminal failure, logs a warning and — if ``local_buffer`` is supplied —
    hands the batch to it for persistence. Never raises; safe to call from
    request hot paths.
    """
    if not events:
        return

    url = f"{hub_url.rstrip('/')}/api/v1/usage/events"
    headers = {"Authorization": f"Bearer {service_token}"}
    # HUB expects the batch wrapped in an envelope: `{"events": [...]}` (see
    # `app/usage/schemas.py::UsageEventBatchIn` in the hub repo). Sending the
    # bare list here returns 422 with `loc=["body"]` and the events list
    # echoed back as `input` — that's the canonical signature of this bug.
    payload: dict[str, Any] = {
        "events": [event.model_dump(mode="json") for event in events]
    }

    last_error: str | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            last_error = f"network error: {exc!r}"
        else:
            if response.status_code < 400:
                return
            if response.status_code < 500:
                last_error = f"HTTP {response.status_code} (non-retryable)"
                break
            last_error = f"HTTP {response.status_code}"

        if attempt < _MAX_ATTEMPTS - 1:
            base = _INITIAL_DELAY_SECONDS * (_BACKOFF_FACTOR**attempt)
            jitter = base * _JITTER_FRACTION
            await asyncio.sleep(max(0.0, base + random.uniform(-jitter, jitter)))  # noqa: S311

    logger.warning(
        "Failed to emit %d usage event(s) to HUB after %d attempt(s): %s",
        len(events),
        _MAX_ATTEMPTS,
        last_error,
    )
    if local_buffer is not None:
        try:
            await local_buffer(events)
        except Exception:
            logger.exception("Usage event local_buffer raised; events lost")
