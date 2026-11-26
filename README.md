# 面面俱到 · 模拟面试多智能体

[![CI](https://github.com/Jiyue0321/gdut-homework4/actions/workflows/ci.yml/badge.svg)](https://github.com/Jiyue0321/gdut-homework4/actions/workflows/ci.yml)

> 粘贴一份简历和一份岗位 JD（或直接上传 PDF），让 HR、技术、压力三位 AI 面试官轮流发难。

**在线体验**：<https://interview-agent-test.streamlit.app>

> 免费实例无访问时会休眠，冷启动约 30–60 秒，期间页面显示「Your app is waking up」，等待即可。
> 演示或答辩前请提前打开一次预热。

**界面原型**：`prototype/index.html`，浏览器直接打开即可（单文件、零依赖、无需构建）。
前台 3 页 + 后台 4 页的高保真交互原型，不接后端，用于展示下一版界面设计；
打开方式、演示数据边界与答辩截图清单见 [prototype/README.md](prototype/README.md)。

**只读后台**：运行主站后，侧边栏进入「后台管理」，可查看题库统计、系统配置与本次会话的
模型/工具调用记录。数据全部来自真实系统，**不写任何内容**——跨会话统计需要持久化，见
[原型后台接口约定](docs/prototype-api.md) §5.2。

应届生和转行者缺的往往不是题库，而是**有人像真实面试官一样追问到底，并告诉你差在哪里**。
本项目用多智能体协作复现真实面试：先读简历与岗位，找出能力缺口，再针对缺口定向出题、
逐层追问、交叉拷问，最后给出一份可执行的复盘报告。

## 功能

- **简历 × 岗位缺口雷达**：把 JD 要求、简历自评、面试实测三组能力画在同一张雷达图上
- **文件导入**：简历与 JD 支持直接上传 PDF / TXT / Markdown，自动抽取文字后可再编辑
- **三类面试官**：HR、技术、压力面试官各有考察侧重与评分口径
- **行业定制题库**：98 道参考题覆盖后端、前端、AI、数据分析、测试、嵌入式、产品运营、金融科技
  等 9 个行业，按 JD 自动识别或手动指定
- **自适应追问**：回答含糊或缺量化依据时，追问一次
- **交叉拷问**：针对最弱的一题，三位面试官轮流发难并独立打分
- **复盘报告**：加权总分、逐题证据、改进建议与话术模板，可导出 Markdown 或 PDF

## 架构

```
Streamlit 界面（5 步向导）
  └─ agent/orchestrator.py         确定性状态机：阶段流转、题量上限、评分聚合
       ├─ agent/agents/*            无状态智能体：简历分析 / 岗位分析 / 面试官 / 评估 / 报告
       ├─ agent/llm.py              结构化 JSON 输出（OpenAI 兼容接口）
       └─ agent/tools.py            ToolProvider ─┬─ LocalTools（进程内直调）
                                                  └─ MCPTools（stdio 子进程）
                                                       └─ mcp_server/interview_server.py
                                                          确定性工具：缺口匹配、抽题、
                                                          评分聚合、报告渲染（MD/PDF）
```

设计取向：**智能体的自主性用在提问与追问，关键流程由代码保证可复现、可测试。**
评分不交给模型自由发挥——大模型产出 rubric 与维度分，加权、裁剪、交叉合并全部由确定性代码完成。

## 目录

| 目录 | 说明 |
| --- | --- |
| `app.py` | Streamlit 入口与 5 步向导 |
| `pages/` | 只读后台页（概览 / 题库 / 配置 / 运行日志），与主站共享会话 |
| `agent/` | 编排器、智能体、LLM 封装、确定性工具客户端、语音接口 |
| `mcp_server/` | MCP 工具服务、评分函数、题库、路径沙箱 |
| `ui/` | 页面与组件（雷达图、评分卡、对话记录、报告） |
| `prototype/` | 高保真界面原型，单文件静态页，见 [prototype/README.md](prototype/README.md) |
| `tests/` | 单元测试与 golden 集成测试 |
| `scripts/` | 真实模型冒烟脚本 `smoke_real_llm.py`（默认 dry-run） |
| `docs/` | 需求、设计、冲刺复盘、稳定性验证、原型接口约定 |
| `workspace/` | 导出的面试报告（沙箱目录） |

## 快速开始

**Windows 一键启动**：双击 `start.bat`。脚本会自动创建 `.venv`、安装依赖、
在缺少 `.env` 时从模板复制一份并打开编辑，然后启动服务。

手动启动：

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # 填入 API Key
streamlit run app.py
```

浏览器打开 <http://localhost:8501>。模型接口为 OpenAI 兼容协议，默认 DeepSeek，
可通过 `OPENAI_BASE_URL` / `OPENAI_MODEL` 切换到通义千问、智谱 GLM。

## 测试

```bash
pytest                  # 单元 + golden 集成测试，不调用真实模型
pytest -m slow          # 需要真实 API Key 的联调测试
pytest --cov=agent --cov=mcp_server --cov=ui --cov=app --cov-report=term-missing
python scripts/smoke_real_llm.py          # 真实模型冒烟：默认 dry-run，只检查配置与工具链
python scripts/smoke_real_llm.py --run    # 真跑完整 6 题，会消耗 API 额度
```

当前 **185 passed / 1 deselected**，语句覆盖率 **85%**（`agent` / `mcp_server` / `ui` / `pages` / `app.py`，
共 2142 条语句，未覆盖 331 条）。

| 模块 | 覆盖率 | 说明 |
| --- | --- | --- |
| `agent/orchestrator.py` | 94% | 状态机主路径与失败分支 |
| `agent/telemetry.py` | 93% | 观测层：调用计数、耗时、失败标记与事件上限 |
| `mcp_server/pdf_report.py` | 95% | 含字体未内嵌时的回退分支 |
| `mcp_server/toolkit.py` | 94% | 缺口匹配、抽题、评分聚合 |
| `ui/` | 81–90% | 页面渲染与下载按钮 |
| `pages/` | 73% | 只读后台页；基于会话状态的概览分支未在用例中铺满 |
| `mcp_server/interview_server.py` | 0% | 仅由 `tests/integration/test_mcp_server.py` 以子进程方式调用，`coverage` 不跨进程统计 |
| `agent/voice.py` | 0% | 只有 Protocol 与 `NotImplementedError` 占位，无逻辑可测 |

CI（`.github/workflows/ci.yml`）在每次 `push` 与 `pull_request` 到 `main` 时自动执行同一套命令，
完整覆盖率报告作为 Actions 产物提供下载。

## 部署

线上实例：<https://interview-agent-test.streamlit.app>（Streamlit Community Cloud，从本仓库直接部署）

Streamlit Cloud 直接从 GitHub 部署。密钥写在应用的 Secrets 中：

```toml
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL = "deepseek-chat"
```

部署注意事项：

- **冷启动**：免费实例无访问时休眠，唤醒约 30–60 秒。
- **工具路径**：`agent/tools.py` 提供 `LocalTools`（进程内直调）与 `MCPTools`（stdio 子进程）
  两套等价实现，用 Secrets 中的 `USE_MCP` 切换。云端若 MCP 子进程受限，设
  `USE_MCP = "false"` 走进程内直调即可，功能一致。
- **PDF 字体**：中文字体 `assets/fonts/SimHei.ttf` 随仓库分发，`mcp_server/pdf_report.py` 会优先内嵌它；
  都找不到时回退到 reportlab 的 `STSong-Light` CID 字体（此时中文能否显示取决于阅读器）。
  **判据是文件大小而不是肉眼看中文**：导出的 PDF 若只有十几 KB，说明走了回退（内嵌字体的报告 ≥35 KB）。
  报告页在未内嵌时会直接提示；`tests/unit/test_pdf_font.py` 也断言了这一点。
- **模型选择**：`deepseek-chat` 单题约 3 秒；`deepseek-flash` 带推理 token，延迟约翻倍，
  对 N5 的「单题 ≤3 秒」指标有压力，演示与测试建议用 `deepseek-chat`。

## 团队

| 学号 | 姓名 | 分工 |
| --- | --- | --- |
| - | - | - |

## 文档

| 文档 | 内容 |
| --- | --- |
| [软件需求规格说明书](docs/requirements.md) | F1–F11 功能需求、N1–N8 非功能需求、验收标准与代码对应表 |
| [Alpha 冲刺复盘](docs/alpha-retrospective.md) | 现状盘点、现存问题、落地方案、冲刺目标、计划 vs 实际 |
| [成员分工与工作量](docs/alpha-workload.md) | S1–S11 任务的交付物、人天与占比 |
| [云端稳定性验证记录](docs/stability-check.md) | 冷启动、MCP 路径、PDF 字体、完整流程的实测数据 |
| [真实模型冒烟回归记录](docs/smoke-real-llm.md) | 真 DeepSeek 跑完整链路的脚本、判定条件与实测记录 |
| [原型后台接口约定](docs/prototype-api.md) | 后台各页数据来源、Alpha 只读实现记录与 Beta 持久化 A 计划 |
| [原型说明](prototype/README.md) | 打开方式、技术栈、演示数据边界、答辩截图与录屏清单 |
| [v0.9.0 Release 正文](docs/release-notes-v0.9.0.md) | Alpha 基线版本的发布说明 |

设计说明书（系统设计 34 页、数据库设计 24 页）见 `docs/` 下两份 PDF。
