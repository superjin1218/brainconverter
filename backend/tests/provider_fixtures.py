"""Synthetic responses shared by offline provider and API tests."""

from backend.app.models import EntryIR, SignalIR, StrategyIR

FAKE_KEY = "sk-provider-test-placeholder-never-a-real-key"


def reply(content=None, finish="stop"):
    return {
        "model": "gpt-5.4-mini",
        "choices": [
            {
                "finish_reason": finish,
                "message": {
                    "content": content if content is not None else example_ir().model_dump_json(),
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
