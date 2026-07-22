# G3_data_browser 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 Dashboard 的“数据浏览器页面”。

前面 G1 搭好了 Dashboard 的六页框架，G2 实现了 `DocumentManager`，可以从多个底层存储里统一管理文档。G3 就是在这个基础上，把“已经摄取进知识库的数据”展示到网页里。

现在 Data Browser 页面可以查看当前 collection 下有哪些文档，每个文档有多少 chunk、多少图片，还可以搜索文档，并展开查看某个文档的 chunk 文本、metadata 和图片索引信息。

在整个 RAG 项目中，G3 属于“可视化数据管理层”。它不负责摄取文档，也不负责检索回答，而是帮助用户看清楚：知识库里现在到底有什么数据，这些数据是怎么被切成 chunk 的，每个 chunk 带了哪些元数据。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/dashboard/services/data_service.py` | 新增 Dashboard 数据服务，封装 `DocumentManager`，把文档、chunk、图片数据整理成页面友好的字典格式 |
| `src/observability/dashboard/pages/data_browser.py` | 实现数据浏览器页面，支持 collection 筛选、文档搜索、文档列表、chunk 详情和图片信息展示 |
| `tests/unit/test_dashboard_data_service.py` | 新增 DataService 单元测试，验证 collection、文档列表、文档详情格式化 |
| `tests/unit/test_dashboard_app.py` | 更新 Dashboard 页面测试，增加 Data Browser 页面渲染验证 |
| `DEV_SPEC.md` | 更新 G3 完成状态 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步更新开发进度 |

## 3. 核心调用关系

```text
用户打开 Dashboard
  -> app.py 进入 Data Browser 页面
  -> data_browser.render(st)
  -> 调用 DataService
  -> DataService 调用 DocumentManager
  -> DocumentManager 读取 ChromaStore / ImageStorage / FileIntegrity
  -> DataService 把对象整理成字典
  -> data_browser.py 用 Streamlit 展示文档表格和详情
```

页面上查看文档详情时：

```text
用户选择某个文档
  -> data_browser.py 取出 source_path
  -> DataService.get_document_detail(source_path)
  -> DocumentManager.get_document_detail(source_path)
  -> 返回 chunks、metadata、images、integrity_record
  -> 页面用 expander 展开显示 chunk 文本和 metadata
```

## 4. 每个核心文件的作用

### 文件：`src/observability/dashboard/services/data_service.py`

* 主要职责：给 Dashboard 页面提供“已经整理好的数据”。
* 关键类 / 函数：
  * `DataService`：Dashboard 数据浏览服务。
  * `document_manager`：懒加载 `DocumentManager`，需要时才读取 settings 并创建底层存储对象。
  * `list_collections()`：从文档列表里收集所有 collection 名称。
  * `list_documents(collection, query)`：返回页面表格可直接展示的文档行，并支持搜索过滤。
  * `get_document_detail(doc_id)`：返回某个文档的详情，包括 chunk、metadata、图片和完整性记录。
  * `collection_stats(collection)`：返回文档数、chunk 数、图片数等统计。
* 输入是什么：settings 路径，或者测试时注入的 `DocumentManager`。
* 输出是什么：普通字典和列表，方便 Streamlit 页面直接展示。
* 在项目中的作用：作为 Dashboard 页面和 `DocumentManager` 之间的适配层。

### 文件：`src/observability/dashboard/pages/data_browser.py`

* 主要职责：渲染数据浏览器页面。
* 关键函数：
  * `render(st, data_service=None)`：页面入口，加载 collection、搜索框、文档列表和详情。
  * `_render_document_detail(st, detail)`：展示单个文档的 metadata、chunk 和图片信息。
* 输入是什么：Streamlit 对象，以及可选的 `DataService`。
* 输出是什么：Dashboard 中的数据浏览页面。
* 在项目中的作用：让用户通过网页查看知识库内容，而不是手动打开 Chroma JSON、SQLite 或日志文件。

### 文件：`tests/unit/test_dashboard_data_service.py`

* 主要职责：验证 `DataService` 不依赖真实数据库也能正确整理数据。
* 关键测试：
  * 验证 collection 列表。
  * 验证文档列表字段格式。
  * 验证文档详情里的 chunk preview、image_refs、images、integrity_record。
* 在项目中的作用：保证数据服务层稳定，后续页面改动时不容易破坏数据格式。

### 文件：`tests/unit/test_dashboard_app.py`

* 主要职责：验证 Dashboard 页面注册和页面渲染逻辑。
* 本阶段变化：
  * Data Browser 不再是简单占位页，所以测试改为使用 fake Streamlit 和 fake DataService 来验证页面渲染。
* 在项目中的作用：在不启动真实浏览器的情况下，确认页面逻辑能跑通。

## 5. 新手重点理解

这一阶段最重要的是理解“页面代码”和“数据整理代码”为什么要分开。

`data_browser.py` 负责页面展示，比如 selectbox、text_input、dataframe、expander。这些都是 Streamlit 相关的 UI 逻辑。它不应该直接关心 ChromaStore 怎么读、FileIntegrity 怎么查、图片索引在哪里。

`DataService` 则负责把底层复杂对象整理成简单字典。比如 `DocumentInfo` 是一个 dataclass，但页面表格更适合用普通 dict 列表展示；chunk 的原文可能很长，所以 `DataService` 会生成一个 `preview` 字段，用于 expander 标题；metadata 里如果有 `image_refs`，也会单独整理出来。

这样拆分之后，后续维护会轻松很多。页面想换展示方式，可以主要改 `data_browser.py`；底层数据结构变了，可以主要改 `DataService`。这就是典型的“展示层”和“服务层”分离。

另一个重点是 G3 依赖 G2。G3 并不自己直接跨存储读取数据，而是通过 `DocumentManager` 间接获取文档信息。这个设计让 Dashboard 不需要知道一个文档的数据到底分散在 Chroma、BM25、SQLite 还是图片目录里。对页面来说，一个文档就是一个可以展示的对象。

从 RAG 角度看，数据浏览器非常重要。很多 RAG 问题不是模型回答错了，而是数据在摄取时就已经切坏了、metadata 丢了、图片引用没挂上、collection 放错了。G3 提供的页面就是用来快速检查这些问题的：看文档是否存在、chunk 是否合理、metadata 是否完整、图片是否关联成功。

# 整体结构与流程

1. 文件定位
在项目中的作用：本文件是 RAG（检索增强生成）系统可视化面板（Dashboard）的数据访问服务层。
所处层级：它处于“前端展示层”与“底层核心业务层”的中间地带。向下对接 DocumentManager（文档管理器）及各类底层存储引擎，向上为 Dashboard 的页面路由提供数据接口。
核心职责：扮演 “数据翻译官与过滤器” 的角色。底层存储返回的是复杂的 Python 数据类对象（如 DocumentInfo、DocumentDetail），而前端需要的是简单的字典（JSON）格式。该文件负责提取底层数据，进行关键字过滤、字段拼接、文本截断等加工，最终输出前端直接可用的标准化字典数据。
2. 函数拆解
核心类：DataService
init
目的：初始化服务，接收配置文件路径和可选的文档管理器实例。
输入：settings_path（配置路径），document_manager（文档管理器，支持外部依赖注入）。
输出：无。
document_manager (属性)
目的：懒加载文档管理器。如果外部没传入，就自动读取配置并实例化一个包含向量库、BM25索引、图片存储等组件的完整底层管理器。
list_collections
目的：获取系统中所有的文档集合（Collection）名称。
输入：无。
输出：排序后的集合名称列表（如 ["技术文档", "产品手册"]）。
list_documents
目的：获取文档列表，支持按集合和关键字进行过滤。
输入：collection（集合名），query（搜索关键字）。
输出：格式化后的文档字典列表。
get_document_detail
目的：获取单个文档的详细信息（包含分块、图片等）。
输入：doc_id（文档ID）。
输出：格式化后的文档详情字典。
collection_stats
目的：获取集合级别的统计信息（如文档数、分块数等）。
输入：collection（集合名）。
输出：统计信息字典。
辅助格式化函数（私有函数）
_document_row：将 DocumentInfo 对象转换为包含基础信息的字典（ID、路径、分块数、处理时间等）。
_detail_payload：将 DocumentDetail 对象转换为包含基础信息、元数据、分块列表、图片列表的完整详情字典。
_chunk_payload：处理单个文本块（Chunk），提取文本、生成预览、提取关联的图片引用。
_document_matches_query：在文档的 ID、路径、集合、哈希、标题、摘要中查找是否包含搜索关键字（简单的全文本匹配）。
_preview：文本截断工具。将多行文本合并为单行，如果超过限制长度（默认160字符），则截断并加上 ...。
3. 执行流程
初始化阶段：Dashboard 启动时，实例化 DataService。当首次调用数据方法时，触发 document_manager 属性，懒加载初始化底层的 DocumentManager 及其依赖的存储组件。
列表查询链路：
调用 list_documents -> 底层 DocumentManager.list_documents 获取原始对象列表。
若传入了 query，调用 _document_matches_query 在内存中进行关键字过滤。
遍历过滤后的对象，调用 _document_row 将其转换为字典列表返回。
详情查询链路：
调用 get_document_detail -> 底层 DocumentManager.get_document_detail 获取原始详情对象。
调用 _detail_payload 进行整体结构转换。
内部递归调用 _document_row 转换基础信息，调用 _chunk_payload 转换每个文本块。
在 _chunk_payload 中，调用 _preview 生成长文本的预览摘要。
最终组装成完整的详情字典返回给前端。
4. 场景示例
场景：运维工程师小李打开 RAG 系统的 Dashboard，想查看“产品手册”集合下的文档，并点开其中一篇名为《V2.0更新日志》的文档查看具体的分块内容。

加载集合：页面初始化时，前端调用 list_collections()，系统从底层查出所有集合，小李在下拉框看到了“产品手册”。
筛选文档：小李选择“产品手册”，前端调用 list_documents(collection="产品手册")。系统从底层拉取该集合的文档，并通过 _document_row 转换为包含文件名、分块数、处理时间的列表，展示在表格中。
搜索文档：小李在搜索框输入“V2.0”，前端调用 list_documents(collection="产品手册", query="v2.0")。系统调用 _document_matches_query，在文档的标题和摘要中匹配到了《V2.0更新日志》，并返回该文档的行数据。
查看详情：小李点击该文档，前端调用 get_document_detail(doc_id="doc_123")。
数据加工：系统底层返回包含几十个分块的原始对象。_detail_payload 开始工作，它调用 _document_row 提取基础信息，然后遍历所有分块调用 _chunk_payload。
文本预览：在 _chunk_payload 处理某个长达 500 字的分块时，调用 _preview 函数。_preview 将文本压缩成一行，并截断到 157 个字符加上 ...，生成 preview 字段。
最终渲染：前端拿到这个包含基础信息、元数据、以及带有预览文本的分块列表的字典，完美渲染出文档详情页，小李可以直观地看到每个分块的摘要和关联图片。



# 整体结构与流程

文件定位
文件路径：src/observability/dashboard/pages/data_browser.py 项目作用：该文件是项目可观测性仪表盘（Dashboard）中的一个核心页面模块，专门负责“数据浏览（Data Browser）”功能。 所处层级：属于表现层（UI/前端展示层），基于 Streamlit 框架构建。 核心职责：将底层向量数据库或文档存储中已索引的复杂数据（如原始文档、文本分块、元数据、关联图像等）以直观、可视化的方式呈现给管理员或用户，方便他们检查数据摄入（Ingestion）的结果和质量。

函数拆解
1. render(st, data_service: DataService | None = None)
作用目的：页面的主入口函数，负责渲染整个数据浏览页面的布局和交互逻辑。
输入输出：
输入：st（Streamlit 模块实例，用于绘制 UI 组件），data_service（数据服务实例，用于查询底层数据，可选）。
输出：无返回值（None），直接通过 st 将 UI 渲染到网页上。
核心功能：
集合与搜索：提供下拉框让用户选择数据集合（Collection），并提供文本框进行文档搜索。
数据获取：根据用户的筛选条件，调用 data_service 获取文档列表和统计数据。
指标展示：在页面顶部展示三个核心指标卡片：文档数、分块数（Chunks）、图像数。
列表与详情：使用表格展示文档列表，并提供下拉框让用户选择具体文档，进而触发详情的加载与渲染。
2. _render_document_detail(st, detail: dict)
作用目的：辅助函数，专门用于渲染单个文档的详细信息面板。
输入输出：
输入：st（Streamlit 实例），detail（包含文档详细信息的字典数据）。
输出：无返回值，直接渲染 UI。
核心功能：
基础信息：展示文档名称、源路径、文档 ID 和文件哈希值。
元数据展示：使用可折叠面板（Expander）以 JSON 格式展示文档的元数据。
分块（Chunks）展示：遍历文档的所有文本分块，每个分块作为一个可折叠面板，展示其预览标题、完整文本和元数据。
图像展示：遍历关联的图像列表，展示图像 ID 和路径；如果图像文件在本地磁盘存在，则直接在页面上渲染出图片。
执行流程
页面初始化：render 函数被调用，设置页面标题和说明文字。
加载筛选条件：调用 service.list_collections() 获取所有集合，渲染集合选择框；同时渲染搜索输入框。
查询与统计：根据用户选择的集合和输入的搜索词，调用 list_documents 获取文档列表，调用 collection_stats 获取统计信息。若发生异常，则显示错误提示并终止。
渲染统计指标：将获取到的文档数、分块数、图像数渲染为三个并排的指标卡片。
渲染文档列表：如果文档列表为空，提示用户；否则，使用 st.dataframe 渲染数据表格。
选择文档详情：根据文档列表生成带摘要的下拉选项，用户选择后，提取对应的 source_path。
获取并渲染详情：调用 get_document_detail 获取该路径下的完整详情数据，然后将其传递给 _render_document_detail 函数。
详情内部渲染：_render_document_detail 依次渲染文档基础信息、元数据 JSON、分块文本列表，最后检查并渲染本地图像文件。
场景示例
业务场景：假设你是一名知识库管理员，刚刚将一份名为《2023年产品操作手册.pdf》的文档导入到 RAG 系统中，你想检查系统是否正确解析了里面的文字和图片。

全流程串联：

进入页面：你打开 Dashboard 的“Data Browser”页面。
筛选数据：在“Collection”下拉框中，你选择了存放产品文档的集合 product_docs。在搜索框中输入“操作手册”。
查看概览：页面顶部立刻刷新，显示指标卡片：Documents: 1，Chunks: 120，Images: 15。你心里有数了：系统识别出了 1 个文档，切成了 120 个文本块，并提取了 15 张图。
定位文档：下方的表格里出现了《2023年产品操作手册.pdf》。你在“Document detail”下拉框中选中它。
查看详情：
页面下方展示了该文档的路径和唯一 ID。
你展开 “Document metadata”，看到了 PDF 的原作者、创建时间等 JSON 信息。
你展开 “Chunks” 区域，看到了 120 个文本块。你点开其中一个名为“第3章 核心功能”的折叠面板，检查了切分后的文本是否通顺，有无乱码。
滑到最下方的 “Images” 区域，系统列出了 15 张图片。因为图片文件真实存在于服务器磁盘上，页面直接渲染出了这些图片的缩略图，你确认系统成功提取了手册里的架构图和流程图。
结论：通过这一套流畅的可视化流程，你确认数据摄入完美成功，可以安心让前端用户进行问答检索了。