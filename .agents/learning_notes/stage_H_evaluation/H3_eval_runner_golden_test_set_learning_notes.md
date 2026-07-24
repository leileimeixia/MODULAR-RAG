# H3_eval_runner_golden_test_set 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 `EvalRunner + Golden Test Set`。

前面 H1、H2 已经有了评估器：可以单独评估，也可以组合多个评估器一起评估。H3 进一步解决“怎么批量评估”的问题：项目现在可以读取一份 golden test set，也就是人工准备好的标准测试集，然后逐条运行检索流程，再把检索结果交给 evaluator 计算指标，最后汇总成一份评估报告。

通俗理解，golden test set 就像一套固定考题。每道题里写清楚：

* 用户会问什么问题。
* 正确情况下应该检索到哪些 chunk。
* 可选地记录期望来源、生成答案、过滤条件、top_k。

`EvalRunner` 就像自动阅卷器：它拿着这套题去跑当前 RAG 系统，然后看系统检索结果和标准答案之间差得多不多。

这一阶段在 RAG 项目中的位置是“评估运行层”。它不直接实现某个指标，而是把检索链路、测试集、评估器串起来，形成可重复运行的评估闭环。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/evaluation/eval_runner.py` | 实现 `EvalRunner`、`EvalCase`、`EvalCaseResult`、`EvalReport`，负责读取测试集、运行检索、调用 evaluator、聚合指标 |
| `src/observability/evaluation/__init__.py` | 导出 EvalRunner 相关类，方便外部统一导入 |
| `scripts/evaluate.py` | 新增命令行入口，可以通过命令运行 golden test set 评估 |
| `tests/fixtures/golden_test_set.json` | 新增示例 golden test set |
| `tests/unit/test_eval_runner.py` | 测试 EvalRunner 的读取、校验、检索调用和指标聚合 |
| `tests/unit/test_evaluate_cli.py` | 测试 `scripts/evaluate.py` 的成功输出和失败报错 |
| `DEV_SPEC.md` | 更新 H3 任务进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步自动开发进度表 |

## 3. 核心调用关系

```text
scripts/evaluate.py
  -> load_settings()
  -> 创建 HybridSearch
  -> EvaluatorFactory.create(settings)
  -> 创建 EvalRunner
  -> EvalRunner.run(golden_test_set.json)
  -> load_golden_test_set()
  -> 对每个 EvalCase 调用 HybridSearch.search()
  -> 提取 retrieved_ids
  -> evaluator.evaluate()
  -> 聚合所有 case 的 metrics
  -> 输出 EvalReport JSON
```

核心数据流是：

```text
golden_test_set.json
  -> EvalCase
  -> HybridSearch.search(query)
  -> RetrievalResult[]
  -> retrieved_ids
  -> evaluator.evaluate(retrieved_ids, expected_chunk_ids)
  -> EvalCaseResult
  -> EvalReport
```

## 4. 每个核心文件的作用

### 文件：`src/observability/evaluation/eval_runner.py`

* 主要职责：批量运行评估。
* 关键类：
  * `EvalCase`：表示一条标准测试用例。
  * `EvalCaseResult`：表示一条测试用例的评估结果。
  * `EvalReport`：表示整次评估的汇总报告。
  * `EvalRunner`：真正执行评估流程。
* 关键函数：
  * `load_golden_test_set()`：读取并校验 JSON 测试集。
  * `EvalRunner.run()`：运行所有测试用例并返回 `EvalReport`。
  * `_run_case()`：运行单条测试用例。
  * `_aggregate_metrics()`：把多条 case 的指标按平均值聚合。
* 输入是什么：配置、HybridSearch 实例、Evaluator 实例、golden test set 路径。
* 输出是什么：`EvalReport`，里面包含总体 metrics 和每条 case 的详细结果。
* 在项目中的作用：把“单次评估”升级成“批量回归评估”。

### 文件：`scripts/evaluate.py`

* 主要职责：提供命令行运行入口。
* 常见使用方式：

```bash
python scripts/evaluate.py
```

或者指定测试集和配置：

```bash
python scripts/evaluate.py --test-set tests/fixtures/golden_test_set.json --settings config/settings.yaml
```

* 输入是什么：命令行参数。
* 输出是什么：JSON 格式的评估报告。
* 在项目中的作用：让评估不只停留在代码 API，而是可以被人工、脚本或 CI 直接调用。

### 文件：`tests/fixtures/golden_test_set.json`

* 主要职责：提供一份示例 golden test set。
* 当前结构示例：

```json
{
  "test_cases": [
    {
      "query": "How do I configure Azure OpenAI?",
      "expected_chunk_ids": ["chunk_azure_openai_001"],
      "expected_sources": ["config_guide.pdf"],
      "generated_answer": "Configure the Azure OpenAI endpoint, deployment, and API key.",
      "top_k": 3
    }
  ]
}
```

* 在项目中的作用：作为后续真实评估集的模板。

### 文件：`tests/unit/test_eval_runner.py`

* 主要职责：保证 EvalRunner 行为稳定。
* 测试重点：
  * 能正确读取多条测试用例。
  * 能把 query、top_k、filters 传给 HybridSearch。
  * 能从检索结果中提取 chunk id。
  * 能把 retrieved ids 和 expected chunk ids 传给 evaluator。
  * 能把每条 case 的 metrics 聚合成总体 metrics。
  * 能拒绝空测试集和非法 expected ids。

### 文件：`tests/unit/test_evaluate_cli.py`

* 主要职责：保证命令行入口可用。
* 测试重点：
  * 成功时打印 JSON 报告。
  * 测试集缺失时返回错误码并打印 `Evaluation failed:`。

## 5. 新手重点理解

H3 的重点是“可重复评估”。

一次 RAG 查询跑通，只能说明系统在这一刻能用。但如果你改了检索策略、切块策略、embedding 模型、reranker 或 prompt，怎么知道效果有没有变好？这就需要固定测试集。

golden test set 的价值在于：它把“我觉得效果不错”变成“这批标准问题的指标是多少”。以后每次改代码，都可以重新跑同一套题，观察指标是否下降。

`EvalRunner` 不自己计算指标，而是调用 evaluator。这样设计是为了保持分工清楚：

```text
EvalRunner：负责批量组织评估流程
Evaluator：负责具体怎么算分
HybridSearch：负责怎么检索
```

这三个角色拆开后，后续扩展会比较轻松。比如以后要换评估器，不用改 EvalRunner；要换检索实现，也可以通过注入新的 hybrid_search 来测试。

这个阶段相当于给项目加了一条“自动考试流水线”：输入固定题库，运行当前 RAG 系统，输出可比较的成绩单。



用户要求对 eval_runner.py 文件做完整解析，按照四个部分进行说明。这是一个代码解析/文档说明类的需求，不需要修改代码文件。我需要：

文件定位：说明该文件在项目中的作用、所处层级与核心职责
函数拆解：逐个讲解每个函数的作用目的、输入输出与核心功能
执行流程：梳理各函数间的调用关系与完整运行链路
场景示例：用一个贴合业务的具体例子，把全流程从头到尾串联讲解
让我先分析这个文件的结构和内容：

文件定位：

这是评估运行器模块，属于 src/observability/evaluation/ 目录
核心职责是加载黄金测试集、执行检索、聚合评估指标
属于可观测性/评估层，用于对检索管道进行自动化评估
函数拆解：

EvalRunnerError - 自定义异常类
EvalCase - 数据类，表示一个评估用例
EvalCaseResult - 数据类，表示单个评估用例的结果
EvalReport - 数据类，表示聚合评估报告
EvalRunner.init - 初始化评估运行器
EvalRunner.run - 运行完整评估
EvalRunner._run_case - 运行单个评估用例
load_golden_test_set - 加载黄金测试集
_parse_case - 解析单个测试用例
_retrieval_id - 提取检索结果的chunk_id
_aggregate_metrics - 聚合指标
_default_top_k - 获取默认top_k值
执行流程： run() -> load_golden_test_set() -> _parse_case() -> _run_case() -> hybrid_search.search() -> _retrieval_id() -> evaluator.evaluate() -> _aggregate_metrics()

场景示例： 假设我们有一个RAG系统，需要评估其检索质量。我们准备了一个黄金测试集，包含用户问题和期望检索到的文档块ID。评估运行器会加载这些用例，对每个用例执行检索，然后用评估器计算指标（如精确率、召回率等），最后汇总成报告。

由于这是一个文档说明类的需求，不需要修改代码，我只需要输出解析说明即可。但根据格式要求，如果不需要修改代码，我应该直接输出说明文本。让我检查一下需求——用户要求"对当前代码文件做完整解析"，这是一个纯文档/说明需求，不需要代码修改。

我将按照要求的四个部分组织输出。



# `eval_runner.py` 完整解析

---

## 一、文件定位

| 维度 | 说明 |
|------|------|
| **文件路径** | `src/observability/evaluation/eval_runner.py` |
| **所属层级** | 可观测性层（Observability）→ 评估子模块（Evaluation） |
| **核心职责** | 充当"评估调度器"——加载黄金测试集、驱动检索管道执行、收集并聚合评估指标，最终输出一份完整的评估报告 |
| **在项目中的角色** | 相当于一个**自动化考试系统**：出题（测试集）、让考生答题（检索管道）、老师批改打分（评估器）、汇总成绩（评估报告） |

简单来说，这个文件是 **RAG 系统质量保障的核心组件**，用于回答"我的检索管道到底准不准"这个问题。

---

## 二、函数拆解

### 1. 数据类（Dataclass）

#### `EvalCase` — 评估用例
- **作用**：描述一个"考试题目"
- **字段**：
  - [query](file://d:\RAG\MODULAR-RAG-MCP-SERVER\scripts\query.py#L0-L0)：用户提问（题目）
  - `expected_chunk_ids`：期望检索到的文档块 ID（标准答案）
  - `expected_sources`：期望的来源（附加答案）
  - `generated_answer`：预生成的回答（可选，用于回答质量评估）
  - [top_k](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L0-L0)：该用例期望返回的 top_k 数量（可选，覆盖默认值）
  - `filters`：检索过滤条件（可选）

#### `EvalCaseResult` — 单个用例的评估结果
- **作用**：记录一道题的"答题情况"
- **字段**：
  - [query](file://d:\RAG\MODULAR-RAG-MCP-SERVER\scripts\query.py#L0-L0)：原始问题
  - `retrieved_ids`：实际检索到的文档块 ID
  - `expected_chunk_ids`：期望的文档块 ID
  - [metrics](file://d:\RAG\MODULAR-RAG-CLEAN-START\tests\unit\test_dashboard_app.py#L0-L0)：该用例的各项指标得分（如 Precision、Recall）
  - [details](file://d:\RAG\MODULAR-RAG-CLEAN-START\tests\unit\test_composite_evaluator.py#L0-L0)：额外细节信息

#### `EvalReport` — 聚合评估报告
- **作用**：整场"考试"的总成绩单
- **字段**：
  - [metrics](file://d:\RAG\MODULAR-RAG-CLEAN-START\tests\unit\test_dashboard_app.py#L0-L0)：所有用例的平均指标
  - `case_results`：每个用例的详细结果列表
  - [details](file://d:\RAG\MODULAR-RAG-CLEAN-START\tests\unit\test_composite_evaluator.py#L0-L0)：报告元信息（测试集路径、用例数量等）
- **方法**：[to_dict()](file://d:\RAG\MODULAR-RAG-MCP-SERVER\src\ingestion\pipeline.py#L105-L116) — 将报告序列化为 JSON 兼容的字典，方便持久化或展示

---

### 2. 核心类 [EvalRunner](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L67-L119)

#### `__init__(self, settings, hybrid_search, evaluator, top_k)`
- **作用**：初始化评估运行器，注入依赖
- **输入**：
  - [settings](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L0-L0)：全局配置对象
  - [hybrid_search](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L0-L0)：混合检索引擎实例
  - [evaluator](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L0-L0)：评估器实例（继承自 `BaseEvaluator`）
  - `top_k`：全局默认的返回数量
- **输出**：无（构造器）

#### `run(self, test_set_path) -> EvalReport`
- **作用**：**入口方法**，执行完整评估流程
- **输入**：`test_set_path` — 黄金测试集的 JSON 文件路径
- **输出**：`EvalReport` — 聚合评估报告
- **核心逻辑**：
  1. 调用 `load_golden_test_set()` 加载所有测试用例
  2. 对每个用例调用 [_run_case()](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L95-L119) 获取结果
  3. 调用 [_aggregate_metrics()](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L183-L188) 汇总指标
  4. 组装并返回 `EvalReport`

#### `_run_case(self, case) -> EvalCaseResult`
- **作用**：执行单个测试用例的评估
- **输入**：`EvalCase` 实例
- **输出**：`EvalCaseResult` 实例
- **核心逻辑**：
  1. 确定 [top_k](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L0-L0)（用例级 > 全局级 > 配置默认值）
  2. 调用 `hybrid_search.search()` 执行检索
  3. 用 [_retrieval_id()](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L174-L180) 提取检索结果的 chunk_id 列表
  4. 调用 `evaluator.evaluate()` 计算指标
  5. 组装并返回 `EvalCaseResult`

---

### 3. 辅助函数

#### `load_golden_test_set(path) -> list[EvalCase]`
- **作用**：从 JSON 文件加载并校验测试集
- **输入**：文件路径
- **输出**：`EvalCase` 列表
- **核心逻辑**：
  1. 检查文件是否存在
  2. 读取 JSON，验证结构（必须有 `test_cases` 列表）
  3. 逐个调用 [_parse_case()](file://d:\RAG\MODULAR-RAG-CLEAN-START\src\observability\evaluation\eval_runner.py#L137-L171) 解析
  4. 确保至少有一个用例

#### `_parse_case(payload, index) -> EvalCase`
- **作用**：解析并校验单个测试用例的 JSON 数据
- **输入**：JSON 字典 + 用例索引（用于错误提示）
- **输出**：`EvalCase` 实例
- **校验规则**：
  - [query](file://d:\RAG\MODULAR-RAG-MCP-SERVER\scripts\query.py#L0-L0) 必须是非空字符串
  - `expected_chunk_ids` 必须是非空字符串列表
  - `expected_sources` 必须是字符串列表
  - `filters` 必须是字典

#### `_retrieval_id(result) -> str`
- **作用**：从检索结果中提取 chunk_id
- **输入**：`RetrievalResult` 对象或字典
- **输出**：chunk_id 字符串
- **兼容逻辑**：先尝试属性访问，再尝试字典键访问

#### `_aggregate_metrics(case_results) -> dict[str, float]`
- **作用**：将所有用例的指标按名称分组，计算平均值
- **输入**：`EvalCaseResult` 列表
- **输出**：`{指标名: 平均值}` 字典
- **示例**：`{"precision": 0.85, "recall": 0.72}`

#### `_default_top_k(settings) -> int`
- **作用**：从配置中读取默认的 top_k 值
- **输入**：配置对象
- **输出**：整数（默认 10）

---

## 三、执行流程
用户调用 │ ▼ EvalRunner.run(test_set_path) │ ├──► load_golden_test_set(path) │ │ │ ├── 读取 JSON 文件 │ ├── 校验结构（test_cases 列表） │ └── 逐个调用 _parse_case() → 返回 list[EvalCase] │ ├──► 对每个 case 调用 _run_case(case) │ │ │ ├── 确定 top_k（用例级 → 全局级 → 配置默认） │ │ │ ├── hybrid_search.search(query, top_k, filters) │ │ └── 返回检索结果列表 │ │ │ ├── 对每个结果调用 _retrieval_id() → 提取 chunk_id │ │ │ ├── evaluator.evaluate(query, retrieved_ids, golden_ids, ...) │ │ └── 返回 EvaluationResult（含 metrics 和 details） │ │ │ └── 组装 → EvalCaseResult │ ├──► _aggregate_metrics(case_results) │ └── 按指标名分组求平均 → dict[str, float] │ └──► 组装 → EvalReport（含聚合指标 + 逐用例结果 + 元信息）


---

## 四、场景示例

### 背景
假设你运营一个**企业知识库问答系统**，用户会问诸如"公司年假政策是什么？"之类的问题。你需要定期评估检索管道的质量。

### 准备测试集（`golden_test.json`）
```json
{
  "test_cases": [
    {
      "query": "公司年假政策是什么？",
      "expected_chunk_ids": ["chunk_001", "chunk_002"],
      "expected_sources": ["员工手册.pdf"],
      "top_k": 5
    },
    {
      "query": "如何申请报销？",
      "expected_chunk_ids": ["chunk_010", "chunk_011", "chunk_012"],
      "expected_sources": ["财务制度.pdf"],
      "top_k": 5
    }
  ]
}
执行评估
python
runner = EvalRunner(
    settings=config,
    hybrid_search=search_engine,
    evaluator=my_evaluator,
)
report = runner.run("golden_test.json")
全流程走一遍
第一步：加载测试集

load_golden_test_set() 读取 JSON，校验结构合法
_parse_case() 逐个解析，生成 2 个 EvalCase 对象
第二步：执行用例 1 — "公司年假政策是什么？"

_run_case() 被调用
top_k = 5（用例指定）
hybrid_search.search("公司年假政策是什么？", top_k=5) 执行检索
假设检索返回了 [chunk_001, chunk_003, chunk_002, chunk_099, chunk_050]
_retrieval_id() 提取出 ["chunk_001", "chunk_003", "chunk_002", "chunk_099", "chunk_050"]
evaluator.evaluate() 对比检索结果与标准答案 ["chunk_001", "chunk_002"]
假设评估器算出：precision=0.4（5个里命中2个），recall=1.0（2个标准答案都找到了）
生成 EvalCaseResult
第三步：执行用例 2 — "如何申请报销？"

同理，假设检索返回 [chunk_010, chunk_011, chunk_020]
对比标准答案 ["chunk_010", "chunk_011", "chunk_012"]
算出：precision=0.667（3个里命中2个），recall=0.667（3个标准答案找到2个）
第四步：聚合指标

_aggregate_metrics() 计算平均值：
precision = (0.4 + 0.667) / 2 = 0.533
recall = (1.0 + 0.667) / 2 = 0.833
第五步：输出报告

python
report.to_dict()
# 输出：
# {
#   "metrics": {"precision": 0.533, "recall": 0.833},
#   "case_results": [
#     {"query": "公司年假政策是什么？", "metrics": {"precision": 0.4, "recall": 1.0}, ...},
#     {"query": "如何申请报销？", "metrics": {"precision": 0.667, "recall": 0.667}, ...}
#   ],
#   "details": {"test_set_path": "golden_test.json", "case_count": 2}
# }
一句话总结
这个文件就是一个 "检索质量考试系统"：你给它一份标准答案（测试集），它自动让检索管道"答题"，然后用评估器"批改"，最后给你一份"成绩单"（评估报告），告诉你检索到底准不准、全不全。