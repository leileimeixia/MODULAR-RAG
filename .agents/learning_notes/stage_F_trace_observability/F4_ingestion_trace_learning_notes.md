# F4_ingestion_trace 学习笔记

## 1. 本阶段完成了什么

本阶段给 Ingestion 摄取链路加上了 trace 打点。

也就是说，当系统导入一个文档时，不只是最后告诉你“导入成功”或“导入失败”，还会记录整个导入过程经过了哪些阶段、每个阶段用了多久、每个阶段处理了多少数据、失败时失败在哪一步。

在整个 RAG 项目里，Ingestion 是把原始文档变成可检索知识库数据的入口。F4 让这条链路变得可追踪，方便后面排查导入慢、导入失败、图片没保存、向量没入库等问题。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/pipeline.py` | 在 IngestionPipeline 中创建 ingestion trace，记录各阶段耗时和处理详情，并通过 TraceCollector 收集 |
| `tests/integration/test_ingestion_pipeline.py` | 增加 ingestion trace 相关断言，覆盖成功、跳过和失败路径 |
| `DEV_SPEC.md` | 更新 F4 任务状态和总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 的任务进度记录 |

## 3. 核心调用关系

```text
IngestionPipeline.run(path)
  -> 创建 TraceContext(trace_type="ingestion")
  -> integrity
  -> load
  -> image_store
  -> split
  -> transform
  -> embed
  -> upsert
  -> bm25_index
  -> ingestion_complete / ingestion_failed / ingestion_skip
  -> TraceCollector.collect(trace)
  -> 返回 IngestionResult(trace=trace)
```

每个主要阶段都会通过 `_stage()` 包一层：

```text
_stage()
  -> 记录开始时间
  -> 执行业务 action
  -> 成功：record_stage(... failed=False, elapsed_ms=...)
  -> 失败：record_stage(... failed=True, error=..., elapsed_ms=...)
```

这样每个阶段都有统一的 `method`、`details` 和 `elapsed_ms`。

## 4. 每个核心文件的作用

### 文件：`src/ingestion/pipeline.py`

* 主要职责：编排完整的文档摄取流程。
* 本阶段修改点：
  * 默认创建 `TraceContext(trace_type="ingestion")`。
  * 构造或接收 `TraceCollector`。
  * `_stage()` 增加 `method`、`details` 和耗时记录。
  * 成功路径调用 `TraceCollector.collect(trace)`。
  * 跳过路径调用 `TraceCollector.collect(trace)`。
  * 失败路径记录 `ingestion_failed` 后也调用 `TraceCollector.collect(trace)`。
  * 内部组件调用时避免继续传同一个 trace，减少重复阶段。
* 输入是什么：文档路径、collection、force、可选 trace。
* 输出是什么：`IngestionResult`，其中包含本次摄取的 trace。
* 在项目中的作用：它是 ingestion 链路的总调度器，也是 ingestion trace 的创建和收口位置。

### 文件：`tests/integration/test_ingestion_pipeline.py`

* 主要职责：验证摄取流程和摄取 trace 是否符合预期。
* 本阶段修改点：
  * fake pipeline 组件中加入 `TraceCollector`。
  * 成功路径断言 trace_type 是 `"ingestion"`。
  * 成功路径断言存在 `load`、`split`、`transform`、`embed`、`upsert` 阶段。
  * 断言每个关键阶段有 `method` 和非负 `elapsed_ms`。
  * 跳过路径断言 `ingestion_skip` 被记录并 finish。
  * 失败路径断言 `ingestion_failed` 被收集。
* 在项目中的作用：保证 ingestion trace 覆盖成功、跳过和失败三类常见路径。

## 5. 新手重点理解

Ingestion 可以理解成“把原始文件加工成知识库数据”的生产线。一份 PDF 或 Markdown 文件进来后，会经过很多步骤：

```text
文件校验
加载文档
保存图片
切块
增强文本 / 元数据
生成 embedding
写入向量库
写入 BM25 索引
标记成功
```

如果没有 trace，导入失败时你只能看到最后的错误。加上 trace 后，就能知道失败发生在哪一步，以及前面哪些步骤已经完成。

为什么要统一用 `_stage()` 包住每个阶段？因为每个阶段都需要做类似的事情：

* 开始计时。
* 执行实际业务。
* 成功就记录耗时和结果数量。
* 失败就记录错误类型。
* 把阶段信息写进 trace。

如果每个地方都手写一遍，很容易漏字段，也容易格式不一致。集中到 `_stage()` 后，所有 ingestion 阶段的 trace 格式就统一了。

为什么跳过和失败也要收集 trace？因为它们也是重要历史。比如：

* `ingestion_skip` 说明文件没变，所以系统跳过了重复处理。
* `ingestion_failed` 说明这次导入失败，并记录失败阶段和错误类型。

后面 Dashboard 可以读取这些 trace，展示每次导入是成功、跳过还是失败。

本阶段在 RAG 流程中的位置是“摄取链路观测层”。它不改变文档如何切块、如何 embedding、如何入库，而是让整个摄取过程透明、可分析、可调试。



# 整体结构与流程
文件定位
hybrid_search.py 位于项目的 核心查询引擎层（core/query_engine），是混合检索（Hybrid Search）的编排中枢。

它本身不做具体的向量检索或关键词检索，而是负责把"用户原始查询"拆解成多个子任务，调度 QueryProcessor（查询预处理）→ DenseRetriever（稠密/向量检索）→ SparseRetriever（稀疏/关键词检索）→ RRFusion（结果融合） 四个模块协同工作，最终返回一组排序好的检索结果。可以把它理解为"检索流水线的总指挥"。

函数拆解
1. HybridSearchError（异常类）
作用：当混合检索无法返回可用结果时抛出的自定义异常，继承自 ValueError。
典型触发场景：top_k <= 0、filters 类型不对、稠密和稀疏检索同时失败。
2. HybridSearch.__init__
输入：settings（全局配置）、以及四个可注入的组件（query_processor / dense_retriever / sparse_retriever / fusion）。
作用：初始化混合检索器。如果调用方没传入某个组件，就用默认实现兜底，便于单元测试时 mock。
输出：一个装配好的 HybridSearch 实例。
3. HybridSearch.search（核心入口）
输入：query（原始查询字符串）、top_k（期望返回条数）、filters（元数据过滤条件）、trace（链路追踪对象）。
核心流程：
参数校验：top_k 必须 > 0，filters 必须是 dict。
查询预处理：调用 query_processor.process 做改写/分词/过滤提取，并记录耗时。
计算各路 top_k：从 settings 中读取 dense/sparse/fusion 各自的 top_k，没有配置则用默认值。
并行跑两路检索：通过 _run_route 分别执行稠密检索和稀疏检索，任何一路失败都优雅降级（只有一路挂掉仍可用另一路结果）。
融合：把两路结果交给 fusion.fuse 做 RRF（Reciprocal Rank Fusion）融合排序。
元数据兜底过滤：_apply_metadata_filters 再做一层 metadata 精确匹配过滤。
截断 & 记录 trace：截取前 top_k 条，并把整体统计信息写入 trace。
输出：list[RetrievalResult]，最终给到上层的检索结果列表。
4. HybridSearch._apply_metadata_filters
输入：候选结果列表 + 过滤条件 dict。
作用：对融合后的结果做防御性二次过滤——逐条检查每条结果的 metadata 是否包含所有过滤键值对。
输出：过滤后的候选列表。
设计意图：即使底层检索器漏掉了过滤，这里也能兜底，保证返回结果严格符合过滤条件。
5. HybridSearch._run_route
输入：阶段名、方法名、一个无参 callable（实际检索逻辑）、trace。
作用：用 ThreadPoolExecutor 把检索任务丢到线程池执行，并统一做异常捕获 + 耗时记录。
成功：返回 (results, None)。
失败：返回 ([], exception)，让上层决定是否降级。
输出：(结果列表, 异常或None) 的二元组。
设计意图：把"执行 + 监控 + 容错"封装成一个通用模板，避免 dense/sparse 两路检索写重复代码。
6. 模块级函数 _retrieval_top_k
输入：settings 对象、字段名（如 "dense_top_k"）、默认值。
作用：从 settings.retrieval.xxx 中读取配置，读不到或 ≤ 0 就回退到默认值。
输出：一个正整数 top_k。
7. 模块级函数 _record_timed_stage
输入：trace、阶段名、方法名、起始时间戳、details。
作用：如果 trace 不为空，就把该阶段的耗时（毫秒）和详细信息写入 trace，用于后续的可观测性分析。
执行流程
调用链路如下（以 search 为主干）：

用户调用 HybridSearch.search(query, top_k, filters, trace)
│
├─ 1. 参数校验（top_k / filters）
│
├─ 2. QueryProcessor.process(query, filters)  →  processed
│     └─ _record_timed_stage("query_processing", ...)
│
├─ 3. _retrieval_top_k × 3  →  dense_top_k / sparse_top_k / fusion_top_k
│
├─ 4. _run_route("dense_retrieval", ...)
│     ├─ ThreadPoolExecutor 执行 DenseRetriever.retrieve(...)
│     └─ _record_timed_stage("dense_retrieval", ...)
│     → (dense_results, dense_error)
│
├─ 5. _run_route("sparse_retrieval", ...)
│     ├─ ThreadPoolExecutor 执行 SparseRetriever.retrieve(...)
│     └─ _record_timed_stage("sparse_retrieval", ...)
│     → (sparse_results, sparse_error)
│
├─ 6. 若 dense_error 且 sparse_error 同时存在 → 抛 HybridSearchError
│
├─ 7. RRFusion.fuse(dense_results, sparse_results, top_k=fusion_top_k) → fused
│     └─ _record_timed_stage("fusion", ...)
│
├─ 8. _apply_metadata_filters(fused, processed.filters) → filtered
│
├─ 9. 截取 filtered[:top_k] → results
│
└─10. trace.record_stage("hybrid_search", ...)  → 返回 results
场景示例
假设你在做一个企业知识库问答系统，用户在搜索框输入：

"2024 年 Q3 销售报告"，并限定 filters = {"department": "sales"}，top_k = 5。

参数校验：top_k=5 > 0 ✓，filters 是 dict ✓，通过。
查询预处理：QueryProcessor 把原句改写成更适合检索的形式（比如去掉停用词、提取关键词 ["2024", "Q3", "销售", "报告"]），并把 department=sales 保留到 processed.filters。
读取配置：假设 settings 里配了 dense_top_k=20, sparse_top_k=20, fusion_top_k=30，那就按配置来；没配就都用 5。
稠密检索：DenseRetriever 把改写后的 query 通过 embedding 模型转成向量，去向量数据库里找最相似的 20 条文档，返回 dense_results。
稀疏检索：SparseRetriever 用关键词 ["2024","Q3","销售","报告"] 去 BM25/ES 里做全文检索，返回 sparse_results。
假设此时向量服务抖动，dense_error 不为空，但稀疏检索正常 → 降级，只用稀疏结果继续。
融合：RRFusion 把（可能只有一路的）结果按 RRF 算法重新打分排序，取前 30 条 → fused。
元数据兜底过滤：遍历 fused，只保留 metadata["department"] == "sales" 的文档，把其它部门（如 hr、engineering）的报告剔除。
截断：取前 5 条返回给上层 RAG 生成模块，作为 LLM 生成答案的上下文。
Trace 记录：整个过程的耗时、每路检索的成功/失败、最终命中数都写进 trace，方便后续在监控面板上排查"为什么某次检索效果差"。
最终，上层拿到 5 条既语义相关、又关键词匹配、又符合部门过滤的高质量文档，喂给大模型生成回答。