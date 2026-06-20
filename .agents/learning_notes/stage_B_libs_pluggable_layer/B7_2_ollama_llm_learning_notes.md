# B7.2_ollama_llm 学习笔记

## 1. 本阶段完成了什么

本阶段给项目新增了 Ollama LLM 后端。Ollama 是一个常见的本地大模型服务，默认运行在 `http://localhost:11434`。这次实现后，项目可以通过 `LLMFactory` 根据配置创建 `OllamaLLM`，再用统一的 `chat(messages)` 方法调用本地模型。

这一步的意义是：项目不再只能接 OpenAI、Azure、DeepSeek 这些云端模型，也可以切换到本地模型。这样在没有网络、想降低成本、或希望数据不出本机时，RAG 系统也有可选后端。

在整个 RAG 流程中，`OllamaLLM` 仍然属于“模型能力层”。后续它可以被 Query、Rerank、Chunk 改写、回答生成等模块复用。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/llm/ollama_llm.py` | 实现 Ollama 本地 `/api/chat` provider |
| `src/libs/llm/llm_factory.py` | 注册 `ollama` provider，让工厂可以创建 `OllamaLLM` |
| `src/libs/llm/__init__.py` | 对外导出 `OllamaLLM` |
| `tests/unit/test_ollama_llm.py` | 使用 mock HTTP 测试 Ollama 请求、响应和错误处理 |
| `DEV_SPEC.md` | 标记 B7.2 完成，更新阶段进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> LLMFactory.create(settings)
  -> settings.llm.provider == "ollama"
  -> 创建 OllamaLLM
  -> OllamaLLM.chat(messages)
  -> POST http://localhost:11434/api/chat
  -> 解析 response["message"]["content"]
  -> 返回 assistant 文本
```

Ollama 的请求数据大致这样流动：

```text
messages
  -> 校验 role/content
  -> 组装 model、messages、stream=False、options
  -> 发送到 /api/chat
  -> 从 message.content 取出回答文本
```

## 4. 每个核心文件的作用

### 文件：`src/libs/llm/ollama_llm.py`

* 主要职责：实现 Ollama 的本地聊天模型调用。
* 关键类：`OllamaLLM`。
* 关键函数：
  * `_validate_messages()`：校验消息列表不能为空，并且每条消息都要有 `role` 和字符串类型的 `content`。
  * `_parse_ollama_response()`：从 Ollama 返回结果里取出 `message.content`。
* 输入是什么：`messages: list[dict[str, str]]`。
* 输出是什么：Ollama assistant 的文本回答。
* 在项目中的作用：提供本地 LLM 后端，让项目可以不依赖云端模型。

### 文件：`src/libs/llm/llm_factory.py`

* 主要职责：把 provider 名称映射到具体 LLM 实现。
* 本阶段新增逻辑：`LLMFactory.register("ollama", OllamaLLM)`。
* 输入是什么：完整 `Settings` 或单独的 `LLMSettings`。
* 输出是什么：`OllamaLLM` 实例。
* 在项目中的作用：让配置里的 `provider: ollama` 生效。

### 文件：`src/libs/llm/__init__.py`

* 主要职责：统一导出 LLM 模块对外可用的类。
* 本阶段新增导出：`OllamaLLM`。
* 在项目中的作用：让其它代码可以通过 `from libs.llm import OllamaLLM` 使用该实现。

### 文件：`tests/unit/test_ollama_llm.py`

* 主要职责：验证 Ollama provider 的行为。
* 覆盖点：
  * `LLMFactory` 能创建 `OllamaLLM`。
  * 请求会发送到 `/api/chat`。
  * 请求体包含 `model`、`messages`、`stream: False` 和 `options`。
  * `OLLAMA_BASE_URL` 可以覆盖默认地址。
  * 输入格式错误会报清晰异常。
  * HTTP 错误、连接错误、响应结构错误都会被包装成 `LLMProviderError`。

## 5. 新手重点理解

这里最重要的是理解“同一个接口，不同后端”。

OpenAI、Azure、DeepSeek、Ollama 的真实 HTTP 接口并不完全一样，但项目内部不希望到处关心这些差异。所以我们让它们都实现 `BaseLLM.chat()`。这样上层业务代码只管“我要问模型一个问题”，不用管背后模型在哪里运行。

Ollama 和 OpenAI-compatible provider 最大的不同是响应格式。OpenAI 风格通常从 `choices[0].message.content` 里取文本，而 Ollama 的 `/api/chat` 是从 `message.content` 里取文本。所以 Ollama 单独有自己的 `_parse_ollama_response()`。

为什么用 `OLLAMA_BASE_URL`？因为默认本机地址是 `http://localhost:11434`，但有的人可能把 Ollama 跑在别的端口、Docker 容器、局域网机器上。环境变量可以在不改代码的情况下切换地址。

测试依然使用 mock HTTP，因为单元测试不应该要求用户本机真的启动 Ollama。这样测试只验证代码逻辑，不依赖外部服务。
