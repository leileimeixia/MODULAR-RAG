# C4_document_chunker 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `DocumentChunker`，它负责把一个完整的 `Document` 转换成多个 `Chunk`。

注意，这一层不是重新实现文本切分算法。真正的文本切分仍然由 `libs.splitter` 负责；`DocumentChunker` 做的是业务适配：把纯文本切分结果包装成项目统一的 `Chunk` 对象，并补齐 metadata、chunk id、source_ref、offset 和图片引用信息。

它在 RAG 摄取流程中的位置是 Loader 之后、Embedding 之前：

```text
PdfLoader
  -> Document
  -> DocumentChunker
  -> List[Chunk]
  -> 后续 Transform / Embedding / Store
```

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/chunking/document_chunker.py` | 实现 `Document -> List[Chunk]` 的业务适配 |
| `src/ingestion/chunking/__init__.py` | 导出 `DocumentChunker` 和 `DocumentChunkerError` |
| `tests/unit/test_document_chunker.py` | 验证 chunk id、metadata、source_ref、图片引用分发和配置驱动切分 |
| `DEV_SPEC.md` | 将 C4 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> DocumentChunker(settings)
      -> SplitterFactory.create(settings)
      -> 得到具体 splitter

DocumentChunker.split_document(document)
  -> splitter.split_text(document.text)
  -> 遍历每段 chunk_text
      -> 生成稳定 chunk id
      -> 继承 Document.metadata
      -> 添加 chunk_index
      -> 分发当前 chunk 引用到的图片 metadata
      -> 计算 start_offset / end_offset
      -> 创建 Chunk(source_ref=document.id)
  -> 返回 List[Chunk]
```

测试中也允许注入 `FakeSplitter`，这样可以只测试 `DocumentChunker` 的业务转换逻辑，不被真实 splitter 的切分算法影响。

## 4. 每个核心文件的作用

### 文件：`src/ingestion/chunking/document_chunker.py`

* 主要职责：把 `Document` 转换成多个符合 `core.types.Chunk` 契约的对象。
* 关键函数 / 类：
  * `DocumentChunker`：文档切块业务适配器。
  * `split_document(document)`：主入口，返回 `list[Chunk]`。
  * `_generate_chunk_id(doc_id, index, text)`：根据文档 ID、序号和文本生成稳定 chunk ID。
  * `_inherit_metadata(document, chunk_index, chunk_text)`：继承文档 metadata，并按 chunk 文本分发图片引用。
  * `_find_offset(document_text, chunk_text, cursor)`：定位 chunk 在原文中的起止位置。
  * `_image_refs_in_text(text)`：扫描 `[IMAGE: id]` 占位符。
* 输入是什么：
  * `Document` 对象。
  * settings 或外部注入的 splitter。
* 输出是什么：
  * `list[Chunk]`。
* 在项目中的作用：
  * 连接纯文本 splitter 和后续 RAG 业务对象，是 Ingestion Pipeline 中非常关键的适配层。

### 文件：`src/ingestion/chunking/__init__.py`

* 主要职责：提供 chunking 包的公共导入入口。
* 关键函数 / 类：
  * `DocumentChunker`
  * `DocumentChunkerError`
* 输入是什么：无直接业务输入。
* 输出是什么：包级导出的类。
* 在项目中的作用：
  * 让其他模块可以通过 `from ingestion.chunking import DocumentChunker` 使用切块能力。

### 文件：`tests/unit/test_document_chunker.py`

* 主要职责：固定 `DocumentChunker` 的业务行为。
* 关键测试：
  * 使用注入的 `FakeSplitter` 创建 chunks。
  * chunk id 具有唯一性和确定性。
  * chunk metadata 继承自 document metadata，并添加 `chunk_index`。
  * 图片引用只分发给包含对应 `[IMAGE: id]` 的 chunk。
  * chunk 包含 `start_offset` 和 `end_offset`。
  * 通过不同 splitter 配置可以影响 chunk 数量。
  * 非 `Document` 输入会抛出 `DocumentChunkerError`。
* 输入是什么：
  * 构造出来的 `Document` 和 `ImageRef`。
* 输出是什么：
  * pytest 断言结果。
* 在项目中的作用：
  * 保证后续 transform、embedding、storage 能拿到稳定、可追溯的 `Chunk`。

## 5. 新手重点理解

`libs.splitter` 和 `DocumentChunker` 的职责不一样。

`libs.splitter` 只关心一件事：把一段字符串切成多段字符串。它不关心文档来源、不关心图片、不关心 metadata，也不关心数据库要怎么存。

`DocumentChunker` 关心的是业务语义。它要把 splitter 返回的字符串变成真正能在 RAG 系统里流转的 `Chunk` 对象。每个 chunk 都要知道自己来自哪个文档、在文档中的顺序是什么、源文件路径是什么、有没有引用图片。

稳定 chunk id 很重要。因为后续向量库、BM25 索引、引用返回都需要用 chunk id 来识别一段内容。如果同一份文档每次切分都产生不同 ID，后续增量更新和结果追踪会很难做。

图片引用按需分发也很重要。不能把整个文档的全部图片都塞进每个 chunk，否则后续 `ImageCaptioner` 不知道当前 chunk 真正关联哪张图。这里通过扫描 `[IMAGE: id]` 占位符，只把当前 chunk 实际引用的图片写入 `chunk.metadata["images"]`。

这一阶段的核心价值是把“纯文本切分”升级成“可追溯、可入库、可继续处理的业务 chunk”。
