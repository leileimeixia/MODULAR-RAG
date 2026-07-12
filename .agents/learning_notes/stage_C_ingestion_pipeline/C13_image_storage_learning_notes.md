# C13_image_storage 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `ImageStorage`，它负责把图片文件保存到本地文件系统，并用 SQLite 维护 `image_id -> file_path` 的索引映射。

在 RAG 项目里，图片来自 PDF Loader 或后续多模态处理。前面阶段会在 `metadata.images` 中记录图片引用，但仅有 metadata 还不够，系统还需要知道图片文件真实保存在哪里。C13 就是在做这件事：

```text
图片 bytes / 图片源文件
  -> ImageStorage.save_image(...)
  -> 保存到 data/images/{collection}/{image_id}.png
  -> 写入 data/db/image_index.db
  -> 后续 ImageCaptioner / Dashboard / DocumentManager 查询使用
```

本阶段也实现了按 collection 和 doc_hash 查询图片，以及删除图片文件和索引记录，为后续文档删除、Dashboard 图片预览打基础。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/storage/image_storage.py` | 实现图片文件保存、SQLite 索引、查询和删除 |
| `src/ingestion/storage/__init__.py` | 对外导出 `ImageStorage` 和 `ImageStorageError` |
| `tests/unit/test_image_storage.py` | 验证文件落盘、索引写入、WAL、过滤查询、删除、并发写入和 trace |
| `DEV_SPEC.md` | 将 C13 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> ImageStorage(image_root, db_path)
      -> 创建 data/images
      -> 创建 data/db/image_index.db
      -> 初始化 image_index 表和索引

ImageStorage.save_image(image_id, source, collection, doc_hash, page_num)
  -> 校验 image_id / collection
  -> 判断图片扩展名
  -> 保存 bytes 或复制源图片文件
  -> INSERT INTO image_index
  -> 返回图片保存路径

ImageStorage.get_path(image_id)
  -> 查询 SQLite
  -> 返回 file_path

ImageStorage.list_images(collection?, doc_hash?)
  -> 按条件查询 image_index
  -> 返回图片索引行

ImageStorage.delete_images(collection?, doc_hash?)
  -> 查出匹配图片
  -> 删除文件
  -> 删除 SQLite 记录
```

数据流可以理解成：

```text
图片内容
  -> 文件系统路径
  -> SQLite 索引表
  -> 后续模块根据 image_id 找回图片路径
```

## 4. 每个核心文件的作用

### 文件：`src/ingestion/storage/image_storage.py`

- 主要职责：保存图片文件，并维护图片索引表。
- 关键函数 / 类：
  - `ImageStorage`：图片存储主类。
  - `save_image(...)`：保存图片并写入 SQLite 映射。
  - `get_path(image_id)`：根据 image_id 查询图片路径。
  - `list_images(collection, doc_hash)`：列出图片索引，可按 collection/doc_hash 过滤。
  - `delete_images(collection, doc_hash)`：删除匹配图片文件和索引记录。
  - `_initialize()`：创建 SQLite 表、索引，并启用 WAL。
  - `_write_image(...)`：处理 bytes 写入或源文件复制。
  - `_resolve_extension(...)`：决定保存文件扩展名。
  - `_validate_identifier(...)`：校验 image_id/collection，避免路径穿越。
- 输入是什么：
  - 图片 bytes，或者已有图片文件路径。
  - `image_id`
  - `collection`
  - 可选 `doc_hash`、`page_num`、`extension`、`trace`
- 输出是什么：
  - 保存后的图片路径字符串。
  - SQLite 中的索引记录。
- 在项目中的作用：
  - 为多模态 RAG 提供图片文件存储和图片路径查询能力。

### 文件：`src/ingestion/storage/__init__.py`

- 主要职责：暴露 storage 阶段的公共入口。
- 关键函数 / 类：
  - `ImageStorage`
  - `ImageStorageError`
  - 已有的 `BM25Indexer`、`VectorUpserter`
- 输入是什么：无直接业务输入。
- 输出是什么：包级导入入口。
- 在项目中的作用：
  - 让 pipeline、Dashboard 或 DocumentManager 可以通过 `from ingestion.storage import ImageStorage` 使用图片存储能力。

### 文件：`tests/unit/test_image_storage.py`

- 主要职责：验证 `ImageStorage` 的行为契约。
- 关键测试：
  - 保存 bytes 后文件真实存在，SQLite 能查到路径。
  - 保存已有图片文件时沿用源文件后缀。
  - 同一个 image_id 再次保存会替换映射。
  - 支持按 collection、doc_hash 查询。
  - SQLite 数据库启用 WAL，并创建 collection/doc_hash 索引。
  - 删除图片时同时删除文件和索引记录。
  - 查不存在的 image_id 会报错。
  - 空 bytes、非法 id、缺失源文件会报错。
  - 支持并发写入。
  - 支持 trace 记录 `image_storage` 阶段。
- 输入是什么：
  - pytest 的 `tmp_path`
  - 图片 bytes 或临时图片文件
  - `TraceContext`
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 确保图片存储不会只写文件忘记索引，也不会只写索引忘记文件。

## 5. 新手重点理解

`ImageStorage` 解决的是“图片文件在哪里”的问题。

在文本 RAG 里，我们通常只需要保存 chunk 文本和向量。但多模态 RAG 里，chunk 可能引用图片，例如：

```text
See [IMAGE: img-1]
```

这时系统需要根据 `img-1` 找到真实图片文件，才能给 Vision LLM 生成 caption，或者在 Dashboard 里展示图片预览。

为什么既要保存文件，又要保存 SQLite 索引？因为文件系统适合存放图片二进制内容，SQLite 适合快速查找映射关系。图片本身放在 `data/images/{collection}/`，索引放在 `data/db/image_index.db`，两者各司其职。

为什么要有 collection？因为项目后续可能有多个知识库或多个数据集。用 collection 分目录、分索引查询，可以避免所有图片混在一起。

为什么要有 doc_hash？因为同一篇文档可能提取出多张图片。记录 doc_hash 后，后续删除某个文档时，可以通过 doc_hash 找到它关联的所有图片，一次性清理。

为什么要启用 WAL？SQLite 的 WAL 模式更适合读写并发场景。摄取流程、Dashboard 或管理工具可能同时访问图片索引，WAL 可以减少锁冲突。

这一阶段的核心价值是：让多模态链路不只是“metadata 里有图片引用”，而是真正具备“图片文件可存、可查、可删、可持久化”的能力。


# 整体架构

1. 文件定位
项目中的作用：该文件是项目中的图片资源持久化存储模块，专门负责管理图片文件的物理存储与元数据索引。
所处层级：属于数据接入与存储层（Ingestion -> Storage），位于数据处理流水线的下游，负责将提取出的图片数据落地。
核心职责：将图片数据（无论是内存中的字节流还是本地文件）安全地保存到本地文件系统中，并利用 SQLite 数据库维护图片的元数据索引（如所属集合、关联文档哈希、页码等），从而实现图片的高效检索、追踪与清理。
2. 函数拆解
核心类 ImageStorage 的方法：
init (初始化)
输入：图片存储根目录 (image_root)、数据库文件路径 (db_path)。
作用：自动创建所需的文件夹，并初始化 SQLite 数据库表结构，确保存储环境就绪。
save_image (保存图片)
输入：图片ID、数据源（字节流或文件路径）、集合名、文档哈希、页码等。
输出：保存后的图片绝对路径。
核心功能：校验输入合法性 -> 确定文件后缀 -> 将图片写入磁盘 -> 在数据库中插入或更新索引记录 -> (可选) 记录追踪日志。
get_path (获取路径)
输入：图片ID。
输出：图片在磁盘上的存储路径字符串。
核心功能：通过图片ID在数据库中快速查询其对应的物理文件路径。
list_images (列表查询)
输入：可选的集合名 (collection)、文档哈希 (doc_hash)。
输出：符合条件的图片元数据字典列表。
核心功能：支持按条件过滤，批量查询数据库中的图片索引信息。
delete_images (删除图片)
输入：可选的集合名、文档哈希。
输出：被删除的数据库记录行数。
核心功能：先查出符合条件的记录，删除磁盘上的物理文件，然后再删除数据库中的索引记录，保证数据一致性。
_initialize (内部初始化)：负责在 SQLite 中执行建表 (image_index) 和建索引的 SQL 语句。
_connect (内部连接)：创建并返回一个配置好行工厂（返回字典格式）的 SQLite 数据库连接。
模块级辅助函数：
_write_image (写入图片)：判断数据源类型，如果是字节流则直接写入文件，如果是路径则将源文件复制到目标路径。
_resolve_extension (解析后缀)：智能推断或校验图片的文件后缀（如 .png, .jpg），并拦截包含路径分隔符的非法后缀。
_validate_identifier (校验标识符)：检查 image_id 或 collection 等字符串是否合法，防止包含 / 或 [](file://d:\RAG\MODULAR-RAG-CLEAN-START\DEV_SPEC.md) 导致路径穿越等安全问题。
3. 执行流程
初始化链路： 实例化 ImageStorage $\rightarrow$ 触发 init $\rightarrow$ 创建图片目录和数据库目录 $\rightarrow$ 调用 _initialize $\rightarrow$ 通过 _connect 连接数据库 $\rightarrow$ 执行建表和建索引 SQL。
保存链路： 调用 save_image $\rightarrow$ _validate_identifier 校验 ID 和集合名 $\rightarrow$ _resolve_extension 确定文件后缀 $\rightarrow$ _write_image 将数据写入磁盘 $\rightarrow$ 通过 _connect 连接数据库执行 INSERT ... ON CONFLICT 更新索引 $\rightarrow$ (可选) 记录 trace 日志 $\rightarrow$ 返回文件路径。
查询链路： 调用 list_images 或 get_path $\rightarrow$ _validate_identifier 校验参数 $\rightarrow$ 动态拼接 SQL 条件 $\rightarrow$ 通过 _connect 查询数据库 $\rightarrow$ 返回字典列表或路径字符串。
删除链路： 调用 delete_images $\rightarrow$ 内部调用 list_images 查出待删文件 $\rightarrow$ 遍历删除磁盘物理文件 $\rightarrow$ 拼接 SQL 删除数据库记录 $\rightarrow$ 返回删除的行数。
4. 场景示例
假设我们有一个 “企业规章制度 PDF 解析系统”，需要将 PDF 里的插图提取出来存入库中，全流程如下：

保存阶段：解析器提取出第 5 页的一张流程图（内存中的字节流），调用 save_image(image_id="img_001", source=图片字节, collection="regulations", doc_hash="pdf_hash_888", page_num=5)。系统校验参数后，将图片保存为 data/images/regulations/img_001.png，并在 SQLite 中记录这条关联信息。
查询阶段：前端需要展示该 PDF 的所有图片，调用 list_images(collection="regulations", doc_hash="pdf_hash_888")，系统从数据库查出该文档下的所有图片信息列表返回给前端。
获取阶段：前端拿到列表后，需要渲染某张具体图片，调用 get_path("img_001")，系统返回磁盘路径 data/images/regulations/img_001.png，后端据此读取图片并返回给前端展示。
清理阶段：如果该 PDF 文档被删除或更新，系统调用 delete_images(collection="regulations", doc_hash="pdf_hash_888")，系统会自动把对应的磁盘图片文件删掉，并清空数据库里的索引，保持存储空间的整洁。