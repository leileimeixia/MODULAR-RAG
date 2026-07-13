# D4_rrf_fusion 学习笔记

## 1. 本阶段完成了什么

本阶段完成的是 RAG 查询流程里的“结果融合”模块，也就是 `RRFusion`。

在前两个检索阶段中，项目已经有了两条召回路径：

```text
DenseRetriever：根据语义相似度召回 chunk
SparseRetriever：根据关键词 BM25 召回 chunk
```

这两条路径各有优势。Dense 更擅长理解语义相近的问题，Sparse 更擅长命中明确关键词、术语、编号。D4 要解决的问题是：当两条路径都返回一批结果时，怎样把它们合并成一个统一排序。

本阶段使用的是 RRF，也就是 Reciprocal Rank Fusion。它不直接比较 dense 分数和 BM25 分数，因为两者的分数来源不同，绝对值没有可比性。RRF 只看“排名位置”，排名越靠前，加分越多。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/core/query_engine/fusion.py` | 实现 `RRFusion`，负责融合 dense/sparse 两路检索结果 |
| `src/core/query_engine/__init__.py` | 导出 `RRFusion` 和 `RRFusionError` |
| `tests/unit/test_fusion_rrf.py` | 验证 RRF 融合排序、top_k、rrf_k 配置、去重、异常输入和 trace |
| `DEV_SPEC.md` | 标记 D4 完成并更新总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 D4 进度表 |

## 3. 核心调用关系

```text
HybridSearch 或后续查询编排模块
  -> dense_retriever.retrieve(...)
  -> sparse_retriever.retrieve(...)
  -> RRFusion.fuse(dense_results, sparse_results, top_k)
  -> 返回融合后的 List[RetrievalResult]
```

当前 D4 只负责融合，不负责调用 dense 或 sparse。真正的查询编排会在 D5 `HybridSearch` 中完成。

`RRFusion.fuse()` 的内部流程是：

```text
接收 dense_results 和 sparse_results
  -> 校验输入必须是 RetrievalResult 列表
  -> 遍历每一路结果，根据 rank 计算 RRF 分数
  -> 相同 chunk_id 的结果累加分数
  -> 按融合分数排序
  -> 分数相同时按 best_rank 和 chunk_id 保证确定性
  -> 截取 top_k
```

## 4. 每个核心文件的作用

### 文件：`src/core/query_engine/fusion.py`

* 主要职责：把 dense 和 sparse 两路排名融合成一份统一结果。
* 关键类：`RRFusion`、`RRFusionError`。
* 输入是什么：`dense_results`、`sparse_results`、`top_k`、可选 `trace`。
* 输出是什么：融合排序后的 `List[RetrievalResult]`。
* 在项目中的作用：为后续 `HybridSearch` 提供统一排序能力。

RRF 的核心公式在这里：

```python
entry.score += 1.0 / (self.rrf_k + index)
```

其中 `index` 是当前结果在某一路召回列表里的排名，从 1 开始。排名越靠前，分母越小，贡献分越高。

如果同一个 `chunk_id` 同时出现在 dense 和 sparse 中，它的分数会被累加：

```text
chunk-a dense rank 1  -> 1 / (k + 1)
chunk-a sparse rank 2 -> 1 / (k + 2)
最终分数 = 两部分相加
```

这意味着：被多路检索同时命中的 chunk 会更容易排到前面。

`_FusionEntry` 是内部辅助结构：

```python
@dataclass
class _FusionEntry:
    result: RetrievalResult
    score: float = 0.0
    best_rank: int = 0
    routes: int = 0
```

它保存某个 chunk 的代表结果、融合分数、最好排名和命中路数。最终返回时仍然会转换回项目统一的 `RetrievalResult`。

排序规则是：

```python
key=lambda entry: (-entry.score, entry.best_rank, entry.result.chunk_id)
```

意思是：

1. 融合分数越高越靠前。
2. 分数相同，看谁在某一路中的最好排名更靠前。
3. 还相同，则按 `chunk_id` 排序，保证结果确定。

这种 deterministic 排序很重要。测试、调试、线上排查都需要同样输入得到同样输出。

### 文件：`src/core/query_engine/__init__.py`

* 主要职责：统一暴露 query_engine 包里的核心类。
* 本阶段新增：`RRFusion`、`RRFusionError`。
* 在项目中的作用：让其他模块可以通过 `from core.query_engine import RRFusion` 直接使用融合器。

### 文件：`tests/unit/test_fusion_rrf.py`

* 主要职责：验证 D4 的融合行为。
* 关键测试：
  * dense/sparse 两路结果能按 RRF 正确融合。
  * `top_k` 能限制最终返回数量。
  * `rrf_k` 可以从 settings 读取。
  * 同一路里重复的 chunk id 不会重复加分。
  * 分数打平时按 `chunk_id` 稳定排序。
  * 非法输入会抛出 `RRFusionError`。
  * trace 会记录 `rrf_fusion` 阶段。

测试里用 `_result()` 快速构造 `RetrievalResult`，这样可以把注意力集中在排序逻辑上，而不是构造复杂数据。

## 5. 新手重点理解

这一阶段最重要的是理解：为什么不能直接把 dense 分数和 sparse 分数相加。

Dense 分数通常来自向量相似度，比如 cosine similarity。Sparse 分数来自 BM25，反映关键词匹配情况。这两种分数的范围和含义都不同，直接相加会让排序不稳定，也很难解释。

RRF 换了一个思路：不看原始分数，只看排名。

```text
排名第 1：贡献 1 / (k + 1)
排名第 2：贡献 1 / (k + 2)
排名第 3：贡献 1 / (k + 3)
```

这样 dense 和 sparse 就站在同一个规则下比较了。

`rrf_k` 控制排名差距的影响程度。`k` 越大，第 1 名和第 10 名之间的差距会被压平；`k` 越小，靠前排名的优势越明显。本项目默认配置里是 `rrf_k: 60`，这是一个常见的保守值。

这个模块在 RAG 流程中的位置是：

```text
用户问题
  -> QueryProcessor
  -> DenseRetriever + SparseRetriever
  -> RRFusion
  -> 后续 Reranker 或最终返回
```

D4 的价值是把“两路召回”真正变成“一份可用结果”。没有 Fusion，dense 和 sparse 只能各自返回结果，后续模块不知道应该优先相信哪一路。加入 RRF 后，项目就具备了混合检索的核心排序能力。


# 整体架构与流程

以下是对 fusion.py 代码文件的完整解析：

文件定位
项目作用：该文件实现了检索结果融合（Rank Fusion）功能，专门用于处理多路召回（如稠密向量检索和稀疏关键词检索）后的结果合并。
所处层级：属于系统的核心层（core），具体位于查询引擎（query_engine）模块中。
核心职责：通过 RRF（Reciprocal Rank Fusion，倒数秩融合） 算法，将不同检索策略返回的排序列表进行科学融合，重新计算得分并排序，从而输出兼顾语义相关性和关键词匹配度的最终 Top-K 结果。
函数拆解
1. 辅助类与异常
RRFusionError：自定义异常类。当输入数据不合法或参数配置错误时抛出，便于上层捕获和处理融合过程中的错误。
_FusionEntry：内部数据类。用于在融合计算过程中暂存每个文档（Chunk）的中间状态，包含：原始结果对象、累计 RRF 得分、在所有检索路中的最佳排名、参与融合的路由（检索路）数量。
2. RRFusion 类核心方法
__init__(settings, rrf_k)：
目的：初始化 RRF 融合器。
输入：全局配置对象 settings 和可选的平滑参数 rrf_k。
核心功能：确定 RRF 算法中的常数 $k$（默认值为 60）。$k$ 值用于平滑排名差异，防止排名靠前的文档得分过高。如果 $k \le 0$ 则抛出异常。
fuse(dense_results, sparse_results, top_k, trace)：
目的：执行核心的融合逻辑。
输入：稠密检索结果列表、稀疏检索结果列表、需要返回的 Top-K 数量、可选的追踪对象 trace。
输出：融合并重新排序后的 RetrievalResult 列表。
核心功能：校验输入 -> 累加计算各路得分 -> 综合排序 -> 截取 Top-K -> 记录追踪日志。
_accumulate(entries, results)：
目的：计算单条检索链路中每个文档的 RRF 得分并累加。
输入：用于存储中间状态的字典 entries，单条检索结果列表 results。
核心功能：遍历结果列表，根据公式 $\frac{1}{k + rank}$ 计算得分，累加到对应文档的总分中，并记录该文档的最佳排名和出现次数。同时通过 seen_in_route 去重，防止同一路检索中重复文档重复计分。
3. 模块级辅助函数
_settings_rrf_k(settings)：从配置对象中安全地提取 rrf_k 参数，若未配置则返回默认值 60。
_validate_results(results, label)：校验输入的结果列表类型是否合法（必须是 list 且元素必须全是 RetrievalResult 对象）。
执行流程
初始化阶段：实例化 RRFusion 时，调用 init 确定算法参数 rrf_k。
触发融合：调用 fuse 方法传入稠密和稀疏两路结果。
数据校验：调用 _validate_results 确保两路输入数据格式正确，并检查 top_k 是否合法。
得分计算：
初始化空的 entries 字典。
调用 _accumulate 处理稠密结果，计算初始得分并记录最佳排名。
调用 _accumulate 处理稀疏结果，在原有基础上继续累加得分，更新最佳排名。
综合排序：对 entries 中的所有文档进行多维度排序。排序规则优先级为：RRF 总分降序 > 最佳排名升序 > 文档 ID 字典序（确保结果确定性）。
结果封装：截取排序后的前 top_k 个文档，封装成新的 RetrievalResult 对象列表。
链路追踪：如果传入了 trace 对象，则记录本次融合的阶段信息（如参数、各路输入数量、最终输出数量等）。
返回结果：将最终的 Top-K 列表返回给上层调用者。
场景示例
假设我们正在构建一个企业知识库问答系统，用户提问：“如何配置阿里云 OSS 的跨域访问？”

1. 多路召回阶段：

稠密检索（向量语义）：找到了 3 个语义相关的文档：
文档 A（排名 1）
文档 B（排名 2）
文档 C（排名 3）
稀疏检索（BM25 关键词）：找到了 3 个包含“OSS”、“跨域”关键词的文档：
文档 B（排名 1）
文档 D（排名 2）
文档 A（排名 3）
2. RRF 融合计算阶段（假设 rrf_k = 60）：

处理稠密结果：
A 得分：$1 / (60 + 1) \approx 0.01639$
B 得分：$1 / (60 + 2) \approx 0.01612$
C 得分：$1 / (60 + 3) \approx 0.01587$
处理稀疏结果（累加得分）：
B 得分累加：$0.01612 + 1 / (60 + 1) \approx 0.03251$
D 得分：$1 / (60 + 2) \approx 0.01612$
A 得分累加：$0.01639 + 1 / (60 + 3) \approx 0.03226$
3. 最终排序与输出：

综合得分排名：
文档 B (0.03251) —— 既在向量空间高度相关，又是关键词精准匹配，得分最高。
文档 A (0.03226) —— 同样双路命中，但稠密排名略低于 B。
文档 D (0.01612) —— 仅关键词命中。
文档 C (0.01587) —— 仅语义命中。
业务价值：通过 RRF 融合，系统成功将“语义相关”且“关键词精准”的文档 B 提拔到了第一位，避免了单一检索策略可能带来的偏差，为用户提供了最准确的配置指南。