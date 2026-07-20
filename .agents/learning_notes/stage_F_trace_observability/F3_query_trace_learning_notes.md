# F3_query_trace 学习笔记

## 1. 本阶段完成了什么

本阶段给 Query 查询链路加上了 trace 打点。

也就是说，当用户通过 `query_knowledge_hub` 发起一次知识库查询时，系统不只是返回答案，还会记录这次查询经过了哪些阶段、每个阶段用了多久、是否有某个检索分支失败、最终返回了多少结果。

这一步的核心价值是：让查询过程变得“可追踪”。如果以后用户觉得查询慢、结果不对、召回为空，就可以看 trace，判断问题发生在 query 处理、dense 检索、sparse 检索、融合、rerank，还是最终响应组装。

在整个 RAG 项目里，F3 属于“查询链路可观测性”。它不改变 RAG 的检索算法本身，而是在查询流程外面加了一层运行记录。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/mcp_server/tools/query_knowledge_hub.py` | 在 MCP 查询入口创建 `TraceContext(trace_type="query")`，传入查询链路，并把 trace 放入响应 |
| `src/core/query_engine/hybrid_search.py` | 给 query processing、dense retrieval、sparse retrieval、fusion、hybrid_search 阶段记录 trace |
| `src/core/query_engine/reranker.py` | 给 rerank 阶段记录 trace 和耗时 |
| `tests/integration/test_hybrid_search.py` | 验证 HybridSearch 会记录标准查询阶段 |
| `tests/unit/test_query_knowledge_hub_tool.py` | 验证 query tool 会创建 query trace、传递 trace，并把 trace 返回到 structuredContent |
| `DEV_SPEC.md` | 更新 F3 任务状态和总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 的任务进度记录 |

## 3. 核心调用关系

```text
MCP Client
  -> query_knowledge_hub(arguments)
  -> 创建 TraceContext(trace_type="query")
  -> HybridSearch.search(..., trace=trace)
       -> query_processing
       -> dense_retrieval
       -> sparse_retrieval
       -> fusion
       -> hybrid_search
  -> CoreReranker.rerank(..., trace=trace)
       -> rerank
  -> ResponseBuilder.build(...)
  -> TraceCollector.collect(trace)
  -> response.structuredContent["trace"] = trace payload
  -> 返回 MCP tool result
```

最终一次查询会得到类似这样的 trace 阶段列表：

```text
query_processing
dense_retrieval
sparse_retrieval
fusion
hybrid_search
rerank
```

每个阶段都会有 `method`、`details` 和 `elapsed_ms`。

## 4. 每个核心文件的作用

### 文件：`src/mcp_server/tools/query_knowledge_hub.py`

* 主要职责：作为 MCP 查询工具入口，负责组织完整查询流程。
* 本阶段修改点：
  * 创建 `TraceContext(trace_type="query")`。
  * 创建或接收 `TraceCollector`。
  * 调用 `HybridSearch.search(..., trace=trace)`。
  * 调用 `CoreReranker.rerank(..., trace=trace)`。
  * 查询结束后调用 `trace_collector.collect(trace)`。
  * 把最终 trace payload 写入 `response["structuredContent"]["trace"]`。
* 输入是什么：MCP tool arguments，例如 `query`、`top_k`、`collection`。
* 输出是什么：包含答案、引用和 trace 的 MCP tool result。
* 在项目中的作用：它是 Query 链路 trace 的起点和收口。

### 文件：`src/core/query_engine/hybrid_search.py`

* 主要职责：编排 query processing、dense retrieval、sparse retrieval 和 fusion。
* 本阶段修改点：
  * 使用 `time.perf_counter()` 计算阶段耗时。
  * 新增 `_record_timed_stage()` 辅助函数，统一记录阶段耗时。
  * 记录 `query_processing` 阶段。
  * 记录 `dense_retrieval` 阶段。
  * 记录 `sparse_retrieval` 阶段。
  * 记录 `fusion` 阶段。
  * 保留 `hybrid_search` 总结阶段。
* 输入是什么：用户 query、top_k、filters、trace。
* 输出是什么：融合和过滤后的 `RetrievalResult` 列表，同时向 trace 写入阶段记录。
* 在项目中的作用：它是查询链路中最重要的检索编排层。

### 文件：`src/core/query_engine/reranker.py`

* 主要职责：把检索结果交给 reranker 后端进行重排，并在失败时安全降级。
* 本阶段修改点：
  * 在 rerank 开始前记录时间。
  * 调用后端 reranker 时不再继续向内部传递 trace，避免重复记录同名阶段。
  * rerank 完成或失败后，把耗时写入最新的 `rerank` stage。
* 输入是什么：query、候选结果、top_k、trace。
* 输出是什么：重排后的 `RetrievalResult` 列表，同时向 trace 写入 `rerank` 阶段。
* 在项目中的作用：它是查询链路中控制最终排序质量的一层。

### 文件：`tests/integration/test_hybrid_search.py`

* 主要职责：验证 HybridSearch 的查询编排行为。
* 本阶段修改点：
  * 断言 trace 中存在 `query_processing`、`dense_retrieval`、`sparse_retrieval`、`fusion`、`hybrid_search`。
  * 断言每个阶段都有 `method`。
  * 断言每个阶段都有非负 `elapsed_ms`。
  * 断言 `trace.to_dict()["trace_type"] == "query"`。
* 在项目中的作用：保证查询链路打点的基本结构稳定。

### 文件：`tests/unit/test_query_knowledge_hub_tool.py`

* 主要职责：验证 MCP 查询工具行为。
* 本阶段修改点：
  * fake search 和 fake reranker 接收 trace。
  * 断言 trace 类型是 `"query"`。
  * 断言最终 response 的 `structuredContent` 里包含 trace。
  * 断言 `TraceCollector` 收集到的 trace 和返回的 trace 一致。
* 在项目中的作用：确保 MCP tool 入口层真正创建并返回 trace。

## 5. 新手重点理解

F3 可以理解成：给“用户提问到系统返回答案”的整条路装上计时器和记录器。

一次查询并不是一个单独动作，而是一串动作：

```text
处理问题
向量检索
关键词检索
融合结果
重排结果
生成响应
```

如果查询很慢，没有 trace 时只能知道“慢”。有 trace 后，就能知道是 dense retrieval 慢、sparse retrieval 慢，还是 rerank 慢。

这里还有一个重要设计：`query_knowledge_hub` 是 trace 的入口和出口。它创建 trace，把 trace 传给下游模块，最后收集 trace 并放入 response。这样 MCP 客户端拿到结果时，不仅有答案和引用，也能看到这次查询的执行过程。

为什么 `HybridSearch` 里有些内部组件调用时传的是 `trace=None`？这是为了避免重复打点。F3 的目标是形成一条清晰的查询链路记录，所以由编排层统一记录标准阶段名，比如 `dense_retrieval`、`sparse_retrieval`、`fusion`。这样后续 Dashboard 展示时会更稳定。

本阶段在 RAG 流程中的位置是“Query 链路观测层”。它不负责创造新的检索能力，而是让已有查询流程变得透明、可分析、可调试。


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