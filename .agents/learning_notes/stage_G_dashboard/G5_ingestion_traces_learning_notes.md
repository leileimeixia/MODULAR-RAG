# G5_ingestion_traces 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 Dashboard 的 Ingestion 追踪页面。

前面 F 阶段已经完成了 Trace 基础设施：`TraceContext` 可以记录每次 ingestion 的阶段信息，`TraceCollector` 可以把 trace 写入 `traces.jsonl`。G5 的任务，就是把这些 JSONL 日志读取出来，在网页里展示成“摄取历史”和“阶段耗时详情”。

现在页面可以看到所有 ingestion trace 的历史列表，包括 trace_id、开始时间、总耗时、状态、源文件、文档 id 等；点击某条 trace 后，可以看到每个阶段的耗时，比如 load、split、embed、upsert、bm25_index，并展开查看每个阶段的 details。

在整个 RAG 项目中，G5 属于可观测性可视化层。它不改变摄取流程本身，而是帮助你理解摄取流程到底发生了什么、哪一步慢、哪一步失败。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/dashboard/services/trace_service.py` | 实现 TraceService，负责读取 JSONL trace、筛选 ingestion trace、整理摘要和详情 |
| `src/observability/dashboard/pages/ingestion_traces.py` | 实现 Ingestion Traces 页面，展示历史列表、统计指标、阶段耗时和 stage details |
| `tests/unit/test_dashboard_trace_service.py` | 新增 TraceService 单元测试，验证 JSONL 读取、排序、状态识别和详情解析 |
| `tests/unit/test_dashboard_app.py` | 更新 Dashboard 页面测试，验证 Ingestion Traces 页面可用 fake Streamlit 渲染 |
| `DEV_SPEC.md` | 更新 G5 完成状态 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步更新开发进度 |

## 3. 核心调用关系

```text
用户打开 Dashboard 的 Ingestion Traces 页面
  -> ingestion_traces.render(st)
  -> 调用 TraceService.list_ingestion_traces()
  -> TraceService 读取 logs/traces.jsonl
  -> 逐行解析 JSON
  -> 过滤 trace_type == "ingestion"
  -> 生成 trace 历史摘要
  -> 页面展示历史表格和统计指标
```

查看某条 trace 详情时：

```text
用户选择某个 trace
  -> ingestion_traces.py 取出 trace_id
  -> TraceService.get_ingestion_trace(trace_id)
  -> TraceService 找到原始 trace
  -> 整理 stages 为页面可展示的 rows
  -> 页面展示 stage timing 表格、bar chart 和 details
```

## 4. 每个核心文件的作用

### 文件：`src/observability/dashboard/services/trace_service.py`

* 主要职责：读取并整理 trace 日志。
* 关键类 / 函数：
  * `TraceService`：Dashboard trace 数据服务。
  * `list_traces(trace_type=None)`：列出 trace 摘要，并支持按类型筛选。
  * `list_ingestion_traces()`：专门返回 ingestion trace。
  * `get_trace(trace_id)`：返回某条 trace 的完整详情。
  * `get_ingestion_trace(trace_id)`：返回某条 ingestion trace，防止拿错 query trace。
  * `_read_traces()`：读取 JSONL 文件并逐行解析。
  * `_trace_summary()`：把原始 trace 整理成历史表格需要的摘要。
  * `_stage_rows()`：把 stages 整理成阶段列表。
  * `_trace_status()`：根据 stage 判断 trace 是 completed、failed、skipped 还是 unknown。
* 输入是什么：`traces.jsonl` 文件路径。
* 输出是什么：trace 摘要列表或单条 trace 详情字典。
* 在项目中的作用：作为 trace 日志和 Dashboard 页面之间的适配层。

### 文件：`src/observability/dashboard/pages/ingestion_traces.py`

* 主要职责：渲染 Ingestion 追踪页面。
* 关键函数：
  * `render(st, trace_service=None)`：页面入口，加载 ingestion trace 历史并处理选择详情。
  * `_render_trace_detail(st, detail)`：展示单条 trace 的状态、时间、总耗时、阶段耗时表格、柱状图和 details。
* 输入是什么：Streamlit 对象，以及可选的 `TraceService`。
* 输出是什么：可查看 ingestion 历史和阶段详情的 Dashboard 页面。
* 在项目中的作用：让 F 阶段记录下来的 trace 真正变成可视化排查工具。

### 文件：`tests/unit/test_dashboard_trace_service.py`

* 主要职责：验证 TraceService 的数据解析和格式化逻辑。
* 关键测试：
  * 只列出 ingestion trace，并按时间倒序。
  * 能识别 completed 和 failed 状态。
  * 能返回某条 trace 的 stage detail。
  * 遇到非法 JSONL 会抛出清晰错误。
* 在项目中的作用：保证 trace 文件格式变化或页面需求变化时，解析层不容易悄悄坏掉。

### 文件：`tests/unit/test_dashboard_app.py`

* 主要职责：验证 Dashboard 页面渲染逻辑。
* 本阶段变化：
  * 增加 fake `TraceService`。
  * 增加 fake Streamlit 的 `bar_chart()`。
  * 验证 Ingestion Traces 页面可以展示指标、历史表格、阶段耗时和 expander。
* 在项目中的作用：不启动真实 Streamlit，也能确认页面核心逻辑能跑通。

## 5. 新手重点理解

这一阶段最重要的是理解“trace 日志”和“页面展示”之间需要一个转换层。

`traces.jsonl` 里的每一行都是一个原始 JSON 对象，它适合机器写入和读取，但不适合直接展示给用户。用户想看的不是一大坨 JSON，而是：这次摄取有没有成功？用了多久？哪一步最慢？失败发生在哪个阶段？所以 `TraceService` 会把原始 trace 整理成摘要和详情两种结构。

摘要用于历史列表，比如 trace_id、status、started_at、source_path、stage_count。详情用于展开查看，比如每个 stage 的 name、method、elapsed_ms、details。这样页面可以分两层展示：先看整体，再看细节。

另一个重点是状态判断。trace 本身不一定直接写一个 `status` 字段，所以代码会根据 stage 来推断：如果有 `ingestion_complete` 就是 completed；如果有 `ingestion_failed` 或 stage 里 `failed=True` 就是 failed；如果有 `ingestion_skip` 就是 skipped。这个设计让页面可以兼容当前 trace 结构。

从 RAG 工程角度看，G5 很有价值。摄取链路通常比想象中复杂：文件加载、切块、图片保存、向量化、入库、BM25 索引都可能出问题。没有 trace 页面时，只能翻日志；有了 G5，就可以在 Dashboard 里快速定位是哪一步慢、哪一步失败、处理了哪个文件。

这一步也为后续 G6 Query Traces 打下基础。`TraceService` 现在已经支持通用 `list_traces(trace_type)` 和 `get_trace(trace_id)`，G6 可以复用它来展示 query 链路。



# 整体结构与流程
文件定位
文件路径：src/observability/dashboard/services/trace_service.py

项目作用与层级： 该文件位于项目的可观测性（Observability） -> 仪表盘（Dashboard） -> 服务层（Services）。它是连接底层日志数据与前端 Dashboard 页面的核心桥梁。

核心职责： 负责从底层的 JSONL（JSON Lines）格式的 Trace（追踪）日志文件中读取原始数据，进行解析、过滤、排序，并将其格式化为前端页面易于渲染的结构化字典数据。主要服务于“追踪列表”和“追踪详情”页面的数据展示。

函数拆解
1. TraceService 类方法
init
作用：初始化服务，确定要读取的 Trace 日志文件路径。
输入：trace_file（直接指定的文件路径，可选），settings_path（配置文件路径，默认 config/settings.yaml）。
输出：无，将解析后的文件路径保存在 self.trace_file 中。
list_traces
作用：获取 Trace 摘要列表，默认按时间最新到最旧排序。
输入：trace_type（可选，用于过滤特定类型的 Trace，如 "ingestion"）。
输出：格式化后的 Trace 摘要字典列表。
get_trace
作用：根据 ID 获取单个 Trace 的完整详情。
输入：trace_id（字符串）。
输出：包含摘要信息、阶段详情和原始数据的完整字典。若找不到则抛出 TraceServiceError。
list_ingestion_traces
作用：快捷方法，专门获取“文档摄入（ingestion）”类型的 Trace 列表。
输入：无。
输出：摄入类型的 Trace 摘要列表（内部调用 list_traces）。
get_ingestion_trace
作用：快捷方法，获取单个摄入 Trace 的详情，并校验其类型是否确实为 "ingestion"。
输入：trace_id。
输出：摄入类型的 Trace 详情字典。
_read_traces
作用：底层核心方法，负责读取 JSONL 文件并逐行解析为 Python 字典。
输入：无（使用实例属性 self.trace_file）。
输出：原始 Trace 字典列表。遇到 JSON 解析错误会抛出异常。
2. 辅助函数（模块级）
_trace_file_from_settings：从 YAML 配置文件中读取 trace_file 的路径配置，若读取失败则回退到默认路径。
_trace_summary：将原始 Trace 字典转换为摘要字典（提取 ID、类型、时间、总耗时、状态、源文件路径等关键信息）。
_trace_detail：将原始 Trace 字典转换为详情字典（在摘要基础上，增加 stages 阶段列表和 raw 原始数据）。
_stage_rows：解析 Trace 中的 stages（处理阶段）列表，将其格式化为包含索引、名称、方法、耗时、是否失败等字段的字典列表。
_trace_status：根据各个阶段的状态，推断整个 Trace 的最终状态（如 failed, skipped, completed, unknown）。
_first_stage_detail：从阶段详情（details）中提取第一个匹配指定 key 的字符串值（常用于提取 source_path 或 document_id）。
_trace_sort_key：提取 Trace 的 started_at 或 finished_at 时间戳，用于列表排序。
执行流程
初始化链路：
实例化 TraceService -> 调用 _trace_file_from_settings 解析配置文件 -> 确定最终的 trace_file 物理路径。
列表查询链路：
调用 list_traces (或 list_ingestion_traces) -> 调用 _read_traces 读取并解析 JSONL 文件 -> 按 trace_type 过滤数据 -> 对每条数据调用 _trace_summary 生成摘要 -> 使用 _trace_sort_key 进行倒序排序 -> 返回列表。
详情查询链路：
调用 get_trace (或 get_ingestion_trace) -> 调用 _read_traces 遍历寻找目标 trace_id -> 找到后调用 _trace_detail -> _trace_detail 内部调用 _stage_rows 解析处理阶段，调用 _trace_status 计算整体状态，调用 _first_stage_detail 提取关键元数据 -> 组装并返回完整详情字典。
场景示例
业务场景：用户在 Dashboard 的“文档摄入监控”页面，查看某次 PDF 文档上传的处理全过程。

全流程串联：

加载列表：用户打开页面，前端发起请求。后端实例化 TraceService，调用 list_ingestion_traces()。
读取与格式化：_read_traces() 读取 traces.jsonl 文件。假设文件中有 10 条记录，其中 3 条是 ingestion 类型。_trace_summary 被调用 3 次，提取出这 3 次摄入任务的摘要（如：文件名 manual.pdf，状态 completed，耗时 1200ms）。列表按时间倒序返回给前端渲染成表格。
查看详情：用户点击了 manual.pdf 这一行，前端携带 trace_id 请求详情。后端调用 get_ingestion_trace(trace_id)。
深度解析：找到对应记录后，_trace_detail 开始工作。_stage_rows 解析出该次任务的 4 个阶段：读取文件、文本分块、向量化、存入向量库。_trace_status 检查这 4 个阶段都没有失败标记，且存在 ingestion_complete 阶段，于是判定整体状态为 completed。_first_stage_detail 提取出 source_path 为 uploads/manual.pdf。
结果返回：最终返回一个包含基础信息、4 个阶段的详细耗时与状态、以及原始 JSON 数据的字典。前端据此渲染出一个漂亮的时间轴或步骤进度图，让用户清晰看到文档是如何一步步被处理入库的。


# 整体结构与流程

文件解析：ingestion_traces.py
一、文件定位
维度	说明
文件路径	src/observability/dashboard/pages/ingestion_traces.py
所处层级	表现层（Presentation Layer）—— Streamlit Dashboard 的一个页面模块
核心职责	负责渲染"文档摄取链路追踪"页面，将后端 TraceService 提供的 Trace 数据以可视化方式展示给用户，包括：汇总指标、历史列表、单条 Trace 详情（阶段耗时、阶段明细）
依赖关系	依赖 observability.dashboard.services.trace_service.TraceService 获取数据，依赖 Streamlit（st）进行 UI 渲染
简单来说，这个文件就是**"给运维/开发人员看的监控面板页面"**，让你能直观看到每次文档上传过程中，每个环节花了多久、有没有失败。

二、函数拆解
1. render(st, trace_service=None)
项目	说明
作用	页面主入口函数，负责渲染整个 Ingestion Traces 页面
输入	st：Streamlit 模块引用；trace_service：可选的 TraceService 实例（方便测试注入）
输出	无返回值，直接通过 st.* 方法渲染 UI
核心功能	① 加载所有 Trace 列表 → ② 展示汇总指标（总数/成功/失败） → ③ 渲染 Trace 历史表格 → ④ 提供下拉框让用户选择某条 Trace → ⑤ 加载并渲染该 Trace 的详细信息
关键逻辑拆解：

容错设计：加载 Trace 列表和加载 Trace 详情分别用 try/except 包裹，即使某条详情加载失败，历史列表仍然可见。
下拉选择：通过拼接 started_at | status | trace_id 作为 label，让用户能直观区分不同 Trace。
委托渲染：详情部分委托给 _render_trace_detail() 函数处理，保持主函数简洁。
2. _render_trace_detail(st, detail)
项目	说明
作用	渲染单条 Trace 的详细信息（私有辅助函数）
输入	st：Streamlit 模块引用；detail：单条 Trace 的完整字典数据
输出	无返回值，直接渲染 UI
核心功能	① 展示 Trace 基本信息（状态、起止时间、总耗时、来源路径） → ② 以表格+柱状图展示各阶段耗时 → ③ 以可折叠面板展示每个阶段的详细数据
关键逻辑拆解：

基本信息区：用 st.write 逐行展示 Trace 元信息。
Stage Timings：将各阶段数据整理成表格，同时用 st.bar_chart 生成柱状图，直观对比各阶段耗时。
Stage Details：用 st.expander 为每个阶段创建可折叠面板，默认收起，点击展开后显示该阶段的 method 和 details（JSON 格式），方便深入排查。
三、执行流程
用户访问 Ingestion Traces 页面
         │
         ▼
   render(st, trace_service)
         │
         ├──① 初始化 TraceService（若未注入则新建）
         │
         ├──② service.list_ingestion_traces()
         │       │
         │       ├── 成功 → 继续
         │       └── 失败 → st.error() 提示并 return
         │
         ├──③ 判断 traces 是否为空
         │       └── 空 → st.info() 提示并 return
         │
         ├──④ 渲染汇总指标（Traces / Completed / Failed）
         │
         ├──⑤ 渲染 Trace 历史表格（st.dataframe）
         │
         ├──⑥ 生成下拉选择框（st.selectbox）
         │       └── 用户选择某条 Trace → 获取 trace_id
         │
         ├──⑦ service.get_ingestion_trace(trace_id)
         │       │
         │       ├── 成功 → 继续
         │       └── 失败 → st.error() 提示并 return
         │
         └──⑧ _render_trace_detail(st, detail)
                 │
                 ├── 展示 Trace 基本信息
                 │
                 ├── 渲染 Stage Timings 表格 + 柱状图
                 │
                 └── 渲染 Stage Details 折叠面板
四、场景示例
场景：用户上传了一份 PDF 文档，想看看处理过程中每个环节的表现。

用户操作：运维人员小李打开 Dashboard，点击"Ingestion Traces"页面。

页面加载：render() 被调用，TraceService 从 JSONL 日志文件中读取到 5 条 Trace 记录。

汇总展示：页面顶部显示三个指标卡：

Traces: 5（总共 5 次摄取）
Completed: 4（4 次成功）
Failed: 1（1 次失败）
历史列表：下方表格展示 5 条 Trace 的摘要信息（trace_id、状态、开始时间等）。

选择详情：小李注意到有一条状态为 failed 的记录，通过下拉框选择了它：

2024-01-15 10:30:00 | failed | abc-123-def
详情渲染：_render_trace_detail() 被调用，展示该 Trace 的详细信息：

基本信息：状态 failed，开始时间 2024-01-15 10:30:00，总耗时 1523 ms，来源 uploads/report.pdf
Stage Timings：表格+柱状图显示各阶段耗时：
stage	method	elapsed_ms	failed
file_read	read_file	120	False
chunking	split_chunks	350	False
embedding	generate_embeddings	1020	False
storage	save_to_vector_db	33	True
Stage Details：小李展开第 4 阶段"storage"的折叠面板，看到 details 中的错误信息：Connection refused: vector_db host unreachable。
问题定位：小李据此判断是向量数据库连接问题，通知基础设施团队排查，问题快速定位解决。

总结：这个文件就是一个**"摄取链路追踪的可视化看板"**，把后端记录的每次文档处理过程，以指标、表格、图表、可折叠详情的形式呈现出来，帮助开发和运维人员快速了解系统运行状况、定位性能瓶颈或失败原因。