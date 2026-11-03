# I5_full_chain_acceptance 学习笔记

## 1. 本阶段完成了什么

本阶段完成的是项目最后的“全链路验收收口”。它关注的不是某一个单独模块，而是确认整个项目从入口到出口能被稳定地跑起来。

本阶段发现并修复了一个真实的开箱体验问题：`scripts/ingest.py` 和 Dashboard 上传入口都声明支持 `.pdf`、`.txt`、`.md`、`.docx`，但 `IngestionPipeline` 默认只使用 `PdfLoader`，所以当用户摄取目录时，只要目录里有 `sample.md`，pipeline 就会在 load 阶段失败。

为了解决这个问题，本阶段新增了 `DocumentLoader`，让摄取入口可以根据文件后缀自动选择加载方式：

* `.pdf`：继续交给原来的 `PdfLoader`
* `.txt` / `.md`：直接按 UTF-8 文本读取
* `.docx`：用标准库解压并读取 `word/document.xml`

同时，本阶段新增了一个离线 full-chain acceptance E2E 测试，用测试替身串起：

```text
ingest CLI -> query CLI -> evaluate CLI
```

这样即使当前 OpenAI API Key 无效或网络不可用，项目也仍然有一条可复现的自动化全链路验收路径。

本阶段属于 RAG 项目的最终验收阶段，目标是确认项目已经达到“可以交付、可以演示、可以继续扩展”的状态。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/loader/document_loader.py` | 新增多格式文档加载器，统一处理 PDF、TXT、MD、DOCX |
| `src/libs/loader/__init__.py` | 导出 `DocumentLoader`，方便 pipeline 和其他模块直接引用 |
| `src/ingestion/pipeline.py` | 将默认 loader 从 `PdfLoader` 改为 `DocumentLoader` |
| `tests/unit/test_document_loader.py` | 为多格式 loader 补充单元测试 |
| `tests/e2e/test_full_chain_acceptance.py` | 新增离线全链路验收测试，覆盖 ingest、query、evaluate 三个入口 |
| `tests/unit/test_dashboard_app.py` | 调整 Dashboard 页面测试断言，适配真实页面已替代占位页的现状 |
| `DEV_SPEC.md` | 标记 I5 完成，并将项目总进度更新为 100% |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步更新自动开发进度表 |

## 3. 核心调用关系

摄取入口的调用关系：

```text
scripts/ingest.py
  -> IngestionPipeline.run(path)
  -> DocumentLoader.load(path)
      -> PDF: PdfLoader.load(path)
      -> TXT / MD: 读取文本并构造 Document
      -> DOCX: 解压 word/document.xml 并提取段落文本
  -> DocumentChunker
  -> BatchProcessor
  -> VectorUpserter / BM25Indexer / ImageStorage
```

离线全链路验收的调用关系：

```text
test_full_chain_acceptance.py
  -> ingest_cli.main(...)
      -> FakePipeline.run(...)
  -> query_cli.main(...)
      -> FakeHybridSearch.search(...)
      -> FakeReranker.rerank(...)
  -> evaluate_cli.main(...)
      -> FakeHybridSearch.search(...)
      -> FakeEvaluator.evaluate(...)
```

这里的重点是：E2E 测试验证的是 CLI 主入口之间的串联关系，而不是依赖真实 OpenAI 服务。真实外部 API 可以单独复验，但项目自身的工程链路必须先可复现。

## 4. 每个核心文件的作用

### 文件：`src/libs/loader/document_loader.py`

* 主要职责：根据文件类型把源文件加载成统一的 `Document`。
* 关键函数 / 类：`DocumentLoader.load()`、`_load_text_document()`、`_load_docx_document()`。
* 输入是什么：用户上传或 CLI 指定的文档路径。
* 输出是什么：项目统一的 `Document` 对象，包含 `id`、`text`、`metadata`。
* 在项目中的作用：它是 ingestion pipeline 的第一个业务入口，负责把不同格式的原始文件转成后续 chunk、embedding、检索都能理解的统一结构。

### 文件：`src/ingestion/pipeline.py`

* 主要职责：串联完整摄取流程。
* 关键函数 / 类：`IngestionPipeline.__init__()`、`IngestionPipeline.run()`。
* 输入是什么：文件路径、collection、force、trace、progress callback。
* 输出是什么：`IngestionResult`，包含文件 hash、文档 id、chunk 数、入库记录数等。
* 在项目中的作用：它是离线摄取和 Dashboard 上传摄取共用的核心流水线。本阶段把默认 loader 改成 `DocumentLoader`，让它真正支持多格式输入。

### 文件：`tests/unit/test_document_loader.py`

* 主要职责：验证 `DocumentLoader` 对不同格式的处理规则。
* 关键测试：PDF 委托、TXT/MD 读取、DOCX 提取、空文本和不支持格式报错。
* 输入是什么：测试中临时创建的 `.txt`、`.md`、`.docx`，以及项目自带 PDF fixture。
* 输出是什么：断言得到正确的 `Document` 或明确的 `LoaderError`。
* 在项目中的作用：防止以后改 loader 时破坏“多格式入口”这个开箱能力。

### 文件：`tests/e2e/test_full_chain_acceptance.py`

* 主要职责：提供一条不依赖外部 API 的端到端验收测试。
* 关键函数 / 类：`test_offline_full_chain_acceptance()`、`FakePipeline`、`FakeHybridSearch`、`FakeReranker`、`FakeEvaluator`。
* 输入是什么：样例文档目录、测试查询、临时 golden test set。
* 输出是什么：验证 ingest 成功、query 返回 chunk、evaluate 得到 `hit_rate=1.0`。
* 在项目中的作用：这是最终交付前的“工程链路自检”。它不证明真实模型服务可用，但证明项目自己的 CLI 入口、参数传递、结果格式和评估流转是通的。

### 文件：`tests/unit/test_dashboard_app.py`

* 主要职责：验证 Dashboard 页面注册和页面渲染不会报错。
* 关键修改：不再断言页面只有三个标题，而是检查关键页面标题存在。
* 输入是什么：`_FakeStreamlit` 测试替身。
* 输出是什么：确认页面可以在无真实 Streamlit 运行环境下被调用。
* 在项目中的作用：Dashboard 页面已经从占位页升级为真实页面，测试也要跟着关注更稳定的行为，而不是卡死在旧页面结构上。

## 5. 新手重点理解

全链路验收的意义是回答一个很朴素的问题：这个项目从用户角度能不能跑通？

在 RAG 项目里，“能跑通”通常至少包括四件事：

* 文档能被摄取
* 文档能被检索
* 结果能通过 MCP 或 CLI 返回
* 效果能被评估

本阶段真实运行 ingestion 时遇到了 OpenAI `HTTP 401`。这说明外部 API Key 当前不可用，但这不应该阻止我们验证项目自己的工程链路。所以这里采用了两层验收思路：

* 外部依赖验收：需要真实 API Key、网络、模型服务都可用
* 工程链路验收：用 fake/injected 组件验证项目入口和数据流是否正确

`DocumentLoader` 的价值也很好理解：用户不会只上传 PDF。README、CLI、Dashboard 都写了支持 Markdown、文本、DOCX，那么 pipeline 的默认 loader 就应该真的支持这些格式。否则用户照着文档跑，第一步就失败，这就是典型的“文档和代码不一致”。

DOCX 的处理这里没有引入新依赖，而是用标准库 `zipfile` 和 `xml.etree.ElementTree` 读取 `word/document.xml`。这不是一个完整的 Word 解析器，但足够支持基础文本提取，也符合当前项目“轻量、可复现、少依赖”的收口目标。

从 RAG 流程位置看，本阶段覆盖的是整个系统闭环：

```text
文档摄取
  -> 文本加载
  -> 切块与向量化
  -> 检索查询
  -> 结果返回
  -> 评估验收
```

也就是说，I5 是把前面所有阶段串起来做最后检查。完成这个阶段后，项目不只是“模块都写完了”，而是具备了可以持续验证、可以演示、可以交付的基础。

# 整体结构与流程

文件定位
文件路径：src/libs/loader/document_loader.py 项目作用：该文件是 RAG（检索增强生成）系统数据摄入（Ingestion）流程的“大门”。 所处层级：属于底层基础库（libs/loader），位于数据处理的最前端。 核心职责：负责将各种不同格式的项目文档（如 PDF、TXT、Markdown、DOCX）统一读取、解析并转换为系统内部标准的 Document 数据契约（Contract），为后续的文本分块（Chunking）和向量化（Embedding）提供干净、统一的纯文本输入。

函数拆解
DocumentLoader.__init__

目的：初始化文档加载器。
输入：可选的 pdf_loader 实例。
功能：如果外部没有传入 PDF 加载器，则默认创建一个。这采用了依赖注入的设计，方便后续测试或替换不同的 PDF 解析引擎。
DocumentLoader.load

目的：核心路由与加载入口。
输入：文件路径（字符串或 Path 对象）。
输出：标准的 Document 对象。
功能：首先校验文件是否真实存在；然后提取文件后缀，像“交通指挥员”一样，把不同格式的文件分发给对应的处理逻辑（PDF 交给 pdf_loader，文本交给 _load_text_document，Word 交给 _load_docx_document），不支持的格式则直接报错。
_load_text_document

目的：处理纯文本（.txt）和 Markdown（.md）文件。
输入：文件路径、文档类型。
输出：Document 对象。
功能：读取文件内容，进行文本清洗（归一化），计算文件的 SHA256 哈希值作为文档唯一 ID，最后将文本和元数据（来源、类型、哈希等）封装成 Document。
_load_docx_document

目的：处理 Word（.docx）文档。
输入：文件路径。
输出：Document 对象。
功能：因为 .docx 本质是一个压缩包，所以先将其作为 Zip 文件打开，读取核心的 word/document.xml。如果读取失败则抛出异常。成功后提取文本、清洗、计算哈希并封装。
_extract_docx_text

目的：从 Word 的 XML 结构中提取纯文本。
输入：XML 文件的字节流（payload）。
输出：拼接好的纯文本字符串。
功能：使用 XML 解析器，定位到 Word 命名空间下的段落（w:p）和文本节点（w:t），将各个文本块拼接起来，并用换行符连接各个段落。
_normalize_text

目的：文本清洗与标准化。
输入：原始文本字符串。
输出：清洗后的文本字符串。
功能：将 Windows 和旧 Mac 的换行符（\r\n, \r）统一转换为 Linux 的 \n，并将连续 3 个及以上的换行符压缩为 2 个（即保留一个空行），最后去除首尾的空白字符。这能大幅减少后续大模型处理的“噪音”。
执行流程
整个文件的运行链路是一个典型的策略分发与管道处理流程：

入口校验：调用 DocumentLoader.load(path)，检查文件是否存在。
格式路由：获取文件后缀，进入对应的分支。
内容提取：
文本/MD：直接读取文件内容。
DOCX：解压 -> 读取 XML -> 解析 XML 提取文本。
PDF：委托给外部的 PdfLoader 处理。
文本清洗：所有提取出的原始文本，都会经过 _normalize_text 进行换行符统一和多余空行压缩。
身份标识：调用 compute_sha256 计算文件内容的哈希值，作为该文档的全局唯一 ID。
数据封装：将清洗后的文本、文件路径、文档类型、哈希值等元数据打包，实例化为 Document 对象并返回。
场景示例
业务场景：产品经理上传了一份名为 2023年Q4产品规划.docx 的 Word 文档，系统需要将其入库以便后续进行 RAG 问答。

全流程串联：

系统调用 loader.load("2023年Q4产品规划.docx")。
load 方法发现文件存在，且后缀是 .docx，于是调用 _load_docx_document。
_load_docx_document 把 .docx 当作 zip 压缩包打开，精准抽出了里面的 word/document.xml 文件。
接着调用 _extract_docx_text，像剥洋葱一样解析 XML 标签，把 <w:t> 里的文字（如“一、核心目标”、“二、资源盘点”）全部剥离出来，拼成一段段纯文本。
提取出的文本可能包含很多排版导致的多余空行，于是经过 _normalize_text 的“熨烫”，把连续的空行压平，统一换行格式，让文本变得干净清爽。
系统对这份文档计算 SHA256 哈希值（例如 a1b2c3d4...），作为它的唯一身份证。
最终，系统生成一个 Document 对象：
ID：a1b2c3d4...
Text：清洗后的规划纯文本。
Metadata：包含来源路径、类型（docx）、哈希值等。
这个标准的 Document 对象被顺利移交给下游的“文本分块器（Splitter）”，准备切分成小块进入向量数据库。