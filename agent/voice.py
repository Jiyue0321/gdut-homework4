"""语音接口：MVP 只走文字，ASR/TTS 以 Protocol 留出插拔点。

后续接入浏览器 Web Speech API 时，只需实现 ``ASR`` / ``TTS``，
面试引擎与界面代码不需要改动。
"""

from __future__ import annotations

from typing import Protocol


class ASR(Protocol):
    """语音识别：音频字节 → 文本。"""

    def transcribe(self, audio: bytes) -> str: ...


class TTS(Protocol):
    """语音合成：文本 → 音频字节。"""

    def synthesize(self, text: str) -> bytes: ...


class NoopASR:
    def transcribe(self, audio: bytes) -> str:
        raise NotImplementedError("当前版本仅支持文字输入")


class NoopTTS:
    def synthesize(self, text: str) -> bytes:
        raise NotImplementedError("当前版本仅支持文字输出")
