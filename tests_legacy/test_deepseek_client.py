import pytest

from sql_pilot_engine.llm.deepseek_client import DeepSeekLLMClient


def test_deepseek_client_from_env_should_require_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_BASE_URL","https://example.com")

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekLLMClient.from_env()


def test_deepseek_client_from_env_should_require_base_url(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="DEEPSEEK_BASE_URL"):
        DeepSeekLLMClient.from_env()


def test_deepseek_client_from_env_should_build_client(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")

    client = DeepSeekLLMClient.from_env()

    assert client.api_key == "fake-key"
    assert client.base_url == "https://example.com"
    assert client.model == "deepseek-chat"