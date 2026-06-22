# C1_core_types 学习笔记

## 1. 本阶段完成了什么

本阶段定义了项目后续 Ingestion、Retrieval、MCP Tools 都会共用的核心数据结构。

在 RAG 项目里，文档会经历很多阶段：加载、切块、向量化、存储、检索、返回结果。如果每个阶段都自己定义一套数据格式，后面很容易出现字段不一致、metadata 丢失、图片信息无法传递等问题。

所以 C1 的核心目标是先把最基础的数据契约定下来，包括：

* `Document`：完整文档。
* `Chunk`：从文档里切出来的文本片段。
* `ChunkRecord`：用于存储和检索的 chunk 记录，后续会挂载 dense/sparse 向量。
* `ImageRef`：文档中图片占位符和图片文件之间的映射信息。

这些类型都支持序列化成 dict/json，方便后续保存、传输和测试。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/core/types.py` | 定义核心数据契约和校验逻辑 |
| `src/core/__init__.py` | 统一导出核心类型，简化外部导入 |
| `tests/unit/test_core_types.py` | 测试核心类型的序列化、校验和图片 metadata 规范 |
| `DEV_SPEC.md` | 标记 C1 完成，更新阶段 C 进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 阶段进度 |

## 3. 核心调用关系

```text
Loader / Pipeline
  -> 创建 Document
  -> Document.metadata.images 记录图片信息
  -> Splitter / Chunker
  -> 创建 Chunk
  -> Encoder / Storage
  -> 创建 ChunkRecord
  -> VectorStore / BM25 / Retrieval 使用统一字段
```

数据流可以理解为：

```text
原始文件
  -> Document(id, text, metadata)
  -> Chunk(id, text, offsets, metadata)
  -> ChunkRecord(id, text, metadata, dense_vector, sparse_vector)
  -> 存储和检索模块
```

其中图片数据流是：

```text
Document.text 中出现 [IMAGE: image_id]
  -> metadata.images 记录 image_id、path、offset、page、position
  -> 后续 ImageCaptioner 可以根据 image_id 找到图片
  -> 生成 caption 后写回 chunk 或 metadata
```

## 4. 每个核心文件的作用

### 文件：`src/core/types.py`

* 主要职责：定义项目核心数据契约。
* 关键类：
  * `Document`：表示加载后的完整文档。
  * `Chunk`：表示文档切分后的片段。
  * `ChunkRecord`：表示可写入存储或用于检索的 chunk 记录。
  * `ImageRef`：表示图片引用信息。
  * `CoreTypeError`：表示核心类型校验失败。
* 关键函数：
  * `image_placeholder()`：生成统一格式 `[IMAGE: image_id]`。
  * `_validate_metadata()`：确保 metadata 至少包含 `source_path`。
  * `_metadata_images()`：规范化 `metadata.images`。
  * `_validate_dense_vector()` / `_validate_sparse_vector()`：校验向量字段。
* 输入是什么：文档文本、chunk 文本、metadata、向量字段等。
* 输出是什么：可序列化、字段稳定的数据对象。
* 在项目中的作用：给后续 C 阶段和 D 阶段提供统一数据语言。

### 文件：`src/core/__init__.py`

* 主要职责：统一导出 core 层公共类型。
* 本阶段新增导出：
  * `Document`
  * `Chunk`
  * `ChunkRecord`
  * `ImageRef`
  * `CoreTypeError`
  * `Metadata`
  * `DenseVector`
  * `SparseVector`
  * `image_placeholder`
* 在项目中的作用：让其它模块可以通过 `from core import Document, Chunk` 使用，而不必知道具体文件路径。

### 文件：`tests/unit/test_core_types.py`

* 主要职责：验证核心数据契约是否稳定。
* 覆盖点：
  * `Document` 可以稳定序列化成 dict/json。
  * `metadata.images` 可以接收 `ImageRef` 或 dict。
  * metadata 必须包含 `source_path`。
  * `Chunk` 会校验 offset。
  * `ChunkRecord` 可以保存 dense/sparse vector。
  * 非法向量会报 `CoreTypeError`。

## 5. 新手重点理解

这一步看起来只是“定义几个类”，但它非常关键。RAG 项目一旦进入完整链路，数据会在很多模块之间流动。如果没有统一契约，就会出现一个模块叫 `doc_id`，另一个模块叫 `document_id`，某个地方忘了带 `source_path`，后面调试会很痛苦。

为什么 `metadata.source_path` 必须存在？因为后续所有 chunk 都需要知道自己来自哪个原始文件。检索结果返回给用户时，也需要引用来源。

为什么要定义 `ImageRef`？因为项目支持多模态文档。图片本身不能直接进入普通文本检索，所以需要先在文本中放 `[IMAGE: image_id]` 占位符，再用 metadata 记录这个图片在哪里、对应哪个文件、出现在文本哪个位置。

为什么要有 `ChunkRecord`？`Chunk` 更偏“切分阶段的文本片段”，`ChunkRecord` 更偏“准备存储和检索的载体”。后续 dense vector、sparse vector 会挂到 `ChunkRecord` 上。

本阶段在 RAG 流程中的位置是“数据契约层”。它不是某一个具体处理步骤，而是整个 Ingestion 和 Retrieval 链路的共同语言。
