import asyncio

import httpx
import pytest

from backend.app.models import ConvertRequest
from backend.app.provider import MockSemanticProvider, MuseSparkProvider
from backend.app.provider_errors import ProviderError
from backend.app.service import HarnessService
from backend.tests.test_provider import FAKE_KEY, reply

STRATEGY = (
    "최근 5일 동안 가격이 많이 떨어진 종목을 매수한다. "
    "거래량이 최근 20일 평균보다 1.5배 이상일 때만 거래하고 산업별로 중립화한다."
)


async def test_full_conversion_returns_expression_and_twelve_settings():
    service = HarnessService(MockSemanticProvider())
    response = await service.convert(
        ConvertRequest(
            strategy=(
                "최근 5일 동안 가격이 많이 떨어진 종목을 매수한다. "
                "거래량이 최근 20일 평균보다 1.5배 이상일 때만 거래하고 산업별로 중립화한다."
            )
        )
    )
    assert response.status == "PASS"
    assert response.fastExpression is not None
    assert len(response.simulationSettings) == 12
    assert response.simulationSettings["neutralization"] == "INDUSTRY"
    assert response.settingsSource["neutralization"] == "user"
    assert response.confidence is None


@pytest.mark.parametrize(
    ("status", "upstream_code", "expected_code"),
    [
        (401, "invalid_api_key", "authentication"),
        (403, None, "permission"),
        (400, "unsupported_parameter", "invalid_request"),
        (429, "insufficient_quota", "quota"),
        (429, "rate_limit_exceeded", "rate_limit"),
    ],
)
async def test_first_provider_failure_prevents_five_more_paid_calls(
    monkeypatch, status, upstream_code, expected_code
):
    monkeypatch.setenv("MUSE_MODEL", "meta/muse-spark-1.3-contributor")
    monkeypatch.setenv("MAX_CONCURRENT_JOBS", "1")
    calls = []

    def handler(_):
        calls.append(1)
        return httpx.Response(status, json={"error": {"code": upstream_code}})

    service = HarnessService(MuseSparkProvider(httpx.MockTransport(handler), api_key=FAKE_KEY))
    with pytest.raises(ProviderError) as exc:
        await service.convert(ConvertRequest(strategy=STRATEGY))
    assert exc.value.code == expected_code
    assert calls == [1]
    # A failed conversion must release its slot for the next request.
    await asyncio.wait_for(service.job_semaphore.acquire(), timeout=0.2)
    service.job_semaphore.release()


@pytest.mark.parametrize("body", [reply(finish="length"), reply(content="invalid JSON")])
async def test_unusable_first_result_prevents_fanout(monkeypatch, body):
    monkeypatch.setenv("MUSE_MODEL", "meta/muse-spark-1.3-contributor")
    calls = []

    def handler(_):
        calls.append(1)
        return httpx.Response(200, json=body)

    service = HarnessService(MuseSparkProvider(httpx.MockTransport(handler), api_key=FAKE_KEY))
    with pytest.raises(ProviderError):
        await service.convert(ConvertRequest(strategy=STRATEGY))
    assert calls == [1]


async def test_success_interprets_once_and_preserves_expression_settings_and_usage(monkeypatch):
    monkeypatch.setenv("MUSE_MODEL", "meta/muse-spark-1.3-contributor")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=reply())

    service = HarnessService(MuseSparkProvider(httpx.MockTransport(handler), api_key=FAKE_KEY))
    result = await service.convert(ConvertRequest(strategy=STRATEGY))
    assert len(calls) == 1
    assert result.status == "PASS"
    assert result.fastExpression == (
        "trade_when(volume >= 1.5 * ts_mean(volume, 20), rank(-ts_delta(close, 5)), -1)"
    )
    assert len(result.simulationSettings) == 12
    assert result.confidence is None
    assert "consensusPassed" not in result.validation.model_dump()
    assert result.usage == {"inputTokens": 900, "outputTokens": 180, "costMicrousd": 126}


async def test_twenty_simultaneous_interpretations_call_once_and_overflow_never_calls(monkeypatch):
    monkeypatch.delenv("MAX_CONCURRENT_JOBS", raising=False)
    ready, release = asyncio.Event(), asyncio.Event()
    calls = 0

    class GatedProvider(MockSemanticProvider):
        async def interpret(self, system_prompt, strategy):
            nonlocal calls
            calls += 1
            if calls == 20:
                ready.set()
            await release.wait()
            return await super().interpret(system_prompt, strategy)

    service = HarnessService(GatedProvider())
    tasks = [
        asyncio.create_task(service.convert(ConvertRequest(strategy=STRATEGY))) for _ in range(20)
    ]
    try:
        await asyncio.wait_for(ready.wait(), timeout=2)
        with pytest.raises(RuntimeError, match="요청이 많습니다"):
            await service.convert(ConvertRequest(strategy=STRATEGY))
        assert calls == 20
    finally:
        release.set()
        results = await asyncio.gather(*tasks)
    assert all(result.status == "PASS" for result in results)
    assert (await service.convert(ConvertRequest(strategy=STRATEGY))).status == "PASS"
    assert calls == 21
