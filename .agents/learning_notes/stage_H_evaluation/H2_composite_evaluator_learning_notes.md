# H2_composite_evaluator 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `CompositeEvaluator`，也就是“组合评估器”。

前一个阶段 H1 已经接入了 `RagasEvaluator`，可以用 Ragas 指标评估答案质量。项目里原本也有 `CustomEvaluator`，可以计算命中率、MRR、precision 这类检索指标。H2 要解决的问题是：一次评估不一定只跑一种评估器，而是可以同时跑多个评估器，然后把结果合并成一份统一报告。

所以 `CompositeEvaluator` 的作用很像一个评估调度器：它接收多个 evaluator，把同一份 query、retrieved ids、golden ids、generated answer 分发给它们，并行执行，最后合并所有指标。

这一阶段在 RAG 流程中的位置仍然是“评估体系”。它不参与文档入库、检索、重排或生成，而是在 RAG 得到结果之后，统一衡量这次结果的质量。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/evaluation/composite_evaluator.py` | 新增 `CompositeEvaluator`，负责并行运行多个 evaluator 并合并结果 |
| `src/observability/evaluation/__init__.py` | 导出 `CompositeEvaluator` 和 `CompositeEvaluatorError` |
| `src/libs/evaluator/evaluator_factory.py` | 支持 `evaluation.backends` 配置，自动组装多个 evaluator |
| `src/core/settings.py` | 给 `EvaluationSettings` 增加 `backends` 字段 |
| `tests/unit/test_composite_evaluator.py` | 测试组合评估、重复指标命名、失败降级、factory 创建和 trace 记录 |
| `tests/unit/test_config_loading.py` | 测试配置文件能正确读取 `evaluation.backends` |
| `DEV_SPEC.md` | 更新 H2 任务进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步自动开发进度表 |

## 3. 核心调用关系

```text
EvaluatorFactory.create(settings)
  -> 读取 settings.evaluation
  -> 如果配置了 evaluation.backends
  -> 为每个 backend 创建对应 evaluator
  -> 组装 CompositeEvaluator

CompositeEvaluator.evaluate(...)
  -> 把同一份输入分发给多个 evaluator
  -> 使用 ThreadPoolExecutor 并行执行
  -> 收集每个 evaluator 的 EvaluationResult
  -> 合并 metrics
  -> 汇总 details 和 errors
  -> 返回统一 EvaluationResult
```

一次评估的数据流可以理解成：

```text
query + retrieved_ids + golden_ids + generated_answer
  -> CustomEvaluator
  -> RagasEvaluator
  -> 其他 evaluator
  -> CompositeEvaluator 合并指标
  -> EvaluationResult(metrics, details)
```

## 4. 每个核心文件的作用

### 文件：`src/observability/evaluation/composite_evaluator.py`

* 主要职责：同时运行多个 evaluator，并把结果合并。
* 关键类：
  * `CompositeEvaluator`
  * `CompositeEvaluatorError`
* 关键函数：
  * `evaluate()`：并行调用所有 evaluator，合并返回结果。
  * `_evaluator_label()`：给每个 evaluator 生成标签，例如 `1:CustomEvaluator`。
  * `_merge_metrics()`：合并指标，如果遇到同名指标，就加上 evaluator 类名前缀避免覆盖。
* 输入是什么：和普通 evaluator 一样，接收 query、retrieved ids、golden ids、generated answer。
* 输出是什么：统一的 `EvaluationResult`。
* 在项目中的作用：让评估体系可以从“单一指标来源”升级为“多指标、多后端综合评估”。

### 文件：`src/libs/evaluator/evaluator_factory.py`

* 主要职责：根据配置创建 evaluator。
* 本阶段变化：
  * 新增 `"composite"` provider。
  * 当 `evaluation.backends` 不为空时，自动创建 `CompositeEvaluator`。
  * 每个 backend 仍然通过已有注册表创建，保持可插拔。
* 在项目中的作用：让配置可以这样表达组合评估：

```yaml
evaluation:
  enabled: true
  provider: composite
  backends:
    - ragas
    - custom
```

### 文件：`src/core/settings.py`

* 主要职责：定义项目配置结构。
* 本阶段变化：`EvaluationSettings` 增加 `backends: list[str]`。
* 为什么默认是空列表：为了兼容旧配置。旧配置只有 `provider: custom` 时，项目仍然按单 evaluator 创建。

### 文件：`tests/unit/test_composite_evaluator.py`

* 主要职责：证明组合评估器的行为可靠。
* 覆盖内容：
  * 多个 evaluator 的指标能合并。
  * 重复指标不会互相覆盖。
  * 一个 evaluator 失败时，其他成功结果仍会返回。
  * 所有 evaluator 都失败时，抛出明确错误。
  * factory 可以通过 `evaluation.backends` 创建组合评估器。
  * trace 中能记录组合评估摘要。

## 5. 新手重点理解

`CompositeEvaluator` 的核心思想是“统一入口，多路评估”。

为什么要组合多个 evaluator？因为不同 evaluator 关注的问题不同。`CustomEvaluator` 更像检索考试，关心有没有找对文档；`RagasEvaluator` 更像答案质量考试，关心回答是否忠实、相关、上下文是否有用。真实项目里通常需要把这些指标放在一起看，才能判断 RAG 整体效果。

为什么要并行执行？因为多个 evaluator 之间通常没有依赖关系。它们拿到同一份输入，各算各的指标。并行可以节省时间，尤其后面接入真实 Ragas 或 LLM 评估时，单个评估器可能会比较慢。

为什么某个 evaluator 失败时不直接让整体失败？因为评估体系应该尽量给出可用信息。比如 Ragas 因为依赖或模型问题失败了，但 CustomEvaluator 仍然能算出 hit_rate，这部分结果仍然有价值。只有全部 evaluator 都失败时，`CompositeEvaluator` 才会抛错。

为什么要处理重复指标名？两个 evaluator 可能都返回 `score`。如果直接合并，后面的会覆盖前面的。现在第一个保留原名，后续重复项加上 evaluator 类名前缀，这样不会丢数据。

这一阶段相当于给评估体系加了一个“汇总台”：后续 H3 的 EvalRunner 可以不用关心背后有几个评估器，只要调用一个统一的 `evaluate()`，就能拿到完整指标。


# 整体结构与流程
以下是对 composite_evaluator.py 代码文件的完整解析：

1. 文件定位
该文件位于项目的“可观测性与评估（observability/evaluation）”模块中，属于评估器（Evaluator）体系的核心组件。 核心职责：实现设计模式中的“组合模式（Composite Pattern）”。它允许将多个独立的子评估器（如忠实度、相关性等评估器）打包成一个整体，负责并发调度这些子评估器，收集它们的评估结果，合并指标数据，处理潜在异常，并最终输出一个统一的评估报告。

2. 函数拆解
CompositeEvaluatorError (自定义异常类)
作用：当组合评估器完全无法产出有效结果（例如所有子评估器都执行失败）时抛出。
CompositeEvaluator.init (初始化方法)
输入：evaluators (子评估器列表)，max_workers (最大并发线程数，可选)。
作用：校验传入的评估器列表不能为空，并将评估器列表和线程数配置保存到实例属性中，为后续并发执行做准备。
CompositeEvaluator.evaluate (核心评估方法)
输入：query (查询语句)，retrieved_ids (检索到的文档ID)，golden_ids (标准答案文档ID)，generated_answer (生成的回答)，trace (链路追踪对象)。
输出：EvaluationResult (包含合并后指标和详细信息的评估结果对象)。
作用：使用线程池并发执行所有子评估器的评估任务，收集成功结果与失败错误，合并指标，构建详细日志，并记录追踪信息。
_evaluator_label (辅助函数)
输入：evaluator (评估器实例)，index (索引)。
输出：字符串标签（如 "1:FaithfulnessEvaluator"）。
作用：为每个评估器生成一个带有顺序编号的唯一标识，方便在最终结果中区分指标来源。
_merge_metrics (辅助函数)
输入：target (目标总指标字典)，metrics (当前评估器产出的指标字典)，evaluator_label (评估器标签)。
作用：将当前评估器的指标合并到总指标字典中。如果多个评估器产出了同名的指标键，会自动为后续冲突的键加上评估器类名前缀（如 FaithfulnessEvaluator.faithfulness），防止数据覆盖。
3. 执行流程
初始化阶段：实例化 CompositeEvaluator，传入配置好的多个子评估器实例。
任务分发：调用 evaluate 方法时，内部创建 ThreadPoolExecutor 线程池，将每个子评估器的 evaluate 任务提交到线程池中并发执行。
结果收集：通过 as_completed 监听线程池任务完成情况。如果子评估器执行成功，将其结果存入 results 列表；如果抛出异常，则捕获异常并存入 errors 列表，保证单个评估器的失败不会导致整个流程中断。
结果合并：将所有成功的结果按原始提交顺序排序，提取各自的指标（metrics）和详情（details），并调用 _merge_metrics 将指标合并到一个全局字典中。
异常兜底：如果合并后的指标为空且存在错误记录，说明所有评估器都失败了，此时抛出 CompositeEvaluatorError。
构建输出：组装包含查询信息、各评估器详情、错误信息的 details 字典。如果传入了 trace 对象，则记录当前组合评估阶段的执行状态。
返回结果：返回封装了最终合并指标和详细信息的 EvaluationResult 对象。
4. 场景示例
假设我们正在评估一个 RAG（检索增强生成）系统的回答质量，配置了三个子评估器：

FaithfulnessEvaluator（忠实度评估）：检查回答是否基于检索内容。
AnswerRelevancyEvaluator（相关性评估）：检查回答是否切题。
ContextPrecisionEvaluator（上下文精确度评估）：检查检索内容是否精准。
业务场景： 用户提问：“Python的GIL是什么？” 系统检索了文档，并生成了回答。我们将这些数据传入 CompositeEvaluator.evaluate()。

全流程串联：

组合评估器启动 3 个线程，分别运行上述三个子评估器。
FaithfulnessEvaluator 顺利执行完毕，返回指标 {"faithfulness": 0.9}。
AnswerRelevancyEvaluator 也顺利执行，返回指标 {"relevancy": 0.85}。
ContextPrecisionEvaluator 因为网络超时抛出异常。组合评估器捕获该异常，将其记录到 errors 列表中，但不中断整体流程。
所有线程执行完毕后，组合评估器对前两个成功的结果进行指标合并。由于指标名不冲突，merged_metrics 变为 {"faithfulness": 0.9, "relevancy": 0.85}。
因为还有成功的指标，不会抛出全局异常。
组合评估器构建 details，里面清晰记录了前两个评估器的得分，以及第三个评估器超时的错误信息。
最终返回 EvaluationResult。开发者或监控系统拿到这个结果后，既能看到综合的得分情况，又能通过 details 快速定位是哪个子评估器出现了问题，实现了高内聚、高容错的评估机制。