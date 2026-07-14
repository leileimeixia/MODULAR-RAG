# E1_mcp_stdio_server 学习笔记

## 1. 本阶段完成了什么

本阶段完成的是 MCP Server 的最小 stdio 入口，也就是 `src/mcp_server/server.py`。

阶段 D 已经完成了本地 RAG 查询链路。阶段 E 开始把这些能力包装成 MCP Server，让外部 MCP Client 可以通过标准协议调用项目里的知识库工具。

E1 暂时不实现完整工具列表和工具调用，它先解决最基础的问题：

```text
server 能通过 stdin 接收 JSON-RPC 请求
server 能通过 stdout 返回 JSON-RPC 响应
server 的日志只能写 stderr，不能污染 stdout
server 能响应 initialize 握手
```

这一步属于 MCP Server 层的地基。后续 E2 会把协议解析能力拆到 `ProtocolHandler`，E3 以后再接入真正的 tools。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/mcp_server/server.py` | 实现最小 MCP stdio server 入口 |
| `tests/integration/test_mcp_server.py` | 使用子进程验证 stdio 行为和 JSON-RPC 响应 |
| `DEV_SPEC.md` | 标记 E1 完成并更新进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 E1 进度表 |

## 3. 核心调用关系

```text
MCP Client
  -> stdin 写入一行 JSON-RPC 请求
  -> server.py main() 逐行读取
  -> json.loads() 解析请求
  -> _handle_request()
  -> _write_message() 写 JSON-RPC 响应到 stdout
```

日志流向是另一条线：

```text
server 启动/停止日志
  -> _log()
  -> stderr
```

这个分离很关键：MCP Client 会把 stdout 当成协议消息通道。如果 stdout 里混入普通日志，Client 就可能解析失败。

## 4. 每个核心文件的作用

### 文件：`src/mcp_server/server.py`

* 主要职责：提供最小 MCP stdio server 入口。
* 关键函数：`main()`、`_handle_request()`、`_initialize_result()`、`_write_message()`、`_log()`。
* 输入是什么：stdin 中逐行传入的 JSON-RPC 请求。
* 输出是什么：stdout 中逐行返回的 JSON-RPC 响应；stderr 中输出运行日志。
* 在项目中的作用：作为 MCP Server 层的启动入口。

`main()` 是 stdio 循环：

```python
for line in stdin:
    if not line.strip():
        continue
    request = json.loads(line)
    response = _handle_request(request)
    if response is not None:
        _write_message(stdout, response)
```

它做的事情很简单：一行输入对应一次请求处理，一行输出对应一次协议响应。

### `_handle_request()`

这个函数负责处理当前最小协议范围：

```text
initialize -> 返回 serverInfo 和 capabilities
notifications/initialized -> 不返回响应
其他 method -> 返回 -32601 Method not found
```

这里遵循 JSON-RPC 的基本格式：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {}
}
```

如果请求格式不对，会返回：

```text
-32600 Invalid Request
```

如果方法不存在，会返回：

```text
-32601 Method not found
```

### `_initialize_result()`

这个函数构造 initialize 响应：

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

当前 tools 还没有接入，所以 capabilities 里先声明空的 tools 能力结构。后续 E2/E3 会继续补充。

### `_write_message()`

这个函数把响应写到 stdout：

```python
stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
stdout.flush()
```

注意它只写 JSON-RPC payload，而且每条消息后加换行。测试会检查 stdout 里只有 JSON 响应，没有普通日志。

### `_log()`

这个函数把日志写到 stderr：

```python
print(message, file=stderr)
```

这是 E1 的关键约束之一：日志不能进 stdout。

### 文件：`tests/integration/test_mcp_server.py`

* 主要职责：用子进程方式测试真实 stdio 行为。
* 关键测试：
  * 启动 server 后发送 `initialize`，stdout 返回一条 JSON-RPC 响应。
  * stderr 包含启动和停止日志。
  * 未知方法返回 JSON-RPC `-32601` 错误。

测试通过 `subprocess.run()` 启动真实脚本：

```python
subprocess.run(
    [sys.executable, str(SERVER_PATH)],
    input=payload,
    text=True,
    capture_output=True,
)
```

这种测试比直接调用函数更接近真实 MCP Client 与 Server 之间的通信方式。

## 5. 新手重点理解

这一阶段最重要的是理解 stdio transport 的规则。

在 MCP stdio 模式里：

```text
stdin：Client 发给 Server 的协议消息
stdout：Server 发给 Client 的协议消息
stderr：Server 自己的日志
```

所以 stdout 必须非常干净，只能输出可被 Client 解析的 JSON-RPC 消息。哪怕只是多打印一句调试日志，也可能让 Client 认为协议坏了。

另一个重点是 E1 不是完整 MCP Server。它只是先把入口打通：

```text
能启动
能读 stdin
能写 stdout
能响应 initialize
能把日志放 stderr
```

后续 E2 会把协议处理拆成更正式的 `ProtocolHandler`，并支持 `tools/list` 和 `tools/call`。E1 先把“通信管道”铺好。

本阶段在整体项目中的位置是：

```text
MCP Client
  -> mcp_server/server.py
  -> 后续 ProtocolHandler
  -> 后续 Tools
  -> Core 查询链路
```

完成 E1 后，项目已经有了一个最小 MCP stdio server 外壳，可以响应 MCP 初始化握手。


# 整体架构与流程

1. 文件定位
作用：该文件是 Modular RAG 系统中 MCP（Model Context Protocol，模型上下文协议）服务器的极简标准输入输出（stdio）入口。 所处层级：处于系统的通信层/协议层。它不直接处理具体的 RAG 检索或重排业务逻辑，而是作为外部客户端（如大模型应用、IDE 插件等）与 RAG 系统之间的“通信网关”。 核心职责：负责监听标准输入（stdin），接收并解析客户端发来的 JSON-RPC 2.0 格式请求，将请求路由到对应的处理逻辑，最后将处理结果序列化后通过标准输出（stdout）返回给客户端。

2. 函数拆解
main(stdin, stdout, stderr)

目的：运行基于行分隔的 JSON-RPC 标准输入输出循环，是程序的主入口。
输入：标准输入流、标准输出流、标准错误流（可选，默认使用系统自带的 sys.stdin 等）。
输出：返回整数状态码（0 表示正常退出）。
核心功能：初始化流并打印启动日志；进入死循环逐行读取 stdin 的内容；跳过空行，将每行文本解析为 JSON 对象并交给 _handle_request 处理；如果处理过程中发生异常，则捕获并返回内部错误响应；最后将非空响应通过 _write_message 写回 stdout。
_handle_request(request)

目的：解析并路由单个 JSON-RPC 请求。
输入：解析后的 JSON 字典（Any 类型）。
输出：返回响应字典，或者返回 None（对于不需要响应的通知类请求）。
核心功能：首先校验请求是否符合 JSON-RPC 2.0 规范（必须是字典、包含 jsonrpc="2.0" 和 method 字段）。然后根据 method 进行路由：如果是 "initialize"，则构建并返回初始化成功响应；如果是 "notifications/initialized"，返回 None（不回复）；如果是其他未知方法，则返回“方法未找到”的错误响应。
_initialize_result(params)

目的：构建 "initialize" 请求的具体返回结果。
输入：客户端传来的请求参数（Any 类型）。
输出：包含协议版本、能力声明和服务器信息的字典。
核心功能：提取客户端声明的协议版本，返回服务器支持的协议版本，声明当前服务器支持 tools（工具）能力，并返回服务器的名称和版本号。
_error_response(request_id, code, message)

目的：构建标准的 JSON-RPC 错误响应。
输入：请求 ID（用于匹配客户端请求）、错误码（如 -32600 表示无效请求）、错误信息字符串。
输出：符合 JSON-RPC 2.0 规范的错误响应字典。
_write_message(stdout, payload)

目的：将响应数据序列化并发送给客户端。
输入：标准输出流、要发送的字典数据。
核心功能：将字典转换为紧凑的 JSON 字符串（不带多余空格），追加换行符后写入 stdout，并立即刷新缓冲区以确保数据实时发送。
_log(stderr, message)

目的：记录服务器运行日志。
输入：标准错误流、日志消息字符串。
核心功能：将日志信息打印到 stderr，避免与 stdout 中的业务数据混淆。
3. 执行流程
启动与初始化：程序从 if __name__ == "__main__": 启动，调用 main()。main() 绑定输入输出流，并向 stderr 打印 "MCP stdio server starting" 启动日志。
阻塞监听：进入 for line in stdin: 循环，程序阻塞等待客户端通过 stdin 发送数据。
解析与校验：读取到一行数据后，去除首尾空白。使用 json.loads 将其解析为 Python 字典，并传入 _handle_request。
路由与处理：
_handle_request 校验 JSON-RPC 格式。
若 method 为 initialize，调用 _initialize_result 生成握手成功信息，并包装成完整响应。
若 method 为通知（如 notifications/initialized），直接返回 None。
若格式错误或方法不存在，调用 _error_response 生成错误响应。
响应返回：main() 接收到 _handle_request 的返回值，如果不为 None，则调用 _write_message 将 JSON 字符串写入 stdout 并 flush。
异常兜底：如果在第 3、4 步中发生任何异常（如 JSON 解析失败），main() 会捕获异常，调用 _error_response 生成 "Internal error" 并返回给客户端。
优雅退出：当客户端关闭 stdin（发送 EOF）时，循环结束，打印 "MCP stdio server stopped" 日志，程序返回 0 正常退出。
4. 场景示例
场景：一个 AI 编程助手（客户端）需要连接到你的 Modular RAG 系统，以便调用 RAG 工具来查询代码库。

发起握手：AI 助手通过 stdio 启动该 Python 脚本，并发送第一句“暗号”（初始化请求）：
json
{"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{"protocolVersion":"2024-11-05"}}
服务端处理：
main 函数读到这行文本，解析后交给 _handle_request。
_handle_request 看到 method 是 "initialize"，调用 _initialize_result。
_initialize_result 返回包含服务器名称 "modular-rag-mcp-server" 和支持 tools 能力的字典。
服务端回应：main 函数将结果打包，通过 _write_message 写回 stdout：
json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"modular-rag-mcp-server","version":"0.1.0"}}}
确认握手：AI 助手收到响应后，发送一个通知表示初始化完成（不需要服务端回复）：
json
{"jsonrpc":"2.0", "method":"notifications/initialized"}
静默处理：_handle_request 识别出这是通知，返回 None。main 函数判断响应为空，不向 stdout 写入任何内容。
准备就绪：至此，双向通信通道建立完毕，AI 助手接下来就可以发送具体的工具调用请求（如查询某个函数的实现）了（注：当前代码为极简版，后续可在此框架上扩展具体的 tools 调用逻辑）。