# G4_ingestion_manager 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 Dashboard 的 Ingestion 管理页面。

前面 C 阶段已经有了命令行摄取脚本 `scripts/ingest.py`，可以把文件送进 RAG 摄取流水线；F5 又给 `IngestionPipeline.run()` 加了 `on_progress` 回调，可以实时知道 pipeline 跑到了哪一步。G4 的目标，就是把这些能力接到网页里。

现在用户可以在 Dashboard 里上传文件，选择 collection，点击按钮触发摄取，并看到实时进度。页面还可以列出已经摄取的文档，并提供删除入口。也就是说，G4 把“命令行摄取”升级成了“网页管理摄取”。

在整个 RAG 项目中，G4 属于数据摄取管理层。它不重新实现 Loader、Splitter、Embedding、VectorStore，而是调用已有的 `IngestionPipeline` 和 `DocumentManager`，把这些底层能力包装成一个更容易操作的 Web 页面。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/dashboard/services/ingestion_service.py` | 新增 IngestionService，负责保存上传文件、调用 pipeline、收集进度、删除文档 |
| `src/observability/dashboard/pages/ingestion_manager.py` | 实现 Ingestion 管理页面，包括上传、进度条、摄取结果、文档列表和删除入口 |
| `tests/unit/test_dashboard_ingestion_service.py` | 新增 IngestionService 单元测试，验证上传保存、pipeline 调用、进度回调和删除 |
| `tests/unit/test_dashboard_app.py` | 更新 Dashboard 页面测试，验证 Ingestion Manager 页面可在 fake Streamlit 下运行 |
| `DEV_SPEC.md` | 更新 G4 完成状态 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步更新开发进度 |

## 3. 核心调用关系

上传并摄取文档时：

```text
用户在 Dashboard 上传文件
  -> ingestion_manager.render(st)
  -> IngestionService.ingest_upload(uploaded_file, collection, force, on_progress)
  -> 保存文件到 data/documents/<collection>/<filename>
  -> 调用 IngestionPipeline.run(path, collection, force, on_progress)
  -> pipeline 执行 integrity/load/image_store/split/embed/upsert/bm25_index
  -> on_progress 回调更新页面进度条
  -> 返回摄取结果给页面展示
```

删除文档时：

```text
用户在 Manage Documents 中选择文档
  -> ingestion_manager.py 调用 IngestionService.delete_document(...)
  -> IngestionService 调用 DocumentManager.delete_document(...)
  -> DocumentManager 协调删除 Chroma/BM25/ImageStorage/FileIntegrity
  -> 页面展示删除了多少 vector、bm25、image、integrity 记录
```

## 4. 每个核心文件的作用

### 文件：`src/observability/dashboard/services/ingestion_service.py`

* 主要职责：把 Dashboard 的上传/删除操作转成后端可执行动作。
* 关键类 / 函数：
  * `IngestionService`：Dashboard ingestion 管理服务。
  * `pipeline`：懒加载 `IngestionPipeline`。
  * `document_manager`：懒加载 `DocumentManager`。
  * `list_documents()`：给页面返回可删除的文档列表。
  * `ingest_upload()`：保存上传文件，并调用 `IngestionPipeline.run()`。
  * `delete_document()`：调用 `DocumentManager.delete_document()` 并返回普通字典。
  * `_uploaded_name()`：校验上传文件名。
  * `_uploaded_bytes()`：读取上传文件内容。
  * `_safe_segment()`：校验 collection，避免路径穿越。
* 输入是什么：Streamlit 上传文件对象、collection、force 开关、进度回调。
* 输出是什么：摄取结果字典或删除结果字典。
* 在项目中的作用：作为 Dashboard 页面和 ingestion/document 管理后端之间的服务层。

### 文件：`src/observability/dashboard/pages/ingestion_manager.py`

* 主要职责：渲染 Ingestion 管理页面。
* 关键函数：
  * `render(st, ingestion_service=None)`：页面入口。
  * `_render_upload(st, service)`：渲染上传区、collection 输入、force 开关、进度条和摄取结果。
  * `_render_delete_controls(st, service)`：渲染已摄取文档列表和删除按钮。
* 输入是什么：Streamlit 对象，以及可选的 `IngestionService`。
* 输出是什么：可上传、可摄取、可删除文档的 Dashboard 页面。
* 在项目中的作用：让用户不用命令行，也能在浏览器里管理知识库摄取。

### 文件：`tests/unit/test_dashboard_ingestion_service.py`

* 主要职责：验证 `IngestionService` 的核心行为。
* 关键测试：
  * 上传文件会保存到 `data/documents/<collection>/`。
  * 会正确调用 pipeline，并传入 collection、force 和 progress callback。
  * 会拒绝不支持的文件类型、非法 collection 和空文件。
  * 删除文档时会调用 DocumentManager。
* 在项目中的作用：保证服务层逻辑稳定，避免页面操作误写路径或漏传参数。

### 文件：`tests/unit/test_dashboard_app.py`

* 主要职责：验证 Dashboard 页面在不启动真实浏览器时也能跑通。
* 本阶段变化：
  * 增加 fake Streamlit 上传文件、按钮、进度条等方法。
  * 验证 Ingestion Manager 页面能触发上传摄取并展示文档列表。
* 在项目中的作用：让页面逻辑可以自动化回归，而不是只能靠人工点击测试。

## 5. 新手重点理解

这一阶段最重要的是理解“Dashboard 页面不应该直接操作复杂后端”。

如果 `ingestion_manager.py` 直接负责保存文件、读取 settings、创建 pipeline、处理进度、删除文档，页面代码会很快变得难以维护。所以这里单独抽出了 `IngestionService`。页面只关心用户交互，服务层负责真正的业务动作。

第二个重点是上传文件的保存位置。网页上传进来的文件不是天然存在于项目目录里的，它只是一个上传对象。`IngestionService.ingest_upload()` 会先把它保存到 `data/documents/<collection>/<filename>`，然后再把这个本地路径交给 `IngestionPipeline.run()`。这样 pipeline 仍然处理普通文件路径，不需要理解 Streamlit 的上传对象。

第三个重点是进度回调。F5 已经让 pipeline 支持 `on_progress(stage, current, total)`。G4 在页面里把这个回调接到 `st.progress()` 和状态文本上，所以用户可以看到摄取从 load、split、embed、upsert 等阶段一步步推进。这个连接点体现了前面阶段的铺垫价值。

最后要理解删除动作为什么走 `DocumentManager`。删除一个文档不是删一个文件那么简单，它还涉及 Chroma 向量、BM25 索引、图片文件、完整性记录。G4 页面只调用 `IngestionService.delete_document()`，再由 `DocumentManager` 统一协调，这样页面不会被底层存储细节拖乱。

从项目演示角度看，G4 是很关键的一步。它让用户可以直接在浏览器中完成“上传文档 -> 摄取入库 -> 查看进度 -> 管理已摄取文档”的闭环，这比单纯命令行体验更接近真实产品。


# 整体结构与流程

以下是对 ingestion_service.py 文件的完整解析：

一、 文件定位
项目作用：该文件是可观测性仪表盘（Dashboard）中的文档摄入（Ingestion）管理服务。
所处层级：属于服务层（Service Layer）。它向上为 UI 界面（如 Streamlit 页面）提供简单、安全的接口，向下封装并调用核心的业务逻辑组件（如 IngestionPipeline 和 DocumentManager）。
核心职责：负责处理用户上传的文件（校验、保存）、触发数据解析与向量化流程（摄入），以及协调文档的删除和列表查询。它相当于 UI 和底层复杂 AI 数据管道之间的“安全网关”和“调度员”。
二、 函数拆解
1. 核心类 IngestionService 的方法
init

目的：初始化服务。
输入：配置文件路径、文档存储根目录，以及可选的底层管道和管理器（方便测试时注入 Mock 对象）。
功能：保存基础配置，初始化内部状态。
pipeline (属性)

目的：懒加载获取数据摄入管道。
功能：首次调用时读取配置并实例化 IngestionPipeline，后续直接返回缓存实例，避免重复创建。
document_manager (属性)

目的：懒加载获取文档管理器。
功能：首次调用时组装向量库（Chroma）、全文检索（BM25）、图片存储和 SQLite 检查器，生成统一的文档管理实例。
list_documents

目的：获取文档列表。
输入：可选的 collection（集合/分类）名称。
输出：文档信息字典列表。
功能：内部委托给 DataService，为 UI 的“数据管理”页面提供数据源。
ingest_upload

目的：处理文件上传并执行数据摄入（核心方法）。
输入：上传的文件对象、目标 collection 名称、是否强制覆盖（force）、进度回调函数。
输出：包含处理结果（如分块数、向量 ID、文件哈希等）和进度事件的字典。
功能：校验文件名和类型 -> 保存文件到本地 -> 运行底层管道进行解析和向量化 -> 收集并返回结果。
delete_document

目的：删除指定文档。
输入：文档的源路径、可选的 collection 名称。
输出：删除结果的字典。
功能：调用底层 document_manager 清理向量库、索引、本地文件等所有相关数据。
_save_upload

目的：将上传的文件落盘保存。
输入：文件对象、collection、文件名。
输出：保存后的本地文件路径（Path）。
功能：在 documents_root/collection 目录下创建文件夹，并将文件字节流写入磁盘。
2. 模块级辅助函数
_uploaded_name
目的：安全提取文件名。
功能：从上传对象中获取 name 属性，去除路径信息（防止路径穿越攻击），确保文件名合法。
_uploaded_bytes
目的：提取文件字节内容。
功能：兼容 Streamlit 等框架的上传对象，通过 getvalue() 或 read() 方法读取文件的二进制内容。
_safe_segment
目的：安全校验字符串（如 collection 名称）。
功能：确保字符串非空，且不包含路径分隔符（/ 或 [](file://d:\RAG\MODULAR-RAG-CLEAN-START\DEV_SPEC.md)），彻底杜绝目录穿越漏洞。
三、 执行流程
上传与摄入链路： UI 触发上传 ➔ ingest_upload ➔ _safe_segment (校验集合名) ➔ _uploaded_name (校验文件名) ➔ 校验文件后缀 ➔ _save_upload (文件落盘) ➔ pipeline.run (执行解析、分块、向量化) ➔ record_progress (回调进度) ➔ 返回结果字典给 UI。
删除链路： UI 触发删除 ➔ delete_document ➔ document_manager.delete_document (清理向量、索引、本地文件) ➔ 返回结果字典给 UI。
列表查询链路： UI 请求列表 ➔ list_documents ➔ DataService.list_documents ➔ 返回文档列表给 UI。
四、 场景示例
业务场景：用户在 Dashboard 的“数据导入”页面，上传了一份名为 smartphone_manual.pdf 的产品手册，并指定分类（Collection）为 electronics。

全流程串联讲解：

安全校验：用户点击上传后，ingest_upload 首先调用 _safe_segment 检查 electronics 是否包含非法字符（确认安全）；接着调用 _uploaded_name 提取出纯净的文件名 smartphone_manual.pdf，并检查 .pdf 是否在允许的格式列表中。
文件落盘：校验通过后，_save_upload 在 data/documents/electronics/ 目录下创建文件夹，并将 PDF 的二进制内容写入磁盘，生成物理文件。
数据摄入（核心）：文件保存后，系统调用 pipeline.run。底层管道开始工作：读取 PDF 内容，提取文本和插图，将长文本切分成多个小段落（Chunks），调用大模型生成向量，并存入 ChromaDB 向量库，同时更新 BM25 全文索引。
进度反馈：在管道运行的过程中，record_progress 函数会不断捕获当前阶段（如“正在解析”、“正在向量化”）和进度百分比，实时反馈给前端 UI 显示进度条。
结果返回：处理完成后，ingest_upload 将结果打包成字典（包含生成了 50 个文本块、文档 ID、向量 ID 列表等）返回给前端。前端弹出提示：“导入成功！共生成 50 个知识块”。
后续管理：几天后，用户发现手册有误，在“数据管理”页面选中该文档点击“删除”。系统调用 delete_document，底层的 document_manager 会像清道夫一样，把向量库里的向量、BM25 索引、SQLite 记录以及磁盘上的 PDF 文件全部彻底清除，保证数据一致性。






# 整体结构与流程


文件解析：ingestion_manager.py
一、文件定位
文件路径：src/observability/dashboard/pages/ingestion_manager.py

项目层级：该文件属于项目的 Dashboard（仪表盘）层，具体是仪表盘中的一个 页面模块（page）。

核心职责： 这个文件是一个 文档摄入管理页面，可以理解为一个"文档上传与管理的控制台"。它负责：

上传文档：让用户选择文件并上传到系统中进行解析和向量化
查看进度：实时展示文档处理的进度条和状态信息
管理文档：查看已入库的文档列表，并支持删除指定文档
简单来说，这个文件就是一个 Web 界面的"前端控制器"，它调用后端的 IngestionService 服务来完成实际的业务逻辑，自己只负责界面渲染和用户交互。

二、函数拆解
1. render(st, ingestion_service) —— 页面主入口
项目	说明
作用	整个页面的入口函数，负责渲染页面标题和两个子模块
输入	st：Streamlit 实例（用于渲染 UI 组件）；ingestion_service：可选的摄入服务实例
输出	无返回值，直接在页面上渲染 UI
核心逻辑	① 如果没有传入服务实例，就自动创建一个 IngestionService()<br>② 渲染页面标题和说明文字<br>③ 依次调用上传模块和删除模块的渲染函数
🎯 通俗理解：就像一个大厨（render）打开厨房（页面），先挂上招牌（标题），然后安排两个厨师分别负责"做菜"（上传）和"收拾桌子"（删除）。

2. _render_upload(st, service) —— 上传与摄入模块
项目	说明
作用	渲染文档上传界面，处理上传逻辑和进度展示
输入	st：Streamlit 实例；service：IngestionService 服务实例
输出	无返回值，渲染上传相关的 UI 组件
核心逻辑	① 创建文件上传器（支持 pdf/txt/md/docx）<br>② 创建目标 collection 输入框和强制重新摄入复选框<br>③ 创建进度条和状态显示区域<br>④ 点击"Start Ingestion"按钮后，调用 service.ingest_upload() 执行摄入<br>⑤ 根据结果展示成功/跳过/失败信息<br>⑥ 提供可展开的进度事件详情
🎯 通俗理解：这就是一个"快递收件台"——你选好文件（包裹），填好目的地（collection），点下按钮后，系统开始处理，进度条实时显示处理到哪一步了。

内部回调函数 on_progress：

每次后端报告进度时，更新进度条百分比和状态文字
3. _render_delete_controls(st, service) —— 文档管理/删除模块
项目	说明
作用	渲染已入库文档列表，支持按 collection 筛选和删除操作
输入	st：Streamlit 实例；service：IngestionService 服务实例
输出	无返回值，渲染文档列表和删除操作的 UI 组件
核心逻辑	① 提供 collection 筛选输入框<br>② 调用 service.list_documents() 获取文档列表<br>③ 用表格展示文档信息（来源名、chunk数、路径）<br>④ 提供下拉框选择要删除的文档<br>⑤ 点击"Delete"按钮后，调用 service.delete_document() 执行删除<br>⑥ 展示删除结果（向量/BM25/图片/完整性各删了多少条）
🎯 通俗理解：这就是一个"仓库管理台"——先看看仓库里都有什么货（文档列表），选一个不需要的，点删除，系统会从各个存储引擎（向量库、BM25索引、图片库等）中把相关数据全部清除。

三、执行流程
用户打开 Ingestion Manager 页面
        │
        ▼
  render() 被调用
        │
        ├──► 创建/获取 IngestionService 实例
        │
        ├──► 渲染页面标题和说明
        │
        ├──► 调用 _render_upload()
        │       │
        │       ├── 渲染上传组件（文件选择器、collection输入、进度条）
        │       │
        │       ├── 用户点击 "Start Ingestion"
        │       │       │
        │       │       ▼
        │       │   service.ingest_upload() ← 调用后端服务
        │       │       │
        │       │       ├── 文件落盘
        │       │       ├── 文档解析 & 分块
        │       │       ├── 向量化 & 入库
        │       │       └── 通过 on_progress 回调实时更新进度
        │       │
        │       └── 展示结果（成功/跳过/失败 + 进度详情）
        │
        └──► 调用 _render_delete_controls()
                │
                ├── 渲染筛选框和文档列表表格
                │
                ├── 用户选择文档并点击 "Delete"
                │       │
                │       ▼
                │   service.delete_document() ← 调用后端服务
                │       │
                │       ├── 从向量库删除
                │       ├── 从BM25索引删除
                │       ├── 从图片库删除
                │       └── 从完整性记录删除
                │
                └── 展示删除结果统计
调用关系总结：

render() → _render_upload() → service.ingest_upload()
render() → _render_delete_controls() → service.list_documents() / service.delete_document()
四、场景示例
📖 场景：小明上传一份产品手册并管理文档

第一步：打开页面 小明打开 Dashboard，进入 "Ingestion Manager" 页面。页面顶部显示标题 "Ingestion Manager" 和说明文字。

第二步：上传文档 小明想上传一份 产品手册v2.pdf：

他在文件上传器中选择了 产品手册v2.pdf
在 "Target collection" 输入框中填入 product_docs（表示这份文档归到产品文档集合中）
他勾选了 "Force re-ingestion"（因为之前上传过旧版本，需要强制重新处理）
点击 "Start Ingestion" 按钮
第三步：等待处理 系统开始工作，进度条开始走动：

状态显示：parsing: 3/10（正在解析第3页，共10页）
状态显示：chunking: 7/15（正在分第7个chunk，共15个）
状态显示：embedding: 12/15（正在向量化第12个chunk）
最终进度条走到 100%
第四步：查看结果 页面显示绿色成功提示：

✅ Ingested product_docs/产品手册v2.pdf: chunks=15, records=15, images=3

小明展开 "Progress events" 查看详细的处理日志。

第五步：管理文档 几天后，小明想清理一些过时文档：

他在 "Delete filter collection" 中输入 product_docs 进行筛选
表格展示了该集合下的所有文档
他从下拉框中选择了旧版本的 产品手册v1.pdf
点击 "Delete Selected Document"
第六步：确认删除 系统从向量库、BM25索引、图片库中彻底清除该文档的所有数据，页面显示：

✅ Deleted vectors=12, bm25=12, images=2, integrity=1

整个流程完成！小明通过这个页面，完成了文档的 上传→处理→查看→清理 全生命周期管理。