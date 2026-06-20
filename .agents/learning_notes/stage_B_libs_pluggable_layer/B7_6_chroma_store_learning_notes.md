# B7.6_chroma_store 学习笔记

## 1. 本阶段完成了什么

本阶段给项目实现了默认的向量存储后端：`ChromaStore`。它负责把文本 chunk、向量和 metadata 保存起来，并支持后续用查询向量找回最相似的记录。

这里的类名和 provider 仍然叫 `ChromaStore` / `chroma`，但当前实现先采用本地 JSON 文件持久化，而不是直接引入真实 `chromadb` 依赖。这样项目可以先跑通 `upsert -> query` 的完整闭环，后续如果要接真正的 ChromaDB，也可以在这个适配器内部替换存储实现。

在 RAG 流程中，本阶段位于“向量存储与向量检索”位置：Embedding 把文本变成向量后，`ChromaStore.upsert()` 把它们保存起来；用户查询时，`ChromaStore.query()` 根据查询向量找出最相似的 chunk。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/vector_store/chroma_store.py` | 实现本地持久化 ChromaStore adapter |
| `src/libs/vector_store/vector_store_factory.py` | 注册 `chroma` provider |
| `src/libs/vector_store/__init__.py` | 对外导出 `ChromaStore` 和异常类型 |
| `tests/integration/test_chroma_store_roundtrip.py` | 测试 upsert/query/filter/persistence 完整闭环 |
| `DEV_SPEC.md` | 标记 B7.6 完成，更新阶段进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 阶段进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> VectorStoreFactory.create(settings)
  -> settings.vector_store.provider == "chroma"
  -> 创建 ChromaStore
  -> ChromaStore.upsert(records)
  -> 写入本地 collection JSON 文件
  -> ChromaStore.query(vector, top_k, filters)
  -> 读取内存记录并计算 cosine similarity
  -> 返回 VectorQueryResult 列表
```

数据流可以理解为：

```text
VectorRecord(id, text, vector, metadata)
  -> upsert
  -> 保存在内存字典
  -> 序列化到 persist_directory/collection_name.json
  -> query 时按 metadata 过滤
  -> 计算查询向量和记录向量的相似度
  -> 按 score 从高到低返回
```

## 4. 每个核心文件的作用

### 文件：`src/libs/vector_store/chroma_store.py`

* 主要职责：实现默认向量存储适配器。
* 关键类：
  * `ChromaStore`：负责 upsert、query、本地持久化读取。
  * `ChromaStoreError`：表示向量存储输入、配置或数据格式错误。
* 关键函数：
  * `upsert()`：插入或替换记录，并持久化到 JSON 文件。
  * `query()`：根据查询向量返回最相似记录。
  * `get_all()`：按 id 顺序返回全部记录。
  * `get_by_metadata()`：根据 metadata 过滤记录。
  * `_cosine_similarity()`：计算两个向量之间的余弦相似度。
* 输入是什么：`VectorRecord` 列表，或查询向量。
* 输出是什么：`VectorQueryResult` 列表。
* 在项目中的作用：为后续 ingestion 和 retrieval 提供最小可用的向量存储能力。

### 文件：`src/libs/vector_store/vector_store_factory.py`

* 主要职责：根据 provider 名称创建具体向量存储实现。
* 本阶段新增逻辑：`VectorStoreFactory.register("chroma", ChromaStore)`。
* 输入是什么：完整 `Settings` 或单独的 `VectorStoreSettings`。
* 输出是什么：`ChromaStore` 实例。
* 在项目中的作用：让配置里的 `vector_store.provider: chroma` 生效。

### 文件：`src/libs/vector_store/__init__.py`

* 主要职责：统一导出 vector store 模块的公共类。
* 本阶段新增导出：
  * `ChromaStore`
  * `ChromaStoreError`
* 在项目中的作用：让其它模块可以通过 `from libs.vector_store import ChromaStore` 使用默认后端。

### 文件：`tests/integration/test_chroma_store_roundtrip.py`

* 主要职责：验证向量存储的完整闭环。
* 覆盖点：
  * `VectorStoreFactory` 能创建 `ChromaStore`。
  * `upsert -> query` 可以返回正确结果。
  * `top_k` 生效。
  * metadata filters 生效。
  * 相同 id upsert 会替换旧记录。
  * 数据能持久化，重新创建实例后仍能查询。
  * 查询向量维度不匹配会报错。

## 5. 新手重点理解

向量库可以理解成“专门用来按语义相似度找文本片段的数据库”。普通数据库更擅长按字段精确查找，比如 `id=123`；向量库更擅长回答“哪个文本和这个问题最像”。

为什么要有 `VectorRecord`？因为向量库里不只存向量，还要存原文 `text` 和 `metadata`。检索结果如果只有向量分数，没有原文，就无法给用户展示引用内容。

为什么用 cosine similarity？余弦相似度是向量检索里很常见的相似度算法。它关注两个向量方向是否接近，而不是单纯比较数值大小。这里用它可以让 roundtrip 测试确定、可解释。

为什么做本地 JSON 持久化？这是为了先完成可运行闭环，避免项目在早期就依赖外部数据库或额外安装包。它不是最终高性能方案，但足够支撑当前阶段的接口、测试和后续 pipeline 编排。

本阶段在 RAG 流程中的位置是“向量存储与检索”。它连接了 Embedding 和 Retrieval：前面生成向量，存到这里；后面查询向量，也从这里找相似 chunk。
