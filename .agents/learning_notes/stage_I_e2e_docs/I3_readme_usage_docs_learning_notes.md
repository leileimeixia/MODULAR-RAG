# I3_readme_usage_docs 学习笔记

## 1. 本阶段完成了什么

本阶段完成了 README 文档收口。

前面的阶段已经把 RAG 项目的主要能力都做出来了：摄取、检索、MCP Server、Dashboard、评估和 E2E 测试。I3 的重点不是继续加功能，而是把这些功能整理成一份新用户可以照着执行的说明书。

换句话说，这一阶段解决的是“项目怎么被别人跑起来、看懂、接入、测试”的问题。一个工程项目如果只有代码，没有清楚的 README，新用户很容易卡在环境、配置、命令、MCP 接入这些地方。I3 就是在做最后交付前的使用文档整理。

这一阶段在整个项目中的位置是“文档收口”。它属于端到端验收的一部分，因为项目不仅要能跑，还要能被别人复现。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `README.md` | 重写项目使用说明，覆盖快速开始、配置、MCP、Dashboard、评估、测试和 FAQ |
| `DEV_SPEC.md` | 更新 I3 任务进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步自动开发进度表 |

## 3. 核心调用关系

README 本身不是运行时代码，但它把项目的主要入口串起来了：

```text
README.md
  -> 创建 .venv
  -> 安装 requirements / dev 依赖
  -> 配置 OPENAI_API_KEY
  -> scripts/ingest.py 摄取文档
  -> scripts/query.py 查询知识库
  -> scripts/start_dashboard.py 启动 Dashboard
  -> scripts/evaluate.py 运行评估
  -> pytest -q 运行测试
  -> MCP 配置接入 Copilot / Claude Desktop
```

文档中的使用链路可以理解成：

```text
新用户
  -> 阅读 README
  -> 配好环境
  -> 摄取文档
  -> 查询结果
  -> 打开 Dashboard
  -> 运行评估
  -> 配置 MCP Client
```

## 4. 每个核心文件的作用

### 文件：`README.md`

* 主要职责：作为项目入口文档。
* 新增或整理的核心内容：
  * 项目功能概览。
  * 快速开始流程。
  * 虚拟环境创建和依赖安装。
  * OpenAI API Key 配置方式。
  * `config/settings.yaml` 字段说明。
  * 摄取、查询、Dashboard、评估命令。
  * GitHub Copilot / VS Code `mcp.json` 示例。
  * Claude Desktop `claude_desktop_config.json` 示例。
  * 测试命令。
  * 常见问题。
  * 开发流程建议。
* 输入是什么：用户阅读文档并执行命令。
* 输出是什么：用户可以把项目跑起来，并知道如何排查常见问题。
* 在项目中的作用：降低项目使用门槛，让功能可复现、可交付。

### 文件：`config/settings.yaml`

* README 里重点解释了它。
* 主要职责：保存 LLM、Embedding、VectorStore、Retrieval、Rerank、Evaluation、Observability 等配置。
* 在项目中的作用：让用户通过配置切换 provider 和运行参数，而不是直接改代码。

### 文件：`scripts/start_dashboard.py`

* README 里给出了启动方式。
* 主要职责：封装 `streamlit run src/observability/dashboard/app.py`。
* 在项目中的作用：让用户用统一命令启动 Dashboard。

### 文件：`scripts/ingest.py`

* README 里给出了摄取示例命令。
* 主要职责：把本地文档送入 ingestion pipeline。
* 在项目中的作用：构建本地知识库。

### 文件：`scripts/query.py`

* README 里给出了查询示例命令。
* 主要职责：运行本地查询链路，支持 verbose trace。
* 在项目中的作用：让用户验证检索结果和 trace。

### 文件：`scripts/evaluate.py`

* README 里给出了评估命令。
* 主要职责：运行 golden test set 评估。
* 在项目中的作用：量化检索和回答质量。

## 5. 新手重点理解

I3 的重点是“让项目能被别人复现”。

很多项目代码本身写完了，但别人不知道怎么启动、怎么配置 key、怎么摄取文档、怎么接 MCP、怎么跑测试，这样项目就很难真正交付。README 就是把这些入口集中到一起。

为什么 README 要写 MCP 配置？因为这个项目的一个核心价值是作为 MCP Server 被 Copilot、Claude Desktop 等工具调用。只有给出明确配置示例，用户才知道怎么把 server 接入真实客户端。

为什么 README 要写 Dashboard 使用？因为 Dashboard 是项目的可视化入口。它能展示数据、摄取、trace 和评估，适合演示，也适合排查问题。

为什么 README 要写测试命令？因为这是工程项目的可复现保证。用户改了代码以后，可以通过 `pytest -q` 快速知道有没有破坏已有能力。

这一阶段相当于给项目补上“说明书”和“交付入口”：代码能跑只是第一步，别人能照着文档跑起来，才算真正接近可交付。
