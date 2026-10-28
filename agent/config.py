"""读取大模型配置：本地走 .env，Streamlit Cloud 走 st.secrets。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
}


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    use_mcp: bool = True

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


def _secret(name: str, default: str = "") -> str:
    """优先级：st.secrets（云端）> 环境变量（本地）> 默认值。"""
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)


def load_config() -> LLMConfig:
    provider = _secret("LLM_PROVIDER", "").strip().lower()
    preset = PROVIDERS.get(provider, {})
    use_mcp = _secret("USE_MCP", "true").strip().lower() not in {"0", "false", "no"}
    return LLMConfig(
        base_url=_secret("OPENAI_BASE_URL", preset.get("base_url", PROVIDERS["deepseek"]["base_url"])),
        api_key=_secret("OPENAI_API_KEY", ""),
        model=_secret("OPENAI_MODEL", preset.get("model", PROVIDERS["deepseek"]["model"])),
        use_mcp=use_mcp,
    )
