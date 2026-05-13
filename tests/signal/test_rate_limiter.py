"""Tests for signal LiteLLM call parameter resolution."""
from types import SimpleNamespace

from src.signal.rate_limiter import _with_channel_params


def test_with_channel_params_injects_llm_channel_api_base(monkeypatch):
    config = SimpleNamespace(
        llm_model_list=[
            {
                "model_name": "openai/mimo-v2.5",
                "litellm_params": {
                    "model": "openai/mimo-v2.5",
                    "api_key": "test-key",
                    "api_base": "https://token-plan-cn.xiaomimimo.com/v1",
                    "extra_headers": {"X-Test": "1"},
                },
            }
        ]
    )

    monkeypatch.setattr("src.config.get_config", lambda: config)

    resolved = _with_channel_params({"model": "openai/mimo-v2.5", "messages": []})

    assert resolved["api_key"] == "test-key"
    assert resolved["api_base"] == "https://token-plan-cn.xiaomimimo.com/v1"
    assert resolved["extra_headers"] == {"X-Test": "1"}


def test_with_channel_params_keeps_explicit_api_base(monkeypatch):
    config = SimpleNamespace(
        llm_model_list=[
            {
                "model_name": "openai/mimo-v2.5",
                "litellm_params": {
                    "model": "openai/mimo-v2.5",
                    "api_key": "test-key",
                    "api_base": "https://token-plan-cn.xiaomimimo.com/v1",
                },
            }
        ]
    )

    monkeypatch.setattr("src.config.get_config", lambda: config)

    resolved = _with_channel_params({
        "model": "openai/mimo-v2.5",
        "messages": [],
        "api_base": "https://example.com/v1",
    })

    assert resolved["api_base"] == "https://example.com/v1"
    assert "api_key" not in resolved
