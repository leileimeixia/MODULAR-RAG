# B7.3_openai_azure_embedding 学习笔记

## 1. 本阶段完成了什么

本阶段给项目新增了 OpenAI 和 Azure OpenAI 的 Embedding 后端。Embedding 的作用是把文本转换成向量，后续文档检索时就可以用向量相似度来找到最相关的内容。

在 RAG 项目里，Embedding 是非常核心的一环：文档摄取时要把 chunk 转成向量存入向量库；用户查询时也要把 query 转成向量，再去向量库里查相似内容。本阶段就是把这个“文本转向量”的外部服务调用能力补上。

这次实现复用了 OpenAI-compatible 的思路：OpenAI 和 Azure OpenAI 的 embedding API 格式很接近，所以抽了一个通用的 `OpenAICompatibleEmbedding`，再分别实现 `OpenAIEmbedding` 和 `AzureEmbedding`。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/embedding/openai_embedding.py` | 实现 OpenAI-compatible Embedding 通用逻辑和 OpenAI provider |
| `src/libs/embedding/azure_embedding.py` | 实现 Azure OpenAI Embedding provider |
| `src/libs/embedding/embedding_factory.py` | 注册 `openai`、`azure`、`azure-openai` provider |
| `src/libs/embedding/__init__.py` | 对外导出新增的 Embedding 类和异常类型 |
| `tests/unit/test_embedding_providers_smoke.py` | 使用 mock HTTP 测试 OpenAI/Azure Embedding provider |
| `DEV_SPEC.md` | 标记 B7.3 完成，更新阶段进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 阶段进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> EmbeddingFactory.create(settings)
  -> 根据 settings.embedding.provider 选择 provider
  -> OpenAIEmbedding / AzureEmbedding
  -> OpenAICompatibleEmbedding.embed(texts)
  -> 组装 HTTP 请求
  -> 调用 embeddings endpoint
  -> 解析 response["data"][i]["embedding"]
  -> 返回 list[list[float]]
```

数据流可以理解为：

```text
文本列表 texts
  -> 校验不能为空、每项必须是字符串
  -> 加上 model、input、dimensions
  -> 发给 OpenAI 或 Azure Embedding API
  -> 从 data 里取出每条 embedding
  -> 转成 float 向量列表
```

## 4. 每个核心文件的作用

### 文件：`src/libs/embedding/openai_embedding.py`

* 主要职责：实现 OpenAI-compatible Embedding 的通用 HTTP 调用逻辑。
* 关键类：
  * `EmbeddingProviderError`：统一表示 embedding provider 调用失败。
  * `OpenAIEmbeddingConfig`：保存 endpoint、认证 header、超时时间等配置。
  * `OpenAICompatibleEmbedding`：真正执行请求、校验输入、解析响应。
  * `OpenAIEmbedding`：OpenAI 官方 embedding provider。
* 输入是什么：`texts: list[str]`。
* 输出是什么：`list[list[float]]`，也就是一批文本对应的一批向量。
* 在项目中的作用：提供 OpenAI 官方 embedding 能力，也作为 Azure provider 的共用基础。

### 文件：`src/libs/embedding/azure_embedding.py`

* 主要职责：适配 Azure OpenAI 的 embedding URL 和认证方式。
* 关键类：`AzureEmbedding`。
* 输入是什么：`EmbeddingSettings`，其中 `model` 会被当作 Azure deployment 名称。
* 输出是什么：继承自 `OpenAICompatibleEmbedding.embed()` 的向量列表。
* 在项目中的作用：让项目可以切换到 Azure OpenAI 的 embedding 服务。

### 文件：`src/libs/embedding/embedding_factory.py`

* 主要职责：根据配置创建具体 embedding provider。
* 本阶段新增注册：
  * `EmbeddingFactory.register("openai", OpenAIEmbedding)`
  * `EmbeddingFactory.register("azure", AzureEmbedding)`
  * `EmbeddingFactory.register("azure-openai", AzureEmbedding)`
* 输入是什么：完整 `Settings` 或单独的 `EmbeddingSettings`。
* 输出是什么：某个 `BaseEmbedding` 子类实例。
* 在项目中的作用：把 `config/settings.yaml` 里的 provider 配置转换成可用对象。

### 文件：`src/libs/embedding/__init__.py`

* 主要职责：统一导出 embedding 模块对外可用的类。
* 本阶段新增导出：
  * `OpenAIEmbedding`
  * `AzureEmbedding`
  * `OpenAICompatibleEmbedding`
  * `EmbeddingProviderError`
* 在项目中的作用：让其它模块可以通过 `from libs.embedding import OpenAIEmbedding` 这类方式使用。

### 文件：`tests/unit/test_embedding_providers_smoke.py`

* 主要职责：用 mock HTTP 验证 OpenAI 和 Azure Embedding provider。
* 覆盖点：
  * `EmbeddingFactory` 能创建 OpenAI / Azure provider。
  * OpenAI 请求体包含 `model`、`input`、`dimensions`。
  * Azure URL 包含 deployment 和 api-version。
  * Azure 使用 `api-key` header。
  * 空输入、非字符串输入、空字符串输入会报错。
  * HTTP 错误不会泄露 API Key。
  * 响应格式错误会报清晰异常。

## 5. 新手重点理解

Embedding 可以理解成“把文字变成一串数字坐标”。两段文字越相似，它们的向量通常越接近。RAG 系统就是靠这个能力，把用户问题和文档 chunk 放到同一个向量空间里比较相似度。

为什么要有 `BaseEmbedding` 和 `EmbeddingFactory`？因为项目不应该和某一个 embedding 服务绑死。今天可以用 OpenAI，明天可以换 Azure，后面还可以换 Ollama、本地模型或其它服务。上层代码只调用 `embed(texts)`，不用关心背后是哪家 provider。

为什么 OpenAI 和 Azure 要共用 `OpenAICompatibleEmbedding`？因为它们核心请求和响应结构很像：发送 `input`，返回 `data[].embedding`。不同点主要是 URL 和认证 header。把共同逻辑抽出来，可以避免重复实现输入校验、HTTP 调用、响应解析。

为什么要校验空输入？因为 embedding 是批量接口，如果传空列表或空字符串，后续向量库写入、检索流程都可能出现难排查的问题。这里提前报清晰错误，可以让问题在源头暴露。

本阶段在 RAG 流程中的位置是“向量化”。它连接了文本处理和向量检索：文档 chunk 先经过 embedding，再进入向量库；用户 query 也会经过 embedding，再去做相似度搜索。
