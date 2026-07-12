# C9_sparse_encoder 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `SparseEncoder`，它负责把已经切好的 `Chunk` 文本转换成适合 BM25 检索使用的稀疏向量结构。

在 RAG 流程里，前面的 `DenseEncoder` 负责语义向量，也就是让系统能按“意思相近”去检索；本阶段的 `SparseEncoder` 更偏关键词检索，它会统计每个 chunk 里词项出现的次数，为后续 `BM25Indexer` 构建倒排索引做准备。

它在 Ingestion Pipeline 中的位置是：

```text
DocumentChunker / Transform
  -> List[Chunk]
  -> SparseEncoder
  -> List[ChunkRecord] with sparse_vector
  -> BM25Indexer
```

本阶段没有直接实现完整 BM25 公式。原因是 BM25 需要全局语料统计，比如某个词出现在多少个文档中、全部 chunk 的平均长度等。这些信息更适合在下一阶段 `BM25Indexer` 中统一计算。`SparseEncoder` 当前只负责稳定输出每个 chunk 自己的 term frequency。

## 2. 本阶段新增或修改的文件

| 文件路径                                              | 文件作用                                                  |
| ----------------------------------------------------- | --------------------------------------------------------- |
| `src/ingestion/embedding/sparse_encoder.py`           | 实现 `Chunk` 到 `ChunkRecord.sparse_vector` 的稀疏编码    |
| `src/ingestion/embedding/__init__.py`                 | 对外导出 `SparseEncoder` 和 `SparseEncoderError`          |
| `tests/unit/test_sparse_encoder.py`                   | 验证词频统计、顺序保持、空文本行为、异常输入和 trace 记录 |
| `DEV_SPEC.md`                                         | 将 C9 标记为完成，并更新阶段 C 与总进度                   |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表                          |

## 3. 核心调用关系

```text
调用方
  -> SparseEncoder()
  -> encode(chunks, trace?)
      -> 校验输入都是 Chunk
      -> 对每个 chunk.text 做 tokenize
      -> 用 Counter 统计词项出现次数
      -> 创建 ChunkRecord
          -> id/text/metadata 继承自 Chunk
          -> sparse_vector 写入词频字典
      -> 可选记录 trace.record_stage("sparse_encoding")
  -> 返回 List[ChunkRecord]
```

数据从 `Chunk.text` 进入 `_tokenize()`，再进入 `_term_frequencies()`，最后写入 `ChunkRecord.sparse_vector`。后续 `BM25Indexer` 可以直接读取这个 sparse vector 来构建倒排索引。

## 4. 每个核心文件的作用

### 文件：`src/ingestion/embedding/sparse_encoder.py`

- 主要职责：把文本 chunk 转换成稀疏词频向量。
- 关键函数 / 类：
  - `SparseEncoder`：稀疏编码入口。
  - `encode(chunks, trace)`：批量处理 chunks，返回 `ChunkRecord` 列表。
  - `SparseEncoderError`：输入不符合要求时抛出的阶段性异常。
  - `_term_frequencies(text)`：统计每个词出现次数。
  - `_tokenize(text)`：用正则把文本拆成词项，并统一转成小写。
- 输入是什么：
  - `list[Chunk]`
  - 可选 `trace`
- 输出是什么：
  - `list[ChunkRecord]`，每个 record 带有 `sparse_vector`
- 在项目中的作用：
  - 给后续 `BM25Indexer` 提供稳定、可序列化的词频结构。

### 文件：`src/ingestion/embedding/__init__.py`

- 主要职责：集中暴露 ingestion embedding 阶段的公共入口。
- 关键函数 / 类：
  - `SparseEncoder`
  - `SparseEncoderError`
  - 同时保留已有的 `DenseEncoder` 和 `DenseEncoderError`
- 输入是什么：无直接业务输入。
- 输出是什么：包级导入入口。
- 在项目中的作用：
  - 让后续 pipeline 可以通过 `from ingestion.embedding import SparseEncoder` 使用稀疏编码能力。

### 文件：`tests/unit/test_sparse_encoder.py`

- 主要职责：验证 `SparseEncoder` 的行为契约。
- 关键测试：
  - 大小写归一化后统计词频。
  - 输出顺序和输入 chunk 顺序一致。
  - 输出 record 保留原始 text 和 metadata。
  - 空输入返回空列表。
  - 空文本 chunk 输出空 sparse vector `{}`。
  - 非 `Chunk` 输入抛出 `SparseEncoderError`。
  - 支持 Unicode 词项。
  - 支持 trace 记录 `sparse_encoding` 阶段。
- 输入是什么：
  - 测试构造的 `Chunk`
  - `TraceContext`
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 确保稀疏编码结果可以被后续 BM25 阶段可靠消费。

## 5. 新手重点理解

`sparse_vector` 和 `dense_vector` 解决的是两类不同检索问题。

`dense_vector` 适合语义相似，比如用户问“怎么配置模型”，系统可以找到“LLM provider 设置说明”这种不完全同词但意思相关的内容。

`sparse_vector` 更适合关键词匹配，比如用户明确搜索 “OpenAI API Key” 或 “BM25”。这类场景下，词项是否出现、出现多少次就很重要。

本阶段为什么只做词频，不直接算 BM25 分数？因为 BM25 分数不是单个 chunk 自己能完全决定的。它需要知道整个语料库里每个词有多常见。比如 “the” 或 “系统” 这种词可能到处出现，区分度低；而 “SparseEncoder” 这种词出现少，区分度高。这个“全局稀有程度”要等所有 chunk 都收集起来之后，由 `BM25Indexer` 来计算更合理。

空文本为什么返回 `{}` 而不是报错？因为上游流程中可能存在经过清洗后内容为空的 chunk。这里明确把它表示成“没有任何词项”，后续索引器可以跳过或按空向量处理，行为更稳定。

这一阶段的核心价值是：为混合检索中的关键词检索部分打地基。等后续 dense 检索和 sparse 检索都可用后，系统就可以同时利用语义相似和关键词命中，提高 RAG 检索的召回质量。


## 整体架构

文件定位
项目作用：在 RAG（检索增强生成）系统中，该文件负责将文本数据转换为“稀疏向量”（即词频统计），这是实现 BM25 等传统稀疏检索算法的基础。
所处层级：属于数据摄取（Ingestion）模块中的嵌入（Embedding）层。
核心职责：接收切分好的文本块（Chunk），对其进行分词和词频统计，生成包含稀疏向量的数据记录（ChunkRecord），以便后续存入向量数据库进行高效的关键词检索。

### 核心函数拆解

1. SparseEncoderError (自定义异常类)
   作用目的：用于在稀疏编码过程中遇到非法输入或无法生成有效记录时，抛出明确的错误提示。
   输入/输出：无特定输入输出，继承自 Python 内置的 ValueError。
2. SparseEncoder.encode(self, chunks, trace) (核心编码方法)
   作用目的：将一批文本块（Chunk）批量编码为带有稀疏向量的记录列表。
   输入：
   chunks：Chunk 对象的列表，代表切分后的文本块。
   trace：可选的追踪对象，用于记录当前步骤的运行日志和统计信息。
   输出：ChunkRecord 对象的列表。
   核心功能：
   校验输入是否为空以及元素类型是否正确。
   遍历每个文本块，调用内部函数计算词频，并组装成 ChunkRecord。
   如果传入了 trace，则记录本次处理的块数量、总词数和空块数量等统计信息。
3. \_term_frequencies(text) (词频统计函数)
   作用目的：计算一段文本中各个单词出现的频率。
   输入：text（字符串，即文本块的内容）。
   输出：一个字典，键为单词（小写），值为该单词出现的次数（浮点数格式）。
   核心功能：先调用 \_tokenize 进行分词，然后使用 Python 标准库 collections.Counter 统计词频，最后将结果转换为浮点数字典。
4. \_tokenize(text) (基础分词函数)
   作用目的：将连续的文本字符串拆分成独立的单词列表。
   输入：text（字符串）。
   输出：由小写单词组成的列表。
   核心功能：使用正则表达式 \w+ 匹配所有的字母和数字组合（即单词），并通过 .lower() 将所有单词统一转换为小写，以忽略大小写差异。
   
### 执行流程
   入口调用：外部系统调用 SparseEncoder.encode(chunks, trace) 传入文本块列表。
   前置校验：检查 chunks 是否为空（为空则直接返回空列表），并检查列表中的元素是否都是合法的 Chunk 对象。
   遍历处理：通过列表推导式遍历每一个 chunk：
   提取 chunk.text，传入 \_term_frequencies()。
   \_term_frequencies() 内部调用 \_tokenize()，利用正则表达式提取出所有小写单词。
   \_term_frequencies() 使用 Counter 统计单词出现次数，生成词频字典（如 {'python': 2, 'is': 1}）。
   构建记录：将原文本信息（id, text, metadata）与计算出的词频字典（作为 sparse_vector）结合，实例化为 ChunkRecord。
   日志追踪：如果提供了 trace 对象，计算并记录总块数、总词数（所有词频之和）以及空块数量。
   返回结果：返回构建完成的 ChunkRecord 列表，交由下游模块（如向量数据库写入器）进行持久化。

### 场景示例
   假设在 RAG 系统中，用户上传了一份关于 Python 的文档，系统将其切分成了一个文本块（Chunk），内容为：

"Python is great. Python is easy."

全流程串联讲解：

系统调用 SparseEncoder.encode([chunk])。
encode 方法接收到这个包含 1 个元素的列表，校验通过后开始处理。
针对该 chunk 的文本，调用 \_term_frequencies("Python is great. Python is easy.")。
\_term_frequencies 调用 \_tokenize，正则匹配并转小写后，得到单词列表：['python', 'is', 'great', 'python', 'is', 'easy']。
Counter 统计词频，得到字典：{'python': 2, 'is': 2, 'great': 1, 'easy': 1}，并转为浮点数格式。
系统将这些词频数据作为 sparse_vector，连同 chunk 的 id 和原文本，打包成一个 ChunkRecord。
trace 记录下统计信息：处理了 1 个块，总词数为 6，没有空块。
最终返回包含这个 ChunkRecord 的列表。后续系统会将这个稀疏向量存入 Elasticsearch 等支持 BM25 的数据库中。当用户搜索 "Python" 时，数据库就能通过匹配这个稀疏向量快速找到该文档。
