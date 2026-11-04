"""简历 / JD 文档抽取：把上传的 PDF、纯文本文件还原成可编辑文本。

只做文本层抽取，不做 OCR。扫描件没有文字层时明确报错，而不是给模型喂空字符串。
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import PurePath
from typing import Any

MAX_BYTES = 10 * 1024 * 1024
TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
PDF_SUFFIX = ".pdf"

# 零宽字符、BOM、方向控制符、软连字符等不可见字符，会让模型与向量化误判。
_INVISIBLE_RE = re.compile(r"[​-‏‪-‮⁠-⁤﻿­]")
_INLINE_WS_RE = re.compile(r"[ \t　]{2,}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


class DocumentError(ValueError):
    """文件格式不支持、加密、无可抽取文字层等用户可理解的错误。"""


def sanitize_text(text: str) -> str:
    """统一换行、剔除不可见字符、压缩多余空白，保留段落结构。"""
    cleaned = _INVISIBLE_RE.sub("", text or "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    cleaned = _INLINE_WS_RE.sub(" ", cleaned)
    return _MULTI_NEWLINE_RE.sub("\n\n", cleaned).strip()


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    # 上面几种都失败时用字符集检测兜底，覆盖 UTF-16 / Big5 等常见编码。
    for encoding in ("utf-16", _detect_encoding(data)):
        if not encoding:
            continue
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise DocumentError("无法识别文本编码，请另存为 UTF-8 后重试")


def _detect_encoding(data: bytes) -> str:
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(data).best()
    except Exception:
        return ""
    if best is None or not best.encoding:
        return ""
    return best.encoding


def _extract_pdf(data: bytes) -> str:
    import pdfplumber

    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            if not pdf.pages:
                raise DocumentError("PDF 中没有页面，文件可能已损坏")
            pages = [(page.extract_text() or "") for page in pdf.pages]
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("PDF 解析失败，请确认文件未加密、未损坏") from exc

    text = "\n".join(sanitize_text(page) for page in pages if page.strip())
    if not text:
        raise DocumentError("PDF 中没有可抽取的文字层，可能是扫描件或图片；请改为粘贴文字")
    return text


def extract_document(filename: str, data: bytes) -> dict[str, Any]:
    """按扩展名抽取文本，返回 ``{"text", "format", "chars"}``。"""
    if not data:
        raise DocumentError("文件内容为空")
    if len(data) > MAX_BYTES:
        raise DocumentError(f"文件超过 {MAX_BYTES // (1024 * 1024)} MB，请拆分后再上传")

    suffix = PurePath(filename or "").suffix.lower()
    if suffix == PDF_SUFFIX:
        text, fmt = _extract_pdf(data), "pdf"
    elif suffix in TEXT_SUFFIXES:
        text, fmt = _decode_text(data), "text"
    else:
        raise DocumentError("仅支持 PDF、TXT 和 Markdown 文件")

    text = sanitize_text(text)
    if not text:
        raise DocumentError("文件里没有可用文字")
    return {"text": text, "format": fmt, "chars": len(text)}
