# H4_evaluation_panel 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 Dashboard 里的 `Evaluation Panel` 页面。

前面 H3 已经有了 `EvalRunner` 和 `scripts/evaluate.py`，可以通过命令行运行 golden test set 评估。H4 做的是把这套评估能力搬到可视化后台里，让用户不用敲命令，也能在 Dashboard 页面上选择测试集、运行评估、查看指标和每条测试用例的明细。

通俗理解，H3 是“命令行版自动考试”，H4 是“网页上的考试面板”。用户可以在页面里指定 `golden_test_set.json`，点击按钮后，系统会跑评估并展示成绩。

这一阶段在 RAG 项目中的位置是“评估结果可视化”。它不负责计算指标本身，而是负责把评估运行入口和评估结果展示出来。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/dashboard/pages/evaluation_panel.py` | 实现 Dashboard 评估面板页面，支持运行评估并展示结果 |
| `src/observability/dashboard/services/evaluation_service.py` | 新增 Dashboard 服务层，负责加载配置、创建 HybridSearch 和 evaluator、调用 EvalRunner |
| `tests/unit/test_dashboard_app.py` | 增加 Evaluation Panel 页面渲染测试 |
| `tests/unit/test_dashboard_evaluation_service.py` | 新增 EvaluationService 连接测试 |
| `DEV_SPEC.md` | 更新 H4 任务进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步自动开发进度表 |

## 3. 核心调用关系

```text
Dashboard app
  -> evaluation_panel.render(st)
  -> 用户填写 golden test set 路径和 top_k
  -> 点击 Run Evaluation
  -> EvaluationService.run_evaluation()
  -> load_settings()
  -> 创建 HybridSearch
  -> EvaluatorFactory.create(settings)
  -> EvalRunner.run(test_set_path)
  -> 返回 EvalReport.to_dict()
  -> evaluation_panel 展示 metrics 和 case 明细
```

页面数据流可以理解成：

```text
用户输入 test_set_path / top_k
  -> EvaluationService
  -> EvalRunner
  -> report dict
  -> Summary Metrics
  -> Case Results 表格
  -> Case detail JSON
```

## 4. 每个核心文件的作用

### 文件：`src/observability/dashboard/pages/evaluation_panel.py`

* 主要职责：负责页面交互和展示。
* 关键函数：
  * `render()`：页面入口，显示标题、输入框、按钮，并触发评估。
  * `_top_k_input()`：读取 top_k 参数；如果是测试环境没有 `number_input`，就退回到 `text_input`。
  * `_render_report()`：展示评估报告，包括总体指标、测试集路径、case 数量和明细表。
  * `_case_row()`：把每条 case 的结果整理成表格行。
  * `_format_metric()`：把浮点指标格式化成四位小数。
* 输入是什么：Streamlit 对象、可选的 `EvaluationService`。
* 输出是什么：页面上的指标卡、表格、JSON 明细。
* 在项目中的作用：让评估体系可以通过 Dashboard 直接使用。

### 文件：`src/observability/dashboard/services/evaluation_service.py`

* 主要职责：把页面和底层评估流程隔开。
* 关键类：`EvaluationService`
* 关键函数：`run_evaluation()`
* 输入是什么：golden test set 路径、可选 top_k。
* 输出是什么：`EvalReport.to_dict()` 返回的字典。
* 内部做了什么：

```text
load_settings()
  -> HybridSearch(settings=settings)
  -> EvaluatorFactory.create(settings)
  -> EvalRunner(...)
  -> run(test_set_path)
  -> to_dict()
```

* 在项目中的作用：让页面代码不用知道具体怎么创建检索器、评估器和 EvalRunner。

### 文件：`tests/unit/test_dashboard_app.py`

* 主要职责：测试 Dashboard 页面不用真实 Streamlit 也能渲染。
* 本阶段变化：新增 `test_evaluation_panel_runs_and_renders_eval_report()`。
* 测试重点：
  * 页面标题正确。
  * 点击按钮后会调用 fake evaluation service。
  * 指标展示为 `1.0000`、`0.5000` 这种格式。
  * case 结果表格包含 query、retrieved_count、expected_count 和指标。
  * case 明细可以进入 expander。

### 文件：`tests/unit/test_dashboard_evaluation_service.py`

* 主要职责：测试 `EvaluationService` 是否正确串联底层对象。
* 测试重点：
  * 能加载 settings。
  * 能创建 HybridSearch。
  * 能通过 EvaluatorFactory 创建 evaluator。
  * 能把 top_k 和 test_set_path 传给 EvalRunner。
  * 最终返回 report 字典。

## 5. 新手重点理解

H4 的核心思想是“页面只做展示，业务逻辑放到 service”。

为什么不直接在 `evaluation_panel.py` 里写 `load_settings()`、`HybridSearch()`、`EvaluatorFactory.create()`？因为这样页面会变得很重，测试也很难写。现在把这些逻辑放到 `EvaluationService` 里，页面只负责用户交互和结果展示。

这种拆分有一个好处：测试页面时，可以注入 fake service，不需要真的连接向量库、加载模型或读取真实配置。测试 service 时，也可以 monkeypatch 掉 HybridSearch、EvaluatorFactory 和 EvalRunner，只验证 wiring 是否正确。

H4 还把 H3 的命令行能力变成了 Dashboard 能力：

```text
H3：python scripts/evaluate.py
H4：Dashboard -> Evaluation Panel -> Run Evaluation
```

它们背后用的是同一个 `EvalRunner`，所以不会出现“命令行一套逻辑、页面另一套逻辑”的重复实现。

这一阶段相当于给评估体系装上了“可视化操作台”：用户可以在页面里运行标准测试集，并直接看到整体成绩和每道题的详细结果。




# 整体结构与流程

文件定位
项目作用：该文件是 RAG（检索增强生成）系统可观测性仪表盘（Dashboard）中的一个前端页面，专门用于“评估（Evaluation）”模块。
所处层级：属于表现层（UI 层），基于 Streamlit 框架构建，直接面向用户（如算法工程师、测试人员）。
核心职责：提供可视化交互界面，允许用户配置测试集路径和检索参数（top_k），触发自动化评估任务，并直观展示评估的汇总指标与每个测试用例的详细结果。
函数拆解
render(st, evaluation_service)

作用：页面的主入口，负责渲染整个评估面板的 UI 并处理交互逻辑。
输入：st（Streamlit 模块或模拟对象），evaluation_service（评估服务实例，可选）。
输出：无（直接在页面上渲染 UI 组件）。
核心功能：初始化评估服务，渲染标题、文本输入框和运行按钮。当用户点击“运行评估”时，调用后端服务执行评估，捕获异常并调用 _render_report 展示结果。
_top_k_input(st)

作用：渲染 top_k（检索返回的文档数量）参数的输入控件。
输入：st。
输出：int，用户输入的 top_k 值。
核心功能：做兼容性处理。如果 st 支持 number_input 则渲染数字输入框，否则降级为普通的文本输入框。
_render_report(st, report)

作用：渲染评估报告的结果展示区。
输入：st，report（包含评估结果的字典）。
输出：无。
核心功能：解析报告中的汇总指标（Metrics）、用例结果（Case Results）和详情。使用卡片展示汇总指标，使用数据表格（Dataframe）展示所有用例的概览，并提供下拉框和折叠面板让用户查看单个用例的详细 JSON 数据。
_case_row(result)

作用：将单个用例的评估结果转换为数据表格中的一行数据。
输入：result（单个用例的结果字典）。
输出：dict，包含查询语句、检索数量、期望数量以及各项指标值。
核心功能：提取关键字段并调用 _format_metric 格式化指标，以便在表格中整齐展示。
_format_metric(value)

作用：统一格式化指标数值的显示样式。
输入：value（任意类型的指标值）。
输出：str，格式化后的字符串。
核心功能：如果是数字类型，则格式化为保留 4 位小数的字符串；否则直接转换为字符串。
执行流程
页面初始化：用户访问评估页面，触发 render 函数。render 初始化 EvaluationService，并渲染页面标题和输入控件（期间调用 _top_k_input 获取 top_k 设置）。
触发评估：用户配置好测试集路径和参数后，点击“Run Evaluation”按钮。
执行任务：render 函数调用 service.run_evaluation 执行后台评估任务，获取包含指标和用例结果的 report 字典。若发生异常，则在页面提示错误。
渲染报告：评估成功后，render 调用 _render_report 渲染结果。
展示概览：_render_report 提取汇总指标并渲染为指标卡片，同时渲染测试集基本信息。
展示明细：_render_report 遍历用例结果，调用 _case_row 构建表格行数据并渲染为数据表格。
查看详情：用户通过下拉框选择特定用例，页面展开对应的折叠面板，展示该用例的完整 JSON 详情。
场景示例
假设你是一名 RAG 系统的测试工程师，需要评估系统对“公司请假制度”相关问题的回答质量：

打开面板：你在 Dashboard 中点击进入“Evaluation Panel”页面。
配置参数：页面默认加载了标准测试集 golden_test_set.json，你将 top_k 保持为 0（使用系统默认配置）。
运行评估：点击“Run Evaluation”按钮。后台服务开始读取测试集中的问题（如“年假有多少天？”），在向量数据库中检索相关文档，并计算检索准确率和生成质量等指标。
查看汇总：评估完成后，页面顶部展示“Summary Metrics”，例如显示“平均准确率: 0.8500”。
查看用例表格：下方的“Case Results”表格列出了所有测试用例。你看到第一行是：Query="年假有多少天？"，检索到 3 个文档（retrieved_count=3），期望 2 个（expected_count=2），准确率="0.9000"。
深入排查：你觉得“年假有多少天？”这个用例的检索数量（3个）比期望（2个）多，想看看具体检索到了什么。于是你在下拉框选择“1. 年假有多少天？”，下方展开详细的 JSON 数据，你可以清晰地看到系统具体检索到了哪些 Chunk ID，以及各项细分指标的得分，从而帮助你优化检索策略。