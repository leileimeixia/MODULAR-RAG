# D1_query_processor 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `QueryProcessor`，它是 Retrieval 阶段的第一个入口模块，负责把用户输入的原始 query 转换成后续检索模块更容易使用的结构。

在 RAG 查询流程里，用户输入通常是一句话，例如：

```text
collection:docs doc_type:pdf explain BM25 index
```

`QueryProcessor` 会把它拆成两部分：

- `keywords`：用于 sparse retrieval / BM25 的关键词，例如 `["explain", "bm25", "index"]`
- `filters`：用于 metadata 过滤的结构化条件，例如 `{"collection": "docs", "doc_type": "pdf"}`

它输出的统一结构叫 `ProcessedQuery`，后续 DenseRetriever、SparseRetriever、HybridSearch 都可以基于这个结果继续工作。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/core/query_engine/query_processor.py` | 实现查询预处理、关键词提取、inline filters 解析 |
| `src/core/query_engine/__init__.py` | 对外导出 `QueryProcessor`、`ProcessedQuery`、`QueryProcessorError` |
| `tests/unit/test_query_processor.py` | 验证关键词、filters、停用词、Unicode、异常和 trace |
| `DEV_SPEC.md` | 将 D1 标记为完成，并更新阶段 D 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> QueryProcessor()
  -> process(query, filters?, trace?)
      -> 校验 query 非空
      -> _extract_inline_filters(query)
      -> _extract_keywords(query_without_filters)
      -> 合并 inline filters 和外部 filters
      -> 返回 ProcessedQuery
```

数据流可以理解成：

```text
原始 query 字符串
  -> 提取 collection/doc_type/language 等 filters
  -> 对剩余文本分词
  -> 去掉常见停用词
  -> 得到 keywords
  -> 组合成 ProcessedQuery
```

如果 query 里全是停用词，例如 `the and of`，代码会退一步保留这些词，避免输出空 keywords。

## 4. 每个核心文件的作用

### 文件：`src/core/query_engine/query_processor.py`

- 主要职责：把原始查询转换成 `ProcessedQuery`。
- 关键函数 / 类：
  - `ProcessedQuery`：保存标准化后的 query、keywords、filters。
  - `QueryProcessor`：查询预处理主类。
  - `process(query, filters, trace)`：处理入口。
  - `_extract_inline_filters(query)`：解析 `collection:docs` 这类 inline filters。
  - `_extract_keywords(query)`：分词、去重、停用词过滤。
  - `_tokenize(text)`：用正则提取词项并转小写。
  - `QueryProcessorError`：输入不合法时抛出的异常。
- 输入是什么：
  - 用户 query 字符串。
  - 可选外部 filters 字典。
  - 可选 trace。
- 输出是什么：
  - `ProcessedQuery(query, keywords, filters)`
- 在项目中的作用：
  - 为后续 dense/sparse/hybrid 检索提供统一查询输入。

### 文件：`src/core/query_engine/__init__.py`

- 主要职责：暴露 query_engine 包的公共入口。
- 关键函数 / 类：
  - `ProcessedQuery`
  - `QueryProcessor`
  - `QueryProcessorError`
- 输入是什么：无直接业务输入。
- 输出是什么：包级导入入口。
- 在项目中的作用：
  - 让后续代码可以通过 `from core.query_engine import QueryProcessor` 使用查询预处理能力。

### 文件：`tests/unit/test_query_processor.py`

- 主要职责：验证 `QueryProcessor` 的行为契约。
- 关键测试：
  - 普通 query 能提取非空 keywords。
  - 支持 `collection:docs`、`doc_type:pdf`、`language:"zh-CN"` 这类 inline filters。
  - 外部 filters 会覆盖 inline filters。
  - 未注册的 `author:jane` 不会被当成 filter，而是作为普通关键词处理。
  - query 只有停用词时仍能得到 keywords。
  - 支持 Unicode 关键词。
  - 空 query 和非 dict filters 会报错。
  - 支持 trace 记录 `query_processing` 阶段。
- 输入是什么：
  - 测试 query 字符串。
  - 可选 filters。
  - `TraceContext`。
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 保证 Retrieval 阶段的入口数据结构稳定。

## 5. 新手重点理解

`QueryProcessor` 是“查询理解”的第一步，但现在还不是复杂的自然语言理解模块。

它目前采用规则方式，先解决最基础、最稳定的问题：

- 用户到底问了哪些关键词？
- 用户有没有指定 collection、doc_type、language 这类过滤条件？
- 这些结果能不能变成后续模块统一使用的数据结构？

为什么需要 `keywords`？因为后续 SparseRetriever/BM25 不是直接理解整句话，而是根据关键词去倒排索引里找候选 chunk。

为什么需要 `filters`？因为有时用户只想查某个 collection 或某类文档。把过滤条件提前解析出来，后面的 DenseRetriever、HybridSearch 就能少查无关数据。

为什么外部 filters 优先级更高？因为调用方可能已经从界面、API 参数或 MCP tool 参数里拿到了明确过滤条件。这类结构化参数通常比用户在 query 文本里临时写的条件更可靠。

这一阶段的核心价值是：让 Retrieval 阶段有了统一入口。后续 D2、D3、D5 都可以围绕 `ProcessedQuery` 来组合 dense 检索、sparse 检索和混合检索。


# 整体架构与流程
query_processor.py 完整解析
一、文件定位
维度	说明
项目位置	src/core/query_engine/query_processor.py，属于 RAG 系统的核心查询引擎层
核心职责	对用户输入的原始自然语言查询做"预处理"——提取关键词、识别内联过滤条件、去停用词，最终输出一个标准化的 ProcessedQuery 对象，供下游检索组件（向量检索、BM25 等）直接使用
所处层级	位于"用户原始输入"和"检索器"之间，是一个规则驱动的中间处理层，不涉及模型推理，纯靠正则 + 集合运算完成轻量 NLP
二、函数拆解
1. 模块级常量
名称	类型	作用
DEFAULT_STOPWORDS	set[str]	默认停用词表（a, an, the, in…），提取关键词时会被过滤掉
FILTER_KEYS	set[str]	允许通过内联语法识别的过滤字段白名单（collection, doc_type, language…）
2. QueryProcessorError(ValueError)
目的：自定义异常，当查询无法被处理时抛出（如空字符串、无关键词等）。
输入/输出：继承自 ValueError，无额外逻辑。
3. ProcessedQuery（dataclass，frozen）
目的：一个不可变的数据容器，承载预处理后的标准化查询结果，在检索组件间传递。
字段：
query: str — 原始查询的 strip 版本
keywords: list[str] — 提取出的关键词列表（已去重、已小写）
filters: dict[str, Any] — 合并后的过滤条件字典
4. QueryProcessor.__init__(stopwords, filter_keys)
目的：初始化处理器，配置停用词表和过滤字段白名单。
输入：
stopwords：可选，自定义停用词集合；不传则用 DEFAULT_STOPWORDS
filter_keys：可选，自定义过滤字段集合；不传则用 FILTER_KEYS
核心逻辑：全部转为小写存储，保证后续匹配时大小写不敏感。
5. QueryProcessor.process(query, filters, trace) ⭐ 主入口
目的：对外暴露的唯一处理方法，完成"原始查询 → 标准化查询"的全流程。
输入：
query: str — 用户原始查询字符串
filters: dict | None — 外部传入的过滤条件（如 API 层指定的 doc_type）
trace: Any | None — 可选的追踪对象，用于记录处理链路
输出：ProcessedQuery 实例
核心流程：
参数校验：query 必须是非空字符串，filters 必须是字典
提取内联过滤：从 query 中解析出 key:value 形式的过滤条件
合并过滤条件：内联过滤 + 外部过滤（外部优先覆盖内联）
提取关键词：先从去掉过滤条件的 query 中提取；如果提取为空，则回退到原始 query 并允许保留停用词
兜底校验：如果仍然没有关键词，抛出异常
记录 trace：如果有 trace 对象，记录本阶段处理详情
6. QueryProcessor._extract_inline_filters(query)
目的：从查询字符串中识别并提取 key:value 或 key:"value with spaces" 形式的内联过滤条件。
输入：原始 query 字符串
输出：(filters_dict, cleaned_query) 元组
filters_dict：提取到的过滤条件字典
cleaned_query：去掉过滤条件后的干净查询文本
核心逻辑：
使用正则 (?P<key>...)\s*:\s*(?:"(?P<quoted>...)"|(?P<bare>...)) 匹配
只有 key 在 self.filter_keys 白名单中才会被提取
匹配到的部分替换为空格，保留原始查询的其余内容
7. QueryProcessor._extract_keywords(query, allow_stopwords)
目的：从文本中提取关键词列表（去重、小写、可选过滤停用词）。
输入：
query: str — 待提取文本
allow_stopwords: bool — 是否允许保留停用词（默认 False）
输出：list[str] — 关键词列表，保持首次出现顺序
核心逻辑：调用 _tokenize 分词后，逐个检查是否在停用词表中，不在则加入结果（去重）。
8. _tokenize(text) （模块级私有函数）
目的：最基础的分词器，将文本拆分为小写的字母数字 token。
输入：任意字符串
输出：list[str] — 所有 \w+ 匹配项的小写列表
核心逻辑：re.finditer(r"\w+", text) 提取所有连续字母数字片段并转小写。
三、执行流程
用户输入 query
      │
      ▼
┌─────────────────────────────┐
│  process(query, filters)    │  ← 主入口
│                             │
│  1. 参数校验                │
│     ├─ query 非空？         │
│     └─ filters 是 dict？    │
│                             │
│  2. _extract_inline_filters │  ← 解析 "doc_type:pdf" 这类条件
│     ├─ 正则匹配 key:value   │
│     ├─ 白名单过滤           │
│     └─ 返回 (filters, 干净query)
│                             │
│  3. 合并过滤条件            │
│     └─ {**内联, **外部}     │
│                             │
│  4. _extract_keywords       │  ← 从干净 query 提取关键词
│     ├─ _tokenize 分词       │
│     └─ 过滤停用词 + 去重    │
│                             │
│  5. 兜底：关键词为空？      │
│     └─ 用原始 query 再提取  │
│        (allow_stopwords=True)│
│                             │
│  6. 仍为空？→ 抛异常        │
│                             │
│  7. 构造 ProcessedQuery     │
│                             │
│  8. trace.record_stage()    │  ← 可选，记录处理链路
│                             │
│  9. return ProcessedQuery   │
└─────────────────────────────┘
      │
      ▼
  下游检索组件使用
调用关系总结：

process → _extract_inline_filters → 正则匹配 + 闭包 replace
process → _extract_keywords → _tokenize
四、场景示例
业务场景：用户在一个企业知识库 RAG 系统中搜索技术文档。

用户输入：

"如何配置Redis集群 collection:tech_docs doc_type:pdf"
执行过程：

步骤	操作	结果
① 参数校验	query 非空 ✓，filters=None ✓	通过
② 提取内联过滤	正则匹配到 collection:tech_docs 和 doc_type:pdf，两个 key 都在白名单中	filters = {"collection": "tech_docs", "doc_type": "pdf"}，cleaned_query = "如何配置Redis集群 "
③ 合并过滤	外部 filters 为 None，直接用内联	merged_filters = {"collection": "tech_docs", "doc_type": "pdf"}
④ 提取关键词	_tokenize("如何配置Redis集群") → ["如何配置redis集群"]（中文被当作一个整体 token，因为 \w+ 匹配 Unicode）	keywords = ["如何配置redis集群"]
⑤ 构造结果	—	ProcessedQuery(query="如何配置Redis集群 collection:tech_docs doc_type:pdf", keywords=["如何配置redis集群"], filters={"collection": "tech_docs", "doc_type": "pdf"})
下游检索器拿到这个对象后：

用 keywords 去做向量相似度搜索 / BM25 关键词匹配
用 filters 在向量数据库的 metadata 中做精确过滤（只查 tech_docs 集合中的 PDF 文档）
💡 注意：当前 _tokenize 使用 \w+ 正则，对中文支持较弱（会把整句中文当作一个 token）。如果需要更好的中文分词效果，后续可以接入 jieba 等分词库替换 _tokenize 的实现。