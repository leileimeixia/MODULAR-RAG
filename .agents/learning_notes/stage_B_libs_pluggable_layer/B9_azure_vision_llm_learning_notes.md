# B9_azure_vision_llm 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 Azure Vision LLM，也就是通过 Azure OpenAI 的多模态能力处理“文本 + 图片”输入。

前一阶段 B8 只定义了 `BaseVisionLLM` 抽象接口和工厂方法，本阶段则补上了具体 Azure 实现：`AzureVisionLLM`。它可以把图片路径或图片 bytes 转成 base64 data URL，然后组装成 Azure OpenAI Chat Completions 的多模态请求。

在 RAG 项目中，这个能力主要服务于后续图片描述生成。比如 PDF 中有图表、截图、流程图时，系统可以调用 Vision LLM 生成图片说明，再把说明注入 chunk 文本或 metadata 中，让图片内容也能被文本检索命中。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/llm/azure_vision_llm.py` | 实现 Azure Vision LLM provider |
| `src/libs/llm/llm_factory.py` | 注册 `azure` / `azure-openai` Vision provider |
| `src/libs/llm/__init__.py` | 对外导出 `AzureVisionLLM` |
| `tests/unit/test_azure_vision_llm.py` | 使用 mock HTTP 测试 Azure Vision 调用 |
| `DEV_SPEC.md` | 标记 B9 完成，更新阶段 B 进度为 100% |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 阶段进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> LLMFactory.create_vision_llm(settings)
  -> vision_llm.provider == "azure"
  -> 创建 AzureVisionLLM
  -> AzureVisionLLM.chat_with_image(text, image_path)
  -> 将图片转为 data URL
  -> 组装 Azure OpenAI vision chat 请求
  -> 发送 HTTP 请求
  -> 解析 choices[0].message.content
  -> 返回图片描述文本
```

数据流可以理解为：

```text
text + image bytes/path
  -> 读取图片 bytes
  -> 判断大小是否超过 max_image_size byte budget
  -> base64 编码
  -> 拼成 data:image/...;base64,...
  -> 放入 messages[0].content 的 image_url
  -> Azure 返回 caption
```

## 4. 每个核心文件的作用

### 文件：`src/libs/llm/azure_vision_llm.py`

* 主要职责：实现 Azure OpenAI Vision 调用。
* 关键类：
  * `AzureVisionLLM`：实现 `BaseVisionLLM.chat_with_image()`。
* 关键函数：
  * `chat_with_image()`：对外入口，发送多模态请求并返回文本。
  * `_image_to_data_url()`：把 bytes 或图片路径转成 base64 data URL。
  * `_parse_vision_response()`：解析 Azure 返回内容。
* 输入是什么：文本提示词和图片输入。
* 输出是什么：Vision LLM 返回的文字描述。
* 在项目中的作用：为后续图片描述生成模块提供 Azure 视觉理解能力。

### 文件：`src/libs/llm/llm_factory.py`

* 主要职责：注册 Azure Vision provider。
* 本阶段新增逻辑：
  * `LLMFactory.register_vision("azure", AzureVisionLLM)`
  * `LLMFactory.register_vision("azure-openai", AzureVisionLLM)`
* 输入是什么：`VisionLLMSettings` 或完整 `Settings`。
* 输出是什么：`AzureVisionLLM` 实例。
* 在项目中的作用：让配置里的 `vision_llm.provider: azure` 生效。

### 文件：`src/libs/llm/__init__.py`

* 主要职责：统一导出 LLM 模块公共类。
* 本阶段新增导出：`AzureVisionLLM`。
* 在项目中的作用：让其它模块可以通过 `from libs.llm import AzureVisionLLM` 使用该实现。

### 文件：`tests/unit/test_azure_vision_llm.py`

* 主要职责：用 mock HTTP 测试 Azure Vision LLM，不访问真实 Azure API。
* 覆盖点：
  * `LLMFactory.create_vision_llm()` 能创建 `AzureVisionLLM`。
  * bytes 图片输入能被转成 data URL。
  * 图片路径输入能被读取，并根据扩展名推断 mime type。
  * Azure endpoint 和 api-version 拼接正确。
  * HTTP 错误不会泄露敏感信息。
  * 连接错误、响应结构错误会给出清晰异常。
  * 超出 `max_image_size` byte budget 的图片会被拒绝。

## 5. 新手重点理解

Vision LLM 的核心价值是“把图片变成文字”。RAG 系统最终主要靠文本检索，所以图片里的信息必须先被描述成文本，才能进入后面的 embedding、vector store 和 retrieval 流程。

为什么要转成 data URL？因为 Azure OpenAI 的多模态请求可以在 `image_url.url` 中接收 base64 data URL。这样测试和本地文件处理都比较简单，不需要先把图片上传到公网 URL。

为什么本阶段没有真正做图片压缩？项目当前没有引入 Pillow 等图片处理依赖。为了保持环境轻量，本阶段先用 byte budget 做保护：图片太大就报错。后续 C7 或更靠近图片预处理的模块可以加入真正的压缩逻辑。

为什么要 mock HTTP？因为单元测试不应该依赖真实 Azure 服务、API Key 或网络状态。通过 mock HTTP，可以稳定验证请求结构、错误处理和响应解析。

本阶段完成后，阶段 B 的 Libs 可插拔层已经 100% 完成。也就是说，项目的核心可替换能力已经具备，后续阶段可以开始把这些能力串进 Ingestion 和 Retrieval 主流程。
