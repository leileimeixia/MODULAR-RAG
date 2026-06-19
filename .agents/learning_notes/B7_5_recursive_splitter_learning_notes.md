# B7.5_recursive_splitter 学习笔记

## 1. 本阶段完成了什么

本阶段给项目新增了默认的 Recursive Splitter，也就是递归文本切分器。它的作用是把一大段文档文本切成多个较小的 chunk，方便后续做 embedding、写入向量库、检索召回。

RAG 系统里不能直接把整篇 PDF 或整篇 Markdown 一次性送去 embedding，因为文本太长、成本高、检索也不精确。所以需要先切成合适大小的片段。`RecursiveSplitter` 就负责这个工作。

本阶段没有引入 LangChain 依赖，而是实现了一个本地轻量版递归切分器：先尝试按 Markdown 标题、段落、换行、句子、空格这些较自然的边界切分，如果还太长，再退回到固定窗口切分。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/splitter/recursive_splitter.py` | 实现默认 RecursiveSplitter |
| `src/libs/splitter/splitter_factory.py` | 注册 `recursive` provider |
| `src/libs/splitter/__init__.py` | 对外导出 `RecursiveSplitter` 和异常类型 |
| `tests/unit/test_recursive_splitter_lib.py` | 测试递归切分器行为 |
| `DEV_SPEC.md` | 标记 B7.5 完成，更新阶段进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 阶段进度 |

## 3. 核心调用关系

```text
业务代码 / 测试代码
  -> SplitterFactory.create(settings)
  -> settings.splitter.provider == "recursive"
  -> 创建 RecursiveSplitter
  -> RecursiveSplitter.split_text(text)
  -> 按 Markdown/段落/句子/空格递归切分
  -> 必要时按固定窗口兜底
  -> 返回 list[str] chunks
```

数据流可以理解为：

```text
原始长文本
  -> 去掉首尾空白
  -> 保护代码块
  -> 按较大的自然边界切分
  -> 对仍然过长的片段继续用更小边界切分
  -> 合并短片段并加入 overlap
  -> 输出 chunk 列表
```

## 4. 每个核心文件的作用

### 文件：`src/libs/splitter/recursive_splitter.py`

* 主要职责：实现默认文本切分策略。
* 关键类：
  * `RecursiveSplitter`：真正执行递归切分。
  * `RecursiveSplitterError`：表示配置或输入不合法。
* 关键函数：
  * `split_text()`：对外入口，输入文本，输出 chunk 列表。
  * `_split_recursive()`：按分隔符递归切分。
  * `_split_code_fences()`：识别 Markdown 代码块，尽量避免小代码块被拆开。
  * `_merge_chunks()`：把小片段合并成不超过 `chunk_size` 的 chunk。
  * `_window_text()`：当自然边界无法满足时，用固定窗口兜底切分。
* 输入是什么：`text: str`。
* 输出是什么：`list[str]`，每个元素是一个 chunk。
* 在项目中的作用：为文档摄取流程提供默认 chunk 切分能力。

### 文件：`src/libs/splitter/splitter_factory.py`

* 主要职责：根据 provider 名称创建具体 splitter。
* 本阶段新增逻辑：`SplitterFactory.register("recursive", RecursiveSplitter)`。
* 输入是什么：完整 `Settings` 或单独的 `SplitterSettings`。
* 输出是什么：`RecursiveSplitter` 实例。
* 在项目中的作用：让配置里的 `splitter.provider: recursive` 生效。

### 文件：`src/libs/splitter/__init__.py`

* 主要职责：统一导出 splitter 模块的公共类。
* 本阶段新增导出：
  * `RecursiveSplitter`
  * `RecursiveSplitterError`
* 在项目中的作用：让其它模块可以通过 `from libs.splitter import RecursiveSplitter` 使用默认切分器。

### 文件：`tests/unit/test_recursive_splitter_lib.py`

* 主要职责：验证 RecursiveSplitter 的关键行为。
* 覆盖点：
  * `SplitterFactory` 能创建 `RecursiveSplitter`。
  * 空文本返回空列表。
  * 长文本会被切成多个 chunk。
  * chunk 长度不超过配置。
  * chunk 之间支持 overlap。
  * Markdown 标题可以作为切分边界。
  * 小代码块尽量保持完整。
  * 非法配置和非字符串输入会报错。

## 5. 新手重点理解

文本切分是 RAG 中非常关键的一步。切得太大，检索不精确，也可能超过模型或 embedding 接口限制；切得太小，语义上下文容易丢失。所以 splitter 需要在“大小合适”和“语义完整”之间做平衡。

为什么叫 recursive？因为它不是只用一种方式切分，而是按优先级逐层尝试。比如先按标题切，如果某一段还是太长，就按段落切；段落还是太长，就按换行或空格切；最后才用固定窗口兜底。

为什么要有 `chunk_overlap`？因为两个相邻 chunk 如果完全断开，边界处的信息可能丢失。overlap 会把前一个 chunk 的末尾带到下一个 chunk 里，让检索时上下文更连续。

为什么要保护代码块？Markdown 文档里经常有代码示例。如果把代码块中间硬拆开，后续 embedding 或问答时可能失去完整含义。所以这里会先识别小代码块，尽量把它作为一个整体处理。

本阶段在 RAG 流程中的位置是“文档切块”。它位于 Loader 之后、Embedding 之前，是后续向量化和检索质量的基础。
