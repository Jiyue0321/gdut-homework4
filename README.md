# 面面俱到 · 模拟面试多智能体

> 粘贴一份简历和一份岗位 JD，让 HR、技术、压力三位 AI 面试官轮流发难。

应届生和转行者缺的往往不是题库，而是**有人像真实面试官一样追问到底，并告诉你差在哪里**。
本项目用多智能体协作复现真实面试：先读简历与岗位，找出能力缺口，再针对缺口定向出题、
逐层追问、交叉拷问，最后给出一份可执行的复盘报告。

## 功能

- **简历 × 岗位缺口雷达**：把 JD 要求、简历自评、面试实测三组能力画在同一张雷达图上
- **三类面试官**：HR、技术、压力面试官各有考察侧重与评分口径
- **自适应追问**：回答含糊或缺量化依据时，追问一次
- **交叉拷问**：针对最弱的一题，三位面试官轮流发难并独立打分
- **复盘报告**：加权总分、逐题证据、改进建议与话术模板，可导出 Markdown

## 架构

```
Streamlit 界面（5 步向导）
  └─ agent/orchestrator.py   确定性状态机：阶段流转、题量上限、评分聚合
       ├─ agent/agents/*      无状态智能体：简历分析 / 岗位分析 / 面试官 / 评估 / 报告
       ├─ agent/llm.py        结构化 JSON 输出（OpenAI 兼容接口）
       └─ agent/tools.py      ToolProvider ─┬─ LocalTools（进程内直调）
                                            └─ MCPTools（stdio 子进程）
                 └─ mcp_server/interview_server.py  确定性工具：缺口匹配、抽题、评分聚合、报告渲染
```

设计取向：**智能体的自主性用在提问与追问，关键流程由代码保证可复现、可测试。**
评分不交给模型自由发挥——大模型产出 rubric 与维度分，加权、裁剪、交叉合并全部由确定性代码完成。

## 目录

| 目录 | 说明 |
| --- | --- |
| `app.py` | Streamlit 入口与 5 步向导 |
| `agent/` | 编排器、智能体、LLM 封装、确定性工具客户端、语音接口 |
| `mcp_server/` | MCP 工具服务、评分函数、题库、路径沙箱 |
| `ui/` | 页面与组件（雷达图、评分卡、对话记录、报告） |
| `tests/` | 单元测试与 golden 集成测试 |
| `docs/` | 需求分析、架构说明、演示脚本、博客素材 |
| `workspace/` | 导出的面试报告（沙箱目录） |

## 快速开始

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
pytest              # 单元 + golden 集成测试，不调用真实模型
pytest -m slow      # 需要真实 API Key 的联调测试
```

## 部署

Streamlit Cloud 直接从 GitHub 部署。密钥写在应用的 Secrets 中：

```toml
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL = "deepseek-chat"
```

## 团队

| 学号 | 姓名 | 分工 |
| --- | --- | --- |
| - | - | - |

## 文档

- [需求分析文档](docs/requirements.md)
- [架构说明](docs/architecture.md)
