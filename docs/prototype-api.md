# 原型后台接口约定

**项目**：面面俱到 · 模拟面试多智能体
**对应任务**：Alpha 冲刺 S10
**文档版本**：V1.1（待双签）　**编写日期**：2026-11-23　**最近更新**：2026-11-26（补 Alpha 只读后台落地记录与 Beta 持久化 A 计划）
**主笔**：后端 / 部署角色　**确认**：前端 / 原型角色

> **本文档的性质**：只写「页面上的每个字段从哪来」，**Alpha 期内不实现后台功能**。
> 目的是让 Beta 接后端时不用重新猜一遍数据来源——现在标清楚，将来照表实现即可。

---

## 0. 签署

| 角色 | 关注点 | 签署 |
| --- | --- | --- |
| 后端 / 部署 | 每个字段能否在现有 `toolkit` 找到出处；标 🆕/⏳ 的是否接受 | |
| 前端 / 原型 | 页面要展示的字段是否被本文档覆盖；缺的补进本文档 | |

双方都签字后本表才算 S10 完成。**只有后端签字不算。**

---

## 1. 状态标记约定

本文档每个字段都带一个标记，含义固定：

| 标记 | 含义 | Beta 期要做的事 |
| --- | --- | --- |
| ✅ | **现有**：当前代码里已有，直接可用 | 无需改动 |
| 🆕 | **新增只读**：数据在现有模块里，但没暴露成工具，需要加一个只读函数 | 加函数 + 加 MCP tool，不改数据 |
| ⏳ | **需持久化**：现有系统是「一次会话一个 `session_state`」，会话结束即丢，没有任何落库 | 随 V2.2 的 SQLite 一起做 |
| 🚫 | **Alpha / Beta 不做**：明确写出来，避免答辩时被问「为什么这个没做」答不上 | 记进 `docs/backlog.md` |

**为什么有这么多 ⏳**：现在整个系统是**无状态**的——`InterviewSession` 只活在 Streamlit 的
`session_state` 里，页面一刷新、浏览器一关就没了；`workspace/` 只存导出的报告文件，不存会话记录。
所以**任何跨会话的统计（概览页全部指标、题库使用次数）在 Beta 之前都算不出来**，这不是偷懒，
是数据根本没留下。这一点必须在答辩时说清楚，否则「后台概览」会显得像没做完。

---

## 2. 页面与数据总览

原型的三个视图（前台 3 页 + 后台 4 页 + 规则说明页）与本文档的对应关系：

| 原型页面 | 本文档章节 | 数据完备度 | Alpha 结论 |
| --- | --- | --- | --- |
| 前台 · 录入页 | §3.1 | 约 85% ✅ | 原型视觉可做，接后端无阻塞 |
| 前台 · 面试进行页 | §3.2 | 约 70% | 「简历证据高亮」缺字段，见 §6-1 |
| 前台 · 复盘报告页 | §3.3 | 约 90% ✅ | 现有报告数据基本够用 |
| 后台 · 概览 | §4.1 | 约 10% | 几乎全是 ⏳，见 §1 说明 |
| 后台 · 题库 | §4.2 | 约 65% | 缺难度、使用次数、启用状态 |
| 后台 · 配置 | §4.3 | 约 55% | Key 不可回显；Prompt 可读不可改 |
| 后台 · 日志 | §4.4 | 0% | **明确写「待 V2.2」** |
| 规则说明页 | — | 不涉及数据 | 纯说明页，内容即 R1–R10 与本章 §5、§6 |

---

## 3. 前台三页

### 3.1 录入页

原型字段：简历 / JD 双栏、拖拽上传、行业下拉、「1 分钟生成 5+5 精品问题」承诺。

| 原型元素 | 字段 | 数据来源 | 状态 |
| --- | --- | --- | --- |
| 简历文本 | `resume_text` | 用户粘贴 | ✅ |
| 简历拖拽上传 | 解析出的文本 | `toolkit.extract_document_text(filename, bytes)` | ✅ 已有，但原型要走浏览器端 `File API`，需确认前端能否直接调 Python 工具（见 §6-2） |
| JD 文本 | `jd_text` | 用户粘贴 | ✅ |
| JD 拖拽上传 | 同上 | 同上 | ✅ |
| 行业下拉 | `industry` | `toolkit.list_industries()` → `["通用", "互联网后端", …]` 共 9 项 | ✅ |
| 「自动识别」选项 | 识别结果 | `toolkit.detect_job_industry(jd_text)` | ✅ 纯关键词打分，见 `data/question_bank.py:INDUSTRY_KEYWORDS` |
| 岗位名称 | `role_title` | 用户填写，空则回落 `"目标岗位"` | ✅ |
| 简历体检提示 | `tips[]` | `toolkit.check_resume_quality(text)["tips"]` | ✅ 已在用，原型可展示为输入框下方的黄色提示条 |
| 「1 分钟生成 5+5 精品问题」 | — | **现有实现不是 5+5**，见 §6-3 | ⚠️ 文案需与实现对齐 |

### 3.2 面试进行页

原型字段：左侧按能力分段的进度条、右上总分、右侧「简历证据」高亮原文、追问 chip（`追问 1` / `重新提问`）。

| 原型元素 | 字段 | 数据来源 | 状态 |
| --- | --- | --- | --- |
| 进度条分段 | 各题考察能力 | `session.plan.slots[i].competency` | ✅ |
| 进度条完成度 | 当前进度 | `session.slot_index` / `len(session.plan.slots)` | ✅ |
| 右上总分 | 实时总分 | 暂无「实时」总分，只有终局 `overall_score`；需在每轮后用 `toolkit.aggregate_scores(session.turn_records(), session.weights())` 重算 | 🆕 加一个 `partial_score` 只读工具（内部就是调 `aggregate_scores`，已存在，只需暴露） |
| 当前提问 | 题目文本 | `session.current_question.text` | ✅ |
| 面试官身份 | 角色名 | `session.current_agent` → `AGENT_LABELS` | ✅ |
| 本题考察能力 | `competency` | `session.current_question.competency` | ✅ |
| 评分要点 | `criteria[]` | `session.current_question.rubric.criteria` | ✅ |
| 追问标记 | 是否追问 | `session.followup_used` | ✅ |
| 单题得分 | `overall` | `session.turns[-1].score.overall` | ✅ |
| 单题维度分 | `dimensions` | `session.turns[-1].score.dimensions` | ✅ |
| **简历证据高亮** | 简历原文片段 | **无对应字段**，见 §6-1 | 🚫 Alpha 不做 |
| 「重新提问」按钮 | — | 现有只有「重试当前步骤」（`orchestrator.retry`），语义是失败重试，**不是换一题** | 🆕 需新接口，见 §6-4 |

### 3.3 复盘报告页

原型字段：竞争力结论、得分概览（本轮 3.5/5、满分 5/5）、能力图表（雷达）、Q&A 逐题分析（带 `nice`/`good`/`warning` 标签）、行动计划（提升建议 / 时间预估 / 对应官方内容）。

其实这一页是**现有数据最完整**的一页——`session.report_data` 就是为它准备的。

| 原型元素 | 字段 | 数据来源 | 状态 |
| --- | --- | --- | --- |
| 竞争力结论 | `verdict` | `toolkit.aggregate_scores()["verdict"]`（`mcp_server/rubric.py:overall_verdict`，按 4.0 / 3.0 / 2.0 三档） | ✅ |
| 本轮总分 | `overall_score` | 同上，`rubric.weighted_total`，0–5 保留一位小数 | ✅ |
| 满分 | `5.0` | `rubric.SCORE_MAX` | ✅ |
| 雷达图三条线 | `radar[]` | `toolkit.match_competencies()` 返回 `{competency, required, resume, weight}` | ✅ |
| 雷达图「面试实测」线 | `dimensions` | `toolkit.aggregate_scores()["dimensions"]` | ✅ |
| Q&A 逐题 | 完整问答 | `session.qa_pairs`：`index / agent / agent_label / question / answer / overall / competency / comment / evidence / is_followup` | ✅ |
| 逐题标签 `good`/`warning` | — | **无字段**，需由 `overall` 推导，见 §6-5 | 🆕 加推导规则（前端算即可，不必后端出） |
| 「追问 1」小标 | `is_followup` | `session.qa_pairs[i].is_followup` | ✅ |
| 行动清单 | `action_plan[]` | `session.narrative["action_plan"]`，模型产出 3 条 | ✅ |
| 提升建议 | `improvements[]` | `session.narrative["improvements"]`，2–3 条 | ✅ |
| 时间预估 | 「2 周」 | **无字段** | 🚫 Alpha 不做；模型每次产出的时长不可复现，写死会误导 |
| 对应官方内容 | — | **无字段** | 🚫 需要知识库支撑，记进 backlog |
| 参考答案示范 | `sample_answer` | `session.narrative["sample_answer"]` | ✅ |
| 导出 Markdown | 全文 | `toolkit.render_report_md(report)` | ✅ |
| 导出 PDF | 字节流 | `toolkit.render_report_pdf_bytes(report)` | ✅ 中文 A4 |

---

## 4. 后台三页

### 4.1 概览页

原型指标：会话数 1,284 / 完成率 78% / 平均总分 3.8 / AI 调用次数 12,460 / 近 7 天趋势 / 能力维度分布 / 近期会话列表。

**这一页的数据在当前系统里一条都不存在。** 逐项列出，是为了让前端知道「Beta 之前这页只能用演示数据」。

| 原型元素 | 字段 | 数据来源 | 状态 |
| --- | --- | --- | --- |
| 会话数 | `total_sessions` | `interview_sessions` 表 `COUNT(*)` | ⏳ V2.2 |
| 完成率 | `completion_rate` | 同上，`phase='done'` 占比 | ⏳ V2.2 |
| 平均总分 | `avg_score` | 同上，`overall_score` 均值 | ⏳ V2.2 |
| AI 调用次数 | `llm_calls` | **当前 `agent/llm.py` 无计数器**，需在 `_complete()` 里埋一个计数 | 🆕 + ⏳ |
| 近 7 天趋势 | `daily[]` | 按 `created_at` 分天聚合 | ⏳ V2.2 |
| 能力维度分布 | `competency_avg[]` | 历史 `turns` 按能力聚合，函数已存在：`rubric.competency_averages` | 🆕 加跨会话版本 + ⏳ |
| 近期会话列表 | `recent[]` | `id / role_title / score / verdict / duration / created_at` | ⏳ V2.2 |

> 表结构草案（Beta 用，Alpha 不建表）：
> `interview_sessions(id, role_title, industry, phase, overall_score, verdict, turn_count, created_at, duration_sec)`
> `interview_turns(session_id, idx, agent, competency, question, answer, score, is_followup)`

### 4.2 题库页

原型指标：题量 98 道 / 注意行业覆盖 / 平均使用次数 2.6；表格列 `id / 题目 / 行业 / 难度 / 功能标签 / 使用次数 / 状态`。

现有 `data/question_bank.json` 的结构是 `{id, agent, industry, competencies[], text}`，**只有 5 个字段**。

| 原型元素 | 字段 | 数据来源 | 状态 |
| --- | --- | --- | --- |
| 题库总量 | `98` | `len(toolkit.load_bank())` | ✅ |
| 覆盖行业数 | `9` | `len(toolkit.industries_in_bank())`（含通用） | ✅ |
| 按行业筛选 | `industry` | 同名字段，精确匹配 | ✅ |
| 按角色筛选 | `agent` | 同名字段，`hr` / `tech` / `pressure`（当前 27 / 45 / 26） | ✅ |
| 题号 | `id` | 同名字段，如 `hr-01` | ✅ |
| 题目 | `text` | 同名字段 | ✅ |
| 功能标签 | `competencies[]` | 同名字段，`data/question_bank.json` 的 `competencies` 共 10 个标签 | ✅ |
| **难度** | `difficulty` | **字段不存在** | 🆕 加字段（`easy`/`medium`/`hard`）+ 需人工标注 98 条 |
| **使用次数** | `usage_count` | **无记录**，出题时没埋点 | 🆕 埋点 + ⏳ V2.2 |
| **状态** | `status` | **字段不存在**，题库是只读 JSON | 🆕 加字段 + ⏳ V2.2（要能改就得落库） |
| 平均使用次数 | 派生 | 同上 | ⏳ V2.2 |
| 题库覆盖率 | 派生 | 建议定义为「每个 (行业 × 角色) 组合的题数 ≥ 3 的比例」 | 🆕 定义未定，**需前端确认口径** |
| 新增题目 / 批量导入 | — | 目前只能改 JSON 文件 | ⏳ V2.2（写操作） |

> ⚠️ 98 条题目人工补 `difficulty` 是 1 人天左右的工作量，**Beta 前不要排进计划**。

### 4.3 配置页

原型字段：大模型设置（模型、Endpoint、Key、温度、最大 Token）、Prompt 模板、行业配置、修改密码。

| 原型元素 | 字段 | 数据来源 | 状态 |
| --- | --- | --- | --- |
| 当前模型 | `model` | `load_config().model`，如 `deepseek-chat` | ✅ |
| Endpoint | `base_url` | `load_config().base_url` | ✅ |
| Provider | `provider` | `LLM_PROVIDER`，可选 `deepseek` / `qwen` / `glm` | ✅ |
| **API Key** | — | `load_config().api_key` | 🚫 **页面绝不回显**。只显示「已配置 / 未配置」+ 掩码 `sk-****abcd`，来源 `config.configured` |
| 温度 | `temperature` | **硬编码**在 `agent/llm.py:chat_json(temperature=0.2)` 调用点 | 🆕 需下沉到 `LLMConfig` 才能展示 |
| 最大 Token | `max_tokens` | 同上，默认 `2048` | 🆕 同上 |
| Prompt 模板列表 | 8 个常量 | `agent/prompts/__init__.py`：`RESUME_ANALYST` / `JD_ANALYST` / `INTERVIEWER_CONTEXT` / `INTERVIEWER_SCORE_RULES` / `INTERVIEWER_QUESTION_RULES` / `CROSS_EXAM` / `EVALUATOR` / `REPORT_WRITER` | ✅ 可读出，🚫 编辑需落盘 → V2.2 |
| 行业配置 | 8 个行业关键词组 | `mcp_server/question_bank.py:INDUSTRY_KEYWORDS`（另有「通用」） | ✅ 可读出，🚫 编辑 → V2.2 |
| 修改密码 | — | **系统没有用户体系**，不存在密码 | 🚫 原型里的这个入口 Beta 前删掉或置灰 |

### 4.4 日志页

**不在 Alpha 范围内，明确写「待 V2.2」。**

理由：日志需要「会话表 + 错误表」两张持久化表，而持久化本身就是 V2.2 的事。Alpha 期内这页
只保留导航入口并显示空状态（"日志功能将于 V2.2 提供"），不做任何假数据。

---

## 5. 需要新增的工具（Beta 前置清单）

按「不改数据 / 只读」优先排序，前三个是纯粹的暴露工作：

| # | 工具签名 | 用途 | 落在哪 | 工作量 |
| --- | --- | --- | --- | --- |
| 1 | `partial_score(turns_json, weights_json) -> {overall_score, dimensions}` | 面试进行页右上实时总分 | `mcp_server/toolkit.py`，内部直接调 `aggregate_scores` | ✅ 已在后台页内联实现 |
| 2 | `list_bank_stats() -> {total, by_industry, by_agent, by_competency}` | 题库页三张统计卡 | 同上，包一层 `load_bank()` | ✅ 已在后台页内联实现 |
| 3 | `list_prompt_templates() -> {name, text}[]` | 配置页 Prompt 列表 | 同上，读 `agent/prompts` 常量 | ✅ 已在后台页内联实现 |
| 4 | `llm_call_count()` | 概览页 AI 调用次数 | `agent/llm.py` 加 `itertools.count` 计数器 | ✅ 已由 `agent/telemetry.py` 的会话记录器代替 |
| 5 | 题库 `difficulty` / `status` 字段 | 题库页筛选与状态 | `data/question_bank.json` + `pick_questions` 过滤 | 1 天（含人工标注） |
| 6 | 会话 / 轮次入库 | 概览页全部指标 | 随 V2.2 SQLite | 3 天+ |

> 1–4 在 Alpha 期已用「页面内联 + 会话级观测」的方式落地（见 §5.1），**不新增 MCP 工具**——
> 这几项都是纯读，没必要为它们多绕一层子进程。5–6 是 V2.2 的活，Alpha 不碰。

### 5.1 Alpha 已落地的只读后台（2026-11-26）

Alpha 期确认「只读后台、不碰持久化」，实现为独立的 Streamlit 多页面 `pages/1_后台管理.py`，
与主站共享 `st.session_state`，**不改动 `app.py` 的任何流程**。

| 页面 | 实现方式 | 数据真实性 |
| --- | --- | --- |
| 数据概览 | 读 `st.session_state.session`，用 `rubric.competency_averages` / `weighted_total` 实时聚合 | **本次会话真实数据**；跨会话指标明确标注「待 V2.2」 |
| 题库管理 | 直接读 `data/question_bank.json`，前端筛选 + 导出筛选结果 | **全站真实数据**（98 题 / 9 行业 / 27·45·26） |
| 系统配置 | 读 `load_config()`、`agent/prompts` 常量、`INDUSTRY_KEYWORDS`，Key 只显示掩码 | **真实配置**；只读，不可改 |
| 运行日志 | `agent/telemetry.py` 的 `Recorder` 记录模型与工具调用 | **本次会话真实调用**；不落盘 |

**观测层的接线方式**：`app.py` 用 `CountingChat` / `InstrumentedTools` 把 `LLMClient` 与工具层
各包一层，只记调用次数、耗时与结果摘要，行为完全透传。`InstrumentedTools` 用 `__getattr__`
统一包装，将来新增工具无需改观测代码。

**为什么不做写入**：题库是只读 JSON、配置在 `.env` / Secrets、会话在浏览器里，三者都没有写入位置；
且 Streamlit Cloud 的容器文件系统在重启后重置，线上写文件本身不可靠。

### 5.2 Beta 持久化方案（A 计划：留在 Streamlit Cloud + 托管数据库）

**结论：加持久化不需要换部署方式。** 真正要解决的不是「在哪跑」，而是「数据放在一个不随容器消失的地方」。

| 方案 | 换部署 | 做法 | 成本 |
| --- | --- | --- | --- |
| **A. 留 Streamlit Cloud + 外部数据库**（推荐） | 否 | 接 Turso/libSQL 或 Supabase/Neon，加 1 个客户端依赖 + 1 条 Secrets | 低 |
| B. 换到有持久卷的平台 | 是 | Fly.io / Railway / Render 挂 volume，或 VPS 跑 Docker | 中高 |
| C. 不做持久化 | 否 | 维持只读后台，概览与日志只覆盖本次会话 | 低 |

**选 A 的理由**

- 部署方式一行不改：`requirements.txt` 加一个客户端库，Secrets 加一行 `DATABASE_URL`。
- 数据库由 Streamlit Cloud 的服务器直连，**与国内访问速度无关**，不经过用户本机网络。
- 免费额度远超课程项目所需（Turso 9 GB / Supabase 500 MB）。
- 免费实例休眠不影响：数据在外部，醒来接着查。

**A 的两个坑**

1. **HTTP 数据库每次写入有一次网络往返**，比本地 SQLite 慢一个数量级。会话结束写一条记录没问题，
   但**不要在每轮答题时同步写**——要么攒到会话结束一次性写，要么丢后台队列。
2. **写操作不能走 `lru_cache`**。题库的 `_load_raw` 有缓存，写入路径要绕开它。

**建议的代码形状**（关键是把持久化做成协议，默认走内存实现）

```
agent/storage.py
  ├─ Storage Protocol   record_session / list_sessions / stats
  ├─ MemoryStorage      测试与 AppTest 用，零依赖
  └─ RemoteStorage      Turso / Postgres 实现
```

这样 `tests/integration/test_app_flow.py` 的用例不连数据库，本地开发也不需要数据库就能跑，
换数据库只改一个实现类。§4.1 的建表草案（`interview_sessions` / `interview_turns`）可直接照用。

**为什么不选 B**：换平台要补 `Dockerfile`、处理 HTTPS、重验 PDF 中文字体回退链、重测冷启动——
这些在 `docs/stability-check.md` 里刚验证过，换平台等于全部作废。为一个后台页面做这件事性价比很低。

**排期建议**：A 的完整实现（建表、协议、接库、改路由、补测试、云端联调）约 6–7 人天，
建议排在 Beta 第一周，**不在 Alpha 冲刺期内做**。

---

## 6. 已知差异与待确认项

### 6-1 「简历证据高亮」在现有代码里没有对应字段（前端需知）

原型面试页右侧会把简历原文中**被引用到的那一句**高亮出来。现有 `AnswerScore.evidence`
是「从**回答**里摘的原文」，方向相反——它支撑的是打分，不是提问。

要做出高亮，需要模型额外输出简历片段的**字符偏移量**。让模型给 offset 不可靠（差一两个字就高亮错位），
可靠做法是让模型输出**原文片段字符串**，再由代码 `resume_text.find(fragment)` 定位。

**结论**：Alpha 不做。Beta 若要做，在 `Question` 模型加 `resume_span: str`，由代码反查位置。

### 6-2 原型的文件上传走浏览器 File API，与 Python 工具不在同一进程

现有 `extract_document_text` 是服务端 Python 函数，接收 `bytes`。原型若部署为**纯静态站点**
（S9 的部署方案），浏览器里没有 Python 运行时，**上传解析无法直接复用**。

三个选项，需前端确认走哪个：
1. 上传后把 base64 丢给一个轻量后端（Beta 才有）——最贴合现有代码；
2. 前端用 pdf.js 在浏览器里解析——多一份解析逻辑，结果可能与后端不一致；
3. **Alpha 期原型的上传按钮只做视觉，不真的解析**——推荐，符合「原型不接后端」的定位。

### 6-3 「1 分钟生成 5+5 精品问题」与现有实现不符

原型承诺「5 个简历精品问题 + 5 个岗位精品问题」。现有实现是：
`InterviewConfig.max_questions = 6`，按能力缺口排序后**在三类面试官间轮转**（hr → tech → pressure），
不区分「简历题 / 岗位题」，也不保证 5+5。

**结论**：Alpha 文案改为「约 6 道定制问题，含 1 次追问与 1 次交叉拷问」；若要保留 5+5 的承诺，
Beta 需在 `Slot` 加 `source: Literal["resume", "job"]` 并改 `_build_plan`。**现在不要改**。

### 6-4 「重新提问」按钮需要新接口

现有 `orchestrator.retry()` 的语义是「上一次出题失败了，重试」。原型要的是「这题我不想答，换一题」——
完全不同的行为，且会打乱 `slot_index` 与已答记录的对应关系。

**结论**：在 `InterviewSession` 加 `skipped: list[int]`，`retry` 加参数区分两种语义。**Beta 再做**。

### 6-5 逐题标签 `nice` / `good` / `warning` 的阈值待定

原型截图里标签有三种颜色。现有只有 `overall`（0–5 整数）。建议映射：

| 标签 | 含义 | 建议规则 |
| --- | --- | --- |
| `good` | 表现好 | `overall >= 4` |
| `nice` | 合格 | `overall == 3` |
| `warning` | 需加强 | `overall <= 2` |

规则**由前端计算**，后端不新增字段——这样后端保持干净，前端改阈值不用等发版。
**需前端确认这个映射是否符合视觉稿。**

### 6-6 后台导航有「日志」，但 Alpha 不做

见 §4.4。答辩时若被问到，回答：**日志依赖持久化，与 V2.2 的 SQLite 绑定，已在 backlog 中**。

---

## 7. 附：现有工具清单（供核对）

`mcp_server/interview_server.py` 当前注册的 **14** 个 MCP 工具，**全部可用于上述页面**：

| 工具 | 用于哪页 |
| --- | --- |
| `check_resume_quality` | 录入页 · 简历体检提示 |
| `match_competencies` | 录入页 / 报告页 · 雷达图与缺口 |
| `pick_questions` | 题库页 · 抽样预览 |
| `list_competencies` | 题库页 · 功能标签下拉 |
| `list_industries` | 录入页 · 行业下拉；配置页 · 行业配置 |
| `detect_industry` | 录入页 · 自动识别行业 |
| `extract_document` | 录入页 · 上传解析（见 §6-2） |
| `aggregate_scores` | 报告页 · 总分与维度 |
| `merge_cross_exam` | 报告页 · 交叉拷问中位数 |
| `render_report_md` | 报告页 · Markdown 导出 |
| `render_report_pdf` | 报告页 · PDF 导出 |
| `export_report` | 报告页 · Markdown 落盘到 `workspace/` |
| `export_report_pdf` | 报告页 · PDF 落盘到 `workspace/` |
| `get_current_time` | 报告落款 |

---

**修订记录**

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| V0.9 | 2026-11-23 | 初稿：按设计说明书附录 A 的 5 张原型截图逐字段核对，标注数据来源与缺口，待前后端双签 |
| V1.0 | 2026-11-26 | 原型源码入库 `prototype/` 后复核：工具数 13→14；后台结构由「2 页有内容」补全为 4 页，并纳入规则说明页；能力标签 13→10；题库字段按实际只有 5 个键说明 |
| V1.1 | 2026-11-26 | 新增 §5.1 Alpha 只读后台落地记录、§5.2 Beta 持久化 A 计划（留 Streamlit Cloud + 托管数据库）；§5 前四项标记为已在页面内联实现 |
