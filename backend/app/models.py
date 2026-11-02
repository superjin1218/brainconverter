from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .data_fields import DATA_FIELD_PATTERN, validate_data_field

DataField = Annotated[
    str, Field(min_length=1, max_length=128, pattern=DATA_FIELD_PATTERN),
    AfterValidator(validate_data_field),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SignalIR(StrictModel):
    field: DataField
    operation: Literal["delta", "raw", "return"]
    window: int = Field(ge=1, le=1000)
    direction: Literal["up", "down", "none"]
    selection: Literal["relative", "raw"]


class EntryIR(StrictModel):
    enabled: bool
    field: DataField
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
            if self.signal.operation == "return" and self.signal.field != "close":
                raise ValueError("기간 수익률은 종가로 계산합니다.")
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
    intentPlanChecked: bool | None = None


class ImprovementSuggestion(StrictModel):
    title: str
    rationale: str
    experiment: str


class RefinementOption(StrictModel):
    label: str
    description: str
    strategy: str


class DraftIR(StrictModel):
    """AI-designed hypothesis draft; its expression is parsed, never executed."""

    schemaVersion: Literal["draft-v2"]
    status: Literal["ok", "ambiguous", "unsupported"]
    hypothesis: str = Field(max_length=250)
    expression: str = Field(max_length=2000)
    assumptions: list[str] = Field(max_length=5)
    improvementSuggestions: list[ImprovementSuggestion] = Field(max_length=3)
    refinementOptions: list[RefinementOption] = Field(max_length=3)
    reason: str = Field(max_length=300)


class IntentMetric(StrictModel):
    source: str = Field(min_length=2, max_length=300)
    operation: Literal[
        "raw", "return", "delta", "mean", "std_dev", "relative_mean",
        "ratio", "difference", "range_position", "correlation",
    ]
    field: DataField
    window: int = Field(ge=1, le=1000)
    reference: DataField | None
    preference: Literal["higher", "lower"]
    group: Literal["none", "industry", "sector", "subindustry"]
    weight: float = Field(gt=0, le=10)

    @model_validator(mode="after")
    def consistent_measurement(self):
        paired = self.operation in {"ratio", "difference", "correlation"}
        if paired != (self.reference is not None):
            raise ValueError("측정 방법에 맞는 비교 데이터가 필요합니다.")
        if paired and self.field == self.reference:
            raise ValueError("동일 데이터를 자기 자신과 비교할 수 없습니다.")
        if self.operation in {"raw", "ratio", "difference", "range_position"} and self.window != 1:
            raise ValueError("당일 측정값에는 여러 날의 기간을 적용할 수 없습니다.")
        if self.operation == "return" and self.field == "returns":
            raise ValueError("기간 수익률은 가격으로 측정해야 합니다.")
        if self.operation == "range_position" and self.field not in {"open", "close"}:
            raise ValueError("일중 가격 범위 안에서 시가 또는 종가의 위치를 측정합니다.")
        return self


class IntentEntry(StrictModel):
    source: str = Field(min_length=2, max_length=300)
    condition: str = Field(min_length=3, max_length=500)


class IntentIR(StrictModel):
    schemaVersion: Literal["intent-v3"]
    status: Literal["ok", "ambiguous", "unsupported"]
    metrics: list[IntentMetric] = Field(max_length=3)
    entry: IntentEntry | None
    improvementSuggestions: list[ImprovementSuggestion] = Field(max_length=3)
    refinementOptions: list[RefinementOption] = Field(max_length=3)
    reason: str = Field(max_length=300)


class ConversionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requestId: str
    status: Literal["PASS", "REJECTED"]
    fastExpression: str | None
    simulationSettings: dict[str, Any]
    settingsSource: dict[str, Literal["default", "user", "override"]]
    strategyIR: IntentIR | DraftIR | StrategyIR | None
    confidence: float | None = None
    validation: ValidationSummary
    warnings: list[str]
    unresolvedSettings: list[str]
    provider: str
    usage: dict[str, int] = Field(default_factory=dict)
    intentMapping: list[dict[str, str]] = Field(default_factory=list)
    strategyExplanation: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    improvementSuggestions: list[ImprovementSuggestion] = Field(default_factory=list)
    refinementOptions: list[RefinementOption] = Field(default_factory=list)
