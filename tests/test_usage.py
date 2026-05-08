import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from oort_shared import UsageEvent, emit_usage_event


def _event(**overrides: Any) -> UsageEvent:
    base: dict[str, Any] = dict(
        event_type="flow.execution",
        quantity=Decimal("1.50"),
        unit="credits",
        occurred_at=datetime.now(UTC),
        tenant_id=uuid4(),
    )
    base.update(overrides)
    return UsageEvent(**base)


async def test_emit_happy_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await emit_usage_event(
            client,
            hub_url="https://hub.example.com",
            service_token="ost_test_token",
            events=[_event()],
        )

    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://hub.example.com/api/v1/usage/events"
    assert req.headers["authorization"] == "Bearer ost_test_token"

    parsed = json.loads(req.read())
    # HUB expects `{"events": [...]}` envelope per UsageEventBatchIn —
    # sending a bare list returns 422 with `loc=["body"]`.
    assert isinstance(parsed, dict) and list(parsed.keys()) == ["events"]
    assert isinstance(parsed["events"], list) and len(parsed["events"]) == 1
    item = parsed["events"][0]
    assert item["event_type"] == "flow.execution"
    assert item["unit"] == "credits"
    assert item["quantity"] == "1.50"
    assert "tenant_id" in item


async def test_emit_strips_trailing_slash() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await emit_usage_event(
            client,
            hub_url="https://hub.example.com/",
            service_token="ost_test_token",
            events=[_event()],
        )

    assert str(seen[0].url) == "https://hub.example.com/api/v1/usage/events"


async def test_emit_empty_batch_is_noop() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(202)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await emit_usage_event(
            client,
            hub_url="https://hub.example.com",
            service_token="ost_test_token",
            events=[],
        )
    assert calls["n"] == 0


async def test_emit_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("oort_shared.usage.asyncio.sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(202)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await emit_usage_event(
            client,
            hub_url="https://hub.example.com",
            service_token="ost_test_token",
            events=[_event()],
        )

    assert calls["n"] == 3
    assert len(sleeps) == 2
    assert 0.16 <= sleeps[0] <= 0.24  # 0.2 ±20%
    assert 0.48 <= sleeps[1] <= 0.72  # 0.6 ±20%


async def test_emit_terminal_failure_no_buffer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("oort_shared.usage.asyncio.sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    with caplog.at_level("WARNING"):
        async with httpx.AsyncClient(transport=transport) as client:
            await emit_usage_event(
                client,
                hub_url="https://hub.example.com",
                service_token="ost_test_token",
                events=[_event()],
            )

    assert calls["n"] == 3
    assert any("Failed to emit" in rec.message for rec in caplog.records)


async def test_emit_terminal_failure_with_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("oort_shared.usage.asyncio.sleep", fake_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    captured: list[list[UsageEvent]] = []

    async def buffer(events: list[UsageEvent]) -> None:
        captured.append(events)

    events_in = [_event()]
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await emit_usage_event(
            client,
            hub_url="https://hub.example.com",
            service_token="ost_test_token",
            events=events_in,
            local_buffer=buffer,
        )

    assert captured == [events_in]


async def test_emit_4xx_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("oort_shared.usage.asyncio.sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await emit_usage_event(
            client,
            hub_url="https://hub.example.com",
            service_token="ost_test_token",
            events=[_event()],
        )

    assert calls["n"] == 1
    assert sleeps == []


async def test_emit_swallows_buffer_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("oort_shared.usage.asyncio.sleep", fake_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async def broken_buffer(_events: list[UsageEvent]) -> None:
        raise RuntimeError("disk full")

    transport = httpx.MockTransport(handler)
    with caplog.at_level("WARNING"):
        async with httpx.AsyncClient(transport=transport) as client:
            await emit_usage_event(
                client,
                hub_url="https://hub.example.com",
                service_token="ost_test_token",
                events=[_event()],
                local_buffer=broken_buffer,
            )

    assert any("local_buffer raised" in rec.message for rec in caplog.records)


async def test_emit_handles_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("oort_shared.usage.asyncio.sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await emit_usage_event(
            client,
            hub_url="https://hub.example.com",
            service_token="ost_test_token",
            events=[_event()],
        )

    assert calls["n"] == 3


def test_event_type_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(event_type="x" * 65)


def test_unit_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(unit="x" * 33)


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(occurred_at=datetime(2026, 1, 1, 12, 0, 0))  # naive, no tz


def test_quantity_excess_precision_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(quantity=Decimal("1.234"))  # 3 decimal places > 2 allowed
