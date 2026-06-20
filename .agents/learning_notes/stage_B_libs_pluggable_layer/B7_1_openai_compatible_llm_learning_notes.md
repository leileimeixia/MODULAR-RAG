# B7.1_openai_compatible_llm 学习笔记

## 1. 本阶段完成了什么

本阶段给项目补上了 OpenAI-compatible LLM 的默认实现。简单说，就是让项目不再只有 `BaseLLM` 和 `LLMFactory` 这种“接口骨架”，而是可以真正根据配置创建 OpenAI、Azure OpenAI、DeepSeek 这些聊天模型客户端。

这些模型都遵循类似 OpenAI Chat Completions 的请求格式，所以本阶段先抽出一个通用的 `OpenAICompatibleLLM`，再让 OpenAI、Azure、DeepSeek 分别继承或复用它。

在整个 RAG 项目中，LLM 位于生成与文本理解能力层。后续它会被用于回答生成、Chunk 改写、图片说明、Rerank 等需要大模型参与的环节。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/llm/openai_llm.py` | 实现通用 OpenAI-compatible HTTP 客户端和 OpenAI provider |
| `src/libs/llm/azure_llm.py` | 实现 Azure OpenAI provider，负责拼接 Azure 特有的 deployment URL |
| `src/libs/llm/deepseek_llm.py` | 实现 DeepSeek provider，复用 OpenAI-compatible 请求逻辑 |
| `src/libs/llm/llm_factory.py` | 默认注册 `openai`、`azure`、`azure-openai`、`deepseek` provider |
| `src/libs/llm/__init__.py` | 对外导出新增的 LLM 类和异常类型 |
| `tests/unit/test_llm_providers_smoke.py` | 使用 mock HTTP 验证 provider 路由、请求 shape、错误处理 |
| `DEV_SPEC.md` | 标记 B7.1 完成，更新阶段进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 的阶段进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> LLMFactory.create(settings)
  -> 根据 settings.llm.provider 选择 provider
  -> OpenAILLM / AzureLLM / DeepSeekLLM
  -> OpenAICompatibleLLM.chat(messages)
  -> 组装 HTTP 请求
  -> 解析 Chat Completions 响应
  -> 返回 assistant 文本
```

数据流可以理解为：

```text
messages 列表
  -> 校验 role/content
  -> 加上 model、temperature、max_tokens
  -> 发给兼容 OpenAI 格式的接口
  -> 从 choices[0].message.content 取出文本
```

## 4. 每个核心文件的作用

### 文件：`src/libs/llm/openai_llm.py`

* 主要职责：提供通用的 OpenAI-compatible 聊天模型客户端。
* 关键类：
  * `LLMProviderError`：统一包装 provider 调用失败。
  * `OpenAICompatibleConfig`：描述 endpoint、认证 header、超时时间。
  * `OpenAICompatibleLLM`：真正执行请求、校验输入、解析响应。
  * `OpenAILLM`：OpenAI 官方接口的具体 provider。
* 输入是什么：`messages: list[dict[str, str]]`，每条消息包含 `role` 和 `content`。
* 输出是什么：模型返回的 assistant 文本，也就是字符串。
* 在项目中的作用：作为 OpenAI 风格 LLM 后端的基础实现。

### 文件：`src/libs/llm/azure_llm.py`

* 主要职责：适配 Azure OpenAI 的 URL 和认证方式。
* 关键类：`AzureLLM`。
* 输入是什么：`LLMSettings`，其中 `model` 会被当作 Azure deployment 名称。
* 输出是什么：继承自 `OpenAICompatibleLLM.chat()` 的文本结果。
* 在项目中的作用：让同一套 LLM 抽象可以切换到 Azure OpenAI。

### 文件：`src/libs/llm/deepseek_llm.py`

* 主要职责：适配 DeepSeek 的 OpenAI-compatible API。
* 关键类：`DeepSeekLLM`。
* 输入是什么：`LLMSettings` 和聊天消息。
* 输出是什么：DeepSeek 返回的 assistant 文本。
* 在项目中的作用：提供另一个兼容后端，验证架构的可替换性。

### 文件：`src/libs/llm/llm_factory.py`

* 主要职责：根据配置创建具体 LLM provider。
* 关键逻辑：
  * `LLMFactory.register("openai", OpenAILLM)`
  * `LLMFactory.register("azure", AzureLLM)`
  * `LLMFactory.register("deepseek", DeepSeekLLM)`
* 输入是什么：完整 `Settings` 或单独的 `LLMSettings`。
* 输出是什么：某个 `BaseLLM` 子类实例。
* 在项目中的作用：把“配置驱动切换模型后端”落到代码里。

### 文件：`tests/unit/test_llm_providers_smoke.py`

* 主要职责：用 mock HTTP 测试 provider 行为，不访问真实网络。
* 覆盖点：
  * 工厂能创建 OpenAI、Azure、DeepSeek。
  * 请求体包含 `model`、`messages`、`temperature`、`max_tokens`。
  * Azure URL 会包含 deployment 和 api-version。
  * 错误信息不会泄露 API Key。
  * 响应 shape 错误时能清晰报错。

## 5. 新手重点理解

本阶段最重要的是理解“接口”和“实现”的关系。

`BaseLLM` 只规定所有大模型都要有 `chat(messages)` 方法，但它不关心背后到底是 OpenAI、Azure 还是 DeepSeek。`LLMFactory` 负责根据配置选择具体实现。这样后续业务代码只需要调用 `BaseLLM.chat()`，不用到处写 `if provider == "openai"` 之类的判断。

为什么要抽 `OpenAICompatibleLLM`？因为 OpenAI、Azure OpenAI、DeepSeek 的聊天接口格式很像：都是发送 messages，然后从返回值里取 `choices[0].message.content`。把共同逻辑集中到一个类里，可以减少重复代码。不同 provider 只需要提供自己的 endpoint 和认证方式。

为什么测试里要 mock HTTP？因为单元测试要快、稳定、可重复。如果测试真的访问 OpenAI 或 Azure，就会依赖网络、API Key、额度和服务状态。mock HTTP 可以只验证“代码是否组装了正确请求、能否正确解析响应”，不会产生真实调用成本。

在 RAG 流程里，这个模块属于“模型能力层”。它现在还没有直接串进完整问答链路，但后面的 Query、Rerank、Image Caption、Answer Generation 都会依赖这层能力。
