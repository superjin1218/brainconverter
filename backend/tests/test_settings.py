from backend.app.models import SettingsOverrides
from backend.app.settings import DEFAULT_SIMULATION_SETTINGS, resolve_simulation_settings


def test_returns_all_default_settings_when_unspecified():
    settings, sources, warnings, unresolved = resolve_simulation_settings("최근 5일 하락 종목")
    assert settings == DEFAULT_SIMULATION_SETTINGS
    assert len(settings) == 12
    assert set(sources.values()) == {"default"}
    assert warnings
    assert unresolved == []


def test_natural_language_and_overrides_have_priority():
    strategy = "미국 TOP500, Delay 0, Decay 8, 산업 중립화로 테스트"
    overrides = SettingsOverrides(truncation=0.03, nanHandling="ON")
    settings, sources, _, _ = resolve_simulation_settings(strategy, overrides)
    assert settings["region"] == "USA"
    assert settings["universe"] == "TOP500"
    assert settings["delay"] == 0
    assert settings["decay"] == 8
    assert settings["neutralization"] == "INDUSTRY"
    assert settings["truncation"] == 0.03
    assert settings["nanHandling"] == "ON"
    assert sources["decay"] == "user"
    assert sources["truncation"] == "override"


def test_unsupported_region_is_explicitly_reported():
    settings, _, warnings, unresolved = resolve_simulation_settings("중국 TOP3000에서 테스트")
    assert settings["region"] == "USA"
    assert "region=CHN" in unresolved
    assert any("CHN" in warning for warning in warnings)

