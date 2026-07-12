# C11_bm25_indexer 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `BM25Indexer`，它负责把前面 `SparseEncoder` 生成的 `sparse_vector` 转换成可以查询的 BM25 倒排索引，并把索引持久化到本地文件。

在 RAG 流程里，C8-C10 已经把 chunk 变成了带有 dense/sparse 信息的 `ChunkRecord`。其中 `sparse_vector` 表示某个词在当前 chunk 中出现了多少次。C11 要做的事情，就是把这些分散在每个 chunk 里的词频信息整理成索引结构：

```text
term
  -> idf
  -> postings:
      -> chunk_id
      -> tf
      -> doc_length
```

这样后续 `SparseRetriever` 就可以根据用户输入的关键词，快速找到相关 chunk。

它在 Ingestion Pipeline 中的位置是：

```text
BatchProcessor
  -> List[ChunkRecord] with sparse_vector
  -> BM25Indexer.build(...)
      -> 构建倒排索引
      -> 计算 IDF
      -> 保存到 data/db/bm25/bm25_index.pkl
  -> SparseRetriever 查询使用
```

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/storage/bm25_indexer.py` | 实现 BM25 倒排索引构建、保存、加载、查询、重建和增量更新 |
| `src/ingestion/storage/__init__.py` | 对外导出 `BM25Indexer` 和 `BM25IndexerError` |
| `tests/unit/test_bm25_indexer_roundtrip.py` | 验证 build/load/query、IDF 公式、postings 结构、重建和增量更新 |
| `DEV_SPEC.md` | 将 C11 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> BM25Indexer(index_dir)
  -> build(records)
      -> 校验每个 record 都有 sparse_vector
      -> 保存 record payload
      -> _rebuild_index()
          -> 统计 doc_count
          -> 计算每个 chunk 的 doc_length
          -> 按 term 构建 postings
          -> 计算每个 term 的 idf
      -> save()
  -> load()
  -> query("keyword", top_k)
      -> tokenize query
      -> 找到每个 term 的 postings
      -> 用 BM25 公式计算 score
      -> 返回排序后的 chunk_id
```

本阶段的数据流可以理解成：

```text
ChunkRecord.sparse_vector
  -> records 字典
  -> postings_by_term
  -> self.index
  -> bm25_index.pkl
  -> query 读取 index 并返回 top chunk ids
```

## 4. 每个核心文件的作用

### 文件：`src/ingestion/storage/bm25_indexer.py`

- 主要职责：构建并持久化 BM25 倒排索引。
- 关键函数 / 类：
  - `BM25Indexer`：BM25 索引器主类。
  - `build(records, trace)`：从一组 `ChunkRecord` 全量重建索引。
  - `add(records, trace)`：增量新增或替换 records，然后重建索引并保存。
  - `save()`：把索引保存为 pickle 文件。
  - `load()`：从 pickle 文件加载索引。
  - `query(query, top_k)`：根据关键词查询 top chunk ids。
  - `_rebuild_index()`：根据当前 records 重新构建倒排索引和 IDF。
  - `_score_posting()`：计算单个 posting 的 BM25 分数。
  - `_idf(document_count, document_frequency)`：按 DEV_SPEC 公式计算 IDF。
  - `_validate_record(record)`：确保输入是带 `sparse_vector` 的 `ChunkRecord`。
- 输入是什么：
  - `list[ChunkRecord]`
  - 每个 record 必须有 `sparse_vector`
  - 查询时输入关键词字符串
- 输出是什么：
  - 磁盘上的 `bm25_index.pkl`
  - 查询结果 `list[{"chunk_id": ..., "score": ...}]`
- 在项目中的作用：
  - 把 ingestion 阶段的 sparse 编码结果变成后续关键词检索可用的本地索引。

### 文件：`src/ingestion/storage/__init__.py`

- 主要职责：暴露 storage 阶段的公共入口。
- 关键函数 / 类：
  - `BM25Indexer`
  - `BM25IndexerError`
- 输入是什么：无直接业务输入。
- 输出是什么：包级导入入口。
- 在项目中的作用：
  - 让后续代码可以使用 `from ingestion.storage import BM25Indexer`。

### 文件：`tests/unit/test_bm25_indexer_roundtrip.py`

- 主要职责：验证 BM25Indexer 的核心行为。
- 关键测试：
  - build 后能保存索引，load 后能查询到稳定 top ids。
  - IDF 计算符合 `log((N - df + 0.5) / (df + 0.5))`。
  - postings 中保存 `chunk_id`、`tf`、`doc_length`。
  - `build()` 会替换旧索引。
  - `add()` 支持新增和同 id record 替换。
  - 空 sparse vector 可以参与构建，但不会产生 term postings。
  - 缺少 sparse vector 的 record 会报错。
  - 支持 trace 记录 `bm25_build` 阶段。
- 输入是什么：
  - 测试构造的 `ChunkRecord`
  - pytest 的 `tmp_path`
  - `TraceContext`
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 保证本地 BM25 索引可以稳定保存、加载和查询，为后续 `SparseRetriever` 打基础。

## 5. 新手重点理解

BM25Indexer 做的是“从词到 chunk 的反向查找表”。

普通文本是从 chunk 看词：

```text
chunk-a -> alpha: 3, shared: 1
chunk-b -> beta: 2, shared: 1
```

倒排索引则反过来：

```text
alpha -> chunk-a
beta -> chunk-b
shared -> chunk-a, chunk-b
```

为什么要反过来？因为用户查询时通常输入的是词。如果没有倒排索引，就要把所有 chunk 扫一遍；有了倒排索引，就能直接根据词定位候选 chunk。

IDF 是用来衡量一个词“稀不稀有”的。出现在很多 chunk 里的词区分度低，出现在少数 chunk 里的词区分度高。比如 “系统” 可能很多地方都有，而 “BM25Indexer” 更能说明某个 chunk 的主题。

本阶段使用 pickle 保存索引，是为了先快速完成本地可用的持久化。后续如果索引变大，可以再迁移到 SQLite 或更专业的检索后端。

`build()` 和 `add()` 的区别也很重要：

- `build()` 是全量重建，会清掉旧 records。
- `add()` 是增量更新，同一个 `chunk_id` 会被新 record 替换，然后重新计算索引。

为什么 `add()` 后也要重新计算 IDF？因为 IDF 依赖整个语料库的文档数和词出现的文档数。只要新增或替换了 record，全局统计就可能变化，所以需要重新计算。

这一阶段的核心价值是：让 sparse 路线真正从“有词频数据”变成“有可查询索引”。到这里，关键词检索路线已经具备了后续被 `SparseRetriever` 调用的基础。




# 一、 检索算法与核心概念
BM25
含义：一种经典的文本相关性打分算法，是信息检索领域的“老大哥”。
理解：它就像一位 “打分裁判”。当你搜索关键词时，它会根据词在文章里出现的次数（TF）以及这个词有多稀有（IDF），给每篇文章计算一个匹配分数，分数越高代表越相关。
倒排索引 (Inverted Index)
含义：一种从“词”快速查找“文档”的数据结构。
理解：就像书后面的“词汇索引”。正向看书是“第1页写了苹果，第2页写了香蕉”；倒排索引是“苹果 -> 第1页，香蕉 -> 第2页”。有了它，搜索时就不用一页页翻书，直接查目录就能找到答案。
IDF (Inverse Document Frequency, 逆文档频率)
含义：衡量一个词有多“稀有”或“重要”的指标。
理解：“物以稀为贵”。如果“的”、“是”这种词到处都有，它的 IDF 就很低；如果“BM25Indexer”这种词很少见，它的 IDF 就很高。IDF 越高的词，越能代表一篇文章的核心主题。
TF (Term Frequency, 词频)
含义：一个词在当前文档中出现的次数。
理解：一篇文章里“苹果”出现了 5 次，TF 就是 5。出现次数越多，说明这篇文章越可能是在讲“苹果”。
Postings (倒排列表)
含义：在倒排索引中，某个词对应的所有文档信息列表。
理解：在字典里查“苹果”，后面跟着的“第1页、第5页、第10页”这些页码和具体位置信息，就是 postings。

# 二、 数据结构与存储
Chunk (文本块)
含义：将长文本切分后的小段落。
理解：把一本厚厚的小说撕成一页一页的。大模型一次读不完一整本书，所以要把长文章切成一个个小 Chunk 来处理。
Record (ChunkRecord)
含义：数据记录，这里特指包含文本块及其各种特征信息的载体。
理解：就像快递单。上面不仅记录了包裹的内容（Chunk），还记录了它的单号（chunk_id）、重量（sparse_vector）等各种附加信息。
Sparse Vector (sparse_vector, 稀疏向量)
含义：大部分元素为 0 的向量，在本文中用来表示词频。
理解：就像一张包含 10000 门课的成绩单，但你只考了 3 门（有具体分数），其他 9997 门都是 0 分。因为 0 太多，所以叫“稀疏”。在代码里，为了节省空间，通常只记录非 0 的部分。
Pickle (pickle)
含义：Python 提供的一个序列化模块，用于将对象转换为可存储的格式。
理解：就像 “真空保鲜盒”。电脑内存里的数据（如字典、列表）断电就没了，pickle 能把这些复杂的数据结构“打包冷冻”成文件存到硬盘（如 bm25_index.pkl），下次用的时候再“解冻”恢复到内存中。

# 三、 系统流程与组件
Ingestion Pipeline (数据摄入/处理管道)
含义：数据从原始状态到准备好被查询的整个自动化处理流程。
理解：就像自来水厂的处理流水线。原水（原始文档）进来，经过过滤、消毒、加氯（切分文本、向量编码、建索引），最后变成可以直接饮用的纯净水（可查询的本地索引）。
BM25Indexer
含义：本阶段实现的核心类，负责构建和管理 BM25 倒排索引。
理解：它是流水线上的索引加工车间主任。负责把零散的词频信息整理成 倒排索引，算好 IDF，并用 pickle 存起来。
💡 一句话串联理解： 在 Ingestion Pipeline 中，长文本被切成 Chunk，打包成 ChunkRecord（包含 sparse_vector），然后交给 BM25Indexer 构建 倒排索引（记录每个词的 Postings、TF 和 IDF），最后用 pickle 存到硬盘。当用户搜索时，系统利用 BM25 算法快速算出最匹配的文档。


# 整体架构与流程

1. 文件定位
作用：实现了一个基于 BM25 算法的倒排索引，用于对文本块（Chunk）进行高效的关键词检索。
所处层级：属于 RAG（检索增强生成）系统中的“存储与检索”底层模块（位于 ingestion/storage 目录下），是连接原始数据与大模型检索的核心桥梁。
核心职责：负责将文本数据构建成倒排索引，支持索引的持久化（保存到磁盘和从磁盘加载），并提供基于 BM25 算法的关键词打分与查询功能。
2. 函数拆解
核心类方法（BM25Indexer）
init：初始化索引器。设置索引保存路径、BM25 算法的两个关键参数（k1 控制词频权重饱和度，b 控制文档长度惩罚），并初始化空的索引和文档记录字典。
build：全量重建索引。接收一组文本块记录，清空旧数据，验证并转换新数据，重建索引并保存到磁盘。
add：增量添加记录。不清空旧数据，直接添加或覆盖新记录，然后重建索引并保存。
load：加载索引。从磁盘读取之前保存的 pickle 文件，恢复索引和文档数据到内存中，返回自身实例。
save：保存索引。将内存中的索引、文档数据及参数序列化（使用 pickle）并写入磁盘文件，返回文件路径。
query：执行查询。接收查询字符串和返回数量 top_k，对查询词分词后，在倒排索引中查找匹配的文档，计算 BM25 得分，最后按得分从高到低返回 top_k 个文档 ID 及分数。
_rebuild_index：内部核心方法。遍历所有文档记录，统计每个文档的长度、计算平均文档长度，并构建“词项 -> 包含该词项的文档列表及词频”的倒排索引结构，同时计算每个词项的 IDF（逆文档频率）。
_score_posting：计算单个词项在单个文档中的 BM25 得分。结合 IDF、词频（TF）和文档长度进行数学打分。
_record_trace：记录运行轨迹，用于调试或监控（如记录构建了多少文档、索引了多少词等）。
_index_path：返回索引文件在磁盘上的完整绝对路径。
辅助函数
_validate_record：检查传入的对象是否是合法的 ChunkRecord 且包含稀疏向量（词频数据）。
_record_payload：将 ChunkRecord 对象转换为内部存储所需的字典格式（提取 id、text、metadata 和 sparse_vector）。
_idf：根据总文档数和包含该词的文档数，计算逆文档频率（IDF）。词越罕见，IDF 得分越高。
_tokenize：使用正则表达式提取文本中的单词，并全部转换为小写，实现简单的英文/数字分词。
3. 执行流程
初始化阶段：实例化 BM25Indexer，配置存储路径和算法参数。
构建/加载阶段：
首次构建：调用 build 传入文档列表。内部会调用 _validate_record 校验数据，用 _record_payload 转换数据格式，接着调用 _rebuild_index 构建倒排索引和计算 IDF，最后调用 save 将索引持久化到磁盘。
服务重启：调用 load 从磁盘读取 pickle 文件，直接恢复内存状态，无需重新计算。
查询阶段：调用 query 传入用户的搜索词。内部先调用 _tokenize 对搜索词分词，然后遍历每个词，在倒排索引中找到包含该词的文档，调用 _score_posting 累加 BM25 得分，最后排序并返回得分最高的几个文档 ID。
4. 场景示例
假设我们在做一个“水果知识库”的 RAG 系统，有三个文本块（Chunk）：

Chunk 1: "苹果很好吃"
Chunk 2: "香蕉也很好吃"
Chunk 3: "苹果和香蕉都是水果"
【构建索引】 调用 build 传入这三个 Chunk。

系统分词后得到词库：["苹果", "好吃", "香蕉", "也", "和", "都", "是", "水果"]。
构建倒排索引：比如 "苹果" 出现在 Chunk 1 和 3 中；"香蕉" 出现在 Chunk 2 和 3 中。
计算 IDF："苹果" 和 "香蕉" 各出现在 2 个文档中，IDF 较低（比较常见）；而 "也"、"和" 等只出现在 1 个文档中，IDF 较高（相对稀有）。
调用 save 将这套索引结构保存到 bm25_index.pkl 文件中。
【查询检索】 用户提问：“苹果好吃吗？”

query 方法将问题分词为：["苹果", "好吃", "吗"]。
查倒排索引："吗" 没出现过，跳过；"苹果" 在 Chunk 1 和 3 中；"好吃" 在 Chunk 1 和 2 中。
计算 BM25 得分：
Chunk 1 同时包含 "苹果" 和 "好吃"，且文档较短（长度惩罚小），得分累加后最高。
Chunk 3 包含 "苹果" 但不包含 "好吃"，得分次之。
Chunk 2 包含 "好吃" 但不包含 "苹果"，得分再次之。
最终返回排序后的结果，Chunk 1 排在第一位，完美命中用户需求，随后将其送入大模型进行答案生成。