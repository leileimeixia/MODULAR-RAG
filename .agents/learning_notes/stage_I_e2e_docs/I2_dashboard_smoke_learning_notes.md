# I2_dashboard_smoke 学习笔记

## 1. 本阶段完成了什么

本阶段新增了 Dashboard 冒烟测试：`tests/e2e/test_dashboard_smoke.py`。

Dashboard 现在已经有 6 个页面：

* System Overview
* Data Browser
* Ingestion Manager
* Ingestion Traces
* Query Traces
* Evaluation Panel

I2 的目标不是检查每个按钮的全部细节，而是确认这些页面在有基本数据时能正常渲染，不会出现 Python 异常。这类测试叫 smoke test，也就是“冒烟测试”：先确认系统点火能起来，没有明显爆炸，再做更细的测试。

当前测试使用 Streamlit 官方的 `AppTest`。如果本地没有安装 `streamlit`，测试会明确 `skip`，避免非 Dashboard 环境因为可选依赖缺失而失败；如果安装了 `streamlit`，它会真实运行页面渲染。

这一阶段在项目中的位置是“端到端验收与可复现性”。它帮助确认 Dashboard 作为用户入口可以正常加载。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `tests/e2e/test_dashboard_smoke.py` | 新增 Dashboard 冒烟测试，使用 Streamlit AppTest 渲染 6 个页面 |
| `DEV_SPEC.md` | 更新 I2 任务进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步自动开发进度表 |

## 3. 核心调用关系

```text
pytest tests/e2e/test_dashboard_smoke.py
  -> 如果没有 streamlit：skip
  -> 如果有 streamlit：
      -> 生成临时 dashboard_smoke_app.py
      -> AppTest.from_file(smoke_app)
      -> app.run(timeout=10)
      -> 顺序调用 6 个 Dashboard 页面 render()
      -> 断言没有 app.exception
      -> 断言 6 个页面标题都出现
```

页面渲染的数据流是：

```text
FakeConfigService / FakeDataService / FakeIngestionService / FakeTraceService / FakeEvaluationService
  -> 各 Dashboard 页面 render()
  -> Streamlit AppTest 捕获页面元素
  -> 测试断言 title 列表和异常状态
```

## 4. 每个核心文件的作用

### 文件：`tests/e2e/test_dashboard_smoke.py`

* 主要职责：验证 Dashboard 6 个页面能在 Streamlit 测试环境中正常渲染。
* 关键对象：
  * `AppTest`：Streamlit 提供的页面测试工具。
  * `FakeConfigService`：给 Overview 页面提供配置和数据统计。
  * `FakeDataService`：给 Data Browser 页面提供文档、chunk 和图片数据。
  * `FakeIngestionService`：给 Ingestion Manager 页面提供文档列表。
  * `FakeTraceService`：给 Ingestion Traces 和 Query Traces 页面提供 trace 数据。
  * `FakeEvaluationService`：给 Evaluation Panel 页面提供评估报告。
* 关键测试：
  * `test_dashboard_pages_render_without_python_exceptions()`
* 输入是什么：临时生成的 Streamlit app 文件。
* 输出是什么：pytest 通过、失败或在无 Streamlit 时 skip。
* 在项目中的作用：确保 Dashboard 页面整体可以加载，避免页面级 Python 异常进入主分支。

### 文件：`src/observability/dashboard/app.py`

* I2 没有修改它，但测试覆盖了它注册的 6 个页面。
* 主要职责：定义 Dashboard 页面入口和导航顺序。
* 关键函数：
  * `page_specs()`：返回页面列表。
  * `main()`：启动 Streamlit dashboard。
* 在项目中的作用：把各个 Dashboard 页面组织成一个完整应用。

### Dashboard 页面文件

I2 测试覆盖这些页面：

| 页面文件 | 页面作用 |
| --- | --- |
| `overview.py` | 展示系统配置和数据统计 |
| `data_browser.py` | 浏览已入库文档、chunk 和图片 |
| `ingestion_manager.py` | 上传、摄取和管理文档 |
| `ingestion_traces.py` | 查看摄取链路 trace |
| `query_traces.py` | 查看查询链路 trace、检索和 rerank 细节 |
| `evaluation_panel.py` | 运行 golden test set 评估并展示指标 |

## 5. 新手重点理解

冒烟测试的重点是“快速确认页面能不能跑起来”。

为什么不用真实数据？因为 Dashboard 页面会依赖配置、向量库、trace 文件、文档索引、评估器等很多外部状态。如果冒烟测试直接依赖这些真实数据，就容易变慢、变脆弱。这里使用 fake service，给每个页面提供最小可用数据，让测试重点放在页面渲染本身。

为什么要用 Streamlit `AppTest`？因为直接调用 `render(fake_st)` 更像单元测试，而 `AppTest` 会更接近真实 Streamlit 执行环境。它可以捕获页面元素和异常，适合做页面级 E2E 冒烟测试。

为什么没安装 Streamlit 时要 skip？因为这个项目允许在非 Dashboard 环境跑核心测试。Streamlit 是 Dashboard 功能需要的依赖，不应该让所有开发任务都被这个可选依赖卡住。但一旦安装了 Streamlit，这个测试就会真正执行。

这一阶段相当于给 Dashboard 加了一道开门检查：至少能确认 6 个页面都能加载，没有明显的 Python 异常。



# 整体架构与流程

文件定位
文件路径：tests/e2e/test_dashboard_smoke.py

作用与层级： 该文件属于项目中的端到端（E2E）测试层，专门用于对基于 Streamlit 构建的可视化仪表板（Dashboard）进行冒烟测试（Smoke Test）。

核心职责： 它的核心职责是“保底”——确保仪表板的所有核心页面（系统概览、数据浏览、摄入管理、摄入追踪、查询追踪、评估面板）在加载和渲染时，不会抛出任何 Python 异常（如语法错误、模块缺失、类型错误等）。它通过模拟数据来隔离外部依赖，从而快速验证 UI 代码的基本可用性。

函数拆解
1. test_dashboard_pages_render_without_python_exceptions(tmp_path)
作用目的：这是 pytest 识别并执行的核心测试用例，用于验证所有仪表板页面能否正常渲染。
输入：tmp_path（pytest 内置的 fixture，提供一个临时的空目录路径）。
输出：无直接返回值，通过 assert 断言来判定测试通过或失败。
核心功能：
环境检查：首先检查是否安装了 Streamlit 的测试模块（AppTest），如果没有则跳过测试，保证非 UI 环境下的测试兼容性。
生成测试应用：调用 _smoke_app_source() 获取动态生成的 Streamlit 源码，并将其写入临时目录下的 dashboard_smoke_app.py 文件中。
运行与断言：使用 AppTest 加载并运行这个临时应用（设置 10 秒超时）。运行结束后，断言应用没有抛出任何异常（not app.exception），并且页面上渲染出的标题（st.title）必须严格等于预期的 6 个页面标题。
2. _smoke_app_source()
作用目的：动态生成用于冒烟测试的 Streamlit 应用程序的 Python 源代码字符串。
输入：无。
输出：一段包含完整 Streamlit 渲染逻辑和 Mock 数据的 Python 代码字符串。
核心功能：
环境配置：生成的代码会自动将项目的 src 目录加入 sys.path，确保能正确导入业务模块。
定义 Mock 服务（Fake Services）：在生成的代码中定义了 5 个伪造的服务类（如 FakeConfigService, FakeDataService 等）。这些类实现了与真实业务服务相同的接口，但只返回写死的假数据（如假文档列表、假追踪记录等），从而避免测试时依赖真实的数据库或 LLM 服务。
调用渲染函数：在代码末尾，依次导入并调用 6 个页面模块（overview, data_browser 等）的 render 函数，并将对应的 Fake 服务实例传入，触发页面的实际渲染。
执行流程
测试触发：开发者运行 pytest，测试框架扫描到 test_dashboard_smoke.py 文件。
前置检查：执行 test_dashboard_pages_render_without_python_exceptions，检查 Streamlit 测试环境是否就绪。
源码生成：调用 _smoke_app_source()，在内存中拼接出一段包含 Mock 数据和页面渲染逻辑的 Streamlit 代码。
文件落盘：将这段代码写入 pytest 提供的临时目录中，生成一个真实的 .py 文件。
模拟运行：AppTest.from_file() 读取该文件，并在后台启动一个虚拟的 Streamlit 运行环境，执行其中的代码。
页面渲染：虚拟环境依次执行 6 个页面的 render 函数，页面组件（如标题、表格、图表）被渲染到虚拟 DOM 中。
结果校验：运行结束后，测试框架检查虚拟环境中是否捕获到异常，并核对渲染出的标题列表是否与预期的 6 个标题完全一致。一致则测试通过，否则失败。
场景示例
业务场景： 假设你是一名前端/全栈开发者，今天接到了一个新需求：在“数据浏览器（Data Browser）”页面增加一个“按文件类型筛选”的下拉框。你修改了 data_browser.py 的代码。

传统做法： 你需要手动启动 Streamlit 服务（streamlit run ...），打开浏览器，点击侧边栏的“Data Browser”，看看页面有没有报错，下拉框有没有显示。如果项目有 6 个页面，你每次改了一行代码，都要手动点一遍，非常繁琐。

使用本文件的自动化做法：

你修改完代码后，直接在终端运行 pytest tests/e2e/test_dashboard_smoke.py。
测试框架在后台“偷偷”生成了一个包含所有 6 个页面的 Streamlit 应用，并塞入了 FakeDataService 等假数据。
AppTest 就像一个不知疲倦的虚拟测试员，在后台瞬间把 6 个页面都“点”了一遍。
情况 A（你改错了）：如果你在新加的下拉框代码里把变量名拼错了（比如把 options 拼成了 optinos），虚拟测试员在渲染“Data Browser”时就会崩溃。测试框架会立刻捕获到这个异常，并标红报错，告诉你哪里出了问题。
情况 B（你改对了）：页面顺利渲染，虚拟测试员看到了“System Overview”、“Data Browser”等 6 个熟悉的标题，测试显示 PASSED（通过）。
总结：这个文件就像是一个自动化巡检机器人，每次代码提交后自动跑一遍，确保你的修改没有把仪表板的任何页面搞崩溃，极大地提升了开发效率和代码安全性。