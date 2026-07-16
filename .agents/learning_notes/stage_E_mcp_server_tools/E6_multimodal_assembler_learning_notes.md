# E6_multimodal_assembler 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 MCP 响应的多模态组装能力，也就是让查询结果不仅能返回文本，还能在命中的 chunk 带有图片引用时，把本地图片读取出来，编码成 Base64，并作为 MCP `ImageContent` 放进返回结果的 `content` 数组里。

这一步解决的问题是：RAG 系统检索到的内容有时不只是文字，还可能关联图表、截图、PDF 中的图片等。如果只返回文本，用户会丢失一部分上下文。E6 通过 `MultimodalAssembler` 把这些图片一起返回，让 MCP 客户端有机会展示图像内容。

在整个项目中，它属于“响应组装层”。前面的检索模块负责找到相关 chunk，`ResponseBuilder` 负责把结果组装成 MCP tool result，而 E6 则在这个结果里追加图片内容。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/core/response/multimodal_assembler.py` | 新增多模态组装器，负责从检索结果 metadata 中读取图片路径并生成 MCP ImageContent |
| `src/core/response/response_builder.py` | 在原有文本响应和引用信息基础上，调用 `MultimodalAssembler` 追加图片内容 |
| `src/core/response/__init__.py` | 导出 `MultimodalAssembler` 和 `ContentBlock` |
| `tests/unit/test_multimodal_assembler.py` | 测试图片内容追加、缺失图片跳过、`ResponseBuilder` 集成多模态内容 |
| `tests/integration/test_mcp_server.py` | 增加协议层测试，确认 MCP tool result 可以返回 image content |
| `DEV_SPEC.md` | 更新 E6 任务状态和总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 的任务进度记录 |

## 3. 核心调用关系

```text
query_knowledge_hub tool
  -> HybridSearch 检索 chunk
  -> CoreReranker 重排 chunk
  -> ResponseBuilder.build(results, query)
  -> CitationGenerator 生成引用信息
  -> MultimodalAssembler 检查 result.metadata.images
  -> 读取图片文件
  -> Base64 编码
  -> 返回 TextContent + ImageContent
```

最终 MCP tool result 的 `content` 大致是这样的顺序：

```text
content[0] = 文本答案 / Markdown 引用
content[1...] = 图片内容 ImageContent
```

这样设计是为了保证兼容性。即使某些 MCP 客户端暂时不展示图片，也至少能显示第一项文本内容。

## 4. 每个核心文件的作用

### 文件：`src/core/response/multimodal_assembler.py`

* 主要职责：把检索结果中的图片元数据转换成 MCP `ImageContent`。
* 关键类 / 函数：
  * `MultimodalAssembler`：多模态内容组装器。
  * `assemble()`：接收已有文本 content 和 retrieval results，返回追加图片后的 content 列表。
  * `_result_images()`：从 `result.metadata["images"]` 中筛选当前 chunk 真正引用的图片。
  * `_image_content()`：读取图片文件，生成 `{"type": "image", "mimeType": "...", "data": "..."}`。
  * `_mime_type()`：根据文件名推断 MIME 类型，例如 `.png` 推断为 `image/png`。
* 输入是什么：文本 content 列表和 `RetrievalResult` 列表。
* 输出是什么：包含文本和图片的 MCP content 列表。
* 在项目中的作用：把 RAG 查询结果从纯文本响应升级为 Text + Image 的多模态响应。

### 文件：`src/core/response/response_builder.py`

* 主要职责：构造 MCP tool result。
* 本阶段修改点：新增 `multimodal_assembler` 依赖，在生成 Markdown 文本后调用 `assemble()`。
* 输入是什么：检索结果列表和用户 query。
* 输出是什么：MCP tool result，包含 `content`、`structuredContent`、`isError`。
* 在项目中的作用：它是 query tool 的统一响应出口，因此多模态内容放在这里接入最自然。

### 文件：`src/core/response/__init__.py`

* 主要职责：统一导出 response 包里的公共类型和类。
* 本阶段修改点：导出 `ContentBlock` 和 `MultimodalAssembler`。
* 在项目中的作用：让其他模块可以通过 `from core.response import MultimodalAssembler` 使用该能力。

### 文件：`tests/unit/test_multimodal_assembler.py`

* 主要职责：验证多模态组装逻辑。
* 关键测试：
  * 图片文件存在时，会追加 `type=image` 的 content block。
  * MIME 类型能根据 `.png` 推断为 `image/png`。
  * 图片数据会被 Base64 编码。
  * 图片文件不存在时不会报错，而是跳过。
  * `ResponseBuilder` 能把图片 content 一起返回。
* 在项目中的作用：保证多模态响应的核心行为稳定。

### 文件：`tests/integration/test_mcp_server.py`

* 主要职责：验证 MCP 协议层能正确透传 image content。
* 本阶段修改点：新增一个 fake tool，返回 text + image content，确认 `ProtocolHandler` 不会把图片内容改坏。
* 在项目中的作用：证明协议层可以承载多模态响应。

## 5. 新手重点理解

MCP tool 的返回结果里，`content` 不是只能放一段文字，而是一个数组。数组里可以有文本，也可以有图片。E6 就是利用这个能力，把 RAG 检索结果中关联的图片一起返回。

这里最重要的约定是图片来自 metadata：

```text
result.metadata["images"]
result.metadata["image_refs"]
```

`images` 里保存图片路径、图片 id 等信息；`image_refs` 表示当前 chunk 实际引用了哪些图片。为什么要看 `image_refs`？因为一个原始文档可能有很多图片，但某个 chunk 只和其中一两张有关。只返回当前 chunk 相关图片，可以避免把无关图片也塞给客户端。

另一个重点是容错。`MultimodalAssembler` 遇到不存在的图片文件会跳过，而不是让整个查询失败。这样做更适合 RAG 系统：图片是增强信息，文本答案和引用仍然应该尽量返回。

本阶段在 RAG 流程中的位置是“最终响应组装”。它不负责加载文档、不负责切块、不负责检索，也不负责生成答案；它只负责在最终 MCP 返回结果里，把文本和图片整理成客户端能理解的格式。


# 整体结构与流程

1. 文件定位
文件路径：src/core/response/multimodal_assembler.py 项目作用：该文件属于 RAG（检索增强生成）系统核心响应处理模块，专门负责多模态内容的组装。 所处层级：处于系统的“响应组装层”（Response Layer），在检索引擎返回结果后、最终输出给大模型或前端之前进行数据处理。 核心职责：将纯文本的响应内容与检索结果中附带的图片元数据相结合，读取本地图片文件并进行 Base64 编码，最终拼装成符合 MCP（Model Context Protocol）等多模态协议标准的内容块（ContentBlock）列表。

2. 函数拆解
① MultimodalAssembler.assemble (类方法)
作用目的：作为核心入口，负责将“文本内容”和“图片内容”合并成一个完整的多模态响应列表，并处理图片去重。
输入：
text_content：初始的文本内容块列表（如大模型生成的文本或检索到的纯文本）。
retrieval_results：检索引擎返回的结果对象列表（包含文档内容及元数据）。
输出：list[ContentBlock]，包含文本和去重后图片的完整内容块列表。
核心功能：
拷贝初始文本内容。
维护一个 seen_paths 集合用于图片路径去重。
遍历检索结果，提取图片路径，校验文件是否存在。
对合法的图片调用转换函数，追加到结果列表中。
② _result_images (内部辅助函数)
作用目的：从单个检索结果的元数据中，过滤并提取出合法、有效的图片信息。
输入：result（单个 RetrievalResult 检索结果对象）。
输出：list[dict]，过滤后的图片元数据字典列表。
核心功能：
从 metadata 中获取 images 列表，处理空值或非列表类型的异常情况。
检查是否存在 image_refs（允许的图片 ID 白名单）。
遍历图片字典，只保留 ID 在白名单内（或没有白名单限制）的有效图片。
③ _image_content (内部辅助函数)
作用目的：将磁盘上的图片文件转换为多模态协议所需的 Base64 数据块格式。
输入：path（图片文件的 Path 路径对象）。
输出：ContentBlock（包含 type、mimeType、data 的字典）。
核心功能：读取图片的二进制字节流，进行 Base64 编码转为 ASCII 字符串，并获取对应的 MIME 类型，组装成标准字典。
④ _mime_type (内部辅助函数)
作用目的：根据文件扩展名推断图片的 MIME 类型（如 image/png）。
输入：path（文件路径对象）。
输出：str（MIME 类型字符串）。
核心功能：调用 Python 标准库 mimetypes.guess_type，如果无法识别则兜底返回 application/octet-stream。
3. 执行流程
整个多模态组装的调用链路如下：

启动组装：外部调用 MultimodalAssembler.assemble()，传入文本块和检索结果。
提取图片元数据：assemble 遍历每个检索结果，调用 _result_images() 获取经过白名单过滤的有效图片字典列表。
路径校验与去重：assemble 检查图片路径是否为真实存在的文件，并通过 seen_paths 集合剔除重复的图片。
转换图片格式：对于每一张去重后的有效图片，assemble 调用 _image_content()。
获取 MIME 类型：_image_content() 内部调用 _mime_type() 获取图片的媒体类型。
编码与封装：_image_content() 读取图片文件内容，Base64 编码后，与类型信息一起封装成字典，返回给 assemble。
合并输出：assemble 将生成的图片字典追加到文本内容列表末尾，最终返回完整的多模态内容列表。
4. 场景示例
业务场景： 用户在一个企业知识库中提问：“请展示一下我们新产品的实物图和设计草图。” RAG 系统检索到了包含这两张图的文档，文档的元数据中记录了图片信息。

全流程串联：

输入准备：

text_content = [{"type": "text", "text": "这是为您找到的新产品资料："}]
retrieval_results 包含一个结果，其 metadata 中有： images = [{"id": "img1", "path": "/data/product_photo.png"}, {"id": "img2", "path": "/data/design_sketch.jpg"}] image_refs = ["img1", "img2"]
执行 assemble：

首先复制文本内容到 content 列表。
遍历检索结果，调用 _result_images。因为 img1 和 img2 都在 image_refs 白名单中，两个图片字典都被保留。
处理第一张图 (product_photo.png)：

检查路径 /data/product_photo.png 存在，且不在 seen_paths 中。
调用 _image_content -> 调用 _mime_type 得到 image/png。
读取图片文件，Base64 编码，生成图片块 1。
将路径加入 seen_paths，图片块 1 加入 content。
处理第二张图 (design_sketch.jpg)：

同理，生成 image/jpeg 类型的图片块 2，加入 content。
处理重复情况（假设检索结果中又出现了一次 product_photo.png）：

再次走到路径校验时，发现 /data/product_photo.png 已经在 seen_paths 中，直接 continue 跳过，避免重复传输浪费 Token。
最终输出： 返回包含 1 个文本块和 2 个图片块的列表，前端或大模型接收到后，即可完美渲染出“图文并茂”的回答。