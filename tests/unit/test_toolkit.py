"""工具实现的单元测试：简历体检、能力匹配、报告渲染、沙箱导出。"""

import pytest

from mcp_server import toolkit
from mcp_server.sandbox import SandboxError, resolve_safe

GOOD_RESUME = """
教育背景：广东工业大学 软件工程 本科 2022-2026
实习经历：某互联网公司 后端开发实习，2025.07-2025.09
项目经历：校园二手交易平台，负责订单模块
技术栈：Python、FastAPI、MySQL、Redis
项目成果：接口平均响应从 800ms 降到 120ms，日活 3000 人
"""


def test_check_resume_quality_detects_sections_and_numbers():
    result = toolkit.check_resume_quality(GOOD_RESUME)
    assert result["length"] > 120
    assert result["missing_sections"] == []
    assert result["quantified_results"] >= 2


def test_check_resume_quality_flags_short_text():
    result = toolkit.check_resume_quality("我会 Python")
    assert result["length"] < 120
    assert any("偏短" in tip for tip in result["tips"])


def test_check_resume_quality_flags_missing_quantification():
    result = toolkit.check_resume_quality(
        "教育：本科。经历：做过项目。项目：写了一个网站。技能：Python。"
    )
    assert result["quantified_results"] == 0
    assert any("量化" in tip for tip in result["tips"])


def test_match_competencies_builds_radar_and_gaps():
    result = toolkit.match_competencies(
        [
            {"name": "系统设计", "weight": 0.5, "required_level": 4, "resume_level": 2},
            {"name": "沟通表达", "weight": 0.5, "required_level": 3, "resume_level": 3},
        ]
    )
    assert len(result["radar"]) == 2
    assert result["gaps"][0]["competency"] == "系统设计"
    assert result["gaps"][0]["gap"] == 2.0
    assert result["gaps"][0]["priority"] == "高"


def test_match_competencies_ignores_blank_names():
    assert toolkit.match_competencies([{"name": "  ", "required_level": 1}])["radar"] == []


def test_aggregate_scores_returns_verdict_and_warnings():
    turns = [
        {"competency": "系统设计", "score": 1},
        {"competency": "沟通表达", "score": 4},
    ]
    result = toolkit.aggregate_scores(turns, {"系统设计": 0.5, "沟通表达": 0.5})
    assert result["overall_score"] == 2.5
    assert result["dimensions"] == {"系统设计": 1.0, "沟通表达": 4.0}
    assert result["warnings"]


def test_render_report_md_contains_sections():
    report = {
        "role_title": "后端开发实习生",
        "overall_score": 3.2,
        "verdict": "基本达标",
        "dimensions": {"系统设计": 3.0},
        "turns": [
            {
                "agent_label": "技术面试官",
                "question": "讲讲你的订单模块",
                "answer": "我做了幂等处理",
                "overall": 4,
                "competency": "系统设计",
                "evidence": "幂等处理",
                "comment": "思路清晰",
            }
        ],
        "strengths": ["表达清楚"],
        "improvements": ["补充量化"],
        "action_plan": ["准备三个项目故事"],
        "sample_answer": "可以按 STAR 结构回答",
    }
    md = toolkit.render_report_md(report)
    assert md.startswith("# 后端开发实习生")
    assert "| 系统设计 | 3.0 | 达标 |" in md
    assert "讲讲你的订单模块" in md
    assert "## 行动清单" in md
    assert "启发式参考" in md


def test_render_report_md_includes_cross_exam_table():
    report = {
        "role_title": "后端开发实习生",
        "overall_score": 3.0,
        "verdict": "基本达标",
        "dimensions": {},
        "cross_exam": {
            "question": "你怎么保证幂等？",
            "scores": {
                "hr": {"overall": 2, "comment": "没听清动机"},
                "tech": {"overall": 4, "comment": "方案可行"},
                "pressure": {"overall": 3, "comment": "论据一般"},
            },
            "merged": {"overall": 3},
        },
    }
    md = toolkit.render_report_md(report)
    assert "## 交叉拷问" in md
    assert "| 技术面试官 | 4 / 5 | 方案可行 |" in md
    assert "综合中位数：**3 / 5**" in md


def test_render_report_md_skips_cross_exam_when_absent():
    md = toolkit.render_report_md({"role_title": "岗位", "overall_score": 3.0})
    assert "## 交叉拷问" not in md


def test_export_report_writes_into_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(toolkit, "resolve_safe", lambda name: tmp_path / name)
    monkeypatch.setattr(toolkit, "display_path", lambda p: p.name)
    result = toolkit.export_report("report.md", "# 报告")
    assert result["path"] == "report.md"
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "# 报告"


def test_export_report_rejects_other_extensions(tmp_path, monkeypatch):
    monkeypatch.setattr(toolkit, "resolve_safe", lambda name: tmp_path / name)
    with pytest.raises(ValueError, match="仅支持导出"):
        toolkit.export_report("report.exe", "x")


def test_sandbox_rejects_parent_traversal():
    with pytest.raises(SandboxError):
        resolve_safe("../../etc/passwd")
