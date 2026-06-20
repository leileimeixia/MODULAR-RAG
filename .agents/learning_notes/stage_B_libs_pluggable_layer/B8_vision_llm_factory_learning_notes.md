# B8_vision_llm_factory 学习笔记

## 1. 本阶段完成了什么

本阶段给项目新增了 Vision LLM 的抽象接口，并扩展了 `LLMFactory`，让它不仅能创建普通文本 LLM，也能创建支持图片输入的 Vision LLM。

Vision LLM 的作用是处理“文本 + 图片”的多模态输入。后续在文档摄取流程中，如果 PDF 或 Markdown 里有图片，系统可以调用 Vision LLM 给图片生成文字描述，然后把描述写回 chunk，最终仍然走普通文本 RAG 检索链路。

本阶段只做抽象和工厂路由，不实现真实 Azure Vision HTTP 调用。真实 Azure Vision provider 会在 B9 完成。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/llm/base_vision_llm.py` | 定义 Vision LLM 抽象接口和响应结构 |
| `src/libs/llm/llm_factory.py` | 扩展 Vision LLM 注册、注销和创建逻辑 |
| `src/libs/llm/__init__.py` | 对外导出 Vision LLM 抽象类型 |
| `tests/unit/test_vision_llm_factory.py` | 使用 Fake Vision LLM 测试工厂路由 |
| `DEV_SPEC.md` | 标记 B8 完成，更新阶段进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 阶段进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> LLMFactory.register_vision(provider, creator)
  -> LLMFactory.create_vision_llm(settings)
  -> 读取 settings.vision_llm
  -> 根据 vision_llm.provider 找到对应 creator
  -> 创建 BaseVisionLLM 子类实例
  -> chat_with_image(text, image_path)
```

数据流可以理解为：

```text
VisionLLMSettings
  -> 检查 enabled 是否为 true
  -> 规范化 provider 名称
  -> 从 _vision_registry 找 provider
  -> 创建 Vision LLM 实例
  -> 外部调用 chat_with_image
```

## 4. 每个核心文件的作用

### 文件：`src/libs/llm/base_vision_llm.py`

* 主要职责：定义 Vision LLM 的统一接口。
* 关键类型：
  * `ImageInput`：表示图片输入，可以是路径字符串、`Path` 或 bytes。
  * `VisionLLMResponse`：标准化响应结构，包含 `text` 和可选 `raw`。
  * `BaseVisionLLM`：抽象基类，要求实现 `chat_with_image()`。
* 输入是什么：文本提示词和图片输入。
* 输出是什么：Vision LLM 返回的文字结果。
* 在项目中的作用：给后续图片描述生成模块提供统一底层接口。

### 文件：`src/libs/llm/llm_factory.py`

* 主要职责：扩展 LLM 工厂，让它支持 Vision LLM。
* 本阶段新增能力：
  * `_vision_registry`：保存 Vision provider 注册表。
  * `register_vision()`：注册 Vision provider。
  * `unregister_vision()`：注销 Vision provider。
  * `create_vision_llm()`：根据 `VisionLLMSettings` 创建 Vision LLM。
* 输入是什么：完整 `Settings` 或单独的 `VisionLLMSettings`。
* 输出是什么：`BaseVisionLLM` 子类实例。
* 在项目中的作用：让 `vision_llm.provider` 配置可以路由到具体 Vision 后端。

### 文件：`src/libs/llm/__init__.py`

* 主要职责：统一导出 LLM 模块公共类型。
* 本阶段新增导出：
  * `BaseVisionLLM`
  * `ImageInput`
  * `VisionLLMResponse`
* 在项目中的作用：让其它模块可以通过 `from libs.llm import BaseVisionLLM` 使用。

### 文件：`tests/unit/test_vision_llm_factory.py`

* 主要职责：验证 Vision LLM 工厂逻辑。
* 覆盖点：
  * 可以从完整 `Settings` 创建 Vision LLM。
  * 可以从单独 `VisionLLMSettings` 创建 Vision LLM。
  * provider 名称会被规范化。
  * Vision LLM 禁用时会报错。
  * 未知 provider 会报错。
  * `BaseVisionLLM` 不能直接实例化。
  * `VisionLLMResponse` 结构符合预期。

## 5. 新手重点理解

普通 LLM 只处理文本输入，例如“请总结这段话”。Vision LLM 可以同时处理文本和图片，例如“请描述这张图里的流程”。这对多模态 RAG 很重要，因为很多 PDF 里的关键信息藏在图片、图表或截图里。

为什么要单独定义 `BaseVisionLLM`？因为图片输入和普通聊天输入不一样。普通 LLM 的接口是 `chat(messages)`，而 Vision LLM 需要 `chat_with_image(text, image_path)`。单独抽象可以让代码更清楚，也方便后续扩展图片压缩、base64、mime type 等处理。

为什么 Vision LLM 也放在 `LLMFactory` 里？因为它本质上仍然是模型能力，只是输入多了图片。把文本 LLM 和 Vision LLM 都放在同一个工厂里，可以统一管理 provider 路由。

为什么本阶段不实现 Azure Vision？因为 B8 只负责“接口和工厂”。先把抽象定稳，B9 再实现具体 Azure 调用。这样每个阶段职责更清楚，测试也更聚焦。

本阶段在 RAG 流程中的位置是“图片理解能力层”。它会在后续 C7 `ImageCaptioner` 中被调用，把图片变成文本描述，再进入普通文本 RAG 链路。
