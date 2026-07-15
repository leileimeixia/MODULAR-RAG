# E4_list_collections 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 MCP Server 的第二个工具：`list_collections`。

它的作用是扫描项目中的 `data/documents/` 目录，找出下面有哪些文档集合，并统计每个集合里有多少文件、总共占用多少字节。

在整个 RAG 项目里，`list_collections` 属于“对外工具层”。前面的 ingestion 阶段负责把文档导入系统，query 阶段负责检索知识，而这个 tool 负责让 MCP 客户端先知道“当前知识库里有哪些集合可用”。这样用户或外部客户端在调用 `query_knowledge_hub` 前，可以先查看有哪些 collection。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/mcp_server/tools/list_collections.py` | 实现 `list_collections` MCP 工具，扫描 `data/documents/` 下的集合目录并返回统计信息 |
| `src/mcp_server/tools/__init__.py` | 将 `list_collections` 注册到默认 MCP tools 列表中，让 server 可以通过 `tools/list` 暴露它 |
| `tests/unit/test_list_collections.py` | 测试 `list_collections` 的集合统计、空目录处理、参数校验和 tool schema |
| `tests/integration/test_mcp_server.py` | 更新 MCP server 集成测试，确认 `tools/list` 能同时列出 `query_knowledge_hub` 和 `list_collections` |
| `DEV_SPEC.md` | 更新 E4 任务状态和总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 的任务进度记录 |

## 3. 核心调用关系

```text
MCP 客户端
  -> 调用 tools/list
  -> ProtocolHandler 返回 default_tools() 里的工具 schema
  -> list_collections 出现在可用工具列表中

MCP 客户端
  -> 调用 tools/call，name = list_collections
  -> ProtocolHandler 根据工具名找到 ToolSpec.handler
  -> 执行 list_collections(arguments)
  -> 扫描 data/documents/ 下的集合目录
  -> 返回 content + structuredContent
```

这里有两个层次：

第一层是“注册”。`default_tools()` 把 `list_collections_spec()` 放进工具列表，MCP 客户端才能看到这个工具。

第二层是“执行”。客户端真正调用 `list_collections` 时，协议层会执行它的 handler，也就是 `list_collections()` 函数。

## 4. 每个核心文件的作用

### 文件：`src/mcp_server/tools/list_collections.py`

* 主要职责：实现集合列表工具。
* 关键函数：
  * `list_collections()`：工具入口，校验参数，扫描集合目录，并组织 MCP tool result。
  * `tool_spec()`：返回 `ToolSpec`，告诉 MCP server 这个工具叫什么、描述是什么、输入 schema 是什么、handler 是谁。
  * `_collection_stats()`：真正扫描目录并计算每个 collection 的文件数量和总字节数。
  * `_format_collections()`：把结构化结果转换成适合人阅读的文本。
* 输入是什么：一个 MCP arguments 字典，当前没有业务参数；默认扫描 `data/documents`。
* 输出是什么：一个包含 `content`、`structuredContent`、`isError` 的 MCP tool result。
* 在项目中的作用：让 MCP 客户端可以查看本地知识库集合，为后续指定 collection 查询做准备。

### 文件：`src/mcp_server/tools/__init__.py`

* 主要职责：集中管理 MCP tools 的导出和默认注册列表。
* 关键函数：
  * `default_tools()`：返回 server 默认暴露的工具列表。
* 输入是什么：无。
* 输出是什么：`ToolSpec` 列表。
* 在项目中的作用：它是 MCP 工具的“注册表”。如果一个 tool 没有放进这里，server 启动后客户端就看不到它。

### 文件：`tests/unit/test_list_collections.py`

* 主要职责：验证 `list_collections` 本身是否正确。
* 关键测试：
  * 能按集合名称排序返回结果。
  * 能统计递归文件数量。
  * 能统计文件总字节数。
  * 当根目录不存在时返回空集合，而不是直接报错。
  * 非对象参数会被拒绝。
  * `tool_spec()` 暴露了正确的 MCP schema。
* 在项目中的作用：保证工具的核心逻辑稳定，不依赖真实项目目录。

### 文件：`tests/integration/test_mcp_server.py`

* 主要职责：从 server 入口层验证 MCP 协议行为。
* 本阶段修改点：`tools/list` 不再只检查 `query_knowledge_hub`，而是确认 `query_knowledge_hub` 和 `list_collections` 都被注册成功。
* 在项目中的作用：防止工具虽然写好了，但忘记注册到 server 中。

## 5. 新手重点理解

`list_collections` 不是直接做问答的工具，它更像是知识库的“目录查看器”。在一个 RAG 系统里，用户可能导入了多个文档集合，例如默认集合、产品文档集合、项目资料集合。查询前先知道有哪些集合，是很自然的一步。

这个阶段最重要的设计点是返回两种结果：

* `content`：给人看的文本，例如 “alpha: documents=2, bytes=11”。
* `structuredContent`：给程序看的结构化数据，例如 collection name、path、document_count、total_bytes。

这样 MCP 客户端既可以直接展示文字，也可以拿结构化字段做 UI、过滤器或下一步调用。

另一个重点是 `tool_spec()`。在 MCP server 里，写出一个函数还不够，还要把它包装成 `ToolSpec`，并放进 `default_tools()`。`ToolSpec` 就像工具的说明书，告诉协议层：

* 工具名是什么。
* 工具描述是什么。
* 输入参数长什么样。
* 真正执行时调用哪个函数。

本阶段在 RAG 流程中的位置是“服务暴露层”。它不参与文档切分、向量化、检索或生成答案，而是把本地知识库的集合信息通过 MCP 协议提供给外部客户端。





# 整体结构与列表

以下是对 list_collections.py 代码文件的完整解析：

1. 文件定位
项目作用：该文件是 RAG（检索增强生成）系统中 MCP（Model Context Protocol）服务器的一个内置工具（Tool）。它的主要作用是让大模型或外部客户端能够“看到”本地文件系统中有哪些文档集合（即知识库文件夹），并了解每个集合的基本规模。
所处层级：位于 src/mcp_server/tools/ 目录下，属于MCP 工具层。它是连接底层本地文件系统与上层大模型交互协议的桥梁。
核心职责：扫描指定的文档根目录，收集其下所有子目录（文档集合）的文件数量和总大小，并将这些统计信息转换为 MCP 协议要求的标准响应格式返回。
2. 函数拆解
list_collections(arguments, documents_root)

作用：MCP 工具的主处理函数（Handler），负责接收调用请求并返回最终结果。
输入：arguments（工具调用参数，本工具无需额外参数，通常为空字典），documents_root（文档根目录路径，默认为 "data/documents"）。
输出：符合 MCP 协议标准的字典，包含供大模型阅读的文本内容（content）和供程序解析的结构化数据（structuredContent）。
核心功能：校验输入参数，调用统计函数获取数据，调用格式化函数生成文本，最后组装并返回标准响应。
tool_spec()

作用：返回该工具的注册规范（ToolSpec）。
输入：无。
输出：ToolSpec 对象。
核心功能：定义工具的名称（list_collections）、功能描述、输入参数 Schema（此处为空）以及对应的处理函数。MCP 服务器启动时会调用它来注册这个工具。
_collection_stats(root)

作用：内部辅助函数，负责“干脏活”——扫描文件系统并统计数据。
输入：root（根目录的 Path 对象）。
输出：包含各集合统计信息的字典列表（如集合名、路径、文件数、总字节数）。
核心功能：遍历根目录下的所有子文件夹，递归统计每个子文件夹内的文件数量和总大小（字节）。
_format_collections(root, collections)

作用：内部辅助函数，负责将冷冰冰的数据转化为人类（或大模型）易读的文本。
输入：root（根目录），collections（统计信息字典列表）。
输出：格式化后的多行字符串。
核心功能：将统计列表拼接成类似清单的文本格式；如果目录下没有集合，则返回友好的提示信息。
3. 执行流程
工具注册：MCP 服务器启动时，调用 tool_spec() 获取工具定义，将其注册到工具列表中。
发起调用：大模型或客户端决定查询本地文档库，向 MCP 服务器发送调用 list_collections 的请求。
参数校验：请求路由到 list_collections 函数，首先校验传入的 arguments 是否为字典。
文件扫描：调用 _collection_stats(root)，底层使用 pathlib 遍历 data/documents 目录，计算出每个子文件夹的文件数和总大小。
文本格式化：调用 _format_collections(root, collections)，将上一步得到的统计数据拼接成一段清晰的纯文本。
组装返回：将纯文本放入 content 字段，将原始字典数据放入 structuredContent 字段，封装成 MCP 标准响应格式返回给调用方。
4. 场景示例
假设你的 RAG 系统用于企业知识问答，文档存放在 data/documents 目录下，里面有两个子文件夹：

company_policies（公司制度）：里面有 5 个 PDF 文件，总大小 10MB。
project_docs（项目文档）：里面有 20 个 Markdown 文件，总大小 2MB。
全流程串联：

用户问大模型：“系统里现在有哪些知识库？”
大模型判断需要调用工具，触发 list_collections。
函数执行 _collection_stats，扫描发现两个文件夹，统计出 company_policies 有 5 个文件（10485760 字节），project_docs 有 20 个文件（2097152 字节）。
函数执行 _format_collections，生成文本：
text
Document collections under data/documents:
- company_policies: documents=5, bytes=10485760
- project_docs: documents=20, bytes=2097152
大模型接收到这段文本和结构化数据后，用自然语言回答用户：“目前系统里有两个文档集合：一个是‘公司制度’，包含 5 个文件；另一个是‘项目文档’，包含 20 个文件。”
通过这个过程，大模型就成功“感知”到了本地物理文件系统的结构。