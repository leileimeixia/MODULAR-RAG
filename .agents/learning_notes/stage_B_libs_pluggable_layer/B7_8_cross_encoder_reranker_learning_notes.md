# B7.8_cross_encoder_reranker 学习笔记

## 1. 本阶段完成了什么

本阶段给项目实现了 Cross-Encoder Reranker，也就是另一种“对候选 chunk 重新打分排序”的方式。

和 LLM Reranker 不同，Cross-Encoder Reranker 的核心思想是：对每一组 `(query, candidate_text)` 单独打一个相关性分数，然后按分数从高到低排序。后续如果接真实 cross-encoder 模型，它通常就是输入“问题 + 候选文本”，输出一个相关性分数。

当前阶段为了保证项目可跑、测试稳定，先实现了一个可注入 scorer 的结构。测试中可以传入 fake scorer；默认情况下使用 `LexicalOverlapScorer` 做简单词重叠评分，作为占位可跑实现。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/reranker/cross_encoder_reranker.py` | 实现 CrossEncoderReranker 和默认 LexicalOverlapScorer |
| `src/libs/reranker/reranker_factory.py` | 注册 `cross-encoder` provider |
| `src/libs/reranker/__init__.py` | 对外导出 cross-encoder 相关类 |
| `tests/unit/test_cross_encoder_reranker.py` | 使用 mock scorer 测试排序和错误处理 |
| `DEV_SPEC.md` | 标记 B7.8 完成，更新阶段进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 阶段进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> RerankerFactory.create(settings)
  -> settings.rerank.provider == "cross_encoder"
  -> 创建 CrossEncoderReranker
  -> CrossEncoderReranker.rerank(query, candidates)
  -> scorer.score(query, candidate.text)
  -> 给每个 candidate 得到一个分数
  -> 按分数降序排序
  -> 返回 RerankResult 列表
```

数据流可以理解为：

```text
query + candidates
  -> 遍历每个 candidate
  -> 调用 scorer 计算相关性分数
  -> 校验分数必须是数字
  -> 按 score 从高到低排序
  -> 截取 top_k
```

## 4. 每个核心文件的作用

### 文件：`src/libs/reranker/cross_encoder_reranker.py`

* 主要职责：实现基于 scorer 的候选结果重排。
* 关键类：
  * `CrossEncoderReranker`：执行打分和排序。
  * `CrossEncoderRerankerError`：表示 scorer 失败或输入不合法。
  * `CrossEncoderScorer`：定义 scorer 协议，只要求有 `score(query, text)` 方法。
  * `LexicalOverlapScorer`：默认可跑的简单词重叠 scorer。
* 输入是什么：`query: str` 和 `candidates: list[RerankCandidate]`。
* 输出是什么：`list[RerankResult]`。
* 在项目中的作用：为 retrieval 阶段提供一个可替换的本地/托管 rerank 后端结构。

### 文件：`src/libs/reranker/reranker_factory.py`

* 主要职责：根据 provider 名称创建具体 reranker。
* 本阶段新增逻辑：`"cross-encoder": CrossEncoderReranker`。
* 输入是什么：完整 `Settings` 或单独的 `RerankSettings`。
* 输出是什么：`CrossEncoderReranker` 实例。
* 在项目中的作用：让配置里的 `rerank.provider: cross_encoder` 或 `cross-encoder` 可以路由到该实现。

### 文件：`src/libs/reranker/__init__.py`

* 主要职责：统一导出 reranker 模块公共类。
* 本阶段新增导出：
  * `CrossEncoderReranker`
  * `CrossEncoderRerankerError`
  * `LexicalOverlapScorer`
* 在项目中的作用：让其它模块可以直接从 `libs.reranker` 导入 cross-encoder 相关能力。

### 文件：`tests/unit/test_cross_encoder_reranker.py`

* 主要职责：用 fake scorer 测试 cross-encoder reranker。
* 覆盖点：
  * `RerankerFactory` 能创建 `CrossEncoderReranker`。
  * 注入 scorer 后能按分数排序。
  * `top_k` 生效。
  * 默认 `LexicalOverlapScorer` 行为确定。
  * scorer 超时会被包装成清晰错误。
  * scorer 返回非数字会报错。
  * 空 query 和非法 top_k 会报错。

## 5. 新手重点理解

Cross-Encoder Reranker 可以理解成“逐条候选结果重新打分”。它不会像向量检索那样只看向量相似度，而是把 query 和 candidate text 放在一起判断相关性。

为什么要支持注入 scorer？因为真实 cross-encoder 可能来自本地模型、远程服务或第三方库。通过注入 scorer，`CrossEncoderReranker` 本身不用关心模型怎么加载，只关心拿到分数后如何排序。这也让测试变得简单可靠。

为什么默认提供 `LexicalOverlapScorer`？这是一个占位可跑实现。它不是最终高质量 reranker，但能让 provider 在没有真实模型时也能运行，方便后续 Core 层先把流程串起来。

为什么 timeout 要变成明确错误？因为后续 Core 层 D6 会实现 fallback。如果 cross-encoder 超时，系统可以捕获这个错误，然后退回到原始排序或 NoneReranker，避免整个查询失败。

本阶段在 RAG 流程中的位置是“检索结果精排”。它和 LLM Reranker 是可替换关系，都用于提升最终提供给回答模型的上下文质量。
