"""简历 / JD 文档抽取的单元测试。"""

from __future__ import annotations

from io import BytesIO

import pytest

from mcp_server import document


def _pdf(lines: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    try:
        pdfmetrics.registerFont(TTFont("DocTestCJK", "C:/Windows/Fonts/msyh.ttc", subfontIndex=0))
        font = "DocTestCJK"
    except Exception:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font = "STSong-Light"

    buffer = BytesIO()
    canvas_obj = canvas.Canvas(buffer, pagesize=A4)
    canvas_obj.setFont(font, 12)
    y = 800
    for line in lines:
        canvas_obj.drawString(50, y, line)
        y -= 20
    canvas_obj.save()
    return buffer.getvalue()


def test_extract_text_file_returns_content():
    result = document.extract_document("resume.txt", "教育背景：广东工业大学".encode("utf-8"))
    assert result["format"] == "text"
    assert "广东工业大学" in result["text"]
    assert result["chars"] == len(result["text"])


def test_extract_markdown_and_gbk_text():
    assert document.extract_document("jd.md", b"# JD\nPython")["text"].startswith("# JD")
    gbk = document.extract_document("jd.txt", "岗位职责：后端开发".encode("gb18030"))
    assert "后端开发" in gbk["text"]


def test_extract_pdf_with_chinese_text():
    data = _pdf(["教育背景：广东工业大学 软件工程", "项目成果：接口 P99 从 800ms 降到 120ms"])
    result = document.extract_document("resume.pdf", data)
    assert result["format"] == "pdf"
    assert "广东工业大学" in result["text"]
    assert "120ms" in result["text"]


def test_extract_pdf_without_text_layer_is_rejected():
    """模拟扫描件：页面上只有图形、没有文字层。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    canvas_obj = canvas.Canvas(buffer, pagesize=A4)
    canvas_obj.rect(50, 700, 400, 100, fill=1)
    canvas_obj.showPage()
    canvas_obj.save()
    with pytest.raises(document.DocumentError, match="文字层"):
        document.extract_document("scan.pdf", buffer.getvalue())


def test_extract_rejects_unsupported_extension():
    with pytest.raises(document.DocumentError, match="仅支持"):
        document.extract_document("resume.docx", b"PK\x03\x04")


def test_extract_rejects_empty_and_oversized_files():
    with pytest.raises(document.DocumentError, match="为空"):
        document.extract_document("resume.txt", b"")
    oversized = b"x" * (document.MAX_BYTES + 1)
    with pytest.raises(document.DocumentError, match="10 MB"):
        document.extract_document("resume.txt", oversized)


def test_extract_rejects_corrupted_pdf():
    with pytest.raises(document.DocumentError, match="解析失败"):
        document.extract_document("resume.pdf", b"not a pdf")


def test_extract_rejects_whitespace_only_text():
    with pytest.raises(document.DocumentError, match="没有可用文字"):
        document.extract_document("resume.txt", b"   \n\n  ")


def test_extract_strips_invisible_characters_and_normalizes_whitespace():
    raw = "教育背景​：广东工业大学﻿ 软件工程\r\n\r\n\r\n\r\n项目：订单".encode("utf-8")
    result = document.extract_document("resume.txt", raw)
    assert "​" not in result["text"]
    assert "﻿" not in result["text"]
    assert "\r" not in result["text"]
    assert "\n\n\n" not in result["text"]
    assert "广东工业大学" in result["text"]


def test_extract_utf16_text_file():
    data = "岗位职责：后端开发与性能优化".encode("utf-16")
    result = document.extract_document("jd.txt", data)
    assert "后端开发" in result["text"]
