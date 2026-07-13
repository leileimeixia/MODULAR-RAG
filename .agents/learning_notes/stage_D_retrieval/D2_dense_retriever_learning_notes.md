# D2_dense_retriever 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `DenseRetriever`，它负责语义向量检索：把用户 query 转成 dense vector，然后调用向量数据库查询最相似的 chunk。

在 RAG 查询流程里，D1 的 `QueryProcessor` 负责把 query 预处理成 keywords 和 filters。D2 关注的是 dense route：

```text
query
  -> EmbeddingClient.embed([query])
  -> query vector
  -> VectorStore.query(vector, top_k, filters)
  -> RetrievalResult 列表
```

本阶段还新增了 `RetrievalResult`，作为后续 DenseRetriever、SparseRetriever、Fusion、HybridSearch 共同使用的统一检索结果结构。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/core/types.py` | 新增 `RetrievalResult` 数据契约 |
| `src/core/__init__.py` | 对外导出 `RetrievalResult` |
| `src/core/query_engine/dense_retriever.py` | 实现 dense 检索器 |
| `src/core/query_engine/__init__.py` | 对外导出 `DenseRetriever` 和 `DenseRetrieverError` |
| `tests/unit/test_dense_retriever.py` | 验证 dense 检索编排、异常和 trace |
| `tests/unit/test_core_types.py` | 补充 `RetrievalResult` 序列化和校验测试 |
| `DEV_SPEC.md` | 将 D2 标记为完成，并更新阶段 D 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> DenseRetriever(settings?, embedding_client?, vector_store?)
      -> 如果没有注入 embedding_client:
          -> EmbeddingFactory.create(settings)
      -> 如果没有注入 vector_store:
          -> VectorStoreFactory.create(settings)

DenseRetriever.retrieve(query, top_k, filters?, trace?)
  -> 校验 query / top_k / filters
  -> embedding_client.embed([query])
  -> 校验只返回一个 query vector
  -> vector_store.query(vector, top_k, filters)
  -> VectorQueryResult -> RetrievalResult
  -> trace.record_stage("dense_retrieval")
```

数据流可以理解成：

```text
用户问题
  -> 查询向量
  -> 向量数据库相似度检索
  -> 标准 RetrievalResult
```

## 4. 每个核心文件的作用

### 文件：`src/core/types.py`

- 主要职责：定义全链路共享的数据结构。
- 本阶段新增：
  - `RetrievalResult`
- 输入是什么：
  - `chunk_id`
  - `score`
  - `text`
  - `metadata`
- 输出是什么：
  - 可序列化的检索结果对象。
- 在项目中的作用：
  - 为 dense、sparse、hybrid 检索统一结果格式。

### 文件：`src/core/query_engine/dense_retriever.py`

- 主要职责：完成 dense route 的语义召回。
- 关键函数 / 类：
  - `DenseRetriever`：dense 检索主类。
  - `retrieve(query, top_k, filters, trace)`：执行 query embedding 和 vector store 查询。
  - `DenseRetrieverError`：输入或 embedding 结果异常时抛出的错误。
- 输入是什么：
  - 原始 query 字符串。
  - `top_k`
  - 可选 metadata filters。
  - 可选 `BaseEmbedding` 和 `BaseVectorStore`。
- 输出是什么：
  - `list[RetrievalResult]`
- 在项目中的作用：
  - 为后续 HybridSearch 提供 dense 检索候选结果。

### 文件：`tests/unit/test_dense_retriever.py`

- 主要职责：验证 DenseRetriever 的行为契约。
- 关键测试：
  - query 会被送入 embedding client。
  - embedding 返回的 vector 会被传给 vector store。
  - vector store 结果会转换成 `RetrievalResult`。
  - 空结果返回空列表。
  - 空 query、非法 top_k、embedding 数量不匹配、空向量都会报错。
  - 支持 trace 记录 `dense_retrieval` 阶段。
- 输入是什么：
  - `FakeEmbedding`
  - `FakeVectorStore`
  - `TraceContext`
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 保证 dense retrieval 只负责编排，不依赖真实 OpenAI 或 Chroma。

## 5. 新手重点理解

DenseRetriever 做的是“语义检索”。

关键词检索关注词是否出现；语义检索关注意思是否相近。比如用户问“如何启动摄取流程”，dense 检索可能找到“运行 ingest.py 导入文档”这类不完全同词但语义相关的 chunk。

为什么需要 embedding？因为向量数据库不能直接理解文字，它需要数字向量。`DenseRetriever` 先把 query 送给 `BaseEmbedding.embed([query])`，拿到 query vector，再用这个 vector 去向量库里查相似 chunk。

为什么输出不直接返回 `VectorQueryResult`？因为 `VectorQueryResult` 属于 vector store 层。Retrieval 层需要统一自己的结果对象，也就是 `RetrievalResult`。后续 SparseRetriever、Fusion 和 HybridSearch 都会围绕 `RetrievalResult` 工作。

为什么要校验 embedding 只返回一个向量？因为这里只传入一个 query。如果 embedding 返回 0 个或多个向量，说明 provider 或调用方式出了问题，继续查向量库会让错误更难定位。

这一阶段的核心价值是：让在线查询链路第一次具备 dense 语义召回能力，为后续 sparse 召回和 hybrid 融合做准备。





# 整体结构与流程

文件解析：dense_retriever.py
一、文件定位
维度	说明
项目作用	该文件实现了 RAG 系统中的稠密向量检索器（Dense Retriever），是查询引擎（Query Engine）模块的核心组件之一。
所处层级	位于 src/core/query_engine/ 层，属于业务核心层。它向下依赖 libs/embedding（向量编码库）和 libs/vector_store（向量存储库），向上为 RAG 编排层提供检索能力。
核心职责	接收用户的原始查询字符串 → 调用 Embedding 模型将其转为向量 → 在向量数据库中做近似最近邻（ANN）检索 → 返回带分数的检索结果列表。
简单来说：它就是把"人话"变成"向量"，再去向量库里"找最相似的文档片段"的那个模块。

二、函数拆解
1. DenseRetrieverError（异常类）
项目	说明
目的	自定义异常类型，专门用于标识稠密检索过程中出现的错误。
继承	继承自 ValueError，语义上表示"传入的值不合法或处理结果不合法"。
使用场景	当 query 为空、top_k ≤ 0、embedding 返回异常等情况下抛出。
2. DenseRetriever.__init__()（构造函数）
项目	说明
目的	初始化检索器，注入或自动创建 Embedding 客户端和向量存储客户端。
输入	settings：全局配置（可选）；embedding_client：已创建好的 Embedding 客户端（可选）；vector_store：已创建好的向量存储客户端（可选）。
输出	无返回值，完成实例属性绑定。
核心逻辑	如果调用者没有手动传入 embedding_client 或 vector_store，就通过各自的工厂类（EmbeddingFactory.create() / VectorStoreFactory.create()）根据 settings 自动创建。这是一种依赖注入 + 工厂兜底的设计模式，方便测试时 mock，也方便生产环境自动装配。
3. DenseRetriever.retrieve()（核心检索方法）
项目	说明
目的	接收原始查询文本，返回最相似的 top_k 个文档片段。
输入	query: str — 用户查询字符串；top_k: int — 返回结果数量；filters: dict — 可选的元数据过滤条件；trace — 可选的链路追踪对象。
输出	list[RetrievalResult] — 检索结果列表，每个结果包含 chunk_id、score、text、metadata。
核心功能	① 参数校验 → ② 调用 Embedding 编码 → ③ 向量数据库查询 → ④ 结果封装 → ⑤ 链路追踪记录。
内部步骤详解：

步骤	代码行为	说明
参数校验	检查 query 非空、top_k > 0、filters 类型	快速失败，避免无效请求浪费资源
向量编码	self.embedding_client.embed([query])	把查询文本包成列表传入（因为 embed 接口支持批量），返回结果必须恰好 1 个向量
向量校验	检查返回向量数量 = 1 且非空	防止 Embedding 模型异常返回空结果
向量检索	self.vector_store.query(vector, top_k, filters)	在向量库中做 ANN 检索，返回原始结果
结果封装	列表推导式转换为 RetrievalResult	把向量库的原始结果统一转换为项目内部的标准数据结构
链路追踪	trace.record_stage(...)	如果传入了 trace 对象，记录本次检索的关键信息（方法名、top_k、结果数、过滤条件），便于调试和监控
三、执行流程
用户调用 retrieve(query, top_k, filters, trace)
        │
        ▼
  ┌─────────────────┐
  │  参数校验        │  query 为空？top_k ≤ 0？filters 类型不对？
  │  (快速失败)      │  → 抛出 DenseRetrieverError
  └────────┬────────┘
           │ 校验通过
           ▼
  ┌─────────────────┐
  │  Embedding 编码  │  embedding_client.embed([query])
  │                  │  → 返回 [vector]
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  向量结果校验    │  向量数量 ≠ 1 或向量为空？
  │                  │  → 抛出 DenseRetrieverError
  └────────┬────────┘
           │ 校验通过
           ▼
  ┌─────────────────┐
  │  向量库检索      │  vector_store.query(vector, top_k, filters)
  │                  │  → 返回原始结果列表 results
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  结果封装        │  遍历 results → 转换为 RetrievalResult 对象列表
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  链路追踪记录    │  如果 trace 存在 → record_stage(...)
  └────────┬────────┘
           │
           ▼
     返回 retrieval_results
调用关系图：

DenseRetriever.retrieve()
    ├── EmbeddingFactory.create()  ──→  创建 embedding_client（构造阶段）
    ├── VectorStoreFactory.create() ──→  创建 vector_store（构造阶段）
    ├── self.embedding_client.embed()
    ├── self.vector_store.query()
    └── trace.record_stage()
四、场景示例
业务场景：智能客服知识库问答

假设你搭建了一个 RAG 智能客服系统，知识库中已经存储了大量产品FAQ文档片段（之前通过 ingest 流程导入并完成了向量化）。现在用户提了一个问题：

用户提问： "怎么重置密码？"

执行全过程：

python
# 1. 初始化检索器（通常在系统启动时完成一次）
retriever = DenseRetriever(settings=app_settings)
# 内部自动创建：
#   embedding_client → 比如调用 OpenAI 的 text-embedding-3-small 模型
#   vector_store     → 比如连接 Qdrant / Milvus 向量数据库

# 2. 发起检索
results = retriever.retrieve(
    query="怎么重置密码？",
    top_k=5,
    filters={"category": "account"},  # 只检索"账户"类别的文档
)

# ---- 内部发生了什么？ ----

# Step 1: 参数校验 ✅
#   query = "怎么重置密码？" → 非空字符串 ✅
#   top_k = 5 → 大于0 ✅
#   filters = {"category": "account"} → 是字典 ✅

# Step 2: Embedding 编码
#   调用 embedding_client.embed(["怎么重置密码？"])
#   → 返回 [[0.012, -0.034, 0.056, ...]]  (一个 1536 维的向量)

# Step 3: 向量校验 ✅
#   len(vectors) == 1 ✅
#   vector 非空 ✅

# Step 4: 向量库检索
#   调用 vector_store.query(
#       vector=[0.012, -0.034, ...],
#       top_k=5,
#       filters={"category": "account"}
#   )
#   → 向量库返回 5 个最相似的文档片段（按余弦相似度排序）

# Step 5: 结果封装
#   把向量库的原始结果转换为标准的 RetrievalResult 对象：
#   [
#     RetrievalResult(chunk_id="faq_042", score=0.91, text="重置密码请前往...", metadata={...}),
#     RetrievalResult(chunk_id="faq_017", score=0.87, text="如果您忘记了登录密码...", metadata={...}),
#     RetrievalResult(chunk_id="faq_089", score=0.83, text="密码重置链接有效期为...", metadata={...}),
#     ...
#   ]

# Step 6: 链路追踪
#   trace.record_stage("dense_retrieval", method="QdrantVectorStore",
#       details={"top_k": 5, "result_count": 5, "filters": {"category": "account"}})

# 3. 拿到结果后，交给下游（如 LLM 生成模块）进行回答
一句话总结： 这个文件就是 RAG 系统中"以文搜文"的核心引擎——把用户的自然语言问题变成数学向量，然后在向量数据库里找到语义最接近的知识片段，为后续的大模型回答提供上下文素材。