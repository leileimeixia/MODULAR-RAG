# D6_core_reranker 学习笔记

## 1. 本阶段完成了什么

本阶段完成的是 RAG 查询流程里的“重排编排层”，也就是 `CoreReranker`。

在 D5 之后，系统已经可以通过 `HybridSearch` 得到一批融合后的候选结果。D6 做的事情是：把这些候选结果交给 reranker 后端进行精排，让更相关的 chunk 排在更前面。

不过，Core 层不能直接依赖某一个具体 reranker。项目的 libs 层已经提供了可插拔的 reranker 后端，比如：

```text
NoneReranker：不重排，保持原顺序
CrossEncoderReranker：用 cross-encoder 风格 scorer 打分
LLMReranker：用 LLM 返回的 ranked_ids 重排
```

D6 的 `CoreReranker` 是一个适配层。它负责把 Core 层的 `RetrievalResult` 转成 libs 层需要的 `RerankCandidate`，调用具体 reranker 后端，再把 `RerankResult` 转回 `RetrievalResult`。

更重要的是，它实现了 fallback：如果 reranker 后端失败、超时或抛出异常，就回退到原来的融合排序，保证查询链路不会因为重排失败而整体不可用。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/core/query_engine/reranker.py` | 实现 Core 层 reranker 编排与 fallback |
| `src/core/query_engine/__init__.py` | 导出 `CoreReranker` 和 `CoreRerankerError` |
| `tests/unit/test_reranker_fallback.py` | 验证适配、回退、top_k、输入校验和 trace |
| `DEV_SPEC.md` | 标记 D6 完成并更新进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 D6 进度表 |

## 3. 核心调用关系

```text
HybridSearch.search(...)
  -> 返回融合后的 List[RetrievalResult]
  -> CoreReranker.rerank(query, candidates, top_k)
  -> RetrievalResult 转 RerankCandidate
  -> libs.reranker backend.rerank(...)
  -> RerankResult 转 RetrievalResult
  -> 返回重排结果
```

如果后端失败：

```text
CoreReranker.rerank(...)
  -> backend.rerank(...) 抛异常
  -> 捕获异常
  -> 返回 candidates[:top_k]
  -> trace 记录 fallback=True
```

这就是 D6 的核心价值：接入精排能力，同时保证精排失败时系统仍然可用。

## 4. 每个核心文件的作用

### 文件：`src/core/query_engine/reranker.py`

* 主要职责：连接 Core 层检索结果和 libs 层 reranker 后端。
* 关键类：`CoreReranker`、`CoreRerankerError`。
* 输入是什么：原始 query、`List[RetrievalResult]` 候选结果、可选 `top_k`、可选 trace。
* 输出是什么：重排后的 `List[RetrievalResult]`。
* 在项目中的作用：作为 Query 流程中 HybridSearch 之后的精排入口。

`CoreReranker.__init__()` 支持两种使用方式：

```python
CoreReranker(settings=settings)
```

这种方式会通过 `RerankerFactory.create(settings)` 创建真实后端。

```python
CoreReranker(backend=fake_backend)
```

这种方式适合测试，可以直接注入 fake reranker。

### `rerank()`

`rerank()` 是核心方法。它先校验 query 和 candidates：

```python
if not isinstance(query, str) or not query.strip():
    raise CoreRerankerError("query must be a non-empty string")
```

然后解析 `top_k`：

```python
limit = _resolve_top_k(top_k, self.settings)
```

如果调用方传了 `top_k`，优先用调用方的值；否则从 settings 的 `rerank.top_k` 中读取。

接着做数据适配：

```python
_to_rerank_candidates(candidates)
```

把：

```text
RetrievalResult(chunk_id, text, score, metadata)
```

转换成：

```text
RerankCandidate(id, text, score, metadata)
```

libs 层 reranker 返回的是 `RerankResult`，Core 层还需要再转换回来：

```python
_to_retrieval_results(rerank_results)
```

最终对外仍然返回 `RetrievalResult`，这样后续 CLI、MCP tool 或 Dashboard 不需要知道底层 reranker 的数据结构。

### fallback 逻辑

D6 最重要的一段代码是：

```python
except Exception as exc:
    fallback_results = candidates[:limit]
    self._record_trace(..., fallback=True, error=exc)
    return fallback_results
```

意思是：reranker 后端出错时，不把异常继续抛给用户，而是返回原来的候选顺序。

这很符合 RAG 系统的工程取舍。重排可以提高质量，但它不是必须成功的环节。只要 HybridSearch 已经拿到了候选结果，查询就可以继续返回。

### `_record_trace()`

这个方法负责记录 rerank 阶段的 trace：

```text
top_k
candidate_count
result_count
fallback
backend
error
```

如果后端失败，trace 中会出现：

```text
fallback: True
error: RuntimeError 或 TimeoutError 等
```

这对后续排查很有价值。用户看到结果返回了，但系统内部仍然能记录“这次重排失败并回退了”。

### 文件：`src/core/query_engine/__init__.py`

* 主要职责：统一导出 Query Engine 的核心组件。
* 本阶段新增：`CoreReranker`、`CoreRerankerError`。
* 在项目中的作用：后续可以直接通过 `from core.query_engine import CoreReranker` 使用重排入口。

### 文件：`tests/unit/test_reranker_fallback.py`

* 主要职责：验证 Core reranker 编排层的行为。
* 关键测试：
  * 能把 `RetrievalResult` 正确适配成 `RerankCandidate`。
  * 能把 `RerankResult` 转回 `RetrievalResult`。
  * 后端失败时返回原始候选顺序。
  * 未传 `top_k` 时使用 settings 中的 `rerank.top_k`。
  * 空候选不会调用后端。
  * 非法 query、非法 candidates、非法 top_k 会抛出 `CoreRerankerError`。
  * 成功和 fallback 都会记录 trace。

测试里使用 `FakeBackend` 代替真实 reranker，这样能专注验证 Core 层的适配和 fallback。

## 5. 新手重点理解

这一阶段最重要的是理解“Core 层为什么还要包一层 reranker”。

libs 层的 reranker 是可插拔能力层，它只关心：

```text
query + RerankCandidate -> RerankResult
```

而 Core 查询链路使用的是：

```text
RetrievalResult
```

所以 `CoreReranker` 要负责数据结构转换。它相当于一个翻译器，让 Core 层和 libs 层各自保持清晰边界。

第二个重点是 fallback。

在真实应用里，reranker 可能依赖本地模型、远程 LLM、cross-encoder 服务等。这些组件都有失败风险。如果 reranker 失败就让整个查询失败，用户体验会很差。

D6 的策略是：

```text
reranker 成功 -> 返回重排结果
reranker 失败 -> 返回原融合结果
```

这样系统优先追求可用性。重排是质量增强，不是单点阻断。

本阶段在 RAG 流程中的位置是：

```text
用户 query
  -> QueryProcessor
  -> DenseRetriever / SparseRetriever
  -> RRFusion
  -> CoreReranker
  -> 最终 Top-K 结果
```

完成 D6 后，查询主链路已经有了“召回 + 融合 + 可选精排 + 回退”的完整能力。下一阶段 D7 就可以把这套能力包装成命令行查询入口。




# 整体结构与流程

reranker.py 文件完整解析
一、文件定位
1. 项目中的作用
reranker.py 是 RAG（检索增强生成）系统中"重排序"环节的核心调度文件。在 RAG 流程中，系统会先从向量库或关键词索引中召回一批候选文档片段（chunks），但这些片段的排序可能不够精准。重排序（Rerank）的作用就是：用更精细的模型（如 Cross-Encoder）对这批候选结果重新打分、重新排序，把最相关的内容排到最前面，从而提升最终送给大模型的质量。

2. 所处层级
┌─────────────────────────────────────────────┐
│            应用层 / Pipeline                 │
├─────────────────────────────────────────────┤
│   core/query_engine/  ← 本文件所在层级       │
│   (核心编排层：负责串联各模块、做适配与兜底)   │
├─────────────────────────────────────────────┤
│   libs/reranker/                            │
│   (底层实现层：具体的重排模型调用)            │
└─────────────────────────────────────────────┘
本文件处于 core 层，属于"编排/胶水层"，不直接调用模型，而是把上层的 RetrievalResult 数据格式适配成底层 libs 层需要的 RerankCandidate 格式，调用完再把结果转换回来。
同时它承担容错兜底职责：如果底层重排模型挂了，就退回原始排序，保证系统不崩溃。
3. 核心职责
职责	说明
参数校验	校验 query、candidates、top_k 的合法性
格式适配	RetrievalResult ↔ RerankCandidate / RerankResult 互转
调度调用	调用底层 backend.rerank() 执行重排
异常兜底	后端失败时退回原始顺序，不中断主流程
链路追踪	把重排过程的关键信息写入 trace，便于调试和监控
二、函数拆解
2.1 CoreRerankerError（异常类）
python
class CoreRerankerError(ValueError):
    """Raised when rerank input cannot be handled."""
项目	说明
目的	自定义异常，表示"重排器的输入不合法"
继承	ValueError，语义上是"参数值有问题"
触发场景	query 为空、candidates 类型不对、top_k 为负数等
2.2 CoreReranker.__init__（构造函数）
python
def __init__(self, settings=None, backend=None):
项目	说明
输入	settings：配置对象（含 top_k 等参数）；backend：可选的底层重排器实例
输出	初始化后的 CoreReranker 实例
核心逻辑	如果没传 backend，就用 RerankerFactory.create(settings) 工厂方法自动创建一个
💡 设计意图：支持依赖注入，测试时可以传入 Mock 的 backend，生产环境则走工厂自动创建。

2.3 CoreReranker.rerank（核心方法 ⭐）
python
def rerank(self, query, candidates, top_k=None, trace=None):
项目	说明
输入	query：用户问题；candidates：候选文档列表；top_k：返回前 K 个；trace：追踪器
输出	list[RetrievalResult]：重排后的候选列表
核心逻辑	见下方详细流程
详细步骤：

校验 query：必须是非空字符串，否则抛异常
校验 candidates：调用 _validate_candidates() 检查类型
解析 top_k：调用 _resolve_top_k()，优先用传入值，否则从 settings 读
边界处理：
top_k < 0 → 抛异常
top_k == 0 或 candidates 为空 → 直接返回空列表
正常调用：
把 RetrievalResult 转成 RerankCandidate
调用 backend.rerank()
把结果转回 RetrievalResult
记录 trace
异常兜底：
如果 backend 抛任何异常，直接取原始 candidates 的前 top_k 个返回
记录 fallback 信息到 trace
💡 关键设计：except Exception 捕获所有异常，保证重排失败不会导致整个 RAG 流程中断——这是一种优雅降级策略。

2.4 CoreReranker._record_trace（内部方法）
python
def _record_trace(self, trace, top_k, candidate_count, result_count, fallback, error=None):
项目	说明
输入	trace 对象 + 本次重排的各种统计信息
输出	无返回值（直接写入 trace）
核心逻辑	如果 trace 不为 None，就把重排的元信息（top_k、候选数、结果数、是否降级、后端类型、错误类型）记录到 trace 的 rerank 阶段
💡 作用：让开发者能在调试时看到"重排用了什么模型、入参多少、是否降级"等关键信息。

2.5 _resolve_top_k（模块级私有函数）
python
def _resolve_top_k(top_k, settings):
项目	说明
输入	top_k：调用时传入的值（可能为 None）；settings：配置对象
输出	int：最终确定的 top_k 值
核心逻辑	优先用传入的 top_k；如果没传，从 settings.rerank.top_k 读取；都没有则默认 0
2.6 _validate_candidates（模块级私有函数）
python
def _validate_candidates(candidates):
项目	说明
输入	candidates：候选列表
输出	无返回值（校验失败抛异常）
核心逻辑	检查 candidates 是否为 list，且每个元素都是 RetrievalResult 类型
2.7 _to_rerank_candidates（格式转换函数）
python
def _to_rerank_candidates(candidates):
项目	说明
输入	list[RetrievalResult]：core 层的候选对象
输出	list[RerankCandidate]：libs 层需要的格式
核心逻辑	字段映射：chunk_id → id，text → text，score → score，metadata → metadata
💡 为什么需要转换？ core 层和 libs 层解耦，各自定义自己的数据结构，通过转换函数做适配。

2.8 _to_retrieval_results（格式转换函数）
python
def _to_retrieval_results(results):
项目	说明
输入	list[RerankResult]：libs 层返回的重排结果
输出	list[RetrievalResult]：core 层统一的数据结构
核心逻辑	反向映射：id → chunk_id，其余字段同名对应
三、执行流程
3.1 调用关系图
外部调用者 (Pipeline / QueryEngine)
        │
        ▼
  CoreReranker.rerank()
        │
        ├──① 校验 query（内联）
        │
        ├──② _validate_candidates(candidates)
        │
        ├──③ _resolve_top_k(top_k, settings)
        │
        ├──④ [边界判断] top_k==0 or candidates为空 → return []
        │
        ├──⑤ _to_rerank_candidates(candidates)   ← 格式转换
        │
        ├──⑥ backend.rerank(...)                  ← 调用底层重排模型
        │
        ├──⑦ _to_retrieval_results(results)       ← 格式转回
        │
        └──⑧ _record_trace(...)                   ← 记录追踪信息
              │
              └── [异常时] fallback → 返回原始 candidates[:top_k]
3.2 完整运行链路
┌──────────────────────────────────────────────────────────┐
│ 1. 接收输入：query + candidates + top_k + trace          │
├──────────────────────────────────────────────────────────┤
│ 2. 参数校验                                              │
│    ├─ query 非空？         否 → 抛 CoreRerankerError     │
│    ├─ candidates 合法？    否 → 抛 CoreRerankerError     │
│    └─ top_k >= 0？        否 → 抛 CoreRerankerError     │
├──────────────────────────────────────────────────────────┤
│ 3. 边界判断                                              │
│    └─ top_k==0 或 candidates 为空？ 是 → return []       │
├──────────────────────────────────────────────────────────┤
│ 4. 格式转换：RetrievalResult → RerankCandidate           │
├──────────────────────────────────────────────────────────┤
│ 5. 调用 backend.rerank()                                 │
│    ├─ 成功 → 格式转回 → 记录 trace → 返回结果            │
│    └─ 失败 → 取原始 candidates[:top_k] → 记录 fallback   │
│            → 返回降级结果                                 │
└──────────────────────────────────────────────────────────┘
四、场景示例
📖 场景：企业知识库问答系统
背景：某公司的员工问了一个问题："公司的年假政策是什么？"

🔹 第 1 步：检索阶段（已完成）
向量检索 + BM25 混合检索已经召回了 5 个候选文档片段：

序号	chunk_id	内容摘要	初始得分
1	c_001	"员工手册-考勤制度"	0.85
2	c_002	"2024年节假日通知"	0.78
3	c_003	"年假管理办法 v2.0"	0.72
4	c_004	"加班调休说明"	0.65
5	c_005	"入职指南-福利篇"	0.60
注意：初始得分是向量相似度分数，c_001 排第一，但实际上 c_003 "年假管理办法" 才是最相关的。

🔹 第 2 步：进入重排（本文件登场）
python
reranker = CoreReranker(settings=my_settings)
reranked = reranker.rerank(
    query="公司的年假政策是什么？",
    candidates=[c_001, c_002, c_003, c_004, c_005],
    top_k=3,
    trace=tracer,
)
🔹 第 3 步：参数校验
✅ query 是 "公司的年假政策是什么？"，非空字符串 → 通过
✅ candidates 是 list，每个元素都是 RetrievalResult → 通过
✅ top_k = 3，>= 0 → 通过
🔹 第 4 步：格式转换
_to_rerank_candidates() 把 5 个 RetrievalResult 转成 5 个 RerankCandidate：

python
RerankCandidate(id="c_001", text="员工手册-考勤制度...", score=0.85, metadata={...})
RerankCandidate(id="c_002", text="2024年节假日通知...", score=0.78, metadata={...})
# ... 以此类推
🔹 第 5 步：调用底层重排模型
python
backend.rerank(
    query="公司的年假政策是什么？",
    candidates=[5个RerankCandidate],
    top_k=3,
    trace=tracer,
)
底层 Cross-Encoder 模型对 query 和每个 candidate 做精细的语义匹配打分，结果：

chunk_id	重排得分	说明
c_003	0.95	"年假管理办法" 直接相关 → 跃升到第1
c_001	0.82	"考勤制度" 包含部分年假信息 → 第2
c_005	0.70	"入职指南-福利篇" 提到年假 → 第3
c_002	0.40	"节假日通知" 不太相关 → 被淘汰
c_004	0.30	"加班调休" 不相关 → 被淘汰
🔹 第 6 步：格式转回 + 记录 trace
_to_retrieval_results() 把结果转回 RetrievalResult，同时 trace 记录：

json
{
  "stage": "rerank",
  "method": "CoreReranker",
  "details": {
    "top_k": 3,
    "candidate_count": 5,
    "result_count": 3,
    "fallback": false,
    "backend": "CrossEncoderReranker"
  }
}
🔹 第 7 步：返回最终结果
python
[
    RetrievalResult(chunk_id="c_003", text="年假管理办法 v2.0...", score=0.95),
    RetrievalResult(chunk_id="c_001", text="员工手册-考勤制度...", score=0.82),
    RetrievalResult(chunk_id="c_005", text="入职指南-福利篇...", score=0.70),
]
这 3 个高质量的片段会被送给大模型，生成最终回答。

🔹 异常兜底场景
假设第 5 步时，重排模型服务宕机了：

python
except Exception as exc:
    fallback_results = candidates[:3]  # 直接取原始前3个
    # → [c_001, c_002, c_003]
系统不会崩溃，只是排序不够精准——优雅降级，用户依然能得到回答。

📊 总结一句话
reranker.py 就像一个质检调度员：它接收检索召回的候选文档，校验输入合法性，把它们"翻译"成底层模型能理解的格式，交给重排模型精细打分，再把结果"翻译"回来；如果模型出了问题，就退回原始排序保底，全程记录日志方便排查。