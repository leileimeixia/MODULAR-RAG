# G2_document_manager 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `DocumentManager`，它是 Dashboard 后续“数据浏览”和“Ingestion 管理”的基础。

在前面的摄取流程中，一个文档摄取完成后，数据会分散存在多个地方：向量 chunk 存在 ChromaStore，关键词索引存在 BM25Indexer，图片文件和图片索引存在 ImageStorage，文件是否已处理的记录存在 SQLiteIntegrityChecker。这样做对底层模块来说很清晰，但对管理页面来说不方便，因为页面想做的是“查看一个文档”或“删除一个文档”，不想分别操作四个存储。

`DocumentManager` 的作用就是把这些分散的存储统一起来。它提供文档列表、文档详情、集合统计和删除文档这几个管理能力。后续 Dashboard 的数据浏览页和 Ingestion 管理页都会依赖它。

在整个 RAG 项目中，G2 不属于检索算法本身，而是属于“数据资产管理层”。它解决的是：文档摄取进系统之后，如何统一查看、统计和删除。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/document_manager.py` | 新增核心文档管理器，统一管理文档列表、详情、删除和统计 |
| `src/ingestion/__init__.py` | 导出 `DocumentManager` 及相关数据类型，方便其它模块导入 |
| `src/libs/vector_store/chroma_store.py` | 增加 `delete_by_metadata()`，支持按 metadata 删除向量记录 |
| `src/ingestion/storage/bm25_indexer.py` | 增加 `remove_document()`，支持从 BM25 索引中删除某个文档的 chunk |
| `src/libs/loader/file_integrity.py` | 增加 `list_processed()` 和 `remove_record()`，支持管理已处理文件记录 |
| `tests/unit/test_document_manager.py` | 新增 DocumentManager 单元测试 |
| `tests/integration/test_chroma_store_roundtrip.py` | 补充 ChromaStore metadata 删除测试 |
| `tests/unit/test_bm25_indexer_roundtrip.py` | 补充 BM25 删除文档后重建索引测试 |
| `tests/unit/test_file_integrity.py` | 补充完整性记录列表与删除测试 |
| `DEV_SPEC.md` | 更新 G2 完成状态 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步更新开发进度 |

## 3. 核心调用关系

```text
Dashboard 或管理脚本
  -> 调用 DocumentManager
  -> DocumentManager 读取 ChromaStore 中的 chunk 记录
  -> DocumentManager 读取 FileIntegrity 中的处理历史
  -> DocumentManager 读取 ImageStorage 中的图片索引
  -> 返回 DocumentInfo / DocumentDetail / CollectionStats
```

删除文档时的数据流是：

```text
DocumentManager.delete_document(source_path, collection)
  -> ChromaStore.delete_by_metadata({"source_path": source_path})
  -> BM25Indexer.remove_document(...)
  -> ImageStorage.delete_images(collection, doc_hash)
  -> SQLiteIntegrityChecker.remove_record(file_hash)
  -> 返回 DeleteResult
```

这条调用链的关键点是：用户只说“删除这个文档”，底层会自动协调多个存储，把同一个文档相关的数据尽量清理干净。

## 4. 每个核心文件的作用

### 文件：`src/ingestion/document_manager.py`

* 主要职责：统一管理已经摄取进系统的文档。
* 关键类 / 函数：
  * `DocumentInfo`：一个文档的摘要信息，比如 source_path、collection、file_hash、chunk_count、image_count。
  * `DocumentDetail`：文档详情，包含文档摘要、chunk 列表、图片列表、完整性记录。
  * `DeleteResult`：删除结果，记录四类存储分别删除了多少数据。
  * `CollectionStats`：集合维度统计，比如文档数、chunk 数、图片数。
  * `DocumentManager.list_documents()`：按 source_path 聚合 ChromaStore 中的 chunk，并结合完整性记录返回文档列表。
  * `DocumentManager.get_document_detail()`：根据 doc_id/source_path/file_hash 等找到文档，返回 chunk 和图片详情。
  * `DocumentManager.delete_document()`：跨 Chroma、BM25、ImageStorage、FileIntegrity 删除文档。
  * `DocumentManager.get_collection_stats()`：返回集合级别统计。
* 输入是什么：四个底层存储对象。
* 输出是什么：文档列表、文档详情、删除结果、集合统计。
* 在项目中的作用：作为 Dashboard 管理文档的统一后端服务。

### 文件：`src/libs/vector_store/chroma_store.py`

* 主要职责：本地向量记录存储。
* 本阶段新增函数：
  * `delete_by_metadata(filters)`：按 metadata 条件删除向量记录。
* 输入是什么：例如 `{"source_path": "xxx.pdf"}` 这样的过滤条件。
* 输出是什么：删除的向量记录数量。
* 在项目中的作用：让 DocumentManager 可以删除某个源文档对应的 dense chunk。

### 文件：`src/ingestion/storage/bm25_indexer.py`

* 主要职责：保存关键词倒排索引，用于 sparse retrieval。
* 本阶段新增函数：
  * `remove_document(source_path=None, collection=None, file_hash=None, doc_id=None)`：删除某个文档对应的 BM25 records，然后重建索引并保存。
* 输入是什么：文档来源路径、集合名、文件 hash 或文档 id。
* 输出是什么：删除的 BM25 记录数量。
* 在项目中的作用：删除文档时，避免关键词检索还能搜到已经删除的 chunk。

### 文件：`src/libs/loader/file_integrity.py`

* 主要职责：记录文件是否已经成功摄取，用于增量摄取和跳过重复文件。
* 本阶段新增函数：
  * `list_processed(status="success", collection=None)`：列出已处理文件，可按状态和 collection 过滤。
  * `remove_record(file_hash)`：删除某个文件 hash 的处理记录。
* 输入是什么：状态、集合名或文件 hash。
* 输出是什么：处理记录列表或删除数量。
* 在项目中的作用：让 DocumentManager 能知道哪些源文件已经摄取过，也能在删除文档时清掉“已处理”标记。

### 文件：`src/ingestion/__init__.py`

* 主要职责：统一导出 ingestion 层对外可用对象。
* 本阶段新增导出：
  * `DocumentManager`
  * `DocumentInfo`
  * `DocumentDetail`
  * `DeleteResult`
  * `CollectionStats`
  * `DocumentManagerError`
* 在项目中的作用：让其它模块可以直接从 `ingestion` 包导入文档管理能力。

## 5. 新手重点理解

这一阶段最重要的是理解“一个文档进入 RAG 系统后，不是只存在一个地方”。

比如你上传了一个 PDF，它经过 pipeline 后会变成多个 chunk。这些 chunk 的 dense vector 存在 ChromaStore；这些 chunk 的 sparse vector 会进入 BM25Indexer；如果文档里有图片，图片会保存到 ImageStorage；文件 hash 和处理状态会写进 SQLiteIntegrityChecker。也就是说，一个源文档被拆散到了多个存储里。

这就是为什么需要 `DocumentManager`。如果没有它，Dashboard 要删除一个文档时，就必须自己知道四个存储怎么删，这会让页面代码很混乱。现在页面只需要调用 `DocumentManager.delete_document()`，底层清理逻辑由管理器统一处理。

另一个重点是“按 source_path 聚合”。ChromaStore 里保存的是 chunk，不是文档。一个文档可能有很多条 chunk 记录。`DocumentManager.list_documents()` 会把这些 chunk 按 `metadata["source_path"]` 分组，再形成文档级别的 `DocumentInfo`。这一步就是把底层的 chunk 视角重新整理成用户更容易理解的文档视角。

删除时也要特别小心。删除 Chroma 只是删了向量召回，BM25 不删的话，关键词检索仍然可能命中旧文档；图片不删的话，磁盘会残留文件；完整性记录不删的话，下次重新上传同一个文件可能会被误判为已经处理过。所以 G2 的核心价值不是“写一个类”，而是建立跨存储的一致性管理入口。

这一步完成后，后续 G3 数据浏览器可以直接用 `DocumentManager` 展示文档和 chunk，G4 Ingestion 管理页也可以用它做删除和统计。它是阶段 G 从“只有页面框架”走向“真正能管理知识库数据”的关键一层。



# 整体架构与流程


文件定位
文件路径：src/ingestion/document_manager.py 项目作用：该文件是 RAG（检索增强生成）系统中“数据摄入（Ingestion）”模块的核心管理组件。 所处层级：处于业务逻辑层/服务层，向下封装并协调多种底层存储引擎。 核心职责：负责文档的“跨存储生命周期管理”。在 RAG 系统中，一份文档会被拆解并存入多个地方（如向量数据库、BM25 索引、图片存储、SQLite 完整性记录）。该文件确保在对文档进行查询、查看详情、删除等操作时，能够跨这些底层存储保持数据的一致性和协同操作。

函数拆解
1. 数据类（Dataclasses）
DocumentInfo：文档摘要信息。包含文档ID、来源路径、所属集合、文件哈希、分块数量、图片数量等基础元数据。
DocumentDetail：文档详细信息。在摘要基础上，增加了具体的文本分块（chunks）、图片列表和完整性校验记录。
DeleteResult：删除操作的结果统计。记录从向量库、BM25、图片库和完整性表中分别删除了多少条数据。
CollectionStats：集合级别的统计数据，用于仪表盘展示，包含文档数、分块数、图片数和来源列表。
2. 核心管理类 DocumentManager
init：初始化方法。接收并绑定四个底层存储组件：Chroma向量库、BM25索引器、图片存储、SQLite完整性检查器。
list_documents：列出文档。
输入：collection（可选，集合名称）。
输出：DocumentInfo 列表。
功能：从向量库获取记录并按来源路径分组，同时结合完整性记录，生成所有已摄入文档的摘要列表。
get_document_detail：获取文档详情。
输入：doc_id（文档ID、路径或哈希等标识）。
输出：DocumentDetail 对象。
功能：根据 ID 查找文档，并聚合该文档的所有文本分块、关联图片和完整性记录，返回完整视图。
delete_document：删除文档。
输入：source_path（源文件路径），collection（可选）。
输出：DeleteResult 对象。
功能：级联删除。从向量库、BM25索引、图片存储和完整性记录中彻底清除该文档的所有痕迹，并返回各部分的删除数量。
get_collection_stats：获取集合统计。
输入：collection（可选）。
输出：CollectionStats 对象。
功能：汇总特定集合下的文档总数、分块总数和图片总数。
_find_document（内部方法）：根据传入的 doc_id（支持ID、路径、哈希或文件名）在文档列表中精准匹配并返回 DocumentInfo。
_document_info（内部方法）：核心数据组装方法。整合向量记录、完整性记录和图片存储，计算出文件哈希、集合、图片数量等，构建出 DocumentInfo。
3. 模块级辅助函数
_filter_records：根据集合名称过滤向量记录。
_group_records_by_source：将向量记录按 source_path（来源路径）进行字典分组。
_records_for_source：提取特定来源路径的所有向量记录。
_integrity_for_source：从完整性检查器中查找特定来源路径的处理记录。
_count_record_images：统计向量记录元数据中关联的图片数量。
_remove_from_bm25：安全地从 BM25 索引中移除文档（忽略索引不存在的异常，防止阻塞删除流程）。
_first_text：工具函数，返回传入参数中第一个非空字符串，用于兜底取值。
执行流程
列表查询链路： list_documents -> 调用 _filter_records 过滤向量数据 -> 调用 _group_records_by_source 按文件路径分组 -> 遍历分组调用 _document_info -> _document_info 内部调用 _integrity_for_source 获取完整性信息，并调用图片存储统计图片数 -> 最终返回排序后的 DocumentInfo 列表。

详情查询链路： get_document_detail -> 调用 _find_document（内部遍历 list_documents）定位文档 -> 根据文档的 source_path 从向量库提取所有 chunks -> 从图片存储提取图片 -> 从完整性库提取记录 -> 组装成 DocumentDetail 返回。

删除操作链路： delete_document -> 调用 _document_info 确认文档存在并获取元数据 -> 依次调用 chroma_store.delete_by_metadata 删除向量 -> 调用 _remove_from_bm25 删除 BM25 索引 -> 调用 image_storage.delete_images 删除图片 -> 调用 file_integrity.remove_record 删除完整性记录 -> 汇总结果返回 DeleteResult。

场景示例
业务场景：运维工程师在 RAG 系统的管理后台（Dashboard）管理已上传的企业知识库文档。

查看文档列表： 工程师打开“文档管理”页面。系统后台调用 list_documents(collection="company_docs")。

系统从 Chroma 向量库拉取所有属于 company_docs 的文本块，按文件路径（如 docs/manual.pdf）分组。
结合 SQLite 中的文件处理记录，计算出每个文件的分块数、图片数。
最终在页面上展示出一个文档列表，显示 manual.pdf 包含 50 个文本块和 3 张图片。
查看文档详情： 工程师点击 manual.pdf 查看详情。系统调用 get_document_detail("manual.pdf")。

系统先通过 _find_document 确认文件存在。
接着从向量库把属于该 PDF 的 50 个文本块（chunks）全部取出来。
从图片存储中把提取出的 3 张图片信息拉取出来。
页面渲染出该文档的完整内容切片和图片预览。
删除过期文档： 工程师发现 manual.pdf 已过期，点击“删除”按钮。系统调用 delete_document("docs/manual.pdf", collection="company_docs")。

系统首先确认文件存在，获取其文件哈希（file_hash）。
清理向量库：从 Chroma 中删除这 50 个向量记录。
清理 BM25：从 BM25 倒排索引中移除该文档的关键词索引。
清理图片：根据 file_hash 从图片存储中删除那 3 张图片文件。
清理记录：从 SQLite 完整性表中删除该文件的处理记录。
最后，系统返回 DeleteResult，告诉前端：“向量删除50条，BM25删除1条，图片删除3张，完整性记录删除1条”，前端据此提示“文档已彻底清理”。