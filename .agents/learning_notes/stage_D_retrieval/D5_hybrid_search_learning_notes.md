# D5_hybrid_search 学习笔记

## 1. 本阶段完成了什么

本阶段完成的是 RAG 查询流程里的“混合检索编排”模块，也就是 `HybridSearch`。

前面几个阶段已经分别实现了查询预处理、dense 检索、sparse 检索和 RRF 融合：

```text
D1 QueryProcessor：把用户 query 变成 keywords 和 filters
D2 DenseRetriever：用 embedding + vector store 做语义检索
D3 SparseRetriever：用 keywords + BM25 做关键词检索
D4 RRFusion：把两路检索结果融合排序
```

D5 的任务就是把这些模块串起来，让一次用户查询可以完整走完：

```text
用户问题
  -> 查询预处理
  -> Dense + Sparse 两路召回
  -> RRF 融合
  -> metadata 过滤
  -> 返回 Top-K RetrievalResult
```

这一步是 Retrieval 阶段真正变成“可调用查询引擎”的关键。后续 CLI、MCP tool、Dashboard 和评估模块都可以基于 `HybridSearch.search()` 来做。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/core/query_engine/hybrid_search.py` | 实现混合检索编排逻辑 |
| `src/core/query_engine/__init__.py` | 导出 `HybridSearch` 和 `HybridSearchError` |
| `tests/integration/test_hybrid_search.py` | 验证完整编排、metadata 过滤、单路失败降级和 trace |
| `DEV_SPEC.md` | 标记 D5 完成并更新进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 D5 进度表 |

## 3. 核心调用关系

```text
HybridSearch.search(query, top_k, filters, trace)
  -> query_processor.process(query, filters, trace)
  -> dense_retriever.retrieve(processed.query, dense_top_k, processed.filters, trace)
  -> sparse_retriever.retrieve(processed.keywords, sparse_top_k, trace)
  -> fusion.fuse(dense_results, sparse_results, fusion_top_k, trace)
  -> _apply_metadata_filters(fused, processed.filters)
  -> 截取 top_k
  -> 返回 List[RetrievalResult]
```

这里的输入是用户原始 query，输出是项目统一的 `RetrievalResult` 列表。

需要注意：D5 不是重新实现 dense、sparse 或 fusion，而是负责“调度”。它让前面几个模块在正确的顺序里协同工作。

## 4. 每个核心文件的作用

### 文件：`src/core/query_engine/hybrid_search.py`

* 主要职责：编排完整混合检索流程。
* 关键类：`HybridSearch`、`HybridSearchError`。
* 输入是什么：原始查询字符串 `query`、返回数量 `top_k`、可选 metadata filters、可选 trace。
* 输出是什么：过滤和融合后的 `List[RetrievalResult]`。
* 在项目中的作用：作为 Retrieval 阶段的统一查询入口。

`__init__()` 支持依赖注入：

```python
HybridSearch(
    settings=settings,
    query_processor=query_processor,
    dense_retriever=dense_retriever,
    sparse_retriever=sparse_retriever,
    fusion=fusion,
)
```

这样测试时可以传入 fake 组件，真实运行时也可以直接用 settings 创建默认组件。

`search()` 是核心方法。它先做输入校验：

```python
if top_k <= 0:
    raise HybridSearchError("top_k must be greater than 0")
if filters is not None and not isinstance(filters, dict):
    raise HybridSearchError("filters must be a dictionary")
```

然后调用 `QueryProcessor`：

```python
processed = self.query_processor.process(query, filters=filters, trace=trace)
```

这里得到的 `processed` 里包含：

```text
processed.query：清理后的查询文本
processed.keywords：给 sparse 检索用的关键词
processed.filters：inline filters 和外部 filters 合并后的过滤条件
```

接着分别调用 dense 和 sparse：

```python
dense_retriever.retrieve(processed.query, top_k=dense_top_k, filters=processed.filters)
sparse_retriever.retrieve(processed.keywords, top_k=sparse_top_k)
```

Dense 检索会带上 filters，这属于前置过滤。Sparse 这一路当前主要依赖 BM25 关键词召回，所以后面还会有一次统一的 metadata 后置过滤。

### `_run_route()`

`_run_route()` 用来执行某一路检索，并把异常转换成“空结果 + 错误对象”：

```python
try:
    return future.result(), None
except Exception as exc:
    return [], exc
```

这样做是为了支持降级。比如 dense 服务临时失败，但 sparse 还能返回结果，那么整个查询仍然可以继续。

如果 dense 和 sparse 都失败，才会抛出：

```python
HybridSearchError("both dense and sparse retrieval failed")
```

### `_apply_metadata_filters()`

这个方法是 metadata 后置过滤兜底：

```python
candidate.metadata.get(key) == value
```

为什么已经在 dense 里传了 filters，还要后置过滤？

因为不同检索路径支持过滤的能力可能不一样。Dense 可能在向量数据库里做了 pre-filter，但 sparse/BM25 不一定支持同样的过滤。后置过滤可以保证最终输出至少满足用户指定的 metadata 条件。

### `_retrieval_top_k()`

这个辅助函数从 settings 里读取不同阶段的 top_k：

```text
retrieval.dense_top_k
retrieval.sparse_top_k
retrieval.fusion_top_k
```

如果 settings 不存在或值不合法，就退回到本次 `search()` 传入的 `top_k`。

### 文件：`src/core/query_engine/__init__.py`

* 主要职责：统一导出 query engine 模块。
* 本阶段新增：`HybridSearch`、`HybridSearchError`。
* 在项目中的作用：让后续模块可以直接通过 `from core.query_engine import HybridSearch` 使用混合检索。

### 文件：`tests/integration/test_hybrid_search.py`

* 主要职责：用 fake 组件验证完整编排流程。
* 关键测试：
  * 是否按顺序调用 query processor、dense、sparse 和 fusion。
  * dense 是否收到处理后的 query 和 filters。
  * sparse 是否收到关键词列表。
  * fusion 是否收到两路召回结果。
  * metadata 后置过滤是否生效。
  * dense 失败时能否退化为 sparse 结果。
  * sparse 失败时能否退化为 dense 结果。
  * 两路都失败时是否抛出 `HybridSearchError`。
  * 是否记录 `hybrid_search` trace。

这些测试用 fake 对象代替真实模型和数据库，重点验证“编排逻辑”本身是否正确。

## 5. 新手重点理解

这一阶段最重要的是理解“编排层”和“能力层”的区别。

前面的模块各自提供一种能力：

```text
QueryProcessor：会处理 query
DenseRetriever：会做语义召回
SparseRetriever：会做关键词召回
RRFusion：会做融合排序
```

但用户真正需要的是“一次查询得到结果”。`HybridSearch` 就是把这些能力按正确顺序组织起来的地方。

另一个重点是降级机制。

真实系统里，embedding 服务、向量库、BM25 索引都可能暂时出问题。如果 dense 和 sparse 其中一路失败，直接让整个查询失败会让系统可用性变差。D5 的设计是：

```text
dense 失败，sparse 成功 -> 返回 sparse 结果
sparse 失败，dense 成功 -> 返回 dense 结果
dense 和 sparse 都失败 -> 抛出错误
```

这让系统更稳。

metadata 过滤也很重要。它保证用户指定的条件，比如 `collection=docs`、`language=en`，最终会被应用到输出结果上。即使某一路检索暂时不能做前置过滤，后置过滤仍然能兜底。

本阶段在 RAG 流程中的位置是：

```text
用户 query
  -> QueryProcessor
  -> DenseRetriever / SparseRetriever
  -> RRFusion
  -> Metadata Filter
  -> Top-K results
```

完成 D5 后，Retrieval 阶段已经具备一个完整查询入口。后续 D6 可以在这个结果基础上做 rerank，D7 可以把它包装成命令行脚本。



# 整体结构与流程
文件定位
作用：hybrid_search.py 文件实现了 RAG（检索增强生成）系统中的混合检索（Hybrid Search） 编排逻辑。 所处层级：位于项目的核心检索引擎层（core.query_engine），是连接底层检索组件（向量检索、关键词检索）与上层应用（如问答生成）的关键枢纽。 核心职责：负责协调和串联查询预处理、稠密检索（Dense Retrieval）、稀疏检索（Sparse Retrieval）以及结果融合（Fusion）等多个阶段，通过多路召回和融合策略，最终为用户提供兼顾语义理解和字面匹配的高质量检索结果。

函数拆解
1. HybridSearchError (异常类)
目的：自定义异常类，继承自 ValueError。
功能：当混合检索过程中出现严重错误（如参数非法、稠密和稀疏检索双双失败）导致无法返回可用结果时抛出，便于上层捕获和处理。
2. HybridSearch.__init__ (初始化方法)
输入：settings（配置对象）、query_processor（查询处理器）、dense_retriever（稠密检索器）、sparse_retriever（稀疏检索器）、fusion（融合器）。
功能：初始化混合检索引擎。如果调用者没有传入具体的组件实例，则使用默认配置自动实例化这些组件，支持依赖注入，方便测试和扩展。
3. HybridSearch.search (核心搜索方法)
输入：query（原始查询文本）、top_k（需要返回的结果数量）、filters（元数据过滤字典）、trace（链路追踪对象）。
输出：list[RetrievalResult]（融合并过滤后的最终检索结果列表）。
核心功能：
校验输入参数（如 top_k 必须大于0）。
调用查询处理器对原始 query 进行预处理（如改写、提取关键词）。
分别执行稠密检索和稀疏检索，并捕获异常实现优雅降级。
如果两路检索都失败，则抛出异常。
调用融合器将两路结果进行融合（如 RRF 算法）。
应用元数据过滤，截取最终的 top_k 个结果。
记录追踪信息并返回结果。
4. HybridSearch._apply_metadata_filters (元数据过滤方法)
输入：candidates（候选结果列表）、filters（过滤条件字典）。
输出：过滤后的候选结果列表。
核心功能：作为防御性兜底机制，遍历候选结果，检查其 metadata 属性是否完全满足传入的 filters 键值对要求，剔除不符合权限或业务规则的文档。
5. HybridSearch._run_route (路由执行方法)
输入：route（一个无参的 Callable 函数，代表具体的检索任务）。
输出：包含检索结果列表和异常对象的元组 (list[RetrievalResult], Exception | None)。
核心功能：使用线程池执行检索任务。其核心目的是隔离异常，如果某一路检索（如向量库宕机）抛出异常，该方法会捕获它并返回空列表和异常对象，从而保证另一路检索（如关键词检索）仍能正常工作，实现系统的优雅降级。
6. _retrieval_top_k (模块级辅助函数)
输入：settings（配置对象）、field_name（配置字段名，如 "dense_top_k"）、default（默认值）。
输出：int（最终确定的 top_k 值）。
核心功能：从全局配置中读取特定检索阶段的 top_k 设定。如果配置不存在或值小于等于0，则回退使用传入的默认值，增强配置的容错性。
执行流程
参数校验：search 方法首先检查 top_k 和 filters 的合法性。
查询处理：调用 self.query_processor.process()，将原始 query 转化为适合检索的格式（如提取出 processed.query 和 processed.keywords）。
计算召回量：通过 _retrieval_top_k 分别计算稠密、稀疏和融合阶段需要召回的 top_k 数量。
多路召回：
调用 _run_route 执行稠密检索（传入 processed.query）。
调用 _run_route 执行稀疏检索（传入 processed.keywords）。
异常处理：检查两路召回的错误状态，若均失败则抛出 HybridSearchError。
结果融合：调用 self.fusion.fuse()，将稠密和稀疏的结果进行融合排序。
后置过滤：调用 _apply_metadata_filters() 对融合后的结果进行元数据硬过滤。
截断与追踪：截取前 top_k 个结果，若传入了 trace 对象，则记录各阶段的耗时和数量指标。
返回结果：将最终的 RetrievalResult 列表返回给调用方。
场景示例
业务场景：企业内部的“HR 政策智能问答助手”。 用户提问：“正式员工如何申请年假？”

全流程串联：

查询处理：QueryProcessor 接收到问题，提取出用于向量检索的完整语义句子：“正式员工如何申请年假”，以及用于关键词检索的核心词：“正式员工”、“申请”、“年假”。
稠密检索：DenseRetriever 将句子转化为向量，在向量数据库中寻找语义相似的文档。它可能召回了《员工休假管理制度》（因为语义高度相关，即使里面没直接写“申请”两个字）。
稀疏检索：SparseRetriever 使用 BM25 算法，在倒排索引中精确匹配包含“正式”、“员工”、“年假”字眼的文档。它可能召回了《年假申请表填写指南》（因为字面匹配度极高）。
异常隔离：假设此时向量数据库网络抖动导致 DenseRetriever 报错，_run_route 捕获了异常并返回空列表，但 SparseRetriever 依然成功返回了结果，系统不会直接崩溃，而是降级为纯关键词检索。
结果融合：RRFusion 使用 RRF（倒数秩融合）算法，将《员工休假管理制度》和《年假申请表填写指南》的排名进行综合计算，得出一个兼顾语义和字面匹配度的最终排序。
元数据过滤：系统传入 filters={"role": "full_time"}。_apply_metadata_filters 检查召回文档的元数据，如果某篇文档标记为 role: "intern"（实习生），则将其剔除，确保正式员工看不到不适用的内容。
返回结果：截取排名前 5 的文档，记录 Trace 日志，返回给大模型（LLM）作为上下文，最终生成准确的回答。