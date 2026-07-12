# C8_dense_encoder 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `DenseEncoder`，它负责把 `Chunk.text` 批量送入 embedding 模型，并把返回的 dense vector 写入 `ChunkRecord`。

在 RAG 系统里，dense vector 是语义检索的基础。用户查询和文档 chunk 都会被转换成向量，后续向量数据库才能根据语义相似度找到相关内容。

它在 Ingestion Pipeline 中的位置是 Transform 之后、VectorStore 写入之前：

```text
ChunkRefiner / MetadataEnricher / ImageCaptioner
  -> List[Chunk]
  -> DenseEncoder
  -> List[ChunkRecord] with dense_vector
  -> VectorUpserter / VectorStore
```

本阶段没有直接调用真实 OpenAI 或其他 embedding 服务，而是通过 `BaseEmbedding` 抽象接口调用。测试中使用 `FakeEmbedding`，这样可以稳定验证 DenseEncoder 自身逻辑。

## 2. 本阶段新增或修改的文件

| 文件路径                                              | 文件作用                                               |
| ----------------------------------------------------- | ------------------------------------------------------ |
| `src/ingestion/embedding/dense_encoder.py`            | 实现 chunks 到 dense vectors 的编码适配                |
| `src/ingestion/embedding/__init__.py`                 | 导出 `DenseEncoder` 和 `DenseEncoderError`             |
| `tests/unit/test_dense_encoder.py`                    | 验证顺序保持、metadata 保留、向量形状校验和 trace 记录 |
| `DEV_SPEC.md`                                         | 将 C8 标记为完成，并更新阶段 C 与总进度                |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表                       |

## 3. 核心调用关系

```text
调用方
  -> DenseEncoder(settings?, embedding?)
      -> 如果没有注入 embedding:
          -> EmbeddingFactory.create(settings)

DenseEncoder.encode(chunks, trace?)
  -> 校验输入都是 Chunk
  -> texts = [chunk.text for chunk in chunks]
  -> embedding.embed(texts, trace)
  -> 校验 vectors 数量和维度
  -> 为每个 chunk 创建 ChunkRecord
      -> id/text/metadata 继承自 chunk
      -> dense_vector 来自 embedding
  -> trace.record_stage("dense_encoding")
  -> 返回 List[ChunkRecord]
```

核心点是：`DenseEncoder` 不关心具体 embedding provider 是 OpenAI、Azure 还是 Ollama。它只依赖 `BaseEmbedding` 的统一接口。

## 4. 每个核心文件的作用

### 文件：`src/ingestion/embedding/dense_encoder.py`

- 主要职责：把 `Chunk` 转换成带 dense vector 的 `ChunkRecord`。
- 关键函数 / 类：
  - `DenseEncoder`：dense 编码入口。
  - `encode(chunks, trace)`：批量编码 chunks。
  - `DenseEncoderError`：dense 编码阶段的可读异常。
  - `_validate_vectors(chunks, vectors)`：校验 embedding 返回值是否可用。
- 输入是什么：
  - `list[Chunk]`
  - 可选 `BaseEmbedding`
  - 可选 `trace`
- 输出是什么：
  - `list[ChunkRecord]`，每个 record 都带有 `dense_vector`
- 在项目中的作用：
  - 为后续 `VectorUpserter` 和向量数据库写入提供标准数据结构。

### 文件：`src/ingestion/embedding/__init__.py`

- 主要职责：导出 embedding 阶段的公共入口。
- 关键函数 / 类：
  - `DenseEncoder`
  - `DenseEncoderError`
- 输入是什么：无直接业务输入。
- 输出是什么：包级导入入口。
- 在项目中的作用：
  - 让 pipeline 后续可以通过 `from ingestion.embedding import DenseEncoder` 使用 dense 编码能力。

### 文件：`tests/unit/test_dense_encoder.py`

- 主要职责：验证 DenseEncoder 的契约。
- 关键测试：
  - embedding 调用顺序和 chunk 顺序一致。
  - 输出 record 保留 chunk 的 id、text、metadata。
  - 空输入返回空列表。
  - 非 Chunk 输入抛出 `DenseEncoderError`。
  - embedding 返回向量数量不匹配时报错。
  - embedding 返回向量维度不一致时报错。
  - embedding 返回非数字值时报错。
  - 支持 trace 记录。
- 输入是什么：
  - 测试构造的 `Chunk`
  - `FakeEmbedding`
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 保证向量写入前的数据形状稳定，避免脏向量进入后续存储层。

## 5. 新手重点理解

DenseEncoder 是“文本变向量”的适配层。

前面的 Loader、Chunker、Transform 都还在处理文本和 metadata；到了 DenseEncoder，文本第一次被转换成向量。这个向量后续会被写入向量数据库，用于语义检索。

为什么输出是 `ChunkRecord`，不是直接修改 `Chunk`？因为 `Chunk` 表示业务文本片段，而 `ChunkRecord` 更接近存储层 payload。它可以同时携带文本、metadata、dense vector、后续 sparse vector，适合交给 VectorStore 或 BM25 等存储模块。

为什么要严格校验向量数量和维度？因为 embedding provider 是外部依赖，可能返回异常形状。如果两个 chunk 只返回了一个 vector，或者每个 vector 维度不一致，继续写入数据库会造成更难排查的问题。这里尽早报错，能让问题停在最容易定位的位置。



这一阶段的核心价值是：把前面处理好的 chunk 转换成向量检索可用的标准记录，为后续向量存储和检索打基础。

1. Chunk.text (文本块内容)
   字面含义：Chunk 是文档切分后的“文本块”，.text 是这个文本块里具体的文字内容。
   通俗理解：想象你把一本厚厚的书撕成了一沓知识卡片，每张卡片上抄写了一小段话。Chunk 就是这张卡片本身，而 Chunk.text 就是卡片上写的具体文字。
2. embedding 模型 (嵌入模型)
   字面含义：一种能够将文本、图像等数据映射到高维数学空间的机器学习模型。
   通俗理解：它是一个 “语义翻译官”。计算机不认识“苹果”和“香蕉”，但这个翻译官能把词语翻译成一组数字。它的神奇之处在于：意思越相近的词，翻译出来的数字组合就越接近。
3. dense vector (稠密向量)
   字面含义：由 embedding 模型输出的一组浮点数数组（如 [0.12, -0.45, 0.88, ...]），用于表示数据的语义特征。
   通俗理解：这就是翻译官给这段文字分配的 “语义 GPS 坐标”。
   为什么叫 vector（向量）？因为它是一串有方向的数字坐标。
   为什么叫 dense（稠密）？因为在这串坐标里，几乎每一个位置都有具体的数值（不像“稀疏向量 sparse vector”里面大部分是 0）。
   作用：有了这个坐标，计算机就能通过计算坐标之间的距离，知道两段话意思是不是相近。
4. DenseEncoder (稠密编码器)
   字面含义：负责调用 embedding 模型，将 Chunk 批量转换为 dense vector 的组件/类。
   通俗理解：它是流水线上的 “坐标打标机” 或 “车间主任”。它负责把一摞知识卡片（Chunk）批量塞给翻译官（embedding 模型），等翻译官算出坐标后，再把这些坐标（dense vector）工工整整地贴回卡片上。
5. ChunkRecord (块记录)
   字面含义：一种数据结构，不仅包含原始 Chunk 的信息（如 id、text、metadata），还包含了生成的 dense vector（以及后续可能的其他向量），专门用于写入数据库。
   通俗理解：这是入库前的 “最终标准档案袋”。
   原来的 Chunk 只是业务上的“草稿卡片”。
   当它被贴上了“语义 GPS 坐标”（dense vector）后，就升级成了 ChunkRecord。它带着文字、元数据和坐标，变成了可以直接塞进向量数据库（图书馆智能书架）的标准格式。
   💡 总结串联
   把上面的概念连起来，你提供的那句话其实就在说：

“我们造了一台坐标打标机（DenseEncoder），它把一沓知识卡片上的文字（Chunk.text） 批量交给翻译官（embedding 模型），算出每段话的语义 GPS 坐标（dense vector），然后把这些坐标装进最终标准档案袋（ChunkRecord） 里，准备存入数据库。”


## 总体架构
文件定位
文件路径：src/ingestion/embedding/dense_encoder.py

项目层级：该文件位于项目 ingestion（数据摄入）模块的 embedding（嵌入）子模块下，属于数据预处理链路中的"向量化"环节。

核心职责：将文本块（Chunk）通过稠密向量模型（Dense Embedding Model）编码为数值向量，并封装为带有向量信息的 ChunkRecord 对象，供后续的存储、检索使用。简单来说，它就是一个"文本→向量"的转换器。

函数拆解
1. DenseEncoderError（异常类）
作用：自定义异常，继承自 ValueError，当稠密编码过程出现问题时抛出。
使用场景：比如输入不是 Chunk 对象、向量维度不一致、向量包含非数值等。
2. DenseEncoder.__init__（初始化方法）
输入：
settings：配置对象（可选），用于指定使用哪个 Embedding 模型。
embedding：直接传入一个 BaseEmbedding 实例（可选），优先级高于 settings。
核心功能：初始化编码器，如果没传 embedding 实例，就通过 EmbeddingFactory 工厂根据 settings 自动创建一个。
输出：无返回值，完成实例属性绑定。
3. DenseEncoder.encode（核心编码方法）
输入：
chunks：Chunk 对象列表，每个 Chunk 包含 id、text、metadata 等字段。
trace：可选的追踪对象，用于记录执行过程的日志/指标。
核心功能：
校验输入是否为空、是否为合法的 Chunk 列表。
提取所有 Chunk 的文本，调用 self.embedding.embed() 批量生成向量。
调用 _validate_vectors 校验向量合法性。
将每个 Chunk 和对应向量组装成 ChunkRecord。
如果有 trace，记录本次编码的统计信息（块数量、向量维度）。
输出：ChunkRecord 列表，每个记录包含原文本信息和对应的稠密向量。
4. _validate_vectors（内部校验函数）
输入：
chunks：原始 Chunk 列表。
vectors：模型返回的向量列表。
核心功能：逐层校验向量结果的合法性：
向量数量是否等于 Chunk 数量。
向量列表是否为空。
第一个向量的维度是否 > 0。
所有向量的维度是否一致。
向量中每个值是否为数值类型（int 或 float）。
输出：无返回值；校验失败时抛出 DenseEncoderError。
执行流程
用户调用 DenseEncoder.encode(chunks, trace)
        │
        ▼
  ① 空列表检查 → 为空则直接返回 []
        │
        ▼
  ② 类型校验 → 非 Chunk 对象则抛出 DenseEncoderError
        │
        ▼
  ③ 提取文本 → [chunk.text for chunk in chunks]
        │
        ▼
  ④ 调用 Embedding 模型 → self.embedding.embed(texts, trace)
        │
        ▼
  ⑤ 校验向量 → _validate_vectors(chunks, vectors)
        │  ├─ 数量不一致 → 报错
        │  ├─ 空向量 → 报错
        │  ├─ 维度不一致 → 报错
        │  └─ 非数值 → 报错
        │
        ▼
  ⑥ 组装 ChunkRecord → 将 chunk 信息 + dense_vector 打包
        │
        ▼
  ⑦ 记录 Trace（可选）→ 记录 chunk_count 和 dimensions
        │
        ▼
  ⑧ 返回 records 列表
场景示例
假设你正在构建一个 RAG（检索增强生成）系统，用户上传了一份 PDF 文档，系统已经将其切分为 3 个文本块：

Chunk ID	文本内容
chunk_1	"RAG 是一种结合检索与生成的技术"
chunk_2	"向量数据库用于存储文本的嵌入表示"
chunk_3	"Dense Encoder 将文本转换为稠密向量"
执行过程：

初始化：encoder = DenseEncoder(settings=my_config)，工厂根据配置创建了一个 OpenAI 的 Embedding 模型实例。

调用编码：records = encoder.encode([chunk_1, chunk_2, chunk_3])

提取文本：得到 ["RAG 是一种...", "向量数据库...", "Dense Encoder..."]

模型推理：调用 OpenAI Embedding API，返回 3 个 1536 维的浮点数向量。

校验：_validate_vectors 确认 3 个向量、每个 1536 维、全是浮点数 ✅

组装结果：生成 3 个 ChunkRecord，例如：

python
ChunkRecord(
    id="chunk_1",
    text="RAG 是一种结合检索与生成的技术",
    metadata={...},
    dense_vector=[0.0123, -0.0456, ..., 0.0789]  # 1536维
)
记录追踪：trace 记录 {"chunk_count": 3, "dimensions": 1536}

返回：这 3 条 ChunkRecord 随后会被写入向量数据库，供后续检索使用。