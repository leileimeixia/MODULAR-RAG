# C3_pdf_loader 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 Loader 层的基础契约，并增加了一个可以读取 PDF 文本的 `PdfLoader`。

在 RAG 项目里，Loader 的职责是把外部文件变成项目内部统一的 `Document` 对象。也就是说，后续的切块、向量化、入库模块不需要直接理解 PDF 文件格式，只需要处理统一的 `Document`。

本阶段在 Ingestion Pipeline 中的位置是最靠前的数据读取环节：

```text
PDF 文件
  -> PdfLoader
  -> Document
  -> 后续 Splitter / Transform / Embedding / Store
```

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/loader/base_loader.py` | 定义所有 Loader 都要遵守的抽象接口 |
| `src/libs/loader/pdf_loader.py` | 实现 PDF 文件到 `Document` 的转换 |
| `src/libs/loader/__init__.py` | 对外导出 `BaseLoader`、`LoaderError`、`PdfLoader` 等入口 |
| `tests/unit/test_loader_pdf_contract.py` | 验证 PDF Loader 的基础行为和异常处理 |
| `tests/fixtures/sample_documents/simple.pdf` | 用于测试的最小文本 PDF 文件 |
| `DEV_SPEC.md` | 将 C3 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> PdfLoader.load(path)
      -> 校验文件存在
      -> 校验扩展名是 .pdf
      -> compute_sha256(path)
      -> 提取 PDF 文本
      -> 组装 Document
  -> 返回 Document
```

`PdfLoader` 会优先尝试使用 `pypdf`。如果当前环境没有安装 `pypdf`，就使用内置的轻量解析逻辑，从 PDF 的 content stream 中提取基础文本。

当前阶段图片处理采用安全降级：`metadata.images` 先返回空列表。这样即使暂时没有完整图片提取能力，也不会阻塞文本解析链路继续向前跑。

## 4. 每个核心文件的作用

### 文件：`src/libs/loader/base_loader.py`

* 主要职责：定义 Loader 的统一接口。
* 关键函数 / 类：
  * `BaseLoader`：抽象基类。
  * `BaseLoader.load(path) -> Document`：所有具体 Loader 都必须实现的方法。
  * `LoaderError`：Loader 层统一的可读异常。
* 输入是什么：
  * 文件路径。
* 输出是什么：
  * `Document` 对象。
* 在项目中的作用：
  * 让 PDF、TXT、Markdown、DOCX 等不同文件类型以后都能遵守同一个入口。

### 文件：`src/libs/loader/pdf_loader.py`

* 主要职责：把 PDF 文件解析成 `Document`。
* 关键函数 / 类：
  * `PdfLoader.load(path)`：主入口，负责校验、计算 hash、提取文本、组装 `Document`。
  * `_extract_with_pypdf(path)`：如果环境安装了 `pypdf`，优先用它提取文本。
  * `_extract_with_builtin_parser(path)`：无外部依赖时的轻量 fallback。
  * `_extract_streams(raw)`：从 PDF 字节中找出 stream 内容，并尝试解压。
  * `_extract_pdf_strings(raw)`：从 PDF 文本绘制指令中提取字符串。
* 输入是什么：
  * 一个 `.pdf` 文件路径。
* 输出是什么：
  * `Document`，其中包含：
    * `id`：文件 SHA256。
    * `text`：提取出来的文本。
    * `metadata.source_path`：源文件路径。
    * `metadata.doc_type`：`pdf`。
    * `metadata.file_hash`：文件 hash。
    * `metadata.images`：当前阶段为空列表。
* 在项目中的作用：
  * 为后续 Ingestion Pipeline 提供可处理的标准文档对象。

### 文件：`src/libs/loader/__init__.py`

* 主要职责：统一导出 loader 模块的公共 API。
* 关键函数 / 类：
  * `BaseLoader`
  * `LoaderError`
  * `PdfLoader`
* 输入是什么：无直接业务输入。
* 输出是什么：包级导入入口。
* 在项目中的作用：
  * 其他模块可以从 `libs.loader` 直接导入 Loader 能力。

### 文件：`tests/unit/test_loader_pdf_contract.py`

* 主要职责：用测试固定 Loader 的行为边界。
* 关键测试：
  * 文本 PDF 可以被读取成 `Document`。
  * 缺失文件会抛出 `LoaderError`。
  * 非 PDF 文件会被拒绝。
  * 没有可提取文本的 PDF 会报错。
  * `BaseLoader` 作为抽象类不能直接实例化。
* 输入是什么：
  * `simple.pdf` fixture 和临时测试文件。
* 输出是什么：
  * pytest 断言结果。
* 在项目中的作用：
  * 保护 Loader 契约，避免后续改动破坏基础摄取入口。

## 5. 新手重点理解

Loader 是 RAG 摄取链路的“入口适配器”。现实里的文档格式很多，PDF、TXT、Markdown、DOCX 都不一样。如果后面的模块直接处理这些格式，代码会越来越乱。

所以这里先定义 `BaseLoader`，让所有 Loader 都返回同一种 `Document`。这样后续模块只关心 `Document.text` 和 `Document.metadata`，不用关心这个文本原来来自 PDF 还是 Markdown。

`PdfLoader` 使用文件 SHA256 作为 `Document.id`，这样同一个文件内容会得到稳定 ID，和 C2 的文件完整性检查可以自然衔接。

当前 PDF 解析没有强行引入新依赖。原因是这个阶段的目标是先打通最小可运行链路。未来如果安装了更专业的 PDF 解析库，比如 `pypdf` 或 PyMuPDF，就可以增强文本和图片提取能力；但现在即使没有这些依赖，测试里的基础文本 PDF 也能跑通。

图片提取在当前阶段先安全降级为 `metadata.images = []`。这不代表图片能力不重要，而是先保证文本链路稳定。后续 C7 `ImageCaptioner` 和 C13 `ImageStorage` 会继续补齐图片相关能力。
