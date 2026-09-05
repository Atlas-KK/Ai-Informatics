import pytest
from pydantic import ValidationError

from ai_intel.config import MissingConfigurationError, Settings, require_configured


def test_missing_configuration_names_only_the_setting() -> None:
    with pytest.raises(MissingConfigurationError) as exc_info:
        require_configured("AI_INTEL_FAKE_SECRET", None)

    message = str(exc_info.value)
    assert message == "Missing required configuration: AI_INTEL_FAKE_SECRET"
    assert "value" not in message.lower()


def test_configured_value_is_returned_without_logging() -> None:
    assert require_configured("AI_INTEL_FAKE_SECRET", "fixture-only") == "fixture-only"


def test_host_environment_cannot_expose_the_local_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_INTEL_HOST", "0.0.0.0")
    with pytest.raises(ValidationError, match="127.0.0.1"):
        Settings()
