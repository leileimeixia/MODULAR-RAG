# E5_get_document_summary 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 MCP Server 的 `get_document_summary` 工具。

这个工具的作用是：外部 MCP 客户端传入一个 `doc_id`，系统去已经持久化的 BM25 索引里查找这个文档对应的 chunk records，然后从这些 records 的 metadata 里聚合出文档标题、摘要、标签、来源路径、所属集合和 chunk 数量。

在整个 RAG 项目里，它属于“对外服务工具层”。前面的 ingestion 阶段会把文档切成 chunk，并在 metadata 中写入 `title`、`summary`、`tags` 等信息；E5 则把这些已存储的信息重新整理成一个面向用户或 MCP 客户端的文档摘要接口。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/mcp_server/tools/get_document_summary.py` | 实现 `get_document_summary` MCP tool，根据 `doc_id` 从 BM25 持久化 records 中聚合文档摘要 |
| `src/mcp_server/tools/__init__.py` | 将 `get_document_summary` 注册到默认 MCP tools 列表 |
| `tests/unit/test_get_document_summary.py` | 覆盖文档摘要查询、缺失文档、缺失索引、参数校验和 tool schema |
| `tests/integration/test_mcp_server.py` | 确认 MCP server 的 `tools/list` 会暴露 `get_document_summary` |
| `DEV_SPEC.md` | 更新 E5 任务状态和总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 的任务进度记录 |

## 3. 核心调用关系

```text
MCP 客户端
  -> tools/call: get_document_summary({ "doc_id": "..." })
  -> ProtocolHandler 找到 get_document_summary 的 ToolSpec
  -> 执行 get_document_summary(arguments)
  -> BM25Indexer(index_dir).load()
  -> 遍历 indexer.records
  -> 根据 doc_id / document_id / file_hash / chunk id 前缀匹配记录
  -> 聚合 title、summary、tags、source_path、collection、chunk_count
  -> 返回 content + structuredContent
```

这里的数据来源不是重新读取原始文件，而是复用 ingestion 阶段已经写入 BM25 索引的 chunk records。这样做的好处是简单、稳定，并且和当前项目已有的存储能力一致。

## 4. 每个核心文件的作用

### 文件：`src/mcp_server/tools/get_document_summary.py`

* 主要职责：实现按 `doc_id` 查询文档摘要的 MCP 工具。
* 关键函数：
  * `get_document_summary()`：工具入口，读取参数、加载 BM25 索引、查找 records、返回结果。
  * `tool_spec()`：把该函数包装成 MCP 可识别的 `ToolSpec`。
  * `_doc_id()`：校验输入参数，确保 `doc_id` 是非空字符串。
  * `_matches_document()`：判断某个 chunk record 是否属于目标文档。
  * `_build_summary()`：把多个 chunk records 聚合成一个文档级摘要。
  * `_collect_tags()`：从多个 chunk 的 metadata 中合并标签并去重。
  * `_error_result()`：把缺失索引、找不到文档等情况转换成规范 MCP tool error。
* 输入是什么：`{"doc_id": "..."}`。
* 输出是什么：MCP tool result，包含给人看的 `content` 和给程序用的 `structuredContent`。
* 在项目中的作用：为外部客户端提供“查看某篇文档摘要”的能力。

### 文件：`src/mcp_server/tools/__init__.py`

* 主要职责：管理 MCP tools 的统一注册。
* 本阶段修改点：新增导入 `get_document_summary` 和 `get_document_summary_spec`，并在 `default_tools()` 中加入 `get_document_summary_spec()`。
* 输入是什么：无。
* 输出是什么：MCP server 默认暴露的 `ToolSpec` 列表。
* 在项目中的作用：让协议层可以通过 `tools/list` 暴露该工具，也可以通过 `tools/call` 调用该工具。

### 文件：`tests/unit/test_get_document_summary.py`

* 主要职责：验证 `get_document_summary` 的核心行为。
* 关键测试：
  * 能从 BM25 records 中读取 `title`、`summary`、`tags`。
  * 能按 `document_id` 匹配文档。
  * 能按 `file_hash` 匹配文档。
  * metadata 没有标题或摘要时，能用 `source_path` 和 chunk 文本兜底。
  * 找不到文档时返回 `isError=True` 的工具错误。
  * BM25 索引不存在时返回 `document_index_unavailable`。
  * 输入参数为空时抛出参数错误。
* 在项目中的作用：保证这个工具不依赖真实磁盘数据，也能被稳定验证。

### 文件：`tests/integration/test_mcp_server.py`

* 主要职责：验证 MCP server 对外暴露的工具列表。
* 本阶段修改点：`tools/list` 现在需要包含 `query_knowledge_hub`、`list_collections` 和 `get_document_summary`。
* 在项目中的作用：防止工具实现完成后忘记注册到 server。

## 5. 新手重点理解

`get_document_summary` 解决的是“文档级信息查询”问题。RAG 系统里的底层数据通常是 chunk，因为检索时更适合按小片段召回。但用户有时并不想看某个 chunk，而是想知道“一整篇文档的标题、摘要、标签是什么”。这个工具就是把 chunk 级 metadata 再整理回文档级视角。

本阶段最重要的设计点是复用已有存储，不另起一套数据库。项目当前已经有 `BM25Indexer`，它会把每个 `ChunkRecord` 保存到 `bm25_index.pkl` 中，其中包含：

* chunk id
* chunk 文本
* chunk metadata
* sparse vector

所以 E5 直接读取 `indexer.records`，从里面找属于同一篇文档的 records。这样实现范围小，适合当前阶段，也方便后面如果 `DocumentManager` 完善了，再把数据来源替换成更正式的文档元数据表。

另一个重点是错误也按 MCP tool result 返回。比如找不到文档时，函数不是直接抛异常，而是返回：

```text
isError = True
structuredContent.error.code = document_not_found
```

这样客户端能用统一方式处理工具调用结果，而不是每种错误都要单独猜。

本阶段在 RAG 流程中的位置是“工具服务层”。它不做 embedding、不做检索排序，也不生成答案；它负责把已经入库的文档元数据整理出来，通过 MCP 协议交给外部客户端。



# 整体结构与流程

以下是对 get_document_summary.py 文件的完整解析：

1. 文件定位
项目作用：该文件是 MCP（Model Context Protocol）服务器中的一个工具（Tool）实现。它允许大语言模型（LLM）在需要时主动调用，以获取已入库文档的摘要信息（如标题、内容摘要、标签、来源等）。
所处层级：位于 mcp_server/tools 目录下，属于应用工具层。它向下依赖 ingestion.storage 模块（数据索引层），向上为 MCP 协议层提供标准化的工具接口。
核心职责：接收文档标识（doc_id），从底层的 BM25 倒排索引中检索出该文档的所有分块（Chunk）记录，聚合提取元数据，并将其格式化为大模型易于理解的 Markdown 文本和结构化 JSON 返回。
2. 函数拆解
核心入口与注册
get_document_summary
目的：工具的主处理函数，负责整个摘要获取的核心逻辑。
输入：arguments（包含 doc_id 的字典），index_dir（索引目录路径）。
输出：包含 content（Markdown文本）、structuredContent（结构化字典）和 isError（是否报错）的标准 MCP 响应字典。
核心功能：加载索引 -> 匹配文档 -> 构建摘要 -> 格式化输出。
tool_spec
目的：向 MCP 注册表提供该工具的元数据规范。
输入/输出：无输入，返回 ToolSpec 对象（包含工具名、描述、输入参数 Schema 和处理函数指针）。
参数校验与匹配
_doc_id
目的：从请求参数中提取并校验文档 ID。
输入/输出：输入 arguments 字典，输出清洗后的字符串 doc_id。若参数缺失或为空则抛出 ValueError。
_matches_document
目的：判断索引库中的某条记录（Chunk）是否属于目标文档。
输入/输出：输入 doc_id 和单条 record，输出布尔值。
核心功能：支持多种匹配规则，包括 ID 完全相等、ID 前缀匹配（如 doc_id_chunk0），或元数据中的特定字段（document_id、file_hash 等）匹配。
摘要构建与数据提取
_build_summary
目的：将匹配到的多个 Chunk 记录聚合成一个完整的文档摘要字典。
输入/输出：输入 doc_id 和 records 列表，输出包含 title、summary、tags 等字段的字典。
核心功能：按 Chunk 索引排序，提取元数据，并调用其他辅助函数补全缺失的标题、摘要和标签。
_first_metadata_value
目的：从多个 Chunk 的元数据中，获取第一个非空的指定字段值（如标题）。
_fallback_title
目的：当元数据中没有标题时，生成兜底标题（优先使用文件名的 stem，其次使用 doc_id）。
_fallback_summary
目的：当元数据中没有摘要时，生成兜底摘要（截取第一个 Chunk 文本的前 240 个字符）。
_collect_tags
目的：从所有 Chunk 的元数据中提取标签，支持字符串逗号分隔或列表格式，并进行去重。
格式化与错误处理
_format_summary
目的：将摘要字典转换为人类和 LLM 易读的 Markdown 格式文本。
_error_result
目的：构建标准化的错误响应结构（如索引不可用、文档未找到时调用）。
3. 执行流程
请求接入：MCP Server 接收到 LLM 的调用请求，将 arguments 传入 get_document_summary。
参数校验：调用 _doc_id 提取并校验 doc_id。
加载索引：实例化 BM25Indexer 并加载本地索引。若加载失败，调用 _error_result 返回“索引不可用”错误。
文档匹配：遍历索引中的所有记录，通过 _matches_document 过滤出属于该 doc_id 的所有 Chunk 记录。若无匹配项，返回“文档未找到”错误。
聚合构建：
调用 _build_summary，内部先按 chunk_index 对记录排序。
调用 _first_metadata_value 提取标题，若无则调用 _fallback_title 兜底。
提取摘要，若无则调用 _fallback_summary 截取首段文本兜底。
调用 _collect_tags 收集所有标签。
格式化输出：调用 _format_summary 将聚合后的字典转为 Markdown 文本。
返回结果：将 Markdown 文本放入 content，结构化字典放入 structuredContent，返回给 LLM。
4. 场景示例
业务背景： 用户正在使用一个基于 RAG（检索增强生成）的知识库问答系统。系统索引了一篇名为 RAG_Architecture_Design.pdf 的长文档，该文档在入库时被切分成了 3 个 Chunk（分块），doc_id 为 doc_8848。

全流程串联：

触发调用：用户提问：“帮我总结一下 doc_8848 这篇文档讲了什么？” LLM 决定调用 get_document_summary 工具，传入参数 {"doc_id": "doc_8848"}。
加载与匹配：系统加载 BM25 索引，遍历记录。发现 3 条记录的 ID 分别是 doc_8848_0、doc_8848_1、doc_8848_2。_matches_document 通过前缀匹配规则，成功将这 3 个 Chunk 识别为同一篇文档。
数据聚合：
系统读取这 3 个 Chunk 的 metadata。发现 metadata 中自带了 title="RAG架构设计" 和 tags=["AI", "检索增强"]，但没有 summary 字段。
_build_summary 提取到标题和标签。
因为缺少摘要，触发 _fallback_summary，系统读取第 0 个 Chunk 的正文，截取了前 240 个字符作为临时摘要：“本文档详细介绍了 RAG 的核心组件，包括文档解析、向量化、BM25 混合检索以及重排序机制...”。
格式化返回：_format_summary 生成如下 Markdown 文本：
markdown
# RAG架构设计

Document: doc_8848
Source: RAG_Architecture_Design.pdf
Chunks: 3
Tags: AI, 检索增强

本文档详细介绍了 RAG 的核心组件，包括文档解析、向量化、BM25 混合检索以及重排序机制...
LLM 响应：LLM 接收到这段结构化和文本化的信息后，结合用户的提问，流畅地回答：“这篇名为《RAG架构设计》的文档主要介绍了 RAG 的核心组件，包括文档解析、向量化等机制。全文共分为 3 个部分...”