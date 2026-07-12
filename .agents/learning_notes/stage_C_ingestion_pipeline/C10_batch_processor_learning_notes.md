# C10_batch_processor 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `BatchProcessor`，它的作用是把一批 `Chunk` 按固定大小拆成多个 batch，然后依次调用 `DenseEncoder` 和 `SparseEncoder`，最后把两边的结果合并成同一个 `ChunkRecord`。

在前两个阶段里：

- C8 的 `DenseEncoder` 负责生成 `dense_vector`，用于语义检索。
- C9 的 `SparseEncoder` 负责生成 `sparse_vector`，用于关键词/BM25 检索。

C10 则负责把这两个编码步骤组织起来。它不是新的编码算法，而是一个批处理编排层。

它在 RAG ingestion 流程中的位置是：

```text
List[Chunk]
  -> BatchProcessor
      -> 按 batch_size 分批
      -> DenseEncoder.encode(batch)
      -> SparseEncoder.encode(batch)
      -> 合并 dense_vector 和 sparse_vector
  -> List[ChunkRecord]
  -> VectorUpserter / BM25Indexer
```

这样做的好处是：后续 pipeline 不需要分别调用 dense 和 sparse 两套 encoder，只需要交给 `BatchProcessor`，就可以得到同时包含两类检索信息的标准记录。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/embedding/batch_processor.py` | 实现批处理编排，将 dense/sparse 编码结果合并 |
| `src/ingestion/embedding/__init__.py` | 对外导出 `BatchProcessor` 和 `BatchProcessorError` |
| `tests/unit/test_batch_processor.py` | 验证分批、顺序稳定、结果合并、异常处理和 trace 记录 |
| `DEV_SPEC.md` | 将 C10 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> BatchProcessor(batch_size, dense_encoder?, sparse_encoder?)
  -> process(chunks, trace?)
      -> 校验 chunks 都是 Chunk
      -> _batches(chunks, batch_size)
      -> 对每个 batch:
          -> dense_encoder.encode(batch, trace)
          -> sparse_encoder.encode(batch, trace)
          -> _merge_records(batch, dense_records, sparse_records)
      -> trace.record_stage("batch_processing")
  -> 返回合并后的 List[ChunkRecord]
```

`BatchProcessor` 的核心不是“算向量”，而是保证数据流动顺序正确：

```text
chunk-0, chunk-1, chunk-2, chunk-3, chunk-4
  -> batch_size=2
  -> [chunk-0, chunk-1], [chunk-2, chunk-3], [chunk-4]
  -> 编码后仍然按 chunk-0 到 chunk-4 的顺序返回
```

## 4. 每个核心文件的作用

### 文件：`src/ingestion/embedding/batch_processor.py`

- 主要职责：把 chunks 分批，调用 dense/sparse encoder，并把结果合并成完整的 `ChunkRecord`。
- 关键函数 / 类：
  - `BatchProcessor`：批处理编排入口。
  - `process(chunks, trace)`：执行分批、编码、合并和 trace 记录。
  - `BatchProcessorError`：批处理阶段的可读异常。
  - `_batches(chunks, batch_size)`：按 batch size 切分 chunks。
  - `_merge_records(batch, dense_records, sparse_records)`：校验两个 encoder 的输出数量和顺序，并合并向量。
- 输入是什么：
  - `list[Chunk]`
  - `batch_size`
  - 可选注入的 `dense_encoder`
  - 可选注入的 `sparse_encoder`
  - 可选 `trace`
- 输出是什么：
  - `list[ChunkRecord]`，每个 record 同时带有 `dense_vector` 和 `sparse_vector`
- 在项目中的作用：
  - 作为 ingestion embedding 阶段的统一编排层，为后续存储阶段提供完整编码结果。

### 文件：`src/ingestion/embedding/__init__.py`

- 主要职责：导出 embedding 阶段的公共类。
- 关键函数 / 类：
  - `BatchProcessor`
  - `BatchProcessorError`
  - 已有的 `DenseEncoder`、`SparseEncoder` 等
- 输入是什么：无直接业务输入。
- 输出是什么：包级导入入口。
- 在项目中的作用：
  - 让后续代码可以用 `from ingestion.embedding import BatchProcessor` 直接拿到批处理能力。

### 文件：`tests/unit/test_batch_processor.py`

- 主要职责：验证 `BatchProcessor` 的行为契约。
- 关键测试：
  - `batch_size=2` 时，5 个 chunks 被分成 `[2, 2, 1]` 三批。
  - 输出记录顺序和输入 chunks 顺序一致。
  - dense vector 和 sparse vector 会被合并到同一个 record。
  - 空输入返回空列表。
  - 非法 `batch_size` 会报错。
  - 非 `Chunk` 输入会报错。
  - dense/sparse encoder 返回数量不匹配时会报错。
  - encoder 返回的 id 顺序被打乱时会报错。
  - 支持 trace 记录 `batch_processing` 阶段。
- 输入是什么：
  - 测试构造的 `Chunk`
  - `FakeDenseEncoder`
  - `FakeSparseEncoder`
  - `TraceContext`
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 保证批处理不会悄悄打乱 chunk 顺序，也不会把 dense/sparse 向量合并到错误的记录上。

## 5. 新手重点理解

`BatchProcessor` 是一个“编排器”，不是一个“算法实现”。

`DenseEncoder` 和 `SparseEncoder` 各自负责一种编码结果。如果 pipeline 直接分别调用它们，就需要到处处理顺序、数量匹配和结果合并。这样代码会分散，也更容易出错。

把这些事情集中在 `BatchProcessor` 里，后续流程就简单很多：输入 chunks，拿到完整的 `ChunkRecord`。

为什么要 batch？因为 embedding 这类操作通常可以批量处理。一次处理多个文本，比一个文本调用一次更适合后续接入真实模型服务，也能减少网络请求次数。当前测试用的是 fake encoder，但结构已经为真实 provider 留好了位置。

为什么要检查 dense 和 sparse 的输出数量？因为如果输入 2 个 chunks，却只返回 1 条 dense record，继续合并就会把数据对错。这里提前抛出 `BatchProcessorError`，能让问题停在最容易定位的位置。

为什么还要检查 id 顺序？因为即使数量一样，如果 encoder 把顺序打乱了，也可能把 `chunk-0` 的 dense vector 合并到 `chunk-1` 上。RAG 系统里这种错误很隐蔽，后面检索结果会变得奇怪。所以本阶段明确要求 encoder records 必须保持 chunk ids 和顺序。

这一阶段的核心价值是：把 C8 的语义编码和 C9 的关键词编码组织成一个稳定的批处理入口，为 C11-C13 的存储阶段准备统一数据结构。

# lingma

## 文件定位
batch_processor.py 位于项目的 Ingestion（数据摄入）→ Embedding（向量化） 层级，是连接"文本分块"与"向量存储"之间的批处理编排模块。

它的核心职责是：

将大量 Chunk（文本块）按指定 batch_size 拆分成小批次；
对每个批次同时调用稠密编码器（Dense）和稀疏编码器（Sparse）；
将两种编码结果对齐合并为统一的 ChunkRecord，供下游向量数据库写入。
可以把它理解为"流水线调度员"——不负责具体编码，只负责分批、调度、校验、合并。

## 函数拆解
1. BatchProcessorError
作用：自定义异常类，继承自 ValueError。
触发场景：当批次大小非法、输入类型错误、编码器返回数量不匹配、ID 顺序错乱时抛出。
2. BatchProcessor.__init__
输入：batch_size（批次大小）、settings（配置）、dense_encoder、sparse_encoder（可选注入的编码器实例）。
功能：校验 batch_size > 0；若未传入编码器，则自动创建默认的 DenseEncoder 和 SparseEncoder。
输出：初始化完成的 BatchProcessor 实例。
3. BatchProcessor.process
输入：chunks（Chunk 列表）、trace（可选的追踪器，用于记录性能日志）。
功能：
校验输入是否为空、是否全为 Chunk 对象；
按 batch_size 分批；
对每批依次调用稠密/稀疏编码器；
调用 _merge_records 合并结果；
记录每批耗时；
若提供了 trace，将整体批处理信息写入追踪。
输出：合并后的 list[ChunkRecord]。
4. _batches（模块级私有函数）
输入：chunks 列表、batch_size。
功能：用列表切片将 chunks 等分为多个子列表。
输出：list[list[Chunk]]。
5. _merge_records（模块级私有函数）
输入：一个 batch 的 chunks、对应的 dense_records、sparse_records。
功能：
校验 dense/sparse 返回的记录数是否与 batch 大小一致；
逐条校验 ID 是否对齐（保证顺序不乱）；
将 dense_vector 和 sparse_vector 合并进同一个 ChunkRecord。
输出：list[ChunkRecord]。

## 执行流程
用户调用 BatchProcessor.process(chunks)
        │
        ▼
   校验 chunks 非空 & 类型合法
        │
        ▼
   _batches() 按 batch_size 切分
        │
        ▼
   ┌────┴────┐  对每个 batch 循环
   │         │
   ▼         ▼
dense_encoder.encode()   sparse_encoder.encode()
   │         │
   └────┬────┘
        ▼
   _merge_records()  校验数量 & ID 对齐 → 合并为 ChunkRecord
        │
        ▼
   记录本批耗时到 batch_details
        │
        ▼
   所有批次完成后，若 trace 存在 → trace.record_stage(...)
        │
        ▼
   返回 all_records
   
## 场景示例
假设你正在构建一个企业知识库 RAG 系统，用户上传了一份 50 页的产品手册，系统经过切分后得到 200 个 Chunk。

初始化：你创建 BatchProcessor(batch_size=32)，内部自动生成默认的稠密编码器（如 BGE-M3）和稀疏编码器（如 BM25/SPLADE）。
分批：_batches 把 200 个 chunk 切成 7 批（6 批 ×32 + 1 批 ×8）。
第一批处理：
dense_encoder.encode(batch_1) → 返回 32 条带 dense_vector 的记录；
sparse_encoder.encode(batch_1) → 返回 32 条带 sparse_vector 的记录；
_merge_records 检查数量都是 32、ID 一一对应，然后把同一个 chunk 的稠密向量和稀疏向量打包成一个 ChunkRecord。
循环：剩余 6 批重复上述过程，每批记录耗时（比如 0.8s、0.75s…）。
追踪：如果传入了 trace，最终会写出一条 batch_processing 日志，包含总 chunk 数、批次数、每批耗时——方便后续排查性能瓶颈。
返回：最终得到 200 条 ChunkRecord，每条同时拥有 dense_vector 和 sparse_vector，可以直接写入 Milvus / Elasticsearch 等支持混合检索的向量库。
这样，当用户提问"产品 A 的保修政策是什么？"时，系统就能同时用语义相似度（稠密）和关键词匹配（稀疏）进行混合检索，显著提升召回准确率。