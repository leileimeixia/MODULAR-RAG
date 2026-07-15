# E3_query_knowledge_hub 学习笔记

## 1. 本阶段完成了什么

本阶段完成的是 MCP Server 里最核心的查询工具：`query_knowledge_hub`。

前面阶段已经完成了：

```text
阶段 D：HybridSearch + CoreReranker 查询主链路
E1：MCP stdio server 入口
E2：ProtocolHandler 处理 initialize、tools/list、tools/call
```

E3 做的事情是把阶段 D 的查询能力挂到 MCP Tool 上。也就是说，MCP Client 以后可以通过 `tools/call` 调用 `query_knowledge_hub`，传入 query、top_k、collection，然后得到带引用的检索结果。

本阶段还新增了响应构建层：

```text
CitationGenerator：从 RetrievalResult 生成结构化引用
ResponseBuilder：把检索结果包装成 MCP tool result
```

最终 tool 返回两部分内容：

```text
content[0]：人类可读的 Markdown 文本
structuredContent.citations：机器可解析的结构化引用列表
```

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/mcp_server/tools/query_knowledge_hub.py` | 实现 MCP 查询工具入口 |
| `src/mcp_server/tools/__init__.py` | 注册默认 tools，让 server 能暴露 `query_knowledge_hub` |
| `src/mcp_server/server.py` | 启动时把默认 tools 注册给 `ProtocolHandler` |
| `src/core/response/citation_generator.py` | 从检索结果生成结构化 citations |
| `src/core/response/response_builder.py` | 构建 MCP tool result，包括 Markdown 和 structuredContent |
| `src/core/response/__init__.py` | 导出 response 相关类 |
| `tests/unit/test_response_builder.py` | 测试 Markdown 与 citations 构建 |
| `tests/unit/test_query_knowledge_hub_tool.py` | 测试 tool 参数校验、调用链和响应结构 |
| `tests/integration/test_mcp_server.py` | 补充 `tools/list` 能看到 `query_knowledge_hub` 的集成测试 |
| `DEV_SPEC.md` | 标记 E3 完成并更新进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 E3 进度表 |

## 3. 核心调用关系

```text
MCP Client
  -> tools/call: query_knowledge_hub
  -> ProtocolHandler.handle_tools_call()
  -> query_knowledge_hub(arguments)
  -> HybridSearch.search(query, top_k, filters)
  -> CoreReranker.rerank(query, candidates, top_k)
  -> ResponseBuilder.build(results, query)
  -> CitationGenerator.generate(results)
  -> 返回 MCP tool result
```

其中 `collection` 参数会被转换成 metadata filter：

```python
{"collection": collection}
```

然后传给 `HybridSearch.search()`。

## 4. 每个核心文件的作用

### 文件：`src/mcp_server/tools/query_knowledge_hub.py`

* 主要职责：作为 MCP tool 入口，连接 MCP 协议层和 Core 查询链路。
* 关键函数：`query_knowledge_hub()`、`tool_spec()`。
* 输入是什么：tool arguments，例如 `query`、`top_k`、`collection`。
* 输出是什么：MCP tool result 字典。
* 在项目中的作用：把本地 RAG 检索能力暴露给 MCP Client。

`QUERY_KNOWLEDGE_HUB_SCHEMA` 定义了工具输入：

```python
{
    "query": "string",
    "top_k": "integer",
    "collection": "string",
}
```

`tool_spec()` 会把 schema 和 handler 包装成 `ToolSpec`：

```python
ToolSpec(
    name="query_knowledge_hub",
    description="Search the local RAG knowledge hub and return cited chunks.",
    input_schema=QUERY_KNOWLEDGE_HUB_SCHEMA,
    handler=query_knowledge_hub,
)
```

这样 `ProtocolHandler.tools/list` 就能把这个工具暴露给 MCP Client。

`query_knowledge_hub()` 的主流程是：

```python
query = _query(arguments)
top_k = _top_k(arguments)
filters = _filters(arguments)
candidates = hybrid_search.search(query, top_k=top_k, filters=filters)
results = reranker.rerank(query, candidates, top_k=top_k)
return response_builder.build(results, query)
```

这里支持依赖注入：测试时可以传 fake `hybrid_search`、fake `reranker`、fake `response_builder`，不用真的加载模型、向量库或 BM25。

### 文件：`src/core/response/citation_generator.py`

* 主要职责：把 `RetrievalResult` 转成结构化 citation。
* 关键类：`CitationGenerator`。
* 输入是什么：`List[RetrievalResult]`。
* 输出是什么：citation 字典列表。
* 在项目中的作用：给 MCP 响应提供可解析的引用信息。

每条 citation 包含：

```python
{
    "index": 1,
    "source": "...",
    "page": ...,
    "chunk_id": "...",
    "score": ...
}
```

这些字段来自 `RetrievalResult.metadata` 和检索分数。

### 文件：`src/core/response/response_builder.py`

* 主要职责：构建 MCP tool result。
* 关键类：`ResponseBuilder`。
* 输入是什么：检索结果和原始 query。
* 输出是什么：包含 `content` 和 `structuredContent` 的 MCP 响应。
* 在项目中的作用：统一 MCP 工具返回格式。

返回结构大致是：

```python
{
    "content": [{"type": "text", "text": markdown}],
    "structuredContent": {
        "query": query,
        "citations": citations,
    },
    "isError": False,
}
```

`content[0]` 是给人看的 Markdown，里面有 `[1]`、`[2]` 这样的引用标号。

`structuredContent.citations` 是给程序解析的结构化引用，方便高级 MCP Client 做引用展示。

没有检索结果时，`ResponseBuilder` 不返回空白，而是返回友好提示，告诉用户可能需要先摄取数据或换关键词。

### 文件：`src/mcp_server/tools/__init__.py`

* 主要职责：集中注册默认 MCP tools。
* 关键函数：`default_tools()`。
* 在项目中的作用：server 启动时通过这里拿到默认工具列表。

当前默认工具只有：

```text
query_knowledge_hub
```

后续 E4、E5 会继续增加 `list_collections`、`get_document_summary`。

### 文件：`src/mcp_server/server.py`

* 主要职责：运行 stdio server。
* 本阶段变化：创建 `ProtocolHandler` 时注册默认 tools。

```python
handler = ProtocolHandler(tools=default_tools())
```

这样 server 收到 `tools/list` 请求时，就能返回 `query_knowledge_hub` 的 schema。

### 测试文件

`tests/unit/test_response_builder.py` 验证：

```text
CitationGenerator 能提取 source/page/chunk_id/score
ResponseBuilder 能生成 Markdown 和 structuredContent
无结果时返回友好提示
```

`tests/unit/test_query_knowledge_hub_tool.py` 验证：

```text
tool schema 正确
tool 会调用 HybridSearch 和 CoreReranker
collection 会转成 metadata filter
返回内容包含 citations
非法参数会抛 ValueError
```

`tests/integration/test_mcp_server.py` 验证：

```text
server 的 tools/list 能暴露 query_knowledge_hub
```

## 5. 新手重点理解

这一阶段最重要的是理解 MCP Tool 和 Core 查询链路的关系。

Core 层负责真正的检索：

```text
HybridSearch
CoreReranker
RetrievalResult
```

MCP Tool 层负责把这些能力包装成 MCP Client 能调用、能展示的格式：

```text
Tool schema
Tool arguments
MCP content
structuredContent.citations
```

这两层不要混在一起。这样以后不管是 CLI、Dashboard，还是 MCP Client，都可以复用 Core 查询链路，只是入口和输出格式不同。

另一个重点是为什么同时返回 Markdown 和 structuredContent。

Markdown 是给人看的：

```text
### [1] chunk-a
文本片段...
引用：[1] source=...
```

structuredContent 是给程序看的：

```json
{
  "citations": [
    {"source": "...", "chunk_id": "...", "score": 0.9}
  ]
}
```

这让不同能力的 MCP Client 都能使用返回结果。简单 Client 可以直接展示 Markdown，高级 Client 可以解析 citations 做更细的引用展示。

本阶段在整体项目中的位置是：

```text
MCP Client
  -> tools/call query_knowledge_hub
  -> ProtocolHandler
  -> query_knowledge_hub tool
  -> HybridSearch + CoreReranker
  -> ResponseBuilder + CitationGenerator
  -> MCP tool result
```

完成 E3 后，MCP Server 已经能对外暴露主查询工具的 schema，并具备把检索结果包装成带引用响应的能力。





# 整体结构与流程

以下是对 response_builder.py 代码文件的完整解析：

1. 文件定位
项目作用：在 RAG（检索增强生成）系统中，该文件负责将底层检索到的文档片段（Chunks）转化为大模型或客户端（如 MCP 工具）易于理解和展示的格式化响应。
所处层级：处于系统的“响应构建层”（Response Layer），位于检索模块（Retrieval）之后，直接面向调用方（如 MCP Server、AI 助手前端 UI）。
核心职责：将结构化的检索结果（RetrievalResult）转换为包含 Markdown 文本和结构化引用（Citations）的 MCP 标准响应字典，方便前端渲染和模型参考。
2. 函数拆解
ResponseBuilder.__init__
作用目的：初始化响应构建器实例。
输入输出：输入可选的 citation_generator（引用生成器）；无直接输出（初始化实例属性）。
核心功能：检查是否传入了自定义的引用生成器，如果没有，则默认实例化一个 CitationGenerator，确保后续流程有组件可用。
ResponseBuilder.build
作用目的：构建最终的 MCP 兼容工具响应。
输入输出：输入 retrieval_results（检索结果列表）和 query（用户原始查询）；输出 MCPToolResult（一个包含 content、structuredContent 和 isError 的字典）。
核心功能：作为核心调度方法，先调用引用生成器生成引用列表，再调用内部函数生成 Markdown 文本，最后将它们组装成标准的 MCP 响应格式返回。
_build_markdown
作用目的：将检索结果和引用信息渲染为人类可读的 Markdown 格式字符串。
输入输出：输入 query、retrieval_results 和 citations；输出格式化后的 str（Markdown 文本）。
核心功能：
空结果处理：如果没有检索到内容，返回友好的提示语，引导用户检查数据摄取或更换关键词。
有结果处理：遍历检索结果和引用信息，提取 chunk_id、文本预览、来源、页码和相似度分数，拼接成带有标题和引用说明的 Markdown 文本。
_preview
作用目的：对长文本进行清洗和截断，生成用于展示的预览文本。
输入输出：输入 text（原始文本）和 limit（最大长度限制，默认 800）；输出处理后的 str。
核心功能：首先使用 " ".join(text.split()) 将文本中的换行、多余空格等空白字符合并规范化。如果文本长度超过限制，则截断并在末尾加上 ...，防止展示内容过长。
3. 执行流程
触发构建：调用方传入检索结果和用户查询，触发 ResponseBuilder.build() 方法。
生成引用：build() 方法首先调用 self.citation_generator.generate()，将检索结果转化为带有索引、来源、页码等信息的引用列表（citations）。
渲染文本：接着，build() 调用私有函数 _build_markdown()，将查询词、检索结果和引用列表传入。
文本截断：在 _build_markdown() 内部遍历每条结果时，会调用 _preview() 获取长度合规的文本预览。
组装 Markdown：_build_markdown() 将标题、预览文本和引用信息拼接成完整的 Markdown 字符串，并返回给 build()。
封装响应：build() 将 Markdown 字符串放入 content 字段，将查询词和引用列表放入 structuredContent 字段，封装成 MCP 标准字典并返回给调用方。
4. 场景示例
假设用户在一个企业知识库中查询：“公司的差旅报销标准是什么？”

输入阶段：

query: "公司的差旅报销标准是什么？"
retrieval_results: 向量数据库检索到了 1 条高度相关的文档片段，chunk_id 为 "doc_001_chunk_3"，内容是关于高铁二等座和住宿标准的详细说明，相似度得分为 0.89。
执行阶段：

build() 被调用。
CitationGenerator 为该片段生成引用信息：[{"index": 1, "source": "财务管理制度.pdf", "page": 12}]。
_build_markdown() 开始组装文本：
生成总览行：“找到 1 条与 公司的差旅报销标准是什么？ 相关的结果：”
调用 _preview() 处理长文本，确保不超过 800 字。
拼接具体内容块：
markdown
### [1] doc_001_chunk_3
员工出差乘坐高铁...（此处为预览文本）...

引用：[1] source=财务管理制度.pdf, page=12, score=0.890000
最终 build() 返回包含上述 Markdown 文本和结构化引用信息的字典。
结果展示： MCP 客户端（如 AI 助手界面）接收到该字典后，可以直接将 Markdown 渲染给用户阅读，同时利用 structuredContent 中的引用信息，在界面上生成可点击的“参考来源：财务管理制度.pdf 第12页”的链接，实现溯源。




1. 文件定位
文件路径：src/mcp_server/tools/query_knowledge_hub.py 项目作用：该文件是 RAG（检索增强生成）系统中 MCP（Model Context Protocol）服务端的一个核心工具模块。 所处层级：处于系统的 MCP 工具层（Tools Layer），它是连接外部调用方（如大模型、客户端）与底层 RAG 核心引擎（检索、重排、响应构建）的桥梁。 核心职责：将底层的“混合检索 + 重排序 + 结果组装”能力封装成一个标准的 MCP 工具。它负责接收外部传入的自然语言查询请求，校验参数，调度底层组件完成知识库检索，并最终返回带有引用来源的结构化回答。

2. 函数拆解
query_knowledge_hub(arguments, settings, hybrid_search, reranker, response_builder)
作用目的：MCP 工具的主入口处理函数，负责串联整个检索与回答生成的流程。
输入输出：
输入：arguments（包含查询词、返回数量、集合过滤等参数的字典），以及可选的依赖组件（用于依赖注入，方便测试）。
输出：一个字典（dict），即最终构建好的包含引用信息的响应结果。
核心功能：解析并校验输入参数，初始化或获取必要的底层组件，依次执行混合检索、重排序，最后调用响应构建器生成最终结果。
tool_spec()
作用目的：提供该 MCP 工具的注册元数据。
输入输出：无输入；输出一个 ToolSpec 对象。
核心功能：定义工具的名称（query_knowledge_hub）、功能描述、输入参数的 JSON Schema（即 QUERY_KNOWLEDGE_HUB_SCHEMA）以及绑定的处理函数，供 MCP Server 启动时注册使用。
_query(arguments)
作用目的：提取并严格校验查询词（query）。
输入输出：输入 arguments 字典；输出去除首尾空格的有效查询字符串。
核心功能：确保传入的参数是字典，且 query 字段是非空字符串，防止无效查询导致底层组件报错。
_top_k(arguments)
作用目的：提取并校验期望返回的最大结果数（top_k）。
输入输出：输入 arguments 字典；输出一个正整数（默认值为 5）。
核心功能：校验 top_k 必须是大于 0 的整数，保证检索和重排阶段的数量参数合法。
_filters(arguments)
作用目的：提取元数据过滤条件（如指定在哪个知识库/集合中搜索）。
输入输出：输入 arguments 字典；输出一个过滤条件字典（如 {"collection": "xxx"}）或空字典。
核心功能：如果调用方指定了 collection 参数，则校验其格式并封装成底层检索器能识别的过滤字典；若未指定则返回空字典，表示全局搜索。
3. 执行流程
整个工具的运行链路是一个典型的 “参数解析 -> 依赖准备 -> 检索 -> 重排 -> 组装” 的流水线：

参数解析与校验：主函数 query_knowledge_hub 被调用后，首先分别调用 _query、_top_k、_filters 三个辅助函数，从 arguments 中提取并校验出 query（查询词）、top_k（返回数量）和 filters（过滤条件）。
依赖组件准备：通过 or 逻辑初始化 settings（配置）、hybrid_search（混合检索器）、reranker（重排器）和 response_builder（响应构建器）。如果外部没有通过参数注入，则使用默认实例。
混合检索（Hybrid Search）：调用 hybrid_search.search()，传入查询词、数量和过滤条件，从向量/全文索引中召回最相关的候选文档片段（candidates）。
语义重排序（Rerank）：调用 reranker.rerank()，将召回的候选片段再次根据与查询词的语义相关性进行精细排序，截取最终的 top_k 个结果（results）。
响应构建（Build）：调用 response_builder.build()，将排序后的结果和原始查询词传入，组装成带有引用标记（Citations）的最终回答格式并返回给调用方。
4. 场景示例
业务场景：公司的智能助手需要回答员工关于“出差住宿标准”的提问。

全流程串联：

发起请求：大模型或前端向 MCP 工具发送请求，参数为：
json
{
  "query": "出差住宿标准是多少？",
  "top_k": 3,
  "collection": "company_hr_policy"
}
参数校验：
_query 提取出 "出差住宿标准是多少？"。
_top_k 确认返回数量为 3。
_filters 识别到集合参数，构建出过滤条件 {"collection": "company_hr_policy"}，确保只在 HR 政策知识库中搜索。
混合检索：hybrid_search 在 company_hr_policy 知识库中，通过向量相似度+关键词匹配，初步召回了 5 个相关片段（如“交通标准”、“住宿限额”、“餐饮补贴”等）。
重排序：reranker 根据“出差住宿标准”这个核心语义，对这 5 个片段进行重新打分排序，把最相关的“住宿限额”相关片段排到前 3 位，剔除不相关的“交通标准”。
构建回答：response_builder 拿到这 3 个最精准的片段，将其拼装成一段通顺的 Markdown 回答，并在句末加上引用来源（如 [1] 2023年员工差旅手册.pdf），最终返回给大模型展示给员工。