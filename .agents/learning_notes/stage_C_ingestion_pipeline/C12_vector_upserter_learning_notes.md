# C12_vector_upserter 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `VectorUpserter`，它负责把已经带有 `dense_vector` 的 `ChunkRecord` 转换成向量数据库能接收的 `VectorRecord`，然后调用 `BaseVectorStore.upsert()` 写入向量存储。

在前面的阶段里：

- C8 `DenseEncoder` 生成 `ChunkRecord.dense_vector`。
- C10 `BatchProcessor` 把 dense/sparse 编码结果合并成完整 `ChunkRecord`。
- C11 `BM25Indexer` 处理 sparse 路线。

C12 处理的是 dense 路线的存储落地：

```text
List[ChunkRecord] with dense_vector
  -> VectorUpserter
  -> List[VectorRecord]
  -> BaseVectorStore.upsert(...)
  -> ChromaStore / 其他向量数据库
```

这一阶段特别强调幂等性：同一个 chunk 重复写入时，应该使用同一个稳定 id，而不是产生重复数据。本实现直接使用 `ChunkRecord.id` 作为 `VectorRecord.id`，因此同一个 chunk 多次 upsert 会覆盖同一条记录。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/storage/vector_upserter.py` | 实现 `ChunkRecord` 到 `VectorRecord` 的转换，并调用向量存储 upsert |
| `src/ingestion/storage/__init__.py` | 对外导出 `VectorUpserter` 和 `VectorUpserterError` |
| `tests/unit/test_vector_upserter_idempotency.py` | 验证稳定 id、重复 upsert、批量顺序、metadata 映射和 trace |
| `DEV_SPEC.md` | 将 C12 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> VectorUpserter(settings?, vector_store?)
      -> 如果没有注入 vector_store:
          -> VectorStoreFactory.create(settings)
  -> upsert(records, trace?)
      -> 校验输入都是 ChunkRecord
      -> _to_vector_record(record)
          -> id = record.id
          -> text = record.text
          -> vector = record.dense_vector
          -> metadata = record.metadata + chunk_id
      -> vector_store.upsert(vector_records, trace)
      -> trace.record_stage("vector_upsert")
      -> 返回写入 ids
```

数据流可以理解成：

```text
ChunkRecord
  -> dense_vector 存在性校验
  -> VectorRecord
  -> BaseVectorStore.upsert()
  -> 向量数据库本地/远程存储
```

## 4. 每个核心文件的作用

### 文件：`src/ingestion/storage/vector_upserter.py`

- 主要职责：把 dense 编码结果写入向量存储，并保证重复写入的幂等性。
- 关键函数 / 类：
  - `VectorUpserter`：向量写入入口。
  - `upsert(records, trace)`：批量转换并写入向量存储。
  - `VectorUpserterError`：输入不符合写入要求时抛出的异常。
  - `_to_vector_record(record)`：把 `ChunkRecord` 转换成 `VectorRecord`。
- 输入是什么：
  - `list[ChunkRecord]`
  - 每个 record 必须有 `dense_vector`
  - 可选 `BaseVectorStore`
  - 可选 `trace`
- 输出是什么：
  - 写入成功的稳定 id 列表。
- 在项目中的作用：
  - 连接 ingestion 编码阶段和向量数据库存储阶段，为后续 dense retrieval 提供可查询数据。

### 文件：`src/ingestion/storage/__init__.py`

- 主要职责：暴露 storage 阶段的公共入口。
- 关键函数 / 类：
  - `VectorUpserter`
  - `VectorUpserterError`
  - 已有的 `BM25Indexer`
- 输入是什么：无直接业务输入。
- 输出是什么：包级导入入口。
- 在项目中的作用：
  - 让 pipeline 可以通过 `from ingestion.storage import VectorUpserter` 使用向量写入能力。

### 文件：`tests/unit/test_vector_upserter_idempotency.py`

- 主要职责：验证 `VectorUpserter` 的行为契约。
- 关键测试：
  - 同一个 chunk 重复 upsert 会返回相同 id。
  - 同一个 id 的新内容会替换旧内容。
  - 批量 upsert 会保持输入顺序。
  - `ChunkRecord` 会正确映射成 `VectorRecord`。
  - metadata 中会补充 `chunk_id`。
  - 空输入返回空列表。
  - 非 `ChunkRecord` 输入会报错。
  - 缺少 `dense_vector` 的 record 会报错。
  - 支持 trace 记录 `vector_upsert` 阶段。
- 输入是什么：
  - 测试构造的 `ChunkRecord`
  - `FakeVectorStore`
  - `TraceContext`
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 保证 dense route 的存储写入是稳定、可重复、可观测的。

## 5. 新手重点理解

`VectorUpserter` 的重点不是“怎么计算向量”，而是“怎么把已经算好的向量可靠地写入向量数据库”。

`ChunkRecord` 是 ingestion 内部的标准记录，它可以同时带有 `dense_vector` 和 `sparse_vector`。但是向量数据库的抽象层使用的是 `VectorRecord`，字段更聚焦：

```text
VectorRecord:
  id
  text
  vector
  metadata
```

所以 `VectorUpserter` 要做一次适配：把 `ChunkRecord.dense_vector` 放到 `VectorRecord.vector`，把 `ChunkRecord.text` 和 `metadata` 一起带过去。

为什么要强调幂等？因为真实项目里同一个文档可能会重复摄取。如果每次 upsert 都生成新 id，向量库里会出现大量重复 chunk，检索结果也会重复。这里使用稳定的 `ChunkRecord.id`，同一个 chunk 再次写入时就是替换，不会新增重复记录。

为什么 metadata 里额外加 `chunk_id`？因为有些后续流程可能只拿到 metadata，需要反查 chunk 标识。把 `chunk_id` 明确写进去，可以让后面的过滤、删除、调试更方便。

为什么支持注入 `vector_store`？测试时不应该真的启动 Chroma 或其他数据库，所以单元测试注入 `FakeVectorStore`。生产环境则可以不传 `vector_store`，由 `VectorStoreFactory.create(settings)` 根据配置创建真实后端。

这一阶段的核心价值是：让 dense 检索路线从“有向量”推进到“向量已可靠写入存储”，为后续 `DenseRetriever` 查询打基础。



#  整体架构与流程
1. 文件定位
项目作用：该文件负责将经过向量化（Embedding）处理后的文本块（Chunk）数据，安全、幂等地写入到向量数据库中。
所处层级：处于数据摄入（Ingestion）流程的存储（Storage）层。
核心职责：作为上层业务数据模型（ChunkRecord）与底层向量库数据模型（VectorRecord）之间的桥梁，完成数据格式的“翻译”转换，并执行最终的入库操作。
2. 函数拆解
VectorUpserterError (自定义异常类)

目的：定义向量写入操作专属的错误类型。
功能：当数据缺少向量或类型不匹配时抛出，方便调用方精准捕获和处理特定异常。
VectorUpserter.__init__ (初始化方法)

输入：settings（配置信息），vector_store（可选，具体的向量库实例）。
输出：初始化后的 VectorUpserter 对象。
核心功能：如果调用方没有直接传入向量库实例，则利用工厂模式（VectorStoreFactory）根据配置自动创建一个对应的向量库连接。
VectorUpserter.upsert (核心入库方法)

输入：records（ChunkRecord 对象列表），trace（可选，用于链路追踪的对象）。
输出：成功写入的向量记录 ID 列表。
核心功能：
校验数据是否为空及类型是否正确。
调用转换函数，将业务模型批量转为向量库模型。
调用底层向量库的 upsert 方法执行实际写入。
如果传入了追踪对象，记录本次操作的详细信息（如记录数、ID列表等）。
_to_vector_record (辅助转换函数)

输入：单个 ChunkRecord 对象。
输出：单个 VectorRecord 对象。
核心功能：检查数据中是否包含稠密向量（dense_vector），然后将 ChunkRecord 中的文本、向量、元数据等字段提取出来，重新组装成底层向量库所需的 VectorRecord 标准格式。
3. 执行流程
准备阶段：系统通过 init 初始化 VectorUpserter，准备好底层的向量数据库连接。
触发入库：上游调用 upsert 方法，传入一批处理好的 ChunkRecord 列表。
数据校验：upsert 首先检查列表是否为空，并验证每个元素是否都是合法的 ChunkRecord 对象。
格式转换：遍历列表，逐个调用 _to_vector_record，将业务数据“翻译”成向量库能看懂的 VectorRecord 格式。
执行写入：将转换好的 VectorRecord 列表交给底层的 vector_store.upsert 执行真正的数据库写入操作（幂等写入，即存在则更新，不存在则新增）。
日志追踪：如果开启了链路追踪（trace），则记录当前阶段的执行细节（如使用的向量库类名、记录数量等）。
返回结果：将写入成功的记录 ID 列表按输入顺序返回给上游调用方。
4. 场景示例
假设你正在开发一个 “企业规章制度问答系统”：

前置准备：用户上传了一份《员工手册》PDF，系统将其切分成多个段落，并用 AI 模型为每个段落生成了“稠密向量”（把文字变成了高维数字数组），这些数据被打包成了 ChunkRecord 对象。
触发流程：现在需要把这些带向量的段落存入向量数据库（比如 Milvus）。系统实例化了一个 VectorUpserter，并传入了 Milvus 的配置。
数据转换：系统调用 upsert 方法传入这批 ChunkRecord。upsert 内部调用 _to_vector_record，把 ChunkRecord 里的段落文本、数字数组（向量）以及来源页码（metadata）提取出来，组装成 Milvus 认识的 VectorRecord 格式。如果某个段落因为异常没生成向量，这里就会抛出 VectorUpserterError 报错拦截。
入库与反馈：转换完成后，系统调用 Milvus 的接口将数据写入数据库。写入成功后，系统通过 trace 记录下“本次写入了 50 条数据，ID 分别是 xxx”，最后把这 50 个 ID 返回给上游。上游收到 ID 列表后，就可以放心地在前端提示用户“知识库更新成功”了。