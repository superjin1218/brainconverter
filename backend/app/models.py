from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SignalIR(StrictModel):
    field: Literal["open", "high", "low", "close", "volume", "returns"]
    operation: Literal["delta", "raw"]
    window: int = Field(ge=1, le=1000)
    direction: Literal["up", "down", "none"]
    selection: Literal["relative", "raw"]


class EntryIR(StrictModel):
    enabled: bool
    field: Literal["open", "high", "low", "close", "volume", "returns"]
    reference: Literal["ts_mean", "none"]
    window: int = Field(ge=1, le=1000)
    comparator: Literal[">", ">=", "<", "<=", "none"]
    multiplier: float = Field(gt=0, le=1000)


class StrategyIR(StrictModel):
    status: Literal["ok", "ambiguous", "unsupported"]
    signal: SignalIR
    entry: EntryIR
    neutralization: Literal["industry", "sector", "subindustry", "none"]
    exit: Literal["none"]

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "ok":
            if self.signal.operation == "raw" and self.signal.window != 1:
                raise ValueError("raw 신호는 기간을 적용하지 않습니다.")
            if self.entry.enabled and (
                self.entry.reference != "ts_mean" or self.entry.comparator == "none"
            ):
                raise ValueError("활성 진입 조건에는 평균 기준과 비교 연산자가 필요합니다.")
        return self


class TestPeriod(StrictModel):
    years: int = Field(ge=0, le=20)
    months: int = Field(ge=0, le=11)


class SettingsOverrides(StrictModel):
    language: Literal["FASTEXPR"] | None = None
    instrumentType: Literal["EQUITY"] | None = None
    region: str | None = None
    universe: str | None = None
    delay: int | None = Field(default=None, ge=0, le=1)
    neutralization: str | None = None
    decay: int | None = Field(default=None, ge=0, le=100)
    truncation: float | None = Field(default=None, ge=0, le=1)
    pasteurization: Literal["ON", "OFF"] | None = None
    unitHandling: Literal["VERIFY"] | None = None
    nanHandling: Literal["ON", "OFF"] | None = None
    testPeriod: TestPeriod | None = None


class ConvertRequest(StrictModel):
    strategy: str = Field(min_length=3, max_length=2000)
    settings: SettingsOverrides | None = None

    @field_validator("strategy")
    @classmethod
    def meaningful_strategy(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("전략을 세 글자 이상 입력하세요.")
        return value


class ValidationSummary(BaseModel):
    jsonValid: bool = True
    schemaValid: bool = True
    sourceRequirementsPreserved: bool = True
    compilePassed: bool = True


class ConversionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requestId: str
    status: Literal["PASS", "REJECTED"]
    fastExpression: str | None
    simulationSettings: dict[str, Any]
    settingsSource: dict[str, Literal["default", "user", "override"]]
    strategyIR: StrategyIR | None
    confidence: float | None = None
    validation: ValidationSummary
    warnings: list[str]
    unresolvedSettings: list[str]
    provider: str
    usage: dict[str, int] = Field(default_factory=dict)
    intentMapping: list[dict[str, str]] = Field(default_factory=list)
