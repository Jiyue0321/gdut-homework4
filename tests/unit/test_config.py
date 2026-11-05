"""配置读取的单元测试。"""

from agent.config import LLMConfig


def _config(api_key: str) -> LLMConfig:
    return LLMConfig(base_url="https://api.deepseek.com/v1", api_key=api_key, model="deepseek-chat")


def test_real_api_key_is_configured():
    assert _config("sk-0123456789abcdef").configured


def test_placeholder_key_counts_as_unconfigured():
    # .env.example 里的占位符含中文，发请求时会在 HTTP 头编码处崩掉，必须提前拦住。
    assert not _config("sk-你的deepseek密钥").configured


def test_key_with_whitespace_is_unconfigured():
    assert not _config("sk-abc def").configured


def test_empty_key_is_unconfigured():
    assert not _config("").configured
