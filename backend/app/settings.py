from __future__ import annotations

import copy
import re
from typing import Any

from .models import SettingsOverrides

DEFAULT_SIMULATION_SETTINGS: dict[str, Any] = {
    "language": "FASTEXPR",
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "neutralization": "SUBINDUSTRY",
    "decay": 4,
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "testPeriod": {"years": 0, "months": 0},
}

ALLOWED_UNIVERSES = {"TOP200", "TOP500", "TOP1000", "TOP2000", "TOP3000"}
ALLOWED_NEUTRALIZATION = {"NONE", "MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"}


def _set_user(settings: dict, sources: dict, key: str, value: Any) -> None:
    settings[key] = value
    sources[key] = "user"


def resolve_simulation_settings(
    strategy: str, overrides: SettingsOverrides | None = None
) -> tuple[dict[str, Any], dict[str, str], list[str], list[str]]:
    settings = copy.deepcopy(DEFAULT_SIMULATION_SETTINGS)
    sources = {key: "default" for key in settings}
    warnings: list[str] = []
    unresolved: list[str] = []
    lower = strategy.lower()

    if re.search(r"\b(usa|u\.s\.|us market)\b|미국", lower):
        _set_user(settings, sources, "region", "USA")
    for unsupported, canonical in (("중국", "CHN"), ("china", "CHN"), ("유럽", "EUR")):
        if unsupported in lower:
            unresolved.append(f"region={canonical}")
            warnings.append(f"{canonical} 환경 manifest가 없어 기본 USA 설정을 유지했습니다.")
            break

    universe_match = re.search(r"(?i)\btop\s*(200|500|1000|2000|3000)\b", strategy)
    if universe_match:
        _set_user(settings, sources, "universe", f"TOP{universe_match.group(1)}")

    delay_match = re.search(r"(?i)(?:delay|딜레이)\s*[:=]?\s*([01])\b|\bD([01])\b", strategy)
    if delay_match:
        _set_user(settings, sources, "delay", int(delay_match.group(1) or delay_match.group(2)))

    neutralization_patterns = (
        (r"중립화\s*(?:없음|안\s*함)|(?:neutralization|neutralize)\s*(?:none|off)", "NONE"),
        (r"하위\s*산업|subindustry", "SUBINDUSTRY"),
        (r"섹터|sector", "SECTOR"),
        (r"산업|industry", "INDUSTRY"),
        (r"시장\s*중립|market\s*neutral", "MARKET"),
    )
    for pattern, value in neutralization_patterns:
        if re.search(pattern, lower):
            _set_user(settings, sources, "neutralization", value)
            break

    decay_match = re.search(r"(?i)(?:decay|디케이)\s*[:=]?\s*(\d{1,3})\b", strategy)
    if decay_match:
        _set_user(settings, sources, "decay", int(decay_match.group(1)))

    truncation_match = re.search(
        r"(?i)(?:truncation|트런케이션)\s*[:=]?\s*(0?\.\d+|1(?:\.0+)?)",
        strategy,
    )
    if truncation_match:
        value = float(truncation_match.group(1))
        if 0 <= value <= 1:
            _set_user(settings, sources, "truncation", value)

    toggle_patterns = {
        "pasteurization": r"(?i)pasteurization\s*[:=]?\s*(on|off)",
        "nanHandling": r"(?i)(?:nan\s*handling|nan)\s*[:=]?\s*(on|off)",
    }
    for key, pattern in toggle_patterns.items():
        match = re.search(pattern, strategy)
        if match:
            _set_user(settings, sources, key, match.group(1).upper())

    test_match = re.search(
        r"(?i)(?:test\s*period|테스트\s*기간)\s*[:=]?\s*(\d+)\s*(?:년|y(?:ears?)?)"
        r"(?:\s*(\d+)\s*(?:개월|m(?:onths?)?))?",
        strategy,
    )
    if test_match:
        _set_user(
            settings,
            sources,
            "testPeriod",
            {"years": int(test_match.group(1)), "months": int(test_match.group(2) or 0)},
        )

    if overrides:
        for key, value in overrides.model_dump(exclude_none=True).items():
            if key == "region" and str(value).upper() != "USA":
                unresolved.append(f"region={str(value).upper()}")
                warnings.append("현재 배포 manifest는 USA만 지원합니다.")
                continue
            if key == "universe" and str(value).upper() not in ALLOWED_UNIVERSES:
                unresolved.append(f"universe={str(value).upper()}")
                warnings.append("지원하지 않는 Universe라 기본값을 유지했습니다.")
                continue
            if key == "neutralization" and str(value).upper() not in ALLOWED_NEUTRALIZATION:
                unresolved.append(f"neutralization={str(value).upper()}")
                warnings.append("지원하지 않는 Neutralization이라 기본값을 유지했습니다.")
                continue
            settings[key] = str(value).upper() if isinstance(value, str) else value
            sources[key] = "override"

    if any(source == "default" for source in sources.values()):
        warnings.append("명시되지 않은 설정은 표준 첫 시뮬레이션 기본값으로 채웠습니다.")
    return settings, sources, warnings, unresolved
