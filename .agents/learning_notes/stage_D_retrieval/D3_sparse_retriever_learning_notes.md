# D3_sparse_retriever 学习笔记

## 1. 本阶段完成了什么

本阶段完成的是 RAG 查询流程里的“稀疏检索”部分，也就是 `SparseRetriever`。

在前面的阶段里，文档已经经过切块、编码，并且 BM25 索引已经可以保存每个 chunk 的关键词统计。D3 做的事情是：当用户查询被 `QueryProcessor` 提取出关键词之后，用这些关键词去 BM25 索引里查出最相关的 chunk id，然后再根据这些 id 去向量存储里取回正文和 metadata，最后统一包装成 `RetrievalResult`。

简单说，它把：

```text
关键词
  -> BM25 命中的 chunk id 和分数
  -> chunk 正文与 metadata
  -> RetrievalResult
```

串成了一条可用的查询链路。

这一步属于 RAG 流程中的 Retrieval 阶段。它和 D2 的 `DenseRetriever` 是并行关系：D2 负责语义向量检索，D3 负责关键词匹配检索，后续 D4 会把两路结果做融合。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/core/query_engine/sparse_retriever.py` | 新增稀疏检索器，调用 BM25 查询并组装 `RetrievalResult` |
| `src/core/query_engine/__init__.py` | 导出 `SparseRetriever` 和 `SparseRetrieverError` |
| `src/libs/vector_store/base_vector_store.py` | 为向量存储抽象接口新增 `get_by_ids()` |
| `src/libs/vector_store/chroma_store.py` | 在默认存储实现中支持按 chunk id 批量取回记录 |
| `tests/unit/test_sparse_retriever.py` | 覆盖稀疏检索主流程、缺失 id、空结果、参数校验和 trace |
| `tests/unit/test_vector_store_contract.py` | 补充 `get_by_ids()` 的契约测试 |
| `tests/integration/test_chroma_store_roundtrip.py` | 验证 `ChromaStore.get_by_ids()` 的实际行为 |
| `tests/unit/test_dense_retriever.py` | 让测试 fake store 补齐新的抽象方法 |
| `tests/unit/test_vector_upserter_idempotency.py` | 让测试 fake store 补齐新的抽象方法 |
| `DEV_SPEC.md` | 标记 D3 完成并更新进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 D3 进度表 |

## 3. 核心调用关系

```text
SparseRetriever.retrieve(keywords, top_k)
  -> 校验 keywords 和 top_k
  -> 把关键词列表拼成 BM25 查询字符串
  -> bm25_indexer.query(query, top_k)
  -> 得到 [{chunk_id, score}]
  -> vector_store.get_by_ids(chunk_ids)
  -> 得到 VectorRecord(id, text, vector, metadata)
  -> 合并 BM25 score + VectorRecord text/metadata
  -> 返回 List[RetrievalResult]
```

这里要注意一个关键设计：BM25 索引返回的是“这个 chunk 很相关”，但它本身不负责提供完整的 chunk 正文。正文和 metadata 仍然从 `VectorStore` 取，这样查询结果的数据来源保持统一。

## 4. 每个核心文件的作用

### 文件：`src/core/query_engine/sparse_retriever.py`

* 主要职责：实现关键词检索链路。
* 关键类：`SparseRetriever`、`SparseRetrieverError`。
* 输入是什么：关键词列表 `keywords`、返回数量 `top_k`、可选 `trace`。
* 输出是什么：`List[RetrievalResult]`。
* 在项目中的作用：把 BM25 的稀疏检索结果转成项目统一的查询结果格式，方便后续和 dense 检索结果融合。

`SparseRetriever.__init__()` 支持依赖注入：

```python
SparseRetriever(bm25_indexer=fake_bm25, vector_store=fake_store)
```

这让测试可以不用真的加载磁盘上的 BM25 文件和真实向量库，直接用 fake 对象验证行为。

`retrieve()` 里最核心的逻辑有三步：

```python
bm25_results = self.bm25_indexer.query(" ".join(normalized_keywords), top_k=top_k)
records = self.vector_store.get_by_ids(chunk_ids, trace=trace)
retrieval_results.append(_to_retrieval_result(record, float(result["score"])))
```

这三行对应了“查 id、取正文、组装结果”。

### 文件：`src/libs/vector_store/base_vector_store.py`

* 主要职责：定义所有向量存储都必须实现的统一接口。
* 新增方法：`get_by_ids(ids, trace=None)`。
* 输入是什么：chunk id 列表。
* 输出是什么：`List[VectorRecord]`。
* 在项目中的作用：让查询层可以不关心底层是 Chroma、内存存储还是未来的其他数据库，只要调用统一方法即可。

这次新增 `get_by_ids()` 是因为 BM25 查询只返回 chunk id。如果没有这个接口，`SparseRetriever` 就没法通过 id 反查 chunk 正文。

### 文件：`src/libs/vector_store/chroma_store.py`

* 主要职责：项目默认的本地持久化向量存储实现。
* 新增方法：`get_by_ids()`。
* 输入是什么：id 列表。
* 输出是什么：已存在的 `VectorRecord` 列表。
* 在项目中的作用：给 `SparseRetriever` 提供“按 id 批量取正文”的能力。

这里有两个行为很重要：

```python
return [
    self._records[record_id]
    for record_id in ids
    if record_id in self._records
]
```

第一，它保持输入 id 的顺序。BM25 已经排好了相关性顺序，取回正文时不能打乱。

第二，它跳过不存在的 id。这样即使 BM25 索引和向量存储短暂不一致，查询也不会直接崩掉，而是返回能找到的结果。

### 文件：`tests/unit/test_sparse_retriever.py`

* 主要职责：验证 D3 的核心行为。
* 关键测试：
  * BM25 查询参数是否正确。
  * 返回结果是否按 BM25 排名顺序组装。
  * BM25 命中的 id 如果在向量库里不存在，是否能跳过。
  * BM25 没结果时是否返回空列表。
  * 非法输入是否抛出 `SparseRetrieverError`。
  * 是否正确记录 `sparse_retrieval` trace。

这里用 `FakeBM25Indexer` 和 `FakeVectorStore` 是为了把测试重点放在 `SparseRetriever` 自己的逻辑上，而不是依赖真实磁盘文件或真实索引。

### 文件：`tests/unit/test_vector_store_contract.py`

* 主要职责：验证所有向量存储实现都应该遵守的基本约定。
* 本阶段新增重点：`get_by_ids()` 应该保持请求顺序，并跳过缺失 id。

这类契约测试的价值在于：以后如果新增 Milvus、Qdrant 或其他向量存储，只要它们通过同一组契约测试，就能说明它们满足项目核心调用方式。

## 5. 新手重点理解

稀疏检索和 dense 检索最大的区别是：它更依赖关键词是否匹配。

Dense 检索通常是：

```text
用户问题 -> embedding 向量 -> 向量相似度搜索
```

Sparse 检索通常是：

```text
用户问题关键词 -> BM25 关键词匹配 -> chunk id
```

所以 D3 不需要 embedding 模型，它只需要关键词和 BM25 索引。这样做的好处是，当用户问题里有明确术语、编号、专有名词时，BM25 往往很有用。

另一个重点是为什么要新增 `VectorStore.get_by_ids()`。

BM25 索引适合快速回答“哪些 chunk id 跟关键词最相关”，但最终返回给用户或后续模块的结果不能只有 id，还需要正文、来源、metadata。因此需要再去统一存储层取完整记录。

本阶段的设计把职责分得比较清楚：

```text
BM25Indexer：只负责关键词打分和返回 chunk id
VectorStore：负责保存和取回 chunk 正文、向量、metadata
SparseRetriever：负责把两者串起来，输出 RetrievalResult
```

这种拆分让后续 D4 做 RRF Fusion 时会更简单，因为 dense 和 sparse 两条链路最终都会返回同一种 `RetrievalResult`。



# 整体架构与流程
以下是对 sparse_retriever.py 代码文件的完整解析：

1. 文件定位
项目作用：该文件实现了基于 BM25 算法的稀疏检索器（Sparse Retriever），是 RAG（检索增强生成）系统中负责“关键词字面匹配”的核心组件。
所处层级：位于项目的核心查询引擎层（core/query_engine），属于检索模块（Retrieval）的下层执行器。
核心职责：接收归一化后的查询关键词，通过 BM25 索引器进行稀疏检索获取相关的文档块（Chunk）ID，然后从向量存储中“水合”（Hydrate）这些 ID 对应的完整文本和元数据，最终输出标准化的检索结果。
2. 函数拆解
SparseRetrieverError (自定义异常类)
作用目的：定义稀疏检索过程中的专属异常。
核心功能：继承自 ValueError，当输入参数不合法或检索无法完成时抛出，便于上层代码进行精准的异常捕获和处理。
SparseRetriever.__init__ (初始化方法)
输入：settings（配置信息）、bm25_indexer（BM25索引器实例）、vector_store（向量存储实例）。
输出：无（完成实例属性初始化）。
核心功能：初始化检索器依赖。如果外部没有传入索引器或向量存储，则使用默认配置自动加载 BM25 索引和创建向量存储实例。
SparseRetriever.retrieve (核心检索方法)
输入：keywords（关键词字符串列表）、top_k（需要返回的最大结果数量）、trace（可选的链路追踪对象）。
输出：list[RetrievalResult]（标准化的检索结果列表）。
核心功能：
参数校验：严格检查 keywords 是否为纯非空字符串列表，top_k 是否大于 0。
BM25 检索：将关键词用空格拼接，调用底层 bm25_indexer.query 获取 Top-K 的候选 Chunk ID 及其相关性分数。
数据水合：提取有效的 Chunk ID，调用 vector_store.get_by_ids 从向量库中批量拉取完整的文本内容。
结果组装：将 BM25 分数与向量库中的文本进行匹配和组装。
链路追踪：记录本次检索的各项统计指标。
SparseRetriever._record_trace (内部追踪方法)
输入：trace 对象以及各项统计指标（top_k, keyword_count, candidate_count, result_count, missing_count）。
输出：无。
核心功能：如果传入了 trace 对象，则记录当前“稀疏检索”阶段的详细执行日志，包括使用的索引方法名称和各项数据统计，方便后续调试和性能分析。
_to_retrieval_result (模块级辅助函数)
输入：record（向量存储中的原始记录对象）、score（BM25 计算出的浮点数分数）。
输出：RetrievalResult 对象。
核心功能：数据格式转换器。将底层的向量记录对象和分数，转换为项目全局统一的 RetrievalResult 数据结构（包含 chunk_id, score, text, metadata）。
3. 执行流程
实例化阶段：系统启动时，实例化 SparseRetriever，自动加载磁盘上的 BM25 索引文件和向量数据库连接。
触发检索：上层模块调用 retrieve(keywords, top_k)。
参数拦截：首先进行严格的参数合法性校验，不合规直接抛出 SparseRetrieverError。
稀疏打分：调用 bm25_indexer.query，BM25 算法根据词频（TF）和逆文档频率（IDF）计算关键词与索引库中文档的匹配分数，返回 Top-K 的 chunk_id 和 score。
批量获取：提取上一步的 chunk_id 列表，调用 vector_store.get_by_ids 去向量库中“捞取”这些 ID 对应的完整文本（因为 BM25 索引通常只存 ID 和词频，不存完整长文本）。
数据融合：遍历 BM25 结果，通过 chunk_id 作为桥梁，将分数与完整文本结合，调用 _to_retrieval_result 生成标准结果。
日志记录：调用 _record_trace 记录本次检索的耗时、命中数、缺失数等指标。
返回结果：将组装好的 RetrievalResult 列表返回给上游（如重排序模块 Reranker 或大模型）。
4. 场景示例
业务场景：假设我们正在开发一个 “企业智能客服知识库”。

用户提问：员工在对话框输入：“如何申请年假？”
查询预处理：上游的 Query 解析模块将问题提取并归一化为关键词列表：keywords = ["申请", "年假"]。
调用检索器：系统调用 sparse_retriever.retrieve(keywords=["申请", "年假"], top_k=3)。
BM25 匹配：
参数校验通过。
bm25_indexer 在倒排索引中计算匹配度，发现以下 3 个文档块得分最高：
chunk_101 (分数 8.5) - 内容包含“员工每年享有5天年假，需在OA系统提交申请...”
chunk_205 (分数 7.2) - 内容包含“年假申请流程及审批节点说明...”
chunk_088 (分数 6.1) - 内容包含“病假与年假的转换规则...”
数据水合：检索器拿着 ["chunk_101", "chunk_205", "chunk_088"] 去向量数据库（vector_store）中批量查询，获取这 3 个 ID 对应的完整段落文本。
结果组装：调用 _to_retrieval_result，将文本、元数据（如所属文档名、页码）和 BM25 分数打包成 3 个 RetrievalResult 对象。
记录与返回：记录 trace（如：keyword_count=2, result_count=3），然后将这 3 个高相关性的结果返回。
后续处理：这 3 个结果会被送入 Rerank（重排序）模型进行二次精排，最后交给大模型（LLM）生成最终的自然语言回答：“您好，申请年假请按以下步骤操作：1. 登录OA系统...”