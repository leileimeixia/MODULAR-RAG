# C7_image_captioner 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `ImageCaptioner`，用于给包含图片引用的 `Chunk` 生成图片描述。

在多模态 RAG 中，PDF 里可能包含图表、截图、流程图或扫描图片。前面 C4 已经把图片引用按需分发到对应 chunk 的 metadata 里，本阶段要做的就是：当 chunk 里确实有图片时，调用 Vision LLM 生成 caption，并把 caption 写回 chunk metadata。

它在 Ingestion Pipeline 中的位置是 Transform 阶段的一部分，通常位于 `DocumentChunker` 之后、Embedding 之前：

```text
DocumentChunker
  -> ChunkRefiner
  -> MetadataEnricher
  -> ImageCaptioner
  -> DenseEncoder / SparseEncoder
```

如果 Vision LLM 禁用、不可用或调用失败，`ImageCaptioner` 不会阻塞 ingestion，而是保留原始 `image_refs`，并标记图片尚未处理。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/transform/image_captioner.py` | 实现图片 caption 生成与降级处理 |
| `src/ingestion/transform/__init__.py` | 导出 `ImageCaptioner` |
| `tests/unit/test_image_captioner_fallback.py` | 验证 caption 成功、禁用降级、异常降级和 trace 记录 |
| `DEV_SPEC.md` | 将 C7 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
调用方
  -> ImageCaptioner(settings?, vision_llm?, prompt_path?, enabled?)

ImageCaptioner.transform(chunks, trace?)
  -> 遍历每个 Chunk
      -> 检查 chunk.metadata["images"]
      -> 没有图片：原样返回
      -> 有图片但禁用 Vision LLM：
          -> 标记 has_unprocessed_images
      -> 有图片且启用 Vision LLM：
          -> vision_llm.chat_with_image(prompt, image_path)
          -> 成功：写入 image_captions
          -> 失败/空结果：写入 image_caption_errors
  -> trace.record_stage("image_captioning")
  -> 返回新的 List[Chunk]
```

这一层只负责“把图片变成可检索的文本描述”，不负责图片文件的保存。图片存储会在后续 C13 `ImageStorage` 中继续完善。

## 4. 每个核心文件的作用

### 文件：`src/ingestion/transform/image_captioner.py`

* 主要职责：为 chunk 中引用的图片生成 caption，并写入 metadata。
* 关键函数 / 类：
  * `ImageCaptioner`：图片 caption transform 入口。
  * `transform(chunks, trace)`：批量处理 chunks。
  * `_caption_chunk(chunk, trace)`：处理单个 chunk 的图片引用。
  * `_chunk_image_refs(chunk)`：读取 `chunk.metadata["images"]`。
  * `_replace_chunk_metadata(chunk, updates)`：生成新的 Chunk 并更新 metadata。
  * `_resolve_enabled(settings)`：从 settings 或显式参数判断 Vision LLM 是否启用。
* 输入是什么：
  * `list[Chunk]`
  * 可选 Vision LLM
  * 可选 prompt 文件
* 输出是什么：
  * 写入 `image_captions` 或降级标记后的 `list[Chunk]`
* 在项目中的作用：
  * 把图片信息转成文本信息，让后续 embedding 和 retrieval 能利用图像内容。

### 文件：`src/ingestion/transform/__init__.py`

* 主要职责：导出 Transform 层公共入口。
* 关键函数 / 类：
  * `BaseTransform`
  * `ChunkRefiner`
  * `MetadataEnricher`
  * `ImageCaptioner`
  * `TransformError`
* 输入是什么：无直接业务输入。
* 输出是什么：包级导入入口。
* 在项目中的作用：
  * 让 pipeline 后续可以统一从 `ingestion.transform` 导入所有 transform。

### 文件：`tests/unit/test_image_captioner_fallback.py`

* 主要职责：验证图片 caption transform 的核心行为。
* 关键测试：
  * Vision LLM 禁用时，保留 `image_refs` 并标记 `has_unprocessed_images`。
  * Mock Vision LLM 成功时，写入 `image_captions`。
  * 没有图片的 chunk 原样返回。
  * Vision LLM 异常时，不阻塞处理，写入 `image_caption_errors`。
  * caption 为空时，按失败处理。
  * transform 会记录 trace stage。
* 输入是什么：
  * 构造出来的含图片 `Chunk`
  * Mock Vision LLM
* 输出是什么：
  * pytest 断言结果。
* 在项目中的作用：
  * 保证多模态能力即使失败也不会拖垮整个 ingestion。

## 5. 新手重点理解

`ImageCaptioner` 的关键价值是把“图片内容”转成“文本描述”。

向量检索主要处理文本。如果 PDF 里有一张架构图，单纯保留图片路径并不能让文本检索理解图里的内容。caption 就是图片和文本检索之间的桥梁。

为什么要保留 `image_refs`？因为 caption 只是对图片的描述，不能替代原始图片引用。后续系统返回答案时，可能还需要把原图一起展示给用户。

为什么失败时不报错？因为图片 caption 是增强能力，不应该阻塞基础文本摄取。即使 Vision LLM 不可用，文本 chunk 仍然可以继续进入 embedding 和存储流程。

本阶段和 C4 的关系很紧密。C4 负责把图片引用分发到正确的 chunk；C7 负责读取这些图片引用，并把图片内容变成可检索的 caption。


lingma：
以下是对 image_captioner.py 代码文件的完整解析：

# 文件定位
该文件位于 RAG（检索增强生成）系统数据摄入（Ingestion）流水线中的转换（Transform）层。 核心职责：当切分后的文本块（Chunk）中包含图片引用时，调用视觉大模型（Vision LLM）为这些图片生成文字描述（Caption），并将描述补充到文本块的元数据（Metadata）中。这能有效增强多模态文档的语义信息，提升后续检索的准确率。

# 函数拆解
init：初始化转换器。接收系统配置，决定是否启用图片描述功能，按需实例化视觉大模型，并加载提示词（Prompt）。
transform：对外暴露的核心入口。接收一批文本块，遍历处理每个文本块，并记录处理轨迹（Trace）以便监控。
_caption_chunk：处理单个文本块的核心逻辑。提取图片引用，调用大模型生成描述，捕获异常，最后更新文本块的元数据。
_load_prompt：加载用于引导大模型生成图片描述的提示词文本，若指定文件不存在则使用默认兜底提示词。
_chunk_image_refs：辅助函数。从文本块的元数据中安全地提取并校验图片引用列表。
_replace_chunk_metadata：辅助函数。通过合并原有元数据和新更新内容，返回一个全新的 Chunk 实例（符合不可变对象的设计模式）。
_resolve_enabled：辅助函数。兼容对象和字典两种配置格式，解析并返回是否启用视觉大模型的布尔值。

# 执行流程
初始化：系统实例化 ImageCaptioner，读取配置判断是否开启功能，加载视觉大模型和 Prompt。
批量分发：调用 transform 方法传入 Chunk 列表，内部通过列表推导式分发任务。
单块处理（_caption_chunk）：
调用 _chunk_image_refs 检查是否有图片。若无图片，直接返回原 Chunk。
若功能未开启，在元数据中打上“未处理/禁用”标签后返回。
若功能开启，遍历图片路径，调用 vision_llm.chat_with_image 获取描述。
收集成功生成的描述和失败的错误信息。
调用 _replace_chunk_metadata 将描述和状态写入 Chunk 的 metadata。
收尾：记录当前阶段的处理信息（Trace），返回处理完毕的 Chunk 列表。


# 场景示例
假设正在处理一份医疗设备操作手册，其中有一个文本块内容为：“设备正面面板如图1所示，包含电源和急停按钮。”，并且其元数据中记录了图片引用 {"id": "img_01", "path": "images/panel.png"}。

该文本块进入 ImageCaptioner.transform。
_caption_chunk 提取到 img_01，确认功能已开启。
系统调用视觉大模型，传入 Prompt（如“请详细描述图片内容用于检索”）和 panel.png 图片路径。
大模型返回描述：“一个灰色金属面板，左侧是红色圆形急停按钮，右侧是绿色电源开关。”
_replace_chunk_metadata 将这段描述存入该文本块的 image_captions 字段中。
最终效果：这个文本块不仅保留了原文本，还拥有了图片的详细文字描述。后续在进行向量检索时，即使问题只涉及“急停按钮是什么颜色”，也能通过图片描述成功匹配到该文本块，解决了纯文本检索无法理解图片内容的痛点。