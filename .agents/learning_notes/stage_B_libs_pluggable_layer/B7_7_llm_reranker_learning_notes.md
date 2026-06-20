# B7.7_llm_reranker 学习笔记

## 1. 本阶段完成了什么

本阶段给项目实现了 LLM Reranker，也就是“用大模型对候选 chunk 重新排序”的能力。

在 RAG 检索中，前面的 dense/sparse 检索会先召回一批候选文本片段，但这些候选结果的顺序不一定最符合用户问题。Reranker 的作用就是在候选结果基础上再做一次精排，把更相关的 chunk 排到前面。

这次实现的 `LLMReranker` 会读取 `config/prompts/rerank.txt` 作为提示词基础，然后把 query 和候选 chunk 列表发给注入的 LLM。LLM 必须返回严格 JSON，例如：

```json
{"ranked_ids": ["candidate-id"]}
```

这样代码就可以根据 `ranked_ids` 对候选结果重新排序。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/reranker/llm_reranker.py` | 实现 LLMReranker |
| `src/libs/reranker/reranker_factory.py` | 注册 `llm` provider |
| `src/libs/reranker/__init__.py` | 对外导出 `LLMReranker` 和异常类型 |
| `tests/unit/test_llm_reranker.py` | 使用 mock LLM 测试 rerank 行为 |
| `DEV_SPEC.md` | 标记 B7.7 完成，更新阶段进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 阶段进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> RerankerFactory.create(settings)
  -> settings.rerank.provider == "llm"
  -> 创建 LLMReranker
  -> LLMReranker.rerank(query, candidates)
  -> 构造 prompt
  -> 调用 llm.chat(messages)
  -> 解析 {"ranked_ids": [...]}
  -> 按 id 重排 candidates
  -> 返回 RerankResult 列表
```

数据流可以理解为：

```text
query + candidates
  -> candidates 转成 JSON payload
  -> 和 rerank prompt 拼成用户消息
  -> LLM 返回 ranked_ids
  -> 校验 JSON 格式和 id 合法性
  -> 排序并补齐未返回的候选项
  -> 截取 top_k
```

## 4. 每个核心文件的作用

### 文件：`src/libs/reranker/llm_reranker.py`

* 主要职责：实现基于 LLM 的候选结果重排。
* 关键类：
  * `LLMReranker`：执行 prompt 构造、LLM 调用和结果排序。
  * `LLMRerankerError`：表示 LLM rerank 输出不合法或运行条件不足。
  * `ChatClient`：定义最小 LLM 协议，只要求有 `chat(messages)` 方法。
* 关键函数：
  * `rerank()`：对外入口，返回重排后的 `RerankResult`。
  * `_load_prompt()`：读取 `config/prompts/rerank.txt`。
  * `_build_prompt()`：把 query、top_k、candidates 拼成提示词。
  * `_parse_ranked_ids()`：解析 LLM 返回 JSON。
  * `_rank_candidates()`：根据 ranked_ids 重排候选项。
* 输入是什么：`query: str` 和 `candidates: list[RerankCandidate]`。
* 输出是什么：`list[RerankResult]`。
* 在项目中的作用：为 retrieval 阶段提供可选精排能力。

### 文件：`src/libs/reranker/reranker_factory.py`

* 主要职责：根据 provider 名称创建具体 reranker。
* 本阶段新增逻辑：`"llm": LLMReranker`。
* 输入是什么：完整 `Settings` 或单独的 `RerankSettings`。
* 输出是什么：`LLMReranker` 实例。
* 在项目中的作用：让配置里的 `rerank.provider: llm` 可以生效。

### 文件：`src/libs/reranker/__init__.py`

* 主要职责：统一导出 reranker 模块公共类。
* 本阶段新增导出：
  * `LLMReranker`
  * `LLMRerankerError`
* 在项目中的作用：让其它模块可以通过 `from libs.reranker import LLMReranker` 使用。

### 文件：`tests/unit/test_llm_reranker.py`

* 主要职责：使用 fake LLM 测试 reranker，不调用真实模型。
* 覆盖点：
  * `RerankerFactory` 能创建 `LLMReranker`。
  * LLM 返回 `ranked_ids` 后，候选结果能按 id 重排。
  * `top_k` 生效。
  * 没有注入 LLM 时运行会给出清晰错误。
  * 非 JSON 输出会报错。
  * schema 不符合要求会报错。
  * 返回未知 candidate id 会报错。

## 5. 新手重点理解

Reranker 和 Retriever 的区别是：Retriever 负责“先找一批可能相关的结果”，Reranker 负责“把这批结果重新排顺序”。Retriever 更像粗筛，Reranker 更像精筛。

为什么要求 LLM 返回 JSON？因为自然语言输出很难稳定解析。如果 LLM 说“我认为 B 最相关，然后是 A”，程序还要猜它是什么意思。JSON 的 `ranked_ids` 可以让程序直接按 id 排序，稳定、可测试。

为什么要注入 LLM？因为单元测试不应该真的调用模型。通过注入 fake LLM，测试可以固定返回结果，例如 `{"ranked_ids": ["b", "a"]}`，这样排序行为就能稳定验证。

为什么未知 id 要报错？因为如果 LLM 返回了不存在的 candidate id，说明输出不可信。直接忽略可能掩盖问题，所以这里选择明确报错。

本阶段在 RAG 流程中的位置是“检索结果精排”。它位于 Dense/Sparse 检索和 Fusion 之后、最终回答生成之前，用来提升最终上下文质量。
