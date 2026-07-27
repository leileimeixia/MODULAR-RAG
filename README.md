# Modular RAG MCP Server

一个模块化、可插拔、可观测的本地 RAG 项目。它把文档摄取、混合检索、重排、MCP 工具调用、Dashboard 管理和评估回归串成一条完整链路，适合用来学习 RAG 工程化，也适合作为二次开发的干净起点。

## 功能概览

| 模块 | 作用 |
| --- | --- |
| Ingestion Pipeline | 读取文档，切块，增强 metadata，生成向量，写入本地索引 |
| Retrieval | Dense + Sparse + RRF Fusion，支持可选 rerank |
| MCP Server | 通过 stdio JSON-RPC 暴露 `query_knowledge_hub` 等工具 |
| Dashboard | Streamlit 可视化管理页面，覆盖数据、摄取、trace、评估 |
| Evaluation | Custom/Ragas evaluator、golden test set、recall 回归 |
| Observability | 查询链路和摄取链路 trace，便于定位问题 |

## 快速开始

### 1. 克隆并进入项目

```powershell
git clone <repo-url>
cd MODULAR-RAG-CLEAN-START
```

### 2. 创建虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 禁止激活脚本，可以先执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 3. 安装依赖

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev]"
```

### 4. 配置 API Key

项目默认从环境变量读取 OpenAI Key：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "你的 key", "User")
```

设置后请重启终端或 IDE，让新环境变量生效。

### 5. 检查配置

默认配置文件在：

```text
config/settings.yaml
```

最小可用配置已经提供。默认使用：

```yaml
llm:
  provider: openai
  model: gpt-5.5
  api_key: ${OPENAI_API_KEY}

embedding:
  provider: openai
  model: text-embedding-ada-002
  dimensions: 1536
  api_key: ${OPENAI_API_KEY}
```

### 6. 摄取示例文档

```powershell
python scripts/ingest.py --path tests/fixtures/sample_documents --collection test --force
```

成功后会看到类似输出：

```text
INGESTED document=... chunks=... records=... images=...
Summary: ingested=... skipped=... total=...
```

### 7. 查询知识库

```powershell
python scripts/query.py --query "How do I configure Azure OpenAI?" --top-k 5 --verbose
```

如果只想看检索融合结果，不跑 rerank：

```powershell
python scripts/query.py --query "How do I configure Azure OpenAI?" --no-rerank
```

### 8. 启动 Dashboard

```powershell
python scripts/start_dashboard.py
```

也可以直接运行：

```powershell
python -m streamlit run src/observability/dashboard/app.py
```

Dashboard 包含 6 个页面：

| 页面 | 作用 |
| --- | --- |
| System Overview | 查看组件配置和本地数据状态 |
| Data Browser | 浏览文档、chunk、metadata、图片引用 |
| Ingestion Manager | 上传文档、启动摄取、删除文档 |
| Ingestion Traces | 查看摄取链路每一步耗时和详情 |
| Query Traces | 查看查询链路、Dense/Sparse/Fusion/Rerank 过程 |
| Evaluation Panel | 运行 golden test set，查看评估指标和 case 明细 |

### 9. 运行评估

```powershell
python scripts/evaluate.py --test-set tests/fixtures/golden_test_set.json
```

输出是 JSON 格式的评估报告，包含总体 metrics 和每条 case 的明细。

## 配置说明

`config/settings.yaml` 主要字段如下：

| 字段 | 说明 |
| --- | --- |
| `llm.provider` | LLM 提供商，例如 `openai`、`azure`、`deepseek`、`ollama` |
| `llm.model` | 生成模型名称 |
| `embedding.provider` | Embedding 提供商 |
| `embedding.model` | Embedding 模型名称 |
| `vision_llm.enabled` | 是否启用图片描述能力 |
| `vector_store.provider` | 向量库后端，默认 `chroma` |
| `vector_store.persist_directory` | 向量库本地持久化目录 |
| `retrieval.*_top_k` | Dense、Sparse、Fusion 各阶段召回数量 |
| `splitter.chunk_size` | 文档切块大小 |
| `splitter.chunk_overlap` | chunk 重叠长度 |
| `rerank.enabled` | 是否启用 rerank |
| `evaluation.provider` | 评估器，默认 `custom` |
| `evaluation.backends` | 可选，组合评估器后端列表，例如 `[ragas, custom]` |
| `observability.trace_file` | trace JSONL 文件路径 |

组合评估示例：

```yaml
evaluation:
  enabled: true
  provider: composite
  backends:
    - custom
    - ragas
```

`ragas` 是可选依赖。如果没有安装，只有真正运行 `RagasEvaluator` 时才会提示安装。

## MCP 配置示例

本项目通过 stdio 暴露 MCP Server。入口是：

```powershell
python src/mcp_server/server.py
```

### GitHub Copilot / VS Code `mcp.json`

把路径替换成你本机项目路径：

```json
{
  "servers": {
    "modular-rag": {
      "type": "stdio",
      "command": "D:\\RAG\\MODULAR-RAG-CLEAN-START\\.venv\\Scripts\\python.exe",
      "args": [
        "D:\\RAG\\MODULAR-RAG-CLEAN-START\\src\\mcp_server\\server.py"
      ],
      "env": {
        "OPENAI_API_KEY": "你的 key"
      }
    }
  }
}
```

### Claude Desktop `claude_desktop_config.json`

```json
{
  "mcpServers": {
    "modular-rag": {
      "command": "D:\\RAG\\MODULAR-RAG-CLEAN-START\\.venv\\Scripts\\python.exe",
      "args": [
        "D:\\RAG\\MODULAR-RAG-CLEAN-START\\src\\mcp_server\\server.py"
      ],
      "env": {
        "OPENAI_API_KEY": "你的 key"
      }
    }
  }
}
```

当前 MCP tools：

| Tool | 说明 |
| --- | --- |
| `query_knowledge_hub` | 查询本地 RAG 知识库并返回引用 |
| `list_collections` | 查看本地文档 collection |
| `get_document_summary` | 根据文档 id 或 chunk 前缀查看摘要 |

## 测试

运行全部测试：

```powershell
pytest -q
```

按层运行：

```powershell
pytest -q tests/unit
pytest -q tests/integration
pytest -q tests/e2e
```

常用目标测试：

```powershell
pytest -q tests/e2e/test_mcp_client.py
pytest -q tests/e2e/test_recall.py
pytest -q tests/e2e/test_dashboard_smoke.py
```

说明：`test_dashboard_smoke.py` 依赖 Streamlit 的 `AppTest`。如果当前环境没有安装 Streamlit，测试会明确 skip。

## 目录结构

```text
src/
  core/                    # 核心类型、配置、查询链路、响应构造、trace
  ingestion/               # 摄取 pipeline、chunking、transform、embedding、storage
  libs/                    # LLM、Embedding、Loader、Splitter、VectorStore、Reranker、Evaluator 抽象层
  mcp_server/              # MCP stdio server、协议处理器、tools
  observability/           # Dashboard、evaluation、logger
scripts/
  ingest.py                # 离线摄取入口
  query.py                 # 查询入口
  evaluate.py              # 评估入口
  start_dashboard.py       # Dashboard 启动入口
tests/
  unit/
  integration/
  e2e/
  fixtures/
```

## 常见问题

### 1. API Key 设置后仍然读取不到

确认设置的是用户环境变量，并重启终端：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "你的 key", "User")
```

然后检查：

```powershell
echo $env:OPENAI_API_KEY
```

### 2. PowerShell 无法激活 `.venv`

执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后重新运行：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Dashboard 测试被 skip

说明当前环境没有安装 Streamlit。安装依赖即可：

```powershell
pip install streamlit
```

### 4. `ragas` 报缺失

`ragas` 是可选依赖。只有使用 `RagasEvaluator` 时才需要安装：

```powershell
pip install ragas
```

### 5. 摄取后查询不到结果

先确认摄取命令成功，再检查：

```powershell
python scripts/ingest.py --path tests/fixtures/sample_documents --collection test --force
python scripts/query.py --query "sample" --verbose
```

如果仍然没有结果，打开 Dashboard 的 Ingestion Traces 和 Query Traces 页面查看每一步细节。

## 开发流程建议

本项目按 `DEV_SPEC.md` 拆分阶段开发。建议每完成一个阶段后运行：

```powershell
pytest -q
```

如果你正在使用项目内的 `.agents/skills` 工作流，可以按阶段执行：

```text
setup
next
code-review-learning
commit
```

这套流程会帮助你保持“实现、测试、笔记、提交”四件事同步。
