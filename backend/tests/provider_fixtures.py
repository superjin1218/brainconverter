"""Synthetic responses shared by offline provider and API tests."""

from backend.app.models import EntryIR, IntentIR, SignalIR, StrategyIR

FAKE_KEY = "sk-provider-test-placeholder-never-a-real-key"


def reply(content=None, finish="stop"):
    return {
        "model": "gpt-5.4-mini",
        "choices": [
            {
                "finish_reason": finish,
                "message": {
                    "content": content if content is not None else intent_ir().model_dump_json(),
                },
            }
        ],
        "usage": {"prompt_tokens": 900, "completion_tokens": 180},
    }


def example_ir() -> StrategyIR:
    return StrategyIR(
        status="ok",
        signal=SignalIR(
            field="close", operation="delta", window=5, direction="down", selection="relative"
        ),
        entry=EntryIR(
            enabled=True,
            field="volume",
            reference="ts_mean",
            window=20,
            comparator=">=",
            multiplier=1.5,
        ),
        neutralization="industry",
        exit="none",
    )


def intent_ir() -> IntentIR:
    return IntentIR(
        schemaVersion="intent-v3", status="ok",
        metrics=[{
            "source": "가격이 많이 떨어진", "operation": "delta", "field": "close",
            "window": 5, "reference": None, "preference": "lower", "group": "none", "weight": 1,
        }],
        entry={
            "source": "거래량이 최근 20일 평균보다 1.5배 이상",
            "condition": "volume >= 1.5 * ts_mean(volume, 20)",
        },
        improvementSuggestions=[{
            "title": "기간 비교", "rationale": "기간 의존성 확인", "experiment": "기간을 바꿔 비교",
        }],
        refinementOptions=[{
            "label": "긴 기간", "description": "관찰 기간을 늘립니다.",
            "strategy": "최근 10일 가격 하락 순위. 거래량이 20일 평균의 1.5배 이상일 때만 거래",
        }], reason="",
    )
