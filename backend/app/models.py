from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SignalIR(BaseModel):
    field: Literal["open", "high", "low", "close", "volume", "returns"]
    operation: Literal["delta", "raw"]
    window: int = Field(ge=1, le=1000)
    direction: Literal["up", "down", "none"]
    selection: Literal["relative", "raw"]


class EntryIR(BaseModel):
    enabled: bool
    field: Literal["open", "high", "low", "close", "volume", "returns"]
    reference: Literal["ts_mean", "none"]
    window: int = Field(ge=1, le=1000)
    comparator: Literal[">", ">=", "<", "<=", "none"]
    multiplier: float


class StrategyIR(BaseModel):
    status: Literal["ok", "ambiguous", "unsupported"]
    signal: SignalIR
    entry: EntryIR
    neutralization: Literal["industry", "sector", "subindustry", "none"]
    exit: Literal["none"]


class TestPeriod(BaseModel):
    years: int = Field(ge=0, le=20)
    months: int = Field(ge=0, le=11)


class SettingsOverrides(BaseModel):
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


class ConvertRequest(BaseModel):
    strategy: str = Field(min_length=3, max_length=2000)
    settings: SettingsOverrides | None = None


class ValidationSummary(BaseModel):
    jsonValid: bool = True
    schemaValid: bool = True
    consensusPassed: bool = True
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
    confidence: float
    validation: ValidationSummary
    warnings: list[str]
    unresolvedSettings: list[str]
    provider: str

