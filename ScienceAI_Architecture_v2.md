# ScienceAI：AI 驱动的科研辅助系统 — 完整架构设计（v2）

> 基于 2026 年 3 月最新模型规格：GPT-5.4 / Gemini 3.1 Pro / Claude Opus 4.6 & Sonnet 4.6

---

## 一、设计原则

**原则 1：能力驱动选型，而非品牌绑定。** 每个 Agent 的模型选择基于该任务所需的具体能力（推理深度、工具调用、批判分析），而非固定绑定某一家。模型作为运行时配置项，可随时替换。

**原则 2：反馈回路优先于线性流水线。** 科研是迭代的。系统必须允许下游结果反向修正上游决策——读完论文可能改变搜索策略，发现 gap 后需要回去验证是否已有人在做。

**原则 3：每一个结论必须可溯源。** 系统输出的每一条声明、每一个 research gap、每一个 idea，都必须能追溯到具体的论文、具体的段落。没有来源的结论不输出。

**原则 4：成本意识贯穿始终。** 三家模型价格差异显著。用最贵的模型做最需要深度推理的事，用最便宜的模型处理大规模筛选。利用 prompt caching 和 batch API 进一步降本。

**原则 5：渐进式构建。** 系统分阶段实现，每个阶段都能独立运行并产出价值。

---

## 二、三家模型最新规格与分工

### 2.1 模型规格对照表（2026 年 3 月实测数据）

| 规格 | GPT-5.4 | Gemini 3.1 Pro | Claude Opus 4.6 | Claude Sonnet 4.6 |
|------|---------|---------------|-----------------|-------------------|
| **上下文窗口** | 1,050,000 tokens | 1,000,000 tokens | 1,000,000 tokens | 1,000,000 tokens |
| **最大输出** | 128K tokens | 65K tokens | 128K tokens | 64K tokens |
| **输入价格** | $2.50/M | $2.00/M | $5.00/M | $3.00/M |
| **输出价格** | $15.00/M | $12.00/M | $25.00/M | $15.00/M |
| **缓存输入价格** | $0.25/M | $0.50/M（<200K）| 写入 1.25x，读取 0.1x | 写入 1.25x，读取 0.1x |
| **长上下文加价** | >272K: 2x input, 1.5x output | >200K: 2x input, 1.5x output | **无加价**（1M 全窗口统一价） | **无加价** |
| **批处理折扣** | 50%（Batch API） | 支持 | 50%（Batch API） | 50%（Batch API） |
| **推理能力** | 极强（reasoning effort 可调：none/low/medium/high/xhigh） | 强（DeepThink 引擎，thinking_level 可调） | 极强（adaptive thinking，四档 effort） | 强（adaptive thinking） |
| **工具调用** | 最成熟（原生 tool search，动态加载） | 良好 | 良好 | 良好 |
| **文本深度理解** | 强 | 强 | 最强（reviewer 风格分析） | 强 |
| **多模态** | 文本 + 图像输入 | 文本 + 图像 + 音频 + 视频 | 文本 + 图像 | 文本 + 图像 |
| **输出速度** | 快 | 快（120 t/s） | 中（Opus 偏慢；fast mode 可加速 2.5x） | 快 |
| **特色功能** | tool search、computer use、compaction | 原生视频/音频理解、DeepThink | adaptive thinking、compaction、web search | 性价比极高、接近 Opus 水平 |

### 2.2 关键发现：三家都有 ~1M 上下文

2026 年 3 月的格局与半年前完全不同——三家主力模型都已经达到 1M 级别的上下文窗口。这意味着：

- **模型选型不再以"上下文长度"为核心差异化因素**
- **真正的差异化在于：推理深度、工具调用成熟度、批判分析能力、价格**
- **成本优化的关键从"选上下文最长的模型"变成了"利用缓存和批处理"**

### 2.3 基于能力的角色分配

**GPT-5.4 — 编排与创意推理层**
- 研究规划（Query Planning）：最成熟的 tool search 和工具调用
- Agent 调度（Task Routing）：reasoning effort 可精细调节，简单调度用 none/low，复杂决策用 high
- Idea 生成：创造性推理 + 结构化输出
- 实验设计：多步推理 + 工具交互（搜索 API）
- 原因：tool search 功能是独有优势，可动态加载工具定义，大幅减少 token 消耗；reasoning effort 可按任务复杂度调节，兼顾速度和深度

**Gemini 3.1 Pro — 大规模处理与多模态层**
- 论文初筛（Triage）：利用高吞吐量批量处理 abstract
- 带图表的论文理解：原生支持图像、PDF、甚至视频
- 数据提取：从论文中提取表格、图表数据
- 原因：输入价格最低（$2.00/M），速度最快（120 t/s），且原生多模态支持最广，适合高吞吐低深度任务

**Claude Opus 4.6 — 深度分析与批判层**
- 论文精读：最强的文本深度理解能力
- 批判性分析：reviewer 风格的漏洞检测
- 跨论文对比：长文本 reasoning 最可靠
- 研究报告撰写：长文本生成质量最高
- 原因：1M 上下文无加价是核心优势，可以把多篇论文一次传入做对比分析而不产生额外费用

**Claude Sonnet 4.6 — 高性价比执行层**
- 标准结构化提取：方法/数据集/指标提取
- 验证任务：novelty check、搜索回查
- 中等复杂度分析：不需要 Opus 深度但需要高质量
- 原因：$3/$15 的价格接近 Gemini 水平，但分析质量接近 Opus，是整个系统的"主力军"

### 2.4 成本优化路由规则与估算

**Model Router 路由表：**

```
任务特征                          → 模型选择              → 预估成本/篇
──────────────────────────────────────────────────────────────────────
大批量论文初筛（仅 abstract）       → Gemini 3.1 Pro       → ~$0.001
论文全文解析（结构化提取）          → Claude Sonnet 4.6    → ~$0.02
带图表的论文处理                   → Gemini 3.1 Pro       → ~$0.015
论文精读（深度理解+批判分析）       → Claude Opus 4.6      → ~$0.10
跨论文对比（多篇同时传入）          → Claude Opus 4.6      → ~$0.15
研究规划与调度                     → GPT-5.4 (low effort) → ~$0.005
Gap 检测（复杂推理）               → GPT-5.4 (high effort)→ ~$0.06
Idea 生成与实验设计                → GPT-5.4 (medium)     → ~$0.04
验证与 novelty 检查               → Claude Sonnet 4.6    → ~$0.02
最终报告生成                       → Claude Opus 4.6      → ~$0.12
```

**成本优化策略：**

1. **Prompt Caching：** 系统提示（含结构化提取模板、角色定义）在所有请求中复用。三家都支持缓存，可将重复提示的成本降低 80-90%。
2. **Batch API：** 论文初筛和标准提取不需要实时响应，使用 Batch API 可获得 50% 折扣。
3. **Reasoning Effort 动态调节：** GPT-5.4 和 Claude 都支持调节推理深度。简单调度任务用 low/none，复杂推理用 high/xhigh。这是最直接的成本控制杠杆。
4. **Claude 1M 无加价优势：** 跨论文对比分析时，将 5-10 篇论文一次传入 Claude Opus（~200K tokens），不会产生长上下文加价。同样操作在 GPT-5.4 上会触发 2x 加价。

**示例成本估算：处理 200 篇论文的完整研究流程**

| 步骤 | 模型 | 论文数 | 单价 | 小计 | 备注 |
|------|------|--------|------|------|------|
| 初筛 | Gemini 3.1 Pro | 200 | $0.001 | $0.20 | Batch API，50% 折扣后 $0.10 |
| 全文提取 | Sonnet 4.6 | 60 | $0.02 | $1.20 | 通过初筛的论文 |
| 精读 | Opus 4.6 | 15 | $0.10 | $1.50 | 高相关性论文 |
| 批判分析 | Opus 4.6 | 15 | $0.10 | $1.50 | 同上 |
| 跨论文对比 | Opus 4.6 | 3 批 | $0.15 | $0.45 | 每批 5 篇一次传入 |
| 规划+调度 | GPT-5.4 | 多次 | — | $0.30 | 全流程累计 |
| Gap 检测 | GPT-5.4 | 3 轮 | $0.06 | $0.18 | high effort |
| Idea 生成 | GPT-5.4 | 2 轮 | $0.04 | $0.08 | |
| 验证 | Sonnet 4.6 | 10 个 gap | $0.02 | $0.20 | |
| 报告生成 | Opus 4.6 | 1 | $0.12 | $0.12 | |
| **总计** | | | | **$5.73** | |
| **Batch 优化后** | | | | **~$4.00** | 初筛+提取用 Batch API |

---

## 三、系统总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                     用户界面层 (UI Layer)                      │
│   Web Dashboard / CLI / API                                   │
└─────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│               编排层 (Orchestration Layer)                     │
│                      GPT-5.4 驱动                              │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Query Planner │  │ Task Router  │  │ Model Router       │  │
│  │ (GPT-5.4     │  │ (GPT-5.4     │  │ (规则引擎 +        │  │
│  │  + tool      │  │  low effort) │  │  reasoning effort  │  │
│  │  search)     │  │              │  │  动态调节)          │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘  │
│         │                 │                    │              │
│         └─────────────────┴────────────────────┘              │
│                           │                                   │
│                    ┌──────┴──────┐                             │
│                    │ Feedback    │ ◄── 下游结果可反向           │
│                    │ Controller  │     修正上游决策             │
│                    └─────────────┘                             │
└─────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                 Agent 层 (Agent Layer)                         │
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ Paper    │ │ Deep     │ │ Critique │ │ Gap            │  │
│  │ Triage   │ │ Reader   │ │ Agent    │ │ Detector       │  │
│  │(Gemini   │ │(Opus 4.6)│ │(Opus 4.6)│ │(GPT-5.4       │  │
│  │ 3.1 Pro) │ │          │ │          │ │ high effort)   │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬────────┘  │
│       │            │            │                │            │
│  ┌────┴─────┐ ┌────┴─────┐ ┌───┴──────┐ ┌──────┴────────┐  │
│  │ Idea     │ │ Verify   │ │ Report   │ │ Experiment    │  │
│  │Generator │ │ Agent    │ │ Writer   │ │ Planner       │  │
│  │(GPT-5.4  │ │(Sonnet   │ │(Opus 4.6)│ │(GPT-5.4       │  │
│  │ medium)  │ │ 4.6)     │ │          │ │ medium)       │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└─────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│               知识存储层 (Knowledge Memory)                    │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Paper Store  │  │ Vector Index │  │ Knowledge Graph    │  │
│  │ (PostgreSQL) │  │  (Qdrant)    │  │   (Neo4j)          │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐    │
│  │            Session Memory (Redis)                      │    │
│  │    当前研究上下文 / 中间结果 / 对话历史                    │    │
│  └───────────────────────────────────────────────────────┘    │
└─────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│               外部服务层 (External Services)                   │
│                                                               │
│  Semantic Scholar API  │  arXiv API  │  CrossRef API          │
│  Google Scholar        │  OpenAlex   │  PDF 存储 (S3)         │
└──────────────────────────────────────────────────────────────┘
```

---

## 四、八个核心 Agent 的详细设计

### Agent 1：Query Planner（研究规划 Agent）

**模型：** GPT-5.4（reasoning effort: medium）
**输入：** 用户的研究问题（自然语言）
**输出：** 结构化研究计划

**为什么用 GPT-5.4：** GPT-5.4 的 tool search 功能是独有优势——系统会注册多个工具（Semantic Scholar 搜索、arXiv 搜索、citation 查询等），GPT-5.4 可以动态加载所需工具定义而不是把所有工具塞进 prompt，这在多工具场景下可减少 47% 的 token 消耗。

**职责：**
- 将模糊的研究问题分解为明确的子问题
- 生成多组搜索关键词（英文 + 中文）
- 确定子领域范围
- 设定论文筛选标准（年份、venue、引用数阈值）
- 调用文献检索 API 获取初始论文列表
- 制定阅读优先级策略

**输出格式：**
```json
{
  "research_question": "用户的原始问题",
  "decomposed_questions": [
    "子问题 1：...",
    "子问题 2：..."
  ],
  "search_queries": [
    {"keywords": ["term1", "term2"], "source": "semantic_scholar"},
    {"keywords": ["term3", "term4"], "source": "arxiv"}
  ],
  "scope": {
    "year_range": [2021, 2026],
    "venues": ["NeurIPS", "ICML", "ACL", "Nature"],
    "min_citations": 5
  },
  "reading_priority": "先读 survey，再读高引方法论文，最后读最新工作"
}
```

---

### Agent 2：Paper Triage（论文初筛 Agent）

**模型：** Gemini 3.1 Pro
**输入：** 批量论文的 title + abstract（一次可传入 100+ 篇）
**输出：** 相关性评分 + 分类标签

**为什么用 Gemini：** 输入最便宜（$2.00/M），速度最快（120 t/s），且支持原生 PDF/图像理解。一次传入 100 篇 abstract（~30K tokens）只需约 $0.06。用 Batch API 再打五折。

**职责：**
- 快速阅读大量论文的 title 和 abstract
- 判断与研究问题的相关程度（0-1 分）
- 粗分类：survey / method / application / benchmark / theory
- 标记关键论文（必读）和边缘论文（可跳过）
- 对含有图表摘要的论文，利用多模态能力理解图表信息

**输出格式（每篇）：**
```json
{
  "paper_id": "arxiv:2401.xxxxx",
  "relevance_score": 0.85,
  "category": "method",
  "priority": "must_read",
  "brief_reason": "提出了基于 LLM 的假设生成框架，直接相关",
  "has_figures_of_interest": true
}
```

**批处理策略：** 每批 50-100 篇 abstract，使用 Gemini Batch API。全部 200 篇可在几分钟内完成。

---

### Agent 3：Deep Reader（精读 Agent）

**模型：** Claude Opus 4.6（高相关性论文，adaptive thinking: high）/ Claude Sonnet 4.6（中等相关性论文）
**输入：** 单篇论文全文（或多篇一起传入做对比）
**输出：** Paper Knowledge Object（结构化知识对象）

**为什么用 Claude：** 两个关键优势。第一，Claude 的 1M 上下文窗口无加价——你可以把 5 篇论文（每篇约 30-40K tokens）一次传入做交叉对比，总共 ~200K tokens，不会触发任何加价。同样操作在 GPT-5.4 上如果超过 272K 会触发 2x 加价。第二，Claude Opus 在文本深度理解和 reviewer 风格分析方面是公认最强的。

**职责：**
- 提取研究问题的精确表述
- 提取方法的核心思路（不是摘要复述，而是理解方法的本质）
- 提取所有显式和隐式假设
- 提取实验设置：数据集、指标、baseline
- 提取关键结果（带数值）
- 提取作者自述的局限性
- 提取未来工作方向
- 标注关键证据（页码 + 原文片段）

**输出格式：**
```json
{
  "paper_id": "doi:10.xxxx",
  "title": "...",
  "authors": ["..."],
  "year": 2025,
  "venue": "NeurIPS",

  "research_problem": {
    "statement": "精确的问题描述",
    "motivation": "为什么这个问题重要"
  },

  "method": {
    "core_idea": "方法的本质思路（一句话）",
    "description": "详细描述",
    "key_components": ["组件1", "组件2"],
    "novelty_claim": "作者声称的新颖性"
  },

  "assumptions": [
    {
      "assumption": "假设描述",
      "type": "explicit | implicit",
      "evidence": "来源段落",
      "page": 3
    }
  ],

  "experiments": {
    "datasets": ["数据集1", "数据集2"],
    "metrics": ["指标1", "指标2"],
    "baselines": ["baseline1", "baseline2"],
    "key_results": [
      {
        "claim": "方法 A 在指标 X 上超过 baseline Y 达到 Z%",
        "value": "具体数值",
        "table_or_figure": "Table 2"
      }
    ]
  },

  "limitations": [
    {
      "description": "局限性描述",
      "source": "author_stated | reader_identified",
      "severity": "minor | moderate | major"
    }
  ],

  "future_work": ["方向1", "方向2"],

  "key_evidence": [
    {
      "claim": "...",
      "quote": "原文片段",
      "page": 7,
      "section": "Section 4.2"
    }
  ]
}
```

**关键 Prompt 策略：** 不让模型"总结"论文，而是要求它以"审稿人"视角提取信息。Prompt 中显式要求区分"作者声称的"和"实际证据支持的"。

**多篇对比模式：** 利用 Claude 1M 无加价的优势，可以把同一子领域的 5 篇论文一次传入，让 Opus 同时做提取 + 横向对比。这比单篇提取后再汇总效果更好，且无额外成本。

---

### Agent 4：Critique Agent（批判分析 Agent）

**模型：** Claude Opus 4.6（adaptive thinking: high）
**输入：** Paper Knowledge Object + 论文原文（可选）
**输出：** 批判性分析报告

**职责：**
- 检查方法假设是否合理
- 识别实验设计的弱点
- 评估结论是否被证据充分支持
- 寻找潜在的可复现性问题
- 评估方法的泛化能力

**输出格式：**
```json
{
  "paper_id": "...",
  "critique": {
    "assumption_issues": [
      {
        "assumption": "LLM 具备领域知识",
        "problem": "未在专业领域（如材料科学）验证",
        "severity": "high"
      }
    ],
    "experimental_weaknesses": [
      {
        "issue": "缺少人工评估",
        "type": "missing_evaluation",
        "severity": "medium"
      }
    ],
    "evidence_gaps": [
      {
        "claim": "方法适用于所有科学领域",
        "problem": "仅在 biomedicine 上测试",
        "severity": "high"
      }
    ],
    "generalization_concerns": ["..."],
    "reproducibility_risks": ["..."]
  },
  "overall_confidence": 0.65
}
```

**为什么用 Claude Opus：** 批判性分析需要最强的推理深度。且可以复用 Deep Reader 阶段已缓存的论文内容（prompt caching），大幅降低重复输入成本。

---

### Agent 5：Gap Detector（研究空白检测 Agent）

**模型：** GPT-5.4（reasoning effort: high/xhigh）
**输入：** 所有 Paper Knowledge Objects + Critique 报告 + Knowledge Graph 查询结果
**输出：** 候选 Research Gaps（带置信度）

**为什么用 GPT-5.4：** Gap 检测需要大量工具调用（查询 Knowledge Graph、搜索 Semantic Scholar 验证、检索 Vector Index），GPT-5.4 的 tool search 和原生工具调用能力在这种多工具编排场景下最强。reasoning effort 设为 high 或 xhigh 来确保推理深度。

**四个并行检测机制：**

#### 机制 A：方法-问题矩阵（Method × Problem Matrix）

从 Knowledge Memory 中提取：
- 所有研究问题集合（P1, P2, ..., Pn）
- 所有方法集合（M1, M2, ..., Mm）

构建 n × m 矩阵，标记"已有论文"或"空白"。

**空白过滤规则：**
- 方法从未被用于某个问题 → 候选 gap
- 方法与问题的 embedding cosine < 0.3 → 排除（不合理组合）
- 问题有 3+ 种方法已尝试，但都有相同局限性 → 高价值 gap

#### 机制 B：假设链分析（Assumption Chain Analysis）

从所有论文的假设列表中：
1. 被 ≥3 篇论文共享但从未被单独验证的假设 → "unverified foundation"
2. 论文 A 假设 X 成立，论文 B 隐含 X 不成立 → "assumption conflict"
3. 论文声称的假设与实验条件不一致 → "assumption-reality gap"

#### 机制 C：引用图结构分析（Citation Graph Structural Analysis）

利用 Neo4j Knowledge Graph：
1. **社区孤岛：** 两个高内聚但低互引的子图 → 跨领域桥接机会
2. **断裂链：** A 提出方法 → B 指出局限 → 无 C 解决 → 断点即 gap
3. **过时高引节点：** 被高引但 ≥3 年无后续改进，局限性被多篇论文提及

#### 机制 D：评估盲点检测（Evaluation Blind Spot Detection）

统计领域内论文的评估方式：
1. **数据集偏差：** 所有论文都只在相同类型数据集上测试
2. **指标缺失：** 全部使用自动指标，无 human evaluation
3. **Baseline 过时：** 所有人都跟 2022 年的 baseline 比较

**每个候选 Gap 的输出格式：**
```json
{
  "gap_id": "GAP-001",
  "detection_mechanism": "method_problem_matrix",
  "description": "尚无研究将 symbolic reasoning 用于 hypothesis generation",
  "evidence": [
    {"paper_id": "...", "relevant_finding": "..."},
    {"paper_id": "...", "relevant_finding": "..."}
  ],
  "confidence": 0.78,
  "potential_impact": "high",
  "novelty_verified": false
}
```

---

### Agent 6：Verification Agent（验证 Agent）

**模型：** Claude Sonnet 4.6 + 外部搜索 API
**输入：** 候选 Research Gaps / Ideas
**输出：** 验证结果（verified_gap / active_area / emerging）

**职责：**
- 对每个候选 gap 生成搜索查询
- 搜索 Semantic Scholar / arXiv 查找近期相关论文
- 高度相关的已发表工作 → "active_area"
- 正在进行的预印本 → "emerging"
- 确认无人涉及 → "verified_gap"

**为什么用 Sonnet 4.6：** 验证任务需要多轮搜索和判断，但不需要 Opus 级别的深度推理。Sonnet 4.6 以 Opus 1/3 的价格提供接近 Opus 的分析质量，是最佳性价比选择。

---

### Agent 7：Idea Generator（研究思路生成 Agent）

**模型：** GPT-5.4（reasoning effort: medium）
**输入：** 已验证的 Research Gaps + 方法库 + 用户研究背景
**输出：** 研究 Idea 列表

**生成策略：**

1. **Gap 填充法：** 直接针对已验证的 gap 提出解决方案
2. **方法迁移法：** 将领域 A 的成功方法迁移到领域 B
3. **约束放松法：** 找到现有方法的核心限制假设，设计去除该假设的新方法
4. **组合创新法：** 合并两种方法的核心优势

**输出格式：**
```json
{
  "idea_id": "IDEA-001",
  "title": "一句话描述",
  "source_gap": "GAP-001",
  "generation_strategy": "method_transfer",
  "description": "详细描述（2-3 段）",
  "key_hypothesis": "核心假设",
  "expected_contribution": "预期贡献",
  "related_work": ["论文1", "论文2"],
  "novelty_score": 0.82,
  "feasibility_score": 0.65,
  "impact_score": 0.75
}
```

---

### Agent 8：Experiment Planner（实验设计 Agent）

**模型：** GPT-5.4（reasoning effort: medium）
**输入：** 研究 Idea + 方法库 + 已有数据集信息
**输出：** 详细实验方案

**输出格式：**
```json
{
  "idea_id": "IDEA-001",
  "experiment_plan": {
    "phase_1_proof_of_concept": {
      "objective": "验证核心假设",
      "dataset": "...",
      "method": "...",
      "success_criteria": "...",
      "estimated_compute": "...",
      "duration": "2 周"
    },
    "phase_2_full_evaluation": {
      "datasets": ["...", "..."],
      "baselines": ["最新方法1", "最新方法2", "经典方法"],
      "metrics": ["自动指标", "人工评估"],
      "ablation_studies": ["去掉组件 A", "去掉组件 B"],
      "duration": "4 周"
    },
    "risks": [
      {
        "risk": "数据集规模不足",
        "mitigation": "使用数据增强或合成数据",
        "probability": "medium"
      }
    ]
  }
}
```

---

## 五、知识存储层详细设计

### 5.1 Paper Store（PostgreSQL + JSONB）

```sql
CREATE TABLE papers (
    paper_id        TEXT PRIMARY KEY,       -- DOI 或 arXiv ID
    title           TEXT NOT NULL,
    authors         JSONB,
    year            INTEGER,
    venue           TEXT,
    abstract        TEXT,
    full_text       TEXT,                   -- 可选，存储全文用于缓存
    knowledge_obj   JSONB,                  -- Deep Reader 的完整输出
    critique        JSONB,                  -- Critique Agent 的输出
    triage_score    FLOAT,                  -- 初筛相关性分数
    status          TEXT,                   -- triage | extracted | deep_read | critiqued
    token_count     INTEGER,               -- 用于成本追踪
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP
);

CREATE TABLE research_sessions (
    session_id      UUID PRIMARY KEY,
    question        TEXT,
    plan            JSONB,
    gaps            JSONB,
    ideas           JSONB,
    cost_tracking   JSONB,                  -- 每步成本记录
    status          TEXT,
    created_at      TIMESTAMP
);
```

### 5.2 Vector Index（Qdrant）

三种 embedding 类型：

| embedding 类型 | 输入内容 | 用途 |
|---------------|---------|------|
| 论文级 | title + abstract + method summary | 查找语义相关的论文 |
| 方法级 | method.core_idea + method.description | 构建方法-问题矩阵 |
| 声明级 | 每条 key_evidence 的 claim | 查找支持/反驳特定声明的论文 |

**Embedding 模型：** OpenAI `text-embedding-3-large`（1536 维）
**检索策略：** 混合检索
```
最终排序 = 0.6 × 语义相似度 + 0.3 × BM25 关键词匹配 + 0.1 × 引用关系权重
```

### 5.3 Knowledge Graph（Neo4j）

**节点类型：** Paper, Method, Problem, Dataset, Assumption, Author

**关系类型：**
```
(Paper)-[:USES_METHOD]->(Method)
(Paper)-[:ADDRESSES]->(Problem)
(Paper)-[:EVALUATED_ON]->(Dataset)
(Paper)-[:ASSUMES]->(Assumption)
(Paper)-[:CITES]->(Paper)
(Paper)-[:EXTENDS]->(Paper)
(Paper)-[:CRITICIZES]->(Paper)
(Method)-[:REQUIRES_ASSUMPTION]->(Assumption)
(Author)-[:AUTHORED]->(Paper)
```

**关键查询示例：**
```cypher
// 方法-问题矩阵：某个问题上的方法覆盖情况
MATCH (p:Problem {name: $problem})<-[:ADDRESSES]-(paper)-[:USES_METHOD]->(m:Method)
RETURN m.name, COUNT(paper) AS paper_count

// 断裂链检测：A 提出方法，B 批评，无人解决
MATCH (a:Paper)-[:EXTENDS]->(base:Paper)
MATCH (b:Paper)-[:CRITICIZES]->(base)
WHERE NOT EXISTS {
    MATCH (c:Paper)-[:EXTENDS]->(base)
    WHERE c.year > b.year AND c <> a
}
RETURN base.title, b.title AS criticism

// 社区孤岛检测：找互引稀疏的子图
MATCH (p1:Paper)-[:CITES]->(p2:Paper)
WITH p1, p2, p1.subfield AS f1, p2.subfield AS f2
WHERE f1 <> f2
RETURN f1, f2, COUNT(*) AS cross_citations
ORDER BY cross_citations ASC
```

### 5.4 Session Memory（Redis）

```
session:{id}:plan        → 当前研究计划
session:{id}:queue       → 待处理论文队列
session:{id}:results     → Agent 中间结果
session:{id}:feedback    → 反馈循环的修正记录
session:{id}:cost        → 实时成本追踪
```

TTL：7 天。会话结束后可持久化到 PostgreSQL。

---

## 六、反馈回路设计

### 回路 1：搜索修正回路

```
Query Planner (GPT-5.4) → 搜索 → Paper Triage (Gemini) → Deep Reader (Claude)
                                                                  │
                                                                  ▼
                                                     发现新关键词 / 新子领域
                                                                  │
                                                                  ▼
                                                     回到 Query Planner
                                                     重新生成搜索策略
```

**触发条件：** Deep Reader 提取的关键概念中，有 >30% 不在原始搜索计划的关键词列表中。

### 回路 2：Gap 验证回路

```
Gap Detector (GPT-5.4) → 候选 Gaps → Verification Agent (Sonnet 4.6)
                                              │
                                              ▼
                                    发现已有人在做 / 预印本存在
                                              │
                                              ▼
                                    标记为 active_area
                                    反馈给 Gap Detector 调整参数
```

**触发条件：** 候选 gap 的 novelty check 失败。

### 回路 3：Idea 可行性回路

```
Idea Generator (GPT-5.4) → Ideas → Experiment Planner (GPT-5.4)
                                            │
                                            ▼
                                  发现实验不可行
                                  (缺数据/太昂贵/技术不成熟)
                                            │
                                            ▼
                                  反馈给 Idea Generator
                                  调整约束条件重新生成
```

**触发条件：** Experiment Planner 的可行性评分 < 0.4。

---

## 七、完整执行流程示例

**用户输入：** "液晶材料在光学相控阵中的最新研究进展和潜在突破方向"

| 步骤 | Agent | 模型 | 操作 | 输出 |
|------|-------|------|------|------|
| 1 | Query Planner | GPT-5.4 (medium) | 分解问题 → 生成搜索策略 → 调用 Semantic Scholar API | 4 个子问题 + 搜索计划 |
| 2 | Paper Triage | Gemini 3.1 Pro (batch) | 读取 120 篇 abstract → 评分 + 分类 | 18 篇必读 + 35 篇值得看 + 67 篇跳过 |
| 3a | Deep Reader | Opus 4.6 (high) | 精读 18 篇核心论文 → 结构化提取 | 18 个 Knowledge Objects |
| 3b | Deep Reader | Sonnet 4.6 | 提取 35 篇次要论文关键信息 | 35 个简化 Knowledge Objects |
| 4 | Critique | Opus 4.6 (high) | 批判分析 18 篇核心论文 | 18 份批判报告 |
| 5 | Gap Detector | GPT-5.4 (xhigh) | 运行 4 个检测机制 | 8 个候选 gaps |
| 6 | Verification | Sonnet 4.6 + Semantic Scholar | 验证每个 gap | 5 个 verified gaps, 2 个 active_area, 1 个 emerging |
| 7 | Idea Generator | GPT-5.4 (medium) | 针对 5 个 gaps 生成研究方向 | 5 个研究 Ideas |
| 8 | Experiment Planner | GPT-5.4 (medium) | 为每个 idea 设计实验 | 5 份实验方案 |
| → | *回路触发* | — | 1 个 idea 可行性 < 0.4 → 回到 step 7 重新生成 | 修正后的 idea |
| 9 | Report Writer | Opus 4.6 (high) | 生成最终研究报告 | 完整报告 |

**流程中的 Gap 检测发现示例：**
- 矩阵发现：蓝相液晶从未被用于大角度 OPA（> 60°）
- 假设链发现：多篇论文假设"液晶响应速度是 OPA 根本瓶颈"，但铁电液晶论文表明这可能不成立
- 引用图发现：超表面 OPA 和液晶 OPA 两个社区几乎不互引 → 融合机会
- 评估盲点：所有 LC-OPA 论文都在单一波长上测试，无人做宽光谱评估

---

## 八、技术栈选型

| 组件 | 技术选择 | 理由 |
|-----|---------|------|
| 后端框架 | Python + FastAPI | 异步支持好，AI 生态完善 |
| Agent 框架 | LangGraph / 自研 | 支持有状态图执行和反馈回路 |
| 任务队列 | Celery + Redis | 并行 Agent 调度 |
| LLM 统一调用 | LiteLLM | 统一接口调用三家 API，自动 fallback + 重试 |
| Paper Store | PostgreSQL + JSONB | 结构化查询 + 灵活 schema |
| Vector Store | Qdrant | 开源，支持混合检索 |
| Knowledge Graph | Neo4j | Cypher 查询直观，图算法库丰富 |
| Session Memory | Redis | 高速读写，TTL 管理 |
| Embedding | OpenAI text-embedding-3-large | 1536 维，质量最高 |
| PDF 解析 | PyMuPDF + Nougat | PyMuPDF 快速提取，Nougat 处理复杂公式/图表 |
| 论文检索 | Semantic Scholar API + OpenAlex | 免费，结构化好，有引用图 |
| 前端 | Next.js + React | 适合构建研究 Dashboard |
| 部署 | Docker Compose → Kubernetes | 先单机跑通，后续扩展 |
| 成本监控 | 自建 + Helicone | 追踪每个 Agent 的 token 消耗和成本 |

---

## 九、分阶段实施计划

### Phase 1：最小可用产品（2-3 周）

- 接入三家 API（通过 LiteLLM）
- 实现 Query Planner + Paper Triage + Deep Reader
- 仅用 PostgreSQL 存储
- 输出：针对一个研究问题的结构化文献综述
- 验证 Model Router 的路由逻辑和成本追踪

**验收标准：** 输入研究问题 → 输出 20 篇论文的结构化分析，成本 < $2

### Phase 2：深度分析（2-3 周）

- 增加 Critique Agent + Verification Agent
- 增加 Qdrant Vector Index（语义检索）
- 实现 Gap Detection 机制 A（方法-问题矩阵）和 D（评估盲点）
- 实现搜索修正回路（回路 1）

**验收标准：** 自动发现 ≥3 个 verified research gaps

### Phase 3：创意生成（2 周）

- 增加 Neo4j Knowledge Graph（实现机制 B 和 C）
- 增加 Idea Generator + Experiment Planner
- 实现全部 3 个反馈回路
- 增加 Report Writer

**验收标准：** 端到端运行，输出包含文献综述 + gaps + ideas + 实验方案的完整报告

### Phase 4：规模化与优化（持续）

- Prompt Caching 全面启用
- Batch API 集成（初筛和提取阶段）
- 构建 Web Dashboard
- Knowledge Memory 跨 session 累积
- 成本报表和自动优化

---

## 十、API Token 消耗与费用追踪机制

系统内置一个 **Cost Tracker**，实时记录每次 API 调用：

```json
{
  "call_id": "uuid",
  "session_id": "uuid",
  "agent": "deep_reader",
  "model": "claude-opus-4-6",
  "reasoning_effort": "high",
  "input_tokens": 45000,
  "output_tokens": 3200,
  "cached_tokens": 12000,
  "cost_usd": 0.097,
  "timestamp": "2026-03-16T10:30:00Z"
}
```

每次 session 结束后生成成本报告：

```
Session 成本摘要
────────────────
GPT-5.4:     $0.53  (规划 + Gap 检测 + Idea 生成)
Gemini 3.1:  $0.15  (初筛 200 篇)
Opus 4.6:    $3.12  (精读 + 批判 + 报告)
Sonnet 4.6:  $1.40  (提取 + 验证)
────────────────
总计:        $5.20
缓存节省:    $1.85
Batch 节省:  $0.43
```

---

## 十一、与原方案的关键差异

| 维度 | 原方案 | 本方案 |
|-----|-------|-------|
| 模型选择 | GPT-5.4 不存在（原文写的） | 基于 2026.3 实测数据，GPT-5.4 真实存在且有 1.05M 上下文 |
| 上下文假设 | 仅 Gemini 有长上下文 | 三家都有 ~1M，差异化在推理和价格 |
| 成本控制 | 仅声明"多模型降本" | reasoning effort 动态调节 + prompt caching + batch API + 详细成本表 |
| Claude 定位 | 仅用于精读 | 利用 1M 无加价优势做多篇对比分析，Sonnet 做主力执行层 |
| GPT-5.4 定位 | 不存在 | 编排层核心，利用 tool search 独有优势做多工具调度 |
| Gemini 定位 | 仅做初筛 | 增加多模态论文理解（图表、PDF） |
| 流程结构 | 线性 9 步 | 带 3 个反馈回路的有状态图 |
| Gap 检测 | 一笔带过 | 4 个具体机制 + Verification Agent |
| Memory | 仅 JSON schema | 四层存储（SQL + Vector + Graph + Session） |
| 成本追踪 | 无 | 内置 Cost Tracker + session 成本报告 |
| 实施路径 | 无 | 四阶段渐进式构建 |
