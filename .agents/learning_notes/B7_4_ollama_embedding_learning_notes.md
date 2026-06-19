# B7.4_ollama_embedding 学习笔记

## 1. 本阶段完成了什么

本阶段给项目新增了 Ollama Embedding 后端。Ollama 可以在本机运行 embedding 模型，例如 `nomic-embed-text`、`mxbai-embed-large` 等。实现之后，项目可以通过 `EmbeddingFactory` 根据配置创建 `OllamaEmbedding`，然后用统一的 `embed(texts)` 方法把文本批量转换成向量。

这一步的意义是：Embedding 不再只能依赖 OpenAI 或 Azure，也可以切换到本地模型。这样在离线环境、隐私要求较高、或想减少 API 成本时，项目仍然可以完成文本向量化。

在整个 RAG 流程中，Ollama Embedding 属于“向量化”环节。文档 chunk 会先被它转换成向量，再写入向量库；用户 query 也会被转换成向量，再用于相似度检索。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/embedding/ollama_embedding.py` | 实现 Ollama 本地 `/api/embed` embedding provider |
| `src/libs/embedding/embedding_factory.py` | 注册 `ollama` provider，让工厂能创建 `OllamaEmbedding` |
| `src/libs/embedding/__init__.py` | 对外导出 `OllamaEmbedding` |
| `tests/unit/test_ollama_embedding.py` | 使用 mock HTTP 测试 Ollama embedding provider |
| `DEV_SPEC.md` | 标记 B7.4 完成，更新阶段进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 阶段进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> EmbeddingFactory.create(settings)
  -> settings.embedding.provider == "ollama"
  -> 创建 OllamaEmbedding
  -> OllamaEmbedding.embed(texts)
  -> POST http://localhost:11434/api/embed
  -> 解析 response["embeddings"]
  -> 返回 list[list[float]]
```

数据流可以理解为：

```text
文本列表 texts
  -> 校验不能为空、每项必须是非空字符串
  -> 组装 model 和 input
  -> 发送给 Ollama /api/embed
  -> 从 embeddings 里取出向量
  -> 转成 float 向量列表
```

## 4. 每个核心文件的作用

### 文件：`src/libs/embedding/ollama_embedding.py`

* 主要职责：实现 Ollama 本地 embedding 调用。
* 关键类：`OllamaEmbedding`。
* 关键函数：
  * `_validate_texts()`：校验输入文本列表。
  * `_parse_ollama_response()`：解析 Ollama 返回的 `embeddings` 字段。
* 输入是什么：`texts: list[str]`。
* 输出是什么：`list[list[float]]`，也就是每段文本对应的向量。
* 在项目中的作用：提供本地 embedding 能力，让后续 ingestion 和 retrieval 可以不用云端 embedding 服务。

### 文件：`src/libs/embedding/embedding_factory.py`

* 主要职责：根据 provider 名称创建具体 embedding 实现。
* 本阶段新增逻辑：`EmbeddingFactory.register("ollama", OllamaEmbedding)`。
* 输入是什么：完整 `Settings` 或单独的 `EmbeddingSettings`。
* 输出是什么：`OllamaEmbedding` 实例。
* 在项目中的作用：让配置里的 `provider: ollama` 生效。

### 文件：`src/libs/embedding/__init__.py`

* 主要职责：统一导出 embedding 模块对外可用的类。
* 本阶段新增导出：`OllamaEmbedding`。
* 在项目中的作用：让其它模块可以通过 `from libs.embedding import OllamaEmbedding` 使用该实现。

### 文件：`tests/unit/test_ollama_embedding.py`

* 主要职责：验证 Ollama embedding provider 的行为。
* 覆盖点：
  * `EmbeddingFactory` 能创建 `OllamaEmbedding`。
  * 默认 endpoint 是 `http://localhost:11434/api/embed`。
  * `OLLAMA_BASE_URL` 可以覆盖服务地址。
  * 请求体包含 `model` 和 `input`。
  * 输入为空、非字符串、空字符串时会报错。
  * HTTP 错误、连接失败、响应结构错误会被包装成 `EmbeddingProviderError`。
  * 非数字向量会被拒绝。

## 5. 新手重点理解

Ollama Embedding 和 Ollama LLM 的区别是：LLM 是“生成回答”，Embedding 是“生成向量”。LLM 返回的是自然语言文本；Embedding 返回的是一串数字。

为什么要用 `/api/embed`？这是 Ollama 新版用于批量 embedding 的接口。我们传入 `input: texts`，它返回 `embeddings`。这个接口天然适合 RAG，因为 RAG 摄取文档时通常要一次处理很多 chunk。

为什么不在代码里写死某个向量维度？因为不同 embedding 模型的维度不一样。例如一个模型可能是 768 维，另一个可能是 1024 维。这里的代码只负责把 Ollama 返回的向量整理成 `list[list[float]]`，具体维度由模型决定。

为什么要保留 `OLLAMA_BASE_URL`？默认地址适合本机开发，但如果 Ollama 跑在 Docker、远程机器或不同端口，就可以通过环境变量切换，不需要改代码。

本阶段在 RAG 流程中位于“文本向量化”位置，是后续向量检索的基础。
