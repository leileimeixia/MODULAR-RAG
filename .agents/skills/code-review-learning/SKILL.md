---
name: code-review-learning
description: 在完成某个开发阶段后，为该阶段生成面向新手的代码学习笔记，并按 DEV_SPEC.md 的大阶段写入 .agents/learning_notes 子目录。
---

# code-review-learning Skill

## 使用场景

当完成某个阶段代码编写、功能开发、模块修改、Bug 修复或项目结构调整后，使用本 skill 生成一份系统化代码学习笔记，帮助用户理解本阶段代码内容。

## 核心要求

不要在对话窗口直接输出完整学习讲解内容。必须将学习笔记写入单独目录：

```text
.agents/learning_notes/<阶段目录>/
```

学习笔记文件命名格式必须为：

```text
<阶段编号>_<模块名称>_learning_notes.md
```

示例：

```text
B7_8_cross_encoder_reranker_learning_notes.md
C1_core_types_learning_notes.md
```

## 阶段目录映射

必须根据任务编号首字母选择对应目录：

| 任务编号前缀 | DEV_SPEC 大阶段 | 写入目录 |
| --- | --- | --- |
| A | 阶段 A：工程骨架与测试基座 | `.agents/learning_notes/stage_A_project_skeleton_testing/` |
| B | 阶段 B：Libs 可插拔层 | `.agents/learning_notes/stage_B_libs_pluggable_layer/` |
| C | 阶段 C：Ingestion Pipeline | `.agents/learning_notes/stage_C_ingestion_pipeline/` |
| D | 阶段 D：Retrieval | `.agents/learning_notes/stage_D_retrieval/` |
| E | 阶段 E：MCP Server 层与 Tools | `.agents/learning_notes/stage_E_mcp_server_tools/` |
| F | 阶段 F：Trace 基础设施与打点 | `.agents/learning_notes/stage_F_trace_observability/` |
| G | 阶段 G：可视化管理平台 Dashboard | `.agents/learning_notes/stage_G_dashboard/` |
| H | 阶段 H：评估体系 | `.agents/learning_notes/stage_H_evaluation/` |
| I | 阶段 I：端到端验收与文档收口 | `.agents/learning_notes/stage_I_e2e_docs/` |

如果目标阶段目录不存在，必须先创建。

## 执行流程

1. 识别本阶段任务编号和模块名称，例如 `B9 Azure Vision LLM 实现`。
2. 根据任务编号首字母选择阶段目录。
3. 如果目录不存在，创建对应目录。
4. 生成学习笔记 Markdown 文件。
5. 对话窗口只简短说明笔记已生成，并给出文件路径，不要输出完整笔记正文。

## 学习笔记内容结构

每份学习笔记应包含以下内容：

```markdown
# <阶段编号>_<模块名称> 学习笔记

## 1. 本阶段完成了什么

用新手能理解的语言说明本阶段实现了哪些功能，解决了什么问题，在整个项目中处于什么位置。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| xxx.py | 说明该文件负责什么 |

## 3. 核心调用关系

用简单箭头说明本阶段文件之间如何调用，例如：

```text
入口文件
  -> 加载配置
  -> 调用核心模块
  -> 返回处理结果
```

必要时说明每一步的数据流向。

## 4. 每个核心文件的作用

### 文件：xxx.py

* 主要职责：
* 关键函数 / 类：
* 输入是什么：
* 输出是什么：
* 在项目中的作用：

## 5. 新手重点理解

用通俗语言解释本阶段最重要的概念，例如：

* 为什么要这样拆分文件
* 为什么这个模块要单独封装
* 数据如何从一个文件流向另一个文件
* 这个模块在 RAG 流程中的位置
```

## 写作风格要求

- 面向新手，语言必须通俗易懂。
- 不要只堆技术名词，要解释“为什么这么做”。
- 不要写得过长，重点清楚即可。
- 每个文件的作用要讲清楚。
- 必须说明核心调用关系。
- 必须结合当前项目实际生成的代码内容，不要写泛泛而谈的模板。
- 如果本阶段是 RAG 项目的一部分，需要明确它属于 RAG 流程中的哪个环节。

## 输出规则

对话窗口中只允许简短输出，例如：

```text
已生成本阶段学习笔记：
.agents/learning_notes/stage_B_libs_pluggable_layer/B9_azure_vision_llm_learning_notes.md
```

不要在对话窗口中输出完整学习笔记内容。
