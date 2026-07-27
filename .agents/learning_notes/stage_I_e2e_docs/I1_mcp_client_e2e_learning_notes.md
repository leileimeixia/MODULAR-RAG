# I1_mcp_client_e2e 学习笔记

## 1. 本阶段完成了什么

本阶段新增了 `tests/e2e/test_mcp_client.py`，用于模拟 MCP Client 侧调用。

前面阶段已经实现了 MCP Server、协议处理器和 `query_knowledge_hub` 等工具。I1 要验证的是：当外部客户端通过 stdio JSON-RPC 连接这个 server 时，能不能完整走通 MCP 的核心流程。

这条测试会启动一个真正的 Python 子进程，在子进程里运行 `server.main()`，然后测试代码像客户端一样往 stdin 写入 JSON-RPC 请求，从 stdout 读取响应。它依次模拟：

* `initialize`
* `tools/list`
* `tools/call`

最后验证 `query_knowledge_hub` 工具返回了 citations。

这一阶段在整个项目中的位置是“端到端验收”。它不是单独测试某个函数，而是验证 MCP stdio server 能被外部进程像真实 MCP Client 一样调用。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `tests/e2e/test_mcp_client.py` | 新增 MCP Client 侧 E2E 测试，通过子进程模拟 stdio JSON-RPC 调用 |
| `DEV_SPEC.md` | 更新 I1 任务进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步自动开发进度表 |

## 3. 核心调用关系

```text
pytest tests/e2e/test_mcp_client.py
  -> subprocess.Popen([python, "-c", SERVER_BOOTSTRAP])
  -> 子进程导入 mcp_server.server
  -> 替换 server.default_tools 为 fake 工具集合
  -> server.main() 启动 stdio JSON-RPC loop
  -> 测试进程写入 initialize 请求
  -> 测试进程写入 tools/list 请求
  -> 测试进程写入 tools/call 请求
  -> 读取并断言响应内容
```

请求和响应的数据流是：

```text
测试进程 stdin 写 JSON-RPC
  -> server.main()
  -> ProtocolHandler.handle_message()
  -> tools/list 或 tools/call
  -> fake_query_knowledge_hub()
  -> stdout 返回 JSON-RPC response
  -> 测试进程解析并断言
```

## 4. 每个核心文件的作用

### 文件：`tests/e2e/test_mcp_client.py`

* 主要职责：模拟外部 MCP Client 调用 stdio server。
* 关键内容：
  * `SERVER_BOOTSTRAP`：子进程启动脚本。
  * `fake_query_knowledge_hub()`：fake 工具处理函数，返回稳定的 answer 和 citations。
  * `fake_default_tools()`：替换 server 默认工具集合，避免测试依赖真实向量库和配置。
  * `test_mcp_client_lists_and_calls_query_knowledge_hub()`：完整执行 initialize、tools/list、tools/call。
  * `_request()`：向子进程 stdin 写请求，并从 stdout 读取响应。
  * `_stop_process()`：关闭子进程，避免测试结束后残留进程。
* 输入是什么：JSON-RPC 请求。
* 输出是什么：JSON-RPC 响应。
* 在项目中的作用：验证 MCP server 的 stdio 边界能被真实进程调用。

### 文件：`src/mcp_server/server.py`

* I1 没有修改它，但测试会真正运行它。
* 主要职责：启动 line-delimited JSON-RPC stdio loop。
* 核心逻辑：

```text
for line in stdin:
  -> json.loads(line)
  -> ProtocolHandler.handle_message(request)
  -> 如果有 response，就写到 stdout
```

* 在项目中的作用：这是 MCP Server 对外暴露给客户端的入口。

### 文件：`src/mcp_server/protocol_handler.py`

* I1 没有修改它，但测试会经过它。
* 主要职责：处理 JSON-RPC 方法分发。
* 关键方法：
  * `handle_initialize()`：返回 server metadata 和 capabilities。
  * `handle_tools_list()`：返回工具 schema。
  * `handle_tools_call()`：根据工具名调用对应 handler。
* 在项目中的作用：把 MCP 协议请求变成项目内部工具调用。

## 5. 新手重点理解

I1 的重点是“像真实客户端一样调用 server”。

为什么不用直接调用 `ProtocolHandler.handle_message()`？因为那更像单元测试，只能证明函数逻辑没问题。MCP Client 实际连接的是一个 stdio 子进程，所以 I1 用 `subprocess.Popen()` 启动 server，再通过 stdin/stdout 通信，这样更接近真实使用方式。

为什么要替换 `server.default_tools`？因为真实 `query_knowledge_hub` 会加载配置、初始化检索器、访问本地向量库。E2E 协议测试的目标不是验证向量库，而是验证 MCP 通信链路。所以这里用 fake tool 返回稳定数据，让测试可靠、快速、可重复。

为什么要测试 `initialize`、`tools/list`、`tools/call`？这是 MCP Client 使用工具的基本顺序：

```text
先握手 initialize
再询问有哪些工具 tools/list
最后调用具体工具 tools/call
```

为什么要断言 citations？因为 `query_knowledge_hub` 的核心价值不是只返回一段文字，而是返回带引用的结果。客户端拿到 citations 后，才能知道回答依据来自哪个 chunk 或 source。

这一阶段相当于从“项目内部函数能跑”推进到“外部 MCP Client 能真的连上并调用工具”。


# 整体结构与流程
文件定位
文件路径：d:\RAG\MODULAR-RAG-CLEAN-START\tests\e2e\test_mcp_client.py

作用与层级： 该文件属于项目的端到端（E2E）测试层（位于 tests/e2e 目录下）。它的主要作用是模拟真实的客户端，通过标准输入输出（stdio）和 JSON-RPC 协议，与 MCP（Model Context Protocol）服务器进行完整的通信交互测试。

核心职责： 验证 MCP 服务器能否正确启动、响应初始化握手、正确暴露可用工具列表，以及在接收到工具调用请求时，能否正确执行并返回符合协议规范的结构化数据。

函数拆解
1. SERVER_BOOTSTRAP (字符串常量)
作用目的：它不是一個函数，而是一段内嵌的 Python 脚本代码字符串。用于在子进程中动态生成并启动一个“伪造”的 MCP 服务器。
核心功能：
动态注入一个名为 query_knowledge_hub 的假工具及其处理逻辑。
该假工具会返回预设的文本答案和结构化的引用信息（Citations）。
最后调用 server.main() 启动真实的 MCP 服务器逻辑。
2. test_mcp_client_lists_and_calls_query_knowledge_hub()
作用目的：核心的 E2E 测试用例，验证客户端与 MCP 服务器的完整交互链路。
输入/输出：无显式输入输出，通过 assert 断言来验证结果。
核心功能：
启动子进程运行 SERVER_BOOTSTRAP 脚本。
依次发送三个 JSON-RPC 请求：initialize（初始化）、tools/list（获取工具列表）、tools/call（调用工具）。
校验每一步的返回结果是否符合 MCP 协议规范和业务预期。
在 finally 块中确保子进程被安全关闭。
3. _request(process, payload)
作用目的：封装与子进程（MCP 服务器）的底层通信逻辑。
输入：
process：子进程对象（subprocess.Popen）。
payload：字典格式的请求体（符合 JSON-RPC 2.0 规范）。
输出：解析后的字典格式响应体。
核心功能：
将请求字典序列化为 JSON 字符串，并写入子进程的标准输入（stdin）。
从子进程的标准输出（stdout）读取响应行。
反序列化响应 JSON，并校验 jsonrpc 版本、id 匹配以及是否包含 error 字段。
4. _stop_process(process)
作用目的：安全、优雅地终止 MCP 服务器子进程，防止僵尸进程或端口/资源占用。
输入：process（子进程对象）。
输出：无。
核心功能：
关闭子进程的 stdin，向其发送结束信号。
等待进程自然退出（超时时间为 5 秒）。
如果超时未退出，则强制 kill 进程并再次等待。
执行流程
启动环境：测试函数被 pytest 触发，使用 subprocess.Popen 启动一个独立的 Python 子进程，执行 SERVER_BOOTSTRAP 中的代码，从而在后台拉起一个带有假工具的 MCP 服务器。
握手初始化：调用 _request 发送 initialize 请求。服务器返回自身信息（名称、能力），测试代码断言服务器名称为 modular-rag-mcp-server 且具备 tools 能力。
发现工具：调用 _request 发送 tools/list 请求。服务器返回可用工具列表，测试代码断言列表中仅包含我们注入的 query_knowledge_hub 工具。
调用工具：调用 _request 发送 tools/call 请求，指定调用 query_knowledge_hub 并传入查询参数 "How do I configure Azure OpenAI?"。
校验结果：服务器执行假工具逻辑并返回结果。测试代码断言返回结果中：
isError 为 False。
文本内容包含 "Citations:"。
结构化内容（structuredContent）中的引用信息（chunk_id, source_path, score）完全正确。
清理资源：无论测试通过还是失败，触发 finally 块，调用 _stop_process 关闭 stdin 并等待/强杀子进程，完成测试。
场景示例
业务背景： 假设你们团队开发了一个企业级 RAG（检索增强生成）系统，为了让外部的 AI 助手（如 Claude Desktop、Cursor 或自研 Agent）能够直接查询你们内部的知识库，你们使用 MCP 协议 将“查询知识库”的能力封装成了一个工具（Tool）暴露出去。

场景串联： 在正式上线前，你需要确保外部 AI 助手能顺利连上你们的 MCP 服务器并成功查到数据。于是你写了这个 E2E 测试来模拟 AI 助手的行为：

AI 助手连接服务器：测试代码启动子进程，模拟 AI 助手通过 stdio 连上你们的 MCP 服务器。
打招呼（Initialize）：AI 助手发送 initialize 请求：“你好，我是某某客户端，我们建立连接吧。” 服务器回应：“你好，我是 modular-rag-mcp-server，我支持工具调用。”
询问能力（Tools/List）：AI 助手问：“你都能干些什么？” 服务器回答：“我有一个叫 query_knowledge_hub 的工具，可以帮你查知识库。”
发起查询（Tools/Call）：AI 助手说：“那帮我查一下如何配置 Azure OpenAI”。
返回结果：你们的服务器（在测试中由 SERVER_BOOTSTRAP 模拟）去知识库检索后，返回了答案，并附带了引用来源：“答案来自 docs/guide.md 的 chunk-a 片段，置信度 0.95”。
验收与收尾：测试代码检查返回的数据格式是否标准、引用信息是否准确。确认无误后，测试结束，关闭模拟服务器。
通过这个测试，你就可以拍着胸脯保证：只要 MCP 服务器一上线，任何支持 MCP 协议的 AI 客户端都能完美地调用你们的知识库查询功能！