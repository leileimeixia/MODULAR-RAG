# F2_jsonl_logger 学习笔记

## 1. 本阶段完成了什么

本阶段实现了结构化日志输出能力，让 F1 中生成的 trace 数据可以被写入 JSON Lines 文件。

简单说，F1 负责“把一次请求的过程整理成字典”，F2 负责“把这个字典一行一行写到日志文件里”。以后 Dashboard 或调试工具就可以读取 `logs/traces.jsonl`，看到每次查询或摄取的完整过程。

JSON Lines 的特点是：每一行都是一个完整 JSON 对象。例如：

```text
{"trace_id":"trace-1","trace_type":"query","stages":[]}
{"trace_id":"trace-2","trace_type":"ingestion","stages":[]}
```

这样写的好处是追加简单、读取方便，也适合后续按行解析历史记录。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/logger.py` | 增强日志模块，新增 JSONFormatter、get_trace_logger、write_trace |
| `src/core/trace/trace_collector.py` | 让 TraceCollector 支持可选持久化，把 trace 写入 JSONL 文件 |
| `tests/unit/test_jsonl_logger.py` | 测试 JSON 格式化、trace 写入、logger handler 去重、collector 持久化 |
| `DEV_SPEC.md` | 更新 F2 任务状态和总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 的任务进度记录 |

## 3. 核心调用关系

```text
业务流程
  -> 创建 TraceContext
  -> trace.record_stage(...)
  -> TraceCollector.collect(trace)
  -> trace.finish()
  -> trace.to_dict()
  -> write_trace(trace_dict)
  -> get_trace_logger()
  -> JSONFormatter
  -> 追加写入 logs/traces.jsonl
```

如果不通过 `TraceCollector`，也可以直接调用：

```text
write_trace(trace.to_dict(), log_file="logs/traces.jsonl")
```

F2 的重点是把 trace 数据从内存带到磁盘上。这样程序结束后，历史 trace 记录仍然保留。

## 4. 每个核心文件的作用

### 文件：`src/observability/logger.py`

* 主要职责：提供普通 logger 和结构化 trace logger。
* 关键函数 / 类：
  * `get_logger()`：保留原来的 stderr 普通日志能力，兼容已有代码。
  * `JSONFormatter`：把日志记录转换成一行 JSON 字符串。
  * `get_trace_logger()`：创建写入 JSON Lines 文件的 logger。
  * `write_trace()`：把一个 trace 字典追加写入日志文件。
  * `LoggerError`：当传入非法日志数据时抛出。
* 输入是什么：普通日志消息，或 trace 字典。
* 输出是什么：stderr 普通日志，或 JSONL 文件中的一行 trace 记录。
* 在项目中的作用：为后续 query/ingestion 链路的 trace 持久化提供统一出口。

### 文件：`src/core/trace/trace_collector.py`

* 主要职责：收集 trace，并可选地持久化。
* 本阶段修改点：
  * 新增 `trace_file` 参数，用来指定 JSONL 文件路径。
  * 新增 `persist` 参数，用来控制是否写入文件。
  * `collect()` 在保存内存记录后，如果 `persist=True`，会调用 `write_trace()`。
* 输入是什么：一个 `TraceContext`。
* 输出是什么：内存中的 `collector.traces`，以及可选的 JSONL 文件记录。
* 在项目中的作用：把 F1 的 trace 数据结构和 F2 的日志写入能力连接起来。

### 文件：`tests/unit/test_jsonl_logger.py`

* 主要职责：验证 JSON Lines 日志能力。
* 关键测试：
  * `JSONFormatter` 能把 dict message 格式化成 JSON。
  * `write_trace()` 会创建目录并追加一行 JSON。
  * `get_trace_logger()` 对同一个文件不会重复添加 handler。
  * `TraceCollector(persist=True)` 能把 trace 写入 JSONL 文件。
  * 非 dict 输入会被拒绝。
* 在项目中的作用：保证日志文件格式稳定，后续 Dashboard 才能安全读取。

## 5. 新手重点理解

F2 的关键是“结构化”。普通日志通常长这样：

```text
INFO: pipeline finished
```

这种日志人能看，但程序不好解析。结构化日志长这样：

```json
{"trace_id":"abc","trace_type":"query","total_elapsed_ms":120.5,"stages":[]}
```

这种日志既能给人看，也能被程序直接读取。后面的 Dashboard 就可以一行一行读取 `traces.jsonl`，把 query 历史、ingestion 历史、每个阶段耗时展示出来。

为什么使用 JSON Lines，而不是一个大 JSON 数组？因为日志是持续追加的。每次请求结束，只需要往文件末尾追加一行，不需要读取整个文件再改写。对于 trace 历史来说，这种格式简单又实用。

本阶段在 RAG 流程中的位置是“trace 持久化层”。它不负责业务计算，但负责把业务过程记录保存下来，让系统后续可以调试、分析和可视化。


# 整体结构与流程

文件定位
文件路径：d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\logger.py

作用与层级： 该文件属于项目中的 observability（可观测性）模块，处于系统的基础设施层/工具层。 核心职责： 在 RAG（检索增强生成）等复杂AI系统中，排查问题和复盘效果至关重要。该文件的核心职责是提供统一、结构化的日志记录能力。它不仅支持输出到控制台的常规运行日志，还提供将关键业务数据以 JSON Lines 格式持久化到文件的“追踪（Trace）”日志功能，方便后续的数据分析和系统调试。

函数拆解
1. get_logger(name: str = "modular_rag") -> logging.Logger
作用目的：获取一个用于输出到控制台（标准错误流）的常规日志记录器。
输入输出：输入日志器名称（字符串），输出配置好的 logging.Logger 对象。
核心功能：如果该名称的日志器还没有处理器，则为其添加一个控制台处理器，设置格式为 级别:名称:消息，并将日志级别设为 INFO。
2. class JSONFormatter(logging.Formatter)
作用目的：自定义日志格式化器，将日志内容转换为单行 JSON 字符串。
输入输出：输入 Python 原生的 LogRecord 对象，输出 JSON 格式的字符串。
核心功能：
如果传入的日志消息本身就是一个字典（dict），则直接将其序列化为 JSON。
如果传入的是普通字符串，则将其包装成包含 level、logger、message 三个字段的字典，再序列化为 JSON。
3. get_trace_logger(log_file, name) -> logging.Logger
作用目的：获取一个专门用于写入 JSON Lines 追踪日志的文件日志记录器。
输入输出：输入日志文件路径和日志器名称，输出配置好的文件 logging.Logger 对象。
核心功能：
自动创建日志文件所在的目录。
检查该日志器是否已经绑定了目标文件的处理器，防止重复添加。
为日志器添加文件处理器（FileHandler），并使用上面定义的 JSONFormatter 进行格式化。
关闭日志向上传播（propagate = False），避免追踪日志被打印到控制台或其他地方。
4. write_trace(trace_dict: dict, log_file) -> None
作用目的：对外提供的核心 API，用于将一条追踪记录追加写入到 JSON Lines 文件中。
输入输出：输入要记录的字典数据和日志文件路径，无返回值。
核心功能：
校验输入必须是字典类型，否则抛出 LoggerError。
调用 get_trace_logger 获取对应的文件日志器。
以 INFO 级别记录该字典。
立即刷新（flush） 文件处理器，确保数据实时写入磁盘，防止因程序崩溃导致日志丢失。
5. class LoggerError(ValueError)
作用目的：自定义异常类。
核心功能：当结构化日志的输入不合法时（例如 write_trace 传入了非字典类型），抛出此异常以便快速定位问题。
执行流程
该文件主要包含两条并行的日志执行链路：

链路一：常规控制台日志流程

业务代码调用 get_logger() 获取 logger 实例。
业务代码调用 logger.info("系统启动")。
Python 原生 logging 模块调用默认的 Formatter 格式化字符串。
StreamHandler 将格式化后的文本输出到控制台（stderr）。
链路二：追踪（Trace）日志流程

业务代码收集好需要追踪的数据，构建为字典，调用 write_trace(trace_dict)。
write_trace 校验字典合法性。
调用 get_trace_logger()，内部完成目录创建、Logger 获取、FileHandler 绑定及 JSONFormatter 设置。
调用 logger.info(trace_dict)。
JSONFormatter.format() 拦截记录，将字典转换为单行 JSON 字符串。
FileHandler 将 JSON 字符串写入指定的 .jsonl 文件。
write_trace 遍历 handlers 并执行 flush()，强制将缓冲区数据写入磁盘。
场景示例
业务场景：在 Modular RAG 系统中，记录一次“文档检索”的详细过程，以便后续分析检索准确率。

全流程串联：

系统启动：RAG 服务启动时，调用 logger = get_logger()，并打印 logger.info("RAG 服务已启动")，运维人员可以在控制台看到标准的启动提示。
触发检索：用户输入问题“如何配置阿里云 OSS？”，系统进入检索模块。为了复盘这次检索，系统构建了一个追踪字典：
python
trace_data = {
    "step": "retrieval",
    "query": "如何配置阿里云 OSS？",
    "top_k": 3,
    "retrieved_docs": ["doc_102.pdf", "doc_45.pdf", "doc_88.pdf"],
    "latency_ms": 125
}
写入追踪日志：检索模块调用 write_trace(trace_data)。
内部处理：
函数首先确认 trace_data 是个字典。
接着调用 get_trace_logger()，系统发现 logs/traces.jsonl 文件还不存在，于是自动创建 logs 目录和文件，并配置好 JSON 格式化器。
日志器将 trace_data 交给 JSONFormatter，转换为一行紧凑的 JSON 字符串：{"latency_ms": 125, "query": "如何配置...", "retrieved_docs": [...], ...}。
这行 JSON 被追加写入到 logs/traces.jsonl 文件中。
最后执行 flush()，确保这行数据立刻落盘。
后续分析：第二天，算法工程师直接读取 logs/traces.jsonl 文件，因为每一行都是标准的 JSON，可以直接用 Pandas 或 Python 脚本逐行解析，轻松统计出平均检索耗时、高频查询词等指标，从而优化 RAG 系统。