# E2_protocol_handler 学习笔记

## 1. 本阶段完成了什么

本阶段完成的是 MCP Server 的协议处理层，也就是 `ProtocolHandler`。

E1 已经实现了最小 stdio server：它能从 stdin 读请求、向 stdout 写 JSON-RPC 响应，并把日志写到 stderr。E2 在这个基础上，把具体的协议解析和方法分发从 `server.py` 中拆出来，放到 `mcp_server/protocol_handler.py`。

本阶段主要支持三类 MCP/JSON-RPC 方法：

```text
initialize
tools/list
tools/call
```

同时实现 JSON-RPC 常见错误响应：

```text
-32600 Invalid Request
-32601 Method not found
-32602 Invalid params
-32603 Internal error
```

完成 E2 后，`server.py` 只负责 stdio 通信，`ProtocolHandler` 负责协议处理。职责更清楚，也更容易测试。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/mcp_server/protocol_handler.py` | 实现 JSON-RPC 协议解析、能力协商和 tools 路由 |
| `src/mcp_server/server.py` | 改为把请求委托给 `ProtocolHandler` 处理 |
| `tests/unit/test_protocol_handler.py` | 验证 initialize、tools/list、tools/call、通知和错误响应 |
| `DEV_SPEC.md` | 标记 E2 完成并更新进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 E2 进度表 |

## 3. 核心调用关系

```text
server.py
  -> 读取 stdin 中的一行 JSON
  -> json.loads()
  -> ProtocolHandler.handle_message(request)
  -> 返回 JSON-RPC response 或 None
  -> server.py 写入 stdout
```

`ProtocolHandler` 内部的分发关系是：

```text
handle_message()
  -> 校验 JSON-RPC 基本格式
  -> _dispatch(method, params)
      -> initialize   -> handle_initialize()
      -> tools/list   -> handle_tools_list()
      -> tools/call   -> handle_tools_call()
      -> 其他 method  -> -32601 Method not found
```

如果请求是 notification，例如：

```text
notifications/initialized
```

且没有 `id`，则不返回响应。

## 4. 每个核心文件的作用

### 文件：`src/mcp_server/protocol_handler.py`

* 主要职责：处理 JSON-RPC 请求和 MCP 核心方法。
* 关键类：`ProtocolHandler`、`ToolSpec`、`ProtocolError`。
* 输入是什么：已经解析好的 JSON 对象。
* 输出是什么：JSON-RPC 响应字典，或者 notification 时返回 `None`。
* 在项目中的作用：作为 MCP Server 的协议层核心。

### `ToolSpec`

`ToolSpec` 表示一个已注册 MCP tool：

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: JsonObject
    handler: ToolHandler
```

它包含两部分：

```text
schema：给 tools/list 暴露给 MCP Client
handler：tools/call 时真正执行的函数
```

`schema()` 方法会返回：

```python
{
    "name": self.name,
    "description": self.description,
    "inputSchema": dict(self.input_schema),
}
```

这正是 MCP Client 需要看到的工具描述。

### `ProtocolHandler.handle_message()`

这是协议处理入口。它先检查请求是不是一个合法 JSON-RPC 请求：

```python
if not isinstance(message, dict):
    return error_response(None, -32600, "Invalid Request")
if message.get("jsonrpc") != "2.0" or "method" not in message:
    return error_response(request_id, -32600, "Invalid Request")
```

然后根据 method 分发。普通请求有 `id`，需要返回 response；notification 没有 `id`，不返回 response。

### `handle_initialize()`

这个方法返回 server 基本信息和能力声明：

```python
{
    "protocolVersion": "...",
    "capabilities": {"tools": {}},
    "serverInfo": {
        "name": "modular-rag-mcp-server",
        "version": "0.1.0",
    },
}
```

它告诉 MCP Client：这个 server 支持 tools 能力。后续工具细节会通过 `tools/list` 暴露。

### `handle_tools_list()`

这个方法返回所有已注册 tool 的 schema：

```python
return {"tools": [tool.schema() for tool in self.tools.values()]}
```

当前 E2 只实现注册和列出机制，真正的业务 tools 会在 E3 以后逐步补上。

### `handle_tools_call()`

这个方法负责处理工具调用：

```python
name = params.get("name")
arguments = params.get("arguments", {})
tool = self.tools.get(name)
return _tool_result(tool.handler(arguments))
```

它会校验：

```text
params 必须是 object
name 必须是非空字符串
arguments 必须是 object
tool 必须存在
```

如果不符合，就返回 `-32602 Invalid params`。

### `_tool_result()`

这个函数把 tool handler 的返回值包装成 MCP tool result：

```python
{
    "content": [{"type": "text", "text": "..."}],
    "isError": False,
}
```

如果 handler 已经返回了包含 `content` 的结构，就直接使用。这样后续更复杂的工具可以自己构造 MCP 返回格式。

### 文件：`src/mcp_server/server.py`

* 主要职责：保留 stdio 循环。
* 本阶段变化：不再自己处理 `initialize` 和未知方法，而是调用 `ProtocolHandler.handle_message()`。
* 在项目中的作用：把“传输层”和“协议层”分开。

现在 `server.py` 的核心逻辑变成：

```python
request = json.loads(line)
response = handler.handle_message(request)
```

如果 JSON 解析失败，则返回 parse error：

```python
response = parse_error_response()
```

### 文件：`tests/unit/test_protocol_handler.py`

* 主要职责：直接测试协议处理器，不通过子进程。
* 关键测试：
  * `initialize` 返回 serverInfo 和 capabilities。
  * `tools/list` 返回注册工具的 schema。
  * `tools/call` 能路由到注册 tool。
  * notification 不返回 response。
  * invalid request 返回 `-32600`。
  * unknown method 返回 `-32601`。
  * invalid tools/call params 返回 `-32602`。

这类单元测试比子进程测试更快，也能细粒度覆盖协议边界。

## 5. 新手重点理解

这一阶段最重要的是理解为什么要把 `ProtocolHandler` 从 `server.py` 里拆出来。

`server.py` 关注的是传输：

```text
stdin 读
stdout 写
stderr 记日志
```

`ProtocolHandler` 关注的是协议：

```text
这个 JSON-RPC 请求是否合法
method 是什么
params 是否正确
应该返回 result 还是 error
```

这两个职责如果混在一起，后面加工具、加错误处理、加测试都会变得很乱。拆开以后，server 可以保持很薄，协议逻辑可以独立测试。

另一个重点是 JSON-RPC 的错误码。不要随便用普通字符串返回错误，而是要用规范格式：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32601,
    "message": "Method not found"
  }
}
```

这样 MCP Client 才能稳定识别错误类型。

本阶段在整体项目中的位置是：

```text
MCP Client
  -> server.py stdio transport
  -> ProtocolHandler JSON-RPC dispatch
  -> tools/list 或 tools/call
  -> 后续具体工具
```

完成 E2 后，MCP Server 已经有了协议骨架。下一步 E3 就可以把真正的 `query_knowledge_hub` 工具挂到 `tools/call` 上。




# 整体结构与流程

用户要求对代码文件做完整解析，这是一个问答类需求，不需要修改代码。我需要按四个维度讲解：文件定位、函数拆解、执行流程、场景示例。

让我梳理一下这个文件：

文件定位：MCP（Model Context Protocol）服务器的 JSON-RPC 2.0 协议处理层，属于协议层/消息分发层，负责把客户端发来的 JSON-RPC 消息解析、校验、分发到对应的处理方法。

核心函数：

ToolSpec 数据类 - 工具规格定义
ProtocolHandler.init - 初始化工具注册表
handle_message - 入口，校验 JSON-RPC 格式
_dispatch - 方法路由
handle_initialize - 处理 initialize 握手
handle_tools_list - 列出所有工具
handle_tools_call - 调用具体工具
ProtocolError - 协议错误
error_response / parse_error_response - 构造错误响应
_tool_result - 包装工具返回结果
执行流程：客户端消息 → handle_message（校验）→ dispatch（路由）→ 具体 handle*（处理）→ 返回 JSON-RPC 响应

场景示例：客户端调用一个 search 工具

由于不需要修改代码，我直接输出解析内容即可。



# `protocol_handler.py` 完整解析

## 一、文件定位

这个文件是 **MCP（Model Context Protocol）服务器的"协议翻译官"**，处于整个系统的 **协议层 / 消息分发层**。

- **在项目中的作用**：把外部客户端（比如 IDE 插件、AI Agent）发来的 JSON-RPC 2.0 格式消息，翻译成服务器内部能理解的函数调用，再把结果打包成标准的 JSON-RPC 响应返回。
- **所处层级**：位于传输层（stdio/HTTP）之上、业务工具层之下。传输层只负责"把字节送进来"，本文件负责"把消息看懂并分发"，再往下就是具体的工具实现（比如搜索、计算等）。
- **核心职责**：
  1. 校验 JSON-RPC 消息格式是否合法；
  2. 根据 `method` 字段路由到对应的处理函数（`initialize` / `tools/list` / `tools/call`）；
  3. 统一处理异常并返回标准化的错误响应。

---

## 二、函数拆解

### 1. 常量与类型别名（文件顶部）

```python
SERVER_NAME = "modular-rag-mcp-server"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOL_VERSION = "2024-11-05"
JsonObject = dict[str, Any]
ToolHandler = Callable[[JsonObject], Any]
作用：定义服务器身份信息和协议版本，以及两个类型别名，方便后续代码阅读。
输入/输出：无。
2. ToolSpec（dataclass）
作用：描述一个"已注册工具"的元信息——名字、描述、输入 schema、真正的处理函数。
核心方法 schema()：返回暴露给客户端的工具描述（tools/list 接口用）。
输入：name / description / input_schema / handler。
输出：schema() 返回形如 {"name": ..., "description": ..., "inputSchema": ...} 的字典。
3. ProtocolHandler.__init__(self, tools=None)
作用：初始化协议处理器，把传入的 ToolSpec 列表转成 {name: ToolSpec} 的字典，便于按名字快速查找。
输入：可选的 ToolSpec 列表。
输出：无（仅设置 self.tools）。
4. ProtocolHandler.handle_message(self, message) ⭐ 入口函数
作用：处理一条完整的 JSON-RPC 请求，是整个协议的总入口。
输入：任意对象 message（理论上应该是解析后的 JSON 字典）。
输出：JSON-RPC 响应字典，或 None（通知类消息无需响应）。
核心逻辑：
校验 message 是否为 dict；
校验 jsonrpc == "2.0" 且包含 method；
如果是通知（id 为 None 且 method 以 notifications/ 开头），直接返回 None；
调用 _dispatch 分发；
捕获 ProtocolError 和通用 Exception，统一转成错误响应；
没有 id 的请求不返回响应。
5. ProtocolHandler._dispatch(self, method, params)
作用：根据 method 字段路由到具体处理函数。
输入：method 字符串、params 参数。
输出：处理结果字典。
路由表：
initialize → handle_initialize
tools/list → handle_tools_list
tools/call → handle_tools_call
其它 → 抛出 ProtocolError(-32601, "Method not found")
6. ProtocolHandler.handle_initialize(self, params)
作用：处理客户端握手请求，返回服务器元信息和能力声明。
输入：params（可能包含客户端的 protocolVersion）。
输出：包含 protocolVersion、capabilities、serverInfo 的字典。
7. ProtocolHandler.handle_tools_list(self)
作用：返回所有已注册工具的 schema 列表。
输入：无。
输出：{"tools": [schema1, schema2, ...]}。
8. ProtocolHandler.handle_tools_call(self, params) ⭐ 核心业务入口
作用：根据 params.name 找到对应工具，调用其 handler(arguments) 并包装结果。
输入：params 字典，必须含 name 和可选的 arguments。
输出：由 _tool_result 包装后的标准结果字典。
校验点：
params 必须是 dict；
name 必须是非空字符串；
arguments 必须是 dict；
工具必须已注册。
9. ProtocolError（异常类）
作用：携带 JSON-RPC 错误码的自定义异常，继承自 ValueError。
属性：code（错误码）、message（错误描述）。
10. error_response(request_id, code, message)
作用：构造标准的 JSON-RPC 错误响应。
输出：{"jsonrpc": "2.0", "id": ..., "error": {"code": ..., "message": ...}}。
11. parse_error_response(message="Parse error")
作用：专门构造 -32700（Parse error）错误响应，用于 JSON 解析失败场景。
12. _tool_result(result)
作用：把工具返回值统一包装成 MCP 标准格式。
逻辑：
如果已经是 {"content": ...} 形式，直接返回；
否则把字符串/对象转成文本，包装成 [{"type": "text", "text": ...}]，并标记 isError: False。
三、执行流程
客户端发送 JSON-RPC 消息
        ↓
[handle_message]  ← 总入口，做格式校验
        ↓ （校验通过）
[_dispatch]       ← 根据 method 路由
        ↓
   ┌────┴────┬────────────┐
   ↓         ↓            ↓
[initialize] [tools/list] [tools/call]
   ↓         ↓            ↓
返回元信息  返回工具列表   ↓
                     [找到 ToolSpec]
                           ↓
                   调用 tool.handler(arguments)
                           ↓
                   [_tool_result] 包装结果
                           ↓
                   返回 {"content": [...]}
        ↓
[handle_message] 组装最终响应 {"jsonrpc":"2.0","id":...,"result":...}
        ↓
返回给客户端

异常路径：
任意环节抛出 ProtocolError → error_response(对应错误码)
任意环节抛出 Exception   → error_response(-32603, "Internal error: ...")
四、场景示例
假设我们注册了一个名为 search_docs 的工具，用于检索文档。客户端想调用它查询"RAG 是什么"。

步骤 1：客户端发送请求
json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "tools/call",
  "params": {
    "name": "search_docs",
    "arguments": {"query": "RAG 是什么"}
  }
}
步骤 2：handle_message 校验
是 dict ✅
jsonrpc == "2.0" ✅
包含 method ✅
id 不为 None，不是通知 → 需要返回响应
步骤 3：_dispatch 路由
method == "tools/call" → 调用 handle_tools_call(params)
步骤 4：handle_tools_call 处理
校验 params 是 dict、name 是字符串、arguments 是 dict ✅
从 self.tools 中找到 search_docs 对应的 ToolSpec
调用 tool.handler({"query": "RAG 是什么"})，假设返回字符串 "RAG 是检索增强生成..."
步骤 5：_tool_result 包装
把字符串包装成：

json
{
  "content": [{"type": "text", "text": "RAG 是检索增强生成..."}],
  "isError": false
}
步骤 6：handle_message 组装最终响应
json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "content": [{"type": "text", "text": "RAG 是检索增强生成..."}],
    "isError": false
  }
}
异常情况示例
如果客户端发了 method: "unknown/method"：

_dispatch 抛出 ProtocolError(-32601, "Method not found: unknown/method")
handle_message 捕获后返回：
json
{
  "jsonrpc": "2.0",
  "id": 42,
  "error": {"code": -32601, "message": "Method not found: unknown/method"}
}
小结
这个文件就像一个 "前台接待员"：

先检查来客（消息）格式是否规范；
再问清来意（method）并带到对应窗口（handle_*）；
窗口办完事后，把结果按标准格式封装好交还给来客；
任何环节出问题，都统一开具"错误回执"（error_response）。
这样上层业务工具（ToolSpec.handler）就完全不用关心协议细节，只需专注自己的业务逻辑即可。