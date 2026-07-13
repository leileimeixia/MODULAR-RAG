# C14_ingestion_pipeline 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `IngestionPipeline`，它把阶段 C 前面已经完成的模块串成一条完整的摄取链路。

在 C1-C13 中，我们已经分别实现了核心数据类型、文件完整性检查、PDF Loader、DocumentChunker、Transform、Dense/Sparse 编码、BM25 索引、向量写入和图片存储。C14 的任务不是再做一个新的底层能力，而是把这些能力按正确顺序组织起来。

当前 MVP 编排顺序是：

```text
integrity
  -> load
  -> image_store
  -> split
  -> transform
  -> encode
  -> vector_upsert
  -> bm25_index
  -> mark_success
```

如果某一步失败，Pipeline 会抛出带阶段名的 `IngestionPipelineError`，并调用 integrity checker 记录失败。这样排查问题时可以直接知道是 load、split、encode 还是 store 阶段出错。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/pipeline.py` | 实现摄取主编排器 `IngestionPipeline`、结果对象和阶段异常 |
| `src/ingestion/__init__.py` | 对外导出 `IngestionPipeline`、`IngestionPipelineError`、`IngestionResult` |
| `tests/integration/test_ingestion_pipeline.py` | 用 fake 组件验证完整编排、skip、force 和失败标记 |
| `DEV_SPEC.md` | 将 C14 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> IngestionPipeline(...)
  -> run(path, collection, force, trace)
      -> integrity_checker.compute_sha256(path)
      -> integrity_checker.should_skip(file_hash)
      -> loader.load(path)
      -> image_storage.save_image(...)
      -> chunker.split_document(document)
      -> transform.transform(chunks)
      -> batch_processor.process(chunks)
      -> vector_upserter.upsert(records)
      -> bm25_indexer.add(records)
      -> integrity_checker.mark_success(...)
      -> 返回 IngestionResult
```

如果 `should_skip()` 返回 True，并且没有传 `force=True`：

```text
compute_sha256
  -> should_skip == True
  -> 记录 ingestion_skip
  -> 不再执行 load/split/encode/store
  -> 返回 skipped=True 的 IngestionResult
```

如果某个阶段失败：

```text
某阶段抛异常
  -> _stage 包装为 IngestionPipelineError
  -> mark_failed(file_hash, error)
  -> 向上抛出清晰异常
```

## 4. 每个核心文件的作用

### 文件：`src/ingestion/pipeline.py`

- 主要职责：串行执行完整 ingestion 流程，并统一处理跳过、失败、成功结果。
- 关键函数 / 类：
  - `IngestionPipeline`：摄取主入口。
  - `run(path, collection, force, trace)`：执行一次完整摄取。
  - `IngestionResult`：返回一次摄取的摘要信息。
  - `IngestionPipelineError`：阶段失败时抛出的可读异常。
  - `_stage(name, action, trace)`：统一包装每个阶段的日志和异常。
  - `_store_document_images(...)`：保存 Document 中已有图片引用。
- 输入是什么：
  - 文件路径 `path`
  - collection 名称
  - `force` 是否强制重新摄取
  - 可选 `TraceContext`
  - 可注入 loader/chunker/transforms/encoder/storage 等组件
- 输出是什么：
  - `IngestionResult`
  - 成功时写入向量库、BM25 索引、图片存储和 integrity success 记录
- 在项目中的作用：
  - 作为离线摄取链路的统一入口，后续 `scripts/ingest.py` 和 Dashboard 都可以调用它。

### 文件：`src/ingestion/__init__.py`

- 主要职责：暴露 ingestion 包的公共入口。
- 关键函数 / 类：
  - `IngestionPipeline`
  - `IngestionPipelineError`
  - `IngestionResult`
- 输入是什么：无直接业务输入。
- 输出是什么：包级导入入口。
- 在项目中的作用：
  - 让外部代码可以通过 `from ingestion import IngestionPipeline` 使用摄取管线。

### 文件：`tests/integration/test_ingestion_pipeline.py`

- 主要职责：验证管线编排是否能把所有步骤按顺序串起来。
- 关键测试：
  - 完整跑通 fake ingestion 链路，最终写入 vector 和 BM25。
  - integrity 判断已处理时会 skip，不调用 loader。
  - `force=True` 可以忽略 skip，强制继续摄取。
  - loader 失败时抛出带阶段名的异常，并记录 mark_failed。
- 输入是什么：
  - 临时 PDF 文件
  - fake loader、chunker、transform、batch processor、vector upserter、BM25 indexer、image storage
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 保证 Pipeline 的重点是“编排正确”，而不是依赖真实外部模型或数据库。

## 5. 新手重点理解

Pipeline 是“总控台”，不是具体算法。

前面的模块各自解决一个小问题：

- Loader 负责把文件变成 Document。
- Chunker 负责把 Document 切成 Chunk。
- Transform 负责清洗、增强、图片描述等。
- BatchProcessor 负责 dense/sparse 编码。
- VectorUpserter 负责写入向量库。
- BM25Indexer 负责写入关键词索引。
- ImageStorage 负责保存图片。
- IntegrityChecker 负责判断是否重复处理。

如果没有 Pipeline，调用方就必须自己记住这些步骤的顺序，还要自己处理失败、跳过、成功记录。这样很容易漏掉某一步。`IngestionPipeline` 把这些顺序固定下来，外部只需要调用 `run()`。

为什么支持依赖注入？因为单元/集成测试不应该真的调用 OpenAI、Chroma 或文件解析器。测试中注入 fake 组件，就能稳定验证“编排是否正确”。生产环境则可以少传或不传组件，让 Pipeline 使用默认实现。

为什么 transform 默认是空列表？因为 Transform 里可能包含 LLM/Vision 调用。C14 的目标是先把链路串起来，避免默认情况下误触发真实模型调用。后续入口脚本或配置层可以显式加入 `ChunkRefiner`、`MetadataEnricher`、`ImageCaptioner`。

为什么失败异常要带阶段名？因为长 pipeline 里最怕只看到一个模糊的错误。现在如果 loader 失败，会看到 `pipeline failed during load`，如果 encode 失败，会看到 `pipeline failed during encode`。这能大幅减少定位时间。

这一阶段的核心价值是：阶段 C 的零散能力第一次被组织成一条可运行的 ingestion 主链路，为下一步命令行入口 `scripts/ingest.py` 做准备。

# 整体架构与流程

# 文件定位
文件路径：src/ingestion/pipeline.py

项目层级：该文件位于 ingestion（数据摄入）模块中，是整个 RAG 系统数据摄入流程的总调度器，处于 ingestion 模块的最顶层。

核心职责：

负责将原始文档（如 PDF）经过一系列标准化阶段处理后，最终写入向量数据库和 BM25 索引
串联完整性校验、文档加载、图片存储、文本切分、变换处理、向量化编码、向量写入、BM25 索引等所有阶段
提供统一的错误处理和追踪（trace）记录能力

# 函数拆解
1. IngestionPipelineError（类）
作用：自定义异常类，当流水线中任意阶段失败时抛出
继承：RuntimeError
2. IngestionResult（数据类）
作用：封装一次摄入运行的结果摘要
字段：
file_hash：文件哈希值
document_id：文档 ID
skipped：是否跳过（文件未变化）
chunk_count：切分后的块数量
record_count：编码后的记录数量
vector_ids：写入向量库的 ID 列表
image_count：存储的图片数量
trace：追踪上下文
3. IngestionPipeline.__init__
输入：各种可选组件（integrity_checker、loader、chunker 等）和 settings 配置
输出：初始化后的 pipeline 实例
核心功能：依赖注入，如果未传入组件则使用默认实现；部分组件（如 chunker）必须有 settings 才能创建
4. IngestionPipeline.run
输入：
path：源文件路径
collection：目标集合名称（默认 "default"）
force：是否强制重新处理（忽略哈希跳过逻辑）
trace：追踪上下文
输出：IngestionResult 对象
核心功能：按顺序执行所有摄入阶段，包括完整性校验、加载、图片存储、切分、变换、编码、向量写入、BM25 索引，并记录成功或失败状态
5. IngestionPipeline._stage
输入：阶段名称、可执行动作（lambda）、trace 上下文
输出：动作执行结果
核心功能：统一包装每个阶段的执行，添加日志记录和异常捕获，失败时抛出 IngestionPipelineError
6. IngestionPipeline._store_document_images
输入：document 对象、collection 名称、file_hash、trace
输出：成功存储的图片数量（int）
核心功能：遍历文档中的所有图片，将存在的图片文件保存到图片存储中
7. _require_settings（模块级函数）
输入：settings 配置对象、工厂函数
输出：工厂函数创建的组件实例
核心功能：检查 settings 是否存在，不存在则抛出异常；存在则用 settings 调用工厂函数创建组件

# 执行流程
┌─────────────────────────────────────────────────────────────┐
│                    IngestionPipeline.run()                    │
├─────────────────────────────────────────────────────────────┤
│  1. 计算文件 SHA256 哈希 (integrity stage)                    │
│                    ↓                                          │
│  2. 检查是否应跳过 (should_skip)                              │
│     ├── 是 → 返回 skipped=True 的结果                         │
│     └── 否 → 继续执行                                        │
│                    ↓                                          │
│  3. 加载文档 (load stage) → PdfLoader.load()                 │
│                    ↓                                          │
│  4. 存储图片 (image_store stage) → _store_document_images()  │
│                    ↓                                          │
│  5. 切分文档 (split stage) → DocumentChunker.split_document()│
│                    ↓                                          │
│  6. 执行变换 (transform stage) → 遍历 transforms 列表        │
│                    ↓                                          │
│  7. 编码向量化 (encode stage) → BatchProcessor.process()     │
│                    ↓                                          │
│  8. 写入向量库 (vector_upsert stage) → VectorUpserter.upsert()│
│                    ↓                                          │
│  9. 构建 BM25 索引 (bm25_index stage) → BM25Indexer.add()    │
│                    ↓                                          │
│  10. 标记成功 (mark_success) + 记录完成 trace                 │
│                    ↓                                          │
│  11. 返回 IngestionResult                                    │
│                                                              │
│  [异常处理] 任意阶段失败 → mark_failed + 抛出异常             │
└─────────────────────────────────────────────────────────────┘

# 场景示例
业务场景：某企业规章制度问答系统，需要将新发布的《员工手册 v2.0.pdf》摄入到 RAG 系统中。

全流程串联：

完整性校验：系统计算该 PDF 文件的 SHA256 哈希值，发现与上次处理的哈希不同（文件已更新），继续执行

文档加载：PdfLoader 读取 PDF 文件，提取出文本内容、页面信息以及嵌入的图片（如公司组织架构图），生成一个 Document 对象

图片存储：遍历文档中的图片，将组织架构图保存到图片存储系统中，记录 image_count = 1

文本切分：DocumentChunker 将长篇的员工手册按段落和语义边界切分成 50 个文本块（chunks）

变换处理：如果有配置变换器（如敏感信息脱敏），对 50 个 chunks 逐一处理

向量化编码：BatchProcessor 调用 Embedding 模型，将 50 个文本块转换为 50 条向量记录（records）

向量写入：VectorUpserter 将 50 条向量记录写入 Milvus 向量数据库，返回 50 个 vector_ids

BM25 索引：BM25Indexer 将文本内容写入 BM25 索引，支持关键词检索

标记成功：在 SQLite 中记录该文件哈希已成功处理，下次如果文件未变化则直接跳过

返回结果：返回 IngestionResult，包含 chunk_count=50、record_count=50、image_count=1 等信息

异常场景：如果在第 6 步编码阶段 Embedding 服务宕机，_stage 方法会捕获异常，调用 mark_failed 记录失败状态，并抛出 IngestionPipelineError，便于后续重试或告警。