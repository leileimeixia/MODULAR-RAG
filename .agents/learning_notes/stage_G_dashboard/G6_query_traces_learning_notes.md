# G6_query_traces 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 Dashboard 的 Query 追踪页面，也就是查询链路的可视化排查页面。

前面 D 阶段已经完成了查询链路：QueryProcessor、DenseRetriever、SparseRetriever、RRFusion、CoreReranker。F3 又给 query 链路加了 trace 打点，可以记录 query_processing、dense_retrieval、sparse_retrieval、fusion、hybrid_search、rerank 等阶段。G6 的任务，就是把这些 query trace 从 JSONL 日志里读出来，并在 Dashboard 里展示。

现在 Query Traces 页面可以查看查询历史，筛选 trace，查看 Dense/Sparse/Fusion 的召回数量和耗时，也可以查看 Rerank 的 backend、候选数、结果数、fallback 状态等信息。

在整个 RAG 项目中，G6 属于查询链路的可观测性页面。它不改变检索逻辑，而是帮助你理解“为什么这次查询返回了这些结果”以及“Dense、Sparse、Fusion、Rerank 各自起了什么作用”。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/dashboard/services/trace_service.py` | 增强 TraceService，新增 query trace 列表、详情、Dense/Sparse/Fusion 对比、Rerank 摘要 |
| `src/observability/dashboard/pages/query_traces.py` | 实现 Query Traces 页面，展示 query 历史、检索对比、rerank 摘要和 stage details |
| `tests/unit/test_dashboard_trace_service.py` | 补充 query trace 解析测试，验证 retrieval comparison 和 rerank summary |
| `tests/unit/test_dashboard_app.py` | 补充 Query Traces 页面渲染测试 |
| `DEV_SPEC.md` | 更新 G6 完成状态 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步更新开发进度 |

## 3. 核心调用关系

```text
用户打开 Dashboard 的 Query Traces 页面
  -> query_traces.render(st)
  -> 调用 TraceService.list_query_traces()
  -> TraceService 读取 logs/traces.jsonl
  -> 过滤 trace_type == "query"
  -> 生成 query trace 历史列表
  -> 页面展示查询历史、完成数、失败数
```

查看某条 query trace 详情时：

```text
用户选择某个 trace_id
  -> query_traces.py 调用 TraceService.get_query_trace(trace_id)
  -> TraceService 读取该 trace 的 stages
  -> 提取 dense_retrieval / sparse_retrieval / fusion / hybrid_search
  -> 生成 retrieval_comparison
  -> 提取 rerank stage
  -> 生成 rerank_summary
  -> 页面展示召回对比、rerank 摘要和 stage details
```

## 4. 每个核心文件的作用

### 文件：`src/observability/dashboard/services/trace_service.py`

* 主要职责：读取 JSONL trace，并把原始 trace 转换成页面容易展示的数据。
* 本阶段新增或增强的函数：
  * `list_query_traces()`：返回 query 类型 trace 的历史摘要。
  * `get_query_trace(trace_id)`：返回某条 query trace 的详情，并附加检索对比和 rerank 摘要。
  * `_retrieval_comparison(stages)`：提取 Dense、Sparse、Fusion、Hybrid Final 的 result_count、elapsed_ms、method、failed。
  * `_rerank_summary(stages)`：提取 rerank backend、candidate_count、result_count、top_k、fallback、error。
  * `_find_stage(stages, stage_name)`：从 stages 里找到指定阶段。
* 输入是什么：`traces.jsonl` 文件里的 query trace。
* 输出是什么：query trace 摘要、retrieval comparison、rerank summary。
* 在项目中的作用：让 Dashboard 能看懂 query 链路 trace，而不只是展示原始 JSON。

### 文件：`src/observability/dashboard/pages/query_traces.py`

* 主要职责：渲染 Query Traces 页面。
* 关键函数：
  * `render(st, trace_service=None)`：页面入口，加载 query trace 历史，支持搜索和选择详情。
  * `_render_query_detail(st, detail)`：展示 Dense/Sparse/Fusion 对比、Rerank 摘要、Stage Details。
  * `_filter_traces(traces, query)`：按 trace_id、query、started_at、status 过滤历史列表。
* 输入是什么：Streamlit 对象，以及可选的 `TraceService`。
* 输出是什么：一个可查看 query 历史和查询链路细节的 Dashboard 页面。
* 在项目中的作用：帮助排查查询效果，比如 Dense 召回是否为空、Sparse 是否失败、Fusion 后结果数是否合理、Rerank 是否 fallback。

### 文件：`tests/unit/test_dashboard_trace_service.py`

* 主要职责：测试 trace 服务对 query trace 的解析能力。
* 本阶段新增测试：
  * 构造 query trace，包含 dense_retrieval、sparse_retrieval、fusion、rerank。
  * 验证 `retrieval_comparison` 是否正确提取各路线的结果数和耗时。
  * 验证 `rerank_summary` 是否正确提取 backend、candidate_count 等字段。
* 在项目中的作用：保证 query trace 解析逻辑稳定。

### 文件：`tests/unit/test_dashboard_app.py`

* 主要职责：测试 Dashboard 页面渲染逻辑。
* 本阶段新增内容：
  * fake `QueryTraceService`。
  * 验证 Query Traces 页面展示指标、历史表格、Dense/Sparse 对比表格、柱状图和 Rerank JSON。
* 在项目中的作用：不用启动真实 Streamlit，也能确认页面的核心逻辑能跑通。

## 5. 新手重点理解

这一阶段最重要的是理解 Query Trace 是在解释“检索为什么这样工作”。

一次 RAG 查询通常不是一步完成的。它会先处理 query，然后走 dense_retrieval 语义召回，再走 sparse_retrieval 关键词召回，再用 fusion 把两路结果融合，最后可能经过 rerank 重新排序。用户最后看到的答案只是结果，但调试时真正重要的是中间过程。

`TraceService.get_query_trace()` 做的事情，就是把这些中间过程从 trace 里提取出来，整理成两个核心视图：`retrieval_comparison` 和 `rerank_summary`。

`retrieval_comparison` 重点回答这些问题：

* Dense 召回了多少条？
* Sparse 召回了多少条？
* Fusion 后剩多少条？
* 哪一路失败了？
* 每一路耗时是多少？

`rerank_summary` 重点回答这些问题：

* 用了哪个 rerank backend？
* rerank 前有多少候选？
* rerank 后返回多少结果？
* 有没有 fallback？
* 如果失败，错误类型是什么？

这些信息对于 RAG 调试很关键。比如用户问一个专有名词，Dense 可能召回效果一般，但 Sparse 很强；如果 Fusion 后结果数变少，可能是过滤条件太强；如果 Rerank fallback，说明重排后端没有正常工作。G6 页面就是为了让这些问题能在 Dashboard 里一眼看到。

从阶段 G 的角度看，G6 也是 Dashboard 的最后一块核心页面。完成后，系统已经具备系统总览、数据浏览、摄取管理、Ingestion Trace、Query Trace 这些本地管理能力，阶段 G 的可视化管理平台闭环基本完成。
