"""S4 · 真实模型冒烟回归：用真 DeepSeek 跑一次完整 6 题面试。

假模型测试全绿不代表线上能跑通（复盘 B3）。本脚本把「分析 → 逐题作答 → 追问 →
交叉拷问 → 报告 → 导出 PDF」整条链路真跑一遍，记录每次模型调用与耗时，
最后按断言判定通过与否，产出可贴进文档的实测记录。

**默认 dry-run，不发任何网络请求**。只有显式加 ``--run`` 才会消耗 API 额度。

用法::

    python scripts/smoke_real_llm.py                  # 检查配置与工具链，打印计划
    python scripts/smoke_real_llm.py --run            # 真跑（约 18 次模型调用）
    python scripts/smoke_real_llm.py --run --local    # 强制进程内直调，不走 MCP
    python scripts/smoke_real_llm.py --run --model deepseek-chat --questions 4

退出码：0 全部断言通过；1 有断言失败；2 配置不可用（缺 Key / 无法连工具）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.config import LLMConfig, load_config  # noqa: E402
from agent.orchestrator import InterviewConfig, InterviewSession, Orchestrator  # noqa: E402
from agent.state import Phase  # noqa: E402
from agent.tools import LocalTools, MCPTools, ToolProvider  # noqa: E402

# 脚本自带的样例输入，与界面「填入示例简历 / 示例 JD」同源，不读取 workspace 或用户文件。
RESUME_TEXT = """\
教育背景：广东工业大学 软件工程 本科 2022-2026，GPA 3.6/5.0
实习经历：某互联网公司 后端开发实习 2025.07-2025.09，负责交易系统订单模块
项目经历：校园二手交易平台，独立负责订单与支付链路，日活 3000 人
技术栈：Python、FastAPI、MySQL、Redis、Docker
项目成果：下单接口 P99 从 800ms 降到 120ms；缓存命中率 92%
"""

JD_TEXT = """\
后端开发实习生
职责：参与交易系统后端开发，负责接口设计与性能优化，参与线上问题排查。
要求：熟悉 Python 与常见 Web 框架；理解数据库索引与缓存设计；
能独立定位线上问题；有良好的工程习惯，会写单元测试。
"""

# 三段轮流使用，避免 6 题全用同一段回答导致出题重复、追问失控。
# 刻意避开 intent.py 的系统反馈关键词（报错 / 异常 / 超时 / bug 等），否则会被判为无效作答。
ANSWERS = [
    "在实习中负责订单模块重构，把下单接口 P99 从 800ms 降到 120ms。"
    "做法是先用慢查询日志定位到三条没走索引的 SQL，补了联合索引；"
    "再对热点商品加 Redis 缓存，命中率做到 92%。"
    "中间遇到过缓存和数据库不一致，最后用先更新库再删缓存的方案解决。",
    "我用 Python 和 FastAPI 写的订单接口，鉴权放在中间件里统一处理，"
    "请求体用 Pydantic 做参数校验，错误码按业务域分段。"
    "单元测试覆盖了下单幂等、库存不足、重复支付三种边界，"
    "上线前用 pytest 跑了 40 多个用例，接口变更时先补测试再改代码。",
    "如果 QPS 从 200 提到 900，我会先压测看瓶颈在哪一段。"
    "上次压测发现耗时集中在数据库，加了联合索引和连接池之后降到原来的三分之一；"
    "读多写少的商品详情再叠一层本地缓存。"
    "同时会看监控里的慢查询和连接数，避免把压力转移到数据库上。",
]


@dataclass
class ModelCall:
    """一次模型调用的原始记录，用于事后归因耗时与调用次数。"""

    schema: str
    seconds: float
    ok: bool


class CountingClient:
    """给 LLMClient 套一层计数与计时，编排层无感知。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: list[ModelCall] = []

    def chat_json(self, messages: Any, schema: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        ok = False
        try:
            result = self._inner.chat_json(messages, schema, **kwargs)
            ok = True
            return result
        finally:
            self.calls.append(
                ModelCall(schema=getattr(schema, "__name__", str(schema)),
                          seconds=time.perf_counter() - start, ok=ok)
            )


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SmokeRecord:
    started_at: str = ""
    model: str = ""
    base_url: str = ""
    tools: str = ""
    dry_run: bool = True
    first_round_seconds: float = 0.0
    answer_seconds: list[float] = field(default_factory=list)
    followups: int = 0
    finish_seconds: float = 0.0
    turns: int = 0
    overall_score: float = 0.0
    verdict: str = ""
    cross_exam: bool = False
    industry: str = ""
    model_calls: int = 0
    model_seconds_total: float = 0.0
    md_path: str = ""
    pdf_path: str = ""
    pdf_bytes: int = 0
    checks: list[Check] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)


# ---------- 参数与环境 ----------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="真实模型冒烟回归（默认 dry-run，不发请求）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--run", action="store_true", help="真的调用大模型；不加只做检查")
    parser.add_argument("--questions", type=int, default=6, help="面试题数")
    parser.add_argument("--model", default="", help="覆盖 OPENAI_MODEL，例如 deepseek-chat")
    parser.add_argument(
        "--local", action="store_true", help="强制进程内直调（LocalTools），不启动 MCP 子进程"
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="单次模型调用超时（秒）")
    parser.add_argument(
        "--out", default="reports", help="实测记录 JSON 的输出目录（已在 .gitignore）"
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> LLMConfig:
    base = load_config()
    return LLMConfig(
        base_url=base.base_url,
        api_key=base.api_key,
        model=args.model or base.model,
        use_mcp=base.use_mcp and not args.local,
    )


def mask_key(key: str) -> str:
    if len(key) <= 10:
        return "*" * len(key)
    return f"{key[:6]}…{key[-4:]}（{len(key)} 字符）"


def open_tool_provider(config: LLMConfig) -> ToolProvider:
    return MCPTools() if config.use_mcp else LocalTools()


# ---------- dry-run ----------


def dry_run(config: LLMConfig, args: argparse.Namespace, record: SmokeRecord) -> int:
    """不发请求：检查 Key、工具链与配置，打印将要发生的事。"""
    print("=" * 72)
    print("S4 真实模型冒烟回归 · dry-run（未发送任何请求）")
    print("=" * 72)
    print(f"模型      : {config.model}")
    print(f"接口地址  : {config.base_url}")
    print(f"API Key   : {mask_key(config.api_key) if config.api_key else '（未配置）'}")
    print(f"工具层    : {'MCPTools（stdio 子进程）' if config.use_mcp else 'LocalTools（进程内直调）'}")
    print(f"题数      : {args.questions}")
    record.tools = "MCPTools" if config.use_mcp else "LocalTools"

    if not config.configured:
        print()
        print("[不可用] 未配置有效 API Key：请确认 .env 中 OPENAI_API_KEY 为真实 Key。")
        record.checks.append(Check("API Key 已配置", False, "OPENAI_API_KEY 缺失或仍是占位符"))
        return 2
    record.checks.append(Check("API Key 已配置", True, "格式合法（未校验额度）"))

    # 工具链不发网络请求，真调用一次，确认 MCP 子进程能起、确定性工具有返回。
    print()
    print("检查工具链（本地确定性工具，不消耗额度）…")
    try:
        tools = open_tool_provider(config)
        quality = tools.check_resume_quality(RESUME_TEXT)
        match = tools.match_competencies(
            [
                {"name": "系统设计", "weight": 0.4, "required_level": 4, "resume_level": 2},
                {"name": "工程实践", "weight": 0.3, "required_level": 4, "resume_level": 3},
                {"name": "沟通表达", "weight": 0.3, "required_level": 4, "resume_level": 4},
            ]
        )
        industry = tools.detect_industry(JD_TEXT)
    except Exception as exc:
        print(f"[不可用] 工具层初始化失败：{exc}")
        record.checks.append(Check("工具层可用", False, str(exc)[:200]))
        return 2

    gaps = match.get("gaps", [])
    print(f"  简历体检 : {len(quality)} 个字段返回")
    print(f"  缺口匹配 : {len(gaps)} 项缺口，最高优先级 {gaps[0]['competency'] if gaps else '（无）'}")
    print(f"  行业识别 : {industry}")
    record.industry = industry
    record.checks.append(Check("工具层可用", True, f"{record.tools} 返回缺口 {len(gaps)} 项"))

    estimate = 2 + args.questions * 2 + 3 + 1  # 分析2 + 每题打分&出题 + 交叉拷问3 + 报告1
    print()
    print("将要执行的流程（--run 时）：")
    print("  1. 简历体检（本地）→ 简历分析（1 次调用）")
    print("  2. 岗位能力建模（1 次调用）→ 缺口匹配（本地）→ 生成 6 个槽位")
    print(f"  3. 逐题作答 {args.questions} 题，每题「打分 + 出题」2 次并行调用，遇追问追加")
    print("  4. 交叉拷问：3 次调用（HR / 技术 / 压力各一次）")
    print("  5. 复盘报告：1 次调用 → 导出 Markdown 与 PDF")
    print(f"  预计模型调用约 {estimate} 次（去重重试或追问会更多），耗时约 60–150 秒。")
    print()
    print("dry-run 结束。确认额度后加 --run 执行。")
    return 0


# ---------- 真跑 ----------


def run_interview(config: LLMConfig, args: argparse.Namespace, record: SmokeRecord) -> int:
    from agent.llm import LLMClient

    print("=" * 72)
    print("S4 真实模型冒烟回归 · 真跑（会消耗 API 额度）")
    print("=" * 72)
    print(f"模型 {config.model}｜工具层 {record.tools}｜题数 {args.questions}")

    try:
        inner = LLMClient(config, timeout=args.timeout)
    except Exception as exc:
        print(f"[不可用] 无法初始化模型客户端：{exc}")
        return 2

    llm = CountingClient(inner)
    tools = open_tool_provider(config)
    interview_config = InterviewConfig(
        max_questions=args.questions,
        allow_followups=True,
        run_cross_exam=True,
        industry="自动",
    )
    orchestrator = Orchestrator(llm, tools, interview_config)

    print()
    print("阶段 1/3：分析简历与岗位…")
    start = time.perf_counter()
    session = orchestrator.start(RESUME_TEXT, JD_TEXT, "后端开发实习生")
    record.first_round_seconds = time.perf_counter() - start
    if session.error:
        record.errors.append(f"start: {session.error}")
        print(f"[失败] {session.error}")
        return 1
    assert session.competency_model is not None
    record.industry = session.industry
    names = [c.name for c in session.competency_model.competencies]
    print(f"  首轮耗时 {record.first_round_seconds:.1f} 秒（目标 ≤20 秒）")
    print(f"  识别行业 {session.industry}｜能力 {len(names)} 项：{'、'.join(names)}")
    print(f"  第一题 [{session.current_agent}] {_brief(session.current_question.text if session.current_question else '')}")

    print()
    print(f"阶段 2/3：作答 {args.questions} 题（遇追问照常再答）…")
    step = 0
    # 每个槽位最多追问 1 次（F6.4），因此最多 2 倍题数的作答轮次；再留 2 步余量。
    max_steps = args.questions * 2 + 2
    while not session.finished and step < max_steps:
        step += 1
        before_turns = len(session.turns)
        answer = ANSWERS[(len(session.turns)) % len(ANSWERS)]
        tick = time.perf_counter()
        session = orchestrator.answer(session, answer)
        elapsed = time.perf_counter() - tick
        if session.finished:
            # 末题提交里还跑着交叉拷问与报告生成，与「单题」不是同一件事，单独记。
            record.finish_seconds = elapsed
        else:
            record.answer_seconds.append(elapsed)
        if session.followup_used:
            # 答完后 followup_used 仍为 True，说明本题被追问、题号没前进。
            record.followups += 1
        if session.error and session.error.startswith("这段内容"):
            # 脚本自己的答案被意图过滤拦下，属于脚本问题，不是产品问题。
            record.errors.append(f"answer 被意图过滤：{session.error}")
            print(f"  [脚本错误] 答案被意图过滤挡回：{session.error}")
            return 1
        label = "追问" if session.followup_used else f"第 {before_turns + 1} 题"
        status = "进行中" if not session.finished else "进入结题"
        question = session.current_question.text if session.current_question else "（无下一题）"
        print(f"  {label} 提交 → {elapsed:.1f} 秒 → {status}｜下一题：{_brief(question)}")
        if session.error and not session.finished:
            record.errors.append(f"answer: {session.error}")
            print(f"  [失败] {session.error}")
            return 1

    record.model_calls = len(llm.calls)
    record.model_seconds_total = sum(c.seconds for c in llm.calls)
    record.turns = len(session.turns)
    if not session.finished:
        record.errors.append(
            f"流程未走完：phase={session.phase.value}，已答 {record.turns} 轮"
            f"（{record.followups} 次追问），上限 {max_steps} 步"
        )
        print(f"[失败] 流程未走完，phase={session.phase.value}")
        record.checks.append(
            Check("流程走到 DONE", False, f"phase={session.phase.value}，{record.turns} 轮作答")
        )
        return 1

    print()
    print("阶段 3/3：导出报告…")
    report_data = session.report_data
    record.overall_score = float(report_data.get("overall_score", 0.0))
    record.verdict = str(report_data.get("verdict", ""))
    record.cross_exam = session.cross_exam is not None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        markdown = tools.render_report_md(report_data)
        md_info = tools.export_report(f"smoke-{stamp}-report.md", markdown)
        record.md_path = str(md_info.get("path", ""))
        pdf_info = tools.export_report_pdf(f"smoke-{stamp}-report.pdf", report_data)
        record.pdf_path = str(pdf_info.get("path", ""))
        pdf_bytes = tools.render_report_pdf(report_data)
        record.pdf_bytes = len(pdf_bytes)
        print(f"  Markdown {len(markdown)} 字符 → {record.md_path}")
        print(f"  PDF {len(pdf_bytes) / 1024:.0f} KB → {record.pdf_path}")
        record.checks.append(Check("Markdown 报告已导出", bool(record.md_path), record.md_path))
        record.checks.append(Check("PDF 报告已导出", bool(record.pdf_path), record.pdf_path))
        record.checks.append(
            Check(
                "PDF 内嵌中文字体",
                b"/FontFile2" in pdf_bytes and len(pdf_bytes) > 16 * 1024,
                f"{len(pdf_bytes) / 1024:.0f} KB，/FontFile2 {'存在' if b'/FontFile2' in pdf_bytes else '缺失'}",
            )
        )
    except Exception as exc:
        record.errors.append(f"export: {exc}")
        record.checks.append(Check("报告导出成功", False, str(exc)[:200]))
        print(f"  [失败] 报告导出出错：{exc}")

    record.model_calls = len(llm.calls)
    record.model_seconds_total = sum(c.seconds for c in llm.calls)
    record.checks.extend(_collect_checks(session, record, args))
    return 0 if record.passed else 1


def _collect_checks(
    session: InterviewSession, record: SmokeRecord, args: argparse.Namespace
) -> list[Check]:
    """把本次真跑的判定条件集中成一组可复述的断言。"""
    covered = len({t.slot_index for t in session.turns})  # 追问落在同一槽位，不重复计题
    checks = [
        Check(
            "流程走到 DONE",
            session.phase == Phase.DONE,
            f"phase={session.phase.value}",
        ),
        Check(
            f"完成 {args.questions} 道不同的题",
            covered >= args.questions,
            f"{covered} 个槽位，共 {len(session.turns)} 轮作答",
        ),
        Check(
            "每个槽位最多追问 1 次",
            record.followups <= covered,
            f"{record.followups} 次追问 / {covered} 个槽位",
        ),
        Check(
            "首轮分析 ≤20 秒",
            record.first_round_seconds <= 20,
            f"{record.first_round_seconds:.1f} 秒",
        ),
        Check(
            "总分在 0–5 之间",
            0.0 <= record.overall_score <= 5.0,
            str(record.overall_score),
        ),
        Check("结论非空", bool(record.verdict), record.verdict),
        Check(
            "行动清单恰好 3 条",
            len(session.narrative.get("action_plan", [])) == 3,
            f"{len(session.narrative.get('action_plan', []))} 条",
        ),
    ]
    if session.cross_exam is not None:
        merged = session.cross_exam.merged.overall
        checks.append(Check("交叉拷问合并分在 0–5", 0 <= merged <= 5, str(merged)))
    elif args.questions >= 3:
        checks.append(Check("交叉拷问已执行", False, "session.cross_exam 为 None"))
    return checks


def _brief(text: str, limit: int = 46) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


# ---------- 汇总与落盘 ----------


def print_summary(record: SmokeRecord) -> None:
    print()
    print("=" * 72)
    print("实测记录")
    print("=" * 72)
    if record.dry_run:
        print("（dry-run，未调用模型）")
        return
    print(f"模型调用     : {record.model_calls} 次，累计 {record.model_seconds_total:.1f} 秒")
    print(f"首轮分析     : {record.first_round_seconds:.1f} 秒（目标 ≤20 秒）")
    if record.answer_seconds:
        per = record.answer_seconds
        avg = sum(per) / len(per)
        print(
            f"单题「打分+出题」: {len(per)} 次，{min(per):.1f}–{max(per):.1f} 秒，"
            f"中位数 {_median(per):.1f} 秒，均值 {avg:.1f} 秒（目标 ≤3 秒）"
        )
    print(f"作答轮次     : {record.turns}（其中追问 {record.followups} 次）")
    if record.finish_seconds:
        print(f"末题到报告   : {record.finish_seconds:.1f} 秒（含 3 次交叉拷问 + 1 次报告，无对应指标）")
    print(f"交叉拷问     : {'已执行' if record.cross_exam else '未执行'}")
    print(f"行业 / 总分  : {record.industry} / {record.overall_score}（{record.verdict}）")
    if record.pdf_path:
        print(f"报告产物     : {record.md_path}；{record.pdf_path}（{record.pdf_bytes / 1024:.0f} KB）")
    print()
    print("断言：")
    for check in record.checks:
        flag = "PASS" if check.passed else "FAIL"
        print(f"  [{flag}] {check.name}｜{check.detail}")
    if record.errors:
        print()
        print("错误：")
        for err in record.errors:
            print(f"  - {err}")
    print()
    print(f"结论：{'通过' if record.passed else '未通过'}")


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def write_record(record: SmokeRecord, out_dir: str) -> Path | None:
    if record.dry_run:
        return None
    directory = Path(out_dir)
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = directory / f"smoke-{stamp}.json"
    payload = {
        **record.__dict__,
        "checks": [c.__dict__ for c in record.checks],
        "passed": record.passed,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = build_config(args)
    record = SmokeRecord(
        started_at=datetime.now().isoformat(timespec="seconds"),
        model=config.model,
        base_url=config.base_url,
        tools="MCPTools" if config.use_mcp else "LocalTools",
        dry_run=not args.run,
    )

    if not args.run:
        code = dry_run(config, args, record)
    else:
        code = run_interview(config, args, record)
    print_summary(record)
    record_path = write_record(record, args.out)
    if record_path:
        print(f"\n实测记录已写入 {record_path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
