# I4_interface_contract_tests 学习笔记

## 1. 本阶段完成了什么

本阶段做的是“接口一致性清理”。简单说，就是把项目里几个关键抽象的使用规则写得更明确，并用测试把这些规则固定下来。

在 RAG 项目中，很多模块都是可插拔的：向量库可以换，重排器可以换，评估器也可以换。可插拔的前提是大家遵守同一份接口契约。否则某个实现能跑，另一个实现一换上来就缺方法，问题会很隐蔽。

这次最核心的变化是：`ChromaStore` 已经支持 `delete_by_metadata()`，而 `DocumentManager` 也依赖这个方法删除某个文档的所有向量记录，所以 `BaseVectorStore` 也必须把这个方法写进抽象接口。这样以后新增 Qdrant、Milvus 等向量库实现时，Python 会强制它们也实现这个删除能力。

本阶段属于 RAG 工程的收口阶段，不是新增业务功能，而是把已经完成的能力用契约测试兜住，确保项目更稳定、更容易继续扩展。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/vector_store/base_vector_store.py` | 为向量存储抽象接口新增 `delete_by_metadata()`，让删除能力成为正式契约 |
| `tests/unit/test_vector_store_contract.py` | 补充 VectorStore 契约测试，覆盖按 metadata 删除和 provider 边界 |
| `tests/unit/test_reranker_factory.py` | 补充 Reranker 工厂与 `NoneReranker` 的边界测试 |
| `tests/unit/test_custom_evaluator.py` | 补充 CustomEvaluator 对空 golden ids、重复 ids、空 provider 的边界测试 |
| `tests/unit/test_document_manager.py` | 补充 DocumentManager 对空输入的错误处理测试 |
| `tests/unit/test_dense_retriever.py` | 同步测试替身 `FakeVectorStore`，让它符合新的 BaseVectorStore 契约 |
| `tests/unit/test_sparse_retriever.py` | 同步测试替身 `FakeVectorStore`，避免旧 Fake 与新接口不一致 |
| `tests/unit/test_vector_upserter_idempotency.py` | 同步测试替身 `FakeVectorStore`，确保全量测试可继续实例化 Fake |
| `DEV_SPEC.md` | 标记 I4 完成，更新项目进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步更新自动开发进度表 |

## 3. 核心调用关系

```text
DocumentManager.delete_document(source_path)
  -> chroma_store.delete_by_metadata({"source_path": source_path})
  -> 删除该文档对应的向量记录
  -> 同步删除 BM25 / 图片 / ingestion 历史

BaseVectorStore
  -> 规定所有向量库实现必须具备 upsert / query / get_by_ids / delete_by_metadata
  -> ChromaStore 实现这些方法
  -> 测试中的 FakeVectorStore 也必须实现这些方法
```

测试层面的关系可以这样理解：

```text
契约测试
  -> 明确接口应该接受什么输入
  -> 明确接口应该返回什么形状
  -> 明确错误输入应该抛什么异常
  -> 防止以后换实现或重构时破坏约定
```

## 4. 每个核心文件的作用

### 文件：`src/libs/vector_store/base_vector_store.py`

* 主要职责：定义所有向量存储后端必须遵守的统一接口。
* 关键函数 / 类：`BaseVectorStore`、`delete_by_metadata()`。
* 输入是什么：`filters: dict`，也就是要匹配的 metadata 条件。
* 输出是什么：删除的记录数量 `int`。
* 在项目中的作用：它是向量库可插拔的基础。只要某个向量库实现了这个接口，就可以被检索、入库、文档管理等模块统一调用。

### 文件：`tests/unit/test_vector_store_contract.py`

* 主要职责：验证向量存储接口的基本行为。
* 关键函数 / 类：`FakeVectorStore`、`test_vector_store_contract_delete_by_metadata_matches_all_filters()`。
* 输入是什么：构造好的 `VectorRecord` 和 metadata 过滤条件。
* 输出是什么：期望删除数量正确，剩余记录正确。
* 在项目中的作用：确保所有向量库实现都应该按同样方式处理删除、查询、按 id 获取等行为。

### 文件：`tests/unit/test_reranker_factory.py`

* 主要职责：验证重排器工厂和 no-op 重排器的边界行为。
* 关键函数 / 类：`NoneReranker`、`RerankerFactory`。
* 输入是什么：候选结果列表、`top_k`、provider 配置。
* 输出是什么：结果顺序、metadata、错误异常都符合预期。
* 在项目中的作用：保证关闭 rerank 时系统不会改变候选结果语义；配置错误时能尽早报错。

### 文件：`tests/unit/test_custom_evaluator.py`

* 主要职责：验证自定义评估器的指标计算边界。
* 关键函数 / 类：`CustomEvaluator.evaluate()`。
* 输入是什么：查询、召回 chunk id、golden chunk id。
* 输出是什么：`hit_rate`、`mrr`、`precision` 和 details。
* 在项目中的作用：让评估结果更可信。比如没有 golden ids 时不能误判为命中；重复 id 时也要明确当前计算规则。

### 文件：`tests/unit/test_document_manager.py`

* 主要职责：验证文档管理器跨存储操作的边界输入。
* 关键函数 / 类：`DocumentManager.get_document_detail()`、`DocumentManager.delete_document()`。
* 输入是什么：文档 id 或 source path。
* 输出是什么：正常返回详情或删除结果；空字符串输入抛出清晰错误。
* 在项目中的作用：DocumentManager 是 Dashboard 文档列表、详情、删除功能背后的协调层，输入校验可以防止界面层传入脏数据后造成难排查的问题。

## 5. 新手重点理解

接口契约可以理解成“模块之间的约法三章”。比如 `DocumentManager` 不应该关心底层是 Chroma、Qdrant 还是 Milvus，它只需要知道：向量库对象一定有 `delete_by_metadata()`。这就是抽象接口的价值。

为什么要把 `delete_by_metadata()` 放进 `BaseVectorStore`？因为这个方法已经被文档删除链路依赖了。如果只在 `ChromaStore` 里有，而抽象类里没有，未来别人新增一个向量库实现时可能完全不知道还需要实现删除方法，直到 Dashboard 删除文档时报错才发现。

为什么测试里的 `FakeVectorStore` 也要改？因为 Fake 不是随便写的假对象，它代表测试场景下的真实接口替身。抽象类新增方法后，Fake 不实现就不能被实例化，这正好提醒我们：测试替身也必须和真实接口保持一致。

为什么这阶段不主要写业务代码？因为项目已经进入端到端验收和文档收口阶段，这时更重要的是把已有能力稳定下来。契约测试像是给系统补上“使用说明书 + 自动检查器”，以后改代码时，只要接口被破坏，测试会立刻提醒。

在 RAG 流程中，本阶段横跨多个环节：向量存储属于 Ingestion 和 Retrieval 的基础设施；Reranker 属于检索后的精排；Evaluator 属于评估闭环；DocumentManager 属于 Dashboard 管理链路。I4 的意义就是把这些关键环节的接口边界统一收紧，为最后的全链路 E2E 验收做准备。
