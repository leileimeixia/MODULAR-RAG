# C5_chunk_refiner 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 Transform 层的基础接口，并新增了 `ChunkRefiner`。

`ChunkRefiner` 的作用是对已经切好的 `Chunk` 做进一步清洗和增强。PDF 或 OCR 解析出来的文本经常会带有页眉、页脚、HTML 标记、多余空白、分隔线等噪声。如果这些噪声直接进入向量化阶段，会影响后续检索质量。

它在 RAG 摄取流程中的位置是 Chunking 之后、Embedding 之前：

```text
DocumentChunker
  -> List[Chunk]
  -> ChunkRefiner
  -> 更干净的 List[Chunk]
  -> DenseEncoder / SparseEncoder
```

本阶段还实现了最小版 `TraceContext`，用于记录 transform 阶段的处理信息。完整追踪能力会在后续 F 阶段增强。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/transform/base_transform.py` | 定义 Transform 统一抽象接口 |
| `src/ingestion/transform/chunk_refiner.py` | 实现规则去噪、可选 LLM refinement 和失败降级 |
| `src/ingestion/transform/__init__.py` | 导出 Transform 层公共类 |
| `src/core/trace/trace_context.py` | 实现最小版 TraceContext，用于阶段记录 |
| `src/core/trace/__init__.py` | 导出 TraceContext 和 TraceStage |
| `config/prompts/chunk_refinement.txt` | 增加 `{text}` 占位符，作为 LLM refinement prompt |
| `tests/fixtures/noisy_chunks.json` | 提供典型噪声文本样例 |
| `tests/unit/test_chunk_refiner.py` | 覆盖规则清洗、Mock LLM、失败降级、trace 和异常隔离 |
| `DEV_SPEC.md` | 将 C5 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> ChunkRefiner(settings?, llm?, prompt_path?, use_llm?)
      -> 读取 prompt
      -> 判断是否启用 LLM

ChunkRefiner.transform(chunks, trace?)
  -> 遍历每个 Chunk
      -> _rule_based_refine(chunk.text)
      -> 如果启用 LLM:
          -> _llm_refine(rule_text)
          -> 成功则使用 LLM 结果
          -> 失败则回退到规则结果
      -> 生成新的 Chunk
      -> 写入 metadata["refined_by"]
  -> trace.record_stage("chunk_refinement")
  -> 返回新的 List[Chunk]
```

这里的核心原则是：单个 chunk 处理失败，不应该阻塞整个 ingestion 流程。失败的 chunk 会保留原文，并在 metadata 里记录错误原因。

## 4. 每个核心文件的作用

### 文件：`src/ingestion/transform/base_transform.py`

* 主要职责：定义 Transform 层的统一接口。
* 关键函数 / 类：
  * `BaseTransform`：抽象基类。
  * `transform(chunks, trace)`：所有 transform 都要实现的方法。
  * `TransformError`：Transform 层统一异常类型。
* 输入是什么：
  * `list[Chunk]`
  * 可选 `trace`
* 输出是什么：
  * 处理后的 `list[Chunk]`
* 在项目中的作用：
  * 为后续 `MetadataEnricher`、`ImageCaptioner` 等 transform 模块提供统一形状。

### 文件：`src/ingestion/transform/chunk_refiner.py`

* 主要职责：清洗 chunk 文本，并可选调用 LLM 做进一步增强。
* 关键函数 / 类：
  * `ChunkRefiner`：chunk 清洗和增强入口。
  * `transform(chunks, trace)`：批量处理 chunks。
  * `_rule_based_refine(text)`：规则清洗文本。
  * `_llm_refine(text, trace)`：调用 LLM refinement，失败时返回 `None`。
  * `_load_prompt(prompt_path)`：加载 prompt，并保证存在 `{text}` 占位符。
  * `_replace_chunk(...)`：生成新的 Chunk，保留原 id/source_ref/offset，并更新 text 和 metadata。
* 输入是什么：
  * 原始 `Chunk`
  * 可选 LLM
  * 可选 prompt 文件
* 输出是什么：
  * 清洗后的 `Chunk`
* 在项目中的作用：
  * 提升进入 embedding 之前的文本质量，让向量检索更少受噪声干扰。

### 文件：`src/core/trace/trace_context.py`

* 主要职责：提供最小可用的 trace 记录能力。
* 关键函数 / 类：
  * `TraceContext`：保存 `trace_id` 和阶段列表。
  * `record_stage(name, method, details)`：记录一个处理阶段。
  * `TraceStage`：单个阶段的数据结构。
* 输入是什么：
  * 阶段名、方法名、详情字典。
* 输出是什么：
  * 保存在 `trace.stages` 中的阶段记录。
* 在项目中的作用：
  * 让 C5 能先记录基础处理过程，后续 F 阶段再扩展耗时、finish、JSON Lines 等完整能力。

### 文件：`tests/unit/test_chunk_refiner.py`

* 主要职责：验证 `ChunkRefiner` 的关键行为。
* 关键测试：
  * 去除页眉、页脚、分隔线。
  * 规范化多余空白。
  * 去除 HTML 和格式标记。
  * 保留 Markdown 代码块。
  * 干净文本不过度清洗。
  * Mock LLM 模式可以调用并写入 `refined_by: "llm"`。
  * LLM 失败时回退到规则结果。
  * 记录 trace stage。
  * 单个 chunk 异常不阻塞其他 chunk。
* 输入是什么：
  * 测试构造的 `Chunk`
  * `tests/fixtures/noisy_chunks.json`
  * Mock LLM
* 输出是什么：
  * pytest 断言结果。
* 在项目中的作用：
  * 保证文本清洗逻辑稳定，也保证 LLM 失败时 ingestion 不会崩掉。

## 5. 新手重点理解

`ChunkRefiner` 不是必须把文本改得“更漂亮”，它最重要的目标是让文本更适合检索。

比如页眉页脚、页码、HTML 注释、分隔线这些内容，对回答用户问题通常没有帮助，反而会污染 embedding。因此先做规则清洗，可以用低成本方式改善检索质量。

为什么还要支持 LLM？因为有些噪声不是简单正则能处理的，比如 OCR 错误、段落破碎、语义不完整。LLM 可以在保留事实的前提下对 chunk 做轻度整理。但 LLM 有成本，也可能失败，所以这里必须支持降级。

降级机制很关键：如果 LLM 失败，系统不能停止摄取。代码会回退到规则清洗结果，并在 metadata 里标记 `refined_by: "rule"` 和失败原因。这样后续排查时能知道这个 chunk 发生过什么。

当前 `TraceContext` 只是占位版。它先解决“能记录发生了什么”的问题；后续 F 阶段会把它升级为完整观测系统，包括耗时统计、finish、结构化日志和 Dashboard 展示。
