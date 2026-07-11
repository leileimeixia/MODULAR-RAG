# C6_metadata_enricher 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `MetadataEnricher`，它负责给每个 `Chunk` 补充检索友好的元数据：`title`、`summary` 和 `tags`。

在 RAG 系统里，chunk 只有正文还不够。后续检索、展示、引用、过滤和调试时，经常需要快速知道一段内容的标题、摘要和主题标签。`MetadataEnricher` 就是为这些场景准备的。

它在 Ingestion Pipeline 中的位置是 `ChunkRefiner` 之后、Embedding 之前：

```text
DocumentChunker
  -> ChunkRefiner
  -> MetadataEnricher
  -> DenseEncoder / SparseEncoder
```

本阶段提供了规则增强作为兜底逻辑，也支持可选 LLM 增强。即使 LLM 失败，也会回退到规则结果，不阻塞 ingestion。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/transform/metadata_enricher.py` | 实现规则元数据生成、可选 LLM 元数据生成和失败降级 |
| `src/ingestion/transform/__init__.py` | 导出 `MetadataEnricher` |
| `tests/unit/test_metadata_enricher_contract.py` | 验证规则增强、Mock LLM 增强、降级和 trace 记录 |
| `DEV_SPEC.md` | 将 C6 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> MetadataEnricher(settings?, llm?, use_llm?)

MetadataEnricher.transform(chunks, trace?)
  -> 遍历每个 Chunk
      -> _rule_metadata(chunk)
          -> 生成 title / summary / tags
      -> 如果启用 LLM:
          -> _llm_metadata(chunk, fallback_metadata, trace)
          -> 成功则使用 LLM metadata
          -> 失败则回退 rule metadata
      -> 生成新的 Chunk
      -> 更新 chunk.metadata
  -> trace.record_stage("metadata_enrichment")
  -> 返回新的 List[Chunk]
```

这里和 C5 `ChunkRefiner` 的设计一致：每个 chunk 独立处理，单个失败不影响其他 chunk。

## 4. 每个核心文件的作用

### 文件：`src/ingestion/transform/metadata_enricher.py`

* 主要职责：给 chunk 注入 `title`、`summary`、`tags`。
* 关键函数 / 类：
  * `MetadataEnricher`：元数据增强入口。
  * `transform(chunks, trace)`：批量增强 chunks。
  * `_rule_metadata(chunk)`：规则生成 title、summary、tags。
  * `_llm_metadata(chunk, fallback_metadata, trace)`：调用 LLM 返回 JSON 元数据。
  * `_derive_title(chunk, text)`：优先复用已有 title，否则从正文推导标题。
  * `_derive_summary(text)`：从正文首句生成摘要。
  * `_derive_tags(text, metadata)`：从 doc_type 和高频英文词生成标签。
  * `_validate_llm_metadata(payload)`：校验 LLM 返回的 JSON 是否包含非空 title、summary、tags。
* 输入是什么：
  * `list[Chunk]`
  * 可选 LLM
  * 可选 settings
* 输出是什么：
  * metadata 被增强后的 `list[Chunk]`
* 在项目中的作用：
  * 为后续向量化、检索过滤、引用展示和 Dashboard 可视化提供更丰富的语义信息。

### 文件：`src/ingestion/transform/__init__.py`

* 主要职责：导出 Transform 层公共入口。
* 关键函数 / 类：
  * `BaseTransform`
  * `ChunkRefiner`
  * `MetadataEnricher`
  * `TransformError`
* 输入是什么：无直接业务输入。
* 输出是什么：包级导入入口。
* 在项目中的作用：
  * 其他模块可以通过 `from ingestion.transform import MetadataEnricher` 直接使用。

### 文件：`tests/unit/test_metadata_enricher_contract.py`

* 主要职责：固定 MetadataEnricher 的行为契约。
* 关键测试：
  * 规则模式生成非空 `title/summary/tags`。
  * 保留原有 metadata，比如 `source_path/doc_type/chunk_index`。
  * 已有 `metadata["title"]` 时优先复用。
  * Mock LLM 模式可以生成语义 metadata。
  * LLM 返回包裹文本时也能提取 JSON。
  * LLM 失败或 JSON 无效时回退规则 metadata。
  * 支持 trace 记录。
  * 支持 settings dict 开启 LLM 模式。
* 输入是什么：
  * 测试构造的 `Chunk`
  * Mock LLM
* 输出是什么：
  * pytest 断言结果。
* 在项目中的作用：
  * 保证 metadata 增强稳定可靠，并确保 LLM 不可用时系统仍可继续处理。

## 5. 新手重点理解

`MetadataEnricher` 的目标不是改变 chunk 正文，而是给 chunk 补充“说明书”。

一个 chunk 的正文可能很长，也可能只是某个段落的一部分。加上 `title`、`summary`、`tags` 后，系统后面做检索、展示、调试时就更容易理解这段内容是什么。

规则模式是兜底。它不依赖外部服务，速度快、稳定、成本低。它会从文本里提取标题、首句摘要和关键词标签，保证每个 chunk 至少有基础 metadata。

LLM 模式用于生成更高质量的 metadata，比如更自然的摘要和更准确的标签。但 LLM 可能失败、超时、返回格式错误，也可能产生费用。所以代码必须先有规则兜底，再让 LLM 做增强。

本阶段还有一个重要习惯：保留原有 metadata。`source_path`、`doc_type`、`chunk_index` 这些字段来自前面的 Loader 和 Chunker，后续追溯来源时很重要，不能因为增强 metadata 就覆盖掉。

这一阶段的核心价值是：让 chunk 从“只有正文的一段文本”变成“带标题、摘要、标签和来源信息的检索单元”。
