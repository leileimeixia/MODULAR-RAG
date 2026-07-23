# H1_ragas_evaluator 学习笔记

## 1. 本阶段完成了什么

本阶段给项目增加了一个基于 Ragas 的评估器：`RagasEvaluator`。

在 RAG 项目里，生成答案之后不能只靠人工感觉判断效果好不好，还需要一些可量化指标。Ragas 就是常见的 RAG 评估框架，可以评估答案是否忠实于上下文、答案是否相关、上下文是否精准等。

不过这个项目没有把 `ragas` 做成强制依赖，而是采用“可选依赖”的方式：项目平时可以正常启动和测试，只有真正运行 `RagasEvaluator.evaluate()` 并且没有注入 mock evaluator 时，才会尝试加载 `ragas`。如果本地没安装，会给出清楚的 `ImportError` 提示。

这一阶段在整个 RAG 流程中的位置是“评估体系”。它不负责摄取文档，也不负责检索和生成答案，而是在这些流程之后，用统一接口衡量一次问答结果的质量。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/evaluation/ragas_evaluator.py` | 实现 `RagasEvaluator`，封装 Ragas 评估流程，并把结果转换成项目统一的 `EvaluationResult` |
| `src/observability/evaluation/__init__.py` | 导出 `RagasEvaluator` 和默认指标 |
| `src/libs/evaluator/evaluator_factory.py` | 在 evaluator 工厂中注册 `ragas` provider |
| `tests/unit/test_ragas_evaluator.py` | 测试 RagasEvaluator 的 mock 评估、缺依赖报错、指标归一化、trace 记录和 factory 创建 |
| `DEV_SPEC.md` | 更新 H1 任务进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步自动开发进度表 |

## 3. 核心调用关系

```text
EvaluatorFactory.create(settings)
  -> 读取 settings.evaluation.provider
  -> provider 为 "ragas" 时创建 RagasEvaluator
  -> RagasEvaluator.evaluate(query, retrieved_ids, golden_ids, generated_answer)
  -> 校验输入
  -> 组装 Ragas payload
  -> 调用注入的 evaluator 或懒加载 ragas.evaluate
  -> 归一化指标
  -> 返回 EvaluationResult
```

这里最重要的数据流是：

```text
query / retrieved_ids / golden_ids / generated_answer
  -> payload: question / contexts / ground_truth / answer
  -> raw ragas result
  -> dict[str, float]
  -> EvaluationResult(metrics, details)
```

## 4. 每个核心文件的作用

### 文件：`src/observability/evaluation/ragas_evaluator.py`

* 主要职责：把外部 Ragas 框架包装成项目内部统一的 `BaseEvaluator` 接口。
* 关键类：`RagasEvaluator`
* 关键函数：
  * `evaluate()`：执行一次评估，并返回 `EvaluationResult`。
  * `_build_ragas_payload()`：把项目内部参数转换成 Ragas 能理解的数据格式。
  * `_load_ragas_runner()`：只有真正需要运行 Ragas 时才导入 `ragas.evaluate`。
  * `_normalize_metrics()`：把 Ragas 或 mock 返回的结果整理成 `dict[str, float]`。
* 输入是什么：问题、检索到的 chunk id、标准答案对应的 golden id、生成答案。
* 输出是什么：统一的 `EvaluationResult`，其中 `metrics` 保存评估分数，`details` 保存辅助信息。
* 在项目中的作用：让项目后续可以接入 Ragas 指标，同时保持当前测试环境轻量。

### 文件：`src/libs/evaluator/evaluator_factory.py`

* 主要职责：根据配置创建不同 evaluator。
* 本阶段变化：新增 `"ragas"` provider。
* 关键点：`ragas` 使用 `_create_ragas_evaluator()` 延迟导入，避免 factory 模块导入时就要求安装 Ragas。
* 在项目中的作用：让配置层可以通过 `evaluation.provider: ragas` 切换到 RagasEvaluator。

### 文件：`tests/unit/test_ragas_evaluator.py`

* 主要职责：证明 H1 的行为是稳定的。
* 测试重点：
  * mock evaluator 能返回 `faithfulness`、`answer_relevancy`、`context_precision`。
  * factory 可以创建 `RagasEvaluator`。
  * 没安装 Ragas 时有清楚报错。
  * list 类型指标可以被平均成 float。
  * 传入 trace 时会记录 `ragas_evaluation` 阶段。

## 5. 新手重点理解

这个阶段的关键不是“马上真的跑 Ragas”，而是先把评估能力接入到项目架构里。

为什么要可选依赖？因为 Ragas 通常还会牵涉模型、数据集对象、额外依赖。如果把它写成启动时强制导入，没安装的人连普通功能和单测都跑不起来。现在的写法更灵活：不用评估时不受影响，需要评估时再安装。

为什么要注入 `evaluator`？这是为了测试。真实 Ragas 可能需要网络、模型 key 或复杂依赖，而单元测试应该快速、稳定、可重复。所以测试里传入 fake runner，只验证本项目自己的封装逻辑。

为什么要统一返回 `EvaluationResult`？因为后面 H2、H3、H4 还会继续做组合评估器、评估运行器和评估面板。如果每个评估器返回格式都不一样，后面的模块就会很难写。现在所有 evaluator 都遵守同一个接口，后续扩展会轻很多。

这一阶段可以理解成给项目装上“评估插座”：现在已经有了标准接口和 Ragas 插头，后面就可以把 golden test set、Dashboard 评估面板接进来。




# 整体结构与流程

文件解析：ragas_evaluator.py
一、文件定位
项目层级：该文件位于 src/observability/evaluation/ 目录下，属于项目中的可观测性/评估模块。
核心职责：实现一个基于 Ragas 框架的 RAG（检索增强生成）系统评估器，用于对 RAG 系统生成的答案进行自动化质量评分。
设计特点：
继承自 BaseEvaluator，遵循统一的评估器接口规范。
Ragas 依赖是可选的（Optional），如果环境中未安装 ragas 包，可以通过注入自定义的 evaluator 函数来替代，避免强依赖。
支持 Trace 记录，方便在评估过程中留下可观测性日志。
二、函数拆解
1. RagasEvaluator.__init__
作用：初始化评估器实例。
输入：
settings：评估配置（可选）。
evaluator：自定义的评估运行函数（可选，用于替代默认的 Ragas 调用）。
metrics：要评估的指标列表，默认使用 faithfulness、answer_relevancy、context_precision。
输出：无，完成实例属性赋值。
2. RagasEvaluator.evaluate
作用：核心评估方法，对一个「问题-答案」样本进行 Ragas 指标评估。
输入：
query：用户提问。
retrieved_ids：检索到的上下文 ID 列表。
golden_ids：标准答案（Ground Truth）的 ID 列表。
generated_answer：RAG 系统生成的答案。
trace：可选的 Trace 对象，用于记录评估过程。
输出：EvaluationResult 对象，包含归一化后的指标分数和详情。
核心逻辑：校验输入 → 构建 Ragas 请求 → 调用评估器 → 归一化结果 → 记录 Trace → 返回结果。
3. _validate_inputs
作用：校验 evaluate 方法的输入参数是否合法。
输入：query、retrieved_ids、golden_ids、generated_answer。
输出：无，校验失败时抛出 ValueError。
核心功能：确保 query 是非空字符串，retrieved_ids 和 golden_ids 是字符串列表，generated_answer 是字符串。
4. _build_ragas_payload
作用：将输入参数组装成 Ragas 评估所需的字典格式。
输入：同 evaluate 的核心参数。
输出：一个字典，包含 question、answer、contexts、ground_truth、retrieved_ids、golden_ids。
5. _load_ragas_runner
作用：懒加载 Ragas 的 evaluate 函数，并封装为统一的 _runner 调用接口。
输入：无。
输出：一个可调用函数 _runner(payload, metrics)。
核心功能：如果环境中未安装 ragas，则抛出 ImportError 并给出安装提示。
6. _normalize_metrics
作用：将 Ragas 返回的原始结果（可能是 dict、对象、DataFrame 等多种格式）统一归一化为 {指标名: 浮点分数} 的字典。
输入：Ragas 的原始返回结果。
输出：dict[str, float]，如 {"faithfulness": 0.85, "answer_relevancy": 0.92}。
7. _numeric_metrics
作用：从一个字典中提取所有可以转为浮点数的指标值。
输入：一个原始值字典。
输出：过滤后的浮点数字典。
8. _to_float
作用：将任意类型的值尝试转为浮点数。
输入：任意值（可能是 int、float、list、tuple 等）。
输出：浮点数或 None。
特殊处理：布尔值返回 None；列表/元组则递归转换后取平均值。
三、执行流程
用户调用 evaluate()
        │
        ▼
 _validate_inputs()  ──校验输入合法性──▶  失败则抛 ValueError
        │
        ▼ (校验通过)
 _build_ragas_payload()  ──组装 Ragas 请求字典
        │
        ▼
 判断 self._evaluator 是否存在
   ├── 存在 → 直接使用自定义 evaluator
   └── 不存在 → 调用 _load_ragas_runner() 懒加载 Ragas
        │
        ▼
 runner(payload, metrics)  ──执行 Ragas 评估，返回原始结果
        │
        ▼
 _normalize_metrics()
   ├── 如果是 dict → _numeric_metrics()
   ├── 如果有 .scores 属性 → _numeric_metrics(.scores)
   ├── 如果有 .to_pandas() 方法 → 转 DataFrame → _numeric_metrics()
   └── 否则 → 返回空字典
        │
        ▼
 _to_float()  ──递归处理各类值，转为浮点数
        │
        ▼
 组装 details 字典 + 记录 Trace（如有）
        │
        ▼
 返回 EvaluationResult(metrics=..., details=...)
四、场景示例
业务场景：你搭建了一个企业知识库问答系统（RAG），用户问了一句"公司的年假政策是什么？"，系统从知识库中检索到了 3 段相关文档，并生成了一段回答。你想知道这个回答质量如何。

全流程串联：

准备数据：

query = "公司的年假政策是什么？"
retrieved_ids = ["doc_001", "doc_002", "doc_003"]（检索到的 3 段文档 ID）
golden_ids = ["年假按入职年限计算，工作满1年享5天..."]（标准答案）
generated_answer = "根据公司制度，入职满一年可享受5天年假..."（RAG 生成的回答）
调用评估：evaluator.evaluate(query, retrieved_ids, golden_ids, generated_answer)

校验输入：_validate_inputs 检查所有参数格式正确 ✅

构建请求：_build_ragas_payload 将数据打包成 Ragas 能理解的字典格式。

加载评估器：由于没有注入自定义 evaluator，调用 _load_ragas_runner() 加载 Ragas 库。

执行评估：Ragas 计算三个指标：

faithfulness（忠实度）：回答是否忠于检索到的上下文 → 0.90
answer_relevancy（答案相关性）：回答是否切题 → 0.85
context_precision（上下文精确度）：检索的文档是否精准 → 0.78
归一化结果：_normalize_metrics 将 Ragas 的原始返回（可能是 DataFrame）统一转为 {"faithfulness": 0.90, "answer_relevancy": 0.85, "context_precision": 0.78}。

记录 Trace：如果有 trace 对象，将本次评估的详细数据记录下来，方便后续排查和分析。

返回结果：最终返回 EvaluationResult，你可以直接查看各指标分数，判断 RAG 系统的表现是否需要优化。

一句话总结：这个文件就是一个「RAG 答案质量打分器」——你给它一个问题、检索到的文档、标准答案和系统生成的回答，它就能调用 Ragas 帮你自动算出忠实度、相关性、精确度等指标分数，告诉你 RAG 系统回答得好不好。